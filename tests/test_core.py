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
    test_elyby_error_path()
    test_ms_invalid_client()
    print("ALL CORE TESTS PASSED")
