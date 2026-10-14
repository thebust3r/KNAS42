"""KNAS Tools: put commercial breaks (chapter markers) into your episodes, right on the NAS.

ErsatzTV plays "Mid-Roll" filler (commercials) at chapter markers, and most episode files have none.
This finds the act breaks (fades to black, scene changes during a silence), lets you check and fix
them on the Tools page, and adds them to the file. Nothing is re-encoded: the picture and sound are
copied as they are, the new file is checked, and only then does it replace the original.

docker-compose.yml lets KNAS see the NAS drive (at /nas); you add your shows folders as libraries on the Tools page.
"""
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import urllib.parse

VIDEO_EXT = (".mkv", ".mp4", ".m4v", ".mov", ".avi", ".divx", ".mpg", ".mpeg", ".mpe", ".m2v", ".vob", ".ts", ".m2ts", ".mts", ".tp", ".trp",
             ".wmv", ".asf", ".webm", ".flv", ".f4v", ".3gp", ".3g2", ".ogv", ".ogm", ".rm", ".rmvb", ".dv", ".mxf", ".nut", ".y4m")
KEEP_EXT = (".mkv", ".mp4", ".m4v", ".mov")          # these can hold chapters; others become .mkv (no re-encode)
SKIP_DIRS = ("_originals (delete when happy)", "_break previews")
BACKUP_DIR = ".knas-originals"     # one hidden folder at the top of each library; media apps are told to skip it
IGNORE_FILES = {".ignore": "", ".plexignore": "*\n", ".etvignore": "", ".nomedia": ""}
SEARCH = 90.0                                         # seconds around each expected spot to look for the break
DATA = ""
CACHE = ""
ROOTS = []
FF = {"ffmpeg": None, "ffprobe": None, "installing": False, "error": ""}
JOBS = {}
_jobs_lock = threading.Lock()
_busy = set()
_busy_lock = threading.Lock()
_q_interactive = queue.Queue()
_q_batch = queue.Queue()
_probe_cache = {}


EXPLICIT = False      # TOOLS_MEDIA_DIRS set by hand: trust it even if it isn't a mount


def _mounted(r, trust=True):
    """Was something actually mapped in at (or inside) this folder? An empty /media from the
    base image doesn't count."""
    if EXPLICIT and trust:
        return True
    try:
        with open("/proc/mounts") as f:
            pts = [ln.split()[1].replace("\\040", " ") for ln in f if len(ln.split()) > 1]
    except OSError:
        return os.path.ismount(r)
    r = r.rstrip("/")
    return any(m == r or m.startswith(r + "/") for m in pts)


def setup(data_dir, roots, explicit=False, nas_dir="/nas"):
    global DATA, CACHE, ROOTS, EXPLICIT, NAS
    EXPLICIT = explicit
    DATA = data_dir
    CACHE = os.path.join(data_dir, "tools")
    ROOTS = [r.rstrip("/") or "/" for r in roots if r]
    NAS = nas_dir.rstrip("/") or "/nas"
    _libs_load()
    plan_load()
    move_old_backups()
    find_ffmpeg()
    for q in (_q_interactive, _q_batch):
        threading.Thread(target=_worker, args=(q,), daemon=True).start()
    threading.Thread(target=_watchdog, daemon=True).start()
    _batch_load()


class SpaceError(ValueError):
    pass


# ---------------------------------------------------------------- ffmpeg
def find_ffmpeg():
    FF["ffmpeg"] = shutil.which("ffmpeg")
    FF["ffprobe"] = shutil.which("ffprobe")
    return bool(FF["ffmpeg"] and FF["ffprobe"])


def ensure_ffmpeg():
    """Older KNAS images were built without ffmpeg. Install it once (Alpine's package manager) if missing."""
    if find_ffmpeg() or FF["installing"]:
        return
    if not shutil.which("apk"):
        FF["error"] = "ffmpeg isn't installed in the KNAS container. Rebuild the KNAS project in your Docker app."
        return
    FF["installing"] = True
    FF["error"] = ""

    def go():
        try:
            r = subprocess.run(["apk", "add", "--no-cache", "ffmpeg"], capture_output=True, text=True, timeout=900)
            if r.returncode != 0:
                FF["error"] = "Couldn't install the video tools: " + (r.stderr or r.stdout)[-300:]
        except Exception as e:
            FF["error"] = f"Couldn't install the video tools: {e}"
        FF["installing"] = False
        find_ffmpeg()
    threading.Thread(target=go, daemon=True).start()


def status():
    ensure_ffmpeg()
    rs = roots()
    libs = [{"name": l["name"], "path": l["path"], "shown": l.get("shown", ""), "ok": os.path.isdir(l["path"]),
             "writable": os.path.isdir(l["path"]) and os.access(l["path"], os.W_OK), "mine": l.get("mine", True)} for l in rs]
    return {"ffmpeg": bool(FF["ffmpeg"] and FF["ffprobe"]), "installing": FF["installing"], "error": FF["error"],
            "libraries": libs, "any_root": any(l["ok"] for l in libs), "can_add": bool(_bases()), "plan": dict(PLAN),
            "batch": batch_status()}


# ---------------------------------------------------------------- your libraries
# docker-compose.yml hands KNAS the whole NAS drive (at /nas) once. You then paste the location of
# each shows folder on the Tools page, the way your PC or the NAS's Files app shows it, and KNAS only
# ever works inside those folders.
NAS = "/nas"
LIBS = []
_libs_lock = threading.Lock()


def _libs_file():
    return os.path.join(DATA, "tools-libraries.json")


def _libs_load():
    global LIBS
    try:
        with open(_libs_file()) as f:
            LIBS = [l for l in json.load(f) if l.get("path")]
    except (OSError, ValueError):
        LIBS = []


def _libs_save():
    tmp = _libs_file() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(LIBS, f, indent=1)
    os.replace(tmp, _libs_file())


def _ident(p):
    try:
        st = os.stat(p)
        return (st.st_dev, st.st_ino)
    except OSError:
        return os.path.realpath(p)


def roots():
    """Everywhere KNAS may work: your libraries, plus an old-style folder mapped straight to /media."""
    out, seen = [], set()
    for l in LIBS:
        i = _ident(l["path"])
        if i not in seen:
            seen.add(i)
            out.append(dict(l, mine=True))
    for r in ROOTS:
        i = _ident(r)
        if os.path.isdir(r) and _mounted(r) and i not in seen:
            seen.add(i)
            out.append({"name": os.path.basename(r) or r, "path": r, "shown": "", "mine": False})
    return out


def _mountinfo():
    """(where it is inside KNAS, which folder of the NAS it is) for every folder Docker handed in."""
    out = []
    try:
        with open("/proc/self/mountinfo") as f:
            for ln in f:
                parts = ln.split()
                if len(parts) > 4:
                    dec = lambda x: x.replace("\\040", " ").replace("\\011", "\t").replace("\\134", "\\")
                    out.append((dec(parts[4]), dec(parts[3])))
    except OSError:
        pass
    return out


def _bases():
    """The NAS folders KNAS can see: /nas (or folders inside it) and an old-style /media."""
    bases = []
    if os.path.isdir(NAS):
        inside = [m for m, _ in _mountinfo() if m.startswith(NAS + "/")]
        if inside:                                   # /volume1:/nas/volume1 (and maybe /volume2...)
            bases += sorted(m for m in inside if os.path.isdir(m) and m.count("/") == NAS.count("/") + 1)
        elif _mounted(NAS, trust=False):             # /volume1:/nas
            bases.append(NAS)
    for r in ROOTS:
        if os.path.isdir(r) and _mounted(r):
            bases.append(r)
    return bases


def resolve(text):
    r"""Turn a folder location the way people copy it into where KNAS sees that folder.
    Takes \\NAS\Media\TV (Windows), Z:\TV (a mapped drive), smb://nas/Media/TV (Mac),
    /volume1/Media/TV (the NAS itself) or just Media/TV."""
    s = (text or "").strip().strip('"\'').strip()
    if not s:
        raise ValueError("Paste a folder location first.")
    s = s.replace("\\", "/")
    if re.match(r"(?i)^(smb|afp|nfs|file)://", s):
        s = urllib.parse.unquote("//" + s.split("://", 1)[1])
    drive = bool(re.match(r"^[A-Za-z]:(/|$)", s))
    if drive:
        rest = s[2:]
    elif s.startswith("//"):
        rest = s[2:].split("/", 1)[1] if "/" in s[2:] else ""      # drop the NAS's name or address
    else:
        rest = s
    rest = "/".join(p for p in rest.split("/") if p and p != ".")
    if ".." in rest.split("/"):
        raise ValueError("That location has '..' in it. Copy the folder's full location instead.")
    bases = _bases()
    if not bases:
        raise ValueError("KNAS can't see your NAS's drive yet. Add this line under knas42 → volumes in docker-compose.yml, "
                         "then redeploy the project:  - /volume1:/nas/volume1")
    found, ids = [], set()

    def hit(p):
        if p and os.path.isdir(p):
            i = _ident(p)
            if i not in ids:                         # the same folder reached two ways counts once
                ids.add(i)
                found.append(os.path.realpath(p))
    # 1) a full NAS path: match it against the folders Docker handed in (/volume1/... → /nas/volume1/...)
    if not drive:
        names = ["/" + rest]
        m = re.match(r"^/volume\d+(/.*)?$", "/" + rest)
        if m:
            names.append(m.group(1) or "/")
        for mnt, src in sorted(_mountinfo(), key=lambda x: not x[0].startswith(NAS)):
            if not (mnt == NAS or mnt.startswith(NAS + "/") or mnt in ROOTS):
                continue
            src = "" if src in ("", "/") else src.rstrip("/")
            hosts = ([src] if src else []) + ["/" + os.path.basename(mnt) + src]
            for name in names:
                for host in hosts:
                    if name == host or name.startswith(host + "/"):
                        hit(mnt + name[len(host):])
    # 2) relative to the drive (Media/TV), or a Windows share (\\NAS\Media\TV)
    if not found:
        for b in bases:
            hit(os.path.join(b, rest) if rest else None)
            m = re.match(r"^volume\d+/(.+)$", rest)
            if m:
                hit(os.path.join(b, m.group(1)))
    # 3) a mapped drive letter (Z:\TV) hides the share's name: look for it in each shared folder
    if not found and rest:
        for b in bases:
            try:
                for share in sorted(os.listdir(b)):
                    if not share.startswith(".") and not share.startswith("@") and os.path.isdir(os.path.join(b, share)):
                        hit(os.path.join(b, share, rest))
            except OSError:
                pass
    if not found:
        raise ValueError("KNAS couldn't find that folder on your NAS. Copy the location straight from the address bar "
                         "(like \\\\192.168.1.50\\Media\\TV) or from the folder's info in your NAS's Files app (like /volume1/Media/TV).")
    if len(found) > 1:
        opts = " or ".join(_nas_name(f) for f in found[:4])
        raise ValueError(f"There's more than one folder like that on your NAS: {opts}. Paste the one you mean.")
    return found[0]


def _nas_name(p):
    """How the NAS itself would write a folder KNAS sees (/nas/volume1/Media/TV → /volume1/Media/TV)."""
    return p[len(NAS):] if p.startswith(NAS + "/") else p


def add_library(text):
    p = resolve(text)
    with _libs_lock:
        if any(_ident(l["path"]) == _ident(p) for l in LIBS):
            raise ValueError("That folder is already one of your libraries.")
        for l in LIBS:
            lp = os.path.realpath(l["path"])
            if p.startswith(lp + "/"):
                raise ValueError(f"That folder is already inside your library \"{l['name']}\".")
        name = os.path.basename(p) or p
        if any(l["name"] == name for l in LIBS):
            name = f"{name} ({os.path.basename(os.path.dirname(p))})"
        LIBS.append({"name": name, "path": p, "shown": text.strip().strip('"\'')})
        LIBS.sort(key=lambda l: l["name"].lower())
        _libs_save()
    return {"ok": True, "library": {"name": name, "path": p}, "status": status()}


def remove_library(path):
    with _libs_lock:
        keep = [l for l in LIBS if l["path"] != path]
        if len(keep) == len(LIBS):
            raise ValueError("That isn't one of your libraries.")
        LIBS[:] = keep
        _libs_save()
    return {"ok": True, "status": status()}


# ---------------------------------------------------------------- paths
def safe(path):
    """Only files inside your libraries. Raises ValueError otherwise."""
    if not path:
        raise ValueError("no path")
    real = os.path.realpath(path)
    for r in [l["path"] for l in roots()]:
        rr = os.path.realpath(r)
        if real == rr or real.startswith(rr.rstrip("/") + "/"):
            return real
    raise ValueError("That isn't in one of your libraries.")


def _key(path):
    st = os.stat(path)
    return hashlib.sha1(f"{path}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:20]


def _cache_dir(path):
    d = os.path.join(CACHE, _key(path))
    os.makedirs(d, exist_ok=True)
    os.utime(d)
    return d


def _tidy_cache(keep=8, max_bytes=12 * 1024 ** 3):
    """Preview copies of big episodes can be big, so keep only the last few (and under 12 GB in all)."""
    try:
        dirs = [os.path.join(CACHE, d) for d in os.listdir(CACHE) if re.fullmatch(r"[0-9a-f]{20}", d)]
        dirs = [d for d in dirs if os.path.isdir(d)]
        dirs.sort(key=lambda d: os.path.getmtime(d), reverse=True)
        total = 0
        for n, d in enumerate(dirs):
            size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(d) for f in fs)
            total += size
            if n >= 1 and (n >= keep or total > max_bytes):     # never the newest one
                shutil.rmtree(d, ignore_errors=True)
    except OSError:
        pass


# ---------------------------------------------------------------- probing
def _run(args, timeout=None):
    return subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout)


def probe(path):
    st = os.stat(path)
    ck = (path, st.st_size, int(st.st_mtime))
    if ck in _probe_cache:
        return _probe_cache[ck]
    r = _run([FF["ffprobe"], "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-show_chapters", path], timeout=60)
    try:
        j = json.loads(r.stdout or "{}")
    except ValueError:
        j = {}
    streams = j.get("streams") or []
    v = next((s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    chapters = [{"start": float(c.get("start_time", 0)), "end": float(c.get("end_time", 0)), "title": (c.get("tags") or {}).get("title", "")}
                for c in (j.get("chapters") or [])]
    titles = [c["title"] for c in chapters]
    ours = bool(titles) and all(re.match(r"^(KNAS )?Part \d+$", t or "") for t in titles)
    try:
        dur = float((j.get("format") or {}).get("duration") or 0)
    except ValueError:
        dur = 0
    info = {"duration": dur, "chapters": chapters, "ours": ours, "video": bool(v),
            "vcodec": (v or {}).get("codec_name", ""), "pix_fmt": (v or {}).get("pix_fmt", ""), "profile": (v or {}).get("profile", ""),
            "acodec": (a or {}).get("codec_name", ""), "width": (v or {}).get("width", 0), "height": (v or {}).get("height", 0),
            "format": (j.get("format") or {}).get("format_name", "")}
    if len(_probe_cache) > 2000:
        _probe_cache.clear()
    _probe_cache[ck] = info
    return info


def real_length(path, job=None):
    """How long the video really runs: read the file without decoding and take the last timestamp."""
    if job is None:
        r = _run([FF["ffmpeg"], "-hide_banner", "-i", path, "-map", "0:v:0", "-c", "copy", "-f", "null", "-"], timeout=900)
        err = r.stderr
    else:                                   # an episode being opened: stoppable if you move on
        p = subprocess.Popen([FF["ffmpeg"], "-hide_banner", "-i", path, "-map", "0:v:0", "-c", "copy", "-f", "null", "-"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace")
        job["proc"] = p
        err = p.communicate()[1]
        job["proc"] = None
        if job.get("cancel"):
            raise Cancelled()
    ms = re.findall(r"time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if not ms:
        return 0.0
    h, m, s = ms[-1]
    return int(h) * 3600 + int(m) * 60 + float(s)


def length(path, info=None, job=None):
    info = info or probe(path)
    real = real_length(path, job)
    return real if real > 0 else info["duration"]


def browser_ok(info, path):
    """Can a web browser play this file as it is?"""
    ext = os.path.splitext(path)[1].lower()
    h264 = info["vcodec"] == "h264" and info["pix_fmt"] in ("yuv420p", "yuvj420p") and "10" not in (info["profile"] or "")
    audio = info["acodec"] in ("aac", "mp3", "")
    return ext in (".mp4", ".m4v", ".mov") and h264 and audio, h264, audio


# ---------------------------------------------------------------- browsing
def browse(path):
    if not path:
        return {"path": "", "up": None, "dirs": [{"name": l["name"], "path": l["path"], "lib": True} for l in roots() if os.path.isdir(l["path"])], "files": []}
    p = safe(path)
    if not os.path.isdir(p):
        raise ValueError("That folder doesn't exist.")
    dirs, files = [], []
    for name in sorted(os.listdir(p), key=str.lower):
        if name.startswith("."):
            continue
        full = os.path.join(p, name)
        if os.path.isdir(full):
            if name in ("cdrom", "floppy", "usb") and not os.listdir(full):   # empty leftovers from the base image
                continue
            if name not in SKIP_DIRS:
                dirs.append({"name": name, "path": full})
        elif name.lower().endswith(VIDEO_EXT) and ".knas-tmp." not in name:
            files.append({"name": name, "path": full})
    up = None
    if not any(os.path.realpath(l["path"]) == p for l in roots()):
        up = os.path.dirname(p)
    return {"path": p, "up": up, "dirs": dirs, "files": files, "writable": os.access(p, os.W_OK)}


def file_states(paths):
    """For the folder list: does each file have breaks yet? (probing is quick, done a few at a time)"""
    out = {}
    from concurrent.futures import ThreadPoolExecutor

    def one(fp):
        try:
            fp = safe(fp)
            i = probe(fp)
            n = len(i["chapters"])
            out[fp] = {"state": "ours" if i["ours"] else ("own" if n else "none"), "breaks": max(0, n - 1), "duration": i["duration"]}
        except Exception:
            out[fp] = {"state": "error"}
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(one, paths[:400]))
    return out


# ---------------------------------------------------------------- finding breaks
# How many breaks each length of show gets. You can change these on the Tools page (⚙ Break plan).
PLAN_DEFAULT = {"short": 1, "half": 2, "hour": 4, "every": 15, "gentle": True, "replace_junk": True}
PLAN = dict(PLAN_DEFAULT)


def _plan_file():
    return os.path.join(DATA, "tools-settings.json")


def plan_load():
    PLAN.clear()
    PLAN.update(PLAN_DEFAULT)
    try:
        with open(_plan_file()) as f:
            PLAN.update({k: v for k, v in json.load(f).items() if k in PLAN_DEFAULT})
    except (OSError, ValueError):
        pass


def plan_set(new):
    for k in ("short", "half", "hour"):
        if k in new:
            PLAN[k] = max(0, min(8, int(new[k])))
    if "every" in new:
        PLAN["every"] = max(5, min(60, int(new["every"])))
    for k in ("gentle", "replace_junk"):
        if k in new:
            PLAN[k] = bool(new[k])
    with open(_plan_file(), "w") as f:
        json.dump(PLAN, f, indent=1)
    return dict(PLAN)


def break_count(dur):
    m = dur / 60
    if m < 5:
        return 0
    if m < 15:          # 11-minute cartoons, short shows
        return PLAN["short"]
    if m < 35:          # half-hour shows (about 22 minutes)
        return PLAN["half"]
    if m < 75:          # hour shows (about 44 minutes)
        return PLAN["hour"]
    return max(1, int(m // PLAN["every"]))   # movies and specials


def break_spots(dur):
    """Where breaks belong for a show this long, spread evenly through it (two breaks in a
    half-hour show sit a little early, like on TV: after the opening act and before the last)."""
    n = break_count(dur)
    if n <= 0:
        return []
    if n == 2:
        return [0.36 * dur, 0.70 * dur]
    return [dur * i / (n + 1) for i in range(1, n + 1)]


def search_window(dur, n=None):
    """How far from each spot to look: up to 90 seconds, but never so far that two spots' windows meet."""
    n = break_count(dur) if n is None else n
    return min(SEARCH, 0.4 * dur / (n + 1)) if n else SEARCH


def chapters_look_real(chapters, dur):
    """Chapters that came with the file (from a disc or a download) are often junk for this: a few
    stuck at the start, or two in the same spot. They only count if they sit where breaks belong."""
    starts = sorted({round(c["start"], 1) for c in chapters if 30 < c["start"] < dur - 30})
    starts = [t for i, t in enumerate(starts) if i == 0 or t - starts[i - 1] > 20]
    spots = break_spots(dur)
    if not starts or not spots:
        return False
    win = search_window(dur) * 1.5
    near = [sp for sp in spots if any(abs(t - sp) <= win for t in starts)]
    return len(near) >= max(1, (len(spots) + 1) // 2) and len(starts) <= len(spots) * 3


def _parse(text, offset=0.0):
    blacks, quiet, cuts = [], [], []
    for s, e in re.findall(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)", text):
        s, e = float(s) + offset, float(e) + offset
        if e - s <= 6:
            blacks.append((s, e))
    qs = None
    for kind, v in re.findall(r"silence_(start|end):\s*(-?[\d.]+)", text):
        v = float(v) + offset
        if kind == "start":
            qs = v
        elif qs is not None:
            if v - qs <= 8:
                quiet.append((qs, v))
            qs = None
    for t in re.findall(r"Parsed_showinfo[^\n]*pts_time:\s*([\d.]+)", text):
        cuts.append(float(t) + offset)
    return blacks, quiet, cuts


def candidates(blacks, quiet, cuts):
    """Every place that looks like an act break, with how much to trust it.
    fade to black + silence (6) > fade to black (5) > scene change during a silence (4) > long silence (2).
    A plain pause in the middle of a scene doesn't count."""
    out = []
    for b0, b1 in blacks:
        both = any(q0 <= b1 + 0.4 and q1 >= b0 - 0.4 for q0, q1 in quiet)
        out.append({"t": round((b0 + b1) / 2, 3), "score": 6 if both else 5, "how": "fade to black + silence" if both else "fade to black"})
    for q0, q1 in quiet:
        cut = None
        for c in cuts:
            if q0 - 0.6 <= c <= q1 + 0.6:
                cut = c
        if cut is not None and q1 - q0 >= 0.45:
            out.append({"t": round(cut, 3), "score": 4, "how": "scene change during silence"})
        elif q1 - q0 >= 3.0:
            out.append({"t": round((q0 + q1) / 2, 3), "score": 2, "how": "long silence"})
    out.sort(key=lambda c: c["t"])
    merged = []                                      # one candidate per moment, keeping the most trusted
    for c in out:
        if merged and abs(merged[-1]["t"] - c["t"]) < 1.0:
            if c["score"] > merged[-1]["score"]:
                merged[-1] = c
        else:
            merged.append(c)
    return merged


def suggest(cands, dur, cuts=None):
    """The best candidate near each spot where a break belongs. With `cuts`, a spot that has no clean
    break gets the nearest scene change instead (a best guess). Breaks never bunch up together."""
    spots = break_spots(dur)
    win = search_window(dur, len(spots))
    gap = max(60.0, 0.5 * dur / (len(spots) + 1)) if spots else 60.0
    found = []
    for spot in spots:
        ok = lambda t: 30 <= t <= dur - 30 and abs(t - spot) <= win and all(abs(t - f["t"]) >= gap for f in found)
        best, best_score = None, -1
        for c in cands:
            if not ok(c["t"]):
                continue
            score = c["score"] - abs(c["t"] - spot) / (win * 2)
            if score > best_score:
                best, best_score = c, score
        if best:
            found.append(dict(best))
        elif cuts:
            near = [c for c in cuts if ok(c)]
            if near:
                c = min(near, key=lambda c: abs(c - spot))
                found.append({"t": round(c, 3), "score": 1, "how": "best guess: scene change", "guess": True})
    found.sort(key=lambda c: c["t"])
    return found


DETECT_V = "scale=160:-2,blackdetect=d=0.08:pix_th=0.08:pic_th=0.97,select=gt(scene\\,0.30),showinfo"
DETECT_A = "silencedetect=n=-40dB:d=0.3"


def _speed(gentle):
    """Decode a little rougher (fine for spotting fades and cuts, and quicker). Gentle mode also keeps
    ffmpeg to 1 thread, so a long batch uses about a quarter to a third of a 4-core NAS instead of all of it."""
    out = ["-skip_loop_filter", "all"]
    if gentle:
        out = ["-threads", "1", "-filter_threads", "1"] + out
    return out


def analyze(src, start=0.0, span=None, progress=None, total=None, gentle=False, job=None):
    """One pass over (part of) a video: fades to black, silences and scene changes."""
    args = [FF["ffmpeg"], "-hide_banner", "-nostats"] + _speed(gentle)
    if start > 0:
        args += ["-ss", f"{start:.3f}"]
    if span:
        args += ["-t", f"{span:.3f}"]
    args += ["-i", src, "-map", "0:v:0", "-map", "0:a:0?", "-vf", DETECT_V, "-af", DETECT_A, "-progress", "pipe:1", "-f", "null", "-"]
    if gentle:
        args[-1:-1] = ["-threads", "1"]
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
    if job is not None:
        job["proc"] = p
    err = []
    t = threading.Thread(target=lambda: err.extend(p.stderr), daemon=True)
    t.start()
    for line in p.stdout:
        if progress and total and line.startswith("out_time_us="):
            try:
                progress(min(0.99, int(line.split("=")[1]) / 1e6 / total))
            except ValueError:
                pass
    p.wait()
    t.join(5)
    if job is not None:
        job["proc"] = None
        if job.get("cancel"):
            raise Cancelled()
    return _parse("".join(err), start)


# ---------------------------------------------------------------- jobs
def _job(kind, path, q, fn):
    jid = hashlib.sha1(f"{kind}|{path}|{time.time()}".encode()).hexdigest()[:12]
    j = {"id": jid, "kind": kind, "path": path, "state": "queued", "progress": 0.0, "message": "Waiting…", "result": None, "fn": fn,
         "at": time.time(), "seen": time.time(), "cancel": False, "proc": None}
    with _jobs_lock:
        for old in [k for k, v in JOBS.items() if time.time() - v["at"] > 3600 and v["state"] in ("done", "error")]:
            del JOBS[old]
        JOBS[jid] = j
    q.put(jid)
    return j


def _job_public(j):
    return {k: j[k] for k in ("id", "kind", "path", "state", "progress", "message", "result")}


def job(jid):
    j = JOBS.get(jid)
    if j:
        j["seen"] = time.time()          # someone is still waiting for it
    return _job_public(j) if j else None


class Cancelled(Exception):
    pass


def cancel_job(j, why="Stopped."):
    """Stop a job: kills its ffmpeg so the NAS stops working on it straight away."""
    if not j or j["state"] not in ("queued", "running"):
        return
    j["cancel"] = True
    j["message"] = why
    if j["state"] == "queued":
        j["state"] = "error"          # never started: nothing to stop
    p = j.get("proc")
    if p and p.poll() is None:
        try:
            p.kill()
        except OSError:
            pass


def cancel(jid):
    cancel_job(JOBS.get(jid))
    return {"ok": True}


def _watchdog():
    """Opening an episode makes a preview copy and scans it, which keeps the CPU busy. If the page that
    asked for it is closed (or moves on to another episode), nobody is waiting any more: stop the work."""
    while True:
        time.sleep(5)
        for j in list(JOBS.values()):
            if j["kind"] == "open" and j["state"] in ("queued", "running") and time.time() - j["seen"] > 20:
                cancel_job(j, "Stopped: the page that opened this episode was closed.")


def _worker(q):
    while True:
        jid = q.get()
        j = JOBS.get(jid)
        if not j:
            continue
        if j.get("cancel"):
            j["state"] = "error"
            continue
        j["state"] = "running"
        try:
            j["result"] = j["fn"](j)
            j["state"] = "done"
            j["progress"] = 1.0
        except Cancelled:
            j["state"] = "error"
        except Exception as e:
            if j.get("cancel"):
                j["state"] = "error"
                continue
            j["state"] = "error"
            j["message"] = str(e) or e.__class__.__name__


# ---------------------------------------------------------------- opening an episode
def open_episode(path):
    """Everything the editor needs. Makes a browser-friendly preview copy if needed, and finds the
    break candidates. Cached, so opening the same episode again is instant."""
    p = safe(path)
    if not FF["ffmpeg"]:
        raise ValueError("The video tools aren't ready yet.")
    info = probe(p)
    if not info["video"]:
        raise ValueError("No video found in this file.")
    cd = _cache_dir(p)
    cached = os.path.join(cd, "analysis.json")
    if os.path.exists(cached):
        try:
            with open(cached) as f:
                res = json.load(f)
            res["info"] = info
            _fresh_suggestions(res, info)
            res["path"] = p          # the file may have been renamed (an .avi saved as .mkv)
            res["direct"] = browser_ok(info, p)[0]
            res["preview_ready"] = res["direct"] or os.path.exists(os.path.join(cd, "preview.mp4"))
            res["backup"] = bool(_find_backup(p))
            return {"ready": True, "data": res}
        except ValueError:
            pass
    for other in list(JOBS.values()):         # only one episode gets prepared at a time: the one you're looking at
        if other["kind"] == "open" and other["path"] != p:
            cancel_job(other, "Stopped: you opened another episode.")
    for other in list(JOBS.values()):         # already being prepared (page reloaded): keep waiting on that one
        if other["kind"] == "open" and other["path"] == p and other["state"] in ("queued", "running") and not other["cancel"]:
            return {"ready": False, "job": _job_public(other)}
    return {"ready": False, "job": _job_public(_job("open", p, _q_interactive, lambda j: _prepare(j, p, info, cd)))}


def _prepare(j, p, info, cd):
    _tidy_cache()
    j["message"] = "Measuring the episode…"
    dur = length(p, info, j)
    if j.get("cancel"):
        raise Cancelled()
    direct, h264, audio_ok = browser_ok(info, p)
    src_for_analysis = p
    if not direct:
        out = os.path.join(cd, "preview.mp4")
        tmp = out + ".part.mp4"
        if h264:     # just re-wrap (fast); fix the audio if a browser can't play it
            j["message"] = "Making a preview your browser can play (quick)…"
            args = [FF["ffmpeg"], "-hide_banner", "-nostats", "-y", "-i", p, "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "copy"]
            args += (["-c:a", "copy"] if audio_ok else ["-c:a", "aac", "-b:a", "128k", "-ac", "2"])
        else:        # different video format: a small, low-quality copy just for picking spots
            j["message"] = "Making a preview your browser can play (one time, takes a little while)…"
            args = [FF["ffmpeg"], "-hide_banner", "-nostats", "-y", "-i", p, "-map", "0:v:0", "-map", "0:a:0?",
                    "-vf", "scale=-2:'min(480,ih)'", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", "-g", "24", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "96k", "-ac", "2"]
            src_for_analysis = None
        args += ["-movflags", "+faststart", "-progress", "pipe:1", tmp]
        pr = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, errors="replace")
        j["proc"] = pr
        for line in pr.stdout:
            if line.startswith("out_time_us=") and dur:
                try:
                    j["progress"] = min(0.5, int(line.split("=")[1]) / 1e6 / dur * 0.5)
                except ValueError:
                    pass
        pr.wait()
        j["proc"] = None
        if j.get("cancel"):
            if os.path.exists(tmp):
                os.remove(tmp)
            raise Cancelled()
        if pr.returncode != 0 or not os.path.exists(tmp):
            raise ValueError("Couldn't make a preview of this file.")
        os.replace(tmp, out)
        if src_for_analysis is None:
            src_for_analysis = out          # the small copy is much quicker to scan
    j["message"] = "Looking for the act breaks (fades, scene changes, silences)…"
    base = j["progress"]

    def prog(x):
        j["progress"] = base + (1 - base) * x
    blacks, quiet, cuts = analyze(src_for_analysis, progress=prog, total=dur, job=j)
    cands = candidates(blacks, quiet, cuts)
    res = {"path": p, "duration": dur, "direct": direct, "cuts": [round(c, 3) for c in cuts], "candidates": cands}
    with open(os.path.join(cd, "analysis.json"), "w") as f:
        json.dump(res, f)
    res["info"] = info
    res["backup"] = bool(_find_backup(p))
    _fresh_suggestions(res, info)
    res["preview_ready"] = True
    return res


def _fresh_suggestions(res, info):
    """Suggestions follow the current break plan, so they're worked out each time an episode opens."""
    dur = res["duration"]
    res["suggested"] = suggest(res["candidates"], dur, res.get("cuts"))
    res["spots"] = break_spots(dur)
    res["plan_count"] = len(res["spots"])
    res["own_real"] = bool(info.get("chapters")) and not info.get("ours") and chapters_look_real(info["chapters"], dur)


def preview_file(path):
    p = safe(path)
    info = probe(p)
    if browser_ok(info, p)[0]:
        return p
    f = os.path.join(_cache_dir(p), "preview.mp4")
    return f if os.path.exists(f) else None


def thumb(path, t, w=320):
    p = safe(path)
    src = preview_file(p) or p
    d = os.path.join(_cache_dir(p), "thumbs")
    os.makedirs(d, exist_ok=True)
    t = max(0.0, float(t))
    out = os.path.join(d, f"{int(t * 1000)}_{w}.jpg")
    if not os.path.exists(out):
        _run([FF["ffmpeg"], "-hide_banner", "-nostats", "-y", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1",
              "-vf", f"scale={int(w)}:-2", "-q:v", "4", out], timeout=60)
    return out if os.path.exists(out) else None


# ---------------------------------------------------------------- saving
def _lock(p):
    with _busy_lock:
        if p in _busy:
            raise ValueError("This file is already being worked on.")
        _busy.add(p)


def _unlock(p):
    with _busy_lock:
        _busy.discard(p)


def write_chapters(p, breaks, backup=False, known_length=None):
    """Put chapter markers at `breaks` (seconds). Copies the picture and sound as they are, checks
    the new file, then swaps it in under the same name. An empty list removes all chapters.
    Formats that can't hold chapters (.avi, .wmv, .ts...) become .mkv; if a file won't copy as it is,
    the sound (and as a last resort the picture) is converted so the episode still gets its breaks."""
    p = safe(p)
    folder = os.path.dirname(p)
    if not os.access(folder, os.W_OK):
        raise ValueError("KNAS isn't allowed to change files in this folder. Map the folder without :ro in docker-compose.yml.")
    _lock(p)
    try:
        info = probe(p)
        st0 = os.stat(p)
        size = st0.st_size
        free = shutil.disk_usage(folder).free
        if free < size * 1.05 + 300 * 1024 ** 2:
            raise SpaceError(f"Paused: the drive is almost full ({free / 1024 ** 3:.1f} GB free). Adding breaks needs room for one more copy "
                             f"of the episode while it works{' (and backups keep the old copies)' if backup else ''}. Free up some space, then press Continue.")
        dur = known_length or length(p, info)
        times = []
        for t in sorted({round(float(b), 3) for b in breaks if 1 < float(b) < dur - 1}):
            if not times or t - times[-1] >= 5:          # two breaks in (nearly) the same spot become one
                times.append(t)
        base, ext = os.path.splitext(p)
        final_ext = ext if ext.lower() in KEEP_EXT else ".mkv"
        final = base + final_ext
        if final != p and os.path.exists(final):
            raise ValueError(f"There's already a file called {os.path.basename(final)} next to it, so KNAS left both alone.")
        stem = os.path.basename(base)
        meta = os.path.join(folder, ".knas-chapters-" + stem + ".txt")       # hidden, so ErsatzTV doesn't pick them up
        tmp = os.path.join(folder, ".knas-tmp-" + stem + final_ext)
        for left in (meta, tmp):
            if os.path.exists(left):
                os.remove(left)
        lines = [";FFMETADATA1"]
        prev, k = 0.0, 0
        for t in times + [dur]:
            k += 1
            lines += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(prev * 1000)}", f"END={int(t * 1000)}", f"title=KNAS Part {k}"]
            prev = t
        with open(meta, "w") as f:
            f.write("\n".join(lines) + "\n")
        mp4ish = final_ext.lower() in (".mp4", ".m4v", ".mov")
        fix = []
        if info["vcodec"] == "mpeg4" and not mp4ish:          # old DivX/Xvid "packed" frames
            fix = ["-bsf:v", "mpeg4_unpack_bframes"]
        copy = ["-c", "copy"] + fix
        aac = ["-c:v", "copy"] + fix + ["-c:a", "aac", "-b:a", "192k"]
        tries = [(["-map", "0", "-ignore_unknown"], copy, ""),
                 (["-map", "0:v", "-map", "0:a?", "-map", "0:s?", "-ignore_unknown"], copy, ""),
                 (["-map", "0:v:0", "-map", "0:a?"], copy, ""),
                 (["-map", "0:v:0", "-map", "0:a?"], aac, "sound converted"),
                 (["-map", "0:v:0", "-map", "0:a?"], ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                                                      "-c:a", "aac", "-b:a", "192k"], "converted")]
        why, ok, note = "", False, ""
        try:
            for maps, codecs, label in tries:
                args = [FF["ffmpeg"], "-hide_banner", "-nostats", "-y", "-fflags", "+genpts", "-i", p, "-f", "ffmetadata", "-i", meta] + maps
                args += ["-map_metadata", "0", "-map_chapters", "1" if times else "-1"] + codecs + ["-max_interleave_delta", "0"]
                if mp4ish:
                    args += ["-movflags", "+faststart"]
                try:
                    r = _run(args + [tmp], timeout=4 * 3600 if label == "converted" else 3600)
                except subprocess.TimeoutExpired:
                    why = "it took too long"
                    continue
                if r.returncode == 0 and os.path.exists(tmp):
                    chk = probe(tmp)
                    new_len = real_length(tmp)
                    want = len(times) + 1 if times else 0
                    if new_len > 0 and abs(new_len - dur) < max(3, dur * 0.002) and len(chk["chapters"]) >= want:
                        ok, note = True, label
                        break
                    why = f"the new copy didn't check out (runs {new_len:.0f}s, original {dur:.0f}s)"
                else:
                    bad = [l for l in r.stderr.splitlines() if re.search(r"(?i)error|invalid|could not|cannot|denied|not supported|failed|no space", l)]
                    why = " / ".join(bad[-2:]) or f"ffmpeg stopped (code {r.returncode})"
                    if re.search(r"(?i)no space left", r.stderr):
                        raise SpaceError("Paused: the drive filled up. Free up some space, then press Continue.")
                if os.path.exists(tmp):
                    os.remove(tmp)
        finally:
            for left in (meta,) + (() if ok else (tmp,)):
                if os.path.exists(left):
                    os.remove(left)
        if not ok:
            raise ValueError("Couldn't add the breaks, so the file was left alone. " + why)
        old_key = _key(p)
        # the original only goes away once the new copy is in place, so a power cut can't lose the episode
        if backup:
            keep = _backup_path(p)
            if os.path.exists(keep) or _find_backup(p):    # an older original is already saved: keep that one
                os.replace(tmp, final)
                if final != p:
                    os.remove(p)
            else:
                _backup_dirs(os.path.dirname(keep), os.stat(folder))
                shutil.move(p, keep)
                os.replace(tmp, final)
        else:
            os.replace(tmp, final)
            if final != p:
                os.remove(p)
        _same_owner(final, st0)
        # keep the preview and scan results for the new file (same picture, same timings)
        try:
            src = os.path.join(CACHE, old_key)
            if os.path.isdir(src):
                dst = os.path.join(CACHE, _key(final))
                if not os.path.exists(dst):
                    os.rename(src, dst)
        except OSError:
            pass
        _tell_media_server(p, final)
        return {"path": final, "breaks": times, "renamed": final != p, "note": note}
    finally:
        _unlock(p)


# ---------------------------------------------------------------- backups of the originals
# Kept in <library>/.knas-originals/<same folders as the show>, not next to the episodes, so Jellyfin,
# Plex, Emby and ErsatzTV don't list every episode twice. The folder holds .ignore / .plexignore /
# .etvignore files, which tell those apps to skip it.
def _lib_root(p):
    best = None
    for l in roots():
        rr = os.path.realpath(l["path"])
        if (p == rr or p.startswith(rr.rstrip("/") + "/")) and (best is None or len(rr) > len(best)):
            best = rr
    return best or os.path.dirname(p)


def _backup_path(p):
    root = _lib_root(p)
    return os.path.join(root, BACKUP_DIR, os.path.relpath(p, root))


def _backup_dirs(d, st):
    """Make the backup folder (and the 'skip me' files in it) if it isn't there yet."""
    root_bk = d
    while os.path.basename(root_bk) != BACKUP_DIR and os.path.dirname(root_bk) != root_bk:
        root_bk = os.path.dirname(root_bk)
    new = not os.path.isdir(d)
    os.makedirs(d, exist_ok=True)
    for name, body in IGNORE_FILES.items():
        f = os.path.join(root_bk, name)
        if not os.path.exists(f):
            try:
                with open(f, "w") as fh:
                    fh.write(body)
            except OSError:
                pass
    if new:
        x = d
        while True:
            _same_owner(x, st)
            if x == root_bk or os.path.dirname(x) == x:
                break
            x = os.path.dirname(x)


def _find_backup(p):
    """The saved original of this episode, if there is one (it may have another extension, like .avi)."""
    keep = _backup_path(p)
    d, stem = os.path.dirname(keep), os.path.splitext(os.path.basename(keep))[0]
    try:
        for f in sorted(os.listdir(d)):
            if os.path.splitext(f)[0] == stem and f.lower().endswith(VIDEO_EXT):
                return os.path.join(d, f)
    except OSError:
        pass
    return None


def restore_original(path):
    """Put the saved original back in place of the episode KNAS changed."""
    p = safe(path)
    bk = _find_backup(p)
    if not bk:
        raise ValueError("There's no saved original for this episode.")
    target = os.path.join(os.path.dirname(p), os.path.basename(bk))
    _lock(p)
    try:
        old_key = _key(p)
        os.replace(bk, target)
        if target != p and os.path.exists(p):
            os.remove(p)
        shutil.rmtree(os.path.join(CACHE, old_key), ignore_errors=True)
        _prune_empty(os.path.dirname(bk))
        _tell_media_server(p, target)
        return {"ok": True, "path": target}
    finally:
        _unlock(p)


def _prune_empty(d):
    """Remove backup folders that are now empty (keeps the top .knas-originals folder)."""
    while os.path.basename(d) != BACKUP_DIR and os.path.isdir(d):
        try:
            if os.listdir(d):
                return
            os.rmdir(d)
        except OSError:
            return
        d = os.path.dirname(d)


def backups_info():
    n, size = 0, 0
    for l in roots():
        bk = os.path.join(l["path"], BACKUP_DIR)
        for r, _, fs in os.walk(bk):
            for f in fs:
                if f.lower().endswith(VIDEO_EXT):
                    n += 1
                    try:
                        size += os.path.getsize(os.path.join(r, f))
                    except OSError:
                        pass
    return {"count": n, "bytes": size, "moving": _move_state["running"], "moved": _move_state["moved"]}


def delete_backups():
    with _batch_lock:
        if BATCH.get("state") in ("running", "stopping"):
            raise ValueError("Wait for the auto-mark to finish (or stop it) first.")
    gone = 0
    for l in roots():
        bk = os.path.join(l["path"], BACKUP_DIR)
        for r, _, fs in os.walk(bk):
            gone += sum(1 for f in fs if f.lower().endswith(VIDEO_EXT))
        shutil.rmtree(bk, ignore_errors=True)
    return {"ok": True, "deleted": gone, "info": backups_info()}


_move_state = {"running": False, "moved": 0}


def move_old_backups():
    """Earlier versions kept backups in '_originals (delete when happy)' folders right next to the episodes,
    where media apps found them and showed every episode twice. Move them into the hidden folder."""
    if _move_state["running"]:
        return
    _move_state["running"] = True

    def go():
        try:
            for l in roots():
                for r, dirs, fs in os.walk(l["path"]):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    if os.path.basename(r) != SKIP_DIRS[0]:
                        continue
                    show_dir = os.path.dirname(r)
                    for f in fs:
                        src = os.path.join(r, f)
                        dst = _backup_path(os.path.join(show_dir, f))
                        try:
                            if os.path.exists(dst):
                                continue
                            _backup_dirs(os.path.dirname(dst), os.stat(show_dir))
                            shutil.move(src, dst)
                            _move_state["moved"] += 1
                        except OSError:
                            pass
                    try:
                        if not os.listdir(r):
                            os.rmdir(r)
                    except OSError:
                        pass
        finally:
            _move_state["running"] = False
    threading.Thread(target=go, daemon=True).start()


def _tell_media_server(old, new):
    """Jellyfin / Emby re-read the episode so its new breaks reach ErsatzTV (if set up on the setup page)."""
    try:
        import mediaserver
        mediaserver.changed(old, new)
    except Exception as e:
        print("[tools] couldn't tell Jellyfin:", e, flush=True)


def _same_owner(path, st):
    """KNAS runs as the admin inside Docker: give the new file the episode's own owner and permissions,
    so you can still rename or delete it from your PC."""
    try:
        os.chown(path, st.st_uid, st.st_gid)
    except OSError:
        pass
    try:
        os.chmod(path, st.st_mode & 0o7777)
    except OSError:
        pass


def save(path, breaks, backup=False):
    p = safe(path)
    return _job("save", p, _q_interactive, lambda j: _save_job(j, p, breaks, backup))


def _save_job(j, p, breaks, backup):
    j["message"] = "Adding the breaks (nothing is re-encoded)…"
    known = None
    try:
        with open(os.path.join(_cache_dir(p), "analysis.json")) as f:
            known = json.load(f).get("duration")
    except (OSError, ValueError):
        pass
    return write_chapters(p, breaks, backup, known)




# ---------------------------------------------------------------- a whole folder (or library) at once
# A batch can run for days on a big library, so its progress is saved after every episode and it
# picks up where it left off if KNAS restarts. Only one runs at a time, at low priority, so the TV
# channels stay smooth while it works.
BATCH = {}
_batch_lock = threading.Lock()
_batch_thread = None
MAX_FAILS_IN_ROW = 8


def _batch_file():
    return os.path.join(DATA, "tools-batch.json")


def _batch_save():
    try:
        tmp = _batch_file() + ".tmp"
        with open(tmp, "w") as f:
            json.dump(BATCH, f)
        os.replace(tmp, _batch_file())
    except OSError:
        pass


def _batch_load():
    global BATCH
    try:
        with open(_batch_file()) as f:
            BATCH = json.load(f)
    except (OSError, ValueError):
        BATCH = {}
    if BATCH.get("state") == "stopping":
        BATCH["state"] = "stopped"
        BATCH["message"] = "Stopped."
    if BATCH.get("state") == "running":      # KNAS restarted in the middle: carry on
        BATCH["message"] = "Picking up where it left off…"
        _batch_go()


def _walk(folder):
    vids = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted((d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")), key=str.lower)
        for f in sorted(files, key=str.lower):
            full = os.path.join(root, f)
            if ".knas-tmp" in f or f.startswith(".knas-chapters"):    # left over from a crash or power cut
                _drop_leftover(full)
                continue
            if f.startswith("."):
                continue
            if f.lower().endswith(VIDEO_EXT):
                vids.append(full)
    return vids


def _drop_leftover(full):
    """Tidy up after a crash. A half-written copy is deleted, but only if its episode is still there;
    otherwise it's the only copy left, so it gets its name back."""
    try:
        if time.time() - os.path.getmtime(full) < 3600 or any(full.startswith(os.path.join(os.path.dirname(b), ".knas-")) and
                                                              os.path.dirname(b) == os.path.dirname(full) for b in _busy):
            return
        name = os.path.basename(full)
        if name.startswith(".knas-chapters"):
            os.remove(full)
            return
        stem, ext = os.path.splitext(name[len(".knas-tmp-"):]) if name.startswith(".knas-tmp-") else os.path.splitext(name.replace(".knas-tmp", ""))
        folder = os.path.dirname(full)
        if any(os.path.splitext(f)[0] == stem for f in os.listdir(folder) if not f.startswith(".") and ".knas-tmp" not in f):
            os.remove(full)
        else:
            os.replace(full, os.path.join(folder, stem + ext))
    except OSError:
        pass


def batch_start(path, mode="check", redo=False, backup=False, guess=True):
    p = safe(path)
    if not os.path.isdir(p):
        raise ValueError("That folder doesn't exist.")
    if not FF["ffmpeg"]:
        raise ValueError("The video tools aren't ready yet. Try again in a minute.")
    with _batch_lock:
        if BATCH.get("state") in ("running", "stopping"):
            raise ValueError("An auto-mark is already running. Stop it first, or wait for it to finish.")
    if mode != "check" and not os.access(p, os.W_OK):
        raise ValueError("KNAS isn't allowed to change files in this folder. Map the folder without :ro in docker-compose.yml.")
    files = _walk(p)
    if not files:
        raise ValueError("There are no videos in this folder.")
    _batch_new({"folder": p, "mode": mode, "redo": bool(redo), "backup": bool(backup), "guess": bool(guess), "files": files, "plan": {}})
    return batch_status()


def batch_apply():
    """Add the breaks a finished check found, without scanning everything again."""
    with _batch_lock:
        b = dict(BATCH)
    if b.get("mode") != "check" or b.get("state") in ("running", "stopping"):
        raise ValueError("There's no finished check to use.")
    plan = {r["path"]: {"breaks": r["breaks"], "key": r.get("key"), "length": r.get("length"), "kind": r["kind"]}
            for r in b.get("report", []) if r.get("breaks") and r.get("path")}
    if not plan:
        raise ValueError("The check didn't find any episodes to add breaks to.")
    if not os.access(b["folder"], os.W_OK):
        raise ValueError("KNAS isn't allowed to change files in this folder. Map the folder without :ro in docker-compose.yml.")
    _batch_new({"folder": b["folder"], "mode": "apply", "redo": b.get("redo"), "backup": bool(b.get("backup")), "guess": b.get("guess"),
                "files": list(plan), "plan": plan})
    return batch_status()


def batch_set_backup(on):
    with _batch_lock:
        BATCH["backup"] = bool(on)


def _batch_new(fields):
    with _batch_lock:
        BATCH.clear()
        BATCH.update(fields)
        BATCH.update({"id": hashlib.sha1(f"{time.time()}".encode()).hexdigest()[:10], "pos": 0, "report": [], "state": "running",
                      "message": "Starting…", "current": "", "started": time.time(), "finished": None, "worked": 0.0, "fails": 0})
        _batch_save()
    _batch_go()


def batch_stop():
    with _batch_lock:
        if BATCH.get("state") == "running":
            BATCH["state"] = "stopping"
            BATCH["message"] = "Stopping after this episode…"
            _batch_save()
    return batch_status()


def batch_resume():
    with _batch_lock:
        if BATCH.get("state") not in ("stopped", "paused") or BATCH.get("pos", 0) >= len(BATCH.get("files", [])):
            raise ValueError("There's nothing to continue.")
        BATCH["state"] = "running"
        BATCH["fails"] = 0
        BATCH["message"] = "Continuing…"
        _batch_save()
    _batch_go()
    return batch_status()


def batch_clear():
    with _batch_lock:
        if BATCH.get("state") in ("running", "stopping"):
            raise ValueError("Stop it first.")
        BATCH.clear()
        try:
            os.remove(_batch_file())
        except OSError:
            pass
    return batch_status()


def _batch_go():
    global _batch_thread
    with _batch_lock:
        if _batch_thread and _batch_thread.is_alive():
            return
        _batch_thread = threading.Thread(target=_batch_run, daemon=True)
        _batch_thread.start()


def _batch_run():
    try:      # low priority: ffmpeg started from this thread inherits it, so the TV stays smooth
        os.setpriority(os.PRIO_PROCESS, threading.get_native_id(), 12)
    except (AttributeError, OSError):
        pass
    while True:
        with _batch_lock:
            b = BATCH
            if b.get("state") == "stopping":
                b["state"] = "stopped"
                b["message"] = "Stopped. Press Continue to pick up where it left off."
                _batch_save()
                return
            if b.get("state") != "running":
                return
            if b["pos"] >= len(b["files"]):
                b["state"] = "done"
                b["finished"] = time.time()
                b["current"] = ""
                b["message"] = "Finished."
                _batch_save()
                return
            v = b["files"][b["pos"]]
            mode, opts = b["mode"], dict(redo=b.get("redo"), backup=b.get("backup"), guess=b.get("guess"))
            plan = (b.get("plan") or {}).get(v)
            folder = b["folder"]
        # the shows folder can show up late after the NAS starts, or drop out for a moment
        if not FF["ffmpeg"] or not _reachable(folder):
            with _batch_lock:
                BATCH["current"] = ""
                BATCH["message"] = ("Waiting for the video tools to finish installing…" if not FF["ffmpeg"] else
                                    "Waiting for your shows folder: KNAS can't reach it right now. Check that the NAS drive is connected "
                                    "and the library's folder still exists.")
            ensure_ffmpeg()
            time.sleep(20)
            continue
        name = os.path.relpath(v, folder)
        with _batch_lock:
            BATCH["current"] = name
            BATCH["step"] = "Starting…"
            BATCH["frac"] = 0.0
            BATCH["message"] = f"{b['pos'] + 1} of {len(b['files'])}: {name}"
        t0 = time.time()
        try:
            entry = _mark_one(v, mode, plan=plan, **opts)
        except SpaceError as e:
            with _batch_lock:
                BATCH["state"] = "paused"
                BATCH["message"] = str(e)
                _batch_save()
            return
        except Exception as e:
            entry = {"kind": "error", "result": f"couldn't change it: {e}" if mode != "check" else f"couldn't read it: {e}", "fail": True}
        entry["name"] = name
        entry.setdefault("path", v)
        with _batch_lock:
            BATCH["report"].append(entry)
            BATCH["pos"] += 1
            BATCH["frac"] = 0.0
            BATCH["worked"] = BATCH.get("worked", 0.0) + (time.time() - t0)
            BATCH["fails"] = BATCH.get("fails", 0) + 1 if entry.pop("fail", False) else 0     # a damaged file or two doesn't count
            if BATCH["fails"] >= MAX_FAILS_IN_ROW and BATCH["state"] == "running":
                BATCH["state"] = "paused"
                BATCH["message"] = (f"Paused because {MAX_FAILS_IN_ROW} episodes in a row didn't work. The last one said: "
                                    f"{entry['result']}. Fix that, then press Continue.")
            _batch_save()


def _reachable(folder):
    """Is the shows folder there right now? It lives on (or inside) something Docker handed in:
    a library pasted on the Tools page sits inside the /nas drive, an old-style one is /media itself."""
    if not os.path.isdir(folder):
        return False
    if EXPLICIT:
        return True
    try:
        if not os.listdir(folder):       # a drive that dropped out shows up as an empty folder
            return False
    except OSError:
        return False
    for m, _ in _mountinfo():
        if m != "/" and (folder == m or folder.startswith(m.rstrip("/") + "/")):
            return True
    return False


def _step(text, frac=None):
    """What the batch is doing inside the current episode, so the bar keeps moving."""
    with _batch_lock:
        if BATCH.get("state") in ("running", "stopping"):
            BATCH["step"] = text
            if frac is not None:
                BATCH["frac"] = max(0.0, min(0.99, frac))


def _root_of(p):
    for r in [l["path"] for l in roots()]:
        rr = os.path.realpath(r)
        if p == rr or p.startswith(rr.rstrip("/") + "/"):
            return r
    return p


def find_breaks(v, dur, guess=False):
    """Scan only around each spot where a break belongs (much quicker than the whole episode)."""
    spots = break_spots(dur)
    win = search_window(dur, len(spots))
    cands, cuts = [], []
    for k, s in enumerate(spots):
        a, b = max(30.0, s - win), min(dur - 30, s + win)
        if b > a:
            base, share = 0.15 + 0.6 * k / len(spots), 0.6 / len(spots)
            _step(f"Looking for break {k + 1} of {len(spots)} (around {_fmt(s)})…", base)
            bl, qu, cu = analyze(v, a, b - a, gentle=PLAN.get("gentle", True),
                                 progress=lambda x, base=base, share=share: _frac(base + share * x), total=b - a)
            cands += candidates(bl, qu, cu)
            cuts += cu
    return suggest(cands, dur, cuts if guess else None), spots


def _mark_one(v, mode, plan=None, redo=False, backup=False, guess=True):
    if not os.path.exists(v):
        return {"kind": "skip", "result": "skipped: the file is gone (moved or renamed?)"}
    info = probe(v)
    if not info["video"]:
        return {"kind": "error" if not info["format"] else "skip",
                "result": "couldn't read it: the file looks damaged or isn't a video" if not info["format"] else "skipped: no video in this file"}
    replaced = False
    if info["chapters"] and info["ours"] and not redo:
        return {"kind": "skip", "result": "skipped: already has breaks"}
    if info["chapters"] and not info["ours"]:
        dur0 = info["duration"] or length(v, info)
        if chapters_look_real(info["chapters"], dur0) or not PLAN.get("replace_junk", True):
            return {"kind": "skip", "result": "skipped: came with its own chapters at the act breaks"}
        replaced = True          # junk chapters (bunched at the start, doubled up): ErsatzTV would break there, so replace them
    if mode == "apply" and plan and plan.get("key") == _key(v):     # same file the check looked at: no need to scan again
        _step("Adding the breaks to the file and checking it…", 0.3)
        res = write_chapters(v, plan["breaks"], backup, plan.get("length"))
        return {"kind": plan.get("kind", "good"), "result": "breaks at " + ", ".join(_fmt(t) for t in res["breaks"]) + _note(res),
                "path": res["path"], "breaks": res["breaks"]}
    _step("Measuring how long it is…", 0.05)
    dur = length(v, info)
    if dur <= 0:
        return {"kind": "error", "result": "couldn't read it: KNAS couldn't tell how long it is (damaged file?)"}
    found, spots = find_breaks(v, dur, guess)
    if not spots:
        return {"kind": "skip", "result": "skipped: too short for breaks"}
    if not found:
        return {"kind": "none", "result": "left alone: no clean break found (do this one by hand)"}
    times = [c["t"] for c in found]
    kind = "guess" if any(c.get("guess") for c in found) else ("partial" if len(found) < len(spots) else "good")
    desc = ", ".join(f"{_fmt(c['t'])} ({c['how']})" for c in found)
    if kind == "partial":
        desc += f". Only found {len(found)} of {len(spots)}"
    if replaced:
        desc += ". Replaced the chapters that came with the file"
    if mode == "check":
        return {"kind": kind, "result": "would break at " + desc, "breaks": times, "key": _key(v), "length": dur}
    _step("Adding the breaks to the file and checking it…", 0.8)
    res = write_chapters(v, times, backup, dur)
    return {"kind": kind, "result": "breaks at " + desc + _note(res), "path": res["path"], "breaks": times}


def _frac(x):
    with _batch_lock:
        BATCH["frac"] = max(0.0, min(0.99, x))


def _note(res):
    bits = []
    if res.get("renamed"):
        bits.append("now " + os.path.basename(res["path"]))
    if res.get("note"):
        bits.append(res["note"] + " so it would work")
    return f" ({'; '.join(bits)})" if bits else ""


def batch_status(full=False):
    with _batch_lock:
        b = BATCH
        if not b:
            return {"state": "none"}
        rep = b.get("report", [])
        counts = {}
        for r in rep:
            counts[r["kind"]] = counts.get(r["kind"], 0) + 1
        total, pos = len(b.get("files", [])), b.get("pos", 0)
        per = b.get("worked", 0) / pos if pos else 0
        out = {"state": b.get("state"), "mode": b.get("mode"), "folder": b.get("folder"), "message": b.get("message", ""),
               "current": b.get("current", ""), "pos": pos, "total": total, "counts": counts,
               "progress": min(1.0, (pos + (b.get("frac", 0) if b.get("state") in ("running", "stopping") and b.get("current") else 0)) / total) if total else 1.0,
               "step": b.get("step", "") if b.get("current") else "", "waiting": b.get("message", "").startswith("Waiting"), "eta": round(per * (total - pos)) if per and b.get("state") == "running" else None,
               "options": {k: b.get(k) for k in ("redo", "backup", "guess")}, "started": b.get("started"), "finished": b.get("finished"),
               "can_apply": b.get("mode") == "check" and b.get("state") in ("done", "stopped", "paused") and
               any(r.get("breaks") for r in rep),
               "can_resume": b.get("state") in ("stopped", "paused") and pos < total,
               "recent": [_pub(r) for r in rep[-15:]][::-1]}
        if full:
            out["needs"] = [_pub(r) for r in rep if r["kind"] in ("none", "error", "guess", "partial")][:500]
        return out


def _pub(r):
    return {k: r.get(k) for k in ("name", "path", "kind", "result")}


KIND_TITLES = [("good", "Got clean breaks"), ("guess", "Best guesses (worth a quick look)"), ("partial", "Only some breaks found"),
               ("none", "Left alone: no clean break found (do these by hand)"), ("error", "Didn't work"), ("skip", "Skipped")]


def batch_report_text():
    with _batch_lock:
        b = dict(BATCH)
        rep = list(b.get("report", []))
    if not b:
        raise ValueError("No auto-mark has been run yet.")
    what = {"check": "Check (nothing was changed)", "mark": "Added breaks", "apply": "Added the breaks from the check"}.get(b.get("mode"), "")
    lines = ["KNAS commercial breaks report", f"Folder: {b.get('folder')}", f"What: {what}",
             f"Started: {time.strftime('%Y-%m-%d %H:%M', time.localtime(b.get('started') or 0))}",
             f"Episodes: {b.get('pos', 0)} of {len(b.get('files', []))} done ({b.get('state')})", ""]
    for kind, title in KIND_TITLES:
        rows = [r for r in rep if r["kind"] == kind]
        if not rows:
            continue
        lines += [f"== {title}: {len(rows)} ==", ""]
        lines += [f"{r['name']}\n    {r['result']}" for r in rows]
        lines.append("")
    return "\n".join(lines) + "\n"


def _fmt(t):
    t = int(round(t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"
