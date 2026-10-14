"""Phone remote: control any TV that has the KNAS cable box open, from a phone at /remote.

Every open cable box checks in here (what channel it's on, which channels it has) and waits for
button presses. The remote page lists the TVs and sends presses to the one you pick. Each TV also
has its own channel list (hide channels on one TV only), saved here so it survives a browser reset.
"""
import json, os, re, threading, time

DATA = ""
TVS = {}                 # id -> live state (only while the TV is open)
PREFS = {}               # id -> {"name": ..., "hidden": [...]}, saved to data/remote-tvs.json
_lock = threading.Lock()
ACTIVE_SECONDS = 40      # a TV that hasn't checked in for this long is shown as off (it checks in every ~25 s)
KEYS = {"up", "down", "left", "right", "ok", "back", "guide", "info", "volup", "voldown", "mute", "degauss"} | {f"d{i}" for i in range(10)}


def setup(data_dir):
    global DATA
    DATA = data_dir
    try:
        with open(os.path.join(DATA, "remote-tvs.json")) as f:
            # keep TVs you named or customized; plain unnamed ones come back on their own when they're on
            PREFS.update({k: v for k, v in json.load(f).items() if isinstance(v, dict) and (v.get("name") or v.get("hidden"))})
    except (OSError, ValueError):
        pass


def _save():
    try:
        tmp = os.path.join(DATA, "remote-tvs.json.tmp")
        with open(tmp, "w") as f:
            json.dump(PREFS, f, indent=1)
        os.replace(tmp, os.path.join(DATA, "remote-tvs.json"))
    except OSError:
        pass


def _clean_id(i):
    i = str(i or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,40}", i):
        raise ValueError("bad TV id")
    return i


def _tv(i):
    t = TVS.get(i)
    if not t:
        t = TVS[i] = {"cv": threading.Condition(_lock), "queue": [], "seen": 0, "status": {}, "list": []}
    return t


def _prefs(i):
    p = PREFS.get(i) or {}
    return {"name": p.get("name", ""), "hidden": list(p.get("hidden", []))}


def hello(data):
    """A cable box checking in. Returns this TV's name and its hidden channels."""
    i = _clean_id(data.get("id"))
    with _lock:
        t = _tv(i)
        t["seen"] = time.time()
        t["status"] = {k: str(data.get(k, ""))[:120] for k in ("ch", "chname", "show", "kind", "guess", "asp", "vol", "muted", "asleep")}
        if isinstance(data.get("list"), list):
            t["list"] = [[str(c[0])[:12], str(c[1])[:60]] for c in data["list"][:400] if isinstance(c, (list, tuple)) and len(c) >= 2]
        if i not in PREFS:
            PREFS[i] = {"name": "", "hidden": []}
            _save()
        return _prefs(i)


def wait(i, timeout=25):
    """Long poll: hand the TV any button presses, waiting up to `timeout` seconds for one."""
    i = _clean_id(i)
    end = time.time() + timeout
    with _lock:
        t = _tv(i)
        t["seen"] = time.time()
        while not t["queue"]:
            left = end - time.time()
            if left <= 0:
                break
            t["cv"].wait(left)
        out, t["queue"] = t["queue"], []
        t["seen"] = time.time()
        return out


def _push(i, cmd):
    with _lock:
        t = _tv(i)
        t["queue"].append(cmd)
        t["queue"] = t["queue"][-20:]
        t["cv"].notify_all()


def send(data):
    i = _clean_id(data.get("id"))
    if data.get("key") in KEYS:
        _push(i, {"k": data["key"]})
    elif data.get("tune"):
        _push(i, {"tune": str(data["tune"])[:12]})
    elif "vol" in data:                # the volume slider: an exact level, 0-100
        try:
            v = max(0, min(100, int(float(data["vol"]))))
        except (TypeError, ValueError):
            raise ValueError("Bad volume.")
        _push(i, {"vol": v})
        with _lock:
            t = TVS.get(i)
            if t:
                t["status"]["vol"], t["status"]["muted"] = str(v), ""
    else:
        raise ValueError("Unknown button.")
    return {"ok": True}


def watching(me=""):
    """How many TVs are on each channel right now (not counting the one asking): the guide's 👁 numbers."""
    out = {}
    for t in tvs():
        if t["on"] and not t["asleep"] and t["id"] != me and t["ch"]:
            out[t["ch"]] = out.get(t["ch"], 0) + 1
    return out


def sleep_all():
    """All TVs off: every TV that's on goes to a good-night screen with the sound off. Any button wakes it."""
    on = [t["id"] for t in tvs() if t["on"]]
    for i in on:
        _push(i, {"sleep": 1})
    return {"ok": True, "tvs": len(on), "message": f"Good night! Turned off {len(on)} TV{'s' if len(on) != 1 else ''}." if on else "No TVs are on."}


def set_prefs(data):
    i = _clean_id(data.get("id"))
    with _lock:
        p = PREFS.setdefault(i, {"name": "", "hidden": []})
        if "name" in data:
            p["name"] = re.sub(r"\s+", " ", str(data["name"] or "")).strip()[:40]
        if "hidden" in data and isinstance(data["hidden"], list):
            p["hidden"] = sorted({str(x)[:12] for x in data["hidden"]})[:400]
        _save()
    _push(i, {"prefs": 1})            # the TV picks up the change right away
    return {"ok": True, "tvs": tvs()}


def forget(data):
    i = _clean_id(data.get("id"))
    with _lock:
        PREFS.pop(i, None)
        TVS.pop(i, None)
        _save()
    return {"ok": True, "tvs": tvs()}


def bye(data):
    """The cable box page is closing: show that TV as off straight away."""
    i = _clean_id(data.get("id"))
    with _lock:
        t = TVS.get(i)
        if t:
            t["seen"] = 0
    return {"ok": True}


def tvs():
    now = time.time()
    with _lock:
        out = []
        for i in set(TVS) | set(PREFS):
            t = TVS.get(i) or {}
            p = _prefs(i)
            on = now - t.get("seen", 0) < ACTIVE_SECONDS
            st = t.get("status", {})
            if not on and not p["name"] and not p["hidden"]:
                continue                  # an unnamed TV that's off: nothing to show until it's on again
            out.append({"id": i, "name": p["name"] or st.get("guess") or "TV", "named": bool(p["name"]), "on": on,
                        "ch": st.get("ch", ""), "chname": st.get("chname", ""), "show": st.get("show", ""),
                        "list": t.get("list", []), "hidden": p["hidden"], "seen": int(t.get("seen", 0)), "asp": st.get("asp", ""),
                        "vol": st.get("vol", ""), "muted": st.get("muted", "") in ("1", "true", "True"), "asleep": st.get("asleep", "") in ("1", "true", "True")})
        out.sort(key=lambda x: (not x["on"], x["name"].lower(), -x["seen"]))
        count = {}
        for x in out:                     # two "Fire TV"s become "Fire TV" and "Fire TV 2" until you name them
            count[x["name"]] = count.get(x["name"], 0) + 1
            if count[x["name"]] > 1 and not x["named"]:
                x["name"] = f"{x['name']} {count[x['name']]}"
        return out
