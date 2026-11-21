import json
import os
import secrets
import string
import threading

from . import config

_lock = threading.Lock()


def _random_client_token():
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(32))


def load():
    with _lock:
        try:
            with open(config.ACCOUNTS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"selected": None, "accounts": []}


def save(data):
    with _lock:
        os.makedirs(os.path.dirname(config.ACCOUNTS_FILE), exist_ok=True)
        tmp = config.ACCOUNTS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, config.ACCOUNTS_FILE)


def key_hint(account):
    return "%s:%s" % (account.get("type", "?"), account.get("uuid") or account.get("name", "?"))


def upsert(account):
    data = load()
    key = key_hint(account)
    data["accounts"] = [a for a in data["accounts"] if key_hint(a) != key]
    data["accounts"].append(account)
    data["selected"] = key
    save(data)


def remove(acc_id):
    data = load()
    data["accounts"] = [a for a in data["accounts"] if key_hint(a) != acc_id]
    if data.get("selected") and not any(
        key_hint(a) == data["selected"] for a in data["accounts"]
    ):
        data["selected"] = None
    save(data)


def selected():
    data = load()
    for a in data["accounts"]:
        if key_hint(a) == data.get("selected"):
            return a
    return data["accounts"][0] if data["accounts"] else None


def all_accounts():
    return load()["accounts"]


def select(acc_id):
    data = load()
    data["selected"] = acc_id
    save(data)


def fresh_client_token():
    return _random_client_token()
