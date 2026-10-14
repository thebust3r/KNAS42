"""Severe weather alerts, emergency-broadcast style (US only, from the National Weather Service).

Off until you turn it on: WEATHER_ALERTS=on (setup page → Weather → Severe weather alerts). When the NWS
issues a warning for where you live, every TV with the cable box open shows the classic red crawl over
whatever is on, with the attention tones if you want them, and a small "⚠ Tornado Warning" tag stays in the
corner until it expires. It can also send a phone alert through ntfy (the same one the Game time alerts use).

WEATHER_ALERT_LEVEL: warnings (default: tornado, severe thunderstorm, flash flood...), watches (adds watches),
                     all (adds advisories like wind or frost).
WEATHER_ALERT_TONES: on/off     WEATHER_ALERT_PHONE: on/off
"""
import json, os, threading, time, urllib.parse, urllib.request
from datetime import datetime

import clock

DATA = ""
WHERE = lambda: ("", "")             # set by server.py: (lat, lon)
PUSH = None                          # gametime._push, for phone alerts
ACTIVE = []                          # alerts in effect right now
STATE = {"checked": 0, "error": "", "sent": {}}
TEST = {"until": 0, "alert": None}
_lock = threading.Lock()
TICK = 60


def _on(k, default="off"):
    return os.environ.get(k, default).strip().lower() in ("on", "yes", "1", "true")


def enabled():
    return _on("WEATHER_ALERTS")


def _level():
    v = os.environ.get("WEATHER_ALERT_LEVEL", "warnings").strip().lower()
    return v if v in ("warnings", "watches", "all") else "warnings"


def setup(data_dir, where, push=None):
    global DATA, WHERE, PUSH
    DATA, WHERE, PUSH = data_dir, where, push
    try:
        with open(os.path.join(DATA, "alerts.json")) as f:
            STATE["sent"] = json.load(f).get("sent", {})
    except (OSError, ValueError):
        pass
    threading.Thread(target=_loop, daemon=True, name="weather-alerts").start()


def _save():
    try:
        cut = time.time() - 7 * 86400
        STATE["sent"] = {k: v for k, v in STATE["sent"].items() if v > cut}
        with open(os.path.join(DATA, "alerts.json"), "w") as f:
            json.dump({"sent": STATE["sent"]}, f)
    except OSError:
        pass


def _wanted(severity, event):
    """Which alerts to show for the chosen level."""
    e = event.lower()
    lv = _level()
    if lv == "all":
        return True
    if "warning" in e or "emergency" in e or severity == "Extreme":
        return True
    return lv == "watches" and "watch" in e


def _ts(s):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


def _fetch():
    lat, lon = WHERE()
    if not lat or not lon:
        raise RuntimeError("KNAS doesn't know where you are yet (set your town on the setup page)")
    q = urllib.parse.urlencode({"point": f"{float(lat):.4f},{float(lon):.4f}"})
    r = urllib.request.Request("https://api.weather.gov/alerts/active?" + q,
                               headers={"User-Agent": "KNAS42 retro TV (github.com/thebust3r/KNAS42)", "Accept": "application/geo+json"})
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            j = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):
            raise RuntimeError("the National Weather Service only covers the US")
        raise
    out = []
    now = time.time()
    for f in j.get("features") or []:
        p = f.get("properties") or {}
        event = p.get("event") or "Weather Alert"
        if p.get("status") not in (None, "Actual") or p.get("messageType") == "Cancel":
            continue
        if not _wanted(p.get("severity") or "", event):
            continue
        ends = _ts(p.get("ends") or p.get("expires") or "")
        if ends and ends < now:
            continue
        desc = " ".join((p.get("description") or "").split())
        instr = " ".join((p.get("instruction") or "").split())
        out.append({"id": p.get("id") or f.get("id") or event, "event": event, "headline": p.get("headline") or event,
                    "severity": p.get("severity") or "", "urgency": p.get("urgency") or "",
                    "area": p.get("areaDesc") or "", "ends": ends, "sender": p.get("senderName") or "National Weather Service",
                    "text": (desc + (" " + instr if instr else ""))[:900]})
    rank = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3}
    out.sort(key=lambda a: (rank.get(a["severity"], 4), -a["ends"]))
    return out


def check():
    found = _fetch()
    with _lock:
        ACTIVE[:] = found
        STATE.update(checked=time.time(), error="")
    fresh = [a for a in found if a["id"] not in STATE["sent"]]
    for a in fresh:
        STATE["sent"][a["id"]] = time.time()
        print(f"[weather alert] {a['headline']}", flush=True)
        url = (os.environ.get("NTFY_URL") or "").strip()
        if PUSH and url and _on("WEATHER_ALERT_PHONE", "on"):
            until = clock.local_dt(a["ends"]).strftime("%I:%M %p").lstrip("0") if a["ends"] else ""
            body = a["headline"] if not until or until in a["headline"] else f"{a['headline']} (until {until})"
            PUSH(url, (os.environ.get("NTFY_TOKEN") or "").strip(), a["event"], body + "\n" + a["text"][:300],
                 tags="warning,rotating_light", priority="5" if "warning" in a["event"].lower() else "4")
    if fresh:
        _save()


def _loop():
    time.sleep(15)
    while True:
        if enabled():
            try:
                check()
            except RuntimeError as e:
                STATE["error"] = str(e)[:1].upper() + str(e)[1:] + "."
            except Exception as e:
                STATE["error"] = f"Couldn't reach the National Weather Service ({e}). KNAS keeps trying every minute."
                print("[weather alert]", e, flush=True)
        time.sleep(TICK)


def active():
    """What the TVs show. Includes the test alert while one is running."""
    out = list(ACTIVE) if enabled() else []
    if TEST["alert"] and time.time() < TEST["until"]:
        out.insert(0, TEST["alert"])
    return {"ok": True, "on": enabled(), "alerts": out, "tones": _on("WEATHER_ALERT_TONES", "on")}


def test():
    t = time.time()
    TEST.update(until=t + 120, alert={"id": f"test-{int(t)}", "event": "Test Alert", "headline": "This is a test of the KNAS emergency alert crawl",
                                       "severity": "Minor", "area": "Your living room", "ends": t + 120, "sender": "KNAS 42",
                                       "text": "This is only a test. If this had been an actual emergency, the National Weather Service warning for your area would appear here, with what to do. This concludes this test.",
                                       "test": True})
    return {"ok": True, "message": "Every TV with the cable box open shows it within 30 seconds."}


def status():
    return {"ok": True, "on": enabled(), "level": _level(), "checked": STATE["checked"], "error": STATE["error"],
            "active": [{"event": a["event"], "headline": a["headline"]} for a in ACTIVE]}
