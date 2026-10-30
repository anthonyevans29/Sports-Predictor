"""
Centralized configuration. Loads from .env and exposes typed settings.
Single source of truth — never read os.environ elsewhere.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# The machine role AS THE PROCESS WAS STARTED WITH IT, read before .env is loaded (ARCHITECT 2026-10-30 11:30 ET,
# addendum 183 item 2(1)): "The role comes only from the environment the process runs with (host.env through systemd),
# never from a file the code opens; with no role in the environment the role is unknown and every figure is refused
# (law 4)." Desk policy v1.2's figure printing (src/walters/desk_unit.figures_allowed) reads this, never os.environ.
PROCESS_ENV_ROLE = os.environ.get("SP_EXPORTS_MIRROR_ROLE")

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    # API keys
    api_football_key: str
    api_football_host: str
    odds_api_key: str
    # CollegeFootballData (NCAA label lane, ARCHITECT 2026-10-07). Never printed.
    cfbd_api_key: str

    # DB
    database_url: str

    # Web server
    host: str
    port: int
    open_browser: bool

    # Misc
    log_level: str
    project_root: Path

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            api_football_key=os.getenv("API_FOOTBALL_KEY", ""),
            api_football_host=os.getenv("API_FOOTBALL_HOST", "v3.football.api-sports.io"),
            odds_api_key=os.getenv("ODDS_API_KEY", ""),
            cfbd_api_key=os.getenv("CFBD_API_KEY", ""),
            database_url=os.getenv("DATABASE_URL", "sqlite:///./data/sports.db"),
            host=os.getenv("WEB_HOST", "127.0.0.1"),
            port=int(os.getenv("WEB_PORT", "8000")),
            open_browser=os.getenv("OPEN_BROWSER", "true").lower() in {"1", "true", "yes"},
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            project_root=PROJECT_ROOT,
        )


settings = Settings.load()
