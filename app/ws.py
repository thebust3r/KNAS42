"""A small WebSocket helper: a live two-way line between a page and KNAS.

The normal pages check in with KNAS every second or so, which is fine for a jukebox but too slow for
a light gun or a live camera. A WebSocket stays open, so a trigger pull reaches the TV in a few
milliseconds. Works on both the normal and the secure address.
"""
import base64, hashlib, json, socket, struct, threading

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
MAX = 4 * 1024 * 1024         # biggest message we accept (a camera frame is ~40 KB)


class Closed(Exception):
    pass


class WS:
    def __init__(self, handler):
        self.h = handler
        self.r = handler.rfile
        self.sock = handler.connection
        self.lock = threading.Lock()
        self.open = True

    # ---- reading ----
    def _read(self, n):
        b = self.r.read(n)
        if not b or len(b) < n:
            raise Closed()
        return b

    def recv(self, timeout=None):
        """Next message: str for text, bytes for binary. Raises Closed when the page goes away."""
        self.sock.settimeout(timeout)
        parts, kind = [], None
        try:
            while True:
                b1, b2 = self._read(2)
                fin, op = b1 & 0x80, b1 & 0x0F
                n = b2 & 0x7F
                if n == 126:
                    n = struct.unpack(">H", self._read(2))[0]
                elif n == 127:
                    n = struct.unpack(">Q", self._read(8))[0]
                if n > MAX:
                    raise Closed()
                mask = self._read(4) if b2 & 0x80 else None
                data = self._read(n) if n else b""
                if mask:
                    data = bytes(b ^ mask[i % 4] for i, b in enumerate(data)) if n < 256 else _unmask(data, mask)
                if op == 0x8:
                    self.close()
                    raise Closed()
                if op == 0x9:
                    self._send(0xA, data)
                    continue
                if op == 0xA:
                    continue
                if op in (0x1, 0x2):
                    kind, parts = op, [data]
                elif op == 0x0:
                    parts.append(data)
                if fin and kind:
                    msg = b"".join(parts)
                    return msg.decode("utf-8", "replace") if kind == 0x1 else msg
        except (OSError, ValueError, struct.error):
            self.open = False
            raise Closed()

    def recv_json(self, timeout=None):
        while True:
            m = self.recv(timeout)
            if isinstance(m, str):
                try:
                    v = json.loads(m)
                    if isinstance(v, dict):
                        return v
                except ValueError:
                    pass

    # ---- writing ----
    def _send(self, op, data):
        n = len(data)
        head = bytes([0x80 | op]) + (bytes([n]) if n < 126 else (b"\x7e" + struct.pack(">H", n) if n < 65536 else b"\x7f" + struct.pack(">Q", n)))
        with self.lock:
            if not self.open:
                return False
            try:
                self.sock.sendall(head + data)
                return True
            except OSError:
                self.open = False
                return False

    def send(self, obj):
        if isinstance(obj, (bytes, bytearray)):
            return self._send(0x2, bytes(obj))
        if not isinstance(obj, str):
            obj = json.dumps(obj, separators=(",", ":"))
        return self._send(0x1, obj.encode())

    def close(self):
        if self.open:
            self._send(0x8, b"")
        self.open = False


def _unmask(data, mask):
    # fast enough in plain Python: xor the whole message as one big number
    full = (mask * (len(data) // 4 + 1))[:len(data)]
    return (int.from_bytes(data, "big") ^ int.from_bytes(full, "big")).to_bytes(len(data), "big")


def is_upgrade(handler):
    return "websocket" in (handler.headers.get("Upgrade") or "").lower()


def accept(handler):
    """Answer a page that asked for a WebSocket. Returns a WS, or None if it wasn't a proper request."""
    key = handler.headers.get("Sec-WebSocket-Key")
    if not key or not is_upgrade(handler):
        handler.send_error(400)
        return None
    acc = base64.b64encode(hashlib.sha1((key.strip() + GUID).encode()).digest()).decode()
    handler.close_connection = True
    handler.wfile.write(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                         f"Sec-WebSocket-Accept: {acc}\r\n\r\n").encode())
    try:
        handler.wfile.flush()
    except OSError:
        return None
    try:
        handler.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)   # send small messages straight away
    except OSError:
        pass
    return WS(handler)
