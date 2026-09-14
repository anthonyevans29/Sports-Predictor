"""
Local browser app entry point.

Boots the FastAPI server and (optionally) opens a browser tab. Designed
for the "double-click to launch" UX:

    $ python main.py

Then the dashboard is at http://localhost:8000.

Hot-reload during development:
    $ uvicorn src.web.app:app --reload
"""
from __future__ import annotations

import logging
import threading
import time
import webbrowser

import uvicorn

from config import settings


def _open_browser_after_delay(url: str, delay_seconds: float = 1.0) -> None:
    """Open the browser after a short delay so the server is ready."""
    def _do_it():
        time.sleep(delay_seconds)
        webbrowser.open(url)

    threading.Thread(target=_do_it, daemon=True).start()


def main() -> None:
    logging.basicConfig(level=settings.log_level, format="%(levelname)s %(name)s: %(message)s")
    url = f"http://{settings.host}:{settings.port}"

    if settings.open_browser:
        _open_browser_after_delay(url)

    print(f"\n  Sports Predictor → {url}\n  (Ctrl+C to stop)\n")

    uvicorn.run(
        "src.web.app:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False,
    )


if __name__ == "__main__":
    main()
