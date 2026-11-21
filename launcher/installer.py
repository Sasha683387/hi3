import json
import os
import shutil
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor

from . import config, http_util, versions

RESOURCES_BASE = "https://resources.download.minecraft.net"
WORKERS = 24


class Cancelled(RuntimeError):
    pass


def os_name():
    return {"win32": "windows", "darwin": "osx"}.get(sys.platform, "linux")


def _rules_ok(rules, os_key):
    if not rules:
        return True
    result = None
    for rule in rules:
        action = rule.get("action")
        allowed = True
        if "os" in rule:
            o = rule["os"]
            if isinstance(o, dict):
                allowed = o.get("name") == os_key
            else:
                allowed = o == os_key
        elif "features" in rule:
            continue
        if allowed:
            result = action == "allow"
    return bool(result)


def _lib_filename(url):
    return url.rsplit("/", 1)[-1].split("?")[0]


def _artifact(lib):
    dl = lib.get("downloads", {})
    if dl.get("artifact"):
        return dl["artifact"]
    maven = lib.get("name", "").split(":")
    if "url" in lib and len(maven) == 3:
        group, name, ver = maven
        path = "%s/%s/%s/%s-%s.jar" % (
            group.replace(".", "/"), name, ver, name, ver,
        )
        return {"url": lib["url"].rstrip("/") + "/" + path, "path": path,
                "sha1": lib.get("sha1"), "size": 0}
    return None


def install_version(version_id, progress=None, cancel_check=None, os_key=None):
    """Ensure client jar / libs / assets / natives for this version exist.

    progress(stage, done, total, label). Returns version meta.
    """
    os_key = os_key or os_name()
    meta = versions.version_meta(version_id)

    def report(stage, done, total, label=""):
        if progress:
            progress(stage, done, total, label)
        if cancel_check and cancel_check():
            raise Cancelled()

    report("Старт", 0, 1, version_id)
    vdir = os.path.join(config.VERSIONS_DIR, version_id)
    os.makedirs(vdir, exist_ok=True)

    client = (meta.get("downloads") or {}).get("client")
    jar_path = os.path.join(vdir, "%s.jar" % version_id)
    if client:
        ok = os.path.exists(jar_path) and os.path.getsize(jar_path) == client.get(
            "size", -1
        )
        if not ok:
            http_util.download(
                client["url"],
                jar_path,
                sha1=client.get("sha1") or None,
                progress=lambda d, t: report(
                    "Клиент", d, t or client.get("size", 0), "client.jar"
                ),
            )

    jobs = []
    for lib in meta.get("libraries", []):
        if not _rules_ok(lib.get("rules"), os_key):
            continue
        art = _artifact(lib)
        native = (lib.get("downloads", {}).get("classifiers") or {}).get(
            "natives-%s" % os_key
        )
        for a in [art, native]:
            if a and a.get("url"):
                rel = a.get("path") or _lib_filename(a["url"])
                jobs.append((a, os.path.join(config.LIBS_DIR, rel.replace("/", os.sep))))

    total = len(jobs)
    for i, (art, dest) in enumerate(jobs):
        expected = art.get("size", 0) or 0
        ok = os.path.exists(dest) and os.path.getsize(dest) > 0 and (
            expected == 0 or os.path.getsize(dest) == expected
        )
        if not ok:
            http_util.download(
                art["url"],
                dest,
                sha1=art.get("sha1") or None,
                progress=lambda d, t: report(
                    "Библиотеки", i, total, _lib_filename(art["url"])
                ),
            )
        report("Библиотеки", i + 1, total, _lib_filename(art["url"]))

    natives_dir = os.path.join(vdir, "natives")
    natives_jars = [dest for _a, dest in jobs
                    if "natives-%s" % os_key in os.path.basename(dest)]
    if natives_jars:
        os.makedirs(natives_dir, exist_ok=True)
        marker = os.path.join(natives_dir, ".extracted")
        if not os.path.exists(marker):
            for nj in natives_jars:
                with zipfile.ZipFile(nj) as z:
                    for member in z.namelist():
                        if member.startswith("META-INF"):
                            continue
                        if not member.endswith((".dll", ".so", ".dylib", ".jnilib")):
                            continue
                        target = os.path.join(natives_dir, os.path.basename(member))
                        with z.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
            with open(marker, "w") as f:
                f.write(version_id)

    asset_index = meta.get("assetIndex")
    if asset_index:
        idx_dir = os.path.join(config.ASSETS_DIR, "indexes")
        os.makedirs(idx_dir, exist_ok=True)
        idx_path = os.path.join(idx_dir, asset_index["id"] + ".json")
        if not (os.path.exists(idx_path) and os.path.getsize(idx_path) > 10):
            http_util.download(
                asset_index["url"], idx_path, sha1=asset_index.get("sha1") or None
            )
        try:
            with open(idx_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        except (OSError, ValueError):
            http_util.download(asset_index["url"], idx_path)
            with open(idx_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)
        objects_dir = os.path.join(config.ASSETS_DIR, "objects")
        todo = {}
        for obj in index_data.get("objects", {}).values():
            dest = os.path.join(objects_dir, obj["hash"][:2], obj["hash"])
            if not os.path.exists(dest) or os.path.getsize(dest) != obj.get(
                "size", -1
            ):
                todo[obj["hash"]] = dest
        todo = list(todo.items())
        report("Ассеты", 0, len(todo), "ожидание")
        counter = [0]

        def fetch(item):
            h, dest = item
            http_util.download(http_util.resource_url(RESOURCES_BASE, h), dest)
            counter[0] += 1
            if counter[0] % 20 == 0 or counter[0] == len(todo):
                report("Ассеты", counter[0], len(todo), h[:12])
            return dest

        if todo:
            with ThreadPoolExecutor(max_workers=WORKERS) as ex:
                list(ex.map(fetch, todo))

    log_cfg = (meta.get("logging") or {}).get("client") or {}
    log_file = ""
    if log_cfg.get("file"):
        lf = log_cfg["file"]
        log_file = os.path.join(vdir, lf["id"])
        if not os.path.exists(log_file):
            http_util.download(lf["url"], log_file)

    report("Готово", 1, 1, version_id)
    meta["_paths"] = {"jar": jar_path, "natives": natives_dir, "log": log_file}
    return meta
