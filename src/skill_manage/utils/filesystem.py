from __future__ import annotations

import os
from datetime import datetime

from ..config import BINARY_EXTENSIONS, SKIP_DIRS, TEXT_READ_LIMIT
from ..errors import AppError
from .paths import normalize_path


def path_exists(target_path: str) -> bool:
    return os.path.lexists(target_path)


def is_directory(target_path: str) -> bool:
    return os.path.isdir(target_path)


def is_skill_dir(target_path: str) -> bool:
    return is_directory(target_path) and os.path.isfile(os.path.join(target_path, "SKILL.md"))


def is_system_skill_path(target_path: str | None) -> bool:
    return "/.system/" in (target_path or "").replace("\\", "/")


def fs_created_meta(target_path: str, *, follow_symlinks: bool) -> tuple[str, float]:
    try:
        stat_result = os.stat(target_path, follow_symlinks=follow_symlinks)
    except OSError:
        return "", 0.0

    created_ts = float(getattr(stat_result, "st_birthtime", stat_result.st_ctime))
    created_at = ""
    if created_ts > 0:
        created_at = datetime.fromtimestamp(created_ts).strftime("%Y-%m-%d %H:%M:%S")
    return created_at, created_ts


def collect_skill_dirs(root_path: str, mode: str) -> list[str]:
    if mode == "skill_dir":
        if not is_skill_dir(root_path):
            raise AppError("当前目录不包含 SKILL.md，不能作为单个 Skill 目录收录。")
        return [root_path]

    if not is_directory(root_path):
        raise AppError("扫描源路径不存在或不是目录。")

    found: list[str] = []
    stack = [root_path]
    visited: set[str] = set()

    while stack:
        current = stack.pop()
        try:
            real_current = os.path.realpath(current)
        except OSError:
            continue

        if real_current in visited:
            continue
        visited.add(real_current)

        try:
            with os.scandir(current) as iterator:
                entries = list(iterator)
        except OSError:
            continue

        has_skill_md = any(entry.is_file(follow_symlinks=False) and entry.name == "SKILL.md" for entry in entries)
        if has_skill_md:
            found.append(normalize_path(current))
            continue

        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            if entry.name in SKIP_DIRS:
                continue
            stack.append(entry.path)

    return sorted(set(found), key=str.lower)


def resolve_symlink_target(folder_path: str, raw_target: str) -> str:
    folder_real_path = normalize_path(os.path.realpath(folder_path))
    if os.path.isabs(raw_target):
        return normalize_path(raw_target)
    return normalize_path(os.path.join(folder_real_path, raw_target))


def pick_directory_destination(root_path: str, name: str) -> str:
    candidate = os.path.join(root_path, name)
    index = 2
    while path_exists(candidate):
        candidate = os.path.join(root_path, f"{name}__{index}")
        index += 1
    return candidate


def is_text_file(file_path: str) -> bool:
    ext = os.path.splitext(file_path)[1].lower()
    return ext not in BINARY_EXTENSIONS


def read_file_text(file_path: str, limit: int = TEXT_READ_LIMIT) -> str:
    if not os.path.isfile(file_path):
        return ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""

