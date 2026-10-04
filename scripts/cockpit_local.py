#!/usr/bin/env python3
"""
LOCAL COCKPIT LAUNCHER (ARCHITECT 2026-10-04): the published artifact's CSP
blocks api.github.com, so "Load latest from host" cannot run there. Served from
this machine, the same page can reach the GitHub contents API.

    python scripts/cockpit_local.py [--html PATH] [--port 8765] [--no-browser]

--html: the Cockpit file to serve. The LIVE Cockpit is the published artifact
(CLAUDE.md), so save a copy of it and point --html at it. The default
tools/cockpit.html is the repo copy and may lag the published one; the
launcher says so.

The ledger lives in the browser's localStorage, which is per ORIGIN. The local
page (http://127.0.0.1:<port>) has its OWN ledger, separate from the published
artifact's. To carry it over, use "Export ledger (JSON)" on one page and
"Import ledger" on the other. Keep the same --port so the local origin, and its
ledger, stay the same between runs.

Binds 127.0.0.1 only. Serves read-only and writes nothing.
"""
from __future__ import annotations

import argparse
import functools
import http.server
import sys
import threading
import webbrowser
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="serve a Cockpit file on 127.0.0.1")
    ap.add_argument("--html", default=str(REPO / "tools" / "cockpit.html"))
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    page = Path(a.html).expanduser().resolve()
    if not page.is_file():
        print(f"REFUSED: {page} not found")
        return 2
    if page == (REPO / "tools" / "cockpit.html").resolve():
        print("note: serving the REPO copy (tools/cockpit.html); the live Cockpit is the published artifact. "
              "Save it and pass --html to serve that instead.")

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port),
                                          functools.partial(Quiet, directory=str(page.parent)))
    url = f"http://127.0.0.1:{a.port}/{page.name}"
    print(f"Cockpit at {url} (Ctrl-C stops). Ledger: this origin's own localStorage — Export/Import to move it.")
    if not a.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
