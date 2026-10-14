"""Duck Season: a light-gun game where your phone is the gun.

Off until it has a channel number (DUCK_CHANNEL, setup page → Experimental). Players open /zapper
on their phones (the secure address, because the camera and motion sensors need it).

Zapper mode works like the original light guns. When you pull the trigger the TV goes black for a
moment and shows a white box where each duck is, one after another. Your phone's camera checks
whether the very middle of what it sees lit up. If you weren't pointing right at the duck, it's a
miss. There's no crosshair on the TV, so it's all aim. First you "calibrate" (shoot the target in
the middle a few times) so the phone learns how long the TV takes to flash.

Tilt mode uses the phone's motion sensors to move a crosshair instead. Easier, for little kids or
odd angles.

KNAS just passes messages between the phones and the TV over live connections, so a trigger pull
reaches the TV in a few milliseconds. The game itself (ducks, score) runs on the TV screen.
"""
import os, re, threading, time

_lock = threading.Lock()
SCREENS = []                 # the TV pages showing the game (the newest one is "the" screen)
PLAYERS = {}                 # pid -> {"sock", "name", "color", "mode", "ready"}
COLORS = ["#ff3b30", "#2f7bff", "#34c759", "#ffcc00"]
SLOT = 0.1                   # each step of the flash lasts this long (seconds); the phone uses the same number
STEPS = 4                    # black, duck 1, duck 2, black (with one duck: black, duck, black)
FLASH = {"busy_until": 0.0, "n": 0}
LAST_STATE = {}


def channel():
    v = os.environ.get("DUCK_CHANNEL", "0").strip()
    return "" if v in ("", "0") or v.lower() == "off" else v


def enabled():
    return bool(channel())


def _screen():
    return SCREENS[-1] if SCREENS else None


def _to_screen(msg):
    s = _screen()
    return bool(s and s.send(msg))


def _to_players(msg, only=None):
    for pid, p in list(PLAYERS.items()):
        if only is None or pid == only:
            p["sock"].send(msg)


def _roster():
    return [{"id": pid, "name": p["name"], "color": p["color"], "mode": p["mode"], "ready": p["ready"]}
            for pid, p in sorted(PLAYERS.items())]


def _tell_roster():
    _to_screen({"t": "players", "list": _roster()})
    _to_players({"t": "players", "list": _roster(), "screen": bool(SCREENS)})


def run_screen(sock):
    """The TV page. It runs the game and does the flashing."""
    with _lock:
        SCREENS.append(sock)
    sock.send({"t": "hello", "slot": SLOT, "steps": STEPS})
    _tell_roster()
    try:
        while True:
            m = sock.recv_json(timeout=40)
            t = m.get("t")
            if t == "state":                       # score, shells, round: passed on to every phone
                LAST_STATE.clear()
                LAST_STATE.update({k: m.get(k) for k in ("phase", "round", "scores", "shells", "hits", "msg", "need")})
                _to_players(dict(LAST_STATE, t="state"))
            elif t == "outcome":                   # hit or miss, for the phone that fired
                pid = str(m.get("pid", ""))
                if pid in PLAYERS:
                    PLAYERS[pid]["sock"].send({"t": "outcome", "shot": m.get("shot"), "hit": bool(m.get("hit"))})
    except Exception:
        pass
    finally:
        with _lock:
            if sock in SCREENS:
                SCREENS.remove(sock)
        _tell_roster()


def _schedule_flash(pid, kind, shot):
    """Line flashes up one after another, so two players firing at once both get a clean flash."""
    now = time.monotonic()
    with _lock:
        start = max(now, FLASH["busy_until"])
        FLASH["busy_until"] = start + SLOT * STEPS + 0.06
    delay = start - now

    def fire():
        _to_screen({"t": "flash", "pid": pid, "kind": kind, "shot": shot})
    if delay < 0.004:
        fire()
    else:
        threading.Timer(delay, fire).start()
    return delay


def run_player(sock, name, mode):
    """One phone: its trigger, its aim, its results."""
    with _lock:
        if len(PLAYERS) >= 4:
            sock.send({"t": "full"})
            return
        used = {p["color"] for p in PLAYERS.values()}
        pid = next(str(i + 1) for i in range(4) if str(i + 1) not in PLAYERS)
        color = next(c for c in COLORS if c not in used)
        PLAYERS[pid] = {"sock": sock, "name": re.sub(r"[^\w .'-]", "", name or "")[:14].strip() or f"P{pid}", "color": color,
                        "mode": "tilt" if mode == "tilt" else "zapper", "ready": mode == "tilt"}
    sock.send({"t": "welcome", "pid": pid, "color": color, "slot": SLOT, "steps": STEPS, "screen": bool(SCREENS)})
    if LAST_STATE:
        sock.send(dict(LAST_STATE, t="state"))
    _tell_roster()
    try:
        while True:
            m = sock.recv_json(timeout=40)
            t = m.get("t")
            p = PLAYERS[pid]
            if t == "shot":                    # zapper trigger (or a calibration shot)
                if not SCREENS:
                    sock.send({"t": "noscreen"})
                    continue
                kind = "cal" if m.get("cal") else "shot"
                shot = str(m.get("shot", ""))[:20]
                delay = _schedule_flash(pid, kind, shot)
                sock.send({"t": "shotok", "shot": shot, "delay": round(delay * 1000)})
            elif t == "result":                # what the phone's camera saw during the flash
                hits = [bool(x) for x in (m.get("hits") or [])][:2]
                _to_screen({"t": "result", "pid": pid, "shot": str(m.get("shot", ""))[:20], "hits": hits, "aimed": bool(m.get("aimed"))})
            elif t == "calibrated":
                p["ready"] = True
                p["latency"] = int(m.get("latency") or 0)
                _tell_roster()
            elif t == "aim":                   # tilt mode: where the crosshair is (0-1)
                _to_screen({"t": "aim", "pid": pid, "x": float(m.get("x", .5)), "y": float(m.get("y", .5))})
            elif t == "tshot":                 # tilt mode trigger
                _to_screen({"t": "tshot", "pid": pid, "x": float(m.get("x", .5)), "y": float(m.get("y", .5))})
            elif t == "mode":
                p["mode"] = "tilt" if m.get("mode") == "tilt" else "zapper"
                p["ready"] = p["mode"] == "tilt" or bool(m.get("ready"))
                _tell_roster()
            elif t == "name":
                p["name"] = re.sub(r"[^\w .'-]", "", str(m.get("name") or ""))[:14].strip() or p["name"]
                _tell_roster()
            elif t in ("start", "again", "pause"):
                _to_screen({"t": t, "pid": pid})
    except Exception:
        pass
    finally:
        with _lock:
            if PLAYERS.get(pid, {}).get("sock") is sock:
                PLAYERS.pop(pid, None)
        _tell_roster()


def status():
    return {"ok": True, "on": enabled(), "channel": channel(), "players": _roster(), "screen": bool(SCREENS)}
