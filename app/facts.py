"""Facts and trivia for the break screen and the weather channel ticker.

Facts can come from:
  - your facts list (facts.txt)                                   FACTS_LIST=on
  - Wikipedia articles about your town and state                  FACTS_LOCAL=on
  - anything you list in FACTS_SOURCES (separated by semicolons):
      a topic in plain words ("Space", "Kansas City Chiefs")  -> sentences from its Wikipedia article
      a Wikipedia page link                                    -> same
      a Google Sheet or a .txt / .csv file link                -> one fact per line (first column)
      an RSS feed                                              -> its headlines
      any other web page                                       -> the list items / sentences on it

Trivia can come from:
  - your trivia list (trivia.txt)                                 TRIVIA_LIST=on
  - the free Open Trivia Database, by topic                       TRIVIA_TOPICS=tv, movies, music
  - TRIVIA_SOURCES: Google Sheet or .txt / .csv links, one question per line:
        question | right answer | wrong | wrong | wrong      (or the same in spreadsheet columns)

Everything fetched is kept in data/facts-cache.json and refreshed every few hours, so the break
screen never waits on the internet and keeps working if a site is down.
"""
import csv, html, io, json, os, random, re, threading, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CACHE_FILE = os.path.join(ROOT, "data", "facts-cache.json")
REFRESH = 6 * 3600          # how often online sources are fetched again
# Wikipedia asks every program to say what it is and where to find out more, and slows down
# (error 429) anything that doesn't. https://meta.wikimedia.org/wiki/User-Agent_policy
UA = "KNAS-Retro-TV/2.2 (self-hosted retro TV for one home; https://github.com/topics/ersatztv)"

# Open Trivia Database categories (https://opentdb.com, free, no key)
TRIVIA_TOPICS = {
    "general": (9, "General knowledge"), "tv": (14, "TV"), "movies": (11, "Movies"), "music": (12, "Music"),
    "videogames": (15, "Video games"), "sports": (21, "Sports"), "science": (17, "Science & nature"),
    "history": (23, "History"), "geography": (22, "Geography"), "animals": (27, "Animals"),
    "cartoons": (32, "Cartoons & animation"), "comics": (29, "Comics"), "books": (10, "Books"),
    "cars": (28, "Cars & vehicles"), "computers": (18, "Computers"), "boardgames": (16, "Board games"),
    "mythology": (20, "Mythology"), "celebrities": (26, "Celebrities"),
}

_cache, _lock = {}, threading.Lock()
_wake = threading.Event()


def env(k, d=""):
    return os.environ.get(k, d).strip()


def on(k, d="on"):
    return env(k, d).lower() not in ("off", "no", "0", "false")


def split_list(raw):
    """Sources are separated by semicolons (so a topic like "Springfield, Illinois" stays whole)."""
    return [x.strip() for x in re.split(r"[\n;]+", raw or "") if x.strip()]


# ------------------------------------------------------------------ fetching
_wiki_lock, _wiki_last = threading.Lock(), [0.0]


def _get(url, timeout=15, limit=3_000_000, tries=3):
    """Download a page. If the site says "too many requests" (429) or "busy" (503), wait the
    time it asks for (up to 15 seconds) and try again."""
    import urllib.error
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Api-User-Agent": UA, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                ctype = r.headers.get("Content-Type", "")
                return r.geturl(), ctype, r.read(limit).decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code not in (429, 503) or attempt == tries - 1:
                raise
            try:
                wait = float(e.headers.get("Retry-After") or 0)
            except ValueError:
                wait = 0
            time.sleep(min(15, max(wait, 3 * (attempt + 1))))


def _wiki_api(params):
    """One Wikipedia request at a time, at least a second apart (Wikipedia's polite pace)."""
    q = urllib.parse.urlencode(dict(params, format="json", formatversion="2", maxlag="5"))
    with _wiki_lock:
        gap = time.time() - _wiki_last[0]
        if gap < 1.2:
            time.sleep(1.2 - gap)
        try:
            return json.loads(_get("https://en.wikipedia.org/w/api.php?" + q)[2])
        finally:
            _wiki_last[0] = time.time()


def _strip_tags(s):
    s = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", s, flags=re.S)
    s = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<sup[^>]*>.*?</sup>", "", s, flags=re.S | re.I)      # footnote markers like [1]
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\[\s*(\d+|[a-z]|citation needed|note \d+)\s*\]", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip()


_PRONOUN_START = re.compile(r"^(It|Its|It's|He|She|His|Her|They|Their|Them|This|These|Those|That|There|Here|Such|Both|Each|Other|Another|However|Also|In addition|Additionally|Furthermore|Moreover)\b")
# "The city has..." (but not "The University of Arkansas...")
_GENERIC_START = re.compile(r"^The (city|town|village|state|county|team|club|band|group|company|university|college|school|show|series|film|movie|game|park|museum|river|lake|area|region|island|country|nation|franchise|album|song|station|network)\b(?= (?!of\b)[a-z])")


def sentences(text, title="", limit=40):
    """Good stand-alone 'Did you know?' sentences from plain article text."""
    short = re.sub(r"\s*\(.*?\)\s*", " ", title).split(",")[0].strip()
    text = re.sub(r"\([^()]*[;ˈ/][^()]*\)", "", text)       # pronunciations like (/ˈfeɪ.ət.vɪl/; ...)
    text = re.sub(r"\s+", " ", text)
    out = []
    for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"“])", text):
        s = s.strip()
        if not (45 <= len(s) <= 230) or not s[-1] in ".!?":
            continue
        if "==" in s or "http" in s or s.count('"') % 2 or s.count("(") != s.count(")"):
            continue
        if re.search(r"\b(see also|references|external links|citation|this article|wikipedia)\b", s, re.I):
            continue
        if _PRONOUN_START.match(s):
            continue                                        # "It was built..." makes no sense on its own
        if short and re.match(r"^The (population|name|economy|climate|history)\b", s):
            s = re.sub(r"^The ", short + "'s ", s, count=1)       # "The population was..." -> "Springfield's population was..."
        elif _GENERIC_START.match(s):
            if not short:
                continue
            s = _GENERIC_START.sub(short, s, count=1)      # "The city has..." -> "Springfield has..."
        if s not in out:
            out.append(s)
    # facts with numbers in them tend to be the interesting ones
    out.sort(key=lambda s: 0 if re.search(r"\d", s) else 1)
    return out[:limit]


def _page_facts(page, fallback_title):
    text = page.get("extract") or ""
    # stop before the reference-style sections at the end
    text = re.split(r"\n\s*(See also|References|Notes|Further reading|External links|Bibliography|Sources)\s*\n", text)[0]
    return sentences(text.replace("\n", " "), page.get("title", fallback_title))


def wiki_topic(query):
    """Search Wikipedia for a topic and read the best article, all in one request. -> (facts, title)"""
    j = _wiki_api({"action": "query", "generator": "search", "gsrsearch": query, "gsrlimit": 1, "gsrnamespace": 0,
                   "prop": "extracts", "explaintext": 1, "exsectionformat": "plain", "redirects": 1})
    pages = (j.get("query") or {}).get("pages") or []
    if not pages:
        raise RuntimeError(f'Wikipedia has no article for "{query}"')
    return _page_facts(pages[0], query), pages[0].get("title", query)


def wiki_title(query):
    """Best matching Wikipedia article for a topic."""
    j = _wiki_api({"action": "query", "list": "search", "srsearch": query, "srlimit": 1, "srnamespace": 0})
    hits = (j.get("query") or {}).get("search") or []
    if not hits:
        raise RuntimeError(f'Wikipedia has no article for "{query}"')
    return hits[0]["title"]


def wiki_facts(title):
    j = _wiki_api({"action": "query", "prop": "extracts", "explaintext": 1, "exsectionformat": "plain",
                   "redirects": 1, "titles": title})
    pages = (j.get("query") or {}).get("pages") or []
    if not pages or pages[0].get("missing"):
        raise RuntimeError(f'no Wikipedia article called "{title}"')
    return _page_facts(pages[0], title)


def _sheet_csv(url):
    m = re.search(r"docs\.google\.com/spreadsheets/d/([\w-]+)", url)
    if not m:
        return None
    gid = re.search(r"[#&?]gid=(\d+)", url)
    return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv" + (f"&gid={gid.group(1)}" if gid else "")


def _rows(text, is_csv):
    """Lines of a text file or rows of a CSV, as lists of cells."""
    if is_csv:
        return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text)) if any(c.strip() for c in row)]
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append([c.strip() for c in line.split("|")] if "|" in line else [line])
    return out


def _looks_like_file(url, ctype):
    return bool(re.search(r"\.(txt|csv|tsv)(\?|$)", url, re.I)) or "text/plain" in ctype or "text/csv" in ctype


def facts_from(src):
    """-> (list of facts, where they came from)"""
    src = src.strip()
    if not re.match(r"^https?://", src) and not re.match(r"^[\w.-]+\.[a-z]{2,}(/|$)", src, re.I):
        items, title = wiki_topic(src)                           # plain words: a Wikipedia topic
        return items, f"Wikipedia: {title}"
    url = src if src.startswith("http") else "https://" + src
    m = re.search(r"\b([a-z]{2,3})(?:\.m)?\.wikipedia\.org/wiki/([^?#]+)", url)
    if m and m.group(1) == "en":
        title = urllib.parse.unquote(m.group(2)).replace("_", " ")
        return wiki_facts(title), f"Wikipedia: {title}"
    sheet = _sheet_csv(url)
    final, ctype, text = _get(sheet or url)
    if sheet or _looks_like_file(final, ctype):
        rows = _rows(text, bool(sheet) or "csv" in ctype or final.lower().split("?")[0].endswith(".csv"))
        if rows and re.match(r"^(facts?|did you know)\b", rows[0][0], re.I):
            rows = rows[1:]                                      # a header row
        facts = [r[0] for r in rows if 10 <= len(r[0]) <= 300]
        return facts, "Google Sheet" if sheet else "your file"
    if ("<rss" in text[:3000].lower() or "<feed" in text[:3000].lower()):
        titles = [_strip_tags(t) for t in re.findall(r"<item[\s>].*?<title[^>]*>(.*?)</title>", text, re.S)]
        titles += [_strip_tags(t) for t in re.findall(r"<entry[\s>].*?<title[^>]*>(.*?)</title>", text, re.S)]
        return [t for t in titles if len(t) >= 15][:40], "RSS feed"
    # an ordinary web page: list items first (most "facts" pages are lists), else sentences
    m = re.search(r"<main\b[^>]*>(.*?)</main>", text, re.S | re.I) or re.search(r"<article\b[^>]*>(.*?)</article>", text, re.S | re.I)
    body = m.group(1) if m else text
    body = re.sub(r"<(nav|header|footer|aside)\b[^>]*>.*?</\1>", " ", body, flags=re.S | re.I)   # menus, not facts
    items = []
    for li in re.findall(r"<li\b[^>]*>(.*?)</li>", body, re.S | re.I):
        t = _strip_tags(li)
        if 40 <= len(t) <= 260 and t[-1:] in ".!?)\"" and t not in items:
            items.append(re.sub(r"^\d+[.)]\s*", "", t))
    if len(items) < 5:
        paras = " ".join(_strip_tags(p) for p in re.findall(r"<p\b[^>]*>(.*?)</p>", body, re.S | re.I))
        items += [s for s in sentences(paras) if s not in items]
    if not items:
        raise RuntimeError("couldn't find any facts on that page")
    return items[:60], urllib.parse.urlparse(final).netloc.replace("www.", "")


def _trivia_row(cells):
    cells = [c for c in cells if c != ""]
    if len(cells) >= 3 and cells[0] and cells[1]:
        return {"q": cells[0], "a": cells[1], "wrong": cells[2:5]}
    return None


def trivia_from(src):
    """Trivia from a Google Sheet or a .txt / .csv link. -> (questions, where from)"""
    src = src.strip()
    url = src if src.startswith("http") else "https://" + src
    sheet = _sheet_csv(url)
    final, ctype, text = _get(sheet or url)
    is_csv = bool(sheet) or "csv" in ctype or final.lower().split("?")[0].endswith(".csv")
    rows = _rows(text, is_csv)
    if rows and re.match(r"^question\b", rows[0][0], re.I):
        rows = rows[1:]
    out = [t for t in (_trivia_row(r) for r in rows) if t]
    if not out:
        raise RuntimeError("no questions found. Use one per line:  question | right answer | wrong | wrong | wrong")
    return out, "Google Sheet" if sheet else "your file"


def opentdb(topic):
    cat = TRIVIA_TOPICS[topic][0]
    _, _, text = _get(f"https://opentdb.com/api.php?amount=50&category={cat}&type=multiple&encode=url3986")
    j = json.loads(text)
    if j.get("response_code") not in (0, None):
        raise RuntimeError(f"Open Trivia Database said code {j.get('response_code')}")
    dec = urllib.parse.unquote
    return [{"q": dec(r["question"]), "a": dec(r["correct_answer"]), "wrong": [dec(w) for w in r["incorrect_answers"]][:3]}
            for r in j.get("results", [])]


def local_titles():
    """Wikipedia articles for your town and state, from CITY_NAME."""
    city = env("CITY_NAME")
    if not city:
        return []
    states = {"AL":"Alabama","AK":"Alaska","AZ":"Arizona","AR":"Arkansas","CA":"California","CO":"Colorado","CT":"Connecticut","DE":"Delaware",
              "FL":"Florida","GA":"Georgia (U.S. state)","HI":"Hawaii","ID":"Idaho","IL":"Illinois","IN":"Indiana","IA":"Iowa","KS":"Kansas","KY":"Kentucky",
              "LA":"Louisiana","ME":"Maine","MD":"Maryland","MA":"Massachusetts","MI":"Michigan","MN":"Minnesota","MS":"Mississippi","MO":"Missouri",
              "MT":"Montana","NE":"Nebraska","NV":"Nevada","NH":"New Hampshire","NJ":"New Jersey","NM":"New Mexico","NY":"New York (state)",
              "NC":"North Carolina","ND":"North Dakota","OH":"Ohio","OK":"Oklahoma","OR":"Oregon","PA":"Pennsylvania","RI":"Rhode Island",
              "SC":"South Carolina","SD":"South Dakota","TN":"Tennessee","TX":"Texas","UT":"Utah","VT":"Vermont","VA":"Virginia","WA":"Washington (state)",
              "WV":"West Virginia","WI":"Wisconsin","WY":"Wyoming","DC":"Washington, D.C."}
    parts = [p.strip() for p in city.split(",")]
    town, region = parts[0], (parts[1] if len(parts) > 1 else "")
    region = states.get(region.upper(), region)
    out = [wiki_title(f"{town}, {region.split(' (')[0]}" if region else town)]
    if region:
        out.append(region if region in states.values() else wiki_title(region))
    return out


# ------------------------------------------------------------------ cache & refresh
def _load():
    global _cache
    try:
        with open(CACHE_FILE, encoding="utf-8") as f:
            _cache = json.load(f)
    except (OSError, ValueError):
        _cache = {}


def _save():
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        tmp = CACHE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_cache, f)
        os.replace(tmp, CACHE_FILE)
    except OSError:
        pass


def _wanted():
    """Every online source currently turned on -> {cache key: fetch function}"""
    jobs = {}
    for s in split_list(env("FACTS_SOURCES")):
        jobs["facts:" + s] = (lambda s=s: facts_from(s))
    if on("FACTS_LOCAL", "off"):
        jobs["facts:@local:" + env("CITY_NAME")] = _local
    for t in [x.strip() for x in env("TRIVIA_TOPICS").lower().split(",")]:
        if t in TRIVIA_TOPICS:
            jobs["trivia:@otdb:" + t] = (lambda t=t: (opentdb(t), "Open Trivia Database"))
    for s in split_list(env("TRIVIA_SOURCES")):
        jobs["trivia:" + s] = (lambda s=s: trivia_from(s))
    return jobs


def _local():
    facts, names = [], []
    for title in local_titles():
        facts += wiki_facts(title)
        names.append(title)
    return facts, "Wikipedia: " + " & ".join(names)


def refresh(force=False):
    jobs = _wanted()
    for key, fn in jobs.items():
        with _lock:
            hit = _cache.get(key)
        if hit and not force and time.time() - hit.get("t", 0) < (REFRESH if hit.get("items") else 1800):
            continue
        try:
            items, where = fn()
            if key.startswith("trivia:@otdb:") and hit and hit.get("items"):
                seen = {x["q"] for x in items}                     # build up a bigger pool over time
                items = items + [x for x in hit["items"] if x["q"] not in seen]
                items = items[:300]
            entry = {"t": time.time(), "items": items, "from": where, "error": None}
        except Exception as e:
            entry = dict(hit or {"items": []}, t=time.time(), error=friendly(e))
            print(f"[facts] {key}: {entry['error']}", flush=True)
        with _lock:
            _cache[key] = entry
        if key.startswith("trivia:@otdb:"):
            time.sleep(6)                                           # Open Trivia DB allows one request per 5 seconds
    with _lock:
        for k in [k for k in _cache if k not in jobs]:            # sources you took out
            del _cache[k]
    _save()


def _loop():
    time.sleep(5)
    while True:
        try:
            refresh()
        except Exception as e:
            print("[facts] refresh failed:", e, flush=True)
        _wake.wait(900)
        _wake.clear()


def start():
    _load()
    threading.Thread(target=_loop, daemon=True).start()


def all_facts(file_facts):
    out = list(file_facts) if on("FACTS_LIST") else []
    with _lock:
        for k, v in _cache.items():
            if k.startswith("facts:"):
                out += v.get("items") or []
    seen, uniq = set(), []
    for f in out:
        if f not in seen:
            seen.add(f)
            uniq.append(f)
    return uniq


def all_trivia(file_trivia):
    out = list(file_trivia) if on("TRIVIA_LIST") else []
    with _lock:
        for k, v in _cache.items():
            if k.startswith("trivia:"):
                out += v.get("items") or []
    return out


def status():
    with _lock:
        return {k: {"from": v.get("from"), "count": len(v.get("items") or []), "error": v.get("error"),
                    "age_min": int((time.time() - v.get("t", 0)) / 60)} for k, v in _cache.items()}


def friendly(e):
    """Network errors in plain words."""
    import urllib.error, socket
    if isinstance(e, urllib.error.HTTPError):
        return {404: "that page doesn't exist (404)", 403: "that site doesn't allow KNAS to read it (403)",
                429: "that site is getting too many requests right now. KNAS will keep trying by itself every half hour",
                503: "that site is busy right now. KNAS will keep trying by itself every half hour",
                401: "that link needs a login. For a Google Sheet, use Share > Anyone with the link"}.get(e.code, f"the site answered with error {e.code}")
    if isinstance(e, (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError)):
        return "couldn't reach that site. Check the link and that KNAS has internet"
    return str(e)


def check(kind, src):
    """For the setup page's Check button. Uses what KNAS already fetched when it's recent,
    so pressing Check over and over doesn't hammer the site."""
    key = {"trivia": ("trivia:@otdb:" + src.lower()) if src.lower() in TRIVIA_TOPICS else "trivia:" + src}.get(kind)
    key = key or ("facts:@local:" + env("CITY_NAME") if src == "@local" else "facts:" + src)
    with _lock:
        hit = _cache.get(key)
    if hit and hit.get("items") and time.time() - hit.get("t", 0) < REFRESH:
        items = hit["items"]
        sample = random.sample(items, min(2, len(items)))
        if kind == "trivia":
            sample = [f'{t["q"]}  ({t["a"]})' for t in sample]
        return {"ok": True, "count": len(items), "from": hit.get("from") or "saved", "sample": sample}
    try:
        if kind == "trivia":
            if src.lower() in TRIVIA_TOPICS:
                items, where = opentdb(src.lower()), "Open Trivia Database"
            else:
                items, where = trivia_from(src)
            sample = [f'{t["q"]}  ({t["a"]})' for t in random.sample(items, min(2, len(items)))]
        elif src == "@local":
            items, where = _local()
            sample = random.sample(items, min(2, len(items)))
        else:
            items, where = facts_from(src)
            sample = random.sample(items, min(2, len(items)))
        if not items:
            return {"ok": False, "message": "found nothing to use there"}
        with _lock:
            _cache[key] = {"t": time.time(), "items": items, "from": where, "error": None}   # saves a second download later
        return {"ok": True, "count": len(items), "from": where, "sample": sample}
    except Exception as e:
        return {"ok": False, "message": friendly(e)}
