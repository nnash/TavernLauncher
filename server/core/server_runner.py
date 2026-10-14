"""
UI-free pieces of running the game server, shared by the Tk launcher and the
headless (Docker) runner: building the game's command line, wrapping it for
Wine on non-Windows hosts, and a supervisor that starts the process, restarts
it if it dies, handles the scheduled auto-reboot, and archives the log.
"""
import os
import sys
import time
import shlex
import signal
import shutil
import datetime
import subprocess
import threading

from tavern_shared.log_archive import archive_log_now
from tavern_shared.log_tailer import GameLogTailer
from tavern_shared.patch import _patch_is_applied, apply_patch
from server.core.data_store import (
    load_cfg, load_server_settings, CONSOLE_TOKEN_FILE, GAME_LOG_PATH,
)
from server.core.auth_service import (
    start_auth_service, build_console_token, build_server_tokens,
)

DEFAULT_PORT = 1757


def build_server_args(exe, port, access, refresh, identity,
                      show_game=False, debug_helper=False, quest_scene=False):
    """The game's argv, identical for the GUI and headless launchers."""
    args = [exe, "/force_offline",
            "/access_token", access, "/refresh_token", refresh,
            "/identity_token", identity]
    if not show_game:
        args += ["-batchmode", "-nographics"]
    args += ["/fly", "/launcherauth", "/start_server", "-1", "false", str(port)]
    if debug_helper:
        args.append("/debug_helper")
    if quest_scene:
        args.append("/questScene")
    return args


def wine_prefix_command():
    """[] on Windows; otherwise the Wine invocation (TAVERN_WINE overrides,
    e.g. "wine64" or "xvfb-run -a wine")."""
    if sys.platform == "win32":
        return []
    return shlex.split(os.environ.get("TAVERN_WINE", "wine"))


class HeadlessServer:
    """Runs the game server with no UI. Everything goes through log(msg, tag)."""

    CRASH_RESTART_DELAY = 10
    CRASH_BACKOFF_MAX = 300
    STABLE_AFTER = 120  # seconds up before a crash counts as a fresh failure

    def __init__(self, log=None):
        self._log_fn = log or (lambda msg, tag="": print(msg, flush=True))
        self._proc = None
        self._stop_evt = threading.Event()
        self._reboot_evt = threading.Event()
        self._auth_on = False
        self._tailer = None

    def log(self, msg, tag=""):
        self._log_fn(f"[{time.strftime('%H:%M:%S')}] {msg}", tag)

    # ── config ────────────────────────────────────────────────────────────
    def _settings(self):
        cfg = load_cfg()
        exe = os.environ.get("TAVERN_SERVER_EXE") or cfg.get("server_exe", "")
        try:
            port = int(os.environ.get("TAVERN_SERVER_PORT") or cfg.get("server_port", DEFAULT_PORT))
        except ValueError:
            port = DEFAULT_PORT
        return exe.strip(), port, cfg, load_server_settings()

    # ── lifecycle ─────────────────────────────────────────────────────────
    def request_stop(self, *_):
        self._stop_evt.set()

    def request_reboot(self, *_):
        self._reboot_evt.set()

    def run(self):
        """Blocks until stop is requested. Returns a process exit code."""
        exe, _port, _cfg, _ss = self._settings()
        if not exe or not os.path.isfile(exe):
            self.log(f"Game exe not found: {exe!r}. Set TAVERN_SERVER_EXE or "
                     "server_exe in tavern_server.json.", "err")
            return 2

        self._maybe_patch(exe)
        self._start_tailer()
        failures = 0
        try:
            while not self._stop_evt.is_set():
                started = time.monotonic()
                self._launch()
                self._wait_for_exit_or_event()
                if self._stop_evt.is_set():
                    break
                if self._reboot_evt.is_set():
                    self._reboot_evt.clear()
                    self._terminate()
                    self.log("Reboot: restarting in 10 seconds…", "warn")
                    self._stop_evt.wait(10)
                    continue
                if self._proc is not None and self._proc.poll() is not None:
                    up = time.monotonic() - started
                    failures = 1 if up >= self.STABLE_AFTER else failures + 1
                    delay = min(self.CRASH_BACKOFF_MAX,
                                self.CRASH_RESTART_DELAY * 2 ** (failures - 1))
                    self.log(f"Server exited (code {self._proc.returncode}) "
                             f"after {int(up)}s; restarting in {delay}s…", "err")
                    self._stop_evt.wait(delay)
        finally:
            self._terminate()
            if self._tailer:
                self._tailer.stop()
        return 0

    def _maybe_patch(self, exe):
        if os.environ.get("TAVERN_AUTO_PATCH", "1") != "1":
            return
        try:
            if _patch_is_applied(exe):
                return
            self.log("Applying Tavern patch…", "warn")
            self.log(f"Patch applied ({apply_patch(exe, lambda m: self.log(m, 'dim'))}).", "ok")
        except Exception as e:
            self.log(f"Couldn't apply the Tavern patch: {e}", "err")

    def _start_tailer(self):
        """Mirrors the game log to stdout so `docker logs` shows it."""
        def on_line(ts, lv, lg, msg):
            short = lg.split(".")[-1] if lg else ""
            self._log_fn(f"[{ts}] {lv}" + (f" [{short}]" if short else "") + f" {msg}", "game")
        self._tailer = GameLogTailer(GAME_LOG_PATH, on_line)
        self._tailer.start()

    def _launch(self):
        exe, port, cfg, ss = self._settings()
        # Tailer holds the log open (matters on Windows/Wine-mapped files).
        if self._tailer:
            self._tailer.stop_and_wait(timeout=2)
        ok, result, _locked = archive_log_now(GAME_LOG_PATH)
        if ok:
            self.log(f"Log archived to {result}", "ok")
        self._start_tailer()

        access, refresh, identity = build_server_tokens()
        try:
            with open(CONSOLE_TOKEN_FILE, "w") as f:
                f.write(build_console_token())
        except OSError:
            pass
        if not self._auth_on:
            start_auth_service(self.log)
            self._auth_on = True

        args = wine_prefix_command() + build_server_args(
            exe, port, access, refresh, identity,
            show_game=cfg.get("show_game", False),
            debug_helper=cfg.get("debug_helper", False),
            quest_scene=ss.get("quest_scene", False))
        self.log(f"Opening server on port {port}…", "warn")
        # Own session so we can signal the whole wine process tree at once.
        self._proc = subprocess.Popen(
            args, cwd=os.path.dirname(exe),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=(sys.platform != "win32"))
        self._reboot_deadline = self._next_reboot(ss)
        self.log(f"Server running (PID {self._proc.pid})", "ok")

    def _next_reboot(self, ss):
        """Monotonic deadline for the scheduled reboot, or None."""
        if not ss.get("auto_reboot_enabled", False):
            return None
        if ss.get("auto_reboot_mode", "time") == "interval":
            hours = max(1, ss.get("auto_reboot_interval", 6))
            self.log(f"Auto-reboot scheduled in {hours}h.", "dim")
            return time.monotonic() + hours * 3600
        now = datetime.datetime.now()
        target = now.replace(hour=max(0, min(23, ss.get("auto_reboot_hour", 4))),
                             minute=max(0, min(59, ss.get("auto_reboot_minute", 0))),
                             second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        self.log(f"Auto-reboot scheduled for {target.strftime('%H:%M')}.", "dim")
        return time.monotonic() + (target - now).total_seconds()

    def _wait_for_exit_or_event(self):
        while not (self._stop_evt.is_set() or self._reboot_evt.is_set()):
            if self._proc.poll() is not None:
                return
            if self._reboot_deadline and time.monotonic() >= self._reboot_deadline:
                self.log("Auto-reboot triggered.", "warn")
                self._reboot_evt.set()
                return
            self._stop_evt.wait(1)

    def _terminate(self, timeout=20):
        proc, self._proc = self._proc, None
        if proc is None or proc.poll() is not None:
            return
        self.log("Closing server…", "warn")
        try:
            if sys.platform == "win32":
                proc.terminate()
            else:
                os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            self.log("Server didn't exit in time; killing.", "err")
            try:
                if sys.platform == "win32":
                    proc.kill()
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
        except OSError:
            pass
        # wine leaves wineserver + child processes behind; clean them up.
        if sys.platform != "win32" and shutil.which("wineserver"):
            subprocess.run(["wineserver", "-k"], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
