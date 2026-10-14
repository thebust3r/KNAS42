#!/usr/bin/env python3
"""KNAS 42 - a 90s local-forecast channel for a CRT. Stdlib only."""
import html, json, os, re, time, threading, urllib.request, urllib.parse, http.client
import xml.etree.ElementTree as ET
import mimetypes
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("font/woff", ".woff")
import keeper
keeper.load_settings()          # settings.txt wins over docker-compose
import sports, radio, clips, wizard, looks, clock, facts, tools, remote, mediaserver, history, gametime, party, qr, alerts, game
import securecert, ws, throw, livecam, voice, duck, fun, flick, stream
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

VERSION = "2.22.1"
HERE = os.path.dirname(os.path.abspath(__file__))       # the app folder
ROOT = os.path.dirname(HERE)                            # your KNAS folder
DATA = os.path.join(ROOT, "data")                       # caches and logs
WEB = os.path.join(ROOT, "web")
MUSIC = os.environ.get("MUSIC_DIR") or (os.path.join(ROOT, "music") if os.path.isdir(os.path.join(ROOT, "music")) else "/music")
FACTS = os.environ.get("FACTS_FILE", os.path.join(ROOT, "facts.txt"))
TEAMS = os.environ.get("TEAMS_FILE", os.path.join(ROOT, "teams.txt"))
TRIVIA = os.environ.get("TRIVIA_FILE", os.path.join(ROOT, "trivia.txt"))
VIDEOS = os.environ.get("BREAK_VIDEOS_DIR", os.path.join(ROOT, "break-videos"))
VIDEO_EXT = (".mp4", ".webm", ".m4v", ".mov")
AUDIO_EXT = (".mp3", ".ogg", ".m4a", ".aac", ".wav", ".opus")


def env(k, d=""):
    return os.environ.get(k, d).strip()


PORT = int(env("PORT", "8642"))

# ---------- where you are: LATITUDE/LONGITUDE, or looked up from CITY_NAME ----------
US_STATES = {"AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California","CO":"Colorado","CT":"Connecticut","DE":"Delaware",
  "FL":"Florida","GA":"Georgia","HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa","KS":"Kansas","KY":"Kentucky","LA":"Louisiana",
  "ME":"Maine","MD":"Maryland","MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi","MO":"Missouri","MT":"Montana","NE":"Nebraska",
  "NV":"Nevada","NH":"New Hampshire","NJ":"New Jersey","NM":"New Mexico","NY":"New York","NC":"North Carolina","ND":"North Dakota","OH":"Ohio",
  "OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania","RI":"Rhode Island","SC":"South Carolina","SD":"South Dakota","TN":"Tennessee","TX":"Texas",
  "UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington","WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming","DC":"District of Columbia"}
LOC_CACHE = os.path.join(DATA, "location-cache.json")


AUTO_CACHE = os.path.join(DATA, "auto-location.json")
AUTO = {}          # filled when KNAS guessed the town from your internet connection
COUNTRY = ""       # two-letter country code, used to pick °F or °C when UNITS is blank


def auto_locate():
    """No town set yet: ask a free service which town this internet connection is in, so KNAS works
    straight away. Cached for a week. Set a town on the setup page and this never runs."""
    try:
        with open(AUTO_CACHE, encoding="utf-8") as f:
            c = json.load(f)
        if time.time() - c.get("at", 0) < 7 * 86400 and c.get("lat") is not None:
            return c
    except (OSError, ValueError):
        c = None
    tries = (
        ("https://ipwho.is/", lambda j: j.get("success") is not False and
         (j.get("city"), j.get("region_code") or j.get("region"), j.get("latitude"), j.get("longitude"), (j.get("timezone") or {}).get("id"), j.get("country_code"))),
        ("https://ipapi.co/json/", lambda j: not j.get("error") and
         (j.get("city"), j.get("region_code") or j.get("region"), j.get("latitude"), j.get("longitude"), j.get("timezone"), j.get("country_code"))),
        ("https://freeipapi.com/api/json", lambda j:
         (j.get("cityName"), j.get("regionName"), j.get("latitude"), j.get("longitude"), (j.get("timeZones") or [None])[0], j.get("countryCode"))),
    )
    for url, pick in tries:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "knas42/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=8) as r:
                got = pick(json.loads(r.read().decode()))
            if got and got[2] is not None and got[3] is not None:
                city, region, lat, lon, tz, cc = got
                out = {"at": time.time(), "city": city or "Your Town", "region": region or "", "lat": float(lat), "lon": float(lon),
                       "tz": tz or "auto", "cc": (cc or "").upper()}
                os.makedirs(DATA, exist_ok=True)
                with open(AUTO_CACHE, "w", encoding="utf-8") as f:
                    json.dump(out, f)
                return out
        except Exception:
            continue
    return c   # an old guess is better than none


def resolve_location():
    """-> (city label, lat, lon, timezone). Uses LATITUDE/LONGITUDE if set, otherwise looks up CITY_NAME once.
    With neither, KNAS guesses from your internet connection so it works with no setup at all."""
    global COUNTRY
    raw = env("CITY_NAME")
    label = raw.split(",")[0].strip() if raw else "My Town"
    tz = env("TZ") or "auto"
    if env("LATITUDE") and env("LONGITUDE"):
        return label, env("LATITUDE"), env("LONGITUDE"), tz
    if not raw:
        g = auto_locate()
        if g:
            AUTO.update(g); COUNTRY = g.get("cc", "")
            print(f"No town set yet, so KNAS guessed it from your internet connection: {g['city']}"
                  f"{', ' + g['region'] if g.get('region') else ''}. Change it any time on the setup page.", flush=True)
            return g["city"], str(g["lat"]), str(g["lon"]), env("TZ") or g.get("tz") or "auto"
        print("KNAS couldn't guess your town (no internet?). Open the setup page (address below) and pick it.", flush=True)
        return label, "39.8283", "-98.5795", tz         # middle of the USA until you do
    try:
        with open(LOC_CACHE, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("query") == raw:
            COUNTRY = c.get("cc", "")
            return label, str(c["lat"]), str(c["lon"]), env("TZ") or c.get("tz") or "auto"
    except (OSError, ValueError, KeyError):
        pass
    name, _, where = raw.partition(",")
    where = where.strip()
    where_full = US_STATES.get(where.upper(), where).lower()
    try:
        q = urllib.parse.urlencode({"name": name.strip(), "count": 20, "language": "en", "format": "json"})
        req = urllib.request.Request("https://geocoding-api.open-meteo.com/v1/search?" + q, headers={"User-Agent": "knas42/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            results = json.loads(r.read().decode()).get("results") or []
        pick = None
        for res in results:
            fields = [str(res.get(k, "")).lower() for k in ("admin1", "admin2", "country", "country_code")]
            if not where or any(f and (f == where_full or f == where.lower()) for f in fields):
                pick = res
                break
        if pick:
            out = {"query": raw, "lat": pick["latitude"], "lon": pick["longitude"], "tz": pick.get("timezone") or "auto",
                   "cc": (pick.get("country_code") or "").upper()}
            with open(LOC_CACHE, "w", encoding="utf-8") as f:
                json.dump(out, f)
            COUNTRY = out["cc"]
            print(f"Location: {raw} -> {out['lat']}, {out['lon']} ({out['tz']})", flush=True)
            return label, str(out["lat"]), str(out["lon"]), env("TZ") or out["tz"]
        print(f"!! Couldn't find '{raw}'. Try 'City, State' or set LATITUDE and LONGITUDE in settings.txt", flush=True)
    except Exception as e:
        print(f"!! Couldn't look up '{raw}' ({e}). Set LATITUDE and LONGITUDE in settings.txt", flush=True)
    return label, "39.8283", "-98.5795", tz



ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/"
MAP_STYLES = {   # name: (tile address, credit line)
    "osm":       ("https://tile.openstreetmap.org/{z}/{x}/{y}.png", "Map © OpenStreetMap contributors"),
    "dark":      (ESRI + "Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", "Map © Esri"),
    "light":     (ESRI + "Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", "Map © Esri"),
    "terrain":   (ESRI + "World_Terrain_Base/MapServer/tile/{z}/{y}/{x}", "Map © Esri"),
    "relief":    (ESRI + "World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}", "Map © Esri"),
    "satellite": (ESRI + "World_Imagery/MapServer/tile/{z}/{y}/{x}", "Imagery © Esri, Maxar, Earthstar Geographics"),
    "streets":   (ESRI + "World_Street_Map/MapServer/tile/{z}/{y}/{x}", "Map © Esri"),
    "topo":      ("https://tile.opentopomap.org/{z}/{x}/{y}.png", "Map © OpenStreetMap contributors, OpenTopoMap"),
}


def map_style():
    if env("BASEMAP_URL"):
        return env("BASEMAP_URL"), "Map: custom"
    if env("MAP_KEY") and env("MAP_STYLE", "osm") == "carto":
        return (f"https://basemaps.cartocdn.com/rastertiles/voyager_nolabels/{{z}}/{{x}}/{{y}}.png?key={env('MAP_KEY')}",
                "Map © OpenStreetMap contributors, CARTO")
    return MAP_STYLES.get(env("MAP_STYLE", "osm").lower(), MAP_STYLES["osm"])

CITY, LAT, LON, TZ = resolve_location()


def configured_now():
    """A town is set, or KNAS guessed one. Only when both fail do the screens send you to the setup page."""
    return bool(env("CITY_NAME") or (env("LATITUDE") and env("LONGITUDE")) or AUTO)
# UNITS blank = pick for you: °F in the US, °C everywhere else
METRIC = env("UNITS").lower().startswith("m") if env("UNITS") else (COUNTRY not in ("", "US", "LR", "MM", "PR", "GU", "VI"))
CONFIG = {
    "station": env("STATION_NAME", "KNAS 42"),
    "city": CITY,
    "units": "metric" if METRIC else "us",
    "needs_setup": not configured_now(),
    "cities": [],
    "page_seconds": int(env("PAGE_SECONDS", "10")),
    "crawl": env("CRAWL_MESSAGE", ""),
    "spotify_top_label": env("SPOTIFY_TOP_LABEL", "This Week"),
    "lat": LAT, "lon": LON,
    # Map under the radar (MAP_STYLE). None of these need a key.
    "basemap": map_style()[0],
    "break_video_max": env("BREAK_VIDEO_MAX", "90"),
    "shuffle": env("SHUFFLE", "on").lower() not in ("off", "no", "0", "false"),
    # which weather pages / break segments to show (blank = all)
    "pages": [x.strip().lower() for x in env("WEATHER_PAGES").split(",") if x.strip()],
    "segments": [x.strip().lower() for x in env("BREAK_SEGMENTS").split(",") if x.strip()],
    "map_credit": map_style()[1],
}
OPEN_METEO = env("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")

SPOTIFY_URL = env("SPOTIFY_URL").rstrip("/")
SPOTIFY_NOW = env("SPOTIFY_NOWPLAYING_PATH", "/api/now")
SPOTIFY_TOP = env("SPOTIFY_TOP_PATH", "/api/top/artists?range=7d&limit=7")
try:
    SPOTIFY_HEADERS = json.loads(env("SPOTIFY_HEADERS") or "{}")
except ValueError:
    SPOTIFY_HEADERS = {}

KUMA_URL = env("KUMA_URL").rstrip("/")
KUMA_SLUG = env("KUMA_SLUG", "nas")

ETV_URL = env("ERSATZTV_URL").rstrip("/")
ETV_MODE = env("ERSATZTV_MODE", "segmenter")
TV_CONFIG = {
    "knas_channel": env("KNAS_CHANNEL", "42"),
    "static_volume": env("STATIC_VOLUME", "50"),   # static between channels, 0-100
    "sports_channel": env("SPORTS_CHANNEL", "43"),
    "party_channel": env("PARTY_CHANNEL", "0"),     # YouTube jukebox, 0 = off
    "party_name": env("PARTY_NAME", "KNAS Jukebox"),
    "trivia_channel": env("TRIVIA_CHANNEL", "0"),   # party trivia game, 0 = off
    "trivia_name": env("TRIVIA_NAME", "KNAS Games"),
    "wrapped_channel": env("WRAPPED_CHANNEL", "0"),  # KNAS Wrapped on a loop, 0 = off
    "livecam_channel": env("LIVECAM_CHANNEL", "0"),  # phone cameras as a live channel, 0 = off
    "livecam_name": env("LIVECAM_NAME", "KNAS Live Cam"),
    "duck_channel": env("DUCK_CHANNEL", "0"),        # Duck Season light-gun game, 0 = off
    "duck_name": env("DUCK_NAME", "Duck Season"),
    "flick_channel": env("FLICK_CHANNEL", "0"),      # darts, hoops, bowling, cup pong, 0 = off
    "flick_name": env("FLICK_NAME", "Flick Games"),
    "stream_channel": env("STREAM_CHANNEL", "0"),    # live streams from a link, 0 = off
    "stream_name": env("STREAM_NAME", "KNAS Stream"),
    "city": CITY,
    "mode": ETV_MODE,
    "configured": bool(ETV_URL),
    "needs_setup": not configured_now(),
    "station": env("STATION_NAME", "KNAS 42"),
}

LOCAL_NEWS = [u.strip() for u in env("LOCAL_NEWS_FEEDS").split(",") if u.strip()]
US_NEWS = [u.strip() for u in env("US_NEWS_FEEDS", "https://feeds.npr.org/1001/rss.xml").split(",") if u.strip()]


# ---------- experimental tools: hidden on the setup page until someone types the code ----------
EXP_FILE = os.path.join(DATA, "experimental.json")
_exp_tries = []


def experimental():
    try:
        with open(EXP_FILE) as f:
            return bool(json.load(f).get("on"))
    except (OSError, ValueError):
        return False


def set_experimental(on):
    try:
        with open(EXP_FILE, "w") as f:
            json.dump({"on": bool(on)}, f)
    except OSError:
        pass


def try_code(typed):
    """The setup page sends whatever digits were typed; it unlocks if they end with the code.
    The code is EXPERIMENTAL_CODE in settings.txt (the setup page never shows it)."""
    now = time.time()
    _exp_tries[:] = [t for t in _exp_tries if now - t < 60]
    if len(_exp_tries) >= 40:
        return False
    _exp_tries.append(now)
    code = re.sub(r"\D", "", env("EXPERIMENTAL_CODE", "098123")) or "098123"
    return re.sub(r"\D", "", str(typed or ""))[-24:].endswith(code)


def configured():
    """True once a town is set (setup page or settings.txt) or KNAS guessed it from your connection."""
    return configured_now()


def lan_ip():
    """This machine's address on your home network."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "YOUR_NAS_IP"


# KNAS's secure address (https), for the camera, microphone and motion sensors (app/securecert.py)
_sp = (env("SECURE_PORT") or "").strip().lower()
SECURE_PORT = 0 if _sp in ("off", "no", "0", "false") else (int(_sp) if _sp.isdigit() and 0 < int(_sp) < 65536 else PORT + 3)


def secure_base(host=""):
    """https://NAS:8645, or "" when the secure address is off or didn't start."""
    if not SECURE_PORT or not securecert.STATE["on"]:
        return ""
    host = host or lan_ip()
    return f"https://{host}:{SECURE_PORT}"


def builtin_channels():
    return {"weather": env("KNAS_CHANNEL", "42"), "sports": env("SPORTS_CHANNEL", "43"), "party": env("PARTY_CHANNEL", "0"),
            "trivia": env("TRIVIA_CHANNEL", "0"), "wrapped": env("WRAPPED_CHANNEL", "0"), "livecam": env("LIVECAM_CHANNEL", "0"),
            "duck": env("DUCK_CHANNEL", "0"), "flick": env("FLICK_CHANNEL", "0"), "stream": env("STREAM_CHANNEL", "0")}


def voice_command(data):
    """The voice remote: words in, channel changes and button presses out."""
    if not voice.enabled():
        return {"ok": False, "say": "The voice remote is off (setup page → Experimental)."}
    tid = remote._clean_id(data.get("id"))
    tv = next((t for t in remote.tvs() if t["id"] == tid), None)
    if not tv or not tv["on"]:
        return {"ok": False, "say": "That TV is off."}
    chans = [c for c in tv["list"] if c[0] not in tv["hidden"]]
    try:
        programs = cached("tv", 120, tv_guide).get("programs", {}) if ETV_URL else {}
    except Exception:
        programs = {}
    texts = [str(x)[:200] for x in ([data.get("text")] + list(data.get("alts") or [])[:4]) if x]
    built = {k: v for k, v in builtin_channels().items() if v and v != "0"}
    act = None
    for t in texts:                      # the phone sends its best guesses; use the first that makes sense
        a = voice.understand(t, chans, programs, built)
        if act is None or ("tune" in a or "key" in a or "jukebox" in a or "later" in a):
            act, heard = a, t
            if "tune" in a or "key" in a or "jukebox" in a or "later" in a:
                break
    if not act:
        return {"ok": False, "say": "I didn't catch that."}
    say = act.get("say", "")
    if act.get("key"):
        for _ in range(int(act.get("times", 1))):
            remote._push(tid, {"k": act["key"]})
    elif act.get("tune"):
        remote._push(tid, {"tune": act["tune"]})
    elif act.get("later"):
        l = act["later"]
        when = clock.local_dt(l["start"]).strftime("%I:%M %p").lstrip("0")
        say = f"{l['title']} is on channel {l['num']} ({l['name']}) at {when}."
    elif act.get("jukebox"):
        pc = env("PARTY_CHANNEL", "0").strip()
        if pc in ("", "0"):
            return {"ok": True, "heard": heard, "say": "The jukebox is off."}
        r = party.DLR.search(act["jukebox"])
        hit = (r.get("results") or [None])[0] if r.get("ok") else None
        if not hit:
            return {"ok": True, "heard": heard, "say": f"Couldn't find {act['jukebox']} on YouTube."}
        added = party.add({"url": "https://youtu.be/" + hit["id"], "title": hit["title"], "by": hit.get("by", "")})
        if not added.get("ok"):
            return {"ok": True, "heard": heard, "say": added.get("message", "Couldn't add it.")}
        if tv["ch"] != pc and any(c[0] == pc for c in chans):
            remote._push(tid, {"tune": pc})
        say = f"Added “{hit['title']}” to the jukebox."
    return {"ok": True, "heard": heard, "say": say}


def _score_bug_games():
    out = []
    for t in sports.sports_data(TEAMS).get("teams", []):
        g, me = t.get("live"), (t.get("team") or {}).get("id")
        if not g or not g.get("home") or not g.get("away"):
            continue
        side = "home" if g["home"].get("id") == me else "away"
        out.append({"id": g.get("id"), "sport": t.get("sport"), "kind": t.get("kind"), "mine": side, "detail": g.get("detail") or "",
                    "away": {k: g["away"].get(k) for k in ("abbr", "score", "color", "alt")},
                    "home": {k: g["home"].get(k) for k in ("abbr", "score", "color", "alt")}})
    return out


def score_bug():
    """The score bug's data: your teams' games that are on right now, and how you want the bug to behave."""
    mode = (env("SCORE_BUG", "off") or "off").lower()
    out = {"ok": True, "mode": mode if mode in ("scores", "cycle", "always") else "off",
           "on": max(1, int(float(env("SCORE_BUG_ON", "5") or 5))), "off": max(1, int(float(env("SCORE_BUG_OFF", "10") or 10))), "games": []}
    if out["mode"] == "off" or not os.path.exists(TEAMS):
        return out
    try:
        out["games"] = cached("scorebug", 8, _score_bug_games)
    except Exception:
        pass
    return out


WEB_BLURBS = {"weather": "Local forecast, radar and headlines", "sports": "Live scores for your teams", "party": "Music videos from your phones",
              "trivia": "Party games on your phones", "wrapped": "Your year in TV", "livecam": "Live from around the house",
              "duck": "Light-gun game", "flick": "Darts, hoops, bowling, cup pong", "stream": "Live streams from a link"}


def on_now(tid):
    """The phone remote's What's on list: what's playing on each of this TV's channels, and what's next."""
    tid = remote._clean_id(tid)
    tv = next((t for t in remote.tvs() if t["id"] == tid), None)
    if not tv:
        return {"ok": False, "message": "That TV isn't on."}
    try:
        programs = cached("tv", 120, tv_guide).get("programs", {}) if ETV_URL else {}
    except Exception:
        programs = {}
    web = {v: k for k, v in builtin_channels().items() if v and v != "0"}
    now, out = time.time(), {}
    for num, name in tv["list"]:
        if num in tv["hidden"]:
            continue
        if num in web:
            note = WEB_BLURBS.get(web[num], "")
            if web[num] == "stream" and stream.S.get("title"):
                note = stream.S["title"]
            out[num] = {"now": {"t": note}, "web": True}
            continue
        lst = programs.get(num) or []
        cur = next((p for p in lst if p["s"] <= now < p["e"]), None)
        nxt = next((p for p in lst if p["s"] >= (cur["e"] if cur else now) - 1), None)
        out[num] = {"now": {"t": cur["t"], "st": cur.get("st", ""), "s": cur["s"], "e": cur["e"]} if cur else None,
                    "next": {"t": nxt["t"], "s": nxt["s"]} if nxt else None}
    return {"ok": True, "now": now, "channels": out}


def etv_where(auto_only=False):
    """Where ErsatzTV runs: "nas" (this same machine), "windows" or "other" (another computer).
    That decides how the break clips get to it. ERSATZTV_HOST in settings.txt overrides the guess."""
    if not auto_only:
        w = env("ERSATZTV_HOST").lower()
        if w in ("nas", "windows", "other"):
            return w
    host = urllib.parse.urlparse(env("ERSATZTV_URL")).hostname or ""
    if not host:
        return ""
    if host in ("localhost", "127.0.0.1", "::1", "host.docker.internal") or host == lan_ip():
        return "nas"
    return "windows"


# ------------------------------------------------------------------ ErsatzTV rescans
# ErsatzTV only notices that the break clips changed when it scans its library. Until then it can
# try to play a clip version it remembers and say the media is unavailable. So whenever the clips
# change (made here, or copied to your ErsatzTV computer), KNAS asks ErsatzTV to rescan just that
# library. Needs ERSATZTV_CLIPS_LIBRARY: the library's number in ErsatzTV.
_scan = {"timer": None, "last": None}


def etv_scan_now(lib=None, url=None, key=None):
    lib = (lib or env("ERSATZTV_CLIPS_LIBRARY")).strip()
    key = (key or env("ERSATZTV_API_KEY")).strip()
    url = (url or ETV_URL).strip().rstrip("/")
    if not (url and lib.isdigit()):
        return {"ok": False, "message": "set the ErsatzTV address and the clips library number first"}
    headers = {"Content-Type": "application/json", "User-Agent": "KNAS"}
    if key:
        headers["X-Etv-Api-Key"] = key        # newer ErsatzTV versions need their API key on every API call
    req = urllib.request.Request(f"{url}/api/libraries/{lib}/scan", data=b"{}", method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            r.read()
        res = {"ok": True, "message": f"ErsatzTV is rescanning library {lib}"}
    except urllib.error.HTTPError as e:
        res = {"ok": False, "message": {404: f"ErsatzTV has no library number {lib}",
                                        401: "ErsatzTV wants its API key" + (" and didn't accept this one" if key else ". Paste it into ErsatzTV API key below"),
                                        403: "ErsatzTV didn't accept the API key"}.get(
                                            e.code, f"ErsatzTV answered with error {e.code}. It may be too old for this; update ErsatzTV")}
    except Exception as e:
        res = {"ok": False, "message": f"couldn't reach ErsatzTV ({e})"}
    _scan["last"] = dict(res, time=int(time.time()))
    clips.log("ErsatzTV rescan: " + res["message"])
    return res


def etv_scan_soon(delay=20):
    """Rescan once things settle (several clips can change within a minute)."""
    if not (ETV_URL and env("ERSATZTV_CLIPS_LIBRARY")):
        return
    if _scan["timer"]:
        _scan["timer"].cancel()
    _scan["timer"] = threading.Timer(delay, etv_scan_now)
    _scan["timer"].daemon = True
    _scan["timer"].start()


def get_json(url, headers=None, timeout=8):
    req = urllib.request.Request(url, headers={"User-Agent": "knas42/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


_cache, _lock = {}, threading.Lock()


_refreshing = set()
_failed = {}                       # key -> (when, error): a source that's down isn't asked again for a minute


def cached(key, ttl, fn):
    """The last good value for `key`, made by fn() at most every `ttl` seconds.
    Once there's a value it's never waited on again: when it's out of date, the old one is handed back straight
    away and a fresh one is fetched in the background (so the weather channel never sits on a blank screen
    while KNAS asks the weather, news and radar sites for new data)."""
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < ttl:
            return hit[1]
        if hit:
            if key not in _refreshing:
                _refreshing.add(key)
                threading.Thread(target=_refresh, args=(key, fn), daemon=True, name="refresh-" + key).start()
            return hit[1]
        bad = _failed.get(key)
        if bad and now - bad[0] < 60:
            raise bad[1]
    try:
        val = fn()                  # nothing yet (just started): this first time has to wait
    except Exception as e:
        with _lock:
            _failed[key] = (time.time(), e)
        raise
    with _lock:
        _cache[key] = (time.time(), val)
        _failed.pop(key, None)
    return val


def _refresh(key, fn):
    try:
        val = fn()
        with _lock:
            _cache[key] = (time.time(), val)
    except Exception as e:          # keep serving the last good value if a source hiccups
        print(f"[{key}] couldn't refresh: {e}", flush=True)
    finally:
        with _lock:
            _refreshing.discard(key)


def warm_weather_channel():
    """Fetch the weather channel's data when KNAS starts and keep it fresh, so the channel shows up instantly."""
    time.sleep(3)
    while True:
        try:
            everything()
        except Exception:
            pass
        time.sleep(240)


def weather():
    q = urllib.parse.urlencode({
        "latitude": LAT, "longitude": LON, "timezone": TZ, "forecast_days": 7,
        "temperature_unit": "celsius" if METRIC else "fahrenheit", "wind_speed_unit": "kmh" if METRIC else "mph",
        "precipitation_unit": "mm" if METRIC else "inch",
        "current": "temperature_2m,relative_humidity_2m,dew_point_2m,apparent_temperature,weather_code,"
                   "wind_speed_10m,wind_direction_10m,pressure_msl,surface_pressure,visibility,is_day",
        "hourly": "temperature_2m,weather_code,precipitation_probability,is_day",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                 "wind_speed_10m_max,sunrise,sunset",
    })
    j = get_json(OPEN_METEO + "?" + q)
    if isinstance(j, dict) and j.get("utc_offset_seconds") is not None:
        os.environ["KNAS_UTC_OFFSET"] = str(j["utc_offset_seconds"])   # your local time, for clips and holidays
    return j


def spotify():
    if not SPOTIFY_URL:
        return None
    out = {}
    for key, path in (("now", SPOTIFY_NOW), ("top", SPOTIFY_TOP)):
        try:
            out[key] = get_json(SPOTIFY_URL + path, SPOTIFY_HEADERS)
        except Exception as e:
            out[key] = None
            out[key + "_error"] = str(e)
    return out


def kuma():
    if not KUMA_URL:
        return None
    page = get_json(f"{KUMA_URL}/api/status-page/{KUMA_SLUG}")
    beats = get_json(f"{KUMA_URL}/api/status-page/heartbeat/{KUMA_SLUG}")
    hb, up = beats.get("heartbeatList", {}), beats.get("uptimeList", {})
    monitors = []
    for group in page.get("publicGroupList", []):
        for m in group.get("monitorList", []):
            last = (hb.get(str(m["id"])) or [{}])[-1]
            monitors.append({
                "name": m.get("name"),
                "status": last.get("status"),  # 1 up, 0 down, 2 pending, 3 maintenance
                "ping": last.get("ping"),
                "uptime": up.get(f"{m['id']}_24"),
            })
    return monitors


def _clean(t):
    t = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", t, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", "", t)).strip()
    t = re.sub(r"^(WATCH|VIDEO|LIVE|PHOTOS|UPDATE|LISTEN)\s*[:|-]\s*", "", t, flags=re.I)
    return re.sub(r"\s+", " ", t)


FEED_FOUND = {}          # website address -> the RSS feed found on it
FEED_TRY = ["/feed/", "/rss/", "/feed", "/rss", "/rss.xml", "/feed.xml", "/index.xml", "/atom.xml", "/news/feed/", "/feeds/posts/default"]


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KNAS42 news ticker)", "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, text/html;q=0.8, */*;q=0.5"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.geturl(), r.read(600000).decode("utf-8", "replace")


def _is_feed(text):
    head = text[:3000].lower()
    return ("<rss" in head or "<feed" in head or "<rdf:rdf" in head) and ("<item" in text.lower() or "<entry" in text.lower())


def _newest(text):
    """Date of the newest story in a feed (None if it doesn't say)."""
    import email.utils
    best = None
    for raw in re.findall(r"<(?:pubDate|updated|published|dc:date)[^>]*>(.*?)</", text, re.S)[:40]:
        raw = _clean(raw)
        d = None
        try:
            d = email.utils.parsedate_to_datetime(raw)
        except (TypeError, ValueError, IndexError):
            try:
                d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                d = None
        if d is not None:
            if d.tzinfo is None:
                d = d.replace(tzinfo=timezone.utc)
            best = d if best is None or d > best else best
    return best


def _fresh(text, days=21):
    d = _newest(text)
    return d is None or (datetime.now(timezone.utc) - d).days <= days


def news_hours():
    """Only headlines from the last NEWS_MAX_HOURS hours (default 6), so the news is always current."""
    try:
        return max(1, min(72, int(float(env("NEWS_MAX_HOURS", "6") or 6))))
    except ValueError:
        return 6


def _item_time(block):
    """When a feed item was published (None if it doesn't say)."""
    import email.utils
    m = re.search(r"<(?:pubDate|published|updated|dc:date)[^>]*>(.*?)</", block, re.S)
    if not m:
        return None
    raw = _clean(m.group(1))
    try:
        d = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d is None:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def google_news(query):
    """Google News headlines for a site or a search. Always up to date, no feed needed."""
    q = urllib.parse.urlencode({"q": f"{query} when:{news_hours()}h", "hl": "en-US", "gl": "US", "ceid": "US:en"})
    return "https://news.google.com/rss/search?" + q


def find_feed(url):
    """Works with an RSS feed, a normal website address, or just words to search for.
    - RSS feed: used as is (unless it's gone stale)
    - Website: uses the feed the site points to, else the usual feed addresses, else that site's
      headlines from Google News
    - Words (e.g. "Springfield Missouri"): the latest Google News headlines for them"""
    url = url.strip()
    if url in FEED_FOUND:
        return FEED_FOUND[url]
    if not re.match(r"^https?://", url) and not re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", url, re.I):
        g = google_news(url)                  # plain words: search the news
        FEED_FOUND[url] = (g, None)
        return g, None
    if not re.match(r"^https?://", url):
        url = "https://" + url
    stale = None
    try:
        final, text = _fetch(url)
    except Exception:
        final, text = url, ""
    if text and _is_feed(text):
        if _fresh(text):
            return url, text
        stale = url
    cands = []
    for tag in re.findall(r"<link\b[^>]*>", text, re.I):
        if re.search(r"rel=[\"']?alternate", tag, re.I) and re.search(r"(rss|atom)\+xml", tag, re.I):
            h = re.search(r"href=[\"']([^\"']+)", tag, re.I)
            if h:
                cands.append(urllib.parse.urljoin(final, html.unescape(h.group(1))))
    for a in re.findall(r"<a\b[^>]*href=[\"']([^\"']*(?:rss|feed)[^\"']*)[\"']", text, re.I)[:8]:
        cands.append(urllib.parse.urljoin(final, html.unescape(a)))
    base = re.match(r"^(https?://[^/]+)", final).group(1)
    path = urllib.parse.urlparse(final).path.rstrip("/")
    if not stale:
        for t in FEED_TRY:
            if path:
                cands.append(base + path + t)
            cands.append(base + t)
    seen = set()
    for c in cands:
        if c in seen or c.startswith("mailto:") or c == stale:
            continue
        seen.add(c)
        try:
            f_url, f_text = _fetch(c)
            if _is_feed(f_text) and _fresh(f_text):
                FEED_FOUND[url] = (f_url, None)
                print(f"News: found the feed for {url} -> {f_url}", flush=True)
                return f_url, f_text
        except Exception:
            pass
    # no (fresh) feed: that site's latest headlines from Google News
    host = urllib.parse.urlparse(final if text else url).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    g = google_news(f"site:{host}")
    try:
        _, g_text = _fetch(g)
        if _is_feed(g_text) and re.search(r"<item[\s>]", g_text):
            FEED_FOUND[url] = (g, None)
            print(f"News: no {'up-to-date ' if stale else ''}feed at {url}, using Google News for {host}", flush=True)
            return g, g_text
    except Exception:
        pass
    raise RuntimeError(f"couldn't find headlines for {url}. Try the site's RSS feed, or type a few words to search the news instead.")


def read_feed(url, limit=10, _retry=True):
    f_url, xml = find_feed(url)
    if xml is None:
        _, xml = _fetch(f_url)
    gnews = "news.google.com" in f_url
    m = re.search(r"<channel>.*?<title>(.*?)</title>", xml, re.S) or re.search(r"<feed[^>]*>.*?<title[^>]*>(.*?)</title>", xml, re.S)
    source = _clean(m.group(1)) if m else ""
    source = re.sub(r"^NPR Topics:.*", "NPR", source)
    blocks = re.findall(r"<item[\s>].*?</item>", xml, re.S) or re.findall(r"<entry[\s>].*?</entry>", xml, re.S)
    out, names = [], []
    cutoff = datetime.now(timezone.utc) - timedelta(hours=news_hours())
    for b in blocks:
        when = _item_time(b)
        if when is not None and when < cutoff:
            continue                           # older than NEWS_MAX_HOURS: skip it
        t = re.search(r"<title[^>]*>(.*?)</title>", b, re.S)
        title = _clean(t.group(1)) if t else ""
        if gnews:                              # Google News titles end in " - Source Name"
            sm = re.search(r"<source[^>]*>(.*?)</source>", b, re.S)
            src = _clean(sm.group(1)) if sm else ""
            if src and title.endswith(" - " + src):
                title = title[: -len(src) - 3].strip()
            elif " - " in title:
                title, src2 = title.rsplit(" - ", 1)
                src = src or src2
            if src and src not in names:
                names.append(src)
        if title and title not in out:
            out.append(title)
        if len(out) >= limit:
            break
    if gnews:
        source = " / ".join(names[:2]) if names else "Google News"
    if not out and not gnews and _retry and blocks:
        # the site's own feed has nothing from the last few hours: get its newest stories from Google News
        host = urllib.parse.urlparse(url if "://" in url else "https://" + url).netloc.replace("www.", "")
        if host:
            try:
                g = read_feed(google_news("site:" + host), limit, _retry=False)
                if g["headlines"]:
                    return dict(g, source=source or g["source"])
            except Exception:
                pass
    return {"source": source, "headlines": out, "feed": f_url}


def news_group(urls):
    items, sources, errors = [], [], []
    for u in urls:
        try:
            f = read_feed(u)
            items += f["headlines"]
            if f["source"]:
                sources.append(f["source"])
        except Exception as e:
            errors.append(f"{u}: {e}")
    if not items and errors:
        raise RuntimeError("; ".join(errors))
    return {"sources": sources, "headlines": items[:12]}


def news():
    out = {}
    for key, urls in (("local", LOCAL_NEWS), ("us", US_NEWS)):
        try:
            out[key] = news_group(urls) if urls else None
        except Exception as e:
            out[key] = None
            out[key + "_error"] = str(e)
    return out



# ------------------------------------------------------------------ radar + precipitation outlook
RADAR_API = env("RADAR_API", "https://api.rainviewer.com/public/weather-maps.json")
RADAR_COLOR = env("RADAR_COLOR", "2")          # RainViewer free tier only offers scheme 2 (Universal Blue)
CITY_CACHE = os.path.join(DATA, "cities-cache.json")


def nearby_cities():
    """Towns to label on the radar maps: MAP_CITIES in settings.txt, or the biggest nearby towns from OpenStreetMap."""
    custom = env("MAP_CITIES")
    if custom:                       # Name, lat, lon; Name, lat, lon
        out = []
        for part in custom.split(";"):
            bits = [b.strip() for b in part.split(",")]
            if len(bits) == 3:
                try:
                    out.append([bits[0], float(bits[1]), float(bits[2])])
                except ValueError:
                    pass
        CONFIG["cities"] = out
        return
    key = f"{float(LAT):.2f},{float(LON):.2f}"
    try:
        with open(CITY_CACHE, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("key") == key and c.get("cities"):
            CONFIG["cities"] = c["cities"]
            return
    except (OSError, ValueError):
        pass
    q = f'[out:json][timeout:25];node["place"~"^(city|town)$"](around:190000,{LAT},{LON});out tags center;'
    for attempt in range(3):
        try:
            req = urllib.request.Request("https://overpass-api.de/api/interpreter", data=urllib.parse.urlencode({"data": q}).encode(),
                                         headers={"User-Agent": "knas42/1.0"})
            with urllib.request.urlopen(req, timeout=40) as r:
                els = json.loads(r.read().decode()).get("elements") or []
            def pop(e):
                try:
                    return int(re.sub(r"[^0-9]", "", e.get("tags", {}).get("population", "0")) or 0)
                except ValueError:
                    return 0
            els.sort(key=pop, reverse=True)
            cities = [[e["tags"].get("name:en") or e["tags"].get("name"), e["lat"], e["lon"]] for e in els[:30] if e.get("tags", {}).get("name")]
            CONFIG["cities"] = cities
            with open(CITY_CACHE, "w", encoding="utf-8") as f:
                json.dump({"key": key, "cities": cities}, f)
            print(f"Map towns: {', '.join(c[0] for c in cities[:10])}...", flush=True)
            return
        except Exception as e:
            print(f"Map towns lookup failed ({e}); retrying", flush=True)
            time.sleep(30)


MAP_SPAN = (2.3, 4.8)  # degrees of latitude / longitude the outlook grid covers


def radar():
    j = get_json(RADAR_API)
    frames = [{"time": f.get("time"), "path": f.get("path")} for f in (j.get("radar") or {}).get("past") or [] if f.get("path")]
    return {"host": j.get("host", "https://tilecache.rainviewer.com"), "frames": frames[-8:], "color": RADAR_COLOR}


def outlook():
    lat0, lon0 = float(LAT), float(LON)
    rows, cols = 7, 10
    lats, lons = [], []
    for r in range(rows):
        for c in range(cols):
            lats.append(round(lat0 + MAP_SPAN[0] / 2 - r * MAP_SPAN[0] / (rows - 1), 3))
            lons.append(round(lon0 - MAP_SPAN[1] / 2 + c * MAP_SPAN[1] / (cols - 1), 3))
    q = urllib.parse.urlencode({"latitude": ",".join(map(str, lats)), "longitude": ",".join(map(str, lons)),
                                "hourly": "precipitation_probability,precipitation", "forecast_hours": 12,
                                "precipitation_unit": "inch", "timezone": TZ})
    data = get_json(f"{OPEN_METEO}?{q}", timeout=20)
    pts = data if isinstance(data, list) else [data]
    times = (pts[0].get("hourly") or {}).get("time", []) if pts else []
    grid = []
    for p in pts:
        h = p.get("hourly") or {}
        grid.append({"lat": p.get("latitude"), "lon": p.get("longitude"),
                     "prob": h.get("precipitation_probability") or [], "amt": h.get("precipitation") or []})
    return {"rows": rows, "cols": cols, "times": times, "points": grid,
            "lat": [lats[0], lats[-1]], "lon": [lons[0], lons[-1]]}



# ------------------------------------------------------------------ break channel
def _lines(path):
    try:
        with open(path, encoding="utf-8") as f:
            return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]
    except OSError:
        return []


def trivia():
    out = []
    for l in _lines(TRIVIA):
        p = [x.strip() for x in l.split("|")]
        if len(p) >= 3 and p[0] and p[1]:
            out.append({"q": p[0], "a": p[1], "wrong": [w for w in p[2:5] if w]})
    return out


def trivia_pool(topics):
    """Questions for the trivia game: Open Trivia Database topics (what KNAS already keeps, or fetched now)
    and "mine" = your own trivia list and trivia links."""
    out, fetched = [], 0
    for t in topics:
        if t == "mine":
            out += trivia()
            with facts._lock:
                for k, v in facts._cache.items():
                    if k.startswith("trivia:") and not k.startswith("trivia:@otdb:"):
                        out += v.get("items") or []
            continue
        if t not in facts.TRIVIA_TOPICS:
            continue
        with facts._lock:
            have = list((facts._cache.get("trivia:@otdb:" + t) or {}).get("items") or [])
        if len(have) < 30:
            try:
                if fetched:
                    time.sleep(5.5)                    # the Open Trivia Database allows one request per 5 seconds
                have += facts.opentdb(t)
                fetched += 1
            except Exception as e:
                print(f"[trivia] {t}: {e}", flush=True)
        out += have
    return out


def on_this_day():
    d = clock.local_now()
    for url in (f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/selected/{d.month:02d}/{d.day:02d}",
                f"https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/selected/{d.month:02d}/{d.day:02d}"):
        try:
            j = get_json(url, {"User-Agent": facts.UA, "Api-User-Agent": facts.UA}, timeout=15)
            items = [{"year": e.get("year"), "text": e.get("text", "")} for e in (j.get("selected") or []) if e.get("text")]
            if items:
                return items[:30]
        except Exception:
            continue
    return []


def coming_up():
    """Shows starting next on the ErsatzTV channels (the next :00 / :30 change-over)."""
    if not ETV_URL:
        return []
    try:
        g = cached("tv", 120, tv_guide)
    except Exception:
        return []
    now, starts = time.time(), []
    for ch in g["channels"]:
        for p in g["programs"].get(ch["number"], []):
            if now - 60 < p["s"] <= now + 45 * 60:
                starts.append((p["s"], ch, p))
                break
    if not starts:
        return []
    first = min(s for s, _, _ in starts)
    return [{"time": s, "number": ch["number"], "name": ch["name"], "title": p["t"], "sub": p.get("st", ""), "ep": p.get("ep", "")}
            for s, ch, p in sorted(starts, key=lambda x: (x[0], float(x[1]["number"]) if x[1]["number"].replace(".", "").isdigit() else 999))
            if s - first < 15 * 60][:6]


def break_data():
    try:
        vids = sorted(f for f in os.listdir(VIDEOS) if f.lower().endswith(VIDEO_EXT))
    except OSError:
        vids = []
    out = {"config": CONFIG, "trivia": facts.all_trivia(trivia()), "facts": facts.all_facts(_lines(FACTS)), "videos": vids, "onthisday": [], "comingup": []}
    try:
        out["onthisday"] = cached("onthisday-" + clock.local_now().strftime("%m%d"), 6 * 3600, on_this_day)
    except Exception:
        pass
    out["comingup"] = coming_up()
    try:                                       # the latest headlines, for the break screen's ticker
        n = cached("news", 900, news)
        heads = []
        for key in ("local", "us"):
            g = n.get(key) or {}
            heads += [h for h in (g.get("headlines") or [])[:4]]
        out["news"] = heads[:8]
    except Exception:
        out["news"] = []
    return out


def everything():
    out, errors = {"config": CONFIG}, {}

    def get(key, ttl, fn):
        try:
            out[key] = cached(key, ttl, fn)
        except Exception as e:
            out[key] = None
            errors[key] = str(e)
    # all at once, so the slowest source sets the wait (only the very first time; after that it's instant)
    jobs = [threading.Thread(target=get, args=a, daemon=True) for a in
            (("weather", 600, weather), ("spotify", 15, spotify), ("kuma", 30, kuma), ("news", 900, news), ("radar", 300, radar), ("outlook", 1800, outlook))]
    for j in jobs:
        j.start()
    for j in jobs:
        j.join(25)
    for key in ("weather", "spotify", "kuma", "news", "radar", "outlook"):
        out.setdefault(key, None)
    out["errors"] = dict(errors)
    return out


# ------------------------------------------------------------------ cable box (ErsatzTV)
def _art_path(url):
    """Artwork for the guide: ErsatzTV's own images go through this server (so a TV box can load them even
    when ErsatzTV is on another computer). Other web images are kept; ones only reachable on 'localhost' are dropped."""
    if not url:
        return ""
    p = urllib.parse.urlparse(url)
    if p.scheme in ("http", "https") and p.path.startswith("/iptv/"):
        return _local_path(url)
    if p.scheme in ("http", "https") and p.hostname not in ("localhost", "127.0.0.1", "::1"):
        return url
    return ""


def _local_path(url):
    """http://anything/iptv/... -> /iptv/... so the browser fetches through this server."""
    if not url:
        return url
    p = urllib.parse.urlparse(url)
    if p.scheme in ("http", "https") and p.path.startswith("/iptv/"):
        return p.path + (("?" + p.query) if p.query else "")
    return url


def _xmltv_time(s):
    s = s.strip()
    dt = datetime.strptime(s[:14], "%Y%m%d%H%M%S")
    m = re.search(r"([+-])(\d{2})(\d{2})$", s)
    off = timedelta(hours=int(m.group(2)), minutes=int(m.group(3))) if m else timedelta(0)
    if m and m.group(1) == "-":
        off = -off
    return (dt.replace(tzinfo=timezone(off))).timestamp()


def _etv_get(path, timeout=20):
    req = urllib.request.Request(ETV_URL + path, headers={"User-Agent": "knas42-cablebox"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def tv_guide():
    channels, by_id = [], {}
    m3u = _etv_get("/iptv/channels.m3u")
    lines = [l.strip() for l in m3u.splitlines()]
    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF"):
            continue
        attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', line))
        name = line.rsplit(",", 1)[-1].strip() if "," in line else attrs.get("tvg-name", "")
        url = next((l for l in lines[i + 1:] if l and not l.startswith("#")), "")
        number = attrs.get("tvg-chno") or attrs.get("channel-number") or ""
        if not number:
            m = re.search(r"/channel/([\d.]+)\.", url)
            number = m.group(1) if m else ""
        if not number:
            continue
        ch = {"number": number, "name": name or attrs.get("tvg-name") or f"Channel {number}",
              "logo": _local_path(attrs.get("tvg-logo", "")), "id": attrs.get("tvg-id", "")}
        channels.append(ch)
        for key in (ch["id"], attrs.get("channel-id", ""), number):
            if key:
                by_id[key] = number
    programs = {c["number"]: [] for c in channels}
    now = time.time()
    try:
        root = ET.fromstring(_etv_get("/iptv/xmltv.xml", timeout=40))
        names = {}
        for c in root.findall("channel"):
            dn = c.findtext("display-name") or ""
            names[c.get("id", "")] = dn
        for p in root.findall("programme"):
            cid = p.get("channel", "")
            num = by_id.get(cid)
            if num is None:  # match on display name or a leading number in the id
                dn = names.get(cid, "")
                num = next((c["number"] for c in channels if dn and c["name"] == dn), None)
                if num is None:
                    m = re.match(r"C?([\d.]+)", cid)
                    num = m.group(1) if m and m.group(1) in programs else None
            if num is None:
                continue
            try:
                start, stop = _xmltv_time(p.get("start", "")), _xmltv_time(p.get("stop", ""))
            except ValueError:
                continue
            if stop < now - 3 * 3600 or start > now + 12 * 3600:
                continue
            ep = ""
            for e in p.findall("episode-num"):
                if e.get("system") == "onscreen" and e.text:
                    ep = e.text.strip()
            img = ""
            for ic in p.findall("icon"):        # episode or show artwork, when ErsatzTV has it
                img = _art_path(ic.get("src", ""))
                if img:
                    break
            cats = ", ".join(dict.fromkeys((c.text or "").strip() for c in p.findall("category") if (c.text or "").strip()))[:120]
            rating = ""
            for rt in p.findall("rating"):      # TV-PG, TV-Y7, PG-13...
                rating = (rt.findtext("value") or "").strip()[:12]
                if rating:
                    break
            programs[num].append({"s": start, "e": stop, "t": (p.findtext("title") or "").strip(),
                                  "st": (p.findtext("sub-title") or "").strip(), "ep": ep,
                                  "d": (p.findtext("desc") or "").strip()[:400], "img": img, "c": cats, "r": rating})
        for lst in programs.values():
            lst.sort(key=lambda x: x["s"])
    except Exception as e:
        print("guide error:", e, flush=True)
    def numkey(c):
        try:
            return float(c["number"])
        except ValueError:
            return 1e9
    channels.sort(key=numkey)
    return {"channels": channels, "programs": programs}


def station_urls():
    urls = [sports.radio_setting(TEAMS).get("url", "")] + [t.get("radio", "") for t in sports.read_teams(TEAMS)]
    return [u for u in urls if u]


def sports_with_radio():
    d = sports.sports_data(TEAMS)
    radio.warm(station_urls())
    if d.get("radio"):
        d["radio"]["url"] = radio.relay_url(d["radio"].get("url", ""))
    for t in d.get("teams", []):
        t["radio"] = radio.relay_url(t.get("radio", ""))
    return d


def tv_data():
    try:
        radio.warm(station_urls())   # the cable box is open: tune the station in early
    except Exception:
        pass
    out = {"config": TV_CONFIG, "now": time.time(), "channels": [], "programs": {}, "error": None}
    if not ETV_URL:
        out["error"] = "ErsatzTV isn't set up (setup page, ErsatzTV). Showing the KNAS channels only."
        return out
    try:
        out.update(cached("tv", 120, tv_guide))
    except Exception as e:
        out["error"] = f"Can't reach ErsatzTV at {ETV_URL}: {e}"
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def log_message(self, *a):
        pass

    def end_headers(self):
        # Always serve fresh pages so updates show up without Ctrl+F5
        if self.path.split("?")[0].endswith((".html", "/", "/tv", "/sports")) or self.path.split("?")[0] in ("/tv", "/sports", "/"):
            self.send_header("Cache-Control", "no-store")
        elif self.path.startswith("/fonts/"):
            self.send_header("Cache-Control", "max-age=604800")
        super().end_headers()

    def serve_page(self, name, page):
        """Send a KNAS screen with your colors, names, logos and sound settings added.
        Before KNAS is set up, the screens send you to the setup page instead."""
        if not configured() and "cast=" not in self.path and "demo" not in self.path:
            self.send_response(302)
            self.send_header("Location", "/setup")
            self.send_header("Cache-Control", "no-store")
            super().end_headers()
            return
        try:
            with open(os.path.join(WEB, name), encoding="utf-8") as f:
                html_text = f.read()
        except OSError:
            return self.send_error(404)
        html_text = html_text.replace("</head>", looks.boot(page) + "\n</head>", 1)
        body = html_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_file_ranged(self, full, exts):
        """Serve a media file with seeking support (Range requests)."""
        if not full.lower().endswith(exts) or not os.path.isfile(full):
            return self.send_error(404)
        size = os.path.getsize(full)
        start, end = 0, size - 1
        rng = self.headers.get("Range", "")
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if m and (m.group(1) or m.group(2)):
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2)))
            end = min(end, size - 1)
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", self.guess_type(full))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        try:
            with open(full, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(65536, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def proxy_etv(self, head=False):
        """Pass /iptv/... requests through to ErsatzTV so the browser stays on one address."""
        if not ETV_URL:
            return self.send_error(503, "ERSATZTV_URL not set")
        base = urllib.parse.urlparse(ETV_URL)
        conn_cls = http.client.HTTPSConnection if base.scheme == "https" else http.client.HTTPConnection
        conn = conn_cls(base.hostname, base.port or (443 if base.scheme == "https" else 80), timeout=60)
        try:
            conn.request("HEAD" if head else "GET", self.path, headers={
                "Host": self.headers.get("Host", base.netloc), "User-Agent": "knas42-cablebox",
                "Accept": self.headers.get("Accept", "*/*")})
            r = conn.getresponse()
            ctype = r.getheader("Content-Type", "")
            is_playlist = "mpegurl" in ctype.lower() or self.path.split("?")[0].endswith(".m3u8")
            body = r.read() if (is_playlist and not head) else None
            if body is not None:
                text = body.decode("utf-8", "replace")
                text = re.sub(r"https?://[^/\s\"]+(/iptv/)", r"\1", text)
                body = text.encode()
            self.send_response(r.status)
            for h in ("Content-Type", "Cache-Control", "Accept-Ranges", "Content-Range"):
                v = r.getheader(h)
                if v:
                    self.send_header(h, v)
            loc = r.getheader("Location")
            if loc:
                self.send_header("Location", _local_path(loc))
            if body is not None:
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            length = r.getheader("Content-Length")
            if length:
                self.send_header("Content-Length", length)
            else:
                self.close_connection = True
            self.end_headers()
            if head:
                return
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                self.send_error(502, f"ErsatzTV: {e}")
            except Exception:
                pass
        finally:
            conn.close()

    def do_HEAD(self):
        if self.path.startswith("/iptv/"):
            return self.proxy_etv(head=True)
        return super().do_HEAD()

    # ---------- setup page ----------
    def host_ip(self):
        h = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]")
        if h and h not in ("localhost", "127.0.0.1", "::1"):
            return h
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("10.255.255.255", 1))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return "YOUR_NAS_IP"

    def send_download(self, name, text, ctype="text/plain"):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def setup_get(self, path, qs):
        q = lambda k: (qs.get(k) or [""])[0]
        if path == "/api/setup":
            cur = wizard.read_settings()
            return self.send_json({"settings": {k: cur.get(k) for k in wizard.KEYS}, "teams": wizard.read_teams(),
                                   "sports": [[k, v[1]] for k, v in sports.SPORTS.items()], "version": VERSION,
                                   "server": {"ip": self.host_ip(), "port": PORT}, "can_save": wizard.allowed(self.client_address[0]),
                                   "logos": looks.logos(), "presets": looks.PRESETS, "color_keys": looks.COLOR_KEYS, "season_now": looks.season_on(), "fonts": looks.font_list(),
                                   "trivia_topics": [[k, v[1]] for k, v in facts.TRIVIA_TOPICS.items()], "facts_status": facts.status(),
                                   "counts": {"facts": len(_lines(FACTS)), "trivia": len(trivia())},
                                   "etv_where_auto": etv_where(auto_only=True), "configured": configured(),
                                   "auto_location": ({"city": AUTO.get("city"), "region": AUTO.get("region"), "tz": AUTO.get("tz"),
                                                      "metric": METRIC} if AUTO and not env("CITY_NAME") else None)})
        try:
            if path == "/api/setup/geocode":
                return self.send_json(wizard.geocode(q("q")))
            if path == "/api/setup/teams":
                return self.send_json(wizard.team_search(q("sport"), q("q")))
            if path == "/api/setup/test-jellyfin":
                return self.send_json(mediaserver.test(q("url"), q("key")))
            if path == "/api/setup/jellyfin-status":
                return self.send_json(mediaserver.status())
            if path == "/api/setup/test-etv":
                return self.send_json(wizard.test_ersatztv(q("url")))
            if path == "/api/setup/test-scan":
                return self.send_json(etv_scan_now(q("lib"), q("url"), q("key")))
            if path == "/api/setup/test-facts":
                return self.send_json(facts.check(q("kind"), q("src")))
            if path in ("/api/setup/file/facts", "/api/setup/file/trivia"):
                f = FACTS if path.endswith("facts") else TRIVIA
                try:
                    with open(f, encoding="utf-8", errors="replace") as fh:
                        return self.send_json({"ok": True, "text": fh.read()})
                except OSError:
                    return self.send_json({"ok": True, "text": ""})
            if path == "/api/setup/test-feed":
                try:
                    f = read_feed(q("url"), limit=3)
                    return self.send_json({"ok": True, "feed": f["feed"], "source": f["source"], "headlines": f["headlines"]})
                except Exception as e:
                    return self.send_json({"ok": False, "message": str(e)})
        except Exception as e:
            return self.send_json({"error": str(e)}, 502)
        ip = self.host_ip()
        if path == "/api/setup/download/weather.yml":
            return self.send_download("KNAS 42 Weather.yml", wizard.weather_yml(ip))
        if path == "/api/setup/download/clip-sync.sh":
            return self.send_download("knas-clip-sync.sh", wizard.clip_sync_sh(f"http://{ip}:{PORT}"))
        # Windows helpers, with this server's address filled in. The .bat is the only one people
        # download by hand; it fetches the installer, which fetches the copier (which keeps itself up to date).
        for key, fname in (("clip-sync.ps1", "knas-clip-sync.ps1"), ("clip-install.ps1", "knas-clip-install.ps1"),
                           ("get-clips.bat", "Get KNAS Break Clips.bat")):
            if path == "/api/setup/download/" + key:
                return self.send_download(fname, wizard.windows_file(fname, f"http://{ip}:{PORT}"))
        for key, fname in (("restart-ersatztv.bat", "Restart ErsatzTV.bat"),):
            if path == "/api/setup/download/" + key:
                with open(os.path.join(ROOT, "extras", "windows", fname), encoding="utf-8", errors="replace") as f:
                    return self.send_download(fname, f.read())
        return self.send_error(404)

    # ---------- Tools page: commercial breaks for your episodes (home network / Tailscale only) ----------
    def tools_get(self, path, qs):
        q = lambda k: (qs.get(k) or [""])[0]
        if not wizard.allowed(self.client_address[0]):
            return self.send_json({"ok": False, "message": "The Tools page only works from your home network."}, 403)
        try:
            if path == "/api/tools/status":
                return self.send_json(tools.status())
            if path == "/api/tools/browse":
                return self.send_json(tools.browse(q("path")))
            if path == "/api/tools/states":
                b = tools.browse(q("path"))
                return self.send_json(tools.file_states([f["path"] for f in b["files"]]))
            if path == "/api/tools/open":
                return self.send_json(tools.open_episode(q("path")))
            if path == "/api/tools/backups":
                return self.send_json(tools.backups_info())
            if path == "/api/tools/batch":
                return self.send_json(tools.batch_status(full=bool(q("full"))))
            if path == "/api/tools/batch/report":
                return self.send_download("KNAS breaks report.txt", tools.batch_report_text())
            if path == "/api/tools/job":
                return self.send_json(tools.job(q("id")) or {"state": "gone"})
            if path == "/api/tools/preview":
                f = tools.preview_file(q("path"))
                if not f:
                    return self.send_error(404)
                return self.send_file_ranged(f, (".mp4", ".m4v", ".mov"))
            if path == "/api/tools/thumb":
                f = tools.thumb(q("path"), float(q("t") or 0), int(q("w") or 320))
                if not f:
                    return self.send_error(404)
                with open(f, "rb") as fh:
                    body = fh.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "max-age=3600")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
        except ValueError as e:
            return self.send_json({"ok": False, "message": str(e)}, 400)
        except Exception as e:
            return self.send_json({"ok": False, "message": f"Something went wrong: {e}"}, 500)
        return self.send_error(404)

    def tools_post(self, path):
        if not wizard.allowed(self.client_address[0]):
            return self.send_json({"ok": False, "message": "The Tools page only works from your home network."}, 403)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(min(n, 200000)).decode("utf-8") or "{}")
            if path == "/api/tools/save":
                breaks = [float(x) for x in (data.get("breaks") or [])][:60]
                return self.send_json({"ok": True, "job": tools._job_public(tools.save(data.get("path", ""), breaks, bool(data.get("backup"))))})
            if path == "/api/tools/automark":
                return self.send_json(tools.batch_start(data.get("path", ""), "check" if data.get("check") else "mark",
                                                        bool(data.get("redo")), bool(data.get("backup")), data.get("guess", True) is not False))
            if path == "/api/tools/cancel":
                return self.send_json(tools.cancel(str(data.get("id", ""))))
            if path == "/api/tools/restore":
                return self.send_json(tools.restore_original(str(data.get("path", ""))))
            if path == "/api/tools/backups/delete":
                return self.send_json(tools.delete_backups())
            if path == "/api/tools/plan":
                return self.send_json({"ok": True, "plan": tools.plan_set(data)})
            if path == "/api/tools/library/add":
                return self.send_json(tools.add_library(str(data.get("text", ""))))
            if path == "/api/tools/library/remove":
                return self.send_json(tools.remove_library(str(data.get("path", ""))))
            if path == "/api/tools/batch/apply":
                if "backup" in data:
                    tools.batch_set_backup(data["backup"])
                return self.send_json(tools.batch_apply())
            if path == "/api/tools/batch/stop":
                return self.send_json(tools.batch_stop())
            if path == "/api/tools/batch/resume":
                return self.send_json(tools.batch_resume())
            if path == "/api/tools/batch/clear":
                return self.send_json(tools.batch_clear())
        except ValueError as e:
            return self.send_json({"ok": False, "message": str(e)}, 400)
        except Exception as e:
            return self.send_json({"ok": False, "message": f"Something went wrong: {e}"}, 500)
        return self.send_error(404)

    # ---------- phone remote (home network / Tailscale only) ----------
    def remote_api(self, path, data=None, qs=None):
        if not wizard.allowed(self.client_address[0]):
            return self.send_json({"ok": False, "message": "The remote only works from your home network."}, 403)
        try:
            if path == "/api/remote/tvs":
                return self.send_json({"ok": True, "tvs": remote.tvs()})
            if path == "/api/remote/wait":
                return self.send_json({"ok": True, "cmds": remote.wait((qs.get("id") or [""])[0])})
            if path == "/api/remote/hello":
                d = data or {}
                prefs = remote.hello(d)
                if d.get("asleep") in (True, "1", "true"):      # turned off from the remote: not watching anything
                    history.off(d["id"])
                else:
                    history.record(d["id"], prefs.get("name") or str(d.get("guess") or "")[:40], str(d.get("ch") or "")[:12],
                                   str(d.get("chname") or "")[:60], str(d.get("show") or "")[:120])
                return self.send_json({"ok": True, "prefs": prefs})
            if path == "/api/remote/alloff" and data is not None:
                return self.send_json(remote.sleep_all())
            if path == "/api/remote/watching":
                return self.send_json({"ok": True, "watching": remote.watching((qs or {}).get("id", [""])[0])})
            if path == "/api/ratings":
                return self.send_json(dict(history.ratings(), station=env("STATION_NAME", "KNAS 42"), now=remote.watching("")))
            if path == "/api/scorebug":
                return self.send_json(score_bug())
            if path == "/api/remote/onnow":
                return self.send_json(on_now((qs or {}).get("id", [""])[0]))
            if path == "/api/remote/send":
                return self.send_json(remote.send(data or {}))
            if path == "/api/remote/prefs":
                return self.send_json(remote.set_prefs(data or {}))
            if path == "/api/remote/bye":
                out = remote.bye(data or {})
                history.off((data or {}).get("id"))
                return self.send_json(out)
            if path == "/api/history":
                days = int((qs or {}).get("days", ["7"])[0] or 7)
                tv = (qs or {}).get("tv", [""])[0]
                names = {t["id"]: t["name"] for t in remote.tvs()}
                return self.send_json(dict(history.summary(max(0, min(days, 400)), tv, names), ok=True,
                                           all_tvs=[{"id": k, "name": v} for k, v in names.items()]))
            if path == "/api/wrapped":
                try:
                    year = int((qs or {}).get("year", ["-1"])[0])
                except ValueError:
                    year = -1
                if year < 0:
                    year = clock.local_now().year
                names = {t["id"]: t["name"] for t in remote.tvs()}
                chans = {"weather": env("KNAS_CHANNEL", "42"), "sports": env("SPORTS_CHANNEL", "43"), "party": env("PARTY_CHANNEL", "0"),
                         "trivia": env("TRIVIA_CHANNEL", "0"), "wrapped": env("WRAPPED_CHANNEL", "0")}
                return self.send_json(dict(history.wrapped(year, (qs or {}).get("tv", [""])[0], names, chans),
                                           all_tvs=[{"id": k, "name": v} for k, v in names.items()],
                                           station=env("STATION_NAME", "KNAS 42")))
            if path == "/api/history/clear" and data is not None:
                return self.send_json(history.clear())
            if path == "/api/game/watch":       # the "Watch" button on a phone notification
                return self.send_json(gametime.watch_now())
            if path == "/api/game/test":
                return self.send_json(gametime.test(data or {}))
            if path == "/api/game/status":
                return self.send_json(gametime.status())
            if path == "/api/trivia/strokes":
                return self.send_json(game.strokes((qs or {}).get("from", ["0"])[0]))
            if path == "/api/trivia":
                return self.send_json(game.state((qs or {}).get("id", [""])[0][:40] if qs else ""))
            if path.startswith("/api/trivia/") and data is not None:
                act = {"join": game.join, "answer": game.answer, "leave": game.leave, "host": game.host,
                       "guess": game.guess_word, "bluff": game.bluff, "wheel": game.wheel, "pick": game.draw_pick,
                       "ink": game.draw_ops, "drawguess": game.draw_guess}.get(path[len("/api/trivia/"):])
                if act:
                    return self.send_json(act(data))
            if path == "/api/experimental":
                if data is None:
                    return self.send_json({"ok": True, "on": experimental()})
                if data.get("lock"):
                    set_experimental(False)
                    return self.send_json({"ok": True, "on": False})
                if try_code(data.get("code")):
                    set_experimental(True)
                    return self.send_json({"ok": True, "on": True})
                return self.send_json({"ok": True, "on": experimental(), "wrong": True})
            if path == "/api/alerts":
                return self.send_json(alerts.active())
            if path == "/api/alerts/test" and data is not None:
                return self.send_json(alerts.test())
            if path == "/api/alerts/status":
                return self.send_json(alerts.status())
            if path == "/api/party":
                base = f"http://{self.host_ip()}:{PORT}"
                out = dict(party.state(), remote=base + "/remote", join=base + "/j", experimental=experimental())
                wifi = env("JUKEBOX_WIFI_NAME").strip()
                if wifi:                                  # a "scan to join the Wi-Fi" code for guests
                    esc = lambda v: re.sub(r'([\\;,:"])', r"\\\1", v)
                    pw = env("JUKEBOX_WIFI_PASSWORD")
                    out["wifi"] = {"name": wifi, "qr": f"WIFI:T:{'WPA' if pw else 'nopass'};S:{esc(wifi)};" + (f"P:{esc(pw)};" if pw else "") + ";"}
                return self.send_json(out)
            if path == "/api/party/search":
                if env("PARTY_CHANNEL", "0").strip() in ("", "0"):
                    return self.send_json({"ok": False, "message": "The jukebox is off."})
                return self.send_json(party.DLR.search((qs or {}).get("q", [""])[0], karaoke=(qs or {}).get("karaoke", [""])[0] == "1"))
            if path.startswith("/api/party/") and data is not None:
                act = {"add": party.add, "ended": party.ended, "failed": party.failed, "skip": party.skip, "remove": party.remove,
                       "next": party.move_next, "options": party.options, "title": party.title}.get(path[len("/api/party/"):])
                if act:
                    return self.send_json(act(data))
            if path == "/api/remote/features":   # what the phone remote should show
                return self.send_json({"ok": True, "voice": voice.enabled(), "throw": throw.enabled(), "cam": livecam.enabled(),
                                       "duck": duck.enabled(), "fun": fun.enabled(), "flick": flick.enabled(), "stream": stream.enabled(), "history": history.enabled(), "secure": secure_base(self.host_ip())})
            if path == "/api/remote/voice" and data is not None:
                return self.send_json(voice_command(data))
            if path == "/api/secure":
                return self.send_json({"ok": True, "url": secure_base(self.host_ip()), "error": securecert.STATE["error"]})
            if path == "/api/throw":
                return self.send_json({"ok": True, "on": throw.enabled()})
            if path == "/api/throw/status":
                return self.send_json(throw.status((qs or {}).get("id", [""])[0]))
            if path == "/api/throw/show" and data is not None:
                return self.send_json(throw.show(data))
            if path == "/api/throw/clear" and data is not None:
                return self.send_json(throw.clear(data))
            if path == "/api/cam":
                return self.send_json({"ok": True, "on": livecam.enabled(), "channel": livecam.channel(), "cams": livecam.cams(),
                                       "secure": secure_base(self.host_ip()), "station": env("STATION_NAME", "KNAS 42")})
            if path == "/api/cam/tune" and data is not None:
                if not livecam.enabled():
                    return self.send_json({"ok": False, "message": "Live Cam is off."})
                on = [t["id"] for t in remote.tvs() if t["on"]]
                for t in on:
                    remote._push(t, {"tune": livecam.channel()})
                return self.send_json({"ok": True, "message": f"Showing it on {len(on)} TV{'s' if len(on) != 1 else ''}." if on else "No TVs are on right now."})
            if path == "/api/fx" and data is not None:      # Screen fun: splats, confetti, emojis, drawing
                return self.send_json(fun.send(data, self.client_address[0]))
            if path == "/api/stream":
                return self.send_json(stream.state())
            if path.startswith("/api/stream/") and data is not None:
                act = path[len("/api/stream/"):]
                if act == "tune":
                    n = stream.tune_all()
                    return self.send_json({"ok": bool(n), "message": f"Showing it on {n} TV{'s' if n != 1 else ''}." if n else "No TVs are on right now."})
                f = {"play": stream.play, "stop": stream.stop, "fav": stream.fav, "failed": stream.failed}.get(act)
                if f:
                    return self.send_json(f(data))
            if path == "/api/flick":
                return self.send_json(flick.status())
            if path == "/api/duck":
                return self.send_json(dict(duck.status(), secure=secure_base(self.host_ip())))
            if path == "/api/remote/forget":
                return self.send_json(remote.forget(data or {}))
        except ValueError as e:
            return self.send_json({"ok": False, "message": str(e)}, 400)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as e:                 # never leave a phone hanging: say what went wrong
            import traceback
            traceback.print_exc()
            return self.send_json({"ok": False, "message": f"Something went wrong on the NAS ({e.__class__.__name__}: {e})."}, 500)
        return self.send_error(404)

    def live_socket(self, path, qs):
        q = lambda k: (qs.get(k) or [""])[0]
        if not wizard.allowed(self.client_address[0]):
            return self.send_error(403)
        if path == "/api/cam/ws":
            if not livecam.enabled():
                return self.send_error(404)
            sock = ws.accept(self)
            if sock:
                livecam.run(sock, q("name"), q("facing"))
            return
        if path == "/api/flick/ws":
            if not flick.enabled():
                return self.send_error(404)
            sock = ws.accept(self)
            if sock:
                (flick.run_screen(sock) if q("role") == "screen" else flick.run_player(sock, q("name")))
            return
        if not duck.enabled():
            return self.send_error(404)
        sock = ws.accept(self)
        if not sock:
            return
        if q("role") == "screen":
            duck.run_screen(sock)
        else:
            duck.run_player(sock, q("name"), q("mode"))

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith(("/api/remote/", "/api/history", "/api/game/", "/api/party", "/api/alerts", "/api/trivia", "/api/wrapped", "/api/experimental",
                                             "/api/throw/", "/api/cam/", "/api/secure", "/api/fx", "/api/stream")):
            if path == "/api/throw/upload":      # a photo or video from Throw it to the TV (raw file, not JSON)
                if not wizard.allowed(self.client_address[0]):
                    return self.send_json({"ok": False, "message": "Home network only."}, 403)
                try:
                    return self.send_json(throw.upload(self, urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)))
                except ValueError as e:
                    self.close_connection = True
                    return self.send_json({"ok": False, "message": str(e)}, 400)
            try:
                n = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(min(n, 200000)).decode("utf-8") or "{}")
            except (ValueError, json.JSONDecodeError):
                return self.send_json({"ok": False}, 400)
            return self.remote_api(path, data=data)
        if path == "/api/clips/etv-key":     # the clip copier found ErsatzTV's API key on its computer
            if not wizard.allowed(self.client_address[0]):
                return self.send_json({"ok": False}, 403)
            try:
                n = int(self.headers.get("Content-Length") or 0)
                key = str(json.loads(self.rfile.read(min(n, 4000)).decode("utf-8") or "{}").get("key", ""))
            except (ValueError, json.JSONDecodeError):
                return self.send_json({"ok": False}, 400)
            good = wizard.check("ERSATZTV_API_KEY", key)
            if not good:
                return self.send_json({"ok": False, "message": "that doesn't look like an API key"}, 400)
            changed = good != env("ERSATZTV_API_KEY")
            if changed:                      # saving settings restarts KNAS with the key in place
                wizard.write_settings({"ERSATZTV_API_KEY": good})
                clips.log("got ErsatzTV's API key from the clip copier on " + self.client_address[0])
            return self.send_json({"ok": True, "changed": changed})
        if path == "/api/clips/copied":      # the clip copier on your ErsatzTV computer just got new clips
            if wizard.allowed(self.client_address[0]):
                etv_scan_soon()
            return self.send_json({"ok": True})
        if path.startswith("/api/tools/"):
            return self.tools_post(path)
        if path not in ("/api/setup", "/api/setup/logo", "/api/setup/clips-now", "/api/setup/file"):
            return self.send_error(404)
        if not wizard.allowed(self.client_address[0]):
            return self.send_json({"ok": False, "message": "Settings can only be changed from your home network."}, 403)
        if path == "/api/setup/file":        # the facts / trivia list editor on the setup page
            try:
                n = int(self.headers.get("Content-Length") or 0)
                data = json.loads(self.rfile.read(min(n, 2_000_000)).decode("utf-8") or "{}")
                kind = data.get("kind")
                if kind not in ("facts", "trivia"):
                    raise ValueError("unknown list")
                return self.send_json(wizard.write_list(FACTS if kind == "facts" else TRIVIA, kind, str(data.get("text", ""))))
            except Exception as e:
                return self.send_json({"ok": False, "message": str(e)}, 400)
        if path == "/api/setup/clips-now":   # "Make new clips now" on the setup page
            clips.NOW.set()
            return self.send_json({"ok": True})
        if path == "/api/setup/logo":     # upload or remove a logo picture
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > 5 * 1024 * 1024:
                    return self.send_json({"ok": False, "message": "That picture is too big (3 MB max)."}, 413)
                data = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
                kind = str(data.get("kind", ""))
                if data.get("remove"):
                    looks.remove_logo(kind)
                else:
                    import base64
                    raw = str(data.get("data", "")).split(",", 1)[-1]
                    looks.save_logo(kind, base64.b64decode(raw))
                return self.send_json({"ok": True, "logos": looks.logos()})
            except Exception as e:
                return self.send_json({"ok": False, "message": str(e)}, 400)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(min(n, 200000)).decode("utf-8") or "{}")
            if isinstance(data.get("teams"), list):
                wizard.write_teams(data["teams"])
            if isinstance(data.get("settings"), dict):
                wizard.write_settings(data["settings"])
            return self.send_json({"ok": True})
        except Exception as e:
            return self.send_json({"ok": False, "message": str(e)}, 500)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/api/cam/ws", "/api/duck/ws", "/api/flick/ws"):     # live connections (Live Cam, Duck Season)
            return self.live_socket(path, urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
        if getattr(self, "secure", False) and path in ("/", "/index.html"):
            # the secure address is for phones: its front page is the phone menu, not the weather channel
            self.send_response(302)
            self.send_header("Location", "/phone")
            self.end_headers()
            return
        pages = {"/throw": "/throw.html", "/cam": "/cam.html", "/zapper": "/zapper.html", "/z": "/zapper.html", "/phone": "/phone.html", "/fun": "/fun.html", "/flick": "/flickpad.html", "/streams": "/streams.html", "/ratings": "/ratings.html"}
        if path.rstrip("/") in pages:
            self.path = pages[path.rstrip("/")]
            return super().do_GET()
        if path.startswith("/throw-file/"):           # a photo or video someone threw to the TV
            if not wizard.allowed(self.client_address[0]):
                return self.send_error(403)
            f = throw.file_for(path[len("/throw-file/"):].split(".")[0])
            return self.send_file_ranged(f, (".jpg", ".png", ".gif", ".webp", ".mp4", ".mov", ".m4v", ".webm", ".3gp", ".mkv")) if f else self.send_error(404)
        if path.startswith("/streamfeed/"):              # the Stream channel's video, passed through the NAS
            if not wizard.allowed(self.client_address[0]):
                return self.send_error(403)
            return stream.serve(self, path, urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
        if path.startswith("/livecam/") and path.endswith(".mjpg"):   # a live phone camera
            if not wizard.allowed(self.client_address[0]):
                return self.send_error(403)
            return livecam.stream(self, path[len("/livecam/"):-5])
        if path in ("/setup", "/setup/"):
            self.path = "/setup.html"
            return super().do_GET()
        if path in ("/tools", "/tools/"):
            self.path = "/tools.html"
            return super().do_GET()
        if path in ("/remote", "/remote/"):
            self.path = "/remote.html"
            return super().do_GET()
        if path.startswith("/jukebox-video/"):      # a jukebox video the NAS downloaded
            if not wizard.allowed(self.client_address[0]):
                return self.send_error(403)
            vid = path[len("/jukebox-video/"):].rsplit(".", 1)[0]
            f = party.DLR.file_for(vid) if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid) else None
            return self.send_file_ranged(f, (".mp4",)) if f else self.send_error(404)
        if path in ("/p", "/p/", "/play", "/play/"):  # the trivia game on your phone (/p is the short one)
            if path.startswith("/p/") or path == "/p":
                self.send_response(302)
                self.send_header("Location", "/play")
                self.end_headers()
                return
            self.path = "/play.html"
            return super().do_GET()
        if path in ("/j", "/j/"):                    # short address for the jukebox, easy to type
            self.send_response(302)
            self.send_header("Location", "/jukebox")
            self.end_headers()
            return
        if path == "/qr.svg":                         # QR code pictures (the jukebox screen shows them)
            t = (urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("t") or [""])[0][:600]
            try:
                body = qr.qr_svg(t).encode()
            except ValueError:
                return self.send_error(400)
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            self.send_header("Cache-Control", "max-age=86400")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if path in ("/jukebox", "/jukebox/"):
            self.path = "/jukebox.html"
            return super().do_GET()
        if path in ("/wrapped", "/wrapped/"):
            self.path = "/wrapped.html"
            return super().do_GET()
        if path in ("/history", "/history/"):
            self.path = "/history.html"
            return super().do_GET()
        if path.startswith(("/api/remote/", "/api/history", "/api/game/", "/api/party", "/api/alerts", "/api/trivia", "/api/wrapped", "/api/experimental",
                            "/api/throw", "/api/cam", "/api/duck", "/api/secure", "/api/flick", "/api/stream", "/api/ratings", "/api/scorebug")):
            return self.remote_api(path, qs=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
        if path.startswith("/api/tools/"):
            return self.tools_get(path, urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
        if path.startswith("/api/setup"):
            return self.setup_get(path, urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
        if path.startswith("/iptv/"):
            return self.proxy_etv()
        if path == "/api/break":
            return self.send_json(break_data())
        if path == "/api/break/cue":
            return self.send_json(clips.cue)
        if path == "/api/clips":
            files = []
            for name in (sorted(os.listdir(clips.OUT)) if os.path.isdir(clips.OUT) else []):
                full = os.path.join(clips.OUT, name)
                if name.endswith(".ts") and os.path.isfile(full):
                    st = os.stat(full)
                    files.append({"name": name, "size": st.st_size, "mtime": int(st.st_mtime)})
            return self.send_json(dict(clips.status, folder=clips.OUT, files=files, plan=[clips.name_for(s, n) for s, n in clips.plan()],
                                       downloads=clips.downloads, now=int(time.time()), hours=env("BREAK_CLIPS_HOURS", "1"), enabled=clips.enabled(),
                                       where=etv_where(), etv_scan=_scan["last"], etv_library=env("ERSATZTV_CLIPS_LIBRARY")))
        if path == "/api/clips.txt":     # simple list for the Mac/Linux clip copier: name, size, time
            lines = []
            for name in (sorted(os.listdir(clips.OUT)) if os.path.isdir(clips.OUT) else []):
                full = os.path.join(clips.OUT, name)
                if name.endswith(".ts") and os.path.isfile(full):
                    st = os.stat(full)
                    lines.append(f"{name}\t{st.st_size}\t{int(st.st_mtime)}")
            # which clips to keep: everything KNAS plans to make (so clips still being recorded
            # for the first time aren't deleted). With clips off, the copier deletes nothing.
            if clips.enabled():
                lines += [f"#keep\t{clips.name_for(s_, n_)}" for s_, n_ in clips.plan()]
            else:
                lines.append("#nodelete")
            body = ("\n".join(lines) + "\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if path.startswith("/break-clips/"):
            name = os.path.basename(urllib.parse.unquote(path[len("/break-clips/"):]))
            if self.command == "GET" and not self.headers.get("Range", "").startswith("bytes=") or self.headers.get("Range", "") == "bytes=0-":
                clips.note_download(name, self.client_address[0])   # for the setup page's clip status
            return self.send_file_ranged(os.path.join(clips.OUT, name), (".ts",))
        if path in ("/break", "/break/", "/break.html"):
            return self.serve_page("break.html", "break")
        if path in ("/", "/index.html"):
            return self.serve_page("index.html", "index")
        if path.startswith("/logo/"):
            f = looks.logo_file(path[len("/logo/"):].split("?")[0])
            if not f:
                return self.send_error(404)
            return self.send_file_ranged(f, (".png", ".jpg", ".gif", ".webp"))
        if path.startswith("/break-videos/"):
            return self.send_file_ranged(os.path.join(VIDEOS, os.path.basename(urllib.parse.unquote(path[len("/break-videos/"):]))), VIDEO_EXT)
        if path == "/api/sports":
            return self.send_json(sports_with_radio())
        if path.startswith("/radio/") and path.endswith(".mp3"):
            return radio.serve(self, path[len("/radio/"):-4])
        if path.startswith("/vendor/"):
            name = os.path.basename(path)
            for base in (os.path.join(WEB, "vendor"), "/opt/knas/vendor"):
                full = os.path.join(base, name)
                if os.path.isfile(full):
                    self.send_response(200)
                    self.send_header("Content-Type", "application/javascript")
                    self.send_header("Content-Length", str(os.path.getsize(full)))
                    self.end_headers()
                    with open(full, "rb") as f:
                        self.copyfile(f, self.wfile)
                    return
            return self.send_error(404)
        if path in ("/sports", "/sports/", "/sports.html"):
            return self.serve_page("sports.html", "sports")
        if path in ("/tv", "/tv/", "/tv.html"):
            return self.serve_page("tv.html", "tv")
        if path == "/api/version":
            return self.send_json({"version": VERSION, "settings_file": os.path.exists(keeper.SETTINGS), "screen": env("SCREEN", "auto"), "channel_up": env("CHANNEL_UP", "guide").lower(), "shuffle": env("SHUFFLE", "on").lower() not in ("off", "no", "0", "false")})
        if path == "/api/tv":
            return self.send_json(tv_data())
        if path == "/api/all":
            return self.send_json(everything())
        if path == "/api/facts":
            return self.send_json(facts.all_facts(_lines(FACTS)))
        if path == "/api/music":
            try:
                files = sorted(f for f in os.listdir(MUSIC) if f.lower().endswith(AUDIO_EXT))
            except OSError:
                files = []
            return self.send_json(files)
        if path.startswith("/music/"):
            name = os.path.basename(urllib.parse.unquote(path[len("/music/"):]))
            full = os.path.join(MUSIC, name)
            if not name.lower().endswith(AUDIO_EXT) or not os.path.isfile(full):
                return self.send_error(404)
            self.send_response(200)
            self.send_header("Content-Type", self.guess_type(full))
            self.send_header("Content-Length", str(os.path.getsize(full)))
            self.end_headers()
            with open(full, "rb") as f:
                self.copyfile(f, self.wfile)
            return
        return super().do_GET()


if __name__ == "__main__":
    keeper.start_watcher()
    clips.on_made = lambda: etv_scan_soon(5) if etv_where() == "nas" else None
    clips.start()
    remote.setup(DATA)
    history.setup(DATA)
    party.setup(DATA)
    throw.setup(DATA, remote)
    stream.setup(DATA, remote)
    fun.setup(remote)
    alerts.setup(DATA, lambda: (LAT, LON), gametime._push)
    game.setup(DATA, trivia_pool, dict([(k, v[1]) for k, v in facts.TRIVIA_TOPICS.items()] + [("mine", "My trivia list")]),
               tunes=party.DLR.saved)
    gametime.setup(DATA, TEAMS, remote, lambda: env("SPORTS_CHANNEL", "43"), base=lambda: f"http://{lan_ip()}:{PORT}")
    tools.setup(DATA, [x.strip() for x in env("TOOLS_MEDIA_DIRS", "/media").split(",") if x.strip()], explicit=bool(env("TOOLS_MEDIA_DIRS")), nas_dir=env("TOOLS_NAS_DIR", "/nas"))
    facts.start()
    threading.Thread(target=nearby_cities, daemon=True).start()
    threading.Thread(target=warm_weather_channel, daemon=True, name="weather-warm").start()
    print(f"KNAS 42 {VERSION} on the air at http://0.0.0.0:{PORT}", flush=True)
    ip = lan_ip()
    print("", flush=True)
    print("  " + ("Set up KNAS here:  " if not configured() else "Setup page:  ") + f"http://{ip}:{PORT}/setup", flush=True)
    print(f"  Cable box (TV):    http://{ip}:{PORT}/tv", flush=True)
    print("", flush=True)
    if SECURE_PORT:
        import socket as _s
        names = {ip, "localhost", "127.0.0.1", _s.gethostname()}
        try:
            names |= set(_s.gethostbyname_ex(_s.gethostname())[2])
        except OSError:
            pass
        securecert.start(ThreadingHTTPServer, Handler, SECURE_PORT, DATA, sorted(n for n in names if n and n != "YOUR_NAS_IP"))
        print(f"  Secure address:    https://{ip}:{SECURE_PORT}   (for Live Cam, Duck Season and the voice remote)", flush=True)
        print("", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
