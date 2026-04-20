from __future__ import annotations

import sqlite3

from ..db import row_dicts


def fetch_scan_roots(conn: sqlite3.Connection) -> list[dict]:
    return row_dicts(
        conn.execute(
            """
            SELECT
              sr.path,
              sr.mode,
              sr.note,
              sr.status,
              sr.last_error,
              sr.last_scan_at,
              sr.created_at,
              sr.updated_at,
              CASE
                WHEN sr.mode = 'skill_dir' THEN COALESCE(skill_stats.skill_count, 0)
                ELSE NULL
              END AS skill_count
            FROM scan_roots sr
            LEFT JOIN (
              SELECT root_path, COUNT(*) AS skill_count
              FROM skills
              GROUP BY root_path
            ) AS skill_stats
              ON skill_stats.root_path = sr.path
            ORDER BY sr.created_at DESC, sr.path COLLATE NOCASE
            """
        )
    )

