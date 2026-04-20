from __future__ import annotations

import json
import os
import re

from ..config import (
    MAX_OPERATION_LOG_DETAIL_LENGTH,
    MAX_OPERATION_LOG_MESSAGE_LENGTH,
    MAX_OPERATION_LOG_SUMMARY_LENGTH,
    SKIP_DIRS,
    TEXT_READ_LIMIT,
)
from .filesystem import is_directory, is_text_file, read_file_text
from .paths import normalize_path


def read_skill_description(skill_path: str) -> str:
    skill_md = os.path.join(skill_path, "SKILL.md")
    if not os.path.isfile(skill_md):
        return ""

    try:
        with open(skill_md, "r", encoding="utf-8") as handle:
            lines = handle.read(6000).splitlines()
    except OSError:
        return ""

    description_lines: list[str] = []
    started = False
    in_code_block = False

    for raw_line in lines[:80]:
        line = raw_line.strip().lstrip("\ufeff")
        if line.startswith("```"):
            in_code_block = not in_code_block
            if started:
                break
            continue
        if in_code_block:
            continue
        if not line:
            if started:
                break
            continue
        if line.startswith("#"):
            continue
        if re.fullmatch(r"[>|:\-\s|]+", line):
            continue

        line = re.sub(r"^\s*>\s*", "", line)
        line = re.sub(r"^\s*\|\s*", "", line).strip()
        if not line:
            continue

        explicit_prefixes = ("description:", "desc:", "描述:", "描述：")
        lower = line.lower()
        if lower.startswith(explicit_prefixes[:2]) or line.startswith(explicit_prefixes[2:]):
            parts = re.split(r"[:：]", line, maxsplit=1)
            return parts[1].strip()[:500] if len(parts) > 1 else ""

        if not started and (re.match(r"^[-*]\s", line) or re.match(r"^\d+\.\s", line)):
            continue

        description_lines.append(line)
        started = True

    return " ".join(description_lines)[:500]


def normalize_operation_log_level(level: str | None) -> str:
    value = str(level or "info").strip().lower()
    return value if value in {"info", "ok", "warn", "danger"} else "info"


def normalize_operation_log_text(value: object, limit: int) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False)
    return re.sub(r"\s+", " ", text).strip()[:limit]


def build_operation_log_summary(detail: str, message: str) -> str:
    summary = detail or message
    return normalize_operation_log_text(summary, MAX_OPERATION_LOG_SUMMARY_LENGTH)


def normalize_message_text(value: object) -> str:
    return normalize_operation_log_text(value, MAX_OPERATION_LOG_MESSAGE_LENGTH)


def normalize_detail_text(value: object) -> str:
    return normalize_operation_log_text(value, MAX_OPERATION_LOG_DETAIL_LENGTH)


def normalize_summary_text(value: object) -> str:
    return normalize_operation_log_text(value, MAX_OPERATION_LOG_SUMMARY_LENGTH)


def collect_skill_full_text(skill_path: str) -> str:
    normalized = normalize_path(skill_path)
    if not is_directory(normalized):
        return ""

    parts: list[str] = [os.path.basename(normalized)]
    skill_md = os.path.join(normalized, "SKILL.md")
    if os.path.isfile(skill_md):
        parts.append(read_file_text(skill_md))

    stack = [normalized]
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
                for entry in iterator:
                    if entry.name in SKIP_DIRS:
                        continue
                    if entry.is_file(follow_symlinks=False) and entry.name != "SKILL.md" and is_text_file(entry.path):
                        parts.append(read_file_text(entry.path))
                    elif entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
        except OSError:
            continue

    return "\n".join(parts)[:TEXT_READ_LIMIT]


def tokenize_similarity_text(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9_][a-z0-9_.-]*", text.lower())


def build_bigrams(tokens: list[str]) -> set[str]:
    if len(tokens) < 2:
        return set(tokens)
    return set(" ".join(tokens[i : i + 2]) for i in range(len(tokens) - 1))


def pick_overlap_samples(shared_items: set[str], *, limit: int = 6) -> list[str]:
    if not shared_items:
        return []
    return sorted(shared_items, key=lambda item: (-len(item), item))[:limit]


def analyze_similarity(text1: str, text2: str) -> dict:
    tokens1 = tokenize_similarity_text(text1)
    tokens2 = tokenize_similarity_text(text2)
    if not tokens1 or not tokens2:
        return {
            "similarity": 0.0,
            "word_overlap": 0.0,
            "phrase_overlap": 0.0,
            "shared_keywords": [],
            "shared_phrases": [],
        }

    set1, set2 = set(tokens1), set(tokens2)
    word_jaccard = len(set1 & set2) / len(set1 | set2)
    shared_words = set1 & set2

    bg1, bg2 = build_bigrams(tokens1), build_bigrams(tokens2)
    bigram_union = len(bg1 | bg2)
    bigram_jaccard = len(bg1 & bg2) / bigram_union if bigram_union else 0.0
    shared_bigrams = bg1 & bg2

    similarity = round(0.4 * word_jaccard + 0.6 * bigram_jaccard, 4)
    return {
        "similarity": similarity,
        "word_overlap": round(word_jaccard, 4),
        "phrase_overlap": round(bigram_jaccard, 4),
        "shared_keywords": pick_overlap_samples(shared_words),
        "shared_phrases": pick_overlap_samples(shared_bigrams, limit=4),
    }
