"""«Лекарь» — предзапусковая проверка модов: дубли, несовместимости,
чужие загрузчики, повреждённые jar, зависимости (не хватает мода / версия
не подходит) и брошенные моды.

Без внешних баз знаний: всё читается прямо из jar (mods.toml /
fabric.mod.json) плюс маленькая таблица известных самых плохих пар.
"""

import json
import os
import re
import shutil
import zipfile

from . import config

_NUM = re.compile(r"\d+")

_RENDER_MODS = {"embeddium", "oculus", "rubidium", "sodium", "magnesium", "radium"}

# id зависимостей, которые не существуют как jar в папке mods
_SYSTEM_IDS = {
    "minecraft", "java", "javafml", "fml", "forge", "minecraftforge",
    "neoforge", "fabricloader", "fabric", "fabric-api", "quilt_loader",
    "quilted_fabric_api", "forgeconfig", "registryentryutils",
}

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
    "geckoanimfix": (
        "GeckoLibOculusCompat (geckoanimfix) больше не нужен: GeckoLib "
        "для 1.20.1+ уже содержит поддержку Iris/Oculus. Удали этот файл."
    ),
}

BAD_FILE_PATTERNS = ("rubidium",)


def _vt(s):
    return tuple(int(x) for x in _NUM.findall(s or ""))


def _one_ok(vt, r, ver):
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
        if not exact and lo_t and hi_t and lo_t == hi_t:
            exact = True
        if lo_t:
            if r[0] == "(" and vt <= lo_t:
                return False
            if r[0] != "(" and vt < lo_t:
                return False
        if exact:
            return ver == lo_s or (
                vt[: len(lo_t)] == lo_t and not re.search(r"[A-Za-z]", ver)
            )
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


def _range_ok(vt, r, ver=""):
    if not r or r == "*":
        return True
    if r[0] not in "([":
        toks = r.split()
        return all(_one_ok(vt, t, ver) for t in (toks or [r]))
    return _one_ok(vt, r, ver)


def version_ok(version, rng):
    rng = (rng or "").strip()
    if not rng or rng in ("*", "-", ""):
        return True
    vt = _vt(version)
    if not vt:
        return True
    return any(_range_ok(vt, alt.strip(), version) for alt in rng.split("||"))


def _forge_toml(txt):
    out = {"ids": [], "mc_range": None, "version": None, "deps": []}
    section = None
    dep_target = None
    optional = False
    for raw in txt.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r"\[\[(.*)\]\]", line)
        if m:
            key = m.group(1)
            if key == "mods":
                section = "mod"
            elif key.startswith("dependencies"):
                section = "dep"
            else:
                section = None
            dep_target = None
            optional = False
            continue
        if line.startswith("["):
            section = None
            dep_target = None
            optional = False
            continue
        m = re.match(r"modId\s*=\s*[\"']([^\"']+)[\"']", line)
        if m:
            if section == "mod":
                out["ids"].append(m.group(1))
            elif section == "dep":
                dep_target = m.group(1)
            continue
        if section == "mod" and out["version"] is None:
            m = re.match(r"version\s*=\s*[\"']([^\"']+)[\"']", line)
            if m:
                out["version"] = m.group(1)
                continue
        if section == "dep" and re.match(r"(type|mandatory)\s*=", line):
            optional = "optional" in line
            if not optional and re.search(r"mandatory\s*=\s*false", line):
                optional = True
            elif not optional and not re.search(r"(required|mandatory|true)", line):
                optional = True
            continue
        m = re.match(r"versionRange\s*=\s*[\"']([^\"']+)[\"']", line)
        if m and section == "dep" and dep_target and optional is not None:
            rng = m.group(1)
            if dep_target == "minecraft":
                if out["mc_range"] is None and not optional:
                    out["mc_range"] = rng
                continue
            out["deps"].append((dep_target, rng, not optional))
    return out


def read_info(path, loader_type=None):
    info = {
        "file": os.path.basename(path),
        "ids": [],
        "mc_range": None,
        "version": None,
        "deps": [],
        "broken": False,
        "fabric": False,
        "forge": False,
        "provided": [],
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
                d = _forge_toml(z.read(toml_name).decode("utf-8", "replace"))
                info["ids"].extend(i for i in d["ids"] if i)
                info["mc_range"] = d["mc_range"]
                if d["version"] and "${" not in d["version"]:
                    info["version"] = d["version"]
                info["deps"] = d["deps"]
            if "fabric.mod.json" in names:
                info["fabric"] = True
                try:
                    d = json.loads(
                        z.read("fabric.mod.json").decode("utf-8", "replace")
                    )
                except ValueError:
                    d = {}
                mid = d.get("id")
                if mid and str(mid) not in info["ids"]:
                    info["ids"].append(str(mid))
                v = d.get("version")
                if isinstance(v, str) and "${" not in v and not info["version"]:
                    info["version"] = v
                deps_raw = d.get("depends", {})
                if isinstance(deps_raw, dict):
                    for k, v in deps_raw.items():
                        if isinstance(k, str) and k not in info["ids"]:
                            rng = v if isinstance(v, (str, list)) else None
                            info["deps"].append(
                                (k, str(rng), True)
                            )
            if "quilt.mod.json" in names and not info["ids"]:
                try:
                    d = json.loads(
                        z.read("quilt.mod.json").decode("utf-8", "replace")
                    )
                except ValueError:
                    d = {}
                mid = (d.get("quilt_loader") or {}).get("id")
                if mid:
                    info["ids"].append(str(mid))
            provided = []
            for n in sorted(z.namelist()):
                if not n.endswith(".jar"):
                    continue
                if not (n.startswith("META-INF/jars/")
                        or n.startswith("META-INF/jarjar/")):
                    continue
                try:
                    import io

                    nested = {"ids": [], "version": None, "deps": []}
                    with zipfile.ZipFile(io.BytesIO(z.read(n))) as nz:
                        _ids_from_nested(nz, nested)
                except (zipfile.BadZipFile, OSError, ValueError):
                    continue
                for i in nested["ids"]:
                    if i and i not in provided and i not in info["ids"]:
                        provided.append(i)
                if nested["version"] and not info["version"]:
                    info["version"] = nested["version"]
                for dep in nested["deps"]:
                    if dep not in info["deps"]:
                        info["deps"].append(dep)
            if provided:
                if not info["ids"]:
                    info["ids"].extend(provided)
                else:
                    if "provided" not in info:
                        info["provided"] = []
                    for i in provided:
                        if i not in info["ids"] and i not in info["provided"]:
                            info["provided"].append(i)
    except (zipfile.BadZipFile, OSError):
        info["broken"] = True
    return info


def _ids_from_nested(z, info):
    names = set(z.namelist())
    for cand in ("META-INF/mods.toml", "META-INF/neoforge.mods.toml"):
        if cand in names:
            d = _forge_toml(z.read(cand).decode("utf-8", "replace"))
            for i in d["ids"]:
                if i and i not in info["ids"]:
                    info["ids"].append(i)
            if not info["version"] and d["version"]:
                info["version"] = d["version"]
            if d["deps"]:
                info["deps"] = info["deps"] + [
                    dep for dep in d["deps"] if dep not in info["deps"]
                ]
            return
    if "fabric.mod.json" in names:
        d = json.loads(z.read("fabric.mod.json").decode("utf-8", "replace"))
        mid = d.get("id")
        if mid and str(mid) not in info["ids"]:
            info["ids"].append(str(mid))
        v = d.get("version")
        if isinstance(v, str) and "${" not in v and not info["version"]:
            info["version"] = v


def _trash_path(fn, tdir):
    base, ext = os.path.splitext(fn)
    dst = os.path.join(tdir, fn)
    n = 1
    while os.path.exists(dst):
        dst = os.path.join(tdir, "%s(%d)%s" % (base, n, ext))
        n += 1
    return dst


def _mtime(info, mods_dir):
    try:
        return os.path.getmtime(os.path.join(mods_dir, info["file"]))
    except OSError:
        return 0.0


def _dep_findings(infos, by_id):
    findings = []
    ver_by_id = {}
    ins_by_id = {}
    for info in infos:
        for mid in list(info["ids"]) + list(info.get("provided") or []):
            for key in _peers(mid):
                ins_by_id.setdefault(key, info)
                if info.get("version"):
                    ver_by_id.setdefault(key, info["version"])
    for info in infos:
        owner = info["ids"][0] if info["ids"] else info["file"]
        for target, rng, required in info.get("deps") or []:
            key = (target or "").lower()
            if key in _SYSTEM_IDS or not key or key.startswith("fabric-"):
                continue
            installed = ins_by_id.get(key)
            if not installed:
                if required:
                    findings.append(
                        {
                            "level": "error",
                            "text": (
                                "Моду %r нужен мод %r версии %s — его нет в mods. "
                                "Лекарь попробует поставить его сам (или удали %s)"
                                % (owner, target, rng, info["file"])
                            ),
                            "files": [info["file"]],
                            "fix": [],
                            "missing": target,
                        }
                    )
                continue
            if not rng:
                continue
            tver = ver_by_id.get(key) or ""
            if not tver or "${" in tver:
                continue
            if not version_ok(tver, rng):
                if required:
                    findings.append(
                        {
                            "level": "error",
                            "text": (
                                "Несовместимость версий: %r требует %r %s, "
                                "а стоит %s (%s). Обнови %s или поставь %r"
                                % (
                                    owner, target, rng, tver, installed["file"],
                                    target, rng,
                                )
                            ),
                            "files": [installed["file"], info["file"]],
                            "fix": [info["file"]],
                        }
                    )
                else:
                    findings.append(
                        {
                            "level": "warn",
                            "text": (
                                "%r несовместим с %r (нужна %s, стоит %s) — "
                                "рекомендую удалить %s"
                                % (info["file"], target, rng, tver, target)
                            ),
                            "files": [info["file"], installed["file"]],
                            "fix": [installed["file"]],
                        }
                    )
    return findings


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
                    "fix": [fn],
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
        if key in ("geckoliboculuscompat", "geckoanimfix"):
            fix = list(files)
        else:
            fix = []
        findings.append(
            {"level": "warn", "text": _ADVICE[key], "files": files, "fix": fix}
        )

    for key, group in sorted(by_id.items()):
        if len(group) > 1:
            bad = [
                i["file"]
                for i in group
                if any(p in i["file"].lower() for p in BAD_FILE_PATTERNS)
            ]
            if not bad or len(bad) == len(group):
                newest = max(group, key=lambda i: (_mtime(i, mods_dir), i["file"]))
                bad = [i["file"] for i in group if i is not newest]
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
                    "fix": bad,
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
                    "fix": [info["file"]],
                }
            )

    findings.extend(_dep_findings(infos, by_id))

    if loader_type in ("forge", "neoforge"):
        for info in infos:
            if info["fabric"] and not info["forge"]:
                findings.append(
                    {
                        "level": "warn",
                        "text": "%s — это Fabric-мод, а запускаешь Forge: Forge просто не увидит его"
                        % info["file"],
                        "files": [info["file"]],
                        "fix": [],
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
                        "fix": [],
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
                    "fix": [info["file"]],
                }
            )
    return findings


def _norm(s):
    return re.sub(r"[\s_\-]+", "", (s or "").lower())


_SLUG_ALIASES = {
    "kotlinforge": ("kotlin-for-forge", "kotlinforforge"),
    "puzzlesapi": ("puzzles-lib",),
    "puzzleslib": ("puzzles-lib",),
    "architecturyapi": ("architectury-api",),
    "trashslot": ("trashslot",),
}

_ID_GROUPS = (
    {"kotlinforge", "kotlinforforge", "kotlin-for-forge"},
    {"puzzlesapi", "puzzleslib"},
)


def _peers(mid):
    low = (mid or "").lower()
    peers = {low}
    for g in _ID_GROUPS:
        if low in g:
            peers |= set(g)
    return peers


def _dep_targets(mods_dir, game_version, loader):
    targets = []
    for f in scan(mods_dir, game_version, loader):
        mt = f.get("missing")
        mt = [mt] if isinstance(mt, str) else (mt or [])
        for t in mt:
            if t.lower() not in _SYSTEM_IDS and t not in targets:
                targets.append(t)
    return targets


def _project_versions(mr, slug, game_version, loader):
    try:
        v = mr.versions_for(slug, game_version, loader)
        if v:
            return v
    except Exception:
        pass
    if loader and loader != "vanilla":
        try:
            return mr.versions_for(slug, game_version, None)
        except Exception:
            return []
    return []


def _resolve_dep(mr, modid, game_version, loader):
    """Пробует прямые slugs, потом поиск. Возвращает (версия | None, slug)."""
    low = (modid or "").lower()
    slug = re.sub(r"[^a-z0-9\-]+", "-", low).strip("-")
    cands = [low, slug]
    cands += list(_SLUG_ALIASES.get(low, ()))
    if low.startswith("fabric-") and not low.endswith("-api"):
        cands.append("fabric-api")
    ordered = []
    for c in cands:
        if c and c not in ordered:
            ordered.append(c)
    for c in ordered:
        v = _project_versions(mr, c, game_version, loader)
        if v:
            return v[0], c
    return None, None


def install_missing(mods_dir, game_version, loader="vanilla", log=None, skip=()):
    """Ставит недостающие обязательные зависимости с Modrinth.
    Возвращает (installed, failed, findings после пересканирования)."""
    import time as _t

    from . import modrinth as mr

    if log is None:
        log = lambda m: None
    if not os.path.isdir(mods_dir) or loader in (None, "vanilla") or not game_version:
        return [], [], scan(mods_dir, game_version, loader)
    skip_ids = {str(s).lower() for s in skip or ()}
    targets = [
        t for t in _dep_targets(mods_dir, game_version, loader)
        if t.lower() not in skip_ids
    ]
    installed, failed = [], []
    for modid in targets:
        try:
            log("ищу «%s» в Modrinth…" % modid)
            version, slug = _resolve_dep(mr, modid, game_version, loader)
            if version is None:
                version, slug = _search_dep(mr, modid, game_version, loader)
            if version is None:
                failed.append(
                    (modid, "нет на Modrinth (вероятно CurseForge-мод) — поставь сам или удали мод-проситель")
                )
                continue
            log("ставлю «%s» (%s)…" % (modid, slug))
            names = mr.install_from_version(
                version, game_version, loader, mods_dir
            )
            installed.append((modid, names))
            _t.sleep(1)
        except Exception as e:
            failed.append((modid, str(e)))
    return installed, failed, scan(mods_dir, game_version, loader)


def _search_dep(mr, modid, game_version, loader):
    """Фолбэк через поиск; возвращает (версия | None, slug)."""
    queries = [re.sub(r"[_\-]+", " ", modid), modid]
    n = _norm(modid)
    best = None
    best_score = 0
    for q in queries:
        try:
            hits = mr.search(
                q, 12, project_type="mod",
                game_version=game_version, loader=loader,
            )
            if not hits and loader not in (None, "vanilla"):
                hits = mr.search(
                    q, 12, project_type="mod", game_version=game_version,
                )
        except Exception:
            hits = []
        for h in hits:
            ns, nt = _norm(h.get("slug")), _norm(h.get("title"))
            if (not ns and not nt) or not n:
                continue
            if ns == n or nt == n:
                s = 2
            elif ns.startswith(n) or n.startswith(ns) or nt.startswith(n):
                s = 1
            else:
                s = 0
            if s > best_score:
                best, best_score = h, s
        if best_score >= 2:
            break
    if not best or best_score < 1:
        return None, None
    try:
        vlist = mr.versions_for(best["project_id"], game_version, loader)
    except Exception:
        vlist = []
    if not vlist and loader not in (None, "vanilla"):
        try:
            vlist = mr.versions_for(best["project_id"], game_version, None)
        except Exception:
            return None, None
    if not vlist:
        return None, None
    return vlist[0], best.get("slug")


def purge_failed(mods_dir, game_version, loader="vanilla", failed_targets=(),
                 fresh=()):
    """Карантинит моды, чьи обязательные зависимости поставить не удалось.
    Трогает только ошибки "missing"; fresh — файлы, только что поставленные
    Лекарем (их не выкидываем). Возвращает (fixed, оставшиеся)."""
    if not os.path.isdir(mods_dir) or not failed_targets:
        return [], scan(mods_dir, game_version, loader)
    bad = {t.lower() for t in failed_targets}
    fresh = {os.path.basename(f) for f in fresh or ()}
    tdir = os.path.join(config.APP_DIR, "trash")
    os.makedirs(tdir, exist_ok=True)
    fixed = []
    for f in scan(mods_dir, game_version, loader):
        mt = f.get("missing")
        mt = [mt] if isinstance(mt, str) else (mt or [])
        if not any(t.lower() in bad for t in mt):
            continue
        for fn in f.get("files") or []:
            if fn in fresh:
                continue
            src = os.path.join(mods_dir, fn)
            if not os.path.isfile(src):
                continue
            try:
                shutil.move(src, _trash_path(fn, tdir))
                fixed.append((fn, "зависимость не нашлась"))
            except OSError:
                pass
    return fixed, scan(mods_dir, game_version, loader)


def autofix(mods_dir, game_version, loader_type="vanilla"):
    """Убирает проблемные jar в корзину лаунчера и возвращает
    (список удалённых [(файл, уровень)], оставшиеся замечания)."""
    if not os.path.isdir(mods_dir):
        return [], []
    tdir = os.path.join(config.APP_DIR, "trash")
    os.makedirs(tdir, exist_ok=True)
    fixed = []
    for f in scan(mods_dir, game_version, loader_type):
        for fn in f.get("fix") or []:
            src = os.path.join(mods_dir, fn)
            if not os.path.isfile(src):
                continue
            try:
                shutil.move(src, _trash_path(fn, tdir))
                fixed.append((fn, f.get("level", "warn")))
            except OSError:
                pass
    if not fixed:
        return [], scan(mods_dir, game_version, loader_type)
    return fixed, scan(mods_dir, game_version, loader_type)
