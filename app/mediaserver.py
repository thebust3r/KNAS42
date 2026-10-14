"""Tell Jellyfin (or Emby) when KNAS changes an episode, so new commercial breaks show up by themselves.

After the Tools page adds breaks, the episode file has new chapter markers, but Jellyfin (and ErsatzTV,
which reads from Jellyfin) only notices after it re-reads the file. This module finds each changed
episode in Jellyfin's library and asks Jellyfin to refresh just those, a little while after the last
change so a big batch turns into a few requests instead of thousands.

Settings: JELLYFIN_URL (like http://192.168.1.50:8096) and JELLYFIN_API_KEY (Jellyfin: Dashboard →
API Keys; Emby: Settings → Advanced → API Keys). Both servers speak the same API.
"""
import json, os, threading, time, urllib.parse, urllib.request

PENDING = []                      # (old path, new path) as KNAS sees them
STATE = {"last": None, "message": "", "refreshed": 0, "added": 0, "missing": 0, "error": ""}
_lock = threading.Lock()
_kick = threading.Event()
_started = False
WAIT = 20                          # seconds of quiet after the last change before telling Jellyfin
_items = {"at": 0, "by_stem": {}}  # Jellyfin's episode list, kept for a few minutes


def _cfg():
    url = (os.environ.get("JELLYFIN_URL") or "").strip().rstrip("/")
    key = (os.environ.get("JELLYFIN_API_KEY") or "").strip()
    return url, key


def enabled():
    url, key = _cfg()
    return bool(url and key)


def _req(url, key, path, method="GET", body=None, timeout=30):
    """Sends the key the way current Jellyfin wants it (Authorization: MediaBrowser Token=...) and the old way
    Emby uses (X-Emby-Token). Emby also answers under /emby."""
    last = None
    for prefix in ("", "/emby"):
        data = json.dumps(body).encode() if body is not None else (b"" if method == "POST" else None)
        r = urllib.request.Request(url + prefix + path, data=data, method=method,
                                   headers={
                                       # current Jellyfin wants the key here (the old X-Emby-Token way is off by default now)
                                       "Authorization": f'MediaBrowser Client="KNAS42", Device="KNAS42", DeviceId="knas42", Version="1", Token="{key}"',
                                       "X-Emby-Token": key,           # Emby and older Jellyfin
                                       "Accept": "application/json", "Content-Type": "application/json", "User-Agent": "KNAS42"})
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw and raw[:1] in (b"{", b"[") else {}
        except urllib.error.HTTPError as e:
            last = e
            if e.code == 404 and prefix == "":
                continue
            raise
    raise last


def test(url, key):
    url = (url or "").strip().rstrip("/")
    key = (key or "").strip()
    if not url or not key:
        return {"ok": False, "message": "Type the address and the API key first."}
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    try:
        info = _req(url, key, "/System/Info", timeout=8)
        name = info.get("ServerName") or "your server"
        kind = "Emby" if "emby" in (info.get("ProductName") or "").lower() else "Jellyfin"
        return {"ok": True, "url": url, "message": f"Connected to {kind} server “{name}” (version {info.get('Version', '?')})."}
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"ok": False, "url": url, "message": "Jellyfin answered, but didn't accept that API key. Make a new one under Dashboard → API Keys."}
        return {"ok": False, "url": url, "message": f"Jellyfin answered with an error ({e.code})."}
    except Exception as e:
        return {"ok": False, "url": url, "message": f"Couldn't reach Jellyfin there ({e}). Check the IP and port (usually 8096)."}


def status():
    with _lock:
        return dict(STATE, enabled=enabled(), waiting=len(PENDING))


def changed(old, new):
    """KNAS rewrote an episode (old path -> new path, the same unless .avi became .mkv)."""
    if not enabled():
        return
    with _lock:
        PENDING.append((old, new))
    _start()
    _kick.set()


def _start():
    global _started
    with _lock:
        if _started:
            return
        _started = True
    threading.Thread(target=_loop, daemon=True, name="jellyfin-refresh").start()


def _loop():
    while True:
        _kick.wait()
        while True:                      # wait until changes stop coming for a bit
            _kick.clear()
            if not _kick.wait(WAIT):
                break
        with _lock:
            batch, PENDING[:] = list(PENDING), []
        if batch:
            try:
                _send(batch)
            except Exception as e:
                with _lock:
                    STATE.update(error=str(e), message=f"Couldn't tell Jellyfin: {e}", last=time.time())
                print("[jellyfin]", e, flush=True)


def _parts(p):
    return [x for x in p.replace("\\", "/").split("/") if x]


def _stem(p):
    return os.path.splitext(_parts(p)[-1])[0].lower() if _parts(p) else ""


def _load_items(url, key):
    if time.time() - _items["at"] < 300 and _items["by_stem"]:
        return _items["by_stem"]
    q = "/Items?" + urllib.parse.urlencode({"Recursive": "true", "IncludeItemTypes": "Episode,Movie,Video,MusicVideo",
                                           "Fields": "Path", "EnableImages": "false", "EnableUserData": "false"})
    try:
        res = _req(url, key, q, timeout=120)
    except urllib.error.HTTPError as e:      # older servers want a user
        if e.code not in (400, 401, 403, 404):
            raise
        users = _req(url, key, "/Users", timeout=20)
        uid = next((u["Id"] for u in users if (u.get("Policy") or {}).get("IsAdministrator")), users[0]["Id"] if users else "")
        res = _req(url, key, f"/Users/{uid}" + q, timeout=120)
    by = {}
    for it in res.get("Items") or []:
        p = it.get("Path")
        if p:
            by.setdefault(_stem(p), []).append((p, it["Id"]))
    _items.update(at=time.time(), by_stem=by)
    return by


def _match(by, knas_path):
    """Find the episode in Jellyfin's list: same file name (ignoring .avi vs .mkv), and as many matching
    folders above it as possible, since Jellyfin may see the shows folder under a different path."""
    cands = by.get(_stem(knas_path)) or []
    if not cands:
        return None
    mine = [x.lower() for x in _parts(knas_path)[:-1]]

    def score(c):
        theirs = [x.lower() for x in _parts(c[0])[:-1]]
        n = 0
        while n < min(len(mine), len(theirs)) and mine[-1 - n] == theirs[-1 - n]:
            n += 1
        return n
    best = max(cands, key=score)
    return best if score(best) >= 1 or len(cands) == 1 else None


def _send(batch):
    url, key = _cfg()
    by = _load_items(url, key)
    refreshed = added = missing = 0
    updates = []
    for old, new in batch:
        hit = _match(by, old) or _match(by, new)
        if not hit:
            missing += 1
            continue
        jpath, jid = hit
        new_name = _parts(new)[-1]
        if _parts(jpath)[-1] == new_name:           # same file, new chapters inside: re-read it
            _req(url, key, f"/Items/{jid}/Refresh?" + urllib.parse.urlencode({
                "Recursive": "false", "MetadataRefreshMode": "FullRefresh", "ImageRefreshMode": "None",
                "ReplaceAllMetadata": "false", "ReplaceAllImages": "false"}), method="POST")
            refreshed += 1
        else:                                        # .avi became .mkv: tell Jellyfin the file moved
            jnew = jpath[: len(jpath) - len(_parts(jpath)[-1])] + new_name
            updates += [{"Path": jnew, "UpdateType": "Created"}, {"Path": jpath, "UpdateType": "Deleted"}]
            added += 1
    if updates:
        _req(url, key, "/Library/Media/Updated", method="POST", body={"Updates": updates})
        _items["at"] = 0                              # the list changed
    with _lock:
        STATE.update(last=time.time(), refreshed=STATE["refreshed"] + refreshed, added=STATE["added"] + added,
                     missing=STATE["missing"] + missing, error="")
        total = STATE["refreshed"] + STATE["added"]
        msg = f"told Jellyfin about {total} episode{'s' if total != 1 else ''} since KNAS started"
        if STATE["missing"]:
            msg += f" ({STATE['missing']} weren't in Jellyfin's library)"
        STATE["message"] = msg + "."
    print("[jellyfin]", msg, flush=True)
