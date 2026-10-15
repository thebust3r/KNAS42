"""KNAS 42 for Windows.

One program that runs KNAS on your PC: an icon by the clock, the setup page in its own window, and
KNAS started (and kept running) in the background. Your KNAS folder (settings, music, update zips)
lives in %LOCALAPPDATA%\\KNAS42; "Open KNAS folder" in the tray menu takes you there.

  KNAS42.exe              start KNAS (or, if it's already running, open its window)
  KNAS42.exe --background start KNAS without opening a window (used when Windows starts)
  KNAS42.exe --server DIR run the KNAS server itself (the tray app starts this; you never need to)
"""
import os, re, sys, time, json, shutil, socket, threading, subprocess, webbrowser, urllib.request
try:
    import knas_std_imports  # noqa: F401  (made at build time: the whole standard library goes into the app)
except ImportError:
    pass

APP_NAME = "KNAS 42"
PORT = 8642
WIN = os.name == "nt"
FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(sys.executable if FROZEN else os.path.abspath(__file__))
SEED = os.path.join(getattr(sys, "_MEIPASS", HERE), "knas")              # the KNAS that came with this version
HOME = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "KNAS42")
LOG = os.path.join(HOME, "data", "knas-windows.log")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NO_WINDOW = 0x08000000                                                     # CREATE_NO_WINDOW


# ============================================================ the server (KNAS42.exe --server DIR)

def run_server(folder):
    """Runs KNAS itself, in this process. Started by the tray app with no window; output goes to the log."""
    os.environ["KNAS_SUPERVISED"] = "1"                 # a settings change asks for a restart: the tray app does it
    os.chdir(folder)
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        if os.path.exists(LOG) and os.path.getsize(LOG) > 5 * 1024 * 1024:
            os.replace(LOG, LOG + ".old")
        out = open(LOG, "a", buffering=1, encoding="utf-8", errors="replace")
        sys.stdout = sys.stderr = out
    except OSError:
        pass
    if WIN:
        # programs KNAS runs (yt-dlp, ffmpeg) shouldn't flash a black window on the screen
        _Popen = subprocess.Popen

        class Quiet(_Popen):
            def __init__(self, *a, **kw):
                if not kw.get("creationflags"):
                    kw["creationflags"] = NO_WINDOW
                super().__init__(*a, **kw)
        subprocess.Popen = Quiet
        ff = find_ffmpeg()
        if ff:
            os.environ["PATH"] = os.path.dirname(ff) + os.pathsep + os.environ.get("PATH", "")
    import runpy
    sys.argv = [os.path.join(folder, "server.py")]
    sys.path.insert(0, os.path.join(folder, "app"))
    print(f"[windows] KNAS 42 starting from {folder}", flush=True)
    runpy.run_path(os.path.join(folder, "server.py"), run_name="__main__")


def find_ffmpeg():
    """ffmpeg for the radio and video tools: one on the PATH, or the one that comes with ErsatzTV for Windows."""
    p = shutil.which("ffmpeg")
    if p:
        return p
    roots = [os.environ.get(k, "") for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "USERPROFILE")]
    roots += [f"{d}:\\" for d in "CDEF"]
    for r in filter(None, roots):
        for sub in ("ErsatzTV", r"ErsatzTV\ffmpeg", "ffmpeg\\bin", "ffmpeg"):
            c = os.path.join(r, sub, "ffmpeg.exe")
            if os.path.isfile(c):
                return c
        try:                                             # folders like D:\ErsatzTV-v25.1-win-x64
            for name in os.listdir(r):
                if "ersatz" in name.lower():
                    for base, _d, files in os.walk(os.path.join(r, name)):
                        if "ffmpeg.exe" in files:
                            return os.path.join(base, "ffmpeg.exe")
                        if base.count(os.sep) - r.count(os.sep) > 3:
                            break
        except OSError:
            pass
    return None


# ============================================================ setting up the KNAS folder

KEEP = {"settings.txt", "teams.txt", "facts.txt", "trivia.txt"}
USER_DIRS = {"music", "updates", "break-videos", "break-clips", "data"}


def version(root):
    try:
        m = re.search(r'^VERSION = "([^"]+)"', open(os.path.join(root, "app", "server.py"), encoding="utf-8").read(), re.M)
        return m.group(1) if m else ""
    except OSError:
        return ""


def rank(v):
    nums = ([int(x) for x in re.findall(r"\d+", v or "")[:3]] + [0, 0, 0])[:3]
    return (0 if (nums[0] == 2 and 6 <= nums[1] <= 22) else 1, nums) if v else (-1, nums)


def prepare_folder():
    """First start: put KNAS in the KNAS folder. A newer app version: update the code there (your settings,
    music and so on stay). A folder that's already newer (from an update zip) is never downgraded."""
    os.makedirs(HOME, exist_ok=True)
    have, new = version(HOME), version(SEED)
    fresh = not os.path.exists(os.path.join(HOME, "server.py"))
    update = not fresh and new and rank(new) > rank(have)
    for base, dirs, files in os.walk(SEED):
        rel_dir = os.path.relpath(base, SEED)
        top = rel_dir.split(os.sep)[0]
        if update and top in USER_DIRS:
            dirs[:] = []
            continue
        os.makedirs(os.path.join(HOME, rel_dir), exist_ok=True)
        for f in files:
            rel = os.path.normpath(os.path.join(rel_dir, f))
            dest = os.path.join(HOME, rel)
            if os.path.exists(dest) and (not update or rel in KEEP or top in USER_DIRS):
                continue
            shutil.copyfile(os.path.join(base, f), dest + ".new")
            os.replace(dest + ".new", dest)
    for d in ("music", "updates", "break-videos", "data"):
        os.makedirs(os.path.join(HOME, d), exist_ok=True)
    if fresh:
        set_setting("BREAK_CLIPS_ON", "off")          # the break-clip recorder is a Docker-only extra
    if not get_setting("ERSATZTV_URL") and ersatztv_here():
        set_setting("ERSATZTV_URL", "http://127.0.0.1:8409")      # ErsatzTV for Windows on this same PC
    return fresh


def set_setting(key, value):
    p = os.path.join(HOME, "settings.txt")
    try:
        text = open(p, encoding="utf-8").read()
    except OSError:
        text = ""
    if re.search(rf"^{key}=.*$", text, re.M):
        text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, count=1, flags=re.M)
    else:
        text += f"\n{key}={value}\n"
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)


def get_setting(key):
    try:
        m = re.search(rf"^{key}=(.*)$", open(os.path.join(HOME, "settings.txt"), encoding="utf-8").read(), re.M)
        return m.group(1).strip() if m else ""
    except OSError:
        return ""


def ersatztv_here():
    """ErsatzTV for Windows running on this same PC?"""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8409/iptv/channels.m3u", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


# ============================================================ helpers

def lan_ip():
    """This PC's address on the home network (192.168.x.x), skipping VPN and Tailscale addresses."""
    found = []
    for probe in ("192.168.255.255", "172.31.255.255", "10.255.255.255"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((probe, 1))
            found.append(s.getsockname()[0])
            s.close()
        except OSError:
            pass
    try:
        found += [a[4][0] for a in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass

    def score(ip):
        try:
            p = [int(x) for x in ip.split(".")]
        except ValueError:
            return 0
        if p[0] in (0, 127) or (p[0] == 169 and p[1] == 254) or (p[0] == 100 and 64 <= p[1] <= 127):
            return 0
        if p[0] == 192 and p[1] == 168:
            return 5
        if p[0] == 172 and 16 <= p[1] <= 31:
            return 3
        if p[0] == 10:
            return 1 if p[1] in (2, 5, 8, 64, 96, 124) else 4      # ProtonVPN and other VPNs use these
        return 1
    best = max(found, key=score, default="")
    return best if best and score(best) else "127.0.0.1"


def knas_up(timeout=1.5):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/api/version", timeout=timeout) as r:
            return json.loads(r.read().decode()).get("version", "?")
    except Exception:
        return None


def port_taken():
    s = socket.socket()
    try:
        s.bind(("0.0.0.0", PORT))
        return False
    except OSError:
        return True
    finally:
        s.close()


def edge():
    for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", ""), os.environ.get("LOCALAPPDATA", "")):
        p = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
        if base and os.path.isfile(p):
            return p
    return None


def open_window(path="/setup"):
    """KNAS in its own app window (no browser tabs or address bar). Falls back to the normal browser."""
    url = f"http://localhost:{PORT}{path}"
    e = edge() if WIN else None
    if e:
        try:
            subprocess.Popen([e, f"--app={url}", "--window-size=1180,860", "--no-first-run"], creationflags=NO_WINDOW if WIN else 0)
            return
        except OSError:
            pass
    webbrowser.open(url)


def open_folder():
    if WIN:
        os.startfile(HOME)
    else:
        webbrowser.open("file://" + HOME)


def startup_enabled():
    if not WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_startup(on):
    if not WIN:
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, f'"{sys.executable}" --background')
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except OSError:
                pass


def copy_text(text):
    try:
        subprocess.run(["clip"], input=text.encode("utf-16-le"), creationflags=NO_WINDOW, check=False)
    except OSError:
        pass


def single_instance():
    """Only one KNAS app at a time. Returns False when another one is already running."""
    if not WIN:
        return True
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\KNAS42-tray")
    return ctypes.windll.kernel32.GetLastError() != 183          # ERROR_ALREADY_EXISTS


# ============================================================ keeping KNAS running

class Runner:
    def __init__(self, on_change):
        self.proc = None
        self.quitting = False
        self.state = "Starting…"
        self.version = ""
        self.starts = []
        self.on_change = on_change

    def cmd(self):
        if FROZEN:
            return [sys.executable, "--server", HOME]
        return [sys.executable, os.path.abspath(__file__), "--server", HOME]

    def start(self):
        threading.Thread(target=self.loop, daemon=True).start()

    def loop(self):
        while not self.quitting:
            if port_taken() and not knas_up():
                self.set("Port 8642 is in use by another program")
                time.sleep(10)
                continue
            self.starts = [t for t in self.starts if time.time() - t < 120] + [time.time()]
            if len(self.starts) > 6:
                self.set("KNAS keeps stopping: see the log in the KNAS folder")
                time.sleep(60)
                self.starts = []
                continue
            self.set("Starting…")
            try:
                self.proc = subprocess.Popen(self.cmd(), creationflags=NO_WINDOW if WIN else 0, cwd=HOME)
            except OSError as e:
                self.set(f"Couldn't start KNAS ({e})")
                time.sleep(10)
                continue
            threading.Thread(target=self.watch_up, args=(self.proc,), daemon=True).start()
            code = self.proc.wait()
            if self.quitting:
                break
            if code == 75:                                  # KNAS asked for a restart (settings changed, update)
                self.starts.pop()
            self.set("Restarting…")
            time.sleep(1)

    def watch_up(self, proc):
        for _ in range(120):
            if proc.poll() is not None:
                return
            v = knas_up()
            if v:
                self.version = v
                self.set("On the air")
                return
            time.sleep(0.5)

    def set(self, s):
        self.state = s
        try:
            self.on_change()
        except Exception:
            pass

    def restart(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def stop(self):
        self.quitting = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(8)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# ============================================================ the tray icon

def tray(background):
    import pystray
    from PIL import Image

    icon_path = os.path.join(getattr(sys, "_MEIPASS", HERE), "knas.ico")
    try:
        image = Image.open(icon_path)
    except OSError:
        image = Image.new("RGB", (64, 64), (11, 20, 80))
    tv_url = lambda: f"http://{lan_ip()}:{PORT}/tv"
    announced = {"done": False}

    def changed():
        ic.title = f"{APP_NAME}: {runner.state}"
        ic.update_menu()
        if runner.state == "On the air" and not announced["done"]:
            announced["done"] = True
            try:
                ic.notify(f"Watch on any TV or phone at {tv_url()}", f"{APP_NAME} is on the air")
            except Exception:
                pass
            if not background:
                open_window("/setup")

    runner = Runner(changed)

    def status(_):
        v = f" (version {runner.version})" if runner.version and runner.state == "On the air" else ""
        return ("● " if runner.state == "On the air" else "○ ") + runner.state + v

    menu = pystray.Menu(
        pystray.MenuItem(status, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open KNAS (setup)", lambda: open_window("/setup"), default=True),
        pystray.MenuItem("Watch here", lambda: open_window("/tv")),
        pystray.MenuItem("Phone remote", lambda: open_window("/phone")),
        pystray.MenuItem(lambda _: "Copy the TV address  (" + tv_url() + ")", lambda: copy_text(tv_url())),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Open KNAS folder", lambda: open_folder()),
        pystray.MenuItem("Start with Windows", lambda: set_startup(not startup_enabled()), checked=lambda _: startup_enabled()),
        pystray.MenuItem("Restart KNAS", lambda: runner.restart()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit KNAS", lambda: (runner.stop(), ic.stop())),
    )
    ic = pystray.Icon("KNAS42", image, f"{APP_NAME}: starting…", menu)

    def setup(icon):
        icon.visible = True
        runner.start()
    ic.run(setup=setup)
    runner.stop()


def main():
    args = sys.argv[1:]
    if args[:1] == ["--server"]:
        return run_server(args[1] if len(args) > 1 else HOME)
    if args[:1] == ["-u"] and len(args) > 1:            # an old-style restart request: run the server it names
        return run_server(os.path.dirname(os.path.abspath(args[1])))
    background = "--background" in args
    if not single_instance():
        if not background:                               # already running: just bring up its window
            open_window("/setup")
        return
    try:
        prepare_folder()
    except OSError as e:
        if WIN:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"KNAS couldn't set up its folder at {HOME}:\n{e}", APP_NAME, 0x10)
        return
    tray(background)


if __name__ == "__main__":
    main()
