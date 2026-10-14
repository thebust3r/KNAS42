"""Live Cam: any phone's camera becomes a live channel ("LIVE • KITCHEN").

Off until it has a channel number (LIVECAM_CHANNEL, setup page → Experimental). Open /cam on a
phone (it uses the secure address, because phones only share the camera with secure pages), give it
a name and press Go live. The phone sends small pictures over a live connection, about 12 a second,
and the TV channel shows them with a news-style banner. Nothing is recorded: KNAS only keeps the
newest picture from each camera in memory, and it's gone the moment the phone stops.

There's no sound for now (pictures only).
"""
import os, re, secrets, threading, time

CAMS = {}                    # id -> {"name", "frame", "n", "since", "seen", "cv"}
_lock = threading.Lock()
MAX_CAMS = 4


def channel():
    v = os.environ.get("LIVECAM_CHANNEL", "0").strip()
    return "" if v in ("", "0") or v.lower() == "off" else v


def enabled():
    return bool(channel())


def _clean_name(n):
    n = re.sub(r"[^\w .'&-]", "", str(n or "")).strip()[:20]
    return n.upper() or "LIVE CAM"


def run(sock, name, facing=""):
    """One phone's camera, for as long as its live connection stays open."""
    with _lock:
        if len(CAMS) >= MAX_CAMS:
            sock.send({"t": "full", "message": f"{MAX_CAMS} cameras are already live. Stop one first."})
            sock.close()
            return
        i = secrets.token_hex(4)
        cam = CAMS[i] = {"name": _clean_name(name), "frame": b"", "n": 0, "since": time.time(), "seen": time.time(),
                         "cv": threading.Condition(_lock), "facing": facing}
    sock.send({"t": "live", "id": i, "name": cam["name"]})
    print(f"[live cam] {cam['name']} is live", flush=True)
    try:
        while True:
            m = sock.recv(timeout=30)
            if isinstance(m, bytes):
                if m[:2] != b"\xff\xd8":        # only JPEG pictures
                    continue
                with _lock:
                    cam["frame"], cam["n"], cam["seen"] = m, cam["n"] + 1, time.time()
                    cam["cv"].notify_all()
            elif m.startswith("{") and '"name"' in m:
                import json
                try:
                    cam["name"] = _clean_name(json.loads(m).get("name"))
                except ValueError:
                    pass
    except Exception:
        pass
    finally:
        with _lock:
            CAMS.pop(i, None)
            cam["cv"].notify_all()
        print(f"[live cam] {cam['name']} stopped", flush=True)


def cams():
    with _lock:
        return [{"id": i, "name": c["name"], "since": int(c["since"]), "ready": bool(c["frame"])}
                for i, c in sorted(CAMS.items(), key=lambda kv: kv[1]["since"])]


def stream(handler, i):
    """MJPEG: the TV's picture box keeps showing the newest frame as it arrives."""
    with _lock:
        cam = CAMS.get(i)
    if not cam:
        return handler.send_error(404)
    handler.send_response(200)
    handler.send_header("Content-Type", "multipart/x-mixed-replace; boundary=knasframe")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.close_connection = True
    last = -1
    try:
        while True:
            with _lock:
                if CAMS.get(i) is not cam:
                    break
                if cam["n"] == last:
                    cam["cv"].wait(5)
                if CAMS.get(i) is not cam:
                    break
                if cam["n"] == last:
                    continue
                frame, last = cam["frame"], cam["n"]
            if frame:
                handler.wfile.write(b"--knasframe\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass


def still(i):
    with _lock:
        cam = CAMS.get(i)
        return cam["frame"] if cam else b""
