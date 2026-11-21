import gzip
import io
import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "SashaLauncher/vRelease (+minecraft-launcher)"

CHUNK = 256 * 1024

MIRRORS = {
    "https://piston-meta.mojang.com/": "https://bmclapi2.bangbang93.com/",
    "https://piston-data.mojang.com/": "https://bmclapi2.bangbang93.com/",
    "https://launchermeta.mojang.com/": "https://bmclapi2.bangbang93.com/",
    "https://launcher.mojang.com/": "https://bmclapi2.bangbang93.com/",
    "https://resources.download.minecraft.net/":
        "https://bmclapi2.bangbang93.com/assets/",
    "https://libraries.minecraft.net/":
        "https://bmclapi2.bangbang93.com/maven/",
}

use_mirror = True


class HttpError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _mirror(url):
    for base, repl in MIRRORS.items():
        if url.startswith(base):
            return repl + url[len(base):]
    return None


def _is_network_error(e):
    if isinstance(e, urllib.error.HTTPError):
        return False
    return isinstance(
        e, (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError,
            OSError)
    )


def _urlopen_retry(url, req, timeout, attempts=3):
    urls = [url]
    m = _mirror(url)
    if m and use_mirror:
        urls.append(m)
    last = None
    for u in urls:
        for i in range(attempts):
            r = req if u == url else urllib.request.Request(
                u, headers=dict(req.headers), data=req.data,
                method=req.get_method(),
            )
            try:
                r.headers.pop("Content-length", None)
            except Exception:
                pass
            try:
                return urllib.request.urlopen(r, timeout=timeout)
            except urllib.error.HTTPError:
                raise
            except BaseException as e:
                if not _is_network_error(e):
                    raise
                last = e
                if i < attempts - 1:
                    time.sleep([1, 3, 6][min(i, 2)])
    host = urllib.parse.urlsplit(url).netloc
    raise HttpError(
        0, "Сеть: %s не отвечает (%d попыток, зеркало тоже): %s"
        % (host, attempts * len(urls), last)
    )


def request_json(url, method="GET", body=None, headers=None, timeout=30):
    data = None
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with _urlopen_retry(url, req, timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
                raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
            return json.loads(raw.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        raise HttpError(e.code, "HTTP %s %s: %s" % (e.code, url, detail)) from None


def request_form(url, fields, timeout=30):
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with _urlopen_retry(url, req, timeout) as resp:
            return json.loads(resp.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:400]
        except Exception:
            pass
        raise HttpError(e.code, "HTTP %s: %s" % (e.code, detail)) from None


def download(url, dest, progress=None, sha1=None, timeout=60, headers=None):
    """Stream a file to dest. progress(done_bytes, total_bytes_or_None)."""
    import hashlib
    import os
    import threading
    import uuid

    tmp = "%s.part-%s-%s" % (dest, threading.get_ident(), uuid.uuid4().hex[:8])
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, headers=hdrs)
    hasher = hashlib.sha1()
    done = 0
    total = None
    try:
        with _urlopen_retry(url, req, timeout) as resp:
            length = resp.headers.get("Content-Length")
            if length:
                total = int(length)
            with open(tmp, "wb") as f:
                while True:
                    block = resp.read(CHUNK)
                    if not block:
                        break
                    f.write(block)
                    if sha1:
                        hasher.update(block)
                    done += len(block)
                    if progress:
                        progress(done, total)
        if sha1 and hasher.hexdigest() != sha1:
            os.remove(tmp)
            raise HttpError(0, "checksum mismatch: %s" % url)
        os.replace(tmp, dest)
        return done
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def resource_url(base, value_hash):
    return base.rstrip("/") + "/" + value_hash[:2] + "/" + value_hash
