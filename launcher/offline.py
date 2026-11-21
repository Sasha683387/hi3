import hashlib
import uuid


def offline_account(name):
    name = name.strip()
    if not name:
        raise ValueError("Введите имя игрока")
    if len(name) > 16 or any(not (c.isalnum() or c == "_") for c in name):
        raise ValueError("Имя: латиница/цифры/_ , до 16 символов")
    return {
        "type": "offline",
        "name": name,
        "uuid": offline_uuid(name),
        "token": "0",
        "clientToken": "",
    }


def offline_uuid(name):
    """Mojang offline UUID: md5 of 'OfflinePlayer:<name>' as version-3 UUID."""
    data = ("OfflinePlayer:" + name).encode("utf-8")
    b = bytearray(hashlib.md5(data).digest())
    b[6] = (b[6] & 0x0F) | 0x30
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))
