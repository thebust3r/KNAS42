"""Throw it to the TV: flick a photo or video up on your phone and it lands on the TV.

Off until you turn it on (THROW=on, setup page → Experimental). The phone page is /throw. Photos are
shrunk on the phone before they're sent, so they arrive in a second. Videos go up as they are; if a
video is in a format TVs can't play (like the HEVC videos newer iPhones make), the NAS converts it
first, which takes a little while for long videos. Everything thrown is deleted after a day.
"""
import json, os, re, secrets, shutil, subprocess, threading, time

DATA = ""
ITEMS = {}                       # id -> {"kind", "file", "ready", "error", "made", "from"}
_lock = threading.Lock()
KEEP_HOURS = 24
KEEP_BYTES = 3 * 1024 ** 3
MAX_IMAGE = 30 * 1024 ** 2
MAX_VIDEO = 1024 ** 3
REMOTE = None                    # remote.py, set by setup()
IMAGE_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}
VIDEO_TYPES = (".mp4", ".mov", ".m4v", ".webm", ".3gp", ".mkv")


def enabled():
    return os.environ.get("THROW", "off").strip().lower() in ("on", "yes", "1", "true")


def folder():
    f = os.path.join(DATA, "throw")
    os.makedirs(f, exist_ok=True)
    return f


def setup(data_dir, remote):
    global DATA, REMOTE
    DATA, REMOTE = data_dir, remote
    try:                         # anything left over from before a restart
        shutil.rmtree(os.path.join(DATA, "throw"), ignore_errors=True)
    except OSError:
        pass


def _cleanup():
    cut = time.time() - KEEP_HOURS * 3600
    with _lock:
        items = sorted(ITEMS.items(), key=lambda kv: -kv[1]["made"])
        total = 0
        for i, it in items:
            try:
                size = os.path.getsize(it["file"]) if it.get("file") else 0
            except OSError:
                size = 0
            total += size
            if it["made"] < cut or total > KEEP_BYTES:
                for f in (it.get("file"), it.get("raw")):
                    if f:
                        try:
                            os.remove(f)
                        except OSError:
                            pass
                ITEMS.pop(i, None)


def _probe(f):
    try:
        out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name",
                              "-of", "csv=p=0", f], capture_output=True, text=True, timeout=30).stdout.strip()
        return out.splitlines()[0] if out else ""
    except (OSError, subprocess.SubprocessError, IndexError):
        return ""


def _prepare_video(i):
    """Make the video something every TV can play: an H.264 MP4 that starts playing straight away."""
    it = ITEMS[i]
    raw, out = it["raw"], os.path.join(folder(), i + ".mp4")
    codec = _probe(raw)
    if not shutil.which("ffmpeg"):
        it.update(file=raw, ready=True, note="")
        return
    if codec == "h264":     # already fine: just tidy it up (instant)
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", raw, "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
               "-movflags", "+faststart", out]
    else:                   # HEVC and friends: convert (takes a bit)
        it["note"] = "Converting it so the TV can play it…"
        cmd = ["nice", "-n", "10", "ffmpeg", "-y", "-v", "error", "-i", raw, "-t", "900", "-map", "0:v:0", "-map", "0:a:0?",
               "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out]
        if not shutil.which("nice"):
            cmd = cmd[3:]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        if r.returncode == 0 and os.path.getsize(out) > 1000:
            try:
                os.remove(raw)
            except OSError:
                pass
            it.update(file=out, ready=True, note="")
            return
        print("[throw] ffmpeg:", (r.stderr or "")[-300:], flush=True)
    except (OSError, subprocess.SubprocessError) as e:
        print("[throw] ffmpeg:", e, flush=True)
    it.update(file=raw, ready=True, note="")      # try the original; most TVs play it anyway


def upload(handler, qs):
    """POST /api/throw/upload?kind=image|video&type=...&name=... with the file as the body."""
    if not enabled():
        return {"ok": False, "message": "Throw it to the TV is off (setup page → Experimental)."}
    q = lambda k: (qs.get(k) or [""])[0]
    kind = q("kind")
    n = int(handler.headers.get("Content-Length") or 0)
    if kind == "image":
        ext = IMAGE_TYPES.get(q("type").lower())
        if not ext:
            raise ValueError("That kind of picture can't be shown. Try a JPEG or PNG.")
        if n > MAX_IMAGE:
            raise ValueError("That picture is too big.")
    elif kind == "video":
        ext = os.path.splitext(q("name").lower())[1]
        if ext not in VIDEO_TYPES:
            ext = ".mp4"
        if n > MAX_VIDEO:
            raise ValueError("That video is too big (1 GB max). Try a shorter one.")
    else:
        raise ValueError("Pick a photo or a video.")
    if n <= 0:
        raise ValueError("Nothing was sent.")
    _cleanup()
    i = secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")
    raw = os.path.join(folder(), i + ".in" + ext)
    left = n
    with open(raw, "wb") as f:
        while left > 0:
            chunk = handler.rfile.read(min(1 << 20, left))
            if not chunk:
                break
            f.write(chunk)
            left -= len(chunk)
    if left > 0:
        os.remove(raw)
        raise ValueError("The upload was cut off. Try again.")
    who = re.sub(r"[^\w .'-]", "", q("from"))[:24].strip()
    with _lock:
        ITEMS[i] = {"kind": kind, "raw": raw, "file": raw if kind == "image" else "", "ready": kind == "image",
                    "error": "", "made": time.time(), "from": who, "note": "", "ext": ext}
    if kind == "video":
        threading.Thread(target=_prepare_video, args=(i,), daemon=True, name="throw-video").start()
    return dict(status(i), ok=True)


def status(i):
    it = ITEMS.get(str(i))
    if not it:
        return {"ok": False, "message": "That one's gone. Pick it again."}
    return {"ok": True, "id": i, "kind": it["kind"], "ready": it["ready"], "note": it.get("note", "")}


def file_for(i):
    it = ITEMS.get(str(i))
    return it["file"] if it and it["ready"] else None


def _targets(tvs):
    on = [t["id"] for t in REMOTE.tvs() if t["on"]]
    if tvs in (None, "", "all") or not isinstance(tvs, list):
        return on
    return [t for t in tvs if t in on]


def show(data):
    """Put a thrown photo or video up on the TVs."""
    if not enabled():
        return {"ok": False, "message": "Throw it to the TV is off."}
    i = str(data.get("id", ""))
    it = ITEMS.get(i)
    if not it:
        return {"ok": False, "message": "That one's gone. Pick it again."}
    if not it["ready"]:
        return {"ok": False, "wait": True, "message": "Still getting it ready…"}
    tvs = _targets(data.get("tvs"))
    if not tvs:
        return {"ok": False, "message": "No TVs are on. Open the cable box on a TV first."}
    ext = os.path.splitext(it["file"])[1] or it.get("ext", "")
    cmd = {"throw": {"id": i, "kind": it["kind"], "url": f"/throw-file/{i}{ext}", "from": it["from"] or str(data.get("from", ""))[:24],
                     "secs": max(5, min(int(data.get("secs") or 30), 300))}}
    for t in tvs:
        REMOTE._push(t, cmd)
    return {"ok": True, "tvs": len(tvs)}


def clear(data):
    tvs = _targets(data.get("tvs"))
    for t in tvs:
        REMOTE._push(t, {"throw": None})
    return {"ok": True}
