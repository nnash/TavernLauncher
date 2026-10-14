"""
Headless server launcher -- no Tk, no display. Entry point for Docker:

    python -m server.headless

Reads the same tavern_server.json / server_settings.json as the GUI (under
%APPDATA%/TheModdingTavern). Environment overrides:
    TAVERN_SERVER_EXE   path to 'A Township Tale.exe'
    TAVERN_SERVER_PORT  game port (default 1757)
    TAVERN_WINE         wine command prefix (default "wine"; ignored on Windows)
    TAVERN_AUTO_PATCH   "0" to skip applying the Tavern patch (default "1")
SIGTERM/SIGINT stop the server cleanly; SIGHUP triggers a reboot.
"""
import os
import sys
import signal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server.core.server_runner import HeadlessServer


def main():
    srv = HeadlessServer()
    signal.signal(signal.SIGTERM, srv.request_stop)
    signal.signal(signal.SIGINT, srv.request_stop)
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, srv.request_reboot)
    return srv.run()


if __name__ == "__main__":
    sys.exit(main())
