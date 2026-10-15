"""Keeps KNAS up to date by itself.

- settings.txt  : all your settings (KEY=VALUE). Saving it restarts KNAS in a few seconds.
- updates/      : drop a KNAS update .zip here. It gets unpacked (your settings, teams, facts,
                  trivia, music and clips are kept) and KNAS restarts on the new version.
- app/*.py      : if the code changes, KNAS restarts.
A log of what happened is written to updates/update-log.txt.
"""
import os, sys, time, threading, zipfile, shutil, py_compile, tempfile, traceback

APP = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.dirname(APP)                      # your KNAS folder (paths below are relative to it)
SETTINGS = os.path.join(HERE, "settings.txt")
UPDATES = os.path.join(HERE, "updates")
DATA = os.path.join(HERE, "data")
MODULES = ["server.py", "sports.py", "keeper.py", "radio.py", "clips.py", "wizard.py", "looks.py", "clock.py", "facts.py", "tools.py", "remote.py", "mediaserver.py", "history.py", "gametime.py", "party.py", "jukebox_dl.py", "qr.py", "alerts.py", "game.py", "game_content.py", "securecert.py", "ws.py", "throw.py", "livecam.py", "voice.py", "duck.py", "fun.py", "flick.py", "stream.py"]
CODE = ["server.py"] + ["app/" + m for m in MODULES]
KEEP_IF_PRESENT = {"settings.txt", "teams.txt", "facts.txt", "trivia.txt"}   # yours: never overwritten by an update
NEVER = {"docker-compose.yml"}                                 # left alone so the project setup never changes
SKIP_DIRS = {"music", "updates", "break-videos", "break-clips", "break-clips-working", "data"}


def migrate():
    """Tidies folders from older versions. Nothing of yours is ever deleted: old files are
    moved into data/old-files instead."""
    os.makedirs(DATA, exist_ok=True)
    _open_perms(DATA, True)
    old = os.path.join(DATA, "old-files")
    moved = []
    def stash(name):
        src = os.path.join(HERE, name)
        if not os.path.exists(src):
            return
        os.makedirs(old, exist_ok=True)
        dest = os.path.join(old, name)
        if os.path.exists(dest):
            dest += time.strftime("-%Y%m%d%H%M%S")
        try:
            shutil.move(src, dest)
            moved.append(name)
        except OSError:
            pass
    # caches and logs now live in data/
    for name in ("location-cache.json", "cities-cache.json", "settings.backup.txt", "break-clips-log.txt"):
        src, dest = os.path.join(HERE, name), os.path.join(DATA, name)
        if os.path.exists(src):
            try:
                if not os.path.exists(dest):
                    shutil.move(src, dest)
                else:
                    os.remove(src)
                moved.append(name)
            except OSError:
                pass
    shutil.rmtree(os.path.join(HERE, "break-clips-working"), ignore_errors=True)
    shutil.rmtree(os.path.join(HERE, "__pycache__"), ignore_errors=True)
    # code moved into app/; ErsatzTV and Windows helpers moved into extras/
    for m in MODULES:
        if m != "server.py" and os.path.exists(os.path.join(APP, m)):
            stash(m)
    if os.path.isdir(os.path.join(HERE, "extras")):
        for d in ("ersatztv", "windows"):
            stash(d)
    if moved:
        log("tidied up old files: " + ", ".join(moved) + " (older copies are in data/old-files)")


def log(msg):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    print("[updater]", msg, flush=True)
    try:
        os.makedirs(UPDATES, exist_ok=True)
        with open(os.path.join(UPDATES, "update-log.txt"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def load_settings():
    """Read settings.txt into the environment. Values here win over docker-compose."""
    loaded = {}
    try:
        with open(SETTINGS, encoding="utf-8-sig") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                if k:
                    os.environ[k] = v
                    loaded[k] = v
    except OSError:
        pass
    return loaded


def _open_perms(path, is_dir=False):
    try:
        os.chmod(path, 0o777 if is_dir else 0o666)   # so you can still edit the files from your PC
    except OSError:
        pass


def _compiles(path):
    try:
        py_compile.compile(path, doraise=True, cfile=os.path.join(tempfile.gettempdir(), "knas_check.pyc"))
        return True
    except Exception as e:
        log(f"not restarting: {os.path.basename(path)} has an error ({e.__class__.__name__}: {e})")
        return False


def apply_zip(zpath):
    with zipfile.ZipFile(zpath) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        prefix = ""
        if "server.py" not in names:
            hits = [n for n in names if n.endswith("/server.py") and n.count("/") == 1]
            if not hits:
                raise ValueError("this zip doesn't look like a KNAS update (no server.py)")
            prefix = hits[0][: -len("server.py")]
        work = tempfile.mkdtemp(prefix="knas_update_")
        plan = []
        for n in names:
            if not n.startswith(prefix):
                continue
            rel = n[len(prefix):]
            if not rel or rel.split("/")[0] in SKIP_DIRS or rel in NEVER:
                continue
            if rel in KEEP_IF_PRESENT and os.path.exists(os.path.join(HERE, rel)):
                continue
            dest = os.path.realpath(os.path.join(HERE, rel))
            if not dest.startswith(os.path.realpath(HERE) + os.sep):
                continue
            tmp = os.path.join(work, rel)
            os.makedirs(os.path.dirname(tmp), exist_ok=True)
            with z.open(n) as src, open(tmp, "wb") as out:
                shutil.copyfileobj(src, out)
            plan.append((tmp, dest, rel))
        for tmp, _, rel in plan:  # refuse an update whose code doesn't even load
            if rel in CODE and not _compiles(tmp):
                shutil.rmtree(work, ignore_errors=True)
                raise ValueError(f"{rel} in the update has an error, nothing was changed")
        for tmp, dest, rel in plan:
            d = os.path.dirname(dest)
            if not os.path.isdir(d):
                os.makedirs(d, exist_ok=True)
                _open_perms(d, True)
            shutil.copyfile(tmp, dest + ".new")
            os.replace(dest + ".new", dest)
            _open_perms(dest)
        shutil.rmtree(work, ignore_errors=True)
        return [rel for _, _, rel in plan]


def _snapshot():
    out = {}
    for name in CODE + ["settings.txt"]:
        p = os.path.join(HERE, name)
        try:
            st = os.stat(p)
            out[name] = (st.st_mtime, st.st_size)
        except OSError:
            out[name] = None
    return out


def restart(reason):
    log(f"restarting: {reason}")
    time.sleep(0.5)
    if os.environ.get("KNAS_SUPERVISED"):        # the Windows app runs KNAS and starts it again by itself
        os._exit(75)
    os.execv(sys.executable, [sys.executable, "-u", os.path.join(HERE, "server.py")])   # the launcher in your KNAS folder


def _watch():
    os.makedirs(UPDATES, exist_ok=True)
    _open_perms(UPDATES, True)
    seen, pending, zips = _snapshot(), None, {}
    while True:
        time.sleep(2)
        try:
            # 1) update zips dropped into updates/
            for f in sorted(os.listdir(UPDATES)):
                p = os.path.join(UPDATES, f)
                if not f.lower().endswith(".zip") or not os.path.isfile(p):
                    continue
                st = os.stat(p)
                sig = (st.st_size, st.st_mtime)
                if zips.get(f) != sig:          # still copying? wait until it stops changing
                    zips[f] = sig
                    continue
                log(f"found update {f}")
                done = os.path.join(UPDATES, "done")
                os.makedirs(done, exist_ok=True)
                _open_perms(done, True)
                try:
                    changed = apply_zip(p)
                    shutil.move(p, os.path.join(done, time.strftime("%Y%m%d-%H%M%S-") + f))
                    log(f"installed {f}: {len(changed)} files updated")
                    restart(f"update {f}")
                except Exception as e:
                    shutil.move(p, os.path.join(done, time.strftime("%Y%m%d-%H%M%S-FAILED-") + f))
                    log(f"update {f} failed: {e}")
            # 2) code or settings edited directly
            now = _snapshot()
            if now != seen:
                if pending != now:              # wait for the copy/save to settle
                    pending = now
                    continue
                changed = [k for k in now if now[k] != seen.get(k)]
                if all(_compiles(os.path.join(HERE, k)) for k in changed if k in CODE and now[k]):
                    restart("changed " + ", ".join(changed))
                seen, pending = now, None
        except Exception:
            log("watcher error: " + traceback.format_exc().splitlines()[-1])


def start_watcher():
    try:
        migrate()
    except Exception:
        log("tidy-up skipped: " + traceback.format_exc().splitlines()[-1])
    threading.Thread(target=_watch, daemon=True, name="knas-updater").start()
