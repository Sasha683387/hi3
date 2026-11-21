"""Our curated modpack: top-600 mods for Minecraft 1.20.1 (Forge)."""

import json
import os

from . import config

PACK_MINECRAFT = "1.20.1"
PACK_LOADER = "forge"
PACK_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "modpack_%s_%s.json"
    % (PACK_MINECRAFT, PACK_LOADER)
)


def load():
    with open(PACK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def mods():
    return load().get("mods") or []


def download_all(progress, seen=None):
    """Install every pack mod via Modrinth. progress(done, total, slug).

    Returns list of failed slugs. Already-downloaded jars are skipped.
    """
    from . import modrinth

    ms = mods()
    seen = set() if seen is None else seen
    failed = []
    total = len(ms)
    for i, m in enumerate(ms, 1):
        progress(i, total, m.get("slug", "?"))
        try:
            modrinth.install(
                m["project_id"], PACK_MINECRAFT, PACK_LOADER, config.MODS_DIR,
                seen=seen,
            )
        except Exception:
            failed.append(m.get("slug", "?"))
    return failed
