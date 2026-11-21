"""Modrinth API v2: search mods and download with dependencies."""

import json
import os
import urllib.parse

from . import http_util

API = "https://api.modrinth.com/v2"


def search(query, limit=10, project_type="mod"):
    facets = [["project_type:%s" % project_type]]
    url = "%s/search?index=relevance&limit=%d&query=%s&facets=%s" % (
        API,
        limit,
        urllib.parse.quote(query or ""),
        urllib.parse.quote(json.dumps(facets)),
    )
    return http_util.request_json(url, timeout=25).get("hits", [])


def versions_for(project_id, game_version, loader="fabric"):
    url = "%s/project/%s/version?game_versions=%s&loaders=%s" % (
        API,
        project_id,
        urllib.parse.quote(json.dumps([game_version])),
        urllib.parse.quote(json.dumps([loader])),
    )
    return http_util.request_json(url, timeout=25)


def _primary_file(version):
    files = version.get("files") or []
    for f in files:
        if f.get("primary"):
            return f
    return files[0] if files else None


def build_plan(version, game_version, loader="fabric", seen=None, depth=0):
    """Resolve version -> [(url, filename, label)] including required deps."""
    plan = []
    seen = seen if seen is not None else set()
    f = _primary_file(version)
    if f:
        plan.append((f["url"], f["filename"], version.get("name") or f["filename"]))
    if depth >= 2:
        return plan
    for dep in version.get("dependencies", []):
        if dep.get("dependency_type") != "required" or not dep.get("project_id"):
            continue
        pid = dep["project_id"]
        if pid in seen:
            continue
        seen.add(pid)
        try:
            dv = versions_for(pid, game_version, loader)
            if dv:
                plan.extend(
                    build_plan(dv[0], game_version, loader, seen, depth + 1)
                )
        except Exception:
            continue
    return plan


def install(project_id, game_version, loader, dest_dir, seen=None):
    """Download mod + required deps to dest_dir. Returns installed names."""
    vlist = versions_for(project_id, game_version, loader)
    if not vlist:
        raise ValueError(
            "нет сборки %s для Minecraft %s (%s)" % (project_id, game_version, loader)
        )
    plan = build_plan(vlist[0], game_version, loader, seen=seen or set())
    os.makedirs(dest_dir, exist_ok=True)
    names = []
    for url, fname, label in plan:
        http_util.download(url, os.path.join(dest_dir, fname))
        names.append(fname)
    return names


def fmt_downloads(n):
    n = int(n or 0)
    if n >= 1_000_000:
        return "%.1fM" % (n / 1_000_000)
    if n >= 1000:
        return "%.0fK" % (n / 1000)
    return str(n)
