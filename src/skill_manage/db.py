from __future__ import annotations

import shutil
import sqlite3
from contextlib import contextmanager

from .config import DB_JOURNAL_MODE
from .paths import DB_PATH, LEGACY_DB_PATH, ensure_runtime_dirs


def row_dicts(cursor: sqlite3.Cursor) -> list[dict]:
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def prepare_runtime_files() -> None:
    ensure_runtime_dirs()
    if not DB_PATH.exists() and LEGACY_DB_PATH.exists():
        shutil.move(str(LEGACY_DB_PATH), str(DB_PATH))
        for suffix in ("-wal", "-shm"):
            legacy_sidecar = LEGACY_DB_PATH.with_name(f"{LEGACY_DB_PATH.name}{suffix}")
            target_sidecar = DB_PATH.with_name(f"{DB_PATH.name}{suffix}")
            if legacy_sidecar.exists() and not target_sidecar.exists():
                shutil.move(str(legacy_sidecar), str(target_sidecar))


@contextmanager
def db_conn() -> sqlite3.Connection:
    prepare_runtime_files()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA journal_mode={DB_JOURNAL_MODE}")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS scan_roots (
          path TEXT PRIMARY KEY,
          mode TEXT NOT NULL CHECK(mode IN ('skill_root', 'skill_dir')),
          note TEXT DEFAULT '',
          status TEXT DEFAULT 'idle',
          last_error TEXT DEFAULT '',
          last_scan_at TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS skills (
          path TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          root_path TEXT NOT NULL,
          description TEXT DEFAULT '',
          status TEXT NOT NULL DEFAULT 'ok',
          last_scan_at TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agent_targets (
          agent_code TEXT PRIMARY KEY,
          display_name TEXT NOT NULL,
          configured_path TEXT NOT NULL,
          detected_path TEXT,
          is_custom INTEGER NOT NULL DEFAULT 0,
          last_scan_at TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agents (
          agent_code TEXT PRIMARY KEY,
          display_name TEXT NOT NULL,
          default_path TEXT DEFAULT '',
          configured_path TEXT NOT NULL,
          detected_path TEXT DEFAULT '',
          is_builtin INTEGER NOT NULL DEFAULT 0,
          is_visible INTEGER NOT NULL DEFAULT 1,
          sort_order INTEGER NOT NULL DEFAULT 0,
          last_scan_at TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS deleted_builtin_agents (
          agent_code TEXT PRIMARY KEY,
          deleted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agent_links (
          link_path TEXT PRIMARY KEY,
          agent_code TEXT NOT NULL,
          link_name TEXT NOT NULL,
          target_path TEXT NOT NULL,
          target_display_path TEXT,
          link_kind TEXT NOT NULL,
          status TEXT NOT NULL,
          status_reason TEXT DEFAULT '',
          is_managed INTEGER NOT NULL DEFAULT 0,
          last_scan_at TEXT,
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS operation_logs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          level TEXT NOT NULL DEFAULT 'info',
          source TEXT NOT NULL DEFAULT 'ui',
          action TEXT DEFAULT '',
          message TEXT NOT NULL,
          detail TEXT DEFAULT '',
          detail_summary TEXT DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_operation_logs_created_at
        ON operation_logs (created_at DESC, id DESC);
        """
    )
    migrate_db(conn)


def migrate_db(conn: sqlite3.Connection) -> None:
    skill_columns = {row["name"] for row in row_dicts(conn.execute("PRAGMA table_info(skills)"))}
    if "description" not in skill_columns:
        conn.execute("ALTER TABLE skills ADD COLUMN description TEXT DEFAULT ''")
    if "fs_created_at" not in skill_columns:
        conn.execute("ALTER TABLE skills ADD COLUMN fs_created_at TEXT DEFAULT ''")
    if "fs_created_ts" not in skill_columns:
        conn.execute("ALTER TABLE skills ADD COLUMN fs_created_ts REAL DEFAULT 0")

    agent_link_columns = {row["name"] for row in row_dicts(conn.execute("PRAGMA table_info(agent_links)"))}
    if "fs_created_at" not in agent_link_columns:
        conn.execute("ALTER TABLE agent_links ADD COLUMN fs_created_at TEXT DEFAULT ''")
    if "fs_created_ts" not in agent_link_columns:
        conn.execute("ALTER TABLE agent_links ADD COLUMN fs_created_ts REAL DEFAULT 0")

    agent_columns = {row["name"] for row in row_dicts(conn.execute("PRAGMA table_info(agents)"))}
    if agent_columns:
        if "default_path" not in agent_columns:
            conn.execute("ALTER TABLE agents ADD COLUMN default_path TEXT DEFAULT ''")
        if "detected_path" not in agent_columns:
            conn.execute("ALTER TABLE agents ADD COLUMN detected_path TEXT DEFAULT ''")
        if "is_builtin" not in agent_columns:
            conn.execute("ALTER TABLE agents ADD COLUMN is_builtin INTEGER NOT NULL DEFAULT 0")
        if "is_visible" not in agent_columns:
            conn.execute("ALTER TABLE agents ADD COLUMN is_visible INTEGER NOT NULL DEFAULT 1")
        if "sort_order" not in agent_columns:
            conn.execute("ALTER TABLE agents ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0")
        if "last_scan_at" not in agent_columns:
            conn.execute("ALTER TABLE agents ADD COLUMN last_scan_at TEXT")

    operation_log_columns = {row["name"] for row in row_dicts(conn.execute("PRAGMA table_info(operation_logs)"))}
    if operation_log_columns:
        if "source" not in operation_log_columns:
            conn.execute("ALTER TABLE operation_logs ADD COLUMN source TEXT NOT NULL DEFAULT 'ui'")
        if "action" not in operation_log_columns:
            conn.execute("ALTER TABLE operation_logs ADD COLUMN action TEXT DEFAULT ''")
        if "detail" not in operation_log_columns:
            conn.execute("ALTER TABLE operation_logs ADD COLUMN detail TEXT DEFAULT ''")
        if "detail_summary" not in operation_log_columns:
            conn.execute("ALTER TABLE operation_logs ADD COLUMN detail_summary TEXT DEFAULT ''")
