"""Forge / NeoForge / Quilt loaders via Prism meta (MultiMC-style patches).

Modern Forge (1.13+) and NeoForge launch through ForgeWrapper: the Prism
meta supplies launch patches in Mojang-like shape, we merge them into the
vanilla Mojang meta and pass the -Dforgewrapper.* properties at launch.
"""

import json
import os

from . import config, http_util, versions

META = "https://meta.prismlauncher.org/v1"

TYPES = {
    "forge": "net.minecraftforge",
    "neoforge": "net.neoforged",
    "quilt": "org.quiltmc.quilt-loader",
}

FORGEWRAPPER_MAIN = "io.github.zekerzhayard.forgewrapper.installer.Main"

_MAP_FILE = os.path.join(config.APP_DIR, "loaders_map.json")
_map_cache = None


def _map():
    global _map_cache
    if _map_cache is None:
        try:
            with open(_MAP_FILE, "r", encoding="utf-8") as f:
                _map_cache = json.load(f)
        except (OSError, ValueError):
            _map_cache = {}
    return _map_cache


def _save_map():
    tmp = _MAP_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_map_cache, f, indent=2)
    os.replace(tmp, _MAP_FILE)


def version_id(loader_type, loader_ver, game):
    return "%s-%s-%s" % (loader_type, loader_ver, game)


def _parts(version_id):
    head = version_id.split("-", 1)
    if len(head) != 2 or head[0] not in TYPES:
        return None
    tail = head[1]
    parts = tail.rsplit("-", 1)
    if len(parts) != 2:
        return None
    return head[0], parts[0], parts[1]


def loader_versions(loader_type, game):
    if loader_type == "quilt":
        data = http_util.request_json(
            "https://meta.quiltmc.org/v3/versions/loader/%s" % game, timeout=25
        )
        return [
            v["loader"]["version"]
            for v in data
            if v.get("loader", {}).get("version")
        ]
    uid = TYPES[loader_type]
    data = http_util.request_json(META + "/" + uid + "/", timeout=25)
    out = []
    for v in data.get("versions", []):
        for r in v.get("requires") or []:
            if r.get("uid") == "net.minecraft" and r.get("equals") == game:
                if v.get("version") and v.get("type") in ("release", None, ""):
                    out.append(v["version"])
                break
    return out


QUILT_META = "https://meta.quiltmc.org/v3"


def _quilt_profile(loader_ver, game):
    vid = version_id("quilt", loader_ver, game)
    vdir = os.path.join(config.VERSIONS_DIR, vid)
    path = os.path.join(vdir, "loader-patch.json")
    if os.path.exists(path) and os.path.getsize(path) > 100:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    url = "%s/versions/loader/%s/%s/profile/json" % (QUILT_META, game, loader_ver)
    data = http_util.request_json(url, timeout=30)
    os.makedirs(vdir, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)
    return data


def patch(loader_type, loader_ver, game):
    if loader_type == "quilt":
        return _quilt_profile(loader_ver, game)
    vid = version_id(loader_type, loader_ver, game)
    vdir = os.path.join(config.VERSIONS_DIR, vid)
    path = os.path.join(vdir, "loader-patch.json")
    if os.path.exists(path) and os.path.getsize(path) > 100:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    uid = TYPES[loader_type]
    url = "%s/%s/%s.json" % (META, uid, loader_ver)
    data = http_util.request_json(url, timeout=30)
    os.makedirs(vdir, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)
    m = _map()
    m[vid] = [loader_type, loader_ver, game]
    _save_map()
    return data


def _normalize(entry):
    art = (entry.get("downloads") or {}).get("artifact") or {}
    if art.get("url") and not art.get("path"):
        from urllib.parse import urlparse

        p = urlparse(art["url"]).path.lstrip("/")
        art = dict(art, path=p)
        return dict(entry, downloads=dict(entry.get("downloads", {}), artifact=art))
    return entry


def _artifact_path(entry):
    art = (entry.get("downloads") or {}).get("artifact") or {}
    if art.get("path"):
        return art["path"]
    name = entry.get("name", "")
    p = name.split(":")
    if len(p) == 3 and "-" not in p[2]:
        return "%s/%s/%s/%s-%s.jar" % (
            p[0].replace(".", "/"), p[1], p[2], p[1], p[2]
        )
    return None


def _merge(version_id, loader_type, patch_meta, parent):
    merged = dict(parent)
    merged["id"] = version_id
    merged["loader_type"] = loader_type
    merged["loader_installer"] = None

    seen = set()
    libs = []
    for lib in list(parent.get("libraries", [])) + list(
        patch_meta.get("libraries", [])
    ) + [
        dict(m, x_download_only=True)
        for m in patch_meta.get("mavenFiles", [])
    ]:
        lib = _normalize(lib)
        k = _artifact_path(lib) or json.dumps(lib, sort_keys=True)
        if k in seen:
            continue
        seen.add(k)
        libs.append(lib)
        rel = _artifact_path(lib)
        if rel and rel.endswith("-installer.jar") and merged.get(
            "loader_installer"
        ) is None:
            merged["loader_installer"] = rel
    merged["libraries"] = libs

    merged["mainClass"] = patch_meta.get("mainClass") or parent.get("mainClass")
    if loader_type in ("forge", "neoforge"):
        if not merged.get("loader_installer"):
            raise ValueError(
                "сборка %s без installer.jar — попробуй другую версию загрузчика"
                % version_id
            )
    if patch_meta.get("minecraftArguments"):
        merged["minecraftArguments"] = patch_meta["minecraftArguments"]
        merged.pop("arguments", None)
    else:
        args = dict(parent.get("arguments", {}))
        cargs = patch_meta.get("arguments", {})
        if cargs:
            game_args = cargs.get("game")
            if game_args:
                args["game"] = game_args
            jvm = cargs.get("jvm")
            if jvm:
                args["jvm"] = list(args.get("jvm", [])) + list(jvm)
            merged["arguments"] = args
        merged.pop("minecraftArguments", None)
    merged.pop("inheritsFrom", None)
    return merged


def merged_meta(version_id):
    parsed = _parts(version_id)
    if not parsed:
        raise ValueError("неизвестный формат версии: %s" % version_id)
    loader_type, loader_ver, game = parsed
    p = patch(loader_type, loader_ver, game)
    if loader_type in ("forge", "neoforge") and p.get("mainClass") not in (
        FORGEWRAPPER_MAIN,
    ):
        raise ValueError(
            "Forge %s для Minecraft %s пока не поддерживается — работает Forge 1.13+"
            % (loader_ver, game)
        )
    parent = versions.version_meta(game)
    return _merge(version_id, loader_type, p, parent)


def resolve(version_id):
    m = _map().get(version_id)
    if m:
        return m
    p = _parts(version_id)
    if p:
        m = list(p)
        _map()[version_id] = m
        _save_map()
        return m
    return None


def is_loader(version_id):
    head = version_id.split("-", 1)
    return len(head) == 2 and head[0] in TYPES
