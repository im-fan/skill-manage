from __future__ import annotations

import sqlite3

from ..config import DEFAULT_OPERATION_LOG_PAGE_SIZE, MAX_OPERATION_LOG_PAGE_SIZE
from ..db import row_dicts
from ..errors import AppError
from ..utils.text import (
    build_operation_log_summary,
    normalize_detail_text,
    normalize_message_text,
    normalize_operation_log_level,
    normalize_operation_log_text,
    normalize_summary_text,
)


def serialize_operation_log_row(row: sqlite3.Row | dict) -> dict:
    data = dict(row)
    data["time"] = data.get("created_at", "")
    return data


def append_operation_log(
    conn: sqlite3.Connection,
    *,
    message: object,
    detail: object = "",
    level: str | None = None,
    source: object = "ui",
    action: object = "",
    detail_summary: object | None = None,
) -> dict:
    normalized_message = normalize_message_text(message)
    if not normalized_message:
        raise AppError("操作记录 message 不能为空。")

    normalized_detail = normalize_detail_text(detail)
    normalized_summary = normalize_summary_text(detail_summary)
    if not normalized_summary:
        normalized_summary = build_operation_log_summary(normalized_detail, normalized_message)

    cursor = conn.execute(
        """
        INSERT INTO operation_logs (level, source, action, message, detail, detail_summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            normalize_operation_log_level(level),
            normalize_operation_log_text(source, 64) or "ui",
            normalize_operation_log_text(action, 96),
            normalized_message,
            normalized_detail,
            normalized_summary,
        ),
    )
    row = conn.execute(
        """
        SELECT id, level, source, action, message, detail, detail_summary, created_at
        FROM operation_logs
        WHERE id = ?
        LIMIT 1
        """,
        (cursor.lastrowid,),
    ).fetchone()
    return serialize_operation_log_row(row) if row else {}


def parse_positive_int(value: object, *, default: int, minimum: int = 1, maximum: int | None = None) -> int:
    if value in {None, ""}:
        return default
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        raise AppError("分页参数必须是整数。")
    if number < minimum:
        raise AppError("分页参数必须大于等于 1。")
    if maximum is not None and number > maximum:
        number = maximum
    return number


def fetch_operation_logs_page(
    conn: sqlite3.Connection,
    *,
    page: int = 1,
    page_size: int = DEFAULT_OPERATION_LOG_PAGE_SIZE,
) -> dict:
    normalized_page = parse_positive_int(page, default=1)
    normalized_page_size = parse_positive_int(
        page_size,
        default=DEFAULT_OPERATION_LOG_PAGE_SIZE,
        maximum=MAX_OPERATION_LOG_PAGE_SIZE,
    )
    total = int(conn.execute("SELECT COUNT(*) FROM operation_logs").fetchone()[0])
    offset = (normalized_page - 1) * normalized_page_size
    rows = row_dicts(
        conn.execute(
            """
            SELECT id, level, source, action, message, detail, detail_summary, created_at
            FROM operation_logs
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (normalized_page_size, offset),
        )
    )
    items = [serialize_operation_log_row(row) for row in rows]
    has_next = offset + len(items) < total
    return {
        "items": items,
        "pagination": {
            "page": normalized_page,
            "page_size": normalized_page_size,
            "total": total,
            "has_next": has_next,
            "next_page": normalized_page + 1 if has_next else None,
        },
    }
