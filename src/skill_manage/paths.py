from __future__ import annotations

import os
from pathlib import Path

from .config import DB_FILENAME, HTML_FILENAME, LOG_FILENAME, SERVER_SCRIPT_NAME


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
WEB_DIR = PROJECT_ROOT / "web"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

_runtime_home = os.environ.get("SKILL_MANAGE_HOME", "").strip()
RUNTIME_HOME = Path(_runtime_home).expanduser().resolve() if _runtime_home else PROJECT_ROOT
DATA_DIR = RUNTIME_HOME / "data"
LOGS_DIR = RUNTIME_HOME / "logs"

HTML_PATH = WEB_DIR / HTML_FILENAME
DB_PATH = DATA_DIR / DB_FILENAME
LEGACY_DB_PATH = PROJECT_ROOT / DB_FILENAME
LOG_PATH = LOGS_DIR / LOG_FILENAME
SERVER_SCRIPT_PATH = SRC_ROOT / SERVER_SCRIPT_NAME
START_SCRIPT_PATH = SCRIPTS_DIR / "start.sh"


def ensure_runtime_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
