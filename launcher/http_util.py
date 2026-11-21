import gzip
import io
import json
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = "SashaLauncher/1.0 (+minecraft-launcher)"

CHUNK = 256 * 1024


class HttpError(RuntimeError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


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
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
