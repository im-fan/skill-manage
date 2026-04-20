from __future__ import annotations

from ..db import db_conn, init_db
from ..errors import AppError
from ..repositories.local_skills import fetch_local_skills
from ..repositories.agent_targets import ensure_agent_targets
from ..utils.filesystem import is_directory
from ..utils.paths import normalize_path
from ..utils.text import analyze_similarity, collect_skill_full_text, read_skill_description
from .agents import collect_agent_skill_entries, require_agent
from .local_skills import sync_local_skill_status


def serialize_similarity_item(item: dict) -> dict:
    return {
        "name": item["name"],
        "path": item["path"],
        "entry_path": item.get("entry_path", item["path"]),
        "description": item.get("description", ""),
        "kind": item.get("kind", "skill"),
        "kind_label": item.get("kind_label", "Skill"),
    }


def find_similar_pairs(items: list[dict], min_similarity: float) -> list[dict]:
    if len(items) < 2:
        return []

    text_cache: dict[str, str] = {}
    pairs: list[dict] = []

    for index, left in enumerate(items):
        left_key = left.get("text_key", left["path"])
        if left_key not in text_cache:
            text_cache[left_key] = collect_skill_full_text(left["path"])
        left_text = text_cache.get(left_key, "")
        if not left_text:
            continue

        for right in items[index + 1 :]:
            right_key = right.get("text_key", right["path"])
            if right_key not in text_cache:
                text_cache[right_key] = collect_skill_full_text(right["path"])
            right_text = text_cache.get(right_key, "")
            if not right_text:
                continue

            analysis = analyze_similarity(left_text, right_text)
            similarity = analysis["similarity"]
            if similarity < min_similarity:
                continue

            pairs.append(
                {
                    "left_skill": serialize_similarity_item(left),
                    "right_skill": serialize_similarity_item(right),
                    "similarity": similarity,
                    "reason": {
                        "shared_keywords": analysis["shared_keywords"],
                        "shared_phrases": analysis["shared_phrases"],
                        "word_overlap": analysis["word_overlap"],
                        "phrase_overlap": analysis["phrase_overlap"],
                    },
                }
            )

    pairs.sort(
        key=lambda item: (
            item["similarity"],
            item["left_skill"]["name"].lower(),
            item["right_skill"]["name"].lower(),
        ),
        reverse=True,
    )
    return pairs


def collect_agent_similarity_items(folder_path: str) -> list[dict]:
    if not is_directory(folder_path):
        return []

    items: list[dict] = []
    for entry in collect_agent_skill_entries(folder_path, max_depth=2):
        if entry["status"] not in {"linked", "direct"}:
            continue
        items.append(
            {
                "name": entry["link_name"],
                "path": entry["target_path"],
                "entry_path": entry["link_path"],
                "description": read_skill_description(entry["target_path"]),
                "kind": entry["status"],
                "kind_label": "挂载 Skill" if entry["status"] == "linked" else "正常 Skill",
                "text_key": entry["target_path"],
            }
        )
    return items


def collect_local_similarity_items(conn) -> list[dict]:
    items: list[dict] = []
    for skill in fetch_local_skills(conn):
        if skill["status"] != "ok":
            continue
        items.append(
            {
                "name": skill["name"],
                "path": skill["path"],
                "entry_path": skill["path"],
                "description": skill.get("description", ""),
                "kind": "local",
                "kind_label": "SKILL仓库",
                "text_key": skill["path"],
            }
        )
    return items


def find_similar_skills(agent_code: str, min_similarity: float) -> list[dict]:
    require_agent(agent_code)
    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        row = conn.execute(
            "SELECT configured_path FROM agent_targets WHERE agent_code = ?",
            (agent_code,),
        ).fetchone()
        if row is None or not row["configured_path"]:
            raise AppError("未配置 agent skill 目录。")

        folder_path = normalize_path(row["configured_path"])
        return find_similar_pairs(collect_agent_similarity_items(folder_path), min_similarity)


def find_similar_local_skills(min_similarity: float) -> list[dict]:
    with db_conn() as conn:
        init_db(conn)
        sync_local_skill_status(conn)
        return find_similar_pairs(collect_local_similarity_items(conn), min_similarity)
