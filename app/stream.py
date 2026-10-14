"""Stream channel: paste a link to a live stream on your phone and it plays on its own channel.

Off until it has a channel number (STREAM_CHANNEL, setup page → Experimental → Phone extras). The phone
page is /streams. Works with YouTube live streams, Twitch, lots of news and TV station sites, and direct
stream links (.m3u8). KNAS uses the jukebox's video tool (yt-dlp) to find the real video feed behind the
page, then passes it to the TVs through the NAS, so every TV and browser can play it.

Paid services (Netflix, Hulu, ESPN+...) lock their video to their own apps, so they can't work, and sites
that rebroadcast paid channels without permission aren't supported.
"""
import base64, hashlib, hmac, json, os, re, secrets, subprocess, threading, time, urllib.parse, urllib.request

import jukebox_dl as DLR

DATA = ""
S = {"url": "", "title": "", "by": "", "kind": "", "src": "", "headers": {}, "live": False, "at": 0,
     "rev": 0, "error": "", "resolving": False, "favs": []}
_lock = threading.RLock()          # RLock: some steps that hold it also read the state
KEY = secrets.token_bytes(16)          # signs the addresses KNAS hands the TVs, so it can't be used as an open proxy
REMOTE = None
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
NOT_SUPPORTED = ("crackstreams", "methstreams", "buffstreams", "sportsurge", "streameast", "totalsportek", "streamsgate",
                 "sportshd", "nbabite", "nflbite", "hesgoal", "vipbox", "vipleague", "strikeout", "720pstream", "markkystreams",
                 "rojadirecta", "sport365", "stream2watch", "footybite", "givemenbastreams", "6streams", "bilasport")


def channel():
    v = os.environ.get("STREAM_CHANNEL", "0").strip()
    return "" if v in ("", "0") or v.lower() == "off" else v


def enabled():
    return bool(channel())


def setup(data_dir, remote):
    global DATA, REMOTE
    DATA, REMOTE = data_dir, remote
    try:
        with open(os.path.join(DATA, "stream.json")) as f:
            j = json.load(f)
        S["url"], S["title"], S["by"] = j.get("url", ""), j.get("title", ""), j.get("by", "")
        S["favs"] = [x for x in j.get("favs", []) if isinstance(x, dict) and x.get("url")][:30]
    except (OSError, ValueError):
        pass


def _save():
    try:
        with open(os.path.join(DATA, "stream.json"), "w") as f:
            json.dump({"url": S["url"], "title": S["title"], "by": S["by"], "favs": S["favs"]}, f, indent=1)
    except OSError:
        pass


def _clean_url(u):
    u = str(u or "").strip()
    m = re.search(r"https?://\S+", u)
    if not m:
        raise ValueError("Paste a link that starts with http:// or https://")
    u = m.group(0).rstrip(").,")
    host = (urllib.parse.urlparse(u).hostname or "").lower()
    if not host:
        raise ValueError("That doesn't look like a link.")
    if any(b in host for b in NOT_SUPPORTED):
        raise ValueError("KNAS doesn't play that site. Try a YouTube, Twitch or news station live stream.")
    return u


# ---------------------------------------------------------------- finding the video behind a page

def _resolve(url):
    path = urllib.parse.urlparse(url).path.lower()
    if path.endswith(".m3u8"):
        return {"kind": "hls", "src": url, "headers": {}, "title": urllib.parse.urlparse(url).hostname, "by": "", "live": True}
    if path.endswith((".mp4", ".m4v", ".webm")):
        return {"kind": "file", "src": url, "headers": {}, "title": os.path.basename(path), "by": "", "live": False}
    if not DLR.DATA:
        raise RuntimeError("KNAS isn't ready yet")
    if not DLR._ensure_tools():
        raise RuntimeError(DLR.TOOLS.get("message") or "the video tool couldn't be set up")
    cmd, _own = DLR._ytdlp_cmd()
    args = cmd + ["--no-playlist", "--no-warnings", "-J", "--socket-timeout", "20",
                  "-f", "b[height<=720][protocol^=m3u8]/b[protocol^=m3u8]/b[height<=720]/b"]
    name, flag, _p = DLR._js()
    if flag:
        args += ["--js-runtimes", flag]
    args += ["--remote-components", "ejs:github"]
    cookies = os.path.join(DATA, "youtube-cookies.txt")
    if os.path.isfile(cookies) and "youtu" in url:
        args += ["--cookies", cookies]
    r = subprocess.run(args + [url], capture_output=True, text=True, timeout=90)
    if r.returncode != 0 or not r.stdout.strip().startswith("{"):
        err = (r.stderr or "").strip().splitlines()
        err = err[-1] if err else "no video found"
        if "Unsupported URL" in err or "No video formats" in err or "Unable to extract" in err:
            raise RuntimeError("couldn't find a video stream on that page")
        if "not currently live" in err.lower() or "offline" in err.lower() or "will begin" in err.lower():
            raise RuntimeError("that stream isn't live right now")
        if "drm" in err.lower():
            raise RuntimeError("that site locks its video (DRM), so it can only play in its own app")
        raise RuntimeError(re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?", "", err)[:160])
    j = json.loads(r.stdout)
    src = j.get("url") or ""
    proto = j.get("protocol") or ""
    if not src and j.get("requested_formats"):
        f = j["requested_formats"][0]
        src, proto = f.get("url", ""), f.get("protocol", "")
    if not src:
        raise RuntimeError("couldn't find a video stream on that page")
    hdr = {k: v for k, v in (j.get("http_headers") or {}).items() if k.lower() in ("user-agent", "referer", "origin", "cookie", "accept")}
    return {"kind": "hls" if "m3u8" in proto or ".m3u8" in src else "file", "src": src, "headers": hdr,
            "title": (j.get("title") or j.get("fulltitle") or "")[:120], "by": (j.get("uploader") or j.get("channel") or "")[:80],
            "live": bool(j.get("is_live"))}


def _resolve_now(url, quiet=False):
    try:
        got = _resolve(url)
        with _lock:
            if S["url"] != url:
                return
            S.update(got, at=time.time(), error="", resolving=False)
            if got["title"] and got["title"] == (urllib.parse.urlparse(url).hostname or ""):
                S["title"] = S["title"] or got["title"]
            S["rev"] += 1
            _save()
        print(f"[stream] playing {S['title'] or url}", flush=True)
    except Exception as e:
        with _lock:
            if S["url"] == url:
                S.update(resolving=False, error=str(e)[:1].upper() + str(e)[1:] + ".", src="")
                S["rev"] += 1
        print(f"[stream] {url}: {e}", flush=True)


def play(data):
    _fails.clear()
    if not enabled():
        return {"ok": False, "message": "The Stream channel is off (setup page → Experimental → Phone extras)."}
    url = _clean_url(data.get("url"))
    with _lock:
        S.update(url=url, title=str(data.get("title") or "")[:120], by="", kind="", src="", error="", resolving=True)
        S["rev"] += 1
        _save()
    threading.Thread(target=_resolve_now, args=(url,), daemon=True, name="stream-find").start()
    if data.get("tune"):
        tune_all()
    return state()


def stop(data=None):
    with _lock:
        S.update(url="", title="", by="", kind="", src="", error="", resolving=False)
        S["rev"] += 1
        _save()
    return state()


_last_retry = [0]
_fails = []


def failed(data=None):
    """A TV couldn't play the feed: links from YouTube and Twitch expire after a few hours, so look it up again."""
    with _lock:
        if not S["url"] or S["resolving"] or time.time() - _last_retry[0] < 30:
            return state()
        _last_retry[0] = time.time()
        _fails[:] = [t for t in _fails if time.time() - t < 600] + [time.time()]
        if len(_fails) > 3:                 # found it again and again, and the TV still can't play it: stop trying
            _fails.clear()
            S.update(src="", error="The TV couldn't play that stream. Try a different link.")
            S["rev"] += 1
            return state()
        S["resolving"] = True
        url = S["url"]
    threading.Thread(target=_resolve_now, args=(url, True), daemon=True).start()
    return state()


def fav(data):
    with _lock:
        if data.get("remove"):
            S["favs"] = [f for f in S["favs"] if f["url"] != data["remove"]]
        else:
            url = _clean_url(data.get("url") or S["url"])
            title = str(data.get("title") or (S["title"] if url == S["url"] else "") or urllib.parse.urlparse(url).hostname)[:80]
            S["favs"] = [f for f in S["favs"] if f["url"] != url][:29] + [{"url": url, "title": title}]
        _save()
    return state()


def tune_all():
    if not REMOTE or not enabled():
        return 0
    on = [t["id"] for t in REMOTE.tvs() if t["on"]]
    for t in on:
        REMOTE._push(t, {"tune": channel()})
    return len(on)


def state():
    with _lock:
        # a feed found more than 5 hours ago has probably expired: find it again before a TV asks
        if S["url"] and S["src"] and not S["resolving"] and time.time() - S["at"] > 5 * 3600:
            S["resolving"] = True
            threading.Thread(target=_resolve_now, args=(S["url"],), daemon=True).start()
        if S["url"] and not S["src"] and not S["resolving"] and not S["error"]:      # after a restart
            S["resolving"] = True
            threading.Thread(target=_resolve_now, args=(S["url"],), daemon=True).start()
        return {"ok": True, "on": enabled(), "channel": channel(), "name": os.environ.get("STREAM_NAME", "").strip() or "KNAS Stream",
                "url": S["url"], "title": S["title"], "by": S["by"], "kind": S["kind"], "live": S["live"], "ready": bool(S["src"]),
                "feed": ("/streamfeed/main.m3u8" if S["kind"] == "hls" else "/streamfeed/file") + f"?r={S['rev']}" if S["src"] else "",
                "resolving": S["resolving"], "error": S["error"], "rev": S["rev"], "favs": list(S["favs"])}


# ---------------------------------------------------------------- passing the feed through the NAS

def _sign(u):
    return hmac.new(KEY, u.encode(), hashlib.sha256).hexdigest()[:20]


def _proxied(u):
    b = base64.urlsafe_b64encode(u.encode()).decode().rstrip("=")
    return f"/streamfeed/p?u={b}&s={_sign(u)}"


def _open(u, rng=None):
    h = {"User-Agent": UA}
    h.update(S["headers"] or {})
    if rng:
        h["Range"] = rng
    return urllib.request.urlopen(urllib.request.Request(u, headers=h), timeout=25)


def _rewrite(text, base):
    def fix(u):
        return _proxied(urllib.parse.urljoin(base, u.strip()))
    out = []
    for line in text.splitlines():
        if line and not line.startswith("#"):
            out.append(fix(line))
        elif 'URI="' in line:
            out.append(re.sub(r'URI="([^"]+)"', lambda m: 'URI="' + fix(m.group(1)) + '"', line))
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def serve(handler, path, qs):
    """/streamfeed/main.m3u8, /streamfeed/p?u=..., /streamfeed/file"""
    q = lambda k: (qs.get(k) or [""])[0]
    if path == "/streamfeed/main.m3u8" or path == "/streamfeed/file":
        target = S["src"]
        if not target:
            return handler.send_error(404)
    elif path == "/streamfeed/p":
        try:
            b = q("u")
            target = base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode()
        except Exception:
            return handler.send_error(400)
        if not hmac.compare_digest(_sign(target), q("s")):
            return handler.send_error(403)
    else:
        return handler.send_error(404)
    try:
        r = _open(target, handler.headers.get("Range") if path != "/streamfeed/main.m3u8" else None)
    except urllib.error.HTTPError as e:
        return handler.send_error(e.code if e.code in (403, 404, 410) else 502)
    except Exception:
        return handler.send_error(502)
    with r:
        ctype = r.headers.get("Content-Type", "")
        is_list = "mpegurl" in ctype.lower() or target.split("?")[0].endswith(".m3u8") or path == "/streamfeed/main.m3u8"
        try:
            if is_list:
                body = r.read(4 * 1024 * 1024)
                if body.lstrip().startswith(b"#EXTM3U"):
                    body = _rewrite(body.decode("utf-8", "replace"), r.geturl()).encode()
                    ctype = "application/vnd.apple.mpegurl"
                handler.send_response(200)
                handler.send_header("Content-Type", ctype or "application/vnd.apple.mpegurl")
                handler.send_header("Cache-Control", "no-store")
                handler.send_header("Content-Length", str(len(body)))
                handler.end_headers()
                handler.wfile.write(body)
                return
            handler.send_response(r.status)
            for h in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                if r.headers.get(h):
                    handler.send_header(h, r.headers[h])
            handler.send_header("Cache-Control", "no-store")
            if not r.headers.get("Content-Length"):
                handler.close_connection = True
            handler.end_headers()
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                handler.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
