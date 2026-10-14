"""KNAS start-up inside Docker (built into the image as /opt/knas/start.py).

KNAS runs from a folder you give it (mapped to /knas in the container), so your settings, music, clips
and update zips live on your NAS, not inside the container. This makes that work however you start it:

  - From a project / docker-compose.yml (the README way): the folder already has KNAS in it; nothing to do.
  - From your NAS's Docker app (image search -> create a container) with an empty folder mapped to /knas:
    the first start fills the folder with KNAS (settings, music folder, updates folder...), then starts it.
  - Downloading a newer image and re-creating the container updates the code in the folder.
    Your settings.txt, teams, facts and trivia are never touched, and a folder that's already newer
    (from an update zip) is never downgraded.
  - No folder mapped at all: KNAS still runs, but settings are lost when the container is re-created.
"""
import os, re, shutil, sys

SEED = os.environ.get("KNAS_SEED", "/opt/knas/seed")
DEST = os.environ.get("KNAS_DIR", "/knas")
KEEP = {"settings.txt", "teams.txt", "facts.txt", "trivia.txt", "docker-compose.yml"}   # yours once they exist
USER_DIRS = {"music", "updates", "break-videos", "break-clips", "data"}                 # never overwritten


def version(root):
    try:
        m = re.search(r'^VERSION = "([^"]+)"', open(os.path.join(root, "app", "server.py"), encoding="utf-8").read(), re.M)
        return m.group(1) if m else ""
    except OSError:
        return ""


def rank(v):
    """Same as the server's: the numbering restarted at 1.1.1, the old test builds (2.6-2.22) count as older."""
    nums = ([int(x) for x in re.findall(r"\d+", v or "")[:3]] + [0, 0, 0])[:3]
    return (0 if (nums[0] == 2 and 6 <= nums[1] <= 22) else 1, nums) if v else (-1, nums)


def copy_tree(update):
    """Copy the image's KNAS into the folder. update=False: only fill in what's missing."""
    changed = 0
    for base, dirs, files in os.walk(SEED):
        rel_dir = os.path.relpath(base, SEED)
        top = rel_dir.split(os.sep)[0]
        if update and top in USER_DIRS:
            dirs[:] = []
            continue
        os.makedirs(os.path.join(DEST, rel_dir), exist_ok=True)
        for f in files:
            rel = os.path.normpath(os.path.join(rel_dir, f))
            dest = os.path.join(DEST, rel)
            if os.path.exists(dest) and (not update or rel in KEEP or top in USER_DIRS):
                continue
            tmp = dest + ".new"
            shutil.copyfile(os.path.join(base, f), tmp)
            os.replace(tmp, dest)
            changed += 1
    return changed


def is_mounted(path):
    try:
        return any(line.split()[4] == path for line in open("/proc/self/mountinfo"))
    except (OSError, IndexError):
        return True


def main():
    os.umask(0)                                  # files stay editable from your NAS's file manager
    os.makedirs(DEST, exist_ok=True)
    have, new = version(DEST), version(SEED)
    try:
        if not os.path.exists(os.path.join(DEST, "server.py")):
            n = copy_tree(update=False)
            print(f"[knas] set up a new KNAS folder at {DEST} ({n} files, version {new})", flush=True)
        elif new and rank(new) > rank(have):
            n = copy_tree(update=True)
            print(f"[knas] updated the KNAS folder from {have or 'an old version'} to {new} (new image, {n} files). "
                  "Your settings were kept.", flush=True)
        else:
            copy_tree(update=False)              # put back anything missing (a deleted folder, say)
        for d in ("music", "updates", "break-videos", "data"):
            os.makedirs(os.path.join(DEST, d), exist_ok=True)
    except OSError as e:
        print(f"[knas] couldn't write to {DEST} ({e}). Check that the folder you mapped to /knas can be written to.", flush=True)
        if not os.path.exists(os.path.join(DEST, "server.py")):
            os.execv(sys.executable, [sys.executable, "-u", os.path.join(SEED, "server.py")])
    if not is_mounted(DEST):
        print("[knas] NOTE: no folder is mapped to /knas, so your settings will be lost if this container is re-created. "
              "Map a folder on your NAS (for example /volume1/docker/knas42) to /knas to keep them.", flush=True)
    os.chdir(DEST)
    os.execv(sys.executable, [sys.executable, "-u", os.path.join(DEST, "server.py")])


if __name__ == "__main__":
    main()
