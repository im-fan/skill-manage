from __future__ import annotations


APP_NAME = "skill-manage"
HTML_FILENAME = f"{APP_NAME}.html"
SERVER_SCRIPT_NAME = f"{APP_NAME}-server.py"
DB_FILENAME = f"{APP_NAME}.sqlite3"
LOG_FILENAME = f"{APP_NAME}.log"
DB_JOURNAL_MODE = "DELETE"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".idea", ".vscode", "dist", "build", "coverage"}
DEFAULT_OPERATION_LOG_PAGE_SIZE = 20
MAX_OPERATION_LOG_PAGE_SIZE = 100
MAX_OPERATION_LOG_MESSAGE_LENGTH = 240
MAX_OPERATION_LOG_DETAIL_LENGTH = 4000
MAX_OPERATION_LOG_SUMMARY_LENGTH = 280

AGENTS = [
    {
        "code": "codex",
        "label": "Codex",
        "default_path": "~/.codex/skills",
    },
    {
        "code": "claude",
        "label": "ClaudeCode",
        "default_path": "~/.claude/skills",
    },
    {
        "code": "hermes",
        "label": "Hermes",
        "default_path": "~/.hermes/skills",
    },
    {
        "code": "openclaw",
        "label": "OpenClaw",
        "default_path": "~/.openclaw/skills",
    },
]

BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".ico",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".zip",
    ".tar",
    ".gz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
    ".dat",
}
TEXT_READ_LIMIT = 30000
