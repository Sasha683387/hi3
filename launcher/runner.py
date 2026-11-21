import json
import os
import re
import shutil
import subprocess
import threading

from . import config, elyby
from . import __version__ as LAUNCHER_VER


class JavaNotFound(RuntimeError):
    pass


def find_java(preferred=""):
    if preferred and os.path.isfile(preferred):
        return preferred
    env = os.environ.get("JAVA_HOME", "")
    if env:
        cand = os.path.join(env, "bin", "java" + (".exe" if os.name == "nt" else ""))
        if os.path.isfile(cand):
            return cand
    found = shutil.which("java")
    if found:
        return found
    if os.name == "nt":
        import glob

        patterns = [
            r"C:\Program Files\Java\*\bin\java.exe",
            r"C:\Program Files (x86)\Java\*\bin\java.exe",
            r"C:\Program Files\Eclipse Adoptium\*\bin\java.exe",
            r"C:\Program Files\Microsoft\jdk*\bin\java.exe",
        ]
        for pat in patterns:
            hits = sorted(glob.glob(pat))
            if hits:
                return hits[-1]
    raise JavaNotFound(
        "Java не найдена. Установи Java 17+ (Adoptium) или укажи путь в настройках."
    )


def java_major(java_path):
    try:
        out = subprocess.run(
            [java_path, "-version"],
            capture_output=True,
            timeout=20,
            text=True,
        ).stderr
    except (OSError, subprocess.TimeoutExpired):
        return 0
    m = re.search(r'version "(\d+)', out)
    if m:
        return int(m.group(1))
    if "1.8" in out:
        return 8
    return 0


def required_java_major(meta):
    compat = meta.get("javaVersion") or {}
    return int(compat.get("majorVersion") or 8)


def _substitute(arg, ctx):
    if isinstance(arg, str):
        if arg in ctx:
            return ctx[arg]
        for key, val in ctx.items():
            if key in arg:
                arg = arg.replace(key, val)
        return arg
    return arg


def _classic_args(meta):
    line = meta.get("minecraftArguments") or ""
    return line.split(" ") if line else []


def _modern_args(meta, ctx, kind, os_key=None):
    out = []
    for part in (meta.get("arguments") or {}).get(kind, []):
        if isinstance(part, str):
            out.append(_substitute(part, ctx))
        elif isinstance(part, dict):
            rules = part.get("rules")
            if rules:
                from . import installer as _inst
                if not _inst._rules_ok(rules, os_key or "linux"):
                    continue
            val = part.get("value", "")
            if isinstance(val, list):
                out.extend(_substitute(v, ctx) for v in val)
            else:
                out.append(_substitute(val, ctx))
    return out


def classpath_for(meta, os_key):
    from . import installer

    libs = []
    for lib in meta.get("libraries", []):
        if not installer._rules_ok(lib.get("rules"), os_key):
            continue
        dl = lib.get("downloads", {})
        art = dl.get("artifact")
        if art and art.get("path"):
            libs.append(os.path.join(config.LIBS_DIR, art["path"].replace("/", os.sep)))
        else:
            maven = lib.get("name", "").split(":")
            if "url" in lib and len(maven) == 3:
                group, name, ver = maven
                rel = "%s/%s/%s/%s-%s.jar" % (
                    group.replace(".", "/"), name, ver, name, ver,
                )
                libs.append(os.path.join(config.LIBS_DIR, rel.replace("/", os.sep)))
    return libs


def build_command(meta, account, settings, ram_gb=None, os_key=None):
    from . import installer

    os_key = os_key or installer.os_name()
    version_id = meta["id"]
    paths = meta.get("_paths") or {}
    vdir = os.path.join(config.VERSIONS_DIR, version_id)
    natives_dir = paths.get("natives") or os.path.join(vdir, "natives")
    jar_path = paths.get("jar") or os.path.join(vdir, "%s.jar" % version_id)

    asset_index_id = meta.get("assetIndex", {}).get("id", "legacy")

    libs = classpath_for(meta, os_key)
    libs.append(jar_path)
    separator = ";" if os.name == "nt" else ":"
    classpath = separator.join(libs)

    ctx = {
        "${auth_player_name}": account["name"],
        "${auth_uuid}": account["uuid"],
        "${auth_access_token}": account.get("token") or "0",
        "${auth_session}": account.get("token") or "0",
        "${auth_xuid}": account.get("xuid", "0"),
        "${clientid}": account.get("clientToken") or "sashalauncher",
        "${user_type}": "msa" if account.get("type") == "microsoft" else "legacy",
        "${version_name}": version_id,
        "${version_type}": "SashaLauncher",
        "${assets_index_name}": asset_index_id,
        "${game_directory}": config.GAME_DIR,
        "${assets_root}": config.ASSETS_DIR,
        "${game_assets}": os.path.join(config.ASSETS_DIR, "virtual", "legacy"),
        "${launcher_name}": "SashaLauncher",
        "${launcher_version}": LAUNCHER_VER,
        "${resolution_width}": "854",
        "${resolution_height}": "480",
        "${user_properties}": "{}",
        "${natives_directory}": natives_dir,
        "${library_directory}": config.LIBS_DIR,
        "${runtime_directory}": os.path.join(config.GAME_DIR, "runtime"),
        "${classpath}": classpath,
        "${classpath_separator}": separator,
    }

    ram = int(ram_gb or settings.get("ram_gb") or 4)
    jvm = [
        "-Xmx%dM" % (ram * 1024),
        "-Xms512M",
        "-XX:+UseG1GC",
        "-XX:G1NewSizePercent=20",
        "-Djava.library.path=" + natives_dir,
        "-Dorg.lwjgl.librarypath=" + natives_dir,
    ]
    log_file = paths.get("log")
    if log_file and os.path.exists(log_file):
        jvm.append("-Dlog4j.configurationFile=" + log_file)

    if account.get("type") == "elyby":
        try:
            jar = elyby.ensure_authlib_injector(config.AUTHLIB_DIR)
            jvm.append("-javaagent:%s=%s" % (jar, elyby.elyby_game_url()))
        except Exception:
            pass

    if meta.get("loader_type") in ("forge", "neoforge"):
        jvm.append("-Dforgewrapper.librariesDir=" + config.LIBS_DIR)
        jvm.append("-Dforgewrapper.minecraft=" + jar_path)
        inst = meta.get("loader_installer")
        if inst:
            jvm.append(
                "-Dforgewrapper.installer="
                + os.path.join(config.LIBS_DIR, inst.replace("/", os.sep))
            )

    jvm_args = _modern_args(meta, ctx, "jvm", os_key)
    if jvm_args:
        jvm.extend(jvm_args)
    meta_jvm_raw = " ".join(
        p if isinstance(p, str) else json.dumps(p.get("value", ""))
        for p in (meta.get("arguments") or {}).get("jvm", [])
    )
    if "-cp" not in jvm_args and "${classpath}" not in meta_jvm_raw:
        jvm.extend(["-cp", classpath])
    game_args = _modern_args(meta, ctx, "game", os_key)
    if not game_args:
        game_args = []
        for a in _classic_args(meta):
            if a.startswith("${"):
                game_args.append(ctx.get(a, a))
            else:
                game_args.append(a)

    main_class = meta.get("mainClass", "net.minecraft.client.main.Main")
    return jvm + [main_class] + game_args


def launch(meta, account, settings, ram_gb=None, on_stdout=None):
    java = find_java(settings.get("java_path", ""))
    cmd = [java] + build_command(meta, account, settings, ram_gb=ram_gb)
    proc = subprocess.Popen(
        cmd,
        cwd=config.GAME_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if on_stdout:
        def pump():
            for line in proc.stdout:
                on_stdout(line.rstrip("\n"))

        threading.Thread(target=pump, daemon=True).start()
    return proc
