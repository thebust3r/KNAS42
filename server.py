"""KNAS launcher. The real code lives in the app folder; this file just starts it.
(It stays here so Docker and the updater always know where to find KNAS.)"""
import os, runpy, sys

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
sys.path.insert(0, APP)
runpy.run_path(os.path.join(APP, "server.py"), run_name="__main__")
