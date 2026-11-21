"""Self-update: compares local build stamp with the sashalauncher branch."""

import os
import shutil
import tempfile
import zipfile

from . import http_util

RAW_BASE = "https://github.com/Sasha683387/hi3/raw/refs/heads/sashalauncher"
ZIP_URL = RAW_BASE + "/SashaLauncher-vRelease.zip"
BUILD_URL = RAW_BASE + "/launcher/build.txt"


def app_dir():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def local_stamp():
    path = os.path.join(app_dir(), "launcher", "build.txt")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def remote_stamp():
    req = urllib_request(BUILD_URL)
    with http_util._urlopen_retry(BUILD_URL, req, 20) as resp:
        return resp.read().decode("utf-8", "replace").strip()


def urllib_request(url):
    import urllib.request

    return urllib.request.Request(url, headers={"User-Agent": http_util.USER_AGENT})


def needs_update():
    local = local_stamp()
    remote = remote_stamp()
    if not local or not remote or local == remote:
        return False, local, remote
    return True, local, remote


def install_update():
    """Download fresh zip and swap the app dir in place. Returns new stamp."""
    zdest = os.path.join(tempfile.gettempdir(), "sashalauncher-update.zip")
    http_util.download(ZIP_URL, zdest, timeout=60)
    xdir = zdest + ".extracted"
    shutil.rmtree(xdir, ignore_errors=True)
    with zipfile.ZipFile(zdest) as z:
        z.extractall(xdir)
    if not os.path.isfile(os.path.join(xdir, "main.py")):
        raise RuntimeError("битый архив обновления (main.py не найден)")
    app = app_dir()
    bak = app.rstrip("/\\") + ".old"
    shutil.rmtree(bak, ignore_errors=True)
    swapped = False
    try:
        os.rename(app, bak)
        swapped = True
        try:
            os.rename(xdir, app)
        except OSError:
            os.rename(bak, app)
            swapped = False
            raise
    except OSError:
        pass
    if not swapped:
        for root, _dirs, files in os.walk(xdir):
            rel = os.path.relpath(root, xdir)
            target = os.path.join(app, rel) if rel != "." else app
            os.makedirs(target, exist_ok=True)
            for f in files:
                shutil.copy2(os.path.join(root, f), os.path.join(target, f))
    shutil.rmtree(xdir, ignore_errors=True)
    shutil.rmtree(bak, ignore_errors=True)
    return local_stamp()
