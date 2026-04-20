from __future__ import annotations

import sqlite3

from ..config import AGENTS
from ..db import row_dicts
from ..errors import AppError
from ..utils.filesystem import is_directory
from ..utils.paths import normalize_path


def detect_agent_path(agent: dict) -> dict:
    default_path = normalize_path(agent.get("default_path", ""))
    detected = default_path if default_path and is_directory(default_path) else ""
    return {"detected": detected, "default_path": default_path}


def fetch_agents(conn: sqlite3.Connection, *, visible_only: bool = False) -> list[dict]:
    query = """
        SELECT
          agent_code,
          display_name,
          default_path,
          configured_path,
          detected_path,
          is_builtin,
          is_visible,
          sort_order,
          last_scan_at,
          updated_at
        FROM agents
    """
    params: list[object] = []
    if visible_only:
        query += " WHERE is_visible = 1"
    query += " ORDER BY sort_order ASC, display_name COLLATE NOCASE, agent_code COLLATE NOCASE"
    return row_dicts(conn.execute(query, params))


def fetch_agent_targets(conn: sqlite3.Connection) -> dict[str, dict]:
    return {row["agent_code"]: row for row in fetch_agents(conn)}


def fetch_agent_row(conn: sqlite3.Connection, agent_code: str) -> sqlite3.Row | None:
    normalized = normalize_path(agent_code).lower() if "/" in str(agent_code) else str(agent_code or "").strip().lower()
    if not normalized:
        return None
    return conn.execute(
        """
        SELECT
          agent_code,
          display_name,
          default_path,
          configured_path,
          detected_path,
          is_builtin,
          is_visible,
          sort_order,
          last_scan_at,
          updated_at
        FROM agents
        WHERE agent_code = ?
        LIMIT 1
        """,
        (normalized,),
    ).fetchone()


def require_agent_row(conn: sqlite3.Connection, agent_code: str) -> sqlite3.Row:
    row = fetch_agent_row(conn, agent_code)
    if row is None:
        raise AppError(f"不支持的 agent: {agent_code}", 404)
    return row


def next_sort_order(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_sort_order FROM agents").fetchone()
    return int(row["next_sort_order"]) if row else 0


def upsert_agent(
    conn: sqlite3.Connection,
    *,
    agent_code: str,
    display_name: str,
    default_path: str,
    configured_path: str,
    detected_path: str = "",
    is_builtin: bool = False,
    is_visible: bool = True,
    sort_order: int | None = None,
) -> None:
    normalized_code = str(agent_code or "").strip().lower()
    if not normalized_code:
        raise AppError("agent code 不能为空。")
    if not str(display_name or "").strip():
        raise AppError("agent 名称不能为空。")

    existing = fetch_agent_row(conn, normalized_code)
    actual_sort_order = sort_order if sort_order is not None else (existing["sort_order"] if existing else next_sort_order(conn))
    conn.execute(
        """
        INSERT INTO agents (
          agent_code,
          display_name,
          default_path,
          configured_path,
          detected_path,
          is_builtin,
          is_visible,
          sort_order,
          created_at,
          updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(agent_code) DO UPDATE SET
          display_name = excluded.display_name,
          default_path = excluded.default_path,
          configured_path = excluded.configured_path,
          detected_path = excluded.detected_path,
          is_builtin = excluded.is_builtin,
          is_visible = excluded.is_visible,
          sort_order = excluded.sort_order,
          updated_at = CURRENT_TIMESTAMP
        """,
        (
            normalized_code,
            str(display_name or "").strip(),
            normalize_path(default_path),
            normalize_path(configured_path),
            normalize_path(detected_path),
            1 if is_builtin else 0,
            1 if is_visible else 0,
            int(actual_sort_order),
        ),
    )


def update_agent_visibility(conn: sqlite3.Connection, agent_code: str, is_visible: bool) -> None:
    row = require_agent_row(conn, agent_code)
    conn.execute(
        "UPDATE agents SET is_visible = ?, updated_at = CURRENT_TIMESTAMP WHERE agent_code = ?",
        (1 if is_visible else 0, row["agent_code"]),
    )


def fetch_deleted_builtin_agent_codes(conn: sqlite3.Connection) -> set[str]:
    rows = row_dicts(conn.execute("SELECT agent_code FROM deleted_builtin_agents"))
    return {str(row["agent_code"] or "").strip().lower() for row in rows}


def ensure_agent_targets(conn: sqlite3.Connection) -> None:
    builtin_map = {agent["code"]: agent for agent in AGENTS}
    deleted_builtin_codes = fetch_deleted_builtin_agent_codes(conn)
    legacy_targets = {
        row["agent_code"]: row
        for row in row_dicts(
            conn.execute(
                """
                SELECT agent_code, display_name, configured_path, detected_path, is_custom, last_scan_at, updated_at
                FROM agent_targets
                """
            )
        )
    }

    for agent in AGENTS:
        if agent["code"] in deleted_builtin_codes:
            continue
        detection = detect_agent_path(agent)
        existing = fetch_agent_row(conn, agent["code"])
        legacy = legacy_targets.get(agent["code"])
        if existing is None and legacy is None and not detection["detected"]:
            continue

        configured_path = ""
        detected_path = detection["detected"]
        if existing is not None:
            configured_path = normalize_path(existing["configured_path"])
            if not detected_path:
                detected_path = normalize_path(existing["detected_path"])
        elif legacy is not None:
            configured_path = normalize_path(legacy["configured_path"])
            if not detected_path:
                detected_path = normalize_path(legacy["detected_path"])

        if not configured_path:
            configured_path = detected_path or detection["default_path"]

        upsert_agent(
            conn,
            agent_code=agent["code"],
            display_name=agent["label"],
            default_path=detection["default_path"],
            configured_path=configured_path,
            detected_path=detected_path,
            is_builtin=True,
            is_visible=True if existing is None else bool(int(existing["is_visible"])),
            sort_order=existing["sort_order"] if existing is not None else None,
        )

    rows = fetch_agents(conn)
    builtin_codes = set(builtin_map)
    for row in rows:
        if row["agent_code"] in builtin_codes:
            continue
        configured_path = normalize_path(row["configured_path"])
        detected_path = normalize_path(row["detected_path"])
        default_path = normalize_path(row["default_path"])
        resolved_configured = configured_path or detected_path or default_path
        conn.execute(
            """
            UPDATE agents
            SET configured_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE agent_code = ?
            """,
            (resolved_configured, row["agent_code"]),
        )
