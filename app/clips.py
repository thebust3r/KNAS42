"""KNAS Break clips: records the break screen into ordinary video files for ErsatzTV.

ErsatzTV struggles with a *live* stream as filler, so instead we save short clips
(30 seconds, 1, 2 and 5 minutes) into the break-clips folder. ErsatzTV treats them
like normal episodes and stacks them to fill the gap before the next show.

How: the recorder (knas42-cast) already turns the break page into a live HLS stream
made of 2-second pieces. To save CPU, the recorder only runs the break page while clips are
being made ("want" in /api/break/cue). We tell the break page to start over from "We'll Be Right
Back", then save the next N pieces back to back into one .ts file.

Clips are re-recorded every BREAK_CLIPS_HOURS (default 3) and just after midnight
(so On This Day stays right). Same names every time, so ErsatzTV just picks up the
new versions.

Settings (settings.txt):
  BREAK_CLIPS=30s x2, 1m x3, 2m x2, 5m x2     which clips to make (blank = off)
  BREAK_CLIPS_HOURS=3
  BREAK_CLIPS_SOURCE=http://127.0.0.1:8644/live.m3u8
"""
import os, re, json, time, threading, urllib.request, urllib.parse, datetime
from clock import local_now, local_today, local_ts

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.environ.get("BREAK_CLIPS_DIR") or os.path.join(ROOT, "break-clips")
TMP = os.path.join(ROOT, "data", "break-clips-working")
SEG = 2.0                      # seconds per piece (matches the recorder)
CUE_DELAY = 5.0                # page restart -> first piece that shows it

cue = {"id": 0, "clip": False, "want": False}  # the break page polls this; "want" wakes up the recorder
status = {"state": "starting", "last_run": None, "next_run": None, "clips": [], "error": None, "source": None}
LOGFILE = os.path.join(ROOT, "data", "break-clips-log.txt")
DL_FILE = os.path.join(ROOT, "data", "clip-downloads.json")
try:
    with open(DL_FILE, encoding="utf-8") as _f:
        downloads = json.load(_f)       # clip name -> when your ErsatzTV computer last copied it
except (OSError, ValueError):
    downloads = {}


def note_download(name, ip):
    downloads[name] = {"time": int(time.time()), "by": ip}
    try:
        os.makedirs(os.path.dirname(DL_FILE), exist_ok=True)
        with open(DL_FILE, "w", encoding="utf-8") as f:
            json.dump(downloads, f)
    except OSError:
        pass
NOW = threading.Event()         # "Make new clips now" from the setup page
on_made = None                  # set by the server: tells ErsatzTV to rescan when ErsatzTV is on this machine


def env(k, d=""):
    return os.environ.get(k, d).strip()


def log(*a):
    msg = " ".join(str(x) for x in a)
    print("[clips]", msg, flush=True)
    try:
        lines = []
        if os.path.exists(LOGFILE):
            with open(LOGFILE, encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()[-200:]
        lines.append(time.strftime("%Y-%m-%d %H:%M:%S ") + msg)
        with open(LOGFILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(LOGFILE, 0o666)
    except OSError:
        pass


def check_source(src):
    """Plain-English check of the break recorder stream."""
    cc = env("CAST_CHANNELS", "8644=/break?cast=1")
    port = urllib.parse.urlparse(src).port
    if port and "127.0.0.1" in src and not re.search(rf"\b{port}\s*=\s*/break", cc):
        return f"CAST_CHANNELS in settings.txt doesn't record the break page on {port}. Add: {port}=/break?cast=1"
    try:
        s1, u1 = _playlist(src)
    except Exception as e:
        if "127.0.0.1" in src:
            switched = ensure_recorder()
            return ("the break recorder (knas42-cast) isn't running. " + ("KNAS just switched it on for you: " if switched else "")
                    + "restart the KNAS project in your NAS's Docker app (Stop, then Start), or run `docker compose up -d` in the KNAS folder. "
                    + f"({type(e).__name__})")
        return f"can't reach the break recorder at {src} ({type(e).__name__}: {e})"
    if not u1:
        return "the break recorder is up but has no video yet (starting?)"
    time.sleep(5)
    try:
        s2, u2 = _playlist(src)
    except Exception as e:
        return f"the break recorder stopped answering ({e})"
    if s2 == s1 and len(u2) == len(u1):
        return "the break recorder is frozen (no new video in 5 seconds). Restart knas42-cast"
    return "ok"


def wait_for_source(src, limit=120):
    """Give the recorder up to `limit` seconds to start the screen, browser and video."""
    t0, chk = time.time(), "not checked"
    time.sleep(8)
    while time.time() - t0 < limit:
        chk = check_source(src)
        if chk == "ok" or "CAST_CHANNELS" in chk:
            return chk
        time.sleep(5)
    return chk


def plan():
    """'30s x2, 1m x3' -> [(30, 1), (30, 2), (60, 1), ...]"""
    raw = env("BREAK_CLIPS", "30s x2, 1m x3, 2m x2, 5m x2")
    out = []
    for part in raw.split(","):
        m = re.match(r"\s*(\d+)\s*(s|sec|secs|seconds|m|min|mins|minutes)?\s*(?:x\s*(\d+))?\s*$", part, re.I)
        if not m:
            continue
        secs = int(m.group(1)) * (60 if (m.group(2) or "m").lower().startswith("m") else 1)
        if 10 <= secs <= 1800:
            for n in range(1, int(m.group(3) or 1) + 1):
                out.append((secs, n))
    return out


def name_for(secs, n):
    label = f"{secs // 60}min" if secs % 60 == 0 else f"{secs}sec"
    return f"KNAS Break {label} {chr(64 + n) if n <= 26 else n}.ts"


def _get(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "KNAS42"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _playlist(src):
    """-> (media sequence number of first piece, [piece urls])"""
    text = _get(src).decode("utf-8", "replace")
    seq, urls = 0, []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            seq = int(line.split(":", 1)[1])
        elif line and not line.startswith("#"):
            urls.append(urllib.parse.urljoin(src, line))
    return seq, urls


def record(src, secs, dest):
    """Restart the break page, then save the next secs/2 pieces into dest."""
    need = max(1, round(secs / SEG))
    cue["id"] += 1
    cue["clip"] = True
    time.sleep(CUE_DELAY)
    seq, urls = _playlist(src)
    nxt = seq + len(urls)               # only pieces made from now on
    os.makedirs(TMP, exist_ok=True)
    tmp = os.path.join(TMP, os.path.basename(dest))
    got, last_new = 0, time.time()
    with open(tmp, "wb") as f:
        while got < need:
            seq, urls = _playlist(src)
            if nxt < seq:               # fell behind (shouldn't happen) - skip ahead
                nxt = seq
            while nxt < seq + len(urls) and got < need:
                f.write(_get(urls[nxt - seq], timeout=15))
                nxt += 1
                got += 1
                last_new = time.time()
            if time.time() - last_new > 60:
                raise RuntimeError("the break stream stopped sending video")
            time.sleep(0.7)
    os.makedirs(OUT, exist_ok=True)
    os.replace(tmp, dest)
    try:
        os.chmod(dest, 0o666)
    except OSError:
        pass


def run_all():
    src = env("BREAK_CLIPS_SOURCE", "http://127.0.0.1:8644/live.m3u8")
    todo = plan()
    status.update(state="recording")
    log(f"recording {len(todo)} break clips from {src}")
    made = []
    try:
        status["state"] = "waking up the break recorder"
        cue["want"] = True                  # the recorder only runs while clips are being made
        chk = wait_for_source(src)
        status["source"] = chk
        if chk != "ok":
            raise RuntimeError(chk)
        for secs, n in todo:
            name = name_for(secs, n)
            for attempt in range(1, 4):
                status["state"] = f"recording {name}" + (f" (try {attempt})" if attempt > 1 else "")
                try:
                    record(src, secs, os.path.join(OUT, name))
                    break
                except Exception as e:
                    log(f"{name} try {attempt} failed: {type(e).__name__}: {e}")
                    if attempt == 3:
                        raise
                    time.sleep(10)
            made.append(name)
            log("saved", name)
    except Exception as e:
        status["error"] = f"{type(e).__name__}: {e}"
        log("stopped:", status["error"])
    finally:
        cue["clip"] = False
        cue["want"] = False
        cue["id"] += 1
    keep = {name_for(s_, n_) for s_, n_ in todo}
    for old in (os.listdir(OUT) if os.path.isdir(OUT) else []):
        if old.startswith("KNAS Break ") and old.endswith(".ts") and old not in keep:
            try:
                os.remove(os.path.join(OUT, old))       # a clip you took out of BREAK_CLIPS
            except OSError:
                pass
    if made and len(made) == len(todo):
        status["error"] = None
    status.update(state="idle" if len(made) == len(todo) else "error (will try again in a few minutes)",
                  last_run=time.strftime("%Y-%m-%d %H:%M:%S"), clips=sorted(os.listdir(OUT)) if os.path.isdir(OUT) else [])
    if made and on_made:
        try:
            on_made()
        except Exception as e:
            log("couldn't ask ErsatzTV to rescan:", e)
    return len(made) == len(todo)


def _fresh(hours):
    """True if every planned clip exists, is newer than `hours` and was made today."""
    today = local_today()
    for secs, n in plan():
        p = os.path.join(OUT, name_for(secs, n))
        try:
            m = os.path.getmtime(p)
        except OSError:
            return False
        if time.time() - m > hours * 3600 or local_ts(m).date() != today:
            return False
    return True


def enabled():
    return env("BREAK_CLIPS_ON", "on").lower() not in ("off", "no", "0", "false")


ENV_FILE = os.path.join(ROOT, ".env")


def ensure_recorder():
    """Switch on the optional recorder for Docker: COMPOSE_PROFILES=clips in the .env file next to
    docker-compose.yml. Takes effect the next time the project starts. True if it had to be added."""
    try:
        lines = open(ENV_FILE, encoding="utf-8").read().splitlines() if os.path.exists(ENV_FILE) else []
        for i, line in enumerate(lines):
            m = re.match(r"\s*COMPOSE_PROFILES\s*=\s*(.*)$", line)
            if m:
                profiles = [p.strip() for p in m.group(1).strip().strip('"').split(",") if p.strip()]
                if "clips" in profiles:
                    return False
                lines[i] = "COMPOSE_PROFILES=" + ",".join(profiles + ["clips"])
                break
        else:
            lines += ["# Written by KNAS: starts the break-clip recorder (knas42-cast) because break clips are on.",
                      "COMPOSE_PROFILES=clips"]
        with open(ENV_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        log("switched on the recorder (COMPOSE_PROFILES=clips in .env); restart the KNAS project to start it")
        return True
    except OSError as e:
        log("couldn't write .env to switch on the recorder:", e)
        return False


def _loop():
    time.sleep(20)                       # let the server settle
    while True:
        if re.search(r"\b8643\s*=", env("CAST_CHANNELS", "")):
            ensure_recorder()            # the weather channel stream for ErsatzTV needs the recorder too
        if not enabled():                # turned off on the setup page: leave your clips folder alone
            status.update(state="off (break clips are turned off)", next_run=None, error=None)
            NOW.clear()
            time.sleep(10)
            continue
        ensure_recorder()                # break clips need the recorder container
        hours = max(1.0, float(env("BREAK_CLIPS_HOURS", "3") or 3))
        if not plan():
            status["state"] = "off (BREAK_CLIPS is blank)"
            time.sleep(600)
            continue
        forced = NOW.is_set()
        NOW.clear()
        if forced:
            log("making new clips now (asked for on the setup page)")
        if _fresh(hours) and not forced:
            ok = True
            status["state"] = "idle"
        else:
            ok = run_all()
        # next run: in `hours`, or a minute after midnight, whichever comes first (30 min after a failure)
        now = local_now()
        midnight = datetime.datetime.combine(now.date() + datetime.timedelta(days=1), datetime.time(0, 1))
        wake = min(now + (datetime.timedelta(hours=hours) if ok else datetime.timedelta(minutes=3)), midnight)
        status["next_run"] = wake.strftime("%Y-%m-%d %H:%M")
        while local_now() < wake and not (ok and _fresh_needed()) and not NOW.is_set():
            time.sleep(5)


def _fresh_needed():
    """A clip was deleted or the clip list changed -> make them now."""
    for secs, n in plan():
        if not os.path.exists(os.path.join(OUT, name_for(secs, n))):
            return True
    return False


def start():
    os.makedirs(OUT, exist_ok=True)
    try:
        os.chmod(OUT, 0o777)
    except OSError:
        pass
    threading.Thread(target=_loop, daemon=True).start()
