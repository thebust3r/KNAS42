"""Flick games: darts, hoops, bowling and cup pong. Flick on your phone and it flies on the TV.

Off until it has a channel number (FLICK_CHANNEL, setup page → Experimental → Phone extras). Players open
/flick on their phones (the normal address is fine: flicking only needs the touch screen). The first one
in picks the game. Players take turns; how hard and which way you flick decide the throw.

KNAS just passes messages between the phones and the TV over live connections. The games themselves
(the physics, the scores) run on the TV screen.
"""
import os, re, threading

_lock = threading.Lock()
SCREENS = []
PLAYERS = {}
COLORS = ["#ff3b30", "#2f7bff", "#34c759", "#ffcc00", "#ff5ad8", "#36d1ff"]
LAST = {}
GAMES = ("darts", "hoops", "bowling", "pong")


def channel():
    v = os.environ.get("FLICK_CHANNEL", "0").strip()
    return "" if v in ("", "0") or v.lower() == "off" else v


def enabled():
    return bool(channel())


def _screen():
    return SCREENS[-1] if SCREENS else None


def _to_screen(msg):
    s = _screen()
    return bool(s and s.send(msg))


def _to_players(msg):
    for p in list(PLAYERS.values()):
        p["sock"].send(msg)


def _roster():
    ids = sorted(PLAYERS, key=lambda k: PLAYERS[k]["n"])
    return [{"id": i, "name": PLAYERS[i]["name"], "color": PLAYERS[i]["color"], "host": n == 0} for n, i in enumerate(ids)]


def _tell_roster():
    r = _roster()
    _to_screen({"t": "players", "list": r})
    _to_players({"t": "players", "list": r, "screen": bool(SCREENS)})


def run_screen(sock):
    with _lock:
        SCREENS.append(sock)
    _tell_roster()
    try:
        while True:
            m = sock.recv_json(timeout=40)
            if m.get("t") == "state":
                LAST.clear()
                LAST.update({k: m.get(k) for k in ("phase", "game", "turn", "msg", "scores", "left", "round", "rounds")})
                _to_players(dict(LAST, t="state"))
            elif m.get("t") == "result":           # how a throw went, for the phone that threw it
                p = PLAYERS.get(str(m.get("pid", "")))
                if p:
                    p["sock"].send({"t": "result", "text": str(m.get("text", ""))[:60], "good": bool(m.get("good"))})
    except Exception:
        pass
    finally:
        with _lock:
            if sock in SCREENS:
                SCREENS.remove(sock)
        _tell_roster()


_n = [0]


def run_player(sock, name):
    with _lock:
        if len(PLAYERS) >= 6:
            sock.send({"t": "full"})
            return
        used = {p["color"] for p in PLAYERS.values()}
        pid = next(str(i + 1) for i in range(6) if str(i + 1) not in PLAYERS)
        _n[0] += 1
        PLAYERS[pid] = {"sock": sock, "name": re.sub(r"[^\w .'-]", "", name or "")[:14].strip() or f"Player {pid}",
                        "color": next(c for c in COLORS if c not in used), "n": _n[0]}
    sock.send({"t": "welcome", "pid": pid, "color": PLAYERS[pid]["color"], "screen": bool(SCREENS)})
    if LAST:
        sock.send(dict(LAST, t="state"))
    _tell_roster()
    try:
        while True:
            m = sock.recv_json(timeout=40)
            t = m.get("t")
            if t == "throw":
                def num(k, lo, hi):
                    try:
                        return max(lo, min(hi, float(m.get(k, 0))))
                    except (TypeError, ValueError):
                        return 0.0
                _to_screen({"t": "throw", "pid": pid, "ang": num("ang", -1.2, 1.2), "pow": num("pow", 0, 3), "curve": num("curve", -1, 1)})
            elif t == "pick" and m.get("game") in GAMES:
                if _roster() and _roster()[0]["id"] == pid:
                    _to_screen({"t": "pick", "game": m["game"], "pid": pid})
            elif t in ("start", "again", "lobby"):
                _to_screen({"t": t, "pid": pid, "host": bool(_roster() and _roster()[0]["id"] == pid)})
            elif t == "name":
                PLAYERS[pid]["name"] = re.sub(r"[^\w .'-]", "", str(m.get("name") or ""))[:14].strip() or PLAYERS[pid]["name"]
                _tell_roster()
    except Exception:
        pass
    finally:
        with _lock:
            if PLAYERS.get(pid, {}).get("sock") is sock:
                PLAYERS.pop(pid, None)
        _tell_roster()


def status():
    return {"ok": True, "on": enabled(), "channel": channel(), "players": _roster(), "screen": bool(SCREENS)}
