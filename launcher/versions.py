import json
import os
import time

from . import config, http_util

MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
CACHE_TTL = 300


def manifest():
    try:
        if os.path.exists(config.MANIFEST_CACHE):
            age = time.time() - os.path.getmtime(config.MANIFEST_CACHE)
            if age < CACHE_TTL:
                with open(config.MANIFEST_CACHE, "r", encoding="utf-8") as f:
                    return json.load(f)
    except OSError:
        pass
    data = http_util.request_json(MANIFEST_URL, timeout=20)
    tmp = config.MANIFEST_CACHE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, config.MANIFEST_CACHE)
    return data


def list_versions(snapshots=False, ctype=None):
    items = []
    for v in manifest()["versions"]:
        if ctype and v["type"] != ctype:
            continue
        if not ctype and not snapshots and v["type"] != "release":
            continue
        items.append(v)
    return [v["id"] for v in items]


def version_entry(version_id):
    for v in manifest()["versions"]:
        if v["id"] == version_id:
            return v
    raise ValueError("Версия %s не найдена в манифесте Mojang" % version_id)


def version_meta(version_id):
    """Full version JSON, cached in game dir. Loader ids are merged."""
    from . import fabric as _fabric
    from . import loaders as _loaders

    if version_id.startswith("fabric-loader-"):
        return _fabric.merged_meta(version_id)
    if _loaders.is_loader(version_id):
        return _loaders.merged_meta(version_id)
    vdir = os.path.join(config.VERSIONS_DIR, version_id)
    meta_path = os.path.join(vdir, "%s.json" % version_id)
    if os.path.exists(meta_path) and os.path.getsize(meta_path) > 100:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    entry = version_entry(version_id)
    data = http_util.request_json(entry["url"], timeout=30)
    os.makedirs(vdir, exist_ok=True)
    tmp = meta_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, meta_path)
    return data


def has_version_json(version_id):
    p = os.path.join(config.VERSIONS_DIR, version_id, "%s.json" % version_id)
    return os.path.exists(p) and os.path.getsize(p) > 100
