"""«Лекарь» — предзапусковая проверка модов: дубли, несовместимости,
чужие загрузчики, повреждённые jar и брошенные моды.

Без внешних баз знаний: всё читается прямо из jar (mods.toml /
fabric.mod.json) плюс маленькая таблица известных самых плохих пар.
"""

import json
import os
import re
import zipfile

_NUM = re.compile(r"\d+")

_RENDER_MODS = {"embeddium", "oculus", "rubidium", "sodium", "magnesium", "radium"}

_ADVICE = {
    "rubidium": (
        "Rubidium заброшен и вызывает сбои — используй Embeddium "
        "(регистрируется с тем же id 'rubidium', отсюда дубль). "
        "Удали rubidium-*.jar и оставь Embeddium."
    ),
    "geckoliboculuscompat": (
        "GeckoLibOculusCompat больше не нужен: GeckoLib для 1.20.1+ "
        "уже содержит поддержку Iris/Oculus. Удали этот файл."
    ),
}


def _vt(s):
    return tuple(int(x) for x in _NUM.findall(s or ""))


def _range_ok(vt, r):
    if not r or r == "*":
        return True
    if r[0] in "([":
        body = r.strip("[]()")
        if "," in body:
            lo_s, hi_s = body.split(",", 1)
            exact = False
        else:
            lo_s, hi_s = body.strip(), ""
            exact = True
        lo_t = _vt(lo_s)
        hi_t = _vt(hi_s)
        if lo_t:
            if r[0] == "(" and vt <= lo_t:
                return False
            if r[0] != "(" and vt < lo_t:
                return False
        if exact:
            return vt[: len(lo_t)] == lo_t
        if r.endswith(")"):
            return vt < hi_t if hi_t else True
        if r.endswith("]"):
            return bool(hi_t) and vt <= hi_t
        return True
    if r.startswith(">="):
        t = _vt(r[2:])
        return not t or vt >= t
    if r.startswith("<="):
        t = _vt(r[2:])
        return not t or vt <= t
    if r.startswith(">"):
        t = _vt(r[1:])
        return not t or vt > t
    if r.startswith("<"):
        t = _vt(r[1:])
        return not t or vt < t
    t = _vt(r.lstrip("~^="))
    return not t or vt[: len(t)] == t or vt >= t


def version_ok(version, rng):
    rng = (rng or "").strip()
    if not rng or rng in ("*", "-", ""):
        return True
    vt = _vt(version)
    if not vt:
        return True
    return any(_range_ok(vt, alt.strip()) for alt in rng.split("||"))


def _forge_toml(txt):
    ids = []
    mc_range = None
    section = None
    dep_target = None
    for raw in txt.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"\[\[(.*)\]\]$", line)
        if m:
            key = m.group(1)
            if key == "mods":
                section = "mod"
            elif key.startswith("dependencies"):
                section = "dep"
            else:
                section = None
            dep_target = None
            continue
        if line.startswith("["):
            section = None
            dep_target = None
            continue
        m = re.match(r"modId\s*=\s*[\"']([^\"']+)[\"']", line)
        if m:
            if section == "mod":
                ids.append(m.group(1))
            elif section == "dep":
                dep_target = m.group(1)
            continue
        m = re.match(r"versionRange\s*=\s*[\"']([^\"']+)[\"']", line)
        if m and section == "dep" and dep_target == "minecraft" and mc_range is None:
            mc_range = m.group(1)
    return ids, mc_range


def read_info(path, loader_type):
    info = {
        "file": os.path.basename(path),
        "ids": [],
        "mc_range": None,
        "broken": False,
        "fabric": False,
        "forge": False,
    }
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            toml_name = None
            if "META-INF/neoforge.mods.toml" in names:
                toml_name = "META-INF/neoforge.mods.toml"
            elif "META-INF/mods.toml" in names:
                toml_name = "META-INF/mods.toml"
            if toml_name:
                info["forge"] = True
                ids, rng = _forge_toml(z.read(toml_name).decode("utf-8", "replace"))
                info["ids"].extend(i for i in ids if i)
                info["mc_range"] = rng
            if "fabric.mod.json" in names:
                info["fabric"] = True
                try:
                    d = json.loads(z.read("fabric.mod.json").decode("utf-8", "replace"))
                except ValueError:
                    d = {}
                mid = d.get("id")
                if mid and str(mid) not in info["ids"]:
                    info["ids"].append(str(mid))
                dep = (d.get("depends") or {}).get("minecraft")
                dep = str(dep) if isinstance(dep, str) else None
                info["mc_range"] = info["mc_range"] or dep
            if "quilt.mod.json" in names and not info["ids"]:
                try:
                    d = json.loads(z.read("quilt.mod.json").decode("utf-8", "replace"))
                except ValueError:
                    d = {}
                mid = (d.get("quilt_loader") or {}).get("id")
                if mid:
                    info["ids"].append(str(mid))
    except (zipfile.BadZipFile, OSError):
        info["broken"] = True
    return info


def scan(mods_dir, game_version, loader_type="vanilla"):
    findings = []
    if not os.path.isdir(mods_dir):
        return findings
    jars = sorted(f for f in os.listdir(mods_dir) if f.lower().endswith(".jar"))
    infos = []
    for fn in jars:
        ipath = os.path.join(mods_dir, fn)
        info = read_info(ipath, loader_type)
        infos.append(info)
        if info["broken"]:
            findings.append(
                {
                    "level": "error",
                    "text": "%s повреждён или это не jar — удали его или переустанови" % fn,
                    "files": [fn],
                }
            )

    by_id = {}
    advised = set()
    for info in infos:
        for mid in info["ids"]:
            key = mid.lower()
            by_id.setdefault(key, []).append(info)
            advice = _ADVICE.get(key)
            if advice:
                advised.add(key)

    for key in sorted(advised):
        files = [i["file"] for i in infos if key in (m.lower() for m in i["ids"])]
        findings.append({"level": "warn", "text": _ADVICE[key], "files": files})

    for key, group in sorted(by_id.items()):
        if len(group) > 1:
            extra = (
                " %s" % _ADVICE[key]
                if key in _ADVICE
                else " Оставь один из них."
            )
            findings.append(
                {
                    "level": "error",
                    "text": "Дубль мода '%s': %s.%s"
                    % (key, ", ".join(i["file"] for i in group), extra),
                    "files": [i["file"] for i in group],
                }
            )

    for info in infos:
        rng = info.get("mc_range")
        if rng and not version_ok(game_version, rng):
            findings.append(
                {
                    "level": "error",
                    "text": "%s не для Minecraft %s (нужна версия %s) — удали его или поменяй версию игры"
                    % (info["file"], game_version or "?", rng),
                    "files": [info["file"]],
                }
            )

    if loader_type in ("forge", "neoforge"):
        for info in infos:
            if info["fabric"] and not info["forge"]:
                findings.append(
                    {
                        "level": "warn",
                        "text": "%s — это Fabric-мод, а запускаешь Forge: Forge просто не увидит его"
                        % info["file"],
                        "files": [info["file"]],
                    }
                )
    elif loader_type in ("fabric", "quilt"):
        for info in infos:
            if info["forge"] and not info["fabric"]:
                findings.append(
                    {
                        "level": "warn",
                        "text": "%s — это Forge-мод, а запускаешь Fabric: Forge-моды не работают на Fabric"
                        % info["file"],
                        "files": [info["file"]],
                    }
                )

    ids_all = set(by_id)
    for info in infos:
        if info["ids"] or not info["file"].lower().startswith("optifine"):
            continue
        if ids_all & _RENDER_MODS:
            findings.append(
                {
                    "level": "error",
                    "text": "%s (OptiFine) несовместим с Oculus/Embeddium/Sodium — оставь что-то одно (для модпаков рекомендуется Oculus)" % info["file"],
                    "files": [info["file"]],
                }
            )
    return findings
