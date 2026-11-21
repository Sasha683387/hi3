"""Microsoft OAuth device-code login (Xbox Live -> XSTS -> Minecraft)."""

import time

from . import http_util

DEVICE_CODE_URL = (
    "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
)
TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
SCOPE = "XboxLive.signin offline_access"

XBL_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"


class LoginCancelled(RuntimeError):
    pass


def start_device_code(client_id):
    if not client_id:
        raise ValueError(
            "Не задан Azure client_id. Настройки → Microsoft: зарегистрируй "
            "бесплатное приложение на aka.ms/AzurePortalApps и вставь ID."
        )
    return http_util.request_form(
        DEVICE_CODE_URL,
        {"client_id": client_id, "scope": SCOPE},
    )


def wait_for_token(device, progress=None, client_id=""):
    deadline = time.time() + int(device.get("expires_in", 900))
    interval = max(1, int(device.get("interval", 5)))
    while time.time() < deadline:
        time.sleep(interval)
        try:
            tok = http_util.request_form(
                TOKEN_URL,
                {
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device["device_code"],
                    "client_id": client_id,
                },
            )
            if "access_token" in tok:
                return tok
        except http_util.HttpError as e:
            body = getattr(e, "code", 0)
            try:
                err = str(e).rsplit(":", 1)[-1]
            except Exception:
                err = ""
            if "authorization_pending" in err:
                if progress:
                    progress("Ожидаю вход в браузере...")
                continue
            if "slow_down" in err:
                interval += 5
                continue
            if "authorization_declined" in err:
                raise LoginCancelled("Вход отклонён") from None
            if "expired_token" in err:
                raise LoginCancelled("Код истёк, попробуйте снова") from None
            raise
    raise LoginCancelled("Код истёк, попробуйте снова")


def _xbl(msa_token):
    data = http_util.request_json(
        XBL_URL,
        method="POST",
        body={
            "Properties": {
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": "d=" + msa_token,
            },
            "RelyingParty": "http://auth.xboxlive.com",
            "TokenType": "JWT",
        },
    )
    return data["Token"]


def _xsts(xbl_token):
    try:
        data = http_util.request_json(
            XSTS_URL,
            method="POST",
            body={
                "Properties": {"UserTokens": [xbl_token]},
                "RelyingParty": "rp://api.minecraftservices.com/",
                "TokenType": "JWT",
            },
        )
    except http_util.HttpError as e:
        import re

        m = re.search(r"(\d{5})", str(e))
        if m:
            code = m.group(1)
            hints = {
                "2148916233": "Аккаунт Xbox отсутствует — создай Xbox-профиль",
                "2148916235": "Xbox Live недоступен в вашей стране",
                "2148916236": "Аккаунту Xbox нужно указать имя взрослого",
                "2148916237": "Пройди проверки Xbox (birth/settings)",
                "2148916238": "Аккаунт — ребёнок: нужен взрослый в семье",
            }
            raise ValueError(hints.get(code, "Ошибка Xbox: %s" % code)) from None
        raise
    uhs = data["DisplayClaims"]["xui"][0]["uhs"]
    return uhs, data["Token"]


def _mc_token(uhs, xsts_token):
    data = http_util.request_json(
        MC_LOGIN_URL,
        method="POST",
        body={"identityToken": "XBL3.0 x=%s;%s" % (uhs, xsts_token)},
    )
    return data["access_token"], data.get("expires_in", 86400)


def _profile(mc_access_token):
    import urllib.error

    req = urllib.request.Request(
        MC_PROFILE_URL,
        headers={
            "Authorization": "Bearer " + mc_access_token,
            "User-Agent": http_util.USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            import json as _json

            return _json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise ValueError(
                "У этого Microsoft-аккаунта нет игры Minecraft "
                "(лицензия не куплена)"
            ) from None
        raise


def full_login(client_id, progress=None):
    """Returns account dict. progress(msg) for UI updates."""
    device = start_device_code(client_id)
    if progress:
        progress(
            "Открой %s и введи код: %s"
            % (device.get("verification_uri", "microsoft.com/link"), device["user_code"])
        )
    token = wait_for_token(device, progress=progress, client_id=client_id)
    if progress:
        progress("Xbox Live...")
    xbl = _xbl(token["access_token"])
    uhs, xsts = _xsts(xbl)
    if progress:
        progress("Minecraft сервисы...")
    mc_token, exp = _mc_token(uhs, xsts)
    prof = _profile(mc_token)
    account = {
        "type": "microsoft",
        "name": prof["name"],
        "uuid": prof["id"],
        "token": mc_token,
        "expires_at": time.time() + exp - 60,
        "refresh_token": token.get("refresh_token", ""),
        "skin_url": _skin_url(prof),
        "clientToken": "",
    }
    if progress:
        progress("Готово: %s" % account["name"])
    return account


def _skin_url(prof):
    import base64

    for tex in prof.get("textures", {}).values():
        skin = tex.get("SKIN") or tex.get("skin")
        if skin:
            meta = skin.get("metadata") or {}
            if skin.get("url"):
                return skin["url"]

    decoded = prof.get("decoded")
    if decoded:
        return decoded
    try:
        enc = prof.get("textures", {}).get("custom", {}).get("SKIN", {}).get("url")
        return enc
    except Exception:
        return None


def refresh(account, client_id):
    """Refresh Microsoft token; returns updated account."""
    if not account.get("refresh_token"):
        raise ValueError("Нет refresh-токена — войдите заново")
    tok = http_util.request_form(
        TOKEN_URL,
        {
            "grant_type": "refresh_token",
            "refresh_token": account["refresh_token"],
            "client_id": client_id,
            "scope": SCOPE,
        },
    )
    xbl = _xbl(tok["access_token"])
    uhs, xsts = _xsts(xbl)
    mc_token, exp = _mc_token(uhs, xsts)
    account["token"] = mc_token
    account["expires_at"] = time.time() + exp - 60
    account["refresh_token"] = tok.get("refresh_token", account["refresh_token"])
    return account
