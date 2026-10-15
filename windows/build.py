"""Gets everything ready for building KNAS 42 for Windows (run from the repo folder):
  - build/knas: the KNAS files the app sets up on a PC (no Docker, Android, iPhone, Xbox or Samsung parts)
  - windows/knas_std_imports.py: every standard Python module, so KNAS updates that use new ones still work
  - build/knas.ico and the installer pictures, made from the KNAS icon
"""
import os, re, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "build")
SEED = os.path.join(OUT, "knas")
TAKE = ["app", "web", "server.py", "settings.txt", "teams.txt", "facts.txt", "trivia.txt", "music", "updates",
        "break-videos", "extras", "LICENSE"]


def seed():
    shutil.rmtree(SEED, ignore_errors=True)
    os.makedirs(SEED)
    for name in TAKE:
        src = os.path.join(ROOT, name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(SEED, name), ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif os.path.isfile(src):
            shutil.copyfile(src, os.path.join(SEED, name))
    print("seed:", sorted(os.listdir(SEED)))


SKIP = {"tkinter", "turtle", "turtledemo", "idlelib", "test", "lib2to3", "ensurepip", "venv", "pydoc_data", "this",
        "antigravity", "__phello__", "_pyrepl", "xxsubtype", "xxlimited", "xxlimited_35", "_testcapi", "_testinternalcapi",
        "_testbuffer", "_testimportmultiple", "_testmultiphase", "_ctypes_test", "_xxtestfuzz", "_testsinglephase",
        "_testclinic", "_testconsole", "msilib", "nis", "spwd", "crypt", "ossaudiodev", "readline", "curses", "_curses",
        "_curses_panel", "dbm", "_dbm", "_gdbm", "grp", "pwd", "posix", "termios", "tty", "pty", "fcntl", "resource",
        "syslog", "_posixsubprocess", "_posixshmem", "_scproxy", "_tkinter", "_uuid", "_lzma"}


def std_imports():
    names = []
    for n in sorted(getattr(sys, "stdlib_module_names", ())):
        if n in SKIP or n.startswith("_test"):
            continue
        try:
            __import__(n)
        except Exception:
            continue
        names.append(n)
    with open(os.path.join(ROOT, "windows", "knas_std_imports.py"), "w") as f:
        f.write("# made by windows/build.py: bundles the whole standard library into the app\n")
        for n in names:
            f.write(f"try:\n    import {n}  # noqa\nexcept Exception:\n    pass\n")
    print(len(names), "standard modules")


def font(size, bold=True):
    from PIL import ImageFont
    for p in (r"C:\Windows\Fonts\ariblk.ttf", r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def pictures():
    from PIL import Image, ImageDraw
    icon = Image.open(os.path.join(ROOT, "web", "icon-512.png")).convert("RGBA")
    icon.save(os.path.join(OUT, "knas.ico"), sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)])

    gold, top, bottom = (255, 210, 58), (33, 50, 140), (6, 10, 42)

    def big(w, h):
        """The tall picture on the installer's first and last pages: a KNAS cable-channel look."""
        im = Image.new("RGB", (w, h), bottom)
        d = ImageDraw.Draw(im)
        for y in range(h):                                   # navy fade
            t = y / max(1, h - 1)
            d.line([(0, y), (w, y)], fill=tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
        px = im.load()
        for y in range(0, h, 4):                             # soft TV scanlines
            for x in range(w):
                r, g, b = px[x, y]
                px[x, y] = (int(r * .7), int(g * .7), int(b * .7))
        s = int(w * 0.72)
        im.paste(icon.resize((s, s), Image.LANCZOS), ((w - s) // 2, int(h * 0.12)), icon.resize((s, s), Image.LANCZOS))
        y = int(h * 0.12) + s + int(h * 0.05)
        d.rectangle([int(w * 0.12), y, int(w * 0.88), y + max(2, h // 160)], fill=gold)
        f = font(max(10, w // 9))
        for i, line in enumerate(("YOUR OWN", "CABLE TV")):
            tw = d.textlength(line, font=f)
            d.text(((w - tw) / 2 + 2, y + h * 0.03 + i * w * 0.13 + 2), line, font=f, fill=(0, 0, 0))
            d.text(((w - tw) / 2, y + h * 0.03 + i * w * 0.13), line, font=f, fill=gold if i else (255, 255, 255))
        return im

    def small(n):
        im = Image.new("RGB", (n, n), (255, 255, 255))
        im.paste(icon.resize((n, n), Image.LANCZOS), (0, 0), icon.resize((n, n), Image.LANCZOS))
        return im

    for i, (w, h) in enumerate([(164, 314), (205, 393), (246, 471), (328, 628), (410, 785)]):
        big(w, h).save(os.path.join(OUT, f"wizard-{i}.bmp"))
    for i, n in enumerate([55, 69, 83, 110, 138]):
        small(n).save(os.path.join(OUT, f"wizard-small-{i}.bmp"))
    print("pictures ready")


def version():
    m = re.search(r'^VERSION = "([^"]+)"', open(os.path.join(ROOT, "app", "server.py"), encoding="utf-8").read(), re.M)
    return m.group(1)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    seed()
    std_imports()
    pictures()
    v = version()
    with open(os.path.join(OUT, "version.txt"), "w") as f:
        f.write(v)
    print("version", v)
