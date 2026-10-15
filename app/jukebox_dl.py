"""Jukebox downloads: KNAS fetches YouTube videos itself so official music videos play too.

Lots of music videos (official ones, and fan uploads with a label's copyright claim) are blocked from
playing anywhere outside YouTube. With this on, the NAS downloads each video in the jukebox list with
yt-dlp (720p, ahead of time), and the TVs play the file from the NAS: no blocks, no ads, every TV in sync.
A video that was downloaded before is reused, never downloaded twice. The oldest ones are deleted when
the folder gets bigger than JUKEBOX_CACHE_GB (10 GB by default).

The first time it's needed, KNAS gets yt-dlp from its official GitHub page (into data/bin) and keeps it up
to date once a day, plus Node.js (YouTube needs a JavaScript helper). Turn it off with JUKEBOX_DOWNLOAD=off.
If YouTube ever asks KNAS to sign in, export your YouTube cookies to data/youtube-cookies.txt.
"""
import json, os, platform, shutil, subprocess, tempfile, threading, time, urllib.request, zipfile

DATA = ""
BIN = ""
CACHE = ""
_lock = threading.Lock()
_kick = threading.Event()
TOOLS = {"state": "idle", "message": "", "ytdlp": "", "js": "", "updated": 0}
DL = {}                      # video id -> {"state": "queued|getting|ready|failed", "msg": "", "at": time}
WANT = []                    # ids in the order they'll play
on_ready = None              # party.py: called with (id, info) when a download finishes
on_failed = None             # party.py: called with (id, message) when a download can't be done
MAX_SECONDS = 30 * 60        # longer than this (a 10-hour mix, say) isn't downloaded
FAIL_RETRY = 6 * 3600        # try a failed one again after this long
RELEASES = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/"
FORMAT = ("bv*[height<=720][vcodec^=avc1]+ba[ext=m4a]/b[height<=720][ext=mp4]/"
          "bv*[height<=720]+ba/b[height<=720]/b")


def enabled():
    """On by default, but only once the jukebox channel itself is turned on (nothing is installed before that)."""
    ch = (os.environ.get("PARTY_CHANNEL") or "0").strip().lower()
    return ch not in ("", "0", "off") and \
        os.environ.get("JUKEBOX_DOWNLOAD", "on").strip().lower() not in ("off", "no", "0", "false")


def _cap_bytes():
    try:
        return max(1.0, float(os.environ.get("JUKEBOX_CACHE_GB", "10") or 10)) * 1024 ** 3
    except ValueError:
        return 10 * 1024 ** 3


def setup(data_dir):
    global DATA, BIN, CACHE
    DATA = data_dir
    BIN = os.path.join(DATA, "bin")
    CACHE = os.path.join(DATA, "jukebox-cache")
    os.makedirs(CACHE, exist_ok=True)
    try:
        with open(os.path.join(BIN, "tools.json")) as f:
            TOOLS["updated"] = json.load(f).get("updated", 0)
    except (OSError, ValueError):
        pass
    for n in os.listdir(CACHE):            # leftovers from a download that was cut off
        if n.startswith(".tmp"):
            shutil.rmtree(os.path.join(CACHE, n), ignore_errors=True)
    threading.Thread(target=_loop, daemon=True, name="jukebox-dl").start()


# ---------------------------------------------------------------- what's on disk

def file_for(vid):
    p = os.path.join(CACHE, vid + ".mp4")
    return p if os.path.isfile(p) else None


def info_for(vid):
    try:
        with open(os.path.join(CACHE, vid + ".json")) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def saved():
    """Every video the NAS has, with its title (for Name That Tune)."""
    out = []
    if not CACHE or not os.path.isdir(CACHE):
        return out
    for n in os.listdir(CACHE):
        if n.endswith(".mp4") and len(n) == 15:
            meta = info_for(n[:-4])
            if meta.get("title"):
                out.append({"id": n[:-4], "title": meta["title"], "secs": meta.get("secs") or 0})
    return out


def touch(vid):
    """Mark a video as just played, so it's the last to be cleaned out."""
    p = file_for(vid)
    if p:
        try:
            os.utime(p, None)
        except OSError:
            pass


def status(vid):
    if file_for(vid):
        return "ready"
    d = DL.get(vid)
    return d["state"] if d else ""


def message(vid):
    d = DL.get(vid)
    return d.get("msg", "") if d else ""


def usable():
    """Downloads are on and the tools are working (or still being set up)."""
    return enabled() and TOOLS["state"] != "error"


def info():
    files = [n for n in os.listdir(CACHE) if n.endswith(".mp4")] if CACHE and os.path.isdir(CACHE) else []
    size = sum(os.path.getsize(os.path.join(CACHE, n)) for n in files if os.path.isfile(os.path.join(CACHE, n)))
    return {"on": enabled(), "tools": TOOLS["state"], "message": TOOLS["message"], "videos": len(files),
            "gb": round(size / 1024 ** 3, 2), "cap_gb": round(_cap_bytes() / 1024 ** 3, 1),
            "getting": next((k for k, v in DL.items() if v["state"] == "getting"), "")}


def want(ids):
    """The jukebox list changed: these will play, in this order. Downloads follow that order."""
    if not enabled():
        return
    with _lock:
        WANT[:] = [i for i in ids if i]
        for i in WANT:
            d = DL.get(i)
            if file_for(i):
                continue
            if not d or (d["state"] == "failed" and time.time() - d["at"] > FAIL_RETRY):
                DL[i] = {"state": "queued", "msg": "", "at": time.time()}
    _kick.set()


def clear_cache():
    n = 0
    for f in os.listdir(CACHE):
        if f.endswith((".mp4", ".json")):
            try:
                os.remove(os.path.join(CACHE, f))
                n += f.endswith(".mp4")
            except OSError:
                pass
    with _lock:
        for k in [k for k, v in DL.items() if v["state"] == "ready"]:
            DL.pop(k, None)
    return n


# ---------------------------------------------------------------- tools (yt-dlp + a JavaScript helper)

WIN = os.name == "nt"
EXE = ".exe" if WIN else ""


def _musl():
    if WIN:
        return False
    return any(os.path.exists(p) for p in ("/lib/ld-musl-x86_64.so.1", "/lib/ld-musl-aarch64.so.1")) or \
        platform.libc_ver()[0] == ""


def _asset():
    m = platform.machine().lower()
    arm = m in ("aarch64", "arm64")
    if m not in ("x86_64", "amd64") and not arm:
        return None                              # anything else: the plain Python version
    if WIN:
        return "yt-dlp.exe"                     # also runs on Windows on ARM
    return ("yt-dlp_musllinux" if _musl() else "yt-dlp_linux") + ("_aarch64" if arm else "")


def _get(url, dest, timeout=300):
    tmp = dest + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "KNAS42"})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)
    os.replace(tmp, dest)


def _ytdlp_cmd():
    """How to run yt-dlp: one already on the system, or the copy KNAS keeps in data/bin."""
    sysbin = shutil.which("yt-dlp")
    if sysbin:
        return [sysbin], False
    own = os.path.join(BIN, "yt-dlp" + EXE)
    if not WIN and os.path.isfile(own + ".pyz"):
        return [os.environ.get("PYTHON", "python3"), own + ".pyz"], True
    if os.path.isfile(own):
        return [own], True
    return None, True


def _js():
    for name, flag in (("deno", ""), ("node", "node"), ("bun", "bun"), ("qjs", "quickjs")):
        p = shutil.which(name)
        if p:
            return name, flag, p
    p = os.path.join(BIN, "deno" + EXE)
    if os.path.isfile(p):
        return "deno", "deno:" + p, p
    return None, None, None


_tools_lock = threading.Lock()


def _ensure_tools():
    """Set up (or update) yt-dlp. The jukebox and the Stream channel can both ask at once: only one does the work."""
    with _tools_lock:
        return _ensure_tools_locked()


def _ensure_tools_locked():
    if TOOLS["state"] == "ready" and time.time() - TOOLS["updated"] < 20 * 3600:
        return True
    os.makedirs(BIN, exist_ok=True)
    TOOLS.update(state="installing", message="Getting the video downloader ready…")
    try:
        cmd, own = _ytdlp_cmd()
        if not cmd:
            a = _asset()
            if a:
                dest = os.path.join(BIN, "yt-dlp" + EXE)
                _get(RELEASES + a, dest)
                os.chmod(dest, 0o755)
                if subprocess.run([dest, "--version"], capture_output=True, timeout=120).returncode != 0:
                    os.remove(dest)
                    a = None
            if not a and not WIN:                # the plain Python version works everywhere Python does
                _get(RELEASES + "yt-dlp", os.path.join(BIN, "yt-dlp.pyz"))
            cmd, own = _ytdlp_cmd()
        elif own and time.time() - TOOLS["updated"] > 20 * 3600:
            subprocess.run(cmd + ["-U"], capture_output=True, timeout=300)    # keep up with YouTube's changes
        name, flag, _p = _js()
        if not name and shutil.which("apk") and os.geteuid() == 0:
            # YouTube needs a JavaScript helper now. KNAS's container is Alpine, so this is one quick install
            # (it comes back by itself if the container is ever recreated).
            subprocess.run(["apk", "add", "--no-cache", "nodejs"], capture_output=True, timeout=600)
            name, flag, _p = _js()
        if not name and not _musl() and platform.machine().lower() in ("x86_64", "amd64", "aarch64", "arm64"):
            arch = "aarch64" if platform.machine().lower() in ("aarch64", "arm64") else "x86_64"
            z = os.path.join(BIN, "deno.zip")
            target = "pc-windows-msvc" if WIN else "unknown-linux-gnu"
            _get(f"https://github.com/denoland/deno/releases/latest/download/deno-{'x86_64' if WIN else arch}-{target}.zip", z)
            with zipfile.ZipFile(z) as zz:
                zz.extract("deno" + EXE, BIN)
            os.remove(z)
            os.chmod(os.path.join(BIN, "deno" + EXE), 0o755)
            name, flag, _p = _js()
        ver = subprocess.run(cmd + ["--version"], capture_output=True, text=True, timeout=120).stdout.strip()
        TOOLS.update(state="ready", ytdlp=ver, js=name or "", updated=time.time(),
                     message=f"Ready (yt-dlp {ver}" + (f", {name}" if name else ", no JavaScript helper: some videos may fail") + ").")
        try:
            with open(os.path.join(BIN, "tools.json"), "w") as f:
                json.dump({"updated": TOOLS["updated"], "ytdlp": ver, "js": name}, f)
        except OSError:
            pass
        return True
    except Exception as e:
        TOOLS.update(state="error", message=f"Couldn't set up the video downloader: {e}. KNAS tries again in an hour.")
        print("[jukebox]", TOOLS["message"], flush=True)
        return False


# ---------------------------------------------------------------- search

_found = {}                  # search words -> (time, results), so the same search is instant for a while


KARAOKE_CHANNELS = ("sing king", "karafun", "stingray karaoke", "zoom karaoke", "cc karaoke", "karaoke version",
                    "musisi karaoke", "ultimate karaoke", "sing2guitar", "karaoke hits", "party tyme", "lugn")


def _karaoke(e):
    t = ((e.get("title") or "") + " " + (e.get("channel") or e.get("uploader") or "")).lower()
    return "karaoke" in t or "instrumental with lyrics" in t or any(c in t for c in KARAOKE_CHANNELS)


def search(q, n=12, karaoke=False):
    """Look up videos on YouTube by name (no API key needed: yt-dlp asks YouTube's own search).
    Karaoke mode searches for karaoke versions (the music with the words on screen) and puts those first."""
    q = " ".join(str(q or "").split())[:120]
    if karaoke and len(q) >= 2 and "karaoke" not in q.lower():
        q += " karaoke"
    if len(q) < 2:
        return {"ok": False, "message": "Type a song or artist first."}
    hit = _found.get(q.lower())
    if hit and time.time() - hit[0] < 600:
        return {"ok": True, "results": hit[1]}
    cmd, _own = _ytdlp_cmd()
    if not cmd:
        if TOOLS["state"] != "installing":
            threading.Thread(target=_ensure_tools, daemon=True).start()
        return {"ok": False, "message": "Search is getting set up (first time only). Try again in a minute, or paste a link."}
    try:
        r = subprocess.run(cmd + ["--flat-playlist", "-J", "--no-warnings", "--socket-timeout", "15", "--", f"ytsearch{n}:{q}"],
                           capture_output=True, text=True, timeout=45)
        j = json.loads(r.stdout or "{}")
    except (subprocess.TimeoutExpired, ValueError) as e:
        return {"ok": False, "message": "YouTube's search didn't answer. Try again, or paste a link."}
    out = []
    for e in j.get("entries") or []:
        vid = str(e.get("id") or "")
        if len(vid) != 11 or e.get("live_status") in ("is_live", "is_upcoming"):
            continue
        d = e.get("duration") or 0
        out.append({"id": vid, "title": (e.get("title") or "")[:140], "by": (e.get("channel") or e.get("uploader") or "")[:80],
                    "secs": int(d) if isinstance(d, (int, float)) else 0, "saved": bool(file_for(vid)), "karaoke": _karaoke(e)})
    if karaoke:
        out.sort(key=lambda x: not x["karaoke"])     # stable: YouTube's order otherwise
    if not out and r.returncode != 0:
        return {"ok": False, "message": "Search didn't work: " + _why(r.stderr or "no results")}
    _found[q.lower()] = (time.time(), out)
    if len(_found) > 200:
        _found.pop(next(iter(_found)))
    return {"ok": True, "results": out}


# ---------------------------------------------------------------- downloading

def _url(vid):
    t = os.environ.get("KNAS_JUKEBOX_URL")        # only for testing KNAS itself
    return t.replace("{id}", vid) if t else f"https://www.youtube.com/watch?v={vid}"


def _why(err):
    e = err.lower()
    if "sign in to confirm" in e or "not a bot" in e:
        return "YouTube asked KNAS to sign in (see Setup → Jukebox)"
    if "age" in e and ("restricted" in e or "confirm your age" in e or "inappropriate" in e):
        return "it's age-restricted (needs your YouTube login, see Setup → Jukebox)"
    if "private video" in e or "video unavailable" in e or "has been removed" in e:
        return "it was removed or made private"
    if "does not pass filter" in e:
        return "it's too long (over 30 minutes) or a live stream"
    if "no space" in e:
        return "the NAS is out of space"
    line = [x for x in err.strip().splitlines() if x.strip()][-1:] or ["unknown error"]
    return line[0].replace("ERROR: ", "")[:160]


def _download(vid):
    cmd, _own = _ytdlp_cmd()
    if not cmd:
        raise RuntimeError("the video downloader isn't installed")
    if shutil.disk_usage(CACHE).free < 1024 ** 3:
        _cleanup(extra=1024 ** 3)
        if shutil.disk_usage(CACHE).free < 1024 ** 3:
            raise RuntimeError("the NAS is out of space")
    work = tempfile.mkdtemp(prefix=".tmp-", dir=CACHE)
    try:
        args = cmd + ["--no-playlist", "--no-progress", "--no-warnings", "--no-simulate",
                      "--match-filter", f"!is_live & duration <? {MAX_SECONDS}",
                      "-f", FORMAT, "--merge-output-format", "mp4",
                      "--postprocessor-args", "Merger+ffmpeg:-movflags +faststart",
                      "--socket-timeout", "30", "--retries", "5", "--fragment-retries", "5",
                      "-o", os.path.join(work, "%(id)s.%(ext)s"),
                      "--print", "before_dl:KNASINFO\t%(title)s\t%(channel)s\t%(duration)s",
                      "--print", "after_move:KNASFILE\t%(filepath)s"]
        ff = shutil.which("ffmpeg")
        if ff:
            args += ["--ffmpeg-location", ff]
        name, flag, _p = _js()
        if flag:
            args += ["--js-runtimes", flag]
        args += ["--remote-components", "ejs:github"]     # YouTube's puzzle-solver scripts, if this yt-dlp lacks them
        cookies = os.path.join(DATA, "youtube-cookies.txt")
        if os.path.isfile(cookies):
            args += ["--cookies", cookies]
        r = subprocess.run(args + ["--", _url(vid)], capture_output=True, text=True, timeout=1200)
        infoline = next((l for l in r.stdout.splitlines() if l.startswith("KNASINFO\t")), "")
        fileline = next((l for l in r.stdout.splitlines() if l.startswith("KNASFILE\t")), "")
        got = fileline.split("\t", 1)[1].strip() if fileline else ""
        if r.returncode != 0 or not got or not os.path.isfile(got):
            if r.returncode == 0 and not infoline:      # yt-dlp skipped it quietly: too long, or live
                raise RuntimeError("does not pass filter")
            raise RuntimeError(r.stderr or r.stdout or "yt-dlp didn't make a file")
        parts = [("" if x == "NA" else x) for x in infoline.split("\t")]
        meta = {"title": parts[1] if len(parts) > 1 else "", "by": parts[2] if len(parts) > 2 else "",
                "secs": float(parts[3]) if len(parts) > 3 and parts[3].replace(".", "", 1).isdigit() else 0,
                "at": time.time()}
        with open(os.path.join(CACHE, vid + ".json"), "w") as f:
            json.dump(meta, f)
        os.replace(got, os.path.join(CACHE, vid + ".mp4"))
        return meta
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _cleanup(extra=0):
    """Keep the folder under its size limit: delete the videos played longest ago (never ones in the list)."""
    keep = set(WANT)
    files = []
    for n in os.listdir(CACHE):
        if n.endswith(".mp4"):
            p = os.path.join(CACHE, n)
            try:
                st = os.stat(p)
                files.append((st.st_mtime, st.st_size, n[:-4], p))
            except OSError:
                pass
    total = sum(f[1] for f in files)
    for _mt, size, vid, p in sorted(files):
        if total + extra <= _cap_bytes():
            break
        if vid in keep:
            continue
        for q in (p, os.path.join(CACHE, vid + ".json")):
            try:
                os.remove(q)
            except OSError:
                pass
        total -= size


def _next():
    with _lock:
        for i in WANT:
            d = DL.get(i)
            if d and d["state"] == "queued" and not file_for(i):
                d.update(state="getting", at=time.time())
                return i
    return None


def _loop():
    while True:
        _kick.wait(3600)
        _kick.clear()
        if not enabled():
            continue
        if not _ensure_tools():
            time.sleep(3600)                     # try setting up again later
            TOOLS["state"] = "idle"
            _kick.set()
            continue
        while enabled():
            vid = _next()
            if not vid:
                break
            try:
                meta = _download(vid)
                with _lock:
                    DL[vid] = {"state": "ready", "msg": "", "at": time.time()}
                print(f"[jukebox] downloaded {meta.get('title') or vid}", flush=True)
                if on_ready:
                    on_ready(vid, meta)
                _cleanup()
            except Exception as e:
                why = _why(str(e))
                with _lock:
                    DL[vid] = {"state": "failed", "msg": why, "at": time.time()}
                print(f"[jukebox] couldn't download {vid}: {why}", flush=True)
                if on_failed:
                    on_failed(vid, why)
