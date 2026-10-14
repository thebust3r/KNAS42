"""Screen fun: things you fling at the TV from your phone, on top of whatever's playing.

Off until you turn it on (SCREEN_FUN=on, setup page → Experimental → Phone extras). The phone page is /fun.
  🍅 Splat: flick a tomato, a pie, a snowball or an egg at the screen. It splats where you aimed and slides off.
  🎉 Party: shake your phone (or tap) for confetti; the more phones shaking at once, the bigger it gets.
          Tap an emoji and it floats up the screen.
  ✏️ Draw: draw on your phone and the lines show up over the picture, like a football telestrator.
"""
import os, re, time

REMOTE = None
ITEMS = ("tomato", "pie", "snow", "egg")
EMOJI = ("😂", "🔥", "😱", "👏", "❤️", "💀", "🏈", "🎉", "😍", "🤮", "👀", "🍿")
COLORS = ("#ffd23a", "#ff3b30", "#ffffff", "#36d1ff", "#7dff6a", "#ff5ad8")
_last = {}


def enabled():
    return os.environ.get("SCREEN_FUN", "off").strip().lower() in ("on", "yes", "1", "true")


def setup(remote):
    global REMOTE
    REMOTE = remote


def _num(v, lo=0.0, hi=1.0):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return (lo + hi) / 2


def _targets(tvs):
    on = [t["id"] for t in REMOTE.tvs() if t["on"]]
    if not isinstance(tvs, list) or not tvs:
        return on
    return [t for t in tvs if t in on]


def send(data, who=""):
    if not enabled():
        return {"ok": False, "message": "Screen fun is off (setup page → Experimental → Phone extras)."}
    k = data.get("k")
    # a little breathing room so one phone can't flood the TVs
    now = time.time()
    key = (who, k)
    gap = {"ink": 0, "splat": 0.25, "confetti": 0.3, "emoji": 0.12, "clear": 0.2}.get(k, 0.2)
    if now - _last.get(key, 0) < gap:
        return {"ok": True, "skipped": True}
    _last[key] = now
    if k == "splat":
        item = data.get("item") if data.get("item") in ITEMS else "tomato"
        fx = {"k": "splat", "item": item, "x": round(_num(data.get("x")), 4), "y": round(_num(data.get("y")), 4)}
    elif k == "confetti":
        fx = {"k": "confetti", "n": int(_num(data.get("n", 1), 1, 3))}
    elif k == "emoji":
        if data.get("e") not in EMOJI:
            raise ValueError("Pick one of the emojis.")
        fx = {"k": "emoji", "e": data["e"], "x": round(_num(data.get("x", 0.5)), 3)}
    elif k == "ink":
        pts = data.get("pts") if isinstance(data.get("pts"), list) else []
        pts = [[round(_num(p[0]), 4), round(_num(p[1]), 4)] + ([int(_num(p[2], 0, 600000))] if len(p) > 2 else [])
               for p in pts[:120] if isinstance(p, (list, tuple)) and len(p) in (2, 3)]
        if not pts:
            return {"ok": True}
        fx = {"k": "ink", "id": re.sub(r"[^\w-]", "", str(data.get("id", "")))[:24], "c": data.get("c") if data.get("c") in COLORS else COLORS[0],
              "w": int(_num(data.get("w", 2), 1, 4)), "pts": pts}
    elif k == "clear":
        fx = {"k": "clear"}
    else:
        raise ValueError("Unknown.")
    tvs = _targets(data.get("tvs"))
    for t in tvs:
        REMOTE._push(t, {"fx": fx})
    return {"ok": True, "tvs": len(tvs)}
