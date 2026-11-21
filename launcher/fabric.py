"""Fabric loader support: fetch meta, cache profiles, merge into launch metas."""

import os

from . import config, http_util, versions

META = "https://meta.fabricmc.net/v2"

_MAP_FILE = os.path.join(config.APP_DIR, "fabric_map.json")
_map_cache = None


def _map():
    global _map_cache
    if _map_cache is None:
        import json

        try:
            with open(_MAP_FILE, "r", encoding="utf-8") as f:
                _map_cache = json.load(f)
        except (OSError, ValueError):
            _map_cache = {}
    return _map_cache


def _save_map():
    import json

    tmp = _MAP_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(_map_cache, f, indent=2)
    os.replace(tmp, _MAP_FILE)


def loader_versions():
    data = http_util.request_json(META + "/versions/loader", timeout=20)
    return [v["version"] for v in data if v.get("version")]


def profile(game, loader):
    """Raw fabric profile JSON (inheritsFrom style), cached on disk."""
    vdir = os.path.join(config.VERSIONS_DIR, "fabric-loader-%s-%s" % (loader, game))
    path = os.path.join(vdir, "fabric-profile.json")
    if os.path.exists(path) and os.path.getsize(path) > 100:
        import json

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    url = "%s/versions/loader/%s/%s/profile/json" % (META, game, loader)
    data = http_util.request_json(url, timeout=30)
    os.makedirs(vdir, exist_ok=True)
    import json

    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)
    return data


def _game_from_id(version_id):
    m = _map().get(version_id)
    if m:
        return m[0], m[1]
    tail = version_id[len("fabric-loader-"):]
    try:
        for gid in versions.list_versions(snapshots=True):
            if tail.endswith("-" + gid):
                found = (gid, tail[: -len(gid) - 1])
                _map()[version_id] = found
                _save_map()
                return found
    except Exception:
        pass
    parts = tail.rsplit("-", 1)
    return (parts[1] if len(parts) == 2 else tail,
            parts[0] if len(parts) == 2 else "?")


def _merge(child, parent):
    merged = dict(parent)
    merged["id"] = child.get("id") or parent["id"]
    merged["mainClass"] = child.get("mainClass") or parent.get("mainClass")
    merged["libraries"] = list(parent.get("libraries", [])) + list(
        child.get("libraries", [])
    )
    args = dict(parent.get("arguments", {}))
    cargs = child.get("arguments", {})
    game = cargs.get("game")
    if game:
        args["game"] = game
    jvm = cargs.get("jvm")
    if jvm:
        args["jvm"] = list(args.get("jvm", [])) + list(jvm)
    if args:
        merged["arguments"] = args
    if not cargs and not child.get("minecraftArguments"):
        merged["minecraftArguments"] = parent.get("minecraftArguments", "")
    merged.pop("inheritsFrom", None)
    return merged


def merged_meta(version_id):
    """Resolve fabric-loader-<loader>-<game> id into a full launch meta."""
    game, loader = _game_from_id(version_id)
    child = profile(game, loader)
    parent = versions.version_meta(game)
    return _merge(child, parent)


def is_fabric(version_id):
    return version_id.startswith("fabric-loader-")
