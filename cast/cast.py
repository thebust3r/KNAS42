#!/usr/bin/env python3
"""KNAS recorder: opens KNAS pages in hidden browsers, records them with ffmpeg and serves
each one as a live stream for ErsatzTV.

  KNAS 42 weather   -> http://NAS_IP:8643/live.m3u8
  KNAS break        -> http://NAS_IP:8644/live.m3u8

Which pages get recorded is CAST_CHANNELS in settings.txt, e.g.
  CAST_CHANNELS=8644=/break?cast=1                    (add 8643=/?cast=1 for the weather channel)
The break screen only runs while KNAS is making break clips, to save CPU.
The recorder restarts itself when those settings (or its own code) change.
"""
import os, shutil, subprocess, threading, time, functools, sys, json, urllib.request
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

KNAS = os.environ.get("KNAS_DIR", "/knas")
SETTINGS = os.path.join(KNAS, "settings.txt")
WATCH_KEYS = ("CAST_CHANNELS", "CAST_BASE", "TZ", "MUSIC_VOLUME", "VIDEO_BITRATE", "BROWSER_RESTART_HOURS", "FPS", "LEVEL_AUDIO")


def read_settings():
    out = {}
    try:
        with open(SETTINGS, encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


SET = read_settings()
for k, v in SET.items():
    os.environ[k] = v
E = os.environ.get
BASE = E("CAST_BASE", "http://127.0.0.1:8642").rstrip("/")
W, H = int(E("WIDTH", "640")), int(E("HEIGHT", "480"))
FPS = E("FPS", "30")
BITRATE = E("VIDEO_BITRATE", "1500k")
RESTART_HOURS = float(E("BROWSER_RESTART_HOURS", "24") or 24)
if not E("MUSIC_DIR"):
    os.environ["MUSIC_DIR"] = os.path.join(KNAS, "music") if os.path.isdir(os.path.join(KNAS, "music")) else "/music"


def channels():
    raw = E("CAST_CHANNELS") or "8644=/break?cast=1"
    if raw.strip().lower() == "none":
        return []
    out = []
    for item in raw.split(","):
        item = item.strip()
        if "=" not in item:
            continue
        port, page = item.split("=", 1)
        page = page.strip()
        if not page.startswith("http"):
            page = BASE + (page if page.startswith("/") else "/" + page)
        try:
            out.append((int(port), page))
        except ValueError:
            pass
    return out


def log(*a):
    print("[cast]", *a, flush=True)


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def guess_type(self, path):
        if path.endswith(".m3u8"):
            return "application/vnd.apple.mpegurl"
        if path.endswith(".ts"):
            return "video/mp2t"
        return super().guess_type(path)


def clear_stale_displays():
    """After the container restarts, old X lock files are left in /tmp. Their process ids now
    belong to other programs, so Xvfb thinks the display is taken and won't start. Nothing of
    ours is running yet at this point, so they're all stale."""
    import glob
    for f in glob.glob("/tmp/.X*-lock") + glob.glob("/tmp/.X11-unix/X*"):
        try:
            os.remove(f)
        except OSError:
            pass


def xvfb_cmd(n):
    # "-nolisten local": don't use the shared (host network) socket, so nothing else on the NAS can clash with us
    return ["Xvfb", f":{n}", "-screen", "0", f"{W}x{H}x24", "-nolisten", "tcp", "-nolisten", "local"]


def pick_display(first):
    """First display number from `first` that Xvfb can actually start on."""
    for n in range(first, first + 20):
        p = subprocess.Popen(xvfb_cmd(n), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        time.sleep(1.5)
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
            for f in (f"/tmp/.X{n}-lock", f"/tmp/.X11-unix/X{n}"):
                try:
                    os.remove(f)
                except OSError:
                    pass
            return n
        err = [l for l in (p.stderr.read() or b"").decode("utf-8", "replace").splitlines()
               if l.strip() and not l.strip().startswith("(EE)") and "keysym" not in l and not l.startswith(">")]
        log(f"display :{n} won't start ({err[-1] if err else 'code %s' % p.returncode}); trying the next one")
    return first


ALL = []   # every program we start, so they can all be stopped before a restart


class Proc:
    """One program (screen, browser, recorder) kept running while its channel is on."""
    def __init__(self, name, make_cmd, env, max_age=None, **kw):
        self.name, self.make_cmd, self.env, self.max_age, self.kw = name, make_cmd, env, max_age, kw
        self.p, self.t0 = None, 0
        ALL.append(self)

    def start(self):
        log("starting", self.name)
        self.p = subprocess.Popen(self.make_cmd(), env=self.env, **self.kw)
        self.t0 = time.time()

    def tend(self):
        """Restart it if it stopped or is due for its scheduled refresh."""
        if self.p is None:
            return self.start()
        if self.p.poll() is not None:
            log(self.name, "stopped (code %s); restarting" % self.p.returncode)
            return self.start()
        if self.max_age and time.time() - self.t0 > self.max_age:
            log("scheduled restart of", self.name)
            self.stop()
            self.start()

    def stop(self):
        if self.p and self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(10)
            except subprocess.TimeoutExpired:
                self.p.kill()
        self.p = None


class Recorder(Proc):
    """ffmpeg plus the little music player (audio.py) that feeds it sound."""
    def start(self):
        log("starting", self.name)
        self.audio = subprocess.Popen([sys.executable, "-u", os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio.py")],
                                      stdout=subprocess.PIPE, env=self.env)
        self.p = subprocess.Popen(self.make_cmd(), stdin=self.audio.stdout, env=self.env)
        self.audio.stdout.close()
        self.t0 = time.time()

    def stop(self):
        a = getattr(self, "audio", None)       # music player first, so it isn't left writing to nothing
        if a and a.poll() is None:
            a.kill()
            a.wait()
        self.audio = None
        super().stop()

    def tend(self):
        if self.p is not None and self.p.poll() is not None:
            self.stop()          # take the music player down with it before restarting
        super().tend()


def wanted(port, page):
    """On-demand channels (the break screen) only run while KNAS is making break clips.
    Everything else runs all the time. CAST_ALWAYS=on keeps every channel running."""
    if E("CAST_ALWAYS", "off").lower() in ("on", "yes", "1", "true") or "/break" not in page:
        return True
    try:
        with urllib.request.urlopen(BASE + "/api/break/cue", timeout=5) as r:
            return bool(json.loads(r.read().decode()).get("want", True))
    except Exception:
        return False


def start_channel(i, port, page):
    if "lite=" not in page:
        page += ("&" if "?" in page else "?") + "lite=1"   # fewer heavy effects = much less CPU
    n = pick_display(99 + i * 20)
    display, hls, prof = f":{n}", f"/tmp/hls{port}", f"/tmp/chrome-{port}"
    env = dict(os.environ, DISPLAY=display)
    os.makedirs(hls, exist_ok=True)

    def chromium():
        shutil.rmtree(prof, ignore_errors=True)
        return [E("CHROMIUM_BIN", "chromium"), "--no-sandbox", "--test-type", "--kiosk", "--no-first-run",
                "--disable-gpu", "--disable-dev-shm-usage", "--disable-infobars", "--noerrdialogs",
                "--disable-session-crashed-bubble", "--disable-translate", "--disable-features=Translate",
                "--disable-component-update", "--password-store=basic", "--hide-scrollbars",
                "--disable-background-networking", "--disable-sync", "--disable-extensions",
                "--force-device-scale-factor=1", "--mute-audio", "--autoplay-policy=no-user-gesture-required",
                f"--user-data-dir={prof}", f"--window-size={W},{H}", "--window-position=0,0", page]

    def ffmpeg():
        shutil.rmtree(hls, ignore_errors=True)
        os.makedirs(hls, exist_ok=True)
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin",
            "-thread_queue_size", "512", "-f", "x11grab", "-draw_mouse", "0",
            "-framerate", FPS, "-video_size", f"{W}x{H}", "-i", display,
            "-thread_queue_size", "1024", "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", "pipe:0",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-b:v", BITRATE, "-maxrate", BITRATE, "-bufsize", "3000k",
            "-g", str(int(FPS) * 2), "-keyint_min", str(int(FPS) * 2), "-sc_threshold", "0",
            # volume leveling (LEVEL_AUDIO): evens out loud and quiet songs so the recording matches your other channels
            *(["-af", "dynaudnorm=f=200:g=11:p=0.9:m=8"] if E("LEVEL_AUDIO", "on").lower() not in ("off", "no", "0", "false") else []),
            "-c:a", "aac", "-b:a", "128k",
            "-f", "hls", "-hls_time", "2", "-hls_list_size", "8",
            "-hls_flags", "delete_segments+omit_endlist+independent_segments",
            "-hls_segment_filename", f"{hls}/seg%06d.ts", f"{hls}/live.m3u8",
        ]

    procs = [Proc(f"display {display}", lambda: xvfb_cmd(n), env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
             Proc(f"browser {port}", chromium, env, max_age=RESTART_HOURS * 3600 if RESTART_HOURS else None,
                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
             Recorder(f"recorder {port}", ffmpeg, env)]
    waits = (2, 4, 0)   # give the screen and browser a moment before the next one starts

    def run():
        on, last_want = False, 0.0
        while True:
            if wanted(port, page):
                last_want = time.time()
            want = time.time() - last_want < 45     # keep going a little after the last request
            if want and not on:
                log(f"recording {page} -> :{port}")
                for pr, w in zip(procs, waits):
                    pr.start()
                    time.sleep(w)
                on = True
            elif want:
                for pr in procs:
                    pr.tend()
            elif on:
                log(f"pausing :{port} (not needed right now, saves CPU)")
                for pr in reversed(procs):
                    pr.stop()
                shutil.rmtree(hls, ignore_errors=True)
                os.makedirs(hls, exist_ok=True)
                on = False
            time.sleep(3)
    threading.Thread(target=run, daemon=True).start()

    srv = ThreadingHTTPServer(("0.0.0.0", port), functools.partial(Handler, directory=hls))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"channel ready: http://0.0.0.0:{port}/live.m3u8  ({page})")


def watch():
    """Restart (the container brings us back) when recorder settings or code change."""
    me = os.path.abspath(__file__)
    files = [me, os.path.join(os.path.dirname(me), "audio.py")]
    def snap():
        out = {}
        for f in files:
            try:
                out[f] = os.stat(f).st_mtime
            except OSError:
                out[f] = None
        s = read_settings()
        out["settings"] = tuple(s.get(k, "") for k in WATCH_KEYS)
        return out
    base = snap()
    while True:
        time.sleep(5)
        now = snap()
        if now != base:
            time.sleep(4)  # let a copy finish
            log("settings or code changed - restarting the recorder")
            for pr in reversed(ALL):
                try:
                    pr.stop()
                except Exception:
                    pass
            os._exit(3)


if __name__ == "__main__":
    clear_stale_displays()
    chs = channels()
    if not chs:
        log("CAST_CHANNELS is empty - nothing to record")
    for i, (port, page) in enumerate(chs):
        start_channel(i, port, page)
    threading.Thread(target=watch, daemon=True).start()
    while True:
        time.sleep(3600)
