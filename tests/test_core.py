"""Smoke tests for the launcher core. Run: python3 tests/test_core.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher import config, http_util, offline, installer, runner, versions  # noqa: E402


def test_offline_uuid():
    a = offline.offline_account("Steve")
    b = offline.offline_account("Steve")
    assert a["uuid"] == b["uuid"]
    c = offline.offline_account("Alex")
    assert a["uuid"] != c["uuid"]
    assert a["uuid"].count("-") == 4 and len(a["uuid"]) == 36
    assert a["uuid"][14] == "3"
    try:
        offline.offline_account("--bad--")
        raise AssertionError("bad name allowed")
    except ValueError:
        pass
    print("offline uuid OK")


def test_rules():
    cases = [
        ([{"action": "allow", "os": {"name": "windows"}},
          {"action": "disallow", "os": {"name": "linux"}}], "linux", False),
        ([{"action": "allow", "os": {"name": "windows"}},
          {"action": "disallow", "os": {"name": "linux"}}], "windows", True),
        (None, "linux", True),
        ([{"action": "allow", "features": {"is_demo_user": True}}], "linux", False),
    ]
    for rules, os_key, expected in cases:
        got = installer._rules_ok(rules, os_key)
        assert got == expected, (rules, os_key, got)
    print("rules OK")


def test_manifest_and_meta():
    ids = versions.list_versions(snapshots=False)
    assert ids and all(isinstance(i, str) for i in ids)
    snap = versions.list_versions(snapshots=True)
    assert len(snap) >= len(ids)
    release = ids[0]
    meta = versions.version_meta(release)
    assert meta["id"]
    libs = [l for l in meta.get("libraries", [])
            if installer._rules_ok(l.get("rules"), "linux")]
    assert libs
    cmd = runner.build_command(
        meta,
        {"type": "offline", "name": "Steve", "uuid": "x", "token": "0"},
        {"ram_gb": 2},
    )
    assert cmd[0], "java path resolved"
    assert any(a.startswith("-Xmx2048M") for a in cmd), cmd[:4]
    assert "net.minecraft.client.main.Main" in cmd
    print("manifest/meta/command OK (version=%s, java=%s)" % (release, cmd[0]))


def test_fabric():
    from launcher import fabric, versions, runner

    fid = "fabric-loader-0.16.5-1.21.1"
    merged = fabric.merged_meta(fid)
    assert merged["id"] == fid
    assert "KnotClient" in merged["mainClass"]
    assert merged.get("downloads", {}).get("client")
    assert any(
        (l.get("url") or "").startswith("https://maven.fabricmc.net")
        for l in merged["libraries"]
    )
    cmd = runner.build_command(
        merged,
        {"type": "offline", "name": "Steve", "uuid": "x", "token": "0"},
        {"ram_gb": 2},
    )
    joined = " ".join(str(c) for c in cmd)
    assert "${" not in joined and "--username Steve" in joined
    assert "KnotClient" in joined
    print("fabric merge/command OK (%s)" % fid)


def test_loaders():
    from launcher import loaders, versions, runner

    for vid, mainmark in [
        ("forge-47.4.2-1.20.1", "forgewrapper"),
        ("neoforge-21.1.202-1.21.1", "forgewrapper"),
        ("quilt-0.26.4-1.21.1", "KnotClient"),
    ]:
        merged = loaders.merged_meta(vid)
        assert merged["id"] == vid
        assert mainmark in merged["mainClass"]
        assert merged.get("downloads", {}).get("client")
        assert merged.get("loader_installer") is not None or "quilt" in vid
        cmd = runner.build_command(
            merged,
            {"type": "offline", "name": "Steve", "uuid": "x", "token": "0"},
            {"ram_gb": 2},
        )
        joined = " ".join(str(c) for c in cmd)
        assert "${" not in joined and "--username Steve" in joined
        assert mainmark in joined
        cplibs = runner.classpath_for(merged, "windows" if os.name == "nt" else "linux")
        for lib in merged["libraries"]:
            if lib.get("x_download_only"):
                rel = (lib.get("downloads") or {}).get("artifact", {}).get("path", "")
                assert rel
                assert os.path.join(config.LIBS_DIR, rel.replace("/", os.sep)) not in cplibs, rel
        print(vid, "merge/command OK")
    forge = loaders.merged_meta("forge-47.4.2-1.20.1")
    dl_only = [
        (l.get("downloads") or {}).get("artifact", {}).get("path", "")
        for l in forge["libraries"]
        if l.get("x_download_only")
    ]
    assert any("ForgeAutoRenamingTool" in p for p in dl_only), dl_only
    assert any("asm-9.2" in p for p in dl_only), dl_only
    cmd = runner.build_command(
        forge,
        {"type": "offline", "name": "Steve", "uuid": "x", "token": "0"},
        {"ram_gb": 2},
    )
    joined = " ".join(str(c) for c in cmd)
    assert "ForgeAutoRenamingTool" not in joined
    assert "asm-9.2" not in joined and "asm-9.6" not in joined
    assert any(p.endswith("universal.jar") for p in dl_only), dl_only
    print("forge/neoforge/quilt merges OK")


def test_elyby_error_path():
    from launcher import elyby

    try:
        elyby.authenticate("test@example.com", "wrongpass")
        raise AssertionError("bad creds accepted")
    except elyby.YggError:
        pass
    print("elyby endpoint OK (authserver reached)")


def test_ms_invalid_client():
    from launcher import microsoft, http_util

    try:
        microsoft.start_device_code("00000000-0000-0000-0000-000000000000")
        raise AssertionError("invalid client accepted")
    except http_util.HttpError as e:
        assert e.code in (400, 401, 403)
    print("ms device endpoint OK (login.microsoftonline.com reached)")


if __name__ == "__main__":
    config.ensure_dirs()
    test_offline_uuid()
    test_rules()
    test_manifest_and_meta()
    test_fabric()
    test_loaders()
    test_elyby_error_path()
    test_ms_invalid_client()
    print("ALL CORE TESTS PASSED")
