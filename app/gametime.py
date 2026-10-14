"""Game time: a heads-up before your teams play, and (if you want) the TVs flip to the game by themselves.

Everything here is off until you turn it on (setup page → Sports → Game time). Each part is separate:

  GAME_NOTICE=on    a "game starts in 10 minutes, press OK to watch" box on every TV that's on
  GAME_SWITCH=on    TVs that are on change to the game channel by themselves
  GAME_TVS=         which TVs switch (TV ids from the phone remote, comma separated); blank = every TV that's on
  GAME_LEAD=10      how many minutes before the start
  GAME_CHANNEL=     the channel to show (blank = the KNAS Sports channel)
  NTFY_URL=         a phone notification through the free ntfy app (like https://ntfy.sh/my-knas-topic)
  NTFY_TOKEN=       only if your ntfy topic needs a sign-in token
  GAME_FINAL=on     also send the final score to the phone

The teams come from teams.txt (the same ones the Sports channel follows).
"""
import json, os, threading, time, urllib.request

import sports

DATA = ""
TEAMS = ""
REMOTE = None
SPORTS_CH = lambda: "43"
BASE = lambda: ""
STATE = {"fired": {}, "seeded": False, "base": ""}
LOG = []                       # recent things this did, for the setup page
_lock = threading.Lock()
TICK = 60


def _on(k):
    return os.environ.get(k, "off").strip().lower() in ("on", "yes", "1", "true")


def _lead():
    try:
        return max(1, min(120, int(float(os.environ.get("GAME_LEAD", "10") or 10))))
    except ValueError:
        return 10


def channel():
    return (os.environ.get("GAME_CHANNEL") or "").strip() or str(SPORTS_CH() or "43")


def _ntfy():
    return (os.environ.get("NTFY_URL") or "").strip(), (os.environ.get("NTFY_TOKEN") or "").strip()


def anything_on():
    return _on("GAME_NOTICE") or _on("GAME_SWITCH") or bool(_ntfy()[0])


def setup(data_dir, teams_file, remote_mod, sports_channel, base=None):
    global DATA, TEAMS, REMOTE, SPORTS_CH, BASE
    DATA, TEAMS, REMOTE, SPORTS_CH = data_dir, teams_file, remote_mod, sports_channel
    if base:
        BASE = base
    try:
        with open(os.path.join(DATA, "gametime.json")) as f:
            STATE.update(json.load(f))
    except (OSError, ValueError):
        pass
    threading.Thread(target=_loop, daemon=True, name="gametime").start()


def _save():
    try:
        cut = time.time() - 30 * 86400                     # forget games from over a month ago
        STATE["fired"] = {k: v for k, v in STATE["fired"].items() if v > cut}
        tmp = os.path.join(DATA, "gametime.json.tmp")
        with open(tmp, "w") as f:
            json.dump(STATE, f)
        os.replace(tmp, os.path.join(DATA, "gametime.json"))
    except OSError:
        pass


def _log(msg):
    with _lock:
        LOG.insert(0, {"at": time.time(), "text": msg})
        del LOG[20:]
    print("[game time]", msg, flush=True)


def _loop():
    time.sleep(20)
    while True:
        try:
            if anything_on():
                check()
        except Exception as e:
            print("[game time]", e, flush=True)
        time.sleep(TICK)


def _opp(team, g):
    us = (team or {}).get("id")
    home, away = g.get("home") or {}, g.get("away") or {}
    them = away if home.get("id") == us else home
    return them, home.get("id") == us


def _name(team):
    return (team or {}).get("nick") or (team or {}).get("short") or (team or {}).get("name") or "Your team"


def check(now=None, data=None):
    """Look at the schedule once. Split out (with now/data) so it can be tested with a made-up schedule."""
    now = now or time.time()
    data = data or sports.sports_data(TEAMS)
    lead = _lead() * 60
    soon = []
    finals = []
    for t in data.get("teams") or []:
        team = t.get("team")
        if not team:
            continue
        for g in (t.get("live"), t.get("next")):
            if not g or not g.get("id"):
                continue
            start = sports._ts(g.get("date") or "")
            # from LEAD minutes before the start until 20 minutes in (in case KNAS was off at the time)
            if start and start - lead <= now < start + 20 * 60 and g.get("state") in ("pre", "in"):
                soon.append((t, team, g, start))
        g = t.get("last")
        if g and g.get("id") and g.get("state") == "post":
            finals.append((t, team, g))
    fresh = False
    if not STATE.get("seeded"):                   # first run: don't announce games that already finished
        for _t, _team, g in finals:
            STATE["fired"]["final:" + g["id"]] = now
        STATE["seeded"] = True
        fresh = True
    games = []
    for t, team, g, start in soon:
        k = "soon:" + g["id"]
        if k in STATE["fired"]:
            continue
        STATE["fired"][k] = now
        fresh = True
        games.append((t, team, g, start))
    if games:
        _game_time(games, now)
    for t, team, g in finals:
        k = "final:" + g["id"]
        if k in STATE["fired"]:
            continue
        STATE["fired"][k] = now
        fresh = True
        _final(team, g)
    if fresh:
        _save()


def _game_time(games, now):
    lines = []
    for t, team, g, start in games:
        them, home = _opp(team, g)
        mins = int(round((start - now) / 60))
        when = f"starts in {mins} min" if mins > 1 else ("starts in a minute" if mins == 1 else "is on now")
        vs = ("vs " if home else "at ") + (_name(them) if them else "")
        tv = f" on {g['tv']}" if g.get("tv") else ""
        lines.append(f"{_name(team)} {vs} {when}{tv}".replace("  ", " "))
    text = " · ".join(lines)
    ch = channel()
    switched, noticed = _tell_tvs(text, ch)
    bits = []
    if switched:
        bits.append(f"switched {switched} TV{'s' if switched != 1 else ''}")
    if noticed:
        bits.append(f"told {noticed} TV{'s' if noticed != 1 else ''}")
    url, token = _ntfy()
    if url:
        ok = _push(url, token, "Game time!", text + f"\nChannel {ch}.", tags="sports", watch=True)
        bits.append("sent the phone alert" if ok is True else f"phone alert failed ({ok})")
    _log(text + (" — " + ", ".join(bits) if bits else ""))


def _targets():
    ids = {x.strip() for x in (os.environ.get("GAME_TVS") or "").split(",") if x.strip()}
    return ids


def _tell_tvs(text, ch, force_switch=False):
    """Switch the chosen TVs (if that's on) and show the notice on the rest (if that's on)."""
    if not REMOTE:
        return 0, 0
    want = _targets()
    do_switch = force_switch or _on("GAME_SWITCH")
    do_notice = _on("GAME_NOTICE")
    switched = noticed = 0
    for tv in REMOTE.tvs():
        if not tv["on"]:
            continue
        has = any(c[0] == ch for c in tv.get("list") or []) and ch not in tv.get("hidden", [])
        if do_switch and has and (not want or tv["id"] in want or force_switch):
            if tv.get("ch") != ch:
                REMOTE._push(tv["id"], {"tune": ch, "why": text})
            switched += 1
        elif do_notice:
            REMOTE._push(tv["id"], {"notice": {"text": text, "tune": ch if has else ""}})
            noticed += 1
    return switched, noticed


def _final(team, g):
    url, token = _ntfy()
    if not url or not _on("GAME_FINAL"):
        return
    them, home = _opp(team, g)
    us_side = (g.get("home") if home else g.get("away")) or {}
    a, b = us_side.get("score"), (them or {}).get("score")
    res = ""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        res = "won" if a > b else ("lost" if a < b else "tied")
        text = f"{_name(team)} {res} {a:g}-{b:g} {'vs' if home else 'at'} {_name(them)}"
    else:
        text = f"Final: {g.get('short') or g.get('name')}"
    ok = _push(url, token, "Final score", text, tags="trophy" if res == "won" else "sports")
    _log(text + (" — sent to phone" if ok is True else f" — phone alert failed ({ok})"))


def _latin(s):
    return s.encode("latin-1", "ignore").decode("latin-1")


def _push(url, token, title, body, tags="", watch=False, timeout=10, priority=""):
    """Send a phone notification through ntfy (https://ntfy.sh, or your own ntfy server)."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    h = {"Title": _latin(title), "User-Agent": "KNAS42"}
    if tags:
        h["Tags"] = tags
    if priority:
        h["Priority"] = priority
    if token:
        h["Authorization"] = token if " " in token else "Bearer " + token
    base = (STATE.get("base") or BASE() or "").rstrip("/")
    if base:
        acts = [f"view, Remote, {base}/remote"]
        if watch:
            acts.insert(0, f"http, Watch on TV, {base}/api/game/watch, method=POST, clear=true")
        h["Actions"] = _latin("; ".join(acts))
    try:
        r = urllib.request.Request(url, data=body.encode("utf-8"), method="POST", headers=h)
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            resp.read()
        return True
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return "ntfy wants a sign-in token for that topic"
        return f"ntfy answered {e.code}"
    except Exception as e:
        return str(e)


def watch_now():
    """The "Watch on TV" button: put the game channel on the chosen TVs (or every TV that's on)."""
    ch = channel()
    if not REMOTE:
        return {"ok": False, "message": "Not ready yet."}
    want = _targets()
    n = 0
    for tv in REMOTE.tvs():
        if tv["on"] and (not want or tv["id"] in want):
            REMOTE._push(tv["id"], {"tune": ch, "why": "Game time!"})
            n += 1
    if not n and want:                      # none of the chosen TVs are on: use whatever is
        for tv in REMOTE.tvs():
            if tv["on"]:
                REMOTE._push(tv["id"], {"tune": ch, "why": "Game time!"})
                n += 1
    msg = f"Changed {n} TV{'s' if n != 1 else ''} to channel {ch}." if n else "No TVs are on right now."
    _log("Watch button: " + msg)
    return {"ok": bool(n), "message": msg}


def test(data):
    """Setup page buttons: send a test phone alert, or show the notice on the TVs that are on."""
    what = data.get("what") or "phone"
    if data.get("base"):
        b = str(data["base"]).strip().rstrip("/")[:200]
        if b.startswith(("http://", "https://")) and STATE.get("base") != b:
            STATE["base"] = b               # the address you use for KNAS, for the notification buttons
            _save()
    if what == "tv":
        ch = channel()
        n = 0
        if REMOTE:
            for tv in REMOTE.tvs():
                if tv["on"]:
                    has = any(c[0] == ch for c in tv.get("list") or [])
                    REMOTE._push(tv["id"], {"notice": {"text": "Test: your game starts in 10 min", "tune": ch if has else ""}})
                    n += 1
        return {"ok": bool(n), "message": f"Showed it on {n} TV{'s' if n != 1 else ''}." if n else "No TVs are on right now. Open the cable box on a TV and try again."}
    url = str(data.get("url") or "").strip()
    token = str(data.get("token") or "").strip()
    if not url:
        return {"ok": False, "message": "Type your ntfy address first."}
    ok = _push(url, token, "KNAS 42", "Test alert. Game-time alerts will look like this.", tags="tv", watch=True)
    if ok is True:
        return {"ok": True, "message": "Sent! Check your phone."}
    return {"ok": False, "message": f"Couldn't send it: {ok}"}


def status():
    with _lock:
        return {"ok": True, "on": anything_on(), "channel": channel(), "lead": _lead(), "log": list(LOG[:8])}
