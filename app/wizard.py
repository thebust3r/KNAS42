"""KNAS setup page backend: reads and writes settings.txt and teams.txt for the /setup page,
looks up towns and ESPN teams, and tests the ErsatzTV address. Stdlib only."""
import json, os, re, time, ipaddress, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SETTINGS = os.path.join(ROOT, "settings.txt")
BACKUP = os.path.join(ROOT, "data", "settings.backup.txt")
TEAMS = os.environ.get("TEAMS_FILE", os.path.join(ROOT, "teams.txt"))

# Everything the setup page can change. Anything else in settings.txt is left alone.
KEYS = ["CITY_NAME", "LATITUDE", "LONGITUDE", "UNITS", "TZ", "ERSATZTV_URL", "ERSATZTV_MODE", "SCREEN", "CHANNEL_UP", "STATION_NAME",
        "PAGE_SECONDS", "CRAWL_MESSAGE", "KNAS_CHANNEL", "SPORTS_CHANNEL", "PARTY_CHANNEL", "PARTY_NAME", "TRIVIA_CHANNEL", "TRIVIA_NAME", "WRAPPED_CHANNEL", "LIVECAM_CHANNEL", "LIVECAM_NAME", "DUCK_CHANNEL", "DUCK_NAME", "FLICK_CHANNEL", "FLICK_NAME", "STREAM_CHANNEL", "STREAM_NAME", "SCORE_BUG", "SCORE_BUG_ON", "SCORE_BUG_OFF", "SCREEN_FUN", "THROW", "VOICE_REMOTE", "JUKEBOX_DOWNLOAD", "JUKEBOX_CACHE_GB", "JUKEBOX_WIFI_NAME", "JUKEBOX_WIFI_PASSWORD", "STATIC_VOLUME", "LOCAL_NEWS_FEEDS", "US_NEWS_FEEDS", "NEWS_MAX_HOURS",
        "MAP_CITIES", "MAP_KEY", "MAP_STYLE", "WEATHER_PAGES", "SPORTS_RADIO", "SPORTS_RADIO_NAME", "RADIO_KEEP_MINUTES",
        "KUMA_URL", "KUMA_SLUG", "SPOTIFY_URL", "SPOTIFY_NOWPLAYING_PATH", "SPOTIFY_TOP_PATH", "SPOTIFY_TOP_LABEL",
        "CAST_CHANNELS", "MUSIC_VOLUME", "VIDEO_BITRATE", "FPS", "BROWSER_RESTART_HOURS",
        "BREAK_CLIPS_ON", "BREAK_CLIPS", "BREAK_CLIPS_HOURS",
        "ERSATZTV_HOST", "ERSATZTV_CLIPS_LIBRARY", "ERSATZTV_API_KEY", "JELLYFIN_URL", "JELLYFIN_API_KEY", "VIEW_HISTORY", "WEATHER_ALERTS", "WEATHER_ALERT_LEVEL", "WEATHER_ALERT_TONES", "WEATHER_ALERT_PHONE", "GAME_NOTICE", "GAME_SWITCH", "GAME_TVS", "GAME_LEAD", "GAME_CHANNEL", "GAME_FINAL", "NTFY_URL", "NTFY_TOKEN", "FACTS_LIST", "FACTS_LOCAL", "FACTS_SOURCES", "TRIVIA_LIST", "TRIVIA_TOPICS", "TRIVIA_SOURCES", "BREAK_VIDEO_MAX", "BREAK_SEGMENTS", "SHUFFLE",
        # look & feel
        "THEME", "COLOR_SKY_TOP", "COLOR_SKY_MIDDLE", "COLOR_SKY_BOTTOM", "COLOR_PANEL", "COLOR_EDGE", "COLOR_ACCENT",
        "COLOR_TEXT", "COLOR_TICKER", "COLOR_LOGO", "COLOR_LOGO_BAND", "SCANLINES",
        "CABLE_NAME", "SPORTS_NAME", "GUIDE_NAME", "BREAK_LINE1", "BREAK_LINE2", "WELCOME_TEXT",
        # sound
        "LEVEL_AUDIO", "LEVEL_STRENGTH", "LEVEL_TARGET", "LEVEL_LIMITER", "LEVEL_CEILING", "LEVEL_FADE_MS",
        "VOL_TV", "VOL_MUSIC", "VOL_RADIO",
        # guide style & holidays
        "GUIDE_STYLE", "FONT", "FONT_WEIGHT", "TEXT_SHADOW", "SEASON", "SEASON_EFFECTS", "SEASON_TUNE", "SEASON_GREETING", "SEASON_COLORS", "SEASON_WINTER"]
TEXTS = {"PARTY_NAME", "TRIVIA_NAME", "LIVECAM_NAME", "DUCK_NAME", "FLICK_NAME", "STREAM_NAME", "CABLE_NAME", "SPORTS_NAME", "GUIDE_NAME", "BREAK_LINE1", "BREAK_LINE2", "WELCOME_TEXT", "STATION_NAME", "CRAWL_MESSAGE"}

# value checks, so a typo on the setup page can't break anything
NUMBERS = {"PAGE_SECONDS": (4, 120), "KNAS_CHANNEL": (0, 9999), "SPORTS_CHANNEL": (0, 9999), "PARTY_CHANNEL": (0, 9999), "TRIVIA_CHANNEL": (0, 9999), "WRAPPED_CHANNEL": (0, 9999), "LIVECAM_CHANNEL": (0, 9999), "DUCK_CHANNEL": (0, 9999), "FLICK_CHANNEL": (0, 9999), "SCORE_BUG_ON": (1, 60), "SCORE_BUG_OFF": (1, 240), "STREAM_CHANNEL": (0, 9999), "JUKEBOX_CACHE_GB": (1, 2000), "STATIC_VOLUME": (0, 100),
           "RADIO_KEEP_MINUTES": (0, 1440), "MUSIC_VOLUME": (0, 2), "FPS": (10, 30), "BROWSER_RESTART_HOURS": (0, 168),
           "BREAK_CLIPS_HOURS": (1, 48), "NEWS_MAX_HOURS": (1, 72), "ERSATZTV_CLIPS_LIBRARY": (1, 99999), "BREAK_VIDEO_MAX": (5, 1800),
           "LEVEL_TARGET": (-12, 12), "LEVEL_CEILING": (-12, 0), "LEVEL_FADE_MS": (0, 3000), "VOL_TV": (0, 200), "VOL_MUSIC": (0, 200), "VOL_RADIO": (0, 200), "GAME_LEAD": (1, 120), "LATITUDE": (-90, 90), "LONGITUDE": (-180, 180)}
CHOICES = {"BREAK_CLIPS_ON": ("on", "off"), "ERSATZTV_HOST": ("nas", "windows", "other"), "FACTS_LIST": ("on", "off"), "FACTS_LOCAL": ("on", "off"), "TRIVIA_LIST": ("on", "off"),
           "GUIDE_STYLE": ("knas", "satellite", "cable", "chrome", "listings"),
           "FONT": ("classic", "smooth", "modern", "easyread", "rounded", "headline", "scoreboard", "jersey", "friendly",
                    "y2k", "neon", "teletext", "computer", "bubbly", "comic", "marker", "newspaper", "fancy"),
           "FONT_WEIGHT": ("bold", "lighter"), "TEXT_SHADOW": ("classic", "soft", "thin"),
           "SEASON": ("auto", "off", "halloween", "thanksgiving", "christmas", "newyear", "valentines", "stpatricks", "easter", "july4", "winter"),
           "SEASON_EFFECTS": ("full", "light", "off"), "SEASON_TUNE": ("on", "off"), "SEASON_GREETING": ("on", "off"),
           "SEASON_COLORS": ("on", "off"), "SEASON_WINTER": ("on", "off"), "THEME": ("classic", "midnight", "sunset", "ocean", "forest", "cherry", "amber", "terminal", "mono", "pastel"),
           "SCANLINES": ("on", "off", "strong"), "LEVEL_AUDIO": ("on", "off"), "LEVEL_LIMITER": ("on", "off"),
           "LEVEL_STRENGTH": ("light", "medium", "strong"), "SHUFFLE": ("on", "off"), "MAP_STYLE": ("osm", "dark", "light", "terrain", "relief", "satellite", "streets", "topo", "carto"), "UNITS": ("us", "metric"), "SCREEN": ("auto", "4:3"), "CHANNEL_UP": ("guide", "number"), "VIEW_HISTORY": ("on", "off"), "UPDATE_CHECK": ("on", "off"), "WEATHER_ALERTS": ("on", "off"), "WEATHER_ALERT_LEVEL": ("warnings", "watches", "all"), "WEATHER_ALERT_TONES": ("on", "off"), "WEATHER_ALERT_PHONE": ("on", "off"), "JUKEBOX_DOWNLOAD": ("on", "off"), "THROW": ("on", "off"), "SCORE_BUG": ("off", "scores", "cycle", "always"), "SCREEN_FUN": ("on", "off"), "VOICE_REMOTE": ("on", "off"), "GAME_NOTICE": ("on", "off"), "GAME_SWITCH": ("on", "off"), "GAME_FINAL": ("on", "off"), "ERSATZTV_MODE": ("segmenter", "hls-direct")}


def check(k, v):
    v = re.sub(r"[\r\n]+", " ", str(v if v is not None else "")).strip()
    if v == "":
        return ""
    if k in NUMBERS:
        try:
            n = float(v)
        except ValueError:
            return None
        lo, hi = NUMBERS[k]
        n = max(lo, min(hi, n))
        return str(int(n)) if n == int(n) and k not in ("MUSIC_VOLUME", "LATITUDE", "LONGITUDE") else str(round(n, 4))
    if k in CHOICES:
        return v if v in CHOICES[k] else None
    if k.startswith("COLOR_"):
        return ("#" + v.lstrip("#").lower()) if re.fullmatch(r"#?[0-9a-fA-F]{6}", v) else None
    if k in TEXTS:
        return re.sub(r"[<>]", "", v)[:60]
    if k in ("FACTS_SOURCES", "TRIVIA_SOURCES"):
        return "; ".join(x.strip() for x in re.sub(r"[<>]", "", v).split(";") if x.strip())[:2000]
    if k == "TRIVIA_TOPICS":
        import facts
        return ", ".join(t for t in (x.strip().lower() for x in v.split(",")) if t in facts.TRIVIA_TOPICS)
    if k in ("ERSATZTV_API_KEY", "JELLYFIN_API_KEY"):
        v = v.strip().strip('"').strip()
        return v if re.fullmatch(r"[A-Za-z0-9+/=_.\-]{8,300}", v) else None
    if k in ("JUKEBOX_WIFI_NAME", "JUKEBOX_WIFI_PASSWORD"):
        return v[:64]
    if k == "GAME_CHANNEL":
        return v if re.fullmatch(r"\d{1,5}(\.\d{1,3})?", v) else None
    if k == "GAME_TVS":
        return ",".join(x for x in (y.strip() for y in v.split(",")) if re.fullmatch(r"[A-Za-z0-9_-]{6,40}", x))
    if k == "NTFY_TOKEN":
        v = v.strip().strip('"').strip()
        return v if re.fullmatch(r"[A-Za-z0-9+/=_.:\- ]{4,300}", v) else None
    if k == "NTFY_URL":
        v = v.strip()
        if not re.match(r"^https?://", v):
            v = "https://" + v
        return v if re.fullmatch(r"https?://[^\s<>\"']{3,300}", v) else None
    if k == "VIDEO_BITRATE":
        return v if re.fullmatch(r"\d{3,5}k", v) else None
    if k == "CAST_CHANNELS":
        if v.lower() == "none":          # record nothing
            return "none"
        ok = [x.strip() for x in v.split(",") if re.fullmatch(r"\s*\d{2,5}=/[^,\s]*\s*", x)]
        return ", ".join(ok)
    if k in ("ERSATZTV_URL", "KUMA_URL", "SPOTIFY_URL", "SPORTS_RADIO", "JELLYFIN_URL") and not re.match(r"^https?://", v):
        v = "http://" + v
    return v


def allowed(client_ip):
    """Only devices on your own network may change settings."""
    try:
        ip = ipaddress.ip_address(client_ip.split("%")[0])
        if ip.version == 6 and ip.ipv4_mapped:
            ip = ip.ipv4_mapped
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return True
        # Tailscale: your own devices connected through your tailnet count as home
        return any(ip in ipaddress.ip_network(n) for n in ("100.64.0.0/10", "fd7a:115c:a1e0::/48") if ipaddress.ip_network(n).version == ip.version)
    except ValueError:
        return False


def read_settings():
    out = {}
    try:
        with open(SETTINGS, encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    out[k.strip()] = v.strip()
    except OSError:
        pass
    return out


def write_settings(values):
    """Update KEY=value lines in place (keeping all the notes), add any that are missing."""
    clean = {}
    for k, v in values.items():
        if k in KEYS:
            c = check(k, v)
            if c is not None:          # a bad value is skipped and the old one is kept
                clean[k] = c
    try:                               # keep a copy of the last settings, just in case
        import shutil
        os.makedirs(os.path.dirname(BACKUP), exist_ok=True)
        shutil.copyfile(SETTINGS, BACKUP)
    except OSError:
        pass
    try:
        with open(SETTINGS, encoding="utf-8-sig") as f:
            lines = f.read().split("\n")
    except OSError:
        lines = ["# KNAS settings (made by the setup page)", ""]
    seen = set()
    for i, raw in enumerate(lines):
        s = raw.strip()
        if s and not s.startswith("#") and "=" in s:
            k = s.split("=", 1)[0].strip()
            if k in clean:
                lines[i] = f"{k}={clean[k]}"
                seen.add(k)
    missing = [k for k in clean if k not in seen]
    if missing:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append("# ---- Added by the setup page ----")
        lines += [f"{k}={clean[k]}" for k in missing]
    tmp = SETTINGS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    os.replace(tmp, SETTINGS)
    try:
        os.chmod(SETTINGS, 0o666)
    except OSError:
        pass


def read_teams():
    teams = []
    try:
        with open(TEAMS, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                p = [x.strip() for x in line.split("|")]
                if p[0].lower() == "radio" or len(p) < 2:
                    continue
                teams.append({"sport": p[0], "id": p[1], "cheer": p[2] if len(p) > 2 else "", "radio": p[3] if len(p) > 3 else "",
                              "name": ""})
    except OSError:
        pass
    return teams


def write_teams(teams):
    header = []
    try:
        with open(TEAMS, encoding="utf-8") as f:
            for raw in f:
                if raw.strip().startswith("#") or not raw.strip():
                    header.append(raw.rstrip("\n"))
                else:
                    break
    except OSError:
        header = ["# KNAS Sports teams (made by the setup page)", "# sport | ESPN team id | cheer | radio stream", ""]
    while header and not header[-1].strip():
        header.pop()
    rows = []
    for t in teams or []:
        sport = re.sub(r"[^a-z\-]", "", str(t.get("sport", "")).lower())
        tid = re.sub(r"[^0-9A-Za-z]", "", str(t.get("id", "")))
        if not sport or not tid:
            continue
        cheer = re.sub(r"[|\r\n#]", " ", str(t.get("cheer", ""))).strip()
        radio = re.sub(r"[|\r\n ]", "", str(t.get("radio", ""))).strip()
        name = re.sub(r"[\r\n#]", " ", str(t.get("name", ""))).strip()
        rows.append(f"{sport} | {tid} | {cheer}" + (f" | {radio}" if radio else "") + (f"     # {name}" if name else ""))
    with open(TEAMS, "w", encoding="utf-8") as f:
        f.write("\n".join(header + [""] + rows) + "\n")
    try:
        os.chmod(TEAMS, 0o666)
    except OSError:
        pass


def _get_json(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "knas42/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def geocode(q):
    name, _, where = (q or "").partition(",")
    if not name.strip():
        return []
    j = _get_json("https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": name.strip(), "count": 10, "language": "en", "format": "json"}))
    out = []
    for r in j.get("results") or []:
        label = ", ".join(x for x in [r.get("name"), r.get("admin1"), r.get("country")] if x)
        out.append({"label": label, "name": r.get("name"), "admin1": r.get("admin1", ""), "country_code": r.get("country_code", ""),
                    "lat": r.get("latitude"), "lon": r.get("longitude"), "tz": r.get("timezone", "")})
    w = where.strip().lower()
    if w:
        out.sort(key=lambda r: 0 if w in r["label"].lower() or w == r["country_code"].lower() else 1)
    return out


_team_cache = {}


def team_search(sport, q):
    import sports
    if sport not in sports.SPORTS:
        return []
    path = sports.SPORTS[sport][0]
    hit = _team_cache.get(sport)
    if not hit or time.time() - hit[0] > 86400:
        url = f"https://site.api.espn.com/apis/site/v2/sports/{path}/teams?limit=1000"
        if sport.startswith("college") or "college" in sport:
            url += "&groups=" + ("80" if "football" in sport else "50")
        j = _get_json(url, timeout=20)
        teams = []
        for lg in (j.get("sports") or [{}])[0].get("leagues") or []:
            for t in lg.get("teams") or []:
                t = t.get("team", t)
                logo = ((t.get("logos") or [{}])[0] or {}).get("href", "")
                teams.append({"id": str(t.get("id")), "name": t.get("displayName") or t.get("name"),
                              "short": t.get("shortDisplayName", ""), "abbr": t.get("abbreviation", ""), "logo": logo})
        hit = (time.time(), teams)
        _team_cache[sport] = hit
    ql = (q or "").strip().lower()
    res = [t for t in hit[1] if not ql or ql in (t["name"] or "").lower() or ql == (t["abbr"] or "").lower()]
    return res[:25]


def test_ersatztv(url):
    url = (url or "").strip().rstrip("/")
    if not url:
        return {"ok": False, "message": "Type the address first."}
    if not re.match(r"^https?://", url):
        url = "http://" + url
    try:
        req = urllib.request.Request(url + "/iptv/channels.m3u", headers={"User-Agent": "knas42/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            text = r.read().decode("utf-8", "replace")
        n = text.count("#EXTINF")
        return {"ok": True, "url": url, "message": f"Connected! Found {n} channel{'s' if n != 1 else ''}."}
    except Exception as e:
        return {"ok": False, "url": url, "message": f"Couldn't reach ErsatzTV there ({e}). Check the IP and port (usually 8409)."}


def clip_sync_script(nas_url):
    p = os.path.join(ROOT, "extras", "windows", "knas-clip-sync.ps1")
    with open(p, encoding="utf-8") as f:
        s = f.read()
    return s.replace("http://YOUR_NAS_IP:8642", nas_url)


def windows_file(name, nas_url):
    """A Windows helper from extras/windows with your KNAS address filled in (Windows line endings)."""
    with open(os.path.join(ROOT, "extras", "windows", name), encoding="utf-8") as f:
        s = f.read().replace("http://YOUR_NAS_IP:8642", nas_url)
    return s.replace("\r\n", "\n").replace("\n", "\r\n")


def clip_sync_sh(nas_url):
    p = os.path.join(ROOT, "extras", "mac-linux", "knas-clip-sync.sh")
    with open(p, encoding="utf-8") as f:
        s = f.read()
    return s.replace("http://YOUR_NAS_IP:8642", nas_url)


def weather_yml(host_ip):
    p = os.path.join(ROOT, "extras", "ersatztv", "KNAS 42 Weather.yml")
    with open(p, encoding="utf-8") as f:
        return f.read().replace("YOUR_NAS_IP", host_ip)


def write_list(path, kind, text):
    """Save the facts or trivia list from the setup page (keeps a backup of the old one)."""
    import shutil
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [l for l in text.split("\n") if l.strip() and not l.lstrip().startswith("#")]
    if kind == "trivia":
        bad = [l for l in lines if len([p for p in l.split("|") if p.strip()]) < 3]
        if bad:
            return {"ok": False, "message": f"This line needs at least: question | right answer | wrong answer\n{bad[0][:120]}"}
    data = os.path.join(os.path.dirname(path), "data")
    os.makedirs(data, exist_ok=True)
    if os.path.exists(path):
        shutil.copyfile(path, os.path.join(data, os.path.basename(path).replace(".txt", ".backup.txt")))
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.rstrip("\n") + "\n")
    try:
        os.chmod(path, 0o666)
    except OSError:
        pass
    return {"ok": True, "count": len(lines)}
