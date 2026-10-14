"""KNAS's own secure (https) address, for the features that need one.

Phones only let a web page use the camera, the microphone or the motion sensors when the page is
secure (https). So next to the normal address (http://NAS:8642) KNAS also answers on
https://NAS:8645 with a certificate it makes for itself the first time it starts. Nobody "vouches"
for that certificate, so the first time a phone opens the secure address it shows a "not private"
warning: tap Show details / Advanced, then Visit / Proceed, once per phone. It's your own box on your
own Wi-Fi, so that's fine.

Made in plain Python (no extra programs needed): an RSA 2048 key and a self-signed certificate that
lists the NAS's addresses. It's remade when it gets close to expiring or the NAS's address changes.
SECURE_PORT in settings.txt changes the port; SECURE_PORT=off turns the secure address off.
"""
import base64, hashlib, ipaddress, json, os, re, secrets, socket, ssl, threading, time
from datetime import datetime, timedelta, timezone

DAYS = 800            # phones refuse certificates that last longer than 825 days


# ---------- RSA ----------
_SMALL = [p for p in range(3, 2000, 2) if all(p % d for d in range(3, int(p ** .5) + 1, 2))]


def _probable_prime(n, rounds=40):
    for p in _SMALL:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits, e):
    while True:
        n = secrets.randbits(bits) | (3 << (bits - 2)) | 1
        if n % e != 1 and _probable_prime(n):
            return n


def rsa_key(bits=2048):
    e = 65537
    while True:
        p, q = _prime(bits // 2, e), _prime(bits // 2, e)
        if p == q:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        phi = (p - 1) * (q - 1)
        d = pow(e, -1, phi)
        return {"n": n, "e": e, "d": d, "p": p, "q": q}


# ---------- DER (the binary format certificates are written in) ----------
def _len(n):
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag, body):
    return bytes([tag]) + _len(len(body)) + body


def _int(v):
    b = v.to_bytes(max(1, (v.bit_length() + 8) // 8), "big")   # room for a leading 0 so it stays positive
    return _tlv(0x02, b)


def _seq(*parts):
    return _tlv(0x30, b"".join(parts))


def _set(*parts):
    return _tlv(0x31, b"".join(parts))


def _oid(s):
    nums = [int(x) for x in s.split(".")]
    out = bytes([40 * nums[0] + nums[1]])
    for n in nums[2:]:
        chunk = [n & 0x7F]
        n >>= 7
        while n:
            chunk.insert(0, 0x80 | (n & 0x7F))
            n >>= 7
        out += bytes(chunk)
    return _tlv(0x06, out)


def _bits(b):
    return _tlv(0x03, b"\x00" + b)


def _time(dt):
    if dt.year < 2050:
        return _tlv(0x17, dt.strftime("%y%m%d%H%M%SZ").encode())
    return _tlv(0x18, dt.strftime("%Y%m%d%H%M%SZ").encode())


NULL = b"\x05\x00"
SHA256_RSA = _seq(_oid("1.2.840.113549.1.1.11"), NULL)


def _name(cn):
    return _seq(_set(_seq(_oid("2.5.4.3"), _tlv(0x0C, cn.encode()))),
                _set(_seq(_oid("2.5.4.10"), _tlv(0x0C, b"KNAS"))))


def _sign(k, data):
    digest = bytes.fromhex("3031300d060960864801650304020105000420") + hashlib.sha256(data).digest()
    size = (k["n"].bit_length() + 7) // 8
    em = b"\x00\x01" + b"\xff" * (size - len(digest) - 3) + b"\x00" + digest
    return pow(int.from_bytes(em, "big"), k["d"], k["n"]).to_bytes(size, "big")


def make_cert(k, names, cn="KNAS"):
    """A self-signed certificate for these addresses / host names."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    alt = b""
    for n in names:
        try:
            alt += _tlv(0x87, ipaddress.ip_address(n).packed)
        except ValueError:
            alt += _tlv(0x82, n.encode())
    exts = _seq(
        _seq(_oid("2.5.29.17"), _tlv(0x04, _tlv(0x30, alt))),                         # the addresses it's for
        _seq(_oid("2.5.29.37"), _tlv(0x04, _seq(_oid("1.3.6.1.5.5.7.3.1")))),          # for websites
        _seq(_oid("2.5.29.19"), _tlv(0x01, b"\xff"), _tlv(0x04, _seq())),                # not a CA
    )
    spki = _seq(_seq(_oid("1.2.840.113549.1.1.1"), NULL), _bits(_seq(_int(k["n"]), _int(k["e"]))))
    tbs = _seq(_tlv(0xA0, _int(2)), _int(secrets.randbits(63) | 1), SHA256_RSA, _name(cn),
               _seq(_time(now - timedelta(days=1)), _time(now + timedelta(days=DAYS))), _name(cn), spki,
               _tlv(0xA3, exts))
    return _seq(tbs, SHA256_RSA, _bits(_sign(k, tbs)))


def _pem(kind, der):
    b = base64.b64encode(der).decode()
    return f"-----BEGIN {kind}-----\n" + "\n".join(b[i:i + 64] for i in range(0, len(b), 64)) + f"\n-----END {kind}-----\n"


def key_pem(k):
    der = _seq(_int(0), _int(k["n"]), _int(k["e"]), _int(k["d"]), _int(k["p"]), _int(k["q"]),
               _int(k["d"] % (k["p"] - 1)), _int(k["d"] % (k["q"] - 1)), _int(pow(k["q"], -1, k["p"])))
    return _pem("RSA PRIVATE KEY", der)


# ---------- the secure server ----------
STATE = {"on": False, "port": 0, "error": "", "made": 0}


def ensure(data_dir, names):
    """Make (or remake) the certificate if needed. Returns (cert file, key file)."""
    folder = os.path.join(data_dir, "secure")
    os.makedirs(folder, exist_ok=True)
    cf, kf, mf = (os.path.join(folder, n) for n in ("knas-cert.pem", "knas-key.pem", "about.json"))
    names = sorted(set(n for n in names if n))
    try:
        with open(mf) as f:
            about = json.load(f)
        fresh = about.get("expires", 0) - time.time() > 30 * 86400 and set(names) <= set(about.get("names", []))
        if fresh and os.path.isfile(cf) and os.path.isfile(kf):
            STATE["made"] = about.get("made", 0)
            return cf, kf
    except (OSError, ValueError):
        pass
    print("[secure] making KNAS's own certificate for the secure address (a few seconds, once)...", flush=True)
    k = rsa_key()
    with open(kf + ".tmp", "w") as f:
        f.write(key_pem(k))
    try:
        os.chmod(kf + ".tmp", 0o600)
    except OSError:
        pass
    with open(cf + ".tmp", "w") as f:
        f.write(_pem("CERTIFICATE", make_cert(k, names)))
    os.replace(kf + ".tmp", kf)
    os.replace(cf + ".tmp", cf)
    STATE["made"] = time.time()
    with open(mf, "w") as f:
        json.dump({"names": names, "made": STATE["made"], "expires": time.time() + DAYS * 86400}, f)
    return cf, kf


def start(server_cls, handler_cls, port, data_dir, names):
    """Run the secure address in the background. Never stops KNAS from starting if it can't."""
    def run():
        try:
            cf, kf = ensure(data_dir, names)
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain(cf, kf)

            class Secure(server_cls):
                daemon_threads = True

                def handle_error(self, request, client_address):
                    pass                     # a phone gave up halfway, etc.

            class Handler(handler_cls):
                secure = True

                def setup(self):
                    # the secure handshake happens on the connection's own thread, so a slow phone can't hold others up
                    raw = self.request
                    raw.settimeout(15)
                    first = raw.recv(1, socket.MSG_PEEK)
                    if first and first != b"\x16":   # someone typed http:// on the secure port: send them to https://
                        self._plain_redirect(raw)
                        raise ConnectionAbortedError()
                    self.request = ctx.wrap_socket(raw, server_side=True)
                    self.request.settimeout(None)
                    super().setup()

                def _plain_redirect(self, raw):
                    try:
                        head = raw.recv(4096).decode("latin-1", "replace")
                        path = (head.split(" ") + ["/", "/"])[1] if head[:1].isalpha() else "/"
                        host = re.search(r"(?im)^host:\s*([^\s:]+)", head)
                        host = host.group(1) if host else "localhost"
                        loc = f"https://{host}:{port}{path if path.startswith('/') else '/'}"
                        raw.sendall(("HTTP/1.1 301 Moved Permanently\r\nLocation: " + loc + "\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").encode())
                    except OSError:
                        pass
                    try:
                        raw.close()
                    except OSError:
                        pass

                def finish(self):
                    try:
                        super().finish()
                    except (OSError, AttributeError):
                        pass
                    try:
                        if isinstance(self.request, ssl.SSLSocket):
                            self.request.close()
                    except OSError:
                        pass

            srv = Secure(("0.0.0.0", port), Handler)
            STATE.update(on=True, port=port, error="")
            srv.serve_forever()
        except OSError as e:
            STATE.update(on=False, error=f"port {port} is busy or blocked ({e.strerror or e})")
            print(f"[secure] couldn't open the secure address: {STATE['error']}. Set SECURE_PORT to another number in settings.txt.", flush=True)
        except Exception as e:
            STATE.update(on=False, error=str(e))
            print("[secure] couldn't start the secure address:", e, flush=True)
    threading.Thread(target=run, daemon=True, name="secure-address").start()
