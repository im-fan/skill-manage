from __future__ import annotations

import sqlite3

from ..db import row_dicts
from ..errors import AppError
from .agent_targets import fetch_agents
from ..utils.paths import normalize_path


def upsert_agent_entries(conn: sqlite3.Connection, agent_code: str, entries: list[dict]) -> None:
    previous = row_dicts(
        conn.execute("SELECT link_path, is_managed FROM agent_links WHERE agent_code = ?", (agent_code,))
    )
    managed_map = {row["link_path"]: int(row["is_managed"]) for row in previous}

    conn.execute("DELETE FROM agent_links WHERE agent_code = ?", (agent_code,))
    for entry in entries:
        managed = int(entry.get("is_managed", managed_map.get(entry["link_path"], 0)))
        conn.execute(
            """
            INSERT INTO agent_links (
              link_path, agent_code, link_name, target_path, target_display_path, link_kind,
              status, status_reason, is_managed, fs_created_at, fs_created_ts, last_scan_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                entry["link_path"],
                agent_code,
                entry["link_name"],
                entry["target_path"],
                entry.get("target_display_path", entry["target_path"]),
                entry["link_kind"],
                entry["status"],
                entry.get("status_reason", ""),
                managed,
                entry.get("fs_created_at", ""),
                float(entry.get("fs_created_ts", 0) or 0),
            ),
        )


def fetch_agent_entries(conn: sqlite3.Connection) -> dict[str, list[dict]]:
    agents = fetch_agents(conn)
    result = {agent["agent_code"]: [] for agent in agents}
    for agent in agents:
        result[agent["agent_code"]] = row_dicts(
            conn.execute(
                """
                SELECT link_path, agent_code, link_name, target_path, target_display_path,
                       link_kind, status, status_reason, is_managed, last_scan_at, fs_created_at, fs_created_ts
                FROM agent_links
                WHERE agent_code = ?
                ORDER BY CASE status
                  WHEN 'invalid_missing_target' THEN 0
                  WHEN 'invalid_missing_skill_md' THEN 1
                  WHEN 'linked' THEN 2
                  ELSE 3
                END, fs_created_ts DESC, link_name COLLATE NOCASE
                """,
                (agent["agent_code"],),
            )
        )
    return result


def require_agent_entry(conn: sqlite3.Connection, agent_code: str, link_path: str) -> sqlite3.Row:
    normalized = normalize_path(link_path)
    row = conn.execute(
        """
        SELECT link_path, agent_code, link_name, target_path, target_display_path,
               link_kind, status, status_reason, is_managed, last_scan_at
        FROM agent_links
        WHERE agent_code = ? AND link_path = ?
        LIMIT 1
        """,
        (agent_code, normalized),
    ).fetchone()
    if row is None:
        raise AppError("目标 Skill 不存在。", 404)
    return row
