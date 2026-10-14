"""Voice remote: hold the mic button on the phone remote and say what you want.

Off until you turn it on (VOICE_REMOTE=on, setup page → Experimental). The phone's own speech
recognition turns your voice into words (Apple's on iPhone, Google's on Android, the same as dictating
a text), and KNAS works out what you meant:

  "channel 42" · "go to 7" · "put on Nickelodeon" · "King of the Hill" · "channel up" · "last channel"
  "volume up" · "turn it down" · "mute" · "guide" · "what's on" · "weather" · "sports" · "jukebox"
  "play Thriller on the jukebox"

If a show you ask for isn't on right now but is coming up, KNAS tells you when and where.
"""
import difflib, os, re, time

NUM_WORDS = {"zero": 0, "oh": 0, "one": 1, "two": 2, "to": 2, "too": 2, "three": 3, "four": 4, "for": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
             "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
             "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100}
FILLER = r"^(?:hey |ok |okay |um |uh |please |can you |could you |would you |i want to |i wanna |let'?s |go ahead and )+"
WATCH = r"^(?:put on|turn on|switch to|change to|change it to|go to|tune to|tune in to|flip to|watch|play|show me|show|open|find)\s+"


def enabled():
    return os.environ.get("VOICE_REMOTE", "off").strip().lower() in ("on", "yes", "1", "true")


def _norm(s):
    s = s.lower().replace("&", " and ")
    s = re.sub(r"[^\w\s']", " ", s)
    s = re.sub(r"\b(the|a|an)\b", " ", s)
    return re.sub(r"\s+", " ", s.replace("'", "")).strip()


def _words_to_number(t):
    """'forty two' -> 42, 'four two' -> 42, '7' -> 7. None if it isn't a number."""
    t = t.strip().replace("-", " ")
    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        return t
    parts = t.split()
    if not parts or any(p not in NUM_WORDS for p in parts):
        return None
    vals = [NUM_WORDS[p] for p in parts]
    if all(v < 10 for v in vals):                # "four two" -> 42
        return "".join(str(v) for v in vals)
    total, cur = 0, 0
    for v in vals:
        if v == 100:
            cur = max(cur, 1) * 100
        elif v >= 20 and cur % 100 == 0:
            cur += v
        elif v < 10 and cur % 10 == 0:
            cur += v
        else:                                     # "twelve thirteen" -> 1213
            total = (total + cur) * (10 ** len(str(v)))
            cur = v
    return str(total + cur)


def _score(q, name):
    a, b = _norm(q), _norm(name)
    if not a or not b:
        return 0
    if a == b:
        return 1.0
    if (" " + a + " ") in (" " + b + " ") and len(a) >= 3:
        return 0.93 - min(.15, (len(b) - len(a)) / 200)
    if (" " + b + " ") in (" " + a + " ") and len(b) >= 4:
        return 0.86
    r = difflib.SequenceMatcher(None, a, b).ratio()
    aw, bw = set(a.split()), set(b.split())
    overlap = len(aw & bw) / max(1, len(aw | bw))
    return max(r, overlap * 0.95)


def understand(text, channels, programs, builtins, now=None):
    """Work out what someone said. Returns an action dict:
       {"key": "volup", "times": 3} · {"tune": "42", "say": ...} · {"say": ...} · {"jukebox": "song name"}"""
    now = now or time.time()
    raw = (text or "").strip()
    t = re.sub(FILLER, "", _norm(raw)).strip()
    t = re.sub(r"\b(on tv|on the tv|please|for me|now|right now)$", "", t).strip()
    if not t:
        return {"say": "I didn't catch that."}

    # ---- buttons ----
    simple = [
        (r"^(channel |go )?up$|^next( channel)?$|^channel up$", ("up", 1, "Channel up")),
        (r"^(channel )?down$|^channel down$", ("down", 1, "Channel down")),
        (r"^(last|previous|go back|back to last|flip back)( channel)?$|^go back$", ("left", 1, "Last channel")),
        (r"^(louder|turn it up|volume up|turn volume up|turn up( volume)?|crank it( up)?|up volume)$", ("volup", 3, "Louder")),
        (r"^(quieter|softer|turn it down|volume down|turn volume down|turn down( volume)?|lower( volume)?|down volume)$", ("voldown", 3, "Quieter")),
        (r"^(mute|unmute|be quiet|shut up|silence|sound off|sound on|mute it|unmute it)$", ("mute", 1, "Mute")),
        (r"^(guide|tv guide|open guide|show guide|whats on|what is on|whats on tv|what is on tv|channel guide|listings)$", ("guide", 1, "Opening the guide")),
        (r"^(info|whats this|what is this|what am i watching|what show is this)$", ("info", 1, "Show info")),
        (r"^(close|close it|back|exit|cancel|nevermind|never mind)$", ("back", 1, "Back")),
    ]
    for pat, (k, n, say) in simple:
        if re.search(pat, t):
            return {"key": k, "times": n, "say": say}
    m = re.match(r"^(?:volume|turn it|turn) (up|down) (\d+|\w+)(?: times)?$", t)
    if m:
        n = _words_to_number(m.group(2))
        return {"key": "volup" if m.group(1) == "up" else "voldown", "times": max(1, min(10, int(float(n or 1)))), "say": "Volume " + m.group(1)}

    # ---- the jukebox: "play thriller on the jukebox", "jukebox play ..." ----
    m = re.match(r"^(?:(?:play|add|queue( up)?) (.+?) (?:on|to|in) (?:jukebox|juke box|party channel)|(?:jukebox|juke box) (?:play|add) (.+))$", t)
    if m:
        song = (m.group(2) or m.group(3) or "").strip()
        if song:
            return {"jukebox": song, "say": f"Adding {song} to the jukebox"}

    # ---- a channel number ----
    m = re.match(r"^(?:(?:channel|chanel|number|station|go to|tune to|put on|switch to|change to|turn to)\s+)?(?:channel\s+)?(.+)$", t)
    n = _words_to_number(m.group(1).replace(" point ", ".")) if m else None
    if n is not None:
        n = n.rstrip(".")
        if any(c[0] == n for c in channels):
            name = next(c[1] for c in channels if c[0] == n)
            return {"tune": n, "say": f"Channel {n}: {name}"}
        return {"say": f"There's no channel {n} on this TV."}

    q = re.sub(WATCH, "", t).strip()
    q = re.sub(r"\s+(channel|on|show|tv show|the show|episode|an episode|reruns)$", "", q).strip()
    q = re.sub(r"^(some|an episode of|episode of|reruns of)\s+", "", q).strip()

    # ---- KNAS's own channels by what they are ----
    for words, key in ((r"weather|forecast|knas|radar", "weather"), (r"sports|scores|game|the game", "sports"),
                       (r"jukebox|juke box|music videos|party", "party"), (r"games|trivia|party games|kahoot", "trivia"),
                       (r"wrapped|my year", "wrapped"), (r"live cam|livecam|camera|cam", "livecam"),
                       (r"duck season|duck hunt|ducks|light gun|zapper", "duck"),
                       (r"flick games|darts|hoops|basketball|bowling|cup pong|beer pong", "flick"),
                       (r"stream|the stream|live stream|stream channel", "stream")):
        if re.fullmatch(f"(?:{words})(?: channel)?", q) and builtins.get(key):
            num = builtins[key]
            name = next((c[1] for c in channels if c[0] == num), key)
            return {"tune": num, "say": f"Channel {num}: {name}"}

    # ---- a channel by name, or a show that's on ----
    best = (0, None, None)
    for num, name in channels:
        s = _score(q, name)
        if s > best[0]:
            best = (s, num, f"Channel {num}: {name}")
    on_now, later = [], []
    for num, name in channels:
        for p in programs.get(num, []):
            if p.get("e", 0) <= now or p.get("s", 0) > now + 6 * 3600:
                continue
            s = max(_score(q, p.get("t", "")), _score(q, p.get("st", "")) * .9 if p.get("st") else 0)
            if s >= .72:
                (on_now if p["s"] <= now else later).append((s, p["s"], num, name, p))
    if on_now:
        on_now.sort(key=lambda x: (-x[0], x[1]))
        s, _, num, name, p = on_now[0]
        if s >= best[0] - .05 or best[0] < .8:
            return {"tune": num, "say": f"{p['t']} is on channel {num} ({name})"}
    if best[0] >= .78:
        return {"tune": best[1], "say": best[2]}
    if later:
        later.sort(key=lambda x: (-x[0], x[1]))
        s, start, num, name, p = later[0]
        return {"later": {"num": num, "name": name, "title": p["t"], "start": start}, "say": f"{p['t']} isn't on right now"}
    if best[0] >= .62:
        return {"tune": best[1], "say": best[2]}
    return {"say": f"I couldn't find “{raw}” on right now."}
