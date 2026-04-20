from __future__ import annotations

import os
import shutil
import sqlite3
from http import HTTPStatus

from ..db import db_conn, init_db, row_dicts
from ..errors import AppError
from ..repositories.local_skills import fetch_local_skills, upsert_local_skill
from ..utils.filesystem import collect_skill_dirs, fs_created_meta, is_directory, is_skill_dir, path_exists, pick_directory_destination
from ..utils.paths import normalize_path
from ..utils.text import read_skill_description


def validate_scan_root_input(path_value: str, mode: str) -> str:
    normalized = normalize_path(path_value)
    if not normalized:
        raise AppError("请填写有效路径。")
    if mode not in {"skill_root", "skill_dir"}:
        raise AppError("扫描源类型不合法。")
    if not path_exists(normalized) or not is_directory(normalized):
        raise AppError("路径不存在或不是目录。")
    if mode == "skill_dir" and not is_skill_dir(normalized):
        raise AppError("单个 Skill 目录模式要求当前目录下存在 SKILL.md。")
    return normalized


def remove_local_skill(skill_path: str) -> int:
    normalized = normalize_path(skill_path)
    removed_links = 0
    with db_conn() as conn:
        init_db(conn)
        link_rows = row_dicts(
            conn.execute(
                """
                SELECT link_path
                FROM agent_links
                WHERE target_path = ?
                  AND is_managed = 1
                  AND link_kind = 'symlink'
                """,
                (normalized,),
            )
        )
        for row in link_rows:
            if path_exists(row["link_path"]) and os.path.islink(row["link_path"]):
                try:
                    os.unlink(row["link_path"])
                except OSError:
                    pass
            removed_links += 1
            conn.execute("DELETE FROM agent_links WHERE link_path = ?", (row["link_path"],))

        conn.execute("DELETE FROM skills WHERE path = ?", (normalized,))
    return removed_links


def repoint_managed_symlinks(conn: sqlite3.Connection, source_path: str, destination_path: str) -> None:
    rows = row_dicts(
        conn.execute(
            """
            SELECT link_path
            FROM agent_links
            WHERE target_path = ?
              AND link_kind = 'symlink'
            """,
            (source_path,),
        )
    )
    for row in rows:
        link_path = normalize_path(row["link_path"])
        link_parent = os.path.dirname(link_path)
        os.makedirs(link_parent, exist_ok=True)
        if path_exists(link_path):
            if not os.path.islink(link_path):
                raise AppError(f"挂载路径不是软链接，无法自动迁移：{link_path}")
            os.unlink(link_path)
        relative_target = os.path.relpath(destination_path, start=os.path.realpath(link_parent)) or "."
        os.symlink(relative_target, link_path)


def move_local_skill_to_root(skill_path: str, root_path: str) -> str:
    normalized_skill = normalize_path(skill_path)
    normalized_root = normalize_path(root_path)
    if not is_skill_dir(normalized_skill):
        raise AppError("目标 Skill 目录不存在，或缺少 SKILL.md。")

    with db_conn() as conn:
        init_db(conn)
        row = conn.execute(
            """
            SELECT path, root_path
            FROM skills
            WHERE path = ?
            LIMIT 1
            """,
            (normalized_skill,),
        ).fetchone()
        if row is None:
            raise AppError("SKILL不存在。", HTTPStatus.NOT_FOUND)

        root_row = conn.execute(
            """
            SELECT mode
            FROM scan_roots
            WHERE path = ?
            LIMIT 1
            """,
            (normalized_root,),
        ).fetchone()
        if root_row is None or root_row["mode"] != "skill_root":
            raise AppError("目标扫描源不存在，或不是 skill_root。")
        if not is_directory(normalized_root):
            raise AppError("目标扫描源目录不存在。")
        if normalize_path(row["root_path"]) == normalized_root:
            raise AppError("目标扫描源与当前源相同。")

        source_root = normalize_path(row["root_path"])
        source_root_row = conn.execute(
            """
            SELECT mode
            FROM scan_roots
            WHERE path = ?
            LIMIT 1
            """,
            (source_root,),
        ).fetchone()
        destination_path = pick_directory_destination(normalized_root, os.path.basename(normalized_skill))
        moved = False
        try:
            shutil.move(normalized_skill, destination_path)
            moved = True
            repoint_managed_symlinks(conn, normalized_skill, destination_path)
        except Exception as exc:
            if moved and not path_exists(normalized_skill) and path_exists(destination_path):
                try:
                    shutil.move(destination_path, normalized_skill)
                except Exception:
                    pass
            raise AppError(f"移动SKILL失败: {exc}")

        conn.execute("DELETE FROM skills WHERE path = ?", (normalized_skill,))
        upsert_local_skill(conn, destination_path, normalized_root)
        sync_one_root(conn, normalized_root, "skill_root")

        if source_root_row and source_root_row["mode"] == "skill_root":
            sync_one_root(conn, source_root, "skill_root")
        elif source_root_row and source_root_row["mode"] == "skill_dir":
            conn.execute("DELETE FROM scan_roots WHERE path = ?", (source_root,))

        return destination_path


def sync_local_skill_status(conn: sqlite3.Connection) -> None:
    rows = row_dicts(conn.execute("SELECT path FROM skills"))
    for row in rows:
        status = "ok" if is_skill_dir(row["path"]) else "missing"
        fs_created_at, fs_created_ts = ("", 0.0)
        if status == "ok":
            fs_created_at, fs_created_ts = fs_created_meta(row["path"], follow_symlinks=True)
        conn.execute(
            "UPDATE skills SET status = ?, fs_created_at = ?, fs_created_ts = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
            (status, fs_created_at, fs_created_ts, row["path"]),
        )
        if status == "ok":
            conn.execute(
                "UPDATE skills SET description = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (read_skill_description(row["path"]), row["path"]),
            )


def sync_one_root(conn: sqlite3.Connection, root_path: str, mode: str) -> list[str]:
    normalized = normalize_path(root_path)
    discovered = collect_skill_dirs(normalized, mode)

    for skill_path in discovered:
        upsert_local_skill(conn, skill_path, normalized)

    if discovered:
        placeholders = ", ".join("?" for _ in discovered)
        conn.execute(
            f"""
            UPDATE skills
            SET status = 'missing', updated_at = CURRENT_TIMESTAMP
            WHERE root_path = ?
              AND path NOT IN ({placeholders})
            """,
            [normalized, *discovered],
        )
    else:
        conn.execute(
            """
            UPDATE skills
            SET status = 'missing', updated_at = CURRENT_TIMESTAMP
            WHERE root_path = ?
            """,
            (normalized,),
        )

    conn.execute(
        """
        UPDATE scan_roots
        SET status = 'ok', last_error = '', last_scan_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE path = ?
        """,
        (normalized,),
    )
    return discovered


def save_scan_root(path_value: str, mode: str, note: str) -> None:
    normalized = validate_scan_root_input(path_value, mode)

    with db_conn() as conn:
        init_db(conn)
        conn.execute(
            """
            INSERT INTO scan_roots (path, mode, note, status, last_error, created_at, updated_at)
            VALUES (?, ?, ?, 'idle', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(path) DO UPDATE SET mode = excluded.mode, note = excluded.note, updated_at = CURRENT_TIMESTAMP
            """,
            (normalized, mode, note or ""),
        )
        try:
            sync_one_root(conn, normalized, mode)
        except AppError as exc:
            conn.execute(
                "UPDATE scan_roots SET status = 'error', last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (exc.message, normalized),
            )
            raise
        except Exception as exc:
            conn.execute(
                "UPDATE scan_roots SET status = 'error', last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (str(exc), normalized),
            )
            raise AppError(str(exc))


def update_scan_root(old_path_value: str, path_value: str, mode: str, note: str) -> None:
    old_path = normalize_path(old_path_value)
    normalized = validate_scan_root_input(path_value, mode)

    with db_conn() as conn:
        init_db(conn)
        existing_row = conn.execute("SELECT path FROM scan_roots WHERE path = ?", (old_path,)).fetchone()
        if existing_row is None:
            raise AppError("扫描源不存在。", HTTPStatus.NOT_FOUND)
        if old_path != normalized:
            conflict_row = conn.execute("SELECT path FROM scan_roots WHERE path = ?", (normalized,)).fetchone()
            if conflict_row is not None:
                raise AppError("目标扫描源已存在。")
            conn.execute("DELETE FROM skills WHERE root_path = ?", (old_path,))
            conn.execute(
                """
                UPDATE scan_roots
                SET path = ?, mode = ?, note = ?, status = 'idle', last_error = '', updated_at = CURRENT_TIMESTAMP
                WHERE path = ?
                """,
                (normalized, mode, note or "", old_path),
            )
        else:
            conn.execute(
                """
                UPDATE scan_roots
                SET mode = ?, note = ?, status = 'idle', last_error = '', updated_at = CURRENT_TIMESTAMP
                WHERE path = ?
                """,
                (mode, note or "", normalized),
            )
        try:
            sync_one_root(conn, normalized, mode)
        except AppError as exc:
            conn.execute(
                "UPDATE scan_roots SET status = 'error', last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (exc.message, normalized),
            )
            raise
        except Exception as exc:
            conn.execute(
                "UPDATE scan_roots SET status = 'error', last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                (str(exc), normalized),
            )
            raise AppError(str(exc))


def remove_scan_root(path_value: str) -> None:
    normalized = normalize_path(path_value)
    with db_conn() as conn:
        init_db(conn)
        conn.execute("DELETE FROM skills WHERE root_path = ?", (normalized,))
        conn.execute("DELETE FROM scan_roots WHERE path = ?", (normalized,))


def rescan_all_roots() -> None:
    with db_conn() as conn:
        init_db(conn)
        rows = row_dicts(conn.execute("SELECT path, mode FROM scan_roots"))
        for row in rows:
            try:
                sync_one_root(conn, row["path"], row["mode"])
            except Exception as exc:
                conn.execute(
                    "UPDATE scan_roots SET status = 'error', last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE path = ?",
                    (str(exc), row["path"]),
                )


def rescan_one_root(path_value: str, mode: str | None = None) -> None:
    normalized = normalize_path(path_value)
    with db_conn() as conn:
        init_db(conn)
        row = conn.execute("SELECT mode FROM scan_roots WHERE path = ?", (normalized,)).fetchone()
        actual_mode = mode or (row["mode"] if row else None)
        if not actual_mode:
            raise AppError("扫描源不存在。", HTTPStatus.NOT_FOUND)
        sync_one_root(conn, normalized, actual_mode)
