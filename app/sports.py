"""KNAS Sports: schedules, live scores, field/court position and play-by-play from ESPN's public feed."""
import json, os, re, time, threading, urllib.request
from datetime import datetime, timezone

ESPN = os.environ.get("ESPN_BASE", "https://site.api.espn.com/apis/site/v2/sports").rstrip("/")

# Friendly names you can use in teams.txt -> ESPN's path for that sport
SPORTS = {
    "college-football": ("football/college-football", "College Football", "football"),
    "mens-college-basketball": ("basketball/mens-college-basketball", "Men's Basketball", "basketball"),
    "womens-college-basketball": ("basketball/womens-college-basketball", "Women's Basketball", "basketball"),
    "nfl": ("football/nfl", "NFL", "football"),
    "nba": ("basketball/nba", "NBA", "basketball"),
    "wnba": ("basketball/wnba", "WNBA", "basketball"),
    "college-baseball": ("baseball/college-baseball", "Baseball", "other"),
    "mlb": ("baseball/mlb", "MLB", "other"),
    "nhl": ("hockey/nhl", "NHL", "other"),
}
ALIASES = {"football": "college-football", "cfb": "college-football", "basketball": "mens-college-basketball",
           "mbb": "mens-college-basketball", "wbb": "womens-college-basketball", "baseball": "college-baseball"}

_cache, _lock = {}, threading.Lock()


def _get(url, ttl):
    now = time.time()
    with _lock:
        hit = _cache.get(url)
        if hit and now - hit[0] < ttl:
            return hit[1]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KNAS42 sports)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        if hit:  # keep showing the last good data if ESPN hiccups
            return hit[1]
        raise
    with _lock:
        _cache[url] = (now, data)
    return data


def read_teams(path):
    """teams.txt lines:  sport | team id | cheer (optional) | radio stream (optional)"""
    teams = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = re.split(r"(?:^|\s)#", line, 1)[0].strip()
                if not line:
                    continue
                parts = [p.strip() for p in line.split("|")]
                if parts[0].lower() == "radio":
                    continue
                sport = ALIASES.get(parts[0].lower(), parts[0].lower())
                if sport not in SPORTS or len(parts) < 2 or not parts[1]:
                    continue
                teams.append({"sport": sport, "id": parts[1], "cheer": parts[2] if len(parts) > 2 else "",
                              "radio": parts[3] if len(parts) > 3 else ""})
    except OSError:
        pass
    return teams


# ------------------------------------------------------------------ helpers
def _num(v):
    if isinstance(v, dict):
        v = v.get("displayValue", v.get("value"))
    if v is None or v == "":
        return None
    try:
        f = float(v)
        return int(f) if f == int(f) else f
    except (TypeError, ValueError):
        return v


def _logo(t):
    if not t:
        return ""
    if t.get("logo"):
        return t["logo"]
    for l in t.get("logos") or []:
        if l.get("href"):
            return l["href"]
    return ""


def _record(c):
    for key in ("records", "record"):
        recs = c.get(key)
        if isinstance(recs, list):
            for r in recs:
                if r.get("type") in (None, "total") or r.get("name") in ("overall", "All Splits"):
                    return r.get("summary") or r.get("displayValue") or ""
            if recs:
                return recs[0].get("summary") or recs[0].get("displayValue") or ""
    return ""


def _side(c):
    t = c.get("team") or {}
    return {"id": str(t.get("id", "")), "abbr": t.get("abbreviation", ""),
            "name": t.get("displayName") or t.get("name") or "", "short": t.get("shortDisplayName") or t.get("location") or t.get("name") or "",
            "nick": t.get("name") or "", "color": "#" + (t.get("color") or "334488"), "alt": "#" + (t.get("alternateColor") or "ffffff"),
            "logo": _logo(t), "score": _num(c.get("score")), "record": _record(c),
            "rank": (c.get("curatedRank") or {}).get("current") if (c.get("curatedRank") or {}).get("current", 99) <= 25 else None,
            "possession": bool(c.get("possession"))}


def _tv(comp, event):
    names = []
    for src in (comp.get("broadcasts") or [], event.get("broadcasts") or [], comp.get("geoBroadcasts") or []):
        for b in src:
            for n in (b.get("names") or []):
                names.append(n)
            m = (b.get("media") or {}).get("shortName")
            if m:
                names.append(m)
    seen = []
    for n in names:
        if n not in seen:
            seen.append(n)
    return " / ".join(seen[:2])


def _game(event):
    """Normalize a schedule/scoreboard/nextEvent event."""
    comp = (event.get("competitions") or [{}])[0]
    st = comp.get("status") or event.get("status") or {}
    stype = st.get("type") or {}
    sides = {c.get("homeAway"): _side(c) for c in comp.get("competitors") or []}
    venue = comp.get("venue") or {}
    addr = venue.get("address") or {}
    return {"id": str(event.get("id", "")), "date": event.get("date") or comp.get("date"),
            "name": event.get("name", ""), "short": event.get("shortName", ""),
            "state": stype.get("state", "pre"), "detail": stype.get("shortDetail") or stype.get("detail") or "",
            "completed": bool(stype.get("completed")), "clock": st.get("displayClock", ""), "period": st.get("period", 0),
            "venue": venue.get("fullName", ""), "city": ", ".join(x for x in (addr.get("city"), addr.get("state")) if x),
            "tv": _tv(comp, event), "home": sides.get("home"), "away": sides.get("away"),
            "neutral": bool(comp.get("neutralSite"))}


def _ts(d):
    try:
        return datetime.fromisoformat(d.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


# ------------------------------------------------------------------ live game detail
def _football_detail(summary, g):
    situation, plays = summary.get("situation") or {}, []
    drives = summary.get("drives") or {}
    allplays = []
    for d in (drives.get("previous") or []) + ([drives["current"]] if drives.get("current") else []):
        for p in d.get("plays") or []:
            p["_team"] = (d.get("team") or {}).get("abbreviation", "")
            allplays.append(p)
    last = allplays[-1] if allplays else None
    sit = {}
    if situation:
        sit = {"down": situation.get("down"), "distance": situation.get("distance"),
               "toEndzone": situation.get("yardsToEndzone"), "text": situation.get("downDistanceText") or situation.get("shortDownDistanceText") or "",
               "spot": situation.get("possessionText", ""), "team": str(situation.get("possession") or ""),
               "redzone": bool(situation.get("isRedZone"))}
        if sit["toEndzone"] is None and situation.get("yardLine") is not None:
            sit["yardLine"] = situation.get("yardLine")
    if (not sit or sit.get("toEndzone") is None) and last:
        e = last.get("end") or {}
        sit = {"down": e.get("down"), "distance": e.get("distance"), "toEndzone": e.get("yardsToEndzone"),
               "text": e.get("downDistanceText") or e.get("shortDownDistanceText") or "", "spot": e.get("possessionText", ""),
               "team": str((e.get("team") or {}).get("id", "")), "redzone": (e.get("yardsToEndzone") or 99) <= 20}
    if not sit.get("team"):
        for s in ("home", "away"):
            if g[s] and g[s]["possession"]:
                sit["team"] = g[s]["id"]
    for p in reversed(allplays[-12:]):
        plays.append({"text": p.get("text", ""), "type": (p.get("type") or {}).get("text", ""),
                      "clock": (p.get("clock") or {}).get("displayValue", ""), "period": (p.get("period") or {}).get("number", ""),
                      "scoring": bool(p.get("scoringPlay")), "team": p.get("_team", ""), "yards": p.get("statYardage")})
    return sit, plays


def _basketball_detail(summary, g):
    raw = summary.get("plays") or []
    ids = {g["home"]["id"]: "home", g["away"]["id"]: "away"} if g["home"] and g["away"] else {}
    plays, shots = [], []
    for p in raw[-200:]:
        tid = str((p.get("team") or {}).get("id", ""))
        c = p.get("coordinate") or {}
        x, y = c.get("x"), c.get("y")
        if p.get("shootingPlay") and isinstance(x, (int, float)) and isinstance(y, (int, float)) and 0 <= x <= 50 and 0 <= y <= 94:
            shots.append({"x": x, "y": y, "made": bool(p.get("scoringPlay")), "side": ids.get(tid, ""),
                          "pts": p.get("scoreValue", 0), "text": p.get("text", "")})
    for p in reversed(raw[-12:]):
        tid = str((p.get("team") or {}).get("id", ""))
        plays.append({"text": p.get("text", ""), "type": (p.get("type") or {}).get("text", ""),
                      "clock": (p.get("clock") or {}).get("displayValue", ""),
                      "period": (p.get("period") or {}).get("displayValue") or (p.get("period") or {}).get("number", ""),
                      "scoring": bool(p.get("scoringPlay")), "side": ids.get(tid, ""), "pts": p.get("scoreValue", 0)})
    return {}, plays, shots[-24:]


WANT_STATS = {
    "football": ["totalYards", "netPassingYards", "rushingYards", "firstDowns", "thirdDownEff", "turnovers", "possessionTime"],
    "basketball": ["fieldGoalPct", "threePointFieldGoalPct", "freeThrowPct", "totalRebounds", "assists", "turnovers", "pointsInPaint"],
}


def _stats(summary, g, kind):
    out = {}
    for t in (summary.get("boxscore") or {}).get("teams") or []:
        tid = str((t.get("team") or {}).get("id", ""))
        side = "home" if g["home"] and tid == g["home"]["id"] else "away" if g["away"] and tid == g["away"]["id"] else None
        if not side:
            continue
        for s in t.get("statistics") or []:
            out.setdefault(s.get("name"), {"label": s.get("label") or s.get("abbreviation") or s.get("name")})[side] = s.get("displayValue", "")
    order = WANT_STATS.get(kind, [])
    return [dict(out[k], key=k) for k in order if k in out]


def live_detail(path, kind, game):
    summary = _get(f"{ESPN}/{path}/summary?event={game['id']}", 5)
    header = ((summary.get("header") or {}).get("competitions") or [None])[0]
    if header:
        fresh = _game({"id": game["id"], "competitions": [header], "date": game["date"], "name": game["name"]})
        for k in ("state", "detail", "clock", "period", "completed"):
            game[k] = fresh[k]
        for s in ("home", "away"):
            if fresh[s]:
                keep = game.get(s) or {}
                fresh[s]["record"] = fresh[s]["record"] or keep.get("record", "")
                fresh[s]["logo"] = fresh[s]["logo"] or keep.get("logo", "")
                game[s] = fresh[s]
    if kind == "football":
        game["situation"], game["plays"] = _football_detail(summary, game)
    elif kind == "basketball":
        game["situation"], game["plays"], game["shots"] = _basketball_detail(summary, game)
    game["stats"] = _stats(summary, game, kind)
    return game


# ------------------------------------------------------------------ per team
def _schedule(path, tid):
    url = f"{ESPN}/{path}/teams/{tid}/schedule"
    data = _get(url, 600)
    events = data.get("events") or []
    if not events:  # some sports only answer with an explicit season
        y = datetime.now().year
        for season in (y, y + 1):
            d2 = _get(f"{url}?season={season}", 600)
            if d2.get("events"):
                data, events = d2, d2["events"]
                break
    return data, events


def team_status(t):
    path, label, kind = SPORTS[t["sport"]]
    out = {"sport": t["sport"], "label": label, "kind": kind, "cheer": t["cheer"], "radio": t.get("radio", ""), "team": None,
           "live": None, "next": None, "last": None, "error": None}
    try:
        info = _get(f"{ESPN}/{path}/teams/{t['id']}", 60).get("team") or {}
        rec = ""
        for item in ((info.get("record") or {}).get("items") or []):
            if item.get("type") == "total":
                rec = item.get("summary", "")
        out["team"] = {"id": str(info.get("id", t["id"])), "abbr": info.get("abbreviation", ""),
                       "name": info.get("displayName", ""), "nick": info.get("name", ""), "short": info.get("location") or info.get("shortDisplayName", ""),
                       "color": "#" + (info.get("color") or "a32136"), "alt": "#" + (info.get("alternateColor") or "ffffff"),
                       "logo": _logo(info), "record": rec, "standing": info.get("standingSummary", "")}
        games = [_game(e) for e in (info.get("nextEvent") or [])]
        try:
            sched, events = _schedule(path, t["id"])
            if not out["team"]["record"]:
                out["team"]["record"] = (sched.get("team") or {}).get("recordSummary", "")
            games += [_game(e) for e in events]
        except Exception as e:
            out["error"] = f"schedule: {e}"
        byid = {}
        for g in games:  # nextEvent is fresher, keep the first copy
            byid.setdefault(g["id"], g)
        games = sorted(byid.values(), key=lambda g: _ts(g["date"]))
        now = time.time()
        live = [g for g in games if g["state"] == "in"]
        upcoming = [g for g in games if g["state"] == "pre" and _ts(g["date"]) > now - 4 * 3600]
        done = [g for g in games if g["state"] == "post"]
        if live:
            try:
                out["live"] = live_detail(path, kind, live[0])
            except Exception as e:
                out["live"] = live[0]
                out["error"] = f"live: {e}"
        out["next"] = upcoming[0] if upcoming else None
        out["last"] = done[-1] if done else None
        out["results"] = [{"opp": (g["away"] if g["home"] and g["home"]["id"] == out["team"]["id"] else g["home"] or {}).get("abbr", ""),
                           "home": bool(g["home"] and g["home"]["id"] == out["team"]["id"]),
                           "us": (g["home"] if g["home"] and g["home"]["id"] == out["team"]["id"] else g["away"] or {}).get("score"),
                           "them": (g["away"] if g["home"] and g["home"]["id"] == out["team"]["id"] else g["home"] or {}).get("score")}
                          for g in done[-5:]]
    except Exception as e:
        out["error"] = str(e)
    return out


def sports_data(teams_file):
    teams = read_teams(teams_file)
    return {"now": time.time(), "teams": [team_status(t) for t in teams], "configured": bool(teams),
            "radio": radio_setting(teams_file)}


DEFAULT_RADIO = ("", "Radio")


def radio_setting(teams_file):
    """Sports channel radio. Order: a 'radio | url | name' line in teams.txt, then SPORTS_RADIO (blank = no radio).
    'radio | off' turns it off."""
    try:
        with open(teams_file, encoding="utf-8") as f:
            for line in f:
                line = re.split(r"(?:^|\s)#", line, 1)[0].strip()
                parts = [x.strip() for x in line.split("|")]
                if parts and parts[0].lower() == "radio":
                    url = parts[1] if len(parts) > 1 else ""
                    if url.lower() in ("off", "none", ""):
                        return {"url": "", "name": ""}
                    return {"url": url, "name": parts[2] if len(parts) > 2 and parts[2] else "Radio"}
    except OSError:
        pass
    env_url = os.environ.get("SPORTS_RADIO", "").strip()
    if env_url:
        if env_url.lower() in ("off", "none"):
            return {"url": "", "name": ""}
        return {"url": env_url, "name": os.environ.get("SPORTS_RADIO_NAME", "").strip() or "Radio"}
    return {"url": DEFAULT_RADIO[0], "name": DEFAULT_RADIO[1]}
