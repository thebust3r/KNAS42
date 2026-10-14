"""Viewing history: what each TV watched, and for how long.

Every open cable box checks in when it changes channel and every ~25 seconds (see remote.py). This turns
those check-ins into watch sessions (TV, channel, show, start, length) in a small SQLite file in data/.
Channel flips shorter than a minute aren't sessions; they're counted as flips. Turn it off with
VIEW_HISTORY=off (setup page → Channels → Viewing history).
"""
import os, sqlite3, threading, time
from datetime import datetime

import clock
_dt = clock.local_dt          # local time: the container's clock is UTC

DB = ""
_lock = threading.Lock()
CUR = {}                      # tv id -> open session {ch, chname, show, start, last, name}
MIN_SECONDS = 60              # shorter than this is flipping, not watching
GAP = 90                      # no check-in for this long: the TV was off
RESUME = 300                  # after a restart, a TV that checks in within this long carries on its session
KEEP_DAYS = 400


def enabled():
    return os.environ.get("VIEW_HISTORY", "on").strip().lower() not in ("off", "no", "0", "false")


def setup(data_dir):
    global DB
    DB = os.path.join(data_dir, "history.db")
    with _db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS views (id INTEGER PRIMARY KEY, tv TEXT, tvname TEXT, ch TEXT, chname TEXT,
                     show TEXT, start REAL, end REAL, secs INTEGER)""")
        c.execute("CREATE INDEX IF NOT EXISTS views_start ON views(start)")
        c.execute("CREATE TABLE IF NOT EXISTS flips (tv TEXT, day TEXT, n INTEGER, PRIMARY KEY (tv, day))")
        c.execute("DELETE FROM views WHERE start < ?", (time.time() - KEEP_DAYS * 86400,))
        # pick up sessions that were still going when KNAS restarted (an update, say), so they carry on
        now = time.time()
        for r in c.execute("SELECT * FROM views WHERE end > ? ORDER BY end", (now - RESUME,)):
            CUR[r["tv"]] = {"id": r["id"], "ch": r["ch"], "chname": r["chname"], "show": r["show"], "start": r["start"],
                            "last": r["end"], "name": r["tvname"], "resumed": True}
    threading.Thread(target=_sweep, daemon=True, name="history").start()


def _db():
    c = sqlite3.connect(DB, timeout=10)
    c.row_factory = sqlite3.Row
    return c


# Sessions are written to the database as they happen (and updated with every check-in), so nothing is
# lost if KNAS restarts in the middle of a show. One shorter than a minute is removed and counted as a flip.

def _open(tv, s):
    with _db() as c:
        cur = c.execute("INSERT INTO views (tv, tvname, ch, chname, show, start, end, secs) VALUES (?,?,?,?,?,?,?,0)",
                        (tv, s["name"], s["ch"], s["chname"], s["show"], s["start"], s["start"]))
        s["id"] = cur.lastrowid


def _touch(s):
    with _db() as c:
        c.execute("UPDATE views SET end = ?, secs = ?, tvname = ? WHERE id = ?",
                  (s["last"], int(s["last"] - s["start"]), s["name"], s["id"]))


def _close(tv, s, end=None):
    end = end or s["last"]
    secs = int(end - s["start"])
    with _db() as c:
        if secs >= MIN_SECONDS:
            c.execute("UPDATE views SET end = ?, secs = ? WHERE id = ?", (end, secs, s.get("id")))
        else:
            c.execute("DELETE FROM views WHERE id = ?", (s.get("id"),))
            day = _dt(s["start"]).strftime("%Y-%m-%d")
            c.execute("INSERT INTO flips (tv, day, n) VALUES (?,?,1) ON CONFLICT(tv, day) DO UPDATE SET n = n + 1", (tv, day))


def record(tv, name, ch, chname, show, now=None):
    """A TV checked in. Extends its current session, or ends it and starts a new one."""
    if not enabled() or not DB or not ch:
        return
    now = now or time.time()
    with _lock:
        s = CUR.get(tv)
        gap = GAP if not s or not s.get("resumed") else RESUME
        if s and s["ch"] == ch and s["show"] == show and now - s["last"] < max(GAP, gap):
            s["last"] = now
            s["name"] = name or s["name"]
            s.pop("resumed", None)
            _touch(s)
            return
        if s:
            # changed channel (or the show changed): the old one ran until now, unless the TV had been off
            _close(tv, s, now if now - s["last"] < GAP else s["last"])
        CUR[tv] = {"ch": ch, "chname": chname, "show": show, "start": now, "last": now, "name": name}
        _open(tv, CUR[tv])


def off(tv, now=None):
    """The TV's page closed."""
    with _lock:
        s = CUR.pop(tv, None)
        if s:
            _close(tv, s, now or time.time())


def _sweep():
    while True:
        time.sleep(30)
        now = time.time()
        with _lock:
            for tv in [t for t, s in CUR.items() if now - s["last"] > (RESUME if s.get("resumed") else GAP)]:
                _close(tv, CUR.pop(tv))


def clear():
    with _lock:
        CUR.clear()
        with _db() as c:
            c.execute("DELETE FROM views")
            c.execute("DELETE FROM flips")
    return {"ok": True}


def ratings(names=None):
    """KNAS Ratings: this week's channels and shows ranked by hours watched, with last week's rank for the arrows."""
    now = time.time()
    with _db() as c:
        rows = [dict(r) for r in c.execute("SELECT ch, chname, show, secs, start, tv FROM views WHERE start >= ? AND secs >= ?", (now - 14 * 86400, MIN_SECONDS))]
    week = [r for r in rows if r["start"] >= now - 7 * 86400]
    prev = [r for r in rows if r["start"] < now - 7 * 86400]

    def rank(rs, key):
        d = {}
        for r in rs:
            k = r[key] if key == "ch" else (r["show"], r["chname"])
            if not k or (key == "show" and not r["show"]):
                continue
            x = d.setdefault(k, {"secs": 0, "tvs": set(), "name": r["chname"], "show": r["show"], "ch": r["ch"]})
            x["secs"] += r["secs"]
            x["tvs"].add(r["tv"])
        return sorted(d.items(), key=lambda kv: -kv[1]["secs"])
    total = sum(r["secs"] for r in week) or 1
    last = {k: i + 1 for i, (k, _) in enumerate(rank(prev, "ch"))}
    chans = [{"rank": i + 1, "ch": v["ch"], "name": v["name"], "hours": round(v["secs"] / 3600, 1), "share": round(v["secs"] * 100 / total),
              "tvs": len(v["tvs"]), "last": last.get(k)} for i, (k, v) in enumerate(rank(week, "ch")[:10])]
    lasts = {k: i + 1 for i, (k, _) in enumerate(rank(prev, "show"))}
    shows = [{"rank": i + 1, "show": v["show"], "ch": v["name"], "hours": round(v["secs"] / 3600, 1), "last": lasts.get(k)}
             for i, (k, v) in enumerate(rank(week, "show")[:10])]
    return {"ok": True, "enabled": enabled(), "hours": round(sum(r["secs"] for r in week) / 3600, 1), "channels": chans, "shows": shows,
            "from": now - 7 * 86400, "to": now}


def summary(days=7, tv="", names=None):
    """Everything the history page shows. days=0 means all time."""
    names = names or {}
    since = 0 if not days else time.time() - days * 86400
    where, args = "WHERE start >= ?", [since]
    if tv:
        where += " AND tv = ?"
        args.append(tv)
    now = time.time()
    with _lock:                       # what's on right now (already in the database, still growing)
        live = {s["id"] for s in CUR.values() if s.get("id") and now - s["last"] < GAP}
    with _db() as c:
        rows = [dict(r) for r in c.execute(f"SELECT * FROM views {where} AND secs >= ? ORDER BY start DESC", args + [MIN_SECONDS])]
        for r in rows:
            r["live"] = r["id"] in live
        fargs = [_dt(since).strftime("%Y-%m-%d") if since else "0000"] + ([tv] if tv else [])
        flips = [dict(r) for r in c.execute("SELECT tv, day, n FROM flips WHERE day >= ?" + (" AND tv = ?" if tv else ""), fargs)]

    def nm(t, fallback):
        return names.get(t) or fallback or "TV"
    total = sum(r["secs"] for r in rows)
    by_ch, by_show, by_tv, by_hour, by_day = {}, {}, {}, [0] * 24, {}
    for r in rows:
        k = r["ch"]
        x = by_ch.setdefault(k, {"ch": r["ch"], "name": r["chname"], "secs": 0})
        x["secs"] += r["secs"]
        if r["show"]:
            y = by_show.setdefault((r["show"], r["chname"]), {"show": r["show"], "ch": r["chname"], "secs": 0, "times": 0})
            y["secs"] += r["secs"]
            y["times"] += 1
        z = by_tv.setdefault(r["tv"], {"tv": r["tv"], "name": nm(r["tv"], r["tvname"]), "secs": 0})
        z["secs"] += r["secs"]
        # spread each session over the hours it covered
        t, end = r["start"], r["start"] + r["secs"]
        while t < end:
            h = _dt(t)
            step = min(end, t + (3600 - h.minute * 60 - h.second)) - t
            by_hour[h.hour] += step
            t += max(step, 1)
        d = _dt(r["start"]).strftime("%Y-%m-%d")
        by_day[d] = by_day.get(d, 0) + r["secs"]
    longest = max(rows, key=lambda r: r["secs"], default=None)
    flip_days = {}
    for f in flips:
        flip_days[f["day"]] = flip_days.get(f["day"], 0) + f["n"]
    most_flips = max(flip_days.items(), key=lambda x: x[1], default=None)
    busiest = max(by_day.items(), key=lambda x: x[1], default=None)
    recent = [{"tv": nm(r["tv"], r["tvname"]), "ch": r["ch"], "chname": r["chname"], "show": r["show"],
               "start": r["start"], "secs": r["secs"], "live": bool(r.get("live"))} for r in rows[:60]]
    return {"enabled": enabled(), "days": days, "total": total, "sessions": len(rows),
            "flips": sum(flip_days.values()),
            "channels": sorted(by_ch.values(), key=lambda x: -x["secs"])[:12],
            "shows": sorted(by_show.values(), key=lambda x: -x["secs"])[:12],
            "tvs": sorted(by_tv.values(), key=lambda x: -x["secs"]),
            "hours": [int(h) for h in by_hour], "recent": recent,
            "longest": {"show": longest["show"], "chname": longest["chname"], "secs": longest["secs"],
                        "tv": nm(longest["tv"], longest["tvname"]), "start": longest["start"]} if longest else None,
            "most_flips": {"day": most_flips[0], "n": most_flips[1]} if most_flips else None,
            "busiest": {"day": busiest[0], "secs": busiest[1]} if busiest else None}


# ---------------------------------------------------------------- KNAS Wrapped: the year in review

def years():
    with _db() as c:
        r = c.execute("SELECT MIN(start), MAX(start) FROM views").fetchone()
    if not r or not r[0]:
        return [clock.local_now().year]
    return list(range(_dt(r[1]).year, _dt(r[0]).year - 1, -1))


def wrapped(year=0, tv="", names=None, channels=None):
    """Everything the Wrapped slideshow shows. year=0 means all time. channels: {"sports": "43", ...}"""
    names, channels = names or {}, channels or {}
    if year:
        a, b = clock.local_midnight_ts(year), clock.local_midnight_ts(year + 1)
    else:
        a, b = 0, time.time() + 86400
    where, args = "WHERE start >= ? AND start < ?", [a, b]
    if tv:
        where += " AND tv = ?"
        args.append(tv)
    with _db() as c:
        rows = [dict(r) for r in c.execute(f"SELECT * FROM views {where} AND secs >= {MIN_SECONDS} ORDER BY start", args)]
        fl = c.execute("SELECT COALESCE(SUM(n),0) FROM flips WHERE day >= ? AND day < ?" + (" AND tv = ?" if tv else ""),
                       [_dt(a).strftime("%Y-%m-%d") if a else "0000",
                        _dt(b).strftime("%Y-%m-%d")] + ([tv] if tv else [])).fetchone()[0]
    out = {"ok": True, "year": year, "tv": tv, "years": years(), "sessions": len(rows)}
    if not rows:
        return out
    total = sum(r["secs"] for r in rows)
    by_ch, by_show, by_tv, by_hour, by_wd, by_month, by_day = {}, {}, {}, [0] * 24, [0] * 7, [0] * 12, {}
    jukebox = channels.get("party", "")
    knas = {v for v in channels.values() if v and v != "0"}     # KNAS's own channels aren't "shows"
    songs = {}
    for r in rows:
        x = by_ch.setdefault(r["ch"], {"ch": r["ch"], "name": r["chname"], "secs": 0})
        x["secs"] += r["secs"]
        if r["show"] and r["ch"] not in knas:
            y = by_show.setdefault(r["show"], {"show": r["show"], "ch": r["chname"], "secs": 0})
            y["secs"] += r["secs"]
        if r["show"] and jukebox and r["ch"] == jukebox and r["show"] != r["chname"]:
            songs[r["show"]] = songs.get(r["show"], 0) + 1
        z = by_tv.setdefault(r["tv"], {"name": names.get(r["tv"]) or r["tvname"] or "TV", "secs": 0})
        z["secs"] += r["secs"]
        t, end = r["start"], r["start"] + r["secs"]
        while t < end:
            d = _dt(t)
            step = min(end, t + (3600 - d.minute * 60 - d.second)) - t
            by_hour[d.hour] += step
            by_wd[d.weekday()] += step
            by_month[d.month - 1] += step
            k = d.strftime("%Y-%m-%d")
            by_day[k] = by_day.get(k, 0) + step
            t += max(step, 1)
    # longest binge: the same show on the same TV, with breaks of 20 minutes or less
    binge, cur = None, None
    for r in sorted(rows, key=lambda r: (r["tv"], r["start"])):
        if not r["show"] or r["ch"] in knas:
            cur = None
            continue
        if cur and cur["tv"] == r["tv"] and cur["show"] == r["show"] and r["start"] - cur["end"] <= 1200:
            cur["secs"] += r["secs"]
            cur["end"] = r["start"] + r["secs"]
        else:
            cur = {"tv": r["tv"], "tvname": r["tvname"], "show": r["show"], "ch": r["chname"], "start": r["start"], "end": r["start"] + r["secs"], "secs": r["secs"]}
        if not binge or cur["secs"] > binge["secs"]:
            binge = dict(cur)
    chs = sorted(by_ch.values(), key=lambda x: -x["secs"])
    shows = sorted(by_show.values(), key=lambda x: -x["secs"])
    tvs = sorted(by_tv.values(), key=lambda x: -x["secs"])
    peak = max(range(24), key=lambda h: by_hour[h])
    busiest = max(by_day.items(), key=lambda x: x[1])
    night = sum(by_hour[h] for h in (22, 23, 0, 1, 2, 3)) / max(1, total)
    morning = sum(by_hour[h] for h in (5, 6, 7, 8, 9)) / max(1, total)
    share = lambda key: sum(c["secs"] for c in chs if c["ch"] == channels.get(key)) / max(1, total)
    top_share = shows[0]["secs"] / max(1, total) if shows else 0
    # the personality card
    if shows and top_share >= 0.35:
        persona = ("The Superfan", f"{shows[0]['show']} was your show. Like, really your show.")
    elif binge and binge["secs"] >= 4 * 3600:
        persona = ("The Binger", "Just one more episode. Then another. Then another.")
    elif share("sports") >= 0.25:
        persona = ("The Sports Fanatic", "Scores, stats and play-by-play. You never missed a game.")
    elif share("weather") >= 0.25:
        persona = ("The Weather Watcher", "Local forecast on the 8s, every time.")
    elif fl > max(30, len(rows) * 2):
        persona = ("The Channel Surfer", "Why watch one channel when you can watch all of them?")
    elif night >= 0.35:
        persona = ("The Night Owl", "Late-night TV was your happy place.")
    elif morning >= 0.25:
        persona = ("The Early Bird", "Saturday-morning-cartoons energy, every day.")
    else:
        persona = ("The Prime-Time Regular", "Same time, same channel. A true TV classic.")
    out.update(total=int(total), days=len(by_day), flips=int(fl),
               channels=chs[:5], shows=[dict(s, secs=int(s["secs"])) for s in shows[:5]], tvs=tvs[:5],
               hours=[int(h) for h in by_hour], weekdays=[int(w) for w in by_wd], months=[int(m) for m in by_month],
               peak_hour=peak, busiest={"day": busiest[0], "secs": int(busiest[1])},
               binge={"show": binge["show"], "ch": binge["ch"], "secs": int(binge["secs"]), "start": binge["start"],
                      "tv": names.get(binge["tv"]) or binge.get("tvname") or "TV"} if binge else None,
               songs=[{"song": k, "times": v} for k, v in sorted(songs.items(), key=lambda x: -x[1])[:5]],
               persona={"title": persona[0], "line": persona[1]}, first=rows[0]["start"])
    return out
