"""Jukebox channel: a shared list of YouTube videos (music videos at a party, say) that plays on its own channel.

Anyone on your home Wi-Fi adds videos from the phone remote (/remote → Jukebox). Every TV tuned to the
jukebox channel plays the same video, and the next one starts when it ends. The channel is off until you
give it a number: PARTY_CHANNEL=44 (setup page → Channels & screen).

YouTube plays inside the cable box (the /tv page), so this channel can't be recorded for ErsatzTV.

With downloads on (JUKEBOX_DOWNLOAD, see jukebox_dl.py) the NAS fetches each video ahead of time and the TVs
play that file, so videos that are blocked outside YouTube play too. Each video is in one of three modes:
"file" (playing the NAS's copy), "embed" (YouTube's own player) or "wait" (the NAS is still getting it).
"""
import json, os, re, threading, time, random, urllib.parse, urllib.request

import jukebox_dl as DLR

DATA = ""
_lock = threading.Lock()
S = {"now": None, "started": 0, "queue": [], "played": [], "shuffle": False, "note": "", "rev": 0, "stopped": False, "v": 2,
     "mode": "", "wait_since": 0}
WAIT_MAX = 75              # a video that isn't blocked plays with YouTube's player if the download takes longer than this
SHUFFLE_MIN = 3            # shuffle needs a few played videos, so it doesn't replay the same one over and over
REASONS = {"2": "the link is broken", "5": "this TV's browser can't play it", "100": "it was removed or made private",
           "101": "its owner blocks playing it outside YouTube", "150": "its owner blocks playing it outside YouTube",
           "152": "YouTube refused this TV's player", "153": "YouTube refused this TV's player",
           "file": "a TV couldn't play the downloaded copy"}
MAX_QUEUE = 200
MAX_PLAYED = 300


def setup(data_dir):
    global DATA
    DATA = data_dir
    try:
        with open(os.path.join(DATA, "party.json")) as f:
            saved = json.load(f)
        if saved.get("v") != 2:
            saved.pop("shuffle", None)     # 2.9.0 had shuffle on by default; now it's off until you tick it
        S.update({k: v for k, v in saved.items() if k in S})
        S["v"] = 2
    except (OSError, ValueError):
        pass
    S["now"], S["started"], S["mode"] = None, 0, ""     # start fresh after a restart; the list stays
    DLR.setup(DATA)
    DLR.on_ready, DLR.on_failed = _dl_ready, _dl_failed
    _want()


def _save():
    try:
        tmp = os.path.join(DATA, "party.json.tmp")
        with open(tmp, "w") as f:
            json.dump(S, f)
        os.replace(tmp, os.path.join(DATA, "party.json"))
    except OSError:
        pass


def video_id(text):
    """Pull the video id out of anything YouTube: a watch link, youtu.be, shorts, music.youtube.com, or the id itself."""
    t = (text or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", t):
        return t
    if not re.match(r"^https?://", t):
        t = "https://" + t
    try:
        u = urllib.parse.urlparse(t)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if host.endswith("youtu.be"):
        m = re.match(r"/([A-Za-z0-9_-]{11})", u.path)
        return m.group(1) if m else None
    if "youtube.com" in host or "youtube-nocookie.com" in host:
        v = urllib.parse.parse_qs(u.query).get("v", [""])[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", v):
            return v
        m = re.match(r"/(?:shorts|embed|live|v)/([A-Za-z0-9_-]{11})", u.path)
        return m.group(1) if m else None
    return None


def _info(vid):
    """Title and channel from YouTube's oEmbed. A 401/403 there means the owner blocks playing it outside YouTube."""
    try:
        q = urllib.parse.urlencode({"url": f"https://www.youtube.com/watch?v={vid}", "format": "json"})
        r = urllib.request.Request("https://www.youtube.com/oembed?" + q, headers={"User-Agent": "KNAS42"})
        with urllib.request.urlopen(r, timeout=6) as resp:
            j = json.loads(resp.read())
        return {"title": (j.get("title") or "")[:140], "by": (j.get("author_name") or "")[:80]}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"blocked": True}
        if e.code in (400, 404):
            return {"missing": True}
        return {}
    except Exception:
        return {}                                # no internet check: add it anyway, the TV will skip it if it can't play


def _item(vid, info):
    return {"id": vid, "title": info.get("title") or "YouTube video", "by": info.get("by") or "", "added": time.time()}


def _bump():
    S["rev"] += 1
    _save()
    _want()


def _want():
    DLR.want(([S["now"]["id"]] if S["now"] else []) + [q["id"] for q in S["queue"]])


def _pick_mode(now=None):
    """Decide how the current video plays (lock held). Once it's playing as a file or with YouTube's player,
    that stays, so TVs never switch halfway through."""
    n = S["now"]
    t = now or time.time()
    if not n or S["mode"] in ("file", "embed"):
        return
    if DLR.file_for(n["id"]):
        S["mode"] = "file"
    elif DLR.usable() and DLR.status(n["id"]) in ("queued", "getting", "") and \
            (n.get("blocked") or not S["wait_since"] or t - S["wait_since"] < WAIT_MAX):
        if S["mode"] != "wait":
            S["mode"], S["wait_since"] = "wait", t
        return
    elif not n.get("blocked"):
        S["mode"] = "embed"
    else:                                   # blocked, and it can't be downloaded either
        why = DLR.message(n["id"]) or "its owner blocks playing it outside YouTube"
        S["note"] = f"Skipped “{n['title']}”: {why}."
        S["now"], S["mode"] = None, ""
        if S["queue"]:
            _advance()
        return
    S["started"] = t                        # the clock starts when it actually starts playing
    if S["mode"] == "file":
        DLR.touch(n["id"])


def _dl_ready(vid, meta):
    with _lock:
        for it in ([S["now"]] if S["now"] else []) + S["queue"] + S["played"]:
            if it and it["id"] == vid and it["title"] == "YouTube video" and meta.get("title"):
                it["title"], it["by"] = meta["title"][:140], (meta.get("by") or "")[:80]
        if S["now"] and S["now"]["id"] == vid and S["mode"] == "wait":
            S["mode"] = ""
            _pick_mode()
        S["rev"] += 1
        _save()


def _dl_failed(vid, why):
    with _lock:
        if S["now"] and S["now"]["id"] == vid and S["mode"] == "wait":
            S["mode"] = ""
            _pick_mode()
            S["rev"] += 1
            _save()


def _public(it, playing=False):
    if not it:
        return None
    out = dict(it)
    st = DLR.status(it["id"]) if DLR.enabled() else ""
    out["ready"] = st == "ready"
    out["dl"] = st
    if st == "failed":
        out["dl_msg"] = DLR.message(it["id"])
    if playing:
        out["mode"] = S["mode"]
        if S["mode"] == "file":
            out["file"] = f"/jukebox-video/{it['id']}.mp4"
    return out


def state():
    with _lock:
        if not S["now"] and not S["stopped"] and (S["queue"] or (S["shuffle"] and _can_shuffle())):
            _advance()                     # after a restart (or a stop that ended), pick up where the list is
            _bump()
        # Like real TV, the song keeps playing while nobody's watching the channel. If it should have finished
        # by now (no TV was on that channel to say so), go on to the next one, or end the list.
        n = S["now"]
        if n and S["mode"] in ("file", "embed"):
            length = n.get("secs") or DLR.info_for(n["id"]).get("secs") or 0
            if length and time.time() - S["started"] > length + 12:
                _advance()
                _bump()
        before = (S["now"] or {}).get("id"), S["mode"]
        _pick_mode()
        if ((S["now"] or {}).get("id"), S["mode"]) != before:
            _bump()
        now = S["now"]
        return {"ok": True, "now": _public(now, True), "elapsed": round(time.time() - S["started"], 1) if now and S["mode"] != "wait" else 0,
                "queue": [_public(q) for q in S["queue"][:MAX_QUEUE]], "downloads": DLR.info(), "shuffle": S["shuffle"], "played": len(S["played"]), "can_shuffle": _can_shuffle(),
                "note": S["note"], "rev": S["rev"], "channel": os.environ.get("PARTY_CHANNEL", "0").strip() or "0",
                "name": os.environ.get("PARTY_NAME", "").strip() or "KNAS Jukebox"}


def add(data):
    vid = video_id(data.get("url"))
    if not vid:
        return {"ok": False, "message": "That doesn't look like a YouTube link. Copy the link from YouTube's Share button."}
    info = _info(vid)
    cached = DLR.info_for(vid) if DLR.file_for(vid) else {}
    if info.get("blocked") and not (DLR.usable() or cached):
        return {"ok": False, "message": "That video's owner doesn't let it play outside YouTube. Turn on downloads in Setup → Channels & screen → Jukebox to play videos like this."}
    if info.get("missing") and not cached:
        return {"ok": False, "message": "YouTube can't find that video."}
    if not info.get("title") and data.get("title"):          # picked from search: it already knows the name
        info = dict(info, title=str(data["title"])[:140], by=str(data.get("by") or "")[:80])
    if cached and not info.get("title"):
        info = dict(info, title=cached.get("title"), by=cached.get("by"))
    it = _item(vid, info)
    if data.get("karaoke") or "karaoke" in it["title"].lower():
        it["karaoke"] = True
    if info.get("blocked"):
        it["blocked"] = True
    with _lock:
        if len(S["queue"]) >= MAX_QUEUE:
            return {"ok": False, "message": "The list is full."}
        if data.get("next"):
            S["queue"].insert(0, it)
        else:
            S["queue"].append(it)
        S["stopped"] = False
        if not S["now"]:
            _advance()
        S["note"] = ""
        _bump()
    out = state()
    playing = out["now"] and out["now"]["id"] == vid and out["now"].get("added") == it["added"]
    out["message"] = ("Playing: " if playing else ("Up next: " if data.get("next") else "Added: ")) + it["title"]
    return out


def _can_shuffle():
    return len({p["id"] for p in S["played"]}) >= SHUFFLE_MIN


def _advance():
    """Start the next video (lock held)."""
    if S["now"]:
        S["played"] = [p for p in S["played"] if p["id"] != S["now"]["id"]][-(MAX_PLAYED - 1):] + [S["now"]]
    if S["queue"]:
        S["now"] = S["queue"].pop(0)
    elif S["shuffle"] and _can_shuffle():
        last = S["played"][-1]["id"] if S["played"] else ""
        recent = {p["id"] for p in S["played"][-min(len(S["played"]) - 1, 10):]}
        pool = [p for p in S["played"] if p["id"] not in recent] or [p for p in S["played"] if p["id"] != last]
        S["now"] = dict(random.choice(pool), shuffled=True)
    else:
        S["now"] = None
    S["started"] = time.time()
    S["mode"], S["wait_since"] = "", 0
    _pick_mode()


def ended(data):
    """A TV finished the video. Several TVs may say so; only the first one for the current video counts."""
    with _lock:
        if S["now"] and data.get("id") == S["now"]["id"] and time.time() - S["started"] > 5:
            _advance()
            _bump()
    return state()


def failed(data):
    """A TV couldn't play it (blocked outside YouTube, removed, private): skip it and say why on the remote."""
    with _lock:
        if S["now"] and data.get("id") == S["now"]["id"] and str(data.get("code")) in ("101", "150") \
                and S["mode"] == "embed" and DLR.usable() and DLR.status(S["now"]["id"]) != "failed":
            S["now"]["blocked"] = True       # YouTube's player won't play it: the NAS gets it instead
            S["mode"], S["wait_since"] = "", 0
            _pick_mode()
            _bump()
            return state()
        if S["now"] and data.get("id") == S["now"]["id"]:
            why = REASONS.get(str(data.get("code")), f"YouTube error {data.get('code')}")
            S["note"] = f"Skipped “{S['now']['title']}”: {why}."
            S["played"] = [p for p in S["played"] if p["id"] != S["now"]["id"]]
            S["now"], S["mode"] = None, ""
            if S["queue"]:                 # go on to the next one in the list, but don't start shuffling over a failure
                _advance()
            S["started"] = time.time()
            _bump()
    return state()


def title(data):
    """The TV's YouTube player knows the title even when KNAS couldn't look it up: fill it in."""
    t, by = str(data.get("title") or "")[:140].strip(), str(data.get("by") or "")[:80].strip()
    try:
        secs = float(data.get("secs") or 0)
    except (TypeError, ValueError):
        secs = 0
    with _lock:
        if secs > 5 and S["now"] and S["now"]["id"] == data.get("id"):
            S["now"]["secs"] = round(min(secs, 7200), 1)      # how long it is, so it can end even with no TV watching
        for it in ([S["now"]] if S["now"] else []) + S["queue"] + S["played"]:
            if it and it["id"] == data.get("id") and it["title"] == "YouTube video" and t:
                it["title"], it["by"] = t, it["by"] or by
                S["rev"] += 1
        _save()
    return {"ok": True}


def skip(data=None):
    with _lock:
        S["stopped"] = False
        _advance()
        S["note"] = ""
        _bump()
    return state()


def remove(data):
    with _lock:
        i = int(data.get("i", -1))
        if 0 <= i < len(S["queue"]) and (not data.get("id") or S["queue"][i]["id"] == data.get("id")):
            S["queue"].pop(i)
            _bump()
    return state()


def move_next(data):
    with _lock:
        i = int(data.get("i", -1))
        if 0 <= i < len(S["queue"]) and (not data.get("id") or S["queue"][i]["id"] == data.get("id")):
            S["queue"].insert(0, S["queue"].pop(i))
            _bump()
    return state()


def options(data):
    with _lock:
        if "shuffle" in data:
            S["shuffle"] = bool(data["shuffle"])
        if data.get("clear"):
            S["queue"] = []
        if data.get("forget"):
            S["played"] = []
        if data.get("stop"):
            if S["now"]:
                S["played"] = [p for p in S["played"] if p["id"] != S["now"]["id"]][-(MAX_PLAYED - 1):] + [S["now"]]
            S["now"], S["started"], S["mode"] = None, 0, ""
            S["stopped"] = True
        if data.get("clear_downloads"):
            S["note"] = f"Deleted {DLR.clear_cache()} downloaded videos."
        _bump()
    return state()
