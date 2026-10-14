"""Party games channel: games on the TV, with everyone's phone as their controller (a bit like Kahoot / Jackbox).

Off until you give it a channel number: TRIVIA_CHANNEL=45 (setup page → Experimental → Trivia). The TV shows a QR
code; everyone scans it (or opens /p) and types a name. The first one in is the host: they pick the game and its
options, then press Start. Games:

  trivia   multiple-choice questions (Open Trivia Database topics and your own trivia list)
  tune     Name That Tune: a few seconds of a song from the jukebox plays (sound only), pick the title
  wordle   everyone solves the same five-letter word at once; fewer guesses and faster scores more
  bluff    a strange-but-true fact with a blank: everyone makes up a fake answer, then finds the real one
  wheel    a word puzzle: spin, call letters, buy vowels, solve it to bank your money
  draw     one player draws a word on their phone, everyone else guesses; faster guesses score more

Leaderboard between rounds and a podium at the end.
"""
import json, os, random, re, threading, time

import game_content as C

DATA = ""
POOL = None                  # server.py: fn(topics) -> trivia questions [{"q", "a", "wrong": [...]}]
TUNES = None                 # server.py: fn() -> jukebox songs saved on the NAS [{"id", "title", "secs"}]
TOPICS = {}                  # trivia topics: key -> label
_lock = threading.RLock()
G = {}
RECENT = []                  # questions / words / puzzles used lately, so the next game feels new
READ_SECS = 4                # a trivia question shows alone this long before the answers open
REVEAL_SECS = 6
BOARD_SECS = 6
IDLE_DROP = 45               # a phone that hasn't checked in for this long has left
MAX_PLAYERS = 60

MODES = {
    "trivia": {"name": "Trivia", "icon": "❓", "about": "Multiple choice. Faster right answers score more.",
               "count": [5, 10, 15, 20, 30], "count_label": "Questions", "count_def": 10,
               "secs": [10, 15, 20, 30], "secs_label": "Seconds per question", "secs_def": 20, "topics": True},
    "tune": {"name": "Name That Tune", "icon": "🎵", "about": "A few seconds of a jukebox song plays. Pick the title.",
             "count": [5, 10, 15, 20], "count_label": "Songs", "count_def": 10,
             "secs": [8, 12, 15, 20], "secs_label": "Seconds of music", "secs_def": 12},
    "wordle": {"name": "Word Race", "icon": "🟩", "about": "Everyone solves the same five-letter word. Fewer guesses wins.",
               "count": [1, 3, 5], "count_label": "Words", "count_def": 3,
               "secs": [90, 150, 240], "secs_label": "Seconds per word", "secs_def": 150},
    "bluff": {"name": "Bluff", "icon": "🤥", "about": "Make up a fake answer to a true fact, then find the real one.",
              "count": [3, 5, 8], "count_label": "Rounds", "count_def": 5,
              "secs": [45, 60, 90], "secs_label": "Seconds to write", "secs_def": 60},
    "wheel": {"name": "Wheel Puzzle", "icon": "🎡", "about": "Spin, call letters, buy vowels, and solve the puzzle.",
              "count": [1, 3, 5], "count_label": "Puzzles", "count_def": 3,
              "secs": [15, 25, 40], "secs_label": "Seconds per turn", "secs_def": 25},
    "draw": {"name": "Draw It", "icon": "🎨", "about": "One person draws on their phone, everyone else guesses.",
             "count": [1, 2, 3], "count_label": "Turns each", "count_def": 1,
             "secs": [60, 80, 100], "secs_label": "Seconds to draw", "secs_def": 80},
}
WEDGES = [500, 300, 900, "BANKRUPT", 600, 400, 700, 300, 800, "LOSE A TURN", 500, 1000, 350, 450, 600, 2500]
VOWELS = set("AEIOU")


def _defaults():
    return {m: {"count": v["count_def"], "secs": v["secs_def"]} for m, v in MODES.items()}


def _new():
    G.clear()
    G.update(phase="lobby", rev=0, players={}, host="", mode="trivia", rounds=[], ri=-1, R=None, until=0, opens=0,
             settings={"mode": "trivia", "topics": ["general"], "per": _defaults()}, message="", started=0)


def setup(data_dir, pool, topics, tunes=None):
    global DATA, POOL, TUNES
    DATA, POOL, TUNES = data_dir, pool, tunes
    TOPICS.update(topics)
    _new()
    try:
        with open(os.path.join(DATA, "trivia-game.json")) as f:
            j = json.load(f)
        RECENT[:] = j.get("recent", [])[-1500:]
        st = j.get("settings") or {}
        if isinstance(st, dict):
            if st.get("mode") in MODES:
                G["settings"]["mode"] = st["mode"]
            if isinstance(st.get("topics"), list):
                G["settings"]["topics"] = [t for t in st["topics"] if t in TOPICS] or ["general"]
            for m, v in (st.get("per") or {}).items():
                if m in MODES and isinstance(v, dict):
                    G["settings"]["per"][m].update({k: v[k] for k in ("count", "secs") if v.get(k) in MODES[m][k]})
    except (OSError, ValueError):
        pass
    threading.Thread(target=_loop, daemon=True, name="party-games").start()


def _save():
    try:
        with open(os.path.join(DATA, "trivia-game.json"), "w") as f:
            json.dump({"recent": RECENT[-1500:], "settings": G["settings"]}, f)
    except OSError:
        pass


def _bump():
    G["rev"] += 1


def _clean_id(i):
    i = str(i or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,40}", i):
        raise ValueError("bad player id")
    return i


def _active():
    now = time.time()
    return {k: p for k, p in G["players"].items() if now - p["seen"] < IDLE_DROP}


def _fix_host():
    act = _active()
    if G["host"] not in act:
        first = min(act.values(), key=lambda p: p["joined"], default=None)
        G["host"] = first["id"] if first else ""


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _name(pid):
    p = G["players"].get(pid)
    return p["name"] if p else "Someone"


def _per():
    return G["settings"]["per"][G["mode"]]


# ---------------------------------------------------------------- joining and the host's buttons

def join(data):
    pid = _clean_id(data.get("id"))
    name = re.sub(r"\s+", " ", str(data.get("name") or "")).strip()[:16]
    if not name:
        return {"ok": False, "message": "Type a name first."}
    with _lock:
        taken = {p["name"].lower() for k, p in _active().items() if k != pid}
        if name.lower() in taken:
            return {"ok": False, "message": "Someone already has that name. Pick another one."}
        if pid not in G["players"] and len(_active()) >= MAX_PLAYERS:
            return {"ok": False, "message": "The game is full."}
        p = G["players"].get(pid)
        if p:
            p.update(name=name, seen=time.time())
        else:
            G["players"][pid] = {"id": pid, "name": name, "score": 0, "streak": 0, "gain": 0, "right": None,
                                 "joined": time.time(), "seen": time.time()}
        _fix_host()
        _bump()
    return state(pid)


def leave(data):
    pid = _clean_id(data.get("id"))
    with _lock:
        G["players"].pop(pid, None)
        _fix_host()
        _bump()
    return {"ok": True}


def host(data):
    pid = _clean_id(data.get("id"))
    with _lock:
        _fix_host()
        if pid != G["host"]:
            return dict(state(pid), ok=False, message="Only the host can do that.")
        act = data.get("do")
        st = G["settings"]
        if act == "settings" and G["phase"] in ("lobby", "final"):
            if data.get("mode") in MODES:
                st["mode"] = data["mode"]
            m = st["mode"]
            t = [x for x in (data.get("topics") or []) if x in TOPICS][:6]
            if t:
                st["topics"] = t
            if data.get("count") in MODES[m]["count"]:
                st["per"][m]["count"] = data["count"]
            if data.get("secs") in MODES[m]["secs"]:
                st["per"][m]["secs"] = data["secs"]
            G["message"] = ""
            _save()
        elif act == "start" and G["phase"] in ("lobby", "final"):
            G["mode"] = st["mode"]
            G["phase"], G["message"] = "loading", "Getting ready…"
            for p in G["players"].values():
                p.update(score=0, streak=0, gain=0, right=None)
            _bump()
            threading.Thread(target=_prepare, daemon=True).start()
        elif act == "skip" and G["phase"] not in ("lobby", "loading", "final"):
            G["until"] = time.time()
            if G["R"] and G["R"].get("kind") == "wheel" and G["phase"] == "wheel":
                _wheel_end(None)
        elif act == "end" and G["phase"] not in ("lobby", "final"):
            _finish()
        elif act == "lobby":
            G.update(phase="lobby", rounds=[], ri=-1, R=None, message="")
            for p in G["players"].values():
                p.update(score=0, streak=0, gain=0, right=None)
        elif act == "kick":
            G["players"].pop(str(data.get("who") or ""), None)
            _fix_host()
        _bump()
    return state(pid)


# ---------------------------------------------------------------- getting each game ready

def _fresh(items, key, n):
    """n items, skipping ones used lately when there are enough new ones."""
    recent = set(RECENT)
    new = [x for x in items if key(x) not in recent]
    random.shuffle(new)
    picks = new[:n]
    if len(picks) < n:
        old = [x for x in items if x not in picks]
        random.shuffle(old)
        picks += old[:n - len(picks)]
    return picks


def _clean_title(t):
    t = re.sub(C.TUNE_JUNK, "", t or "", flags=re.I)
    t = re.split(r"\s+[|｜]\s+", t)[0]
    return re.sub(r"\s+", " ", t).strip(" -–—") or t


def _prepare():
    mode = G["mode"]
    per = G["settings"]["per"][mode]
    n = per["count"]
    rounds, problem = [], ""
    try:
        if mode == "trivia":
            pool = POOL(G["settings"]["topics"]) or []
            clean, seen = [], set()
            for x in pool:
                q, a = (x.get("q") or "").strip(), (x.get("a") or "").strip()
                wrong = [w.strip() for w in (x.get("wrong") or []) if w and w.strip() and w.strip() != a]
                if q and a and wrong and q not in seen:
                    seen.add(q)
                    clean.append({"q": q, "a": a, "wrong": wrong[:3]})
            rounds = _fresh(clean, lambda x: x["q"], n)
            problem = "Couldn't get any questions. Check the internet, or add your own trivia on the setup page."
        elif mode == "tune":
            songs, seen = [], set()
            for s in (TUNES() if TUNES else []):
                t = _clean_title(s.get("title") or "")
                if t and _norm(t) not in seen and "karaoke" not in t.lower():
                    seen.add(_norm(t))
                    songs.append(dict(s, title=t))
            if len(songs) >= 4:
                for s in _fresh(songs, lambda x: "tune:" + x["id"], n):
                    others = random.sample([o for o in songs if o["id"] != s["id"]], 3)
                    secs = s.get("secs") or 0
                    start = int(secs * random.uniform(0.25, 0.55)) if secs > 60 else (0 if secs else 20)
                    rounds.append({"q": "Name that tune!", "a": s["title"], "wrong": [o["title"] for o in others],
                                   "audio": {"src": f"/jukebox-video/{s['id']}.mp4", "start": start}, "key": "tune:" + s["id"]})
            problem = "Name That Tune needs at least 4 songs saved from the jukebox. Play a few songs on the jukebox first."
        elif mode == "wordle":
            rounds = [{"word": w.upper()} for w in _fresh(C.WORDLE, lambda w: "w:" + w, n)]
        elif mode == "bluff":
            rounds = [{"prompt": p, "truth": a} for p, a in _fresh(C.BLUFF, lambda x: "b:" + x[0], n)]
        elif mode == "wheel":
            rounds = [{"cat": c, "phrase": p} for c, p in _fresh(C.WHEEL, lambda x: "h:" + x[1], n)]
        elif mode == "draw":
            with _lock:
                order = [p["id"] for p in sorted(_active().values(), key=lambda p: p["joined"])]
            if len(order) < 2:
                problem = "Draw It needs at least 2 players."
            else:
                words = _fresh(C.DRAW, lambda w: "d:" + w, len(order) * n * 3)
                k = 0
                for _ in range(n):
                    for pid in order:
                        rounds.append({"drawer": pid, "choices": words[k:k + 3] or random.sample(C.DRAW, 3)})
                        k += 3
    except Exception as e:
        print("[party games]", e, flush=True)
        problem = problem or f"Couldn't start the game ({e})."
    with _lock:
        if G["phase"] != "loading":
            return
        if not rounds:
            G["phase"], G["message"] = "lobby", problem or "Couldn't start the game."
            _bump()
            return
        G.update(rounds=rounds, ri=-1, message="", started=time.time())
        for r in rounds:
            k = r.get("key") or r.get("q") or ("w:" + r["word"].lower() if "word" in r else "") or \
                ("b:" + r["prompt"] if "prompt" in r else "") or ("h:" + r["phrase"] if "phrase" in r else "")
            if k:
                RECENT.append(k)
            for w in r.get("choices", []) if "drawer" in r else []:
                RECENT.append("d:" + w)
        _save()
        _next_round()


def _next_round():
    G["ri"] += 1
    if G["ri"] >= len(G["rounds"]):
        return _finish()
    x, now, mode = G["rounds"][G["ri"]], time.time(), G["mode"]
    for p in G["players"].values():
        p.update(gain=0, right=None)
    per = _per()
    if mode in ("trivia", "tune"):
        choices = [x["a"]] + x["wrong"]
        random.shuffle(choices)
        G["R"] = {"kind": "quiz", "text": x["q"], "choices": choices, "right": choices.index(x["a"]),
                  "secs": per["secs"] if mode == "trivia" else max(10, per["secs"] + 5), "ans": {}, "audio": x.get("audio"),
                  "clip": per["secs"] if mode == "tune" else 0}
        G["opens"] = now + (READ_SECS if mode == "trivia" else 2)
        G["until"] = G["opens"] + G["R"]["secs"]
        G["phase"], G["opened"] = "question", False
    elif mode == "wordle":
        G["R"] = {"kind": "wordle", "word": x["word"], "p": {}, "start": now, "secs": per["secs"]}
        G["phase"], G["until"] = "wordle", now + per["secs"]
    elif mode == "bluff":
        G["R"] = {"kind": "bluff", "prompt": x["prompt"], "truth": x["truth"], "lies": {}, "options": [], "votes": {}}
        G["phase"], G["until"] = "bwrite", now + per["secs"]
    elif mode == "wheel":
        order = [p["id"] for p in sorted(_active().values(), key=lambda p: p["joined"])]
        random.shuffle(order)
        G["R"] = {"kind": "wheel", "cat": x["cat"], "phrase": x["phrase"], "shown": [], "order": order, "turn": order[0] if order else "",
                  "step": "spin", "value": 0, "bank": {}, "last": "", "wedge": -1, "spins": 0, "winner": ""}
        G["phase"], G["until"] = "wheel", now + per["secs"]
    elif mode == "draw":
        G["R"] = {"kind": "draw", "drawer": x["drawer"], "choices": x["choices"], "word": "", "ops": [], "guessed": {},
                  "feed": [], "start": 0, "secs": per["secs"], "hint": []}
        G["phase"], G["until"] = "dpick", now + 15
    _bump()


def _finish():
    G["phase"], G["until"] = "final", 0
    _bump()


def _after_reveal():
    if G["ri"] + 1 >= len(G["rounds"]):
        _finish()
    else:
        G["phase"], G["until"] = "board", time.time() + BOARD_SECS
        _bump()


# ---------------------------------------------------------------- trivia and Name That Tune

def answer(data):
    pid = _clean_id(data.get("id"))
    with _lock:
        R = G["R"]
        p = G["players"].get(pid)
        if not p or not R or R.get("kind") != "quiz" or G["phase"] != "question" or time.time() < G["opens"]:
            return state(pid)
        try:
            i = int(data.get("choice"))
        except (TypeError, ValueError):
            return state(pid)
        if pid not in R["ans"] and 0 <= i < len(R["choices"]):
            R["ans"][pid] = (i, time.time())
            _bump()
            if all(k in R["ans"] for k in _active()):
                G["until"] = min(G["until"], time.time() + 0.6)
    return state(pid)


def _score_quiz():
    R = G["R"]
    for pid, p in G["players"].items():
        a = R["ans"].get(pid)
        if not a:
            p.update(right=None, gain=0, streak=0)
        elif a[0] == R["right"]:
            left = max(0.0, (G["opens"] + R["secs"]) - a[1])
            p["streak"] += 1
            p["gain"] = int(round(500 + 500 * left / R["secs"])) + min(500, 100 * (p["streak"] - 1))
            p["right"] = True
            p["score"] += p["gain"]
        else:
            p.update(right=False, gain=0, streak=0)


# ---------------------------------------------------------------- Word Race (Wordle)

def _colors(guess, word):
    res, left = ["x"] * 5, list(word)
    for i in range(5):
        if guess[i] == word[i]:
            res[i], left[i] = "g", None
    for i in range(5):
        if res[i] != "g" and guess[i] in left:
            res[i] = "y"
            left[left.index(guess[i])] = None
    return "".join(res)


def guess_word(data):
    pid = _clean_id(data.get("id"))
    g = re.sub(r"[^A-Za-z]", "", str(data.get("word") or "")).upper()
    with _lock:
        R = G["R"]
        if not R or R.get("kind") != "wordle" or G["phase"] != "wordle" or pid not in G["players"]:
            return state(pid)
        me = R["p"].setdefault(pid, {"rows": [], "done": False, "won": False, "t": 0})
        if me["done"]:
            return state(pid)
        if len(g) != 5:
            return dict(state(pid), message="Five letters, please.")
        col = _colors(g, R["word"])
        me["rows"].append([g, col])
        if col == "ggggg" or len(me["rows"]) >= 6:
            me.update(done=True, won=col == "ggggg", t=time.time())
            if me["won"]:
                left = max(0, R["start"] + R["secs"] - me["t"])
                gain = 600 + (6 - len(me["rows"])) * 150 + int(300 * left / R["secs"])
                G["players"][pid]["score"] += gain
                G["players"][pid]["gain"] = gain
                G["players"][pid]["right"] = True
            else:
                G["players"][pid]["right"] = False
        _bump()
        if all(R["p"].get(k, {}).get("done") for k in _active()):
            G["until"] = min(G["until"], time.time() + 1)
    return state(pid)


# ---------------------------------------------------------------- Bluff

def bluff(data):
    pid = _clean_id(data.get("id"))
    with _lock:
        R = G["R"]
        if not R or R.get("kind") != "bluff" or pid not in G["players"]:
            return state(pid)
        if G["phase"] == "bwrite" and "lie" in data:
            lie = re.sub(r"\s+", " ", str(data.get("lie") or "")).strip()[:40]
            if not lie:
                return dict(state(pid), message="Type a fake answer first.")
            if _norm(lie) == _norm(R["truth"]):
                return dict(state(pid), message="That's actually the real answer! Make up a fake one.", truth_hit=True)
            R["lies"][pid] = lie
            _bump()
            if all(k in R["lies"] for k in _active()):
                G["until"] = min(G["until"], time.time() + 0.6)
        elif G["phase"] == "bvote" and "vote" in data:
            try:
                i = int(data["vote"])
            except (TypeError, ValueError):
                return state(pid)
            if 0 <= i < len(R["options"]) and pid not in R["options"][i]["by"] and pid not in R["votes"]:
                R["votes"][pid] = i
                _bump()
                if all(k in R["votes"] for k in _active()):
                    G["until"] = min(G["until"], time.time() + 0.6)
    return state(pid)


def _bluff_options():
    R = G["R"]
    opts = {}
    for pid, lie in R["lies"].items():
        o = opts.setdefault(_norm(lie), {"text": lie, "by": [], "truth": False})
        o["by"].append(pid)
    out = list(opts.values()) + [{"text": R["truth"], "by": [], "truth": True}]
    random.shuffle(out)
    R["options"] = out


def _score_bluff():
    R = G["R"]
    for pid, i in R["votes"].items():
        o = R["options"][i]
        p = G["players"].get(pid)
        if not p:
            continue
        if o["truth"]:
            p["gain"] += 1000
            p["right"] = True
        else:
            p["right"] = False
            for author in o["by"]:
                a = G["players"].get(author)
                if a:
                    a["gain"] += 500 // len(o["by"])
    for p in G["players"].values():
        p["score"] += p["gain"]


# ---------------------------------------------------------------- Wheel Puzzle

def _letters(phrase):
    return {c for c in phrase if c.isalpha()}


def _wheel_next_turn(msg=""):
    R = G["R"]
    act = _active()
    order = [p for p in R["order"] if p in act] or list(act)
    R["order"] = order
    if not order:
        return
    i = order.index(R["turn"]) if R["turn"] in order else -1
    R["turn"] = order[(i + 1) % len(order)]
    R["step"], R["value"] = "spin", 0
    if msg:
        R["last"] = msg
    G["until"] = time.time() + _per()["secs"]


def _wheel_end(winner):
    R = G["R"]
    R["shown"] = sorted(_letters(R["phrase"]))
    R["winner"] = winner or ""
    if winner:
        gain = max(R["bank"].get(winner, 0), 1000)
        G["players"][winner]["gain"] = gain
        G["players"][winner]["score"] += gain
        R["last"] = f"{_name(winner)} solved it! +{gain:,}"
    else:
        R["last"] = "Nobody solved it."
    G["phase"], G["until"] = "wsolved", time.time() + 8


def wheel(data):
    pid = _clean_id(data.get("id"))
    act = data.get("do")
    with _lock:
        R = G["R"]
        if not R or R.get("kind") != "wheel" or G["phase"] != "wheel" or pid != R["turn"]:
            return state(pid)
        bank = R["bank"].setdefault(pid, 0)
        shown = set(R["shown"])
        letters = _letters(R["phrase"])
        if act == "spin" and R["step"] == "spin":
            if not (letters - VOWELS - shown):
                return dict(state(pid), message="No consonants left. Buy a vowel or solve it!")
            w = random.randrange(len(WEDGES))
            R["wedge"], R["spins"] = w, R["spins"] + 1
            v = WEDGES[w]
            if v == "BANKRUPT":
                R["bank"][pid] = 0
                _wheel_next_turn(f"{_name(pid)} hit BANKRUPT!")
            elif v == "LOSE A TURN":
                _wheel_next_turn(f"{_name(pid)} loses a turn.")
            else:
                R["step"], R["value"] = "letter", v
                R["last"] = f"{_name(pid)} spun ${v:,}. Pick a consonant!"
                G["until"] = time.time() + _per()["secs"]
        elif act == "letter" and R["step"] == "letter":
            c = str(data.get("letter") or "").upper()[:1]
            if not c.isalpha() or c in VOWELS or c in shown:
                return dict(state(pid), message="Pick a consonant that hasn't been called.")
            R["shown"].append(c)
            n = R["phrase"].count(c)
            if n:
                won = n * R["value"]
                R["bank"][pid] = bank + won
                R["step"], R["value"] = "spin", 0
                R["last"] = f"There {'is' if n == 1 else 'are'} {n} {c}{'' if n == 1 else 's'}! +${won:,}"
                G["until"] = time.time() + _per()["secs"]
            else:
                _wheel_next_turn(f"Sorry, no {c}.")
        elif act == "vowel" and R["step"] == "spin":
            if bank < 250:
                return dict(state(pid), message="A vowel costs $250. Spin to earn some money first.")
            if not (letters & VOWELS - shown):
                return dict(state(pid), message="All the vowels are showing already.")
            R["step"] = "vowel"
            G["until"] = time.time() + _per()["secs"]
        elif act == "letter" and R["step"] == "vowel":
            c = str(data.get("letter") or "").upper()[:1]
            if c not in VOWELS or c in shown:
                return dict(state(pid), message="Pick a vowel that hasn't been called.")
            R["bank"][pid] = bank - 250
            R["shown"].append(c)
            n = R["phrase"].count(c)
            if n:
                R["step"] = "spin"
                R["last"] = f"There {'is' if n == 1 else 'are'} {n} {c}{'' if n == 1 else 's'}."
                G["until"] = time.time() + _per()["secs"]
            else:
                _wheel_next_turn(f"No {c}.")
        elif act == "solve" and R["step"] in ("spin", "solve"):
            if "text" not in data:
                R["step"] = "solve"
                G["until"] = time.time() + max(30, _per()["secs"])
            elif _norm(data.get("text")) == _norm(R["phrase"]):
                _wheel_end(pid)
            else:
                _wheel_next_turn(f"{_name(pid)} guessed “{str(data.get('text'))[:40]}”. Not quite!")
        elif act == "cancel" and R["step"] in ("solve", "vowel"):
            R["step"] = "spin"
        if G["phase"] == "wheel" and letters <= set(R["shown"]):
            _wheel_end(pid)
        _bump()
    return state(pid)


# ---------------------------------------------------------------- Draw It

def draw_pick(data):
    pid = _clean_id(data.get("id"))
    with _lock:
        R = G["R"]
        if R and R.get("kind") == "draw" and G["phase"] == "dpick" and pid == R["drawer"]:
            w = str(data.get("word") or "")
            if w in R["choices"]:
                _draw_begin(w)
                _bump()
    return state(pid)


def _draw_begin(word):
    R = G["R"]
    R.update(word=word, start=time.time(), ops=[], guessed={}, feed=[], hint=[])
    G["phase"], G["until"] = "draw", time.time() + R["secs"]


def draw_ops(data):
    """The drawer's strokes: [[stroke, color, width, x, y], ...] with x/y from 0 to 1000, or clear."""
    pid = _clean_id(data.get("id"))
    with _lock:
        R = G["R"]
        if not R or R.get("kind") != "draw" or G["phase"] != "draw" or pid != R["drawer"]:
            return {"ok": False}
        if data.get("clear"):
            R["ops"].append(["C"])
        for op in (data.get("ops") or [])[:400]:
            try:
                s, c, w, x, y = op
                R["ops"].append([int(s) % 100000, str(c)[:9], max(1, min(40, int(w))), max(0, min(1000, int(x))), max(0, min(1000, int(y)))])
            except (TypeError, ValueError):
                continue
        if len(R["ops"]) > 40000:
            R["ops"] = R["ops"][-40000:]
    return {"ok": True, "n": len(R["ops"])}


def strokes(since=0):
    with _lock:
        R = G["R"]
        if not R or R.get("kind") != "draw":
            return {"ok": True, "ops": [], "n": 0}
        ops = R["ops"]
        since = max(0, min(int(since or 0), len(ops)))
        return {"ok": True, "ops": ops[since:since + 3000], "n": since + len(ops[since:since + 3000]), "word_set": bool(R["word"])}


def _close(a, b):
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    s, l = (a, b) if len(a) < len(b) else (b, a)
    return any(l[:i] + l[i + 1:] == s for i in range(len(l)))


def draw_guess(data):
    pid = _clean_id(data.get("id"))
    text = re.sub(r"\s+", " ", str(data.get("text") or "")).strip()[:40]
    with _lock:
        R = G["R"]
        if not R or R.get("kind") != "draw" or G["phase"] != "draw" or pid == R["drawer"] or pid not in G["players"] or not text:
            return state(pid)
        if pid in R["guessed"]:
            return state(pid)
        g, w = _norm(text), _norm(R["word"])
        out = state(pid)
        if g == w:
            left = max(0, R["start"] + R["secs"] - time.time())
            gain = 200 + int(400 * left / R["secs"]) + (100 if not R["guessed"] else 0)
            R["guessed"][pid] = time.time()
            p = G["players"][pid]
            p["gain"], p["right"] = gain, True
            p["score"] += gain
            d = G["players"].get(R["drawer"])
            if d:
                d["gain"] += 150
                d["score"] += 150
            R["feed"].append({"who": p["name"], "ok": True})
            _bump()
            guessers = [k for k in _active() if k != R["drawer"]]
            if all(k in R["guessed"] for k in guessers):
                G["until"] = min(G["until"], time.time() + 1)
            out = state(pid)
        else:
            close = _close(g, w) or (len(w) > 4 and (w in g or g in w) and len(g) >= len(w) - 2)
            R["feed"].append({"who": _name(pid), "close": True} if close else {"who": _name(pid), "text": text})   # don't give it away
            _bump()
            out = state(pid)
            if close:
                out["message"] = "So close!"
        R["feed"] = R["feed"][-12:]
        return out


def _draw_hint():
    R = G["R"]
    letters = [i for i, c in enumerate(R["word"]) if c.isalpha()]
    want = 1 if time.time() - R["start"] > R["secs"] * 0.5 else 0
    want += 1 if time.time() - R["start"] > R["secs"] * 0.75 and len(letters) > 5 else 0
    while len(R["hint"]) < min(want, max(0, len(letters) - 2)):
        R["hint"].append(random.choice([i for i in letters if i not in R["hint"]]))
        _bump()


# ---------------------------------------------------------------- the clock

def _loop():
    while True:
        time.sleep(0.25)
        with _lock:
            try:
                _tick()
            except Exception as e:
                print("[party games]", e, flush=True)


def _tick():
    ph, now, R = G["phase"], time.time(), G["R"]
    if ph in ("lobby", "loading", "final"):
        return
    if not _active():
        G["phase"] = "lobby"
        _bump()
        return
    if ph == "question":
        if now >= G["opens"] and not G.get("opened"):
            G["opened"] = True
            _bump()
        if now >= G["until"]:
            _score_quiz()
            G["phase"], G["until"] = "reveal", now + REVEAL_SECS + (4 if R.get("audio") else 0)
            _bump()
    elif ph == "wordle" and now >= G["until"]:
        for pid, p in G["players"].items():
            if p["right"] is None and pid in _active():
                p["right"] = False
        G["phase"], G["until"] = "wreveal", now + 8
        _bump()
    elif ph == "bwrite" and now >= G["until"]:
        _bluff_options()
        G["phase"], G["until"] = "bvote", now + 30
        _bump()
    elif ph == "bvote" and now >= G["until"]:
        _score_bluff()
        G["phase"], G["until"] = "breveal", now + 10
        _bump()
    elif ph == "wheel":
        if R["turn"] not in _active():
            _wheel_next_turn(f"{_name(R['turn'])} left.")
            _bump()
        elif now >= G["until"]:
            if R["step"] == "solve":
                R["step"] = "spin"
            _wheel_next_turn(f"{_name(R['turn'])} ran out of time.")
            _bump()
    elif ph == "dpick":
        if R["drawer"] not in _active():
            G["phase"], G["until"] = "dreveal", now + 3
            R["feed"].append({"who": _name(R["drawer"]), "text": "left the game"})
            _bump()
        elif now >= G["until"]:
            _draw_begin(R["choices"][0])
            _bump()
    elif ph == "draw":
        _draw_hint()
        if now >= G["until"] or R["drawer"] not in _active():
            G["phase"], G["until"] = "dreveal", now + 6
            _bump()
    elif ph in ("reveal", "wreveal", "breveal", "wsolved", "dreveal") and now >= G["until"]:
        _after_reveal()
    elif ph == "board" and now >= G["until"]:
        _next_round()


# ---------------------------------------------------------------- what the TV and phones see

def _board():
    ps = sorted(_active().values(), key=lambda p: (-p["score"], p["joined"]))
    return [{"id": p["id"], "name": p["name"], "score": p["score"], "gain": p["gain"], "streak": p["streak"],
             "right": p["right"]} for p in ps]


def _round_view(pid, now):
    R, ph = G["R"], G["phase"]
    if not R:
        return None
    act = _active()
    k = R["kind"]
    if k == "quiz":
        out = {"text": R["text"], "choices": R["choices"] if ph != "question" or now >= G["opens"] else [],
               "secs": R["secs"], "reading": round(max(0, G["opens"] - now), 1) if ph == "question" else 0,
               "answered": sum(1 for p in act if p in R["ans"]), "of": len(act), "audio": R["audio"], "clip": R["clip"]}
        if ph != "question":
            out["right"] = R["right"]
            out["counts"] = [sum(1 for p in act if R["ans"].get(p, (None,))[0] == i) for i in range(len(R["choices"]))]
        if pid in R["ans"]:
            out["mine"] = R["ans"][pid][0]
        return out
    if k == "wordle":
        rows = []
        for p in sorted(act.values(), key=lambda p: p["joined"]):
            me = R["p"].get(p["id"], {"rows": [], "done": False, "won": False})
            rows.append({"name": p["name"], "cols": [r[1] for r in me["rows"]], "done": me["done"], "won": me["won"]})
        out = {"players": rows, "secs": R["secs"]}
        if ph != "wordle":
            out["word"] = R["word"]
        mine = R["p"].get(pid)
        if mine:
            out["mine"] = mine["rows"]
            out["mydone"], out["mywon"] = mine["done"], mine["won"]
        return out
    if k == "bluff":
        out = {"prompt": R["prompt"], "wrote": [_name(p) for p in R["lies"] if p in act],
               "voted": [_name(p) for p in R["votes"] if p in act], "of": len(act)}
        if ph in ("bvote", "breveal"):
            out["options"] = [{"text": o["text"]} for o in R["options"]]
        if ph == "breveal":
            out["options"] = [{"text": o["text"], "truth": o["truth"], "by": [_name(b) for b in o["by"]],
                               "votes": [_name(v) for v, i in R["votes"].items() if i == n]} for n, o in enumerate(R["options"])]
        out["mylie"] = R["lies"].get(pid, "")
        if pid in R["votes"]:
            out["myvote"] = R["votes"][pid]
        if ph == "bvote":
            out["mine_idx"] = [n for n, o in enumerate(R["options"]) if pid in o["by"]]
        return out
    if k == "wheel":
        shown = set(R["shown"])
        board = "".join(c if (not c.isalpha() or c in shown) else "_" for c in R["phrase"])
        return {"cat": R["cat"], "board": board, "used": sorted(shown), "turn": _name(R["turn"]), "myturn": pid == R["turn"],
                "step": R["step"], "value": R["value"], "last": R["last"], "wedge": R["wedge"], "spins": R["spins"],
                "wedges": [w if isinstance(w, str) else f"${w}" for w in WEDGES],
                "banks": [{"name": _name(p), "bank": R["bank"].get(p, 0), "turn": p == R["turn"]} for p in R["order"] if p in act],
                "mybank": R["bank"].get(pid, 0), "winner": _name(R["winner"]) if R["winner"] else "",
                "consonants_left": bool(_letters(R["phrase"]) - VOWELS - shown)}
    if k == "draw":
        w = R["word"]
        mask = "".join(c if (not c.isalpha() or i in R["hint"]) else "_" for i, c in enumerate(w))
        out = {"drawer": _name(R["drawer"]), "isdrawer": pid == R["drawer"], "mask": mask, "len": len(w.replace(" ", "")),
               "guessed": [_name(p) for p in R["guessed"]], "of": max(0, len([p for p in act if p != R["drawer"]])),
               "feed": R["feed"][-8:], "secs": R["secs"], "n": len(R["ops"])}
        if pid == R["drawer"]:
            out["word"] = w
            if ph == "dpick":
                out["choices"] = R["choices"]
        if ph == "dreveal":
            out["word"] = w
        out["iguessed"] = pid in R["guessed"]
        return out
    return None


def state(pid=""):
    with _lock:
        now = time.time()
        if pid and pid in G["players"]:
            G["players"][pid]["seen"] = now
        _fix_host()
        act = _active()
        st = G["settings"]
        m = st["mode"] if G["phase"] in ("lobby", "loading") else G["mode"]
        out = {"ok": True, "phase": G["phase"], "rev": G["rev"], "message": G["message"],
               "channel": os.environ.get("TRIVIA_CHANNEL", "0").strip() or "0",
               "name": os.environ.get("TRIVIA_NAME", "").strip() or "KNAS Games",
               "mode": m, "mode_name": MODES[m]["name"], "mode_icon": MODES[m]["icon"],
               "modes": [{"key": k, "name": v["name"], "icon": v["icon"], "about": v["about"], "count": v["count"],
                          "count_label": v["count_label"], "secs": v["secs"], "secs_label": v["secs_label"], "topics": bool(v.get("topics"))}
                         for k, v in MODES.items()],
               "settings": {"mode": st["mode"], "topics": st["topics"], "count": st["per"][st["mode"]]["count"],
                            "secs": st["per"][st["mode"]]["secs"]},
               "topics": [[k, v] for k, v in TOPICS.items()],
               "players": [{"id": p["id"], "name": p["name"]} for p in sorted(act.values(), key=lambda p: p["joined"])],
               "host_name": act[G["host"]]["name"] if G["host"] in act else "",
               "n": G["ri"] + 1, "total": len(G["rounds"]), "board": _board()[:10],
               "left": round(max(0, G["until"] - now), 1) if G["until"] else 0}
        if G["phase"] not in ("lobby", "loading", "final", "board"):
            out["round"] = _round_view(pid, now)
        if pid:
            me = G["players"].get(pid)
            out["me"] = None if not me else {
                "name": me["name"], "score": me["score"], "right": me["right"], "gain": me["gain"],
                "streak": me["streak"], "host": pid == G["host"],
                "rank": next((i + 1 for i, b in enumerate(_board()) if b["id"] == pid), 0)}
        return out
