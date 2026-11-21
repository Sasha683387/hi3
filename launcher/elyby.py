"""Ely.by account auth (Yggdrasil API) + authlib-injector support."""

import json
import time
import urllib.error
import urllib.request

AUTHSERVER = "https://authserver.ely.by"
AJ_LATEST = "https://authlib-injector.yushi.moe/artifact/latest.json"
AJ_DIR = "https://authserver.ely.by/api/authlib-injector"


class YggError(ValueError):
    @classmethod
    def from_response(cls, status, body):
        try:
            data = json.loads(body)
            msg = data.get("errorMessage") or body[:200]
        except ValueError:
            msg = body[:200] or "HTTP %s" % status
        return cls(msg)


def _ygg_request(url, payload):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "SashaLauncher/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise YggError.from_response(e.code, e.read().decode("utf-8", "replace"))


def authenticate(email, password):
    email = email.strip()
    password = password
    if not email or not password:
        raise ValueError("Введите email и пароль от аккаунта Ely.by")
    data = _ygg_request(
        AUTHSERVER + "/auth/authenticate",
        {
            "agent": {"name": "Minecraft", "version": 1},
            "username": email,
            "password": password,
            "clientToken": "sashalauncher",
            "requestUser": True,
        },
    )
    profile = data.get("selectedProfile") or (
        data.get("availableProfiles") or [None]
    )[0]
    if not profile:
        raise ValueError("У этого аккаунта Ely.by нет Minecraft-профиля")
    user = data.get("user", {})
    return {
        "type": "elyby",
        "name": profile["name"],
        "uuid": profile["id"],
        "token": data["accessToken"],
        "expires_at": 0,
        "clientToken": data.get("clientToken", "sashalauncher"),
        "ely_user_id": user.get("id", ""),
    }


def validate(token):
    try:
        _ygg_request(AUTHSERVER + "/auth/validate", {"accessToken": token})
        return True
    except YggError:
        return False


def refresh(account):
    data = _ygg_request(
        AUTHSERVER + "/auth/refresh",
        {
            "accessToken": account["token"],
            "clientToken": account.get("clientToken", "sashalauncher"),
            "requestUser": True,
        },
    )
    account["token"] = data["accessToken"]
    return account


def head_round_uuid(u):
    return u.replace("-", "")


def ensure_authlib_injector(dest, progress=None):
    """Download authlib-injector jar for Ely.by online-mode servers."""
    import os

    from . import config, http_util

    if os.path.exists(dest) and os.path.getsize(dest) > 100_000:
        return dest
    meta = http_util.request_json(AJ_LATEST)
    url = meta["download_url"]
    http_util.download(url, dest, progress=progress)
    return dest


def elyby_game_url():
    return AJ_DIR
