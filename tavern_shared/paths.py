"""
Shared filesystem locations both apps use — one AppData folder for all
persistent data (config, tokens, macros, custom assets, mod-install
markers), regardless of which folder either .exe happens to run from.
"""
import os
import sys
import shutil
import hashlib

def _app_dir():
    if getattr(sys, "frozen", False): return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _appdata_roaming():
    """The Windows-style %APPDATA% root. The game (and, on Windows, this
    launcher) both resolve it from the APPDATA env var; a headless/Docker
    run points that var at the Wine prefix's Roaming folder so the native
    Python launcher and the Wine-hosted game agree on one location."""
    return os.environ.get("APPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Roaming"))


def _tavern_data_dir():
    """The one shared place BOTH launchers' persistent data lives --
    config, tokens, macros, custom assets, the player database,
    whitelist/blacklist, the console token, mod-install markers -- all of
    it, regardless of which folder either .exe happens to be running
    from. Means downloading a new build to a different folder, or a
    fresh install replacing the old one, never requires manually moving
    files over; they were never next to the exe in the first place. (The
    Patch/ folder and per-game-install files like .tavern_mods_meta.json
    deliberately stay where they are -- see the comments at their own
    definitions for why.)"""
    path = os.path.join(_appdata_roaming(), "TheModdingTavern")
    try: os.makedirs(path, exist_ok=True)
    except Exception: pass
    return path

def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()



def _migrate_legacy_file(old_path, new_path):
    """One-time move from before file storage was unified into
    _tavern_data_dir(). Safe to call every startup — a no-op once the file
    has already been moved, or if it never existed at the old location."""
    try:
        if os.path.isfile(old_path) and not os.path.isfile(new_path):
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            shutil.move(old_path, new_path)
    except Exception:
        pass

