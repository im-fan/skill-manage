from __future__ import annotations

import os
import shutil
import sqlite3

from ..config import AGENTS, SKIP_DIRS
from ..db import db_conn, init_db, row_dicts
from ..errors import AppError
from ..repositories.agent_links import fetch_agent_entries, require_agent_entry, upsert_agent_entries
from ..repositories.agent_targets import (
    detect_agent_path,
    ensure_agent_targets,
    fetch_agent_row,
    fetch_agents,
    require_agent_row,
    update_agent_visibility,
    upsert_agent,
)
from ..repositories.local_skills import upsert_local_skill
from ..utils.filesystem import fs_created_meta, is_directory, is_skill_dir, path_exists, pick_directory_destination, resolve_symlink_target
from ..utils.paths import normalize_path
from .local_skills import sync_one_root


def require_agent(agent_code: str) -> dict:
    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        row = require_agent_row(conn, agent_code)
        return dict(row)


def list_agents(*, visible_only: bool = False) -> list[dict]:
    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        return fetch_agents(conn, visible_only=visible_only)


def create_agent(agent_code: str, display_name: str, default_path: str, configured_path: str | None = None, detected_path: str | None = None) -> None:
    normalized_code = str(agent_code or "").strip().lower()
    normalized_default = normalize_path(default_path)
    normalized_configured = normalize_path(configured_path) or normalized_default
    normalized_detected = normalize_path(detected_path)
    if not normalized_code:
        raise AppError("agent code 不能为空。")
    if not str(display_name or "").strip():
        raise AppError("agent 名称不能为空。")
    if not normalized_configured:
        raise AppError("请填写默认目录或当前目录。")

    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        if fetch_agent_row(conn, normalized_code) is not None:
            raise AppError("agent code 已存在。")
        upsert_agent(
            conn,
            agent_code=normalized_code,
            display_name=display_name,
            default_path=normalized_default,
            configured_path=normalized_configured,
            detected_path=normalized_detected,
            is_builtin=False,
            is_visible=True,
        )


def update_agent(
    agent_code: str,
    *,
    display_name: str,
    default_path: str,
    configured_path: str,
    detected_path: str | None = None,
    is_visible: bool | None = None,
) -> None:
    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        existing = require_agent_row(conn, agent_code)
        upsert_agent(
            conn,
            agent_code=existing["agent_code"],
            display_name=display_name,
            default_path=default_path,
            configured_path=configured_path,
            detected_path=detected_path if detected_path is not None else existing["detected_path"],
            is_builtin=bool(int(existing["is_builtin"])),
            is_visible=bool(int(existing["is_visible"])) if is_visible is None else is_visible,
            sort_order=int(existing["sort_order"]),
        )


def set_agent_visibility(agent_code: str, is_visible: bool) -> None:
    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        update_agent_visibility(conn, agent_code, is_visible)


def delete_agent(agent_code: str) -> None:
    normalized_code = str(agent_code or "").strip().lower()
    if not normalized_code:
        raise AppError("agent code 不能为空。")

    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        existing = require_agent_row(conn, normalized_code)
        conn.execute("DELETE FROM agent_links WHERE agent_code = ?", (existing["agent_code"],))
        conn.execute("DELETE FROM agents WHERE agent_code = ?", (existing["agent_code"],))
        conn.execute("DELETE FROM agent_targets WHERE agent_code = ?", (existing["agent_code"],))
        if bool(int(existing["is_builtin"])):
            conn.execute(
                """
                INSERT INTO deleted_builtin_agents (agent_code, deleted_at)
                VALUES (?, CURRENT_TIMESTAMP)
                ON CONFLICT(agent_code) DO UPDATE SET deleted_at = CURRENT_TIMESTAMP
                """,
                (existing["agent_code"],),
            )
        else:
            conn.execute("DELETE FROM deleted_builtin_agents WHERE agent_code = ?", (existing["agent_code"],))


def auto_discover_agents() -> list[str]:
    discovered: list[str] = []
    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        for agent in AGENTS:
            detection = detect_agent_path(agent)
            if not detection["detected"]:
                continue
            existing = fetch_agent_row(conn, agent["code"])
            conn.execute("DELETE FROM deleted_builtin_agents WHERE agent_code = ?", (agent["code"],))
            upsert_agent(
                conn,
                agent_code=agent["code"],
                display_name=agent["label"],
                default_path=detection["default_path"],
                configured_path=(existing["configured_path"] if existing else detection["detected"]) or detection["detected"],
                detected_path=detection["detected"],
                is_builtin=True,
                is_visible=True if existing is None else bool(int(existing["is_visible"])),
                sort_order=existing["sort_order"] if existing is not None else None,
            )
            discovered.append(agent["code"])
    return discovered


def scan_agent_default_to_local(agent_code: str) -> None:
    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        row = conn.execute(
            "SELECT display_name, configured_path, default_path FROM agents WHERE agent_code = ?",
            (agent_code,),
        ).fetchone()
        if row is None:
            raise AppError("未找到 agent 当前配置 skill 目录。")
        configured_path = normalize_path(row["configured_path"]) or normalize_path(row["default_path"])
        if not configured_path or not is_directory(configured_path):
            raise AppError("agent 当前配置 skill 目录不存在。")

        conn.execute(
            """
            INSERT INTO scan_roots (path, mode, note, status, last_error, created_at, updated_at)
            VALUES (?, 'skill_root', ?, 'idle', '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(path) DO UPDATE SET
              mode = 'skill_root',
              note = excluded.note,
              updated_at = CURRENT_TIMESTAMP
            """,
            (configured_path, f"{row['display_name']} 当前配置目录"),
        )
        sync_one_root(conn, configured_path, "skill_root")


def collect_agent_skill_entries(folder_path: str, max_depth: int = 2) -> list[dict]:
    normalized_root = normalize_path(folder_path)
    collected: list[dict] = []
    stack: list[tuple[str, int]] = [(normalized_root, 0)]

    while stack:
        current_dir, current_depth = stack.pop()
        try:
            children = sorted(os.scandir(current_dir), key=lambda entry: entry.name.lower())
        except OSError:
            continue

        for entry in reversed(children):
            entry_path = normalize_path(entry.path)
            relative_name = os.path.relpath(entry_path, normalized_root)

            try:
                if entry.is_symlink():
                    raw_target = os.readlink(entry_path)
                    resolved_target = resolve_symlink_target(os.path.dirname(entry_path), raw_target)
                    target_exists = os.path.exists(entry_path)
                    target_path = normalize_path(os.path.realpath(entry_path)) if target_exists else resolved_target
                    fs_created_at, fs_created_ts = fs_created_meta(entry_path, follow_symlinks=False)
                    has_skill_md = target_exists and is_skill_dir(target_path)
                    status = "linked"
                    reason = "软链接正常"
                    if not target_exists:
                        status = "invalid_missing_target"
                        reason = "软链接目标不存在"
                    elif not has_skill_md:
                        status = "invalid_missing_skill_md"
                        reason = "目标目录缺少 SKILL.md"

                    collected.append(
                        {
                            "link_path": entry_path,
                            "link_name": relative_name,
                            "target_path": target_path,
                            "target_display_path": resolved_target,
                            "link_kind": "symlink",
                            "status": status,
                            "status_reason": reason,
                            "fs_created_at": fs_created_at,
                            "fs_created_ts": fs_created_ts,
                        }
                    )
                    continue

                if not entry.is_dir(follow_symlinks=False):
                    continue
                if entry.name in SKIP_DIRS:
                    continue
                if is_skill_dir(entry_path):
                    fs_created_at, fs_created_ts = fs_created_meta(entry_path, follow_symlinks=True)
                    collected.append(
                        {
                            "link_path": entry_path,
                            "link_name": relative_name,
                            "target_path": entry_path,
                            "target_display_path": entry_path,
                            "link_kind": "direct",
                            "status": "direct",
                            "status_reason": "",
                            "is_managed": 0,
                            "fs_created_at": fs_created_at,
                            "fs_created_ts": fs_created_ts,
                        }
                    )
                    continue
                if current_depth + 1 < max_depth:
                    stack.append((entry_path, current_depth + 1))
            except OSError:
                continue

    return sorted(collected, key=lambda item: item["link_name"].lower())


def scan_agent_folder(conn: sqlite3.Connection, agent_code: str, folder_path: str) -> None:
    folder_path = normalize_path(folder_path)
    entries: list[dict] = []
    if folder_path and is_directory(folder_path):
        entries = collect_agent_skill_entries(folder_path, max_depth=2)
    upsert_agent_entries(conn, agent_code, entries)
    conn.execute(
        "UPDATE agents SET last_scan_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE agent_code = ?",
        (agent_code,),
    )


def save_agent_path(agent_code: str, path_value: str) -> None:
    normalized = normalize_path(path_value)
    if not normalized:
        raise AppError("请填写 agent skill 目录路径。")
    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        require_agent_row(conn, agent_code)
        conn.execute(
            """
            UPDATE agents
            SET configured_path = ?, updated_at = CURRENT_TIMESTAMP
            WHERE agent_code = ?
            """,
            (normalized, agent_code),
        )


def ensure_agent_folder(conn: sqlite3.Connection, agent_code: str) -> str:
    row = conn.execute(
        "SELECT configured_path FROM agents WHERE agent_code = ? LIMIT 1",
        (agent_code,),
    ).fetchone()
    if row is None or not row["configured_path"]:
        raise AppError("未配置 agent skill 目录。")
    folder_path = normalize_path(row["configured_path"])
    if path_exists(folder_path) and not is_directory(folder_path):
        raise AppError("agent skill 目录路径存在，但不是目录。")
    os.makedirs(folder_path, exist_ok=True)
    return folder_path


def resolve_existing_target(folder_path: str, link_name: str) -> str | None:
    target = os.path.join(folder_path, link_name)
    if not path_exists(target):
        return None
    if os.path.islink(target):
        return resolve_symlink_target(folder_path, os.readlink(target))
    return normalize_path(target)


def pick_link_name(folder_path: str, skill_path: str) -> str:
    base_name = os.path.basename(skill_path)
    candidate = base_name
    index = 2
    while True:
        existing_target = resolve_existing_target(folder_path, candidate)
        if existing_target is None or existing_target == skill_path:
            return candidate
        candidate = f"{base_name}__{index}"
        index += 1


def ensure_entry_in_agent_folder(conn: sqlite3.Connection, agent_code: str, link_path: str) -> str:
    row = conn.execute(
        "SELECT configured_path FROM agents WHERE agent_code = ? LIMIT 1",
        (agent_code,),
    ).fetchone()
    folder_path = normalize_path(row["configured_path"] if row else "")
    if not folder_path:
        raise AppError("未配置 agent skill 目录。")
    normalized = normalize_path(link_path)
    try:
        inside = os.path.commonpath([folder_path, normalized]) == folder_path
    except ValueError:
        inside = False
    if not inside:
        raise AppError("目标路径不在当前 agent skill 目录中。")
    return folder_path


def choose_local_library_root(conn: sqlite3.Connection, source_path: str, preferred_root: str | None = None) -> str:
    source_parent = normalize_path(os.path.dirname(source_path))
    if preferred_root:
        normalized = normalize_path(preferred_root)
        row = conn.execute("SELECT mode FROM scan_roots WHERE path = ? LIMIT 1", (normalized,)).fetchone()
        if row is None or row["mode"] != "skill_root":
            raise AppError("目标SKILL仓库不存在，或不是 skill_root 扫描源。")
        if normalized == source_parent:
            raise AppError("目标SKILL仓库不能与当前 agent 目录相同。")
        if not is_directory(normalized):
            raise AppError("目标SKILL仓库目录不存在。")
        return normalized

    rows = row_dicts(
        conn.execute(
            """
            SELECT path
            FROM scan_roots
            WHERE mode = 'skill_root'
            ORDER BY updated_at DESC, path COLLATE NOCASE
            """
        )
    )
    for row in rows:
        candidate = normalize_path(row["path"])
        if candidate == source_parent or not is_directory(candidate):
            continue
        return candidate

    raise AppError("没有可用的SKILL仓库根目录。请先在“SKILL仓库”页签新增一个 skill_root 扫描源。")


def link_skill(agent_code: str, skill_path: str) -> None:
    normalized_skill = normalize_path(skill_path)
    if not is_skill_dir(normalized_skill):
        raise AppError("目标SKILL目录不存在，或已缺失 SKILL.md。")

    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        require_agent_row(conn, agent_code)
        folder_path = ensure_agent_folder(conn, agent_code)
        scan_agent_folder(conn, agent_code, folder_path)
        existing = conn.execute(
            """
            SELECT link_path, link_name
            FROM agent_links
            WHERE agent_code = ? AND target_path = ? AND status = 'linked'
            LIMIT 1
            """,
            (agent_code, normalized_skill),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE agent_links SET is_managed = 1, updated_at = CURRENT_TIMESTAMP WHERE link_path = ?",
                (existing["link_path"],),
            )
            return

        link_name = pick_link_name(folder_path, normalized_skill)
        link_path = os.path.join(folder_path, link_name)
        relative_target = os.path.relpath(normalized_skill, start=os.path.realpath(folder_path)) or "."
        os.symlink(relative_target, link_path)
        conn.execute(
            """
            INSERT INTO agent_links (
              link_path, agent_code, link_name, target_path, target_display_path, link_kind,
              status, status_reason, is_managed, last_scan_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 'symlink', 'linked', '软链接正常', 1,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(link_path) DO UPDATE SET is_managed = 1, updated_at = CURRENT_TIMESTAMP
            """,
            (link_path, agent_code, link_name, normalized_skill, normalized_skill),
        )


def delete_agent_direct_skill(agent_code: str, link_path: str) -> None:
    normalized = normalize_path(link_path)
    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        require_agent_row(conn, agent_code)
        folder_path = ensure_entry_in_agent_folder(conn, agent_code, normalized)
        entry = require_agent_entry(conn, agent_code, normalized)
        if entry["link_kind"] != "direct":
            raise AppError("只能删除普通 Skill，关联软链接请使用“移除”。")
        if path_exists(normalized):
            if os.path.islink(normalized) or not is_directory(normalized):
                raise AppError("目标不是可删除的普通 Skill 目录。")
            shutil.rmtree(normalized)
        conn.execute("DELETE FROM skills WHERE path = ?", (normalized,))
        scan_agent_folder(conn, agent_code, folder_path)


def move_agent_direct_skill_to_local(agent_code: str, link_path: str, root_path: str | None = None) -> str:
    normalized = normalize_path(link_path)
    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        require_agent_row(conn, agent_code)
        folder_path = ensure_entry_in_agent_folder(conn, agent_code, normalized)
        entry = require_agent_entry(conn, agent_code, normalized)
        if entry["link_kind"] != "direct":
            raise AppError("只能移动普通 Skill，关联软链接无需移动。")
        if not is_skill_dir(normalized):
            raise AppError("目标普通 Skill 目录不存在，或缺少 SKILL.md。")

        target_root = choose_local_library_root(conn, normalized, root_path)
        destination_path = pick_directory_destination(target_root, os.path.basename(normalized))
        moved = False
        try:
            shutil.move(normalized, destination_path)
            moved = True
            relative_target = os.path.relpath(destination_path, start=os.path.realpath(folder_path)) or "."
            os.symlink(relative_target, normalized)
        except Exception as exc:
            if moved and not path_exists(normalized) and path_exists(destination_path):
                try:
                    shutil.move(destination_path, normalized)
                except Exception:
                    pass
            raise AppError(f"移动 Skill 失败: {exc}")

        conn.execute("DELETE FROM skills WHERE path = ?", (normalized,))
        upsert_local_skill(conn, destination_path, target_root)
        sync_one_root(conn, target_root, "skill_root")
        scan_agent_folder(conn, agent_code, folder_path)
        return destination_path


def remove_agent_link(link_path: str) -> None:
    normalized = normalize_path(link_path)
    with db_conn() as conn:
        init_db(conn)
        if path_exists(normalized):
            if not os.path.islink(normalized):
                raise AppError("只能移除软链接，真实目录不会被页面删除。")
            os.unlink(normalized)
        conn.execute("DELETE FROM agent_links WHERE link_path = ?", (normalized,))


def cleanup_invalid(agent_code: str) -> int:
    removed = 0
    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        require_agent_row(conn, agent_code)
        rows = row_dicts(
            conn.execute(
                """
                SELECT link_path
                FROM agent_links
                WHERE agent_code = ?
                  AND status IN ('invalid_missing_target', 'invalid_missing_skill_md')
                """,
                (agent_code,),
            )
        )
        for row in rows:
            try:
                if path_exists(row["link_path"]) and os.path.islink(row["link_path"]):
                    os.unlink(row["link_path"])
                removed += 1
            except OSError:
                removed += 1
            conn.execute("DELETE FROM agent_links WHERE link_path = ?", (row["link_path"],))
    return removed
