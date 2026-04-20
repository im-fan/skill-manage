from __future__ import annotations

import os
import sqlite3

from ..db import row_dicts
from ..errors import AppError
from ..utils.filesystem import fs_created_meta, is_skill_dir
from ..utils.paths import normalize_path
from ..utils.text import read_skill_description


def upsert_local_skill(conn: sqlite3.Connection, skill_path: str, root_path: str | None = None) -> None:
    normalized = normalize_path(skill_path)
    if not is_skill_dir(normalized):
        raise AppError("目标目录不存在，或缺少 SKILL.md。")
    root_value = normalize_path(root_path) or normalized
    fs_created_at, fs_created_ts = fs_created_meta(normalized, follow_symlinks=True)
    conn.execute(
        """
        INSERT INTO skills (path, name, root_path, description, status, last_scan_at, fs_created_at, fs_created_ts, created_at, updated_at)
        VALUES (?, ?, ?, ?, 'ok', CURRENT_TIMESTAMP, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(path) DO UPDATE SET
          name = excluded.name,
          root_path = excluded.root_path,
          description = excluded.description,
          status = 'ok',
          last_scan_at = CURRENT_TIMESTAMP,
          fs_created_at = excluded.fs_created_at,
          fs_created_ts = excluded.fs_created_ts,
          updated_at = CURRENT_TIMESTAMP
        """,
        (normalized, os.path.basename(normalized), root_value, read_skill_description(normalized), fs_created_at, fs_created_ts),
    )


def fetch_local_skills(conn: sqlite3.Connection) -> list[dict]:
    return row_dicts(
        conn.execute(
            """
            SELECT path, name, root_path, description, status, last_scan_at, updated_at, fs_created_at, fs_created_ts
            FROM skills
            ORDER BY CASE status WHEN 'ok' THEN 0 ELSE 1 END, fs_created_ts DESC, name COLLATE NOCASE
            """
        )
    )

