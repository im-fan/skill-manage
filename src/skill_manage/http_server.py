from __future__ import annotations

import ipaddress
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

from .config import DEFAULT_OPERATION_LOG_PAGE_SIZE, HTML_FILENAME, MAX_OPERATION_LOG_PAGE_SIZE
from .db import db_conn, init_db
from .errors import AppError
from .paths import HTML_PATH
from .repositories.agent_targets import ensure_agent_targets
from .repositories.operation_logs import append_operation_log, fetch_operation_logs_page, parse_positive_int
from .services.agents import (
    auto_discover_agents,
    cleanup_invalid,
    create_agent,
    delete_agent,
    delete_agent_direct_skill,
    link_skill,
    list_agents,
    move_agent_direct_skill_to_local,
    remove_agent_link,
    require_agent,
    save_agent_path,
    scan_agent_default_to_local,
    scan_agent_folder,
    set_agent_visibility,
    update_agent,
)
from .services.local_skills import (
    move_local_skill_to_root,
    remove_local_skill,
    remove_scan_root,
    rescan_all_roots,
    rescan_one_root,
    save_scan_root,
    update_scan_root,
)
from .services.similarity import find_similar_local_skills, find_similar_skills
from .services.state import build_state


def _is_loopback_origin_host(host: str | None) -> bool:
    normalized = str(host or "").strip()
    if not normalized:
        return False
    if normalized.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def allowed_cors_origin(origin: str | None) -> str | None:
    if not origin:
        return None
    parsed = urlparse(origin)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not _is_loopback_origin_host(parsed.hostname):
        return None
    return origin


class SkillManageHandler(BaseHTTPRequestHandler):
    server_version = "SkillManagerHTTP/1.0"

    def log_message(self, format: str, *args) -> None:
        return

    def end_headers(self) -> None:
        origin = allowed_cors_origin(self.headers.get("Origin"))
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        super().end_headers()

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        return json.loads(raw) if raw else {}

    def write_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def write_html(self, html: str) -> None:
        data = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def server_url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}"

    def respond_ok(self, message: str | None = None) -> None:
        self.write_json({"ok": True, "message": message or "", "state": build_state(self.server_url())})

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        try:
            parsed = urlparse(self.path)
            if parsed.path in {"/", f"/{HTML_FILENAME}"}:
                if not HTML_PATH.is_file():
                    raise AppError(f"页面文件不存在: {HTML_PATH}", HTTPStatus.NOT_FOUND)
                self.write_html(HTML_PATH.read_text("utf-8"))
                return

            if parsed.path == "/api/state":
                self.write_json({"ok": True, "state": build_state(self.server_url())})
                return

            if parsed.path == "/api/agents":
                self.write_json({"ok": True, "items": list_agents()})
                return

            if parsed.path == "/api/operation-logs":
                query = parse_qs(parsed.query)
                page = parse_positive_int(query.get("page", [""])[0], default=1)
                page_size = parse_positive_int(
                    query.get("page_size", [""])[0],
                    default=DEFAULT_OPERATION_LOG_PAGE_SIZE,
                    maximum=MAX_OPERATION_LOG_PAGE_SIZE,
                )
                with db_conn() as conn:
                    init_db(conn)
                    payload = fetch_operation_logs_page(conn, page=page, page_size=page_size)
                self.write_json({"ok": True, **payload})
                return

            raise AppError("接口不存在。", HTTPStatus.NOT_FOUND)
        except AppError as exc:
            self.write_json({"ok": False, "error": exc.message}, exc.status)
        except Exception as exc:
            self.write_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        try:
            parsed = urlparse(self.path)
            body = self.read_json()

            if parsed.path == "/api/scan-roots":
                save_scan_root(body.get("path"), body.get("mode"), body.get("note", ""))
                self.respond_ok("扫描源已保存并完成扫描")
                return

            if parsed.path == "/api/scan-roots/update":
                update_scan_root(body.get("old_path"), body.get("path"), body.get("mode"), body.get("note", ""))
                self.respond_ok("扫描源已更新并完成扫描")
                return

            if parsed.path == "/api/scan-roots/rescan":
                rescan_all_roots()
                self.respond_ok("已重扫全部扫描源")
                return

            if parsed.path == "/api/agents":
                create_agent(
                    body.get("agent_code"),
                    body.get("display_name"),
                    body.get("default_path", ""),
                    body.get("configured_path", ""),
                    body.get("detected_path", ""),
                )
                self.respond_ok("Agent 已创建")
                return

            if parsed.path == "/api/agents/update":
                update_agent(
                    body.get("agent_code"),
                    display_name=body.get("display_name"),
                    default_path=body.get("default_path", ""),
                    configured_path=body.get("configured_path", ""),
                    detected_path=body.get("detected_path"),
                    is_visible=body.get("is_visible"),
                )
                self.respond_ok("Agent 已更新")
                return

            if parsed.path == "/api/agents/auto-discover":
                discovered = auto_discover_agents()
                self.write_json(
                    {
                        "ok": True,
                        "discovered": discovered,
                        "message": f"已自动检索 {len(discovered)} 个 Agent",
                        "state": build_state(self.server_url()),
                    }
                )
                return

            if parsed.path == "/api/agents/visibility":
                set_agent_visibility(body.get("agent_code"), bool(body.get("is_visible")))
                self.respond_ok("Agent 显示状态已更新")
                return

            if parsed.path == "/api/scan-roots/item/rescan":
                rescan_one_root(body.get("path"), body.get("mode"))
                self.respond_ok("已重扫扫描源")
                return

            if parsed.path == "/api/local-skills":
                with db_conn() as conn:
                    init_db(conn)
                    from .repositories.local_skills import upsert_local_skill

                    upsert_local_skill(conn, body.get("skill_path"), body.get("root_path"))
                self.respond_ok("已加入SKILL仓库")
                return

            if parsed.path == "/api/operation-logs":
                with db_conn() as conn:
                    init_db(conn)
                    entries = body.get("entries")
                    if entries is not None:
                        if not isinstance(entries, list):
                            raise AppError("entries 必须是数组。")
                        items = []
                        for entry in entries:
                            if not isinstance(entry, dict):
                                raise AppError("entries 中的每一项都必须是对象。")
                            items.append(
                                append_operation_log(
                                    conn,
                                    message=entry.get("message"),
                                    detail=entry.get("detail", ""),
                                    level=entry.get("level"),
                                    source=entry.get("source", "ui"),
                                    action=entry.get("action", ""),
                                    detail_summary=entry.get("detail_summary"),
                                )
                            )
                    else:
                        items = [
                            append_operation_log(
                                conn,
                                message=body.get("message"),
                                detail=body.get("detail", ""),
                                level=body.get("level"),
                                source=body.get("source", "ui"),
                                action=body.get("action", ""),
                                detail_summary=body.get("detail_summary"),
                            )
                        ]
                    page = fetch_operation_logs_page(conn)
                self.write_json({"ok": True, "items": items, **page})
                return

            if parsed.path == "/api/local-skills/find-similar":
                min_similarity = _parse_similarity(body.get("min_similarity", 0.5))
                pairs = find_similar_local_skills(min_similarity)
                self.write_json({"ok": True, "similar": pairs, "state": build_state(self.server_url())})
                return

            if parsed.path == "/api/local-skills/move":
                destination_path = move_local_skill_to_root(body.get("skill_path"), body.get("root_path"))
                self.respond_ok(f"SKILL已移动到其他扫描源：{destination_path}")
                return

            parts = [part for part in parsed.path.split("/") if part]
            if len(parts) == 4 and parts[0] == "api" and parts[1] == "agents":
                agent_code = parts[2]
                action = parts[3]
                require_agent(agent_code)

                if action == "path":
                    save_agent_path(agent_code, body.get("path"))
                    self.respond_ok("agent 目录已保存")
                    return

                if action == "scan":
                    with db_conn() as conn:
                        init_db(conn)
                        ensure_agent_targets(conn)
                        row = conn.execute(
                            "SELECT configured_path FROM agent_targets WHERE agent_code = ?",
                            (agent_code,),
                        ).fetchone()
                        scan_agent_folder(conn, agent_code, row["configured_path"])
                    self.respond_ok("agent 目录已刷新")
                    return

                if action == "link":
                    link_skill(agent_code, body.get("skill_path"))
                    self.respond_ok("skill 已挂载")
                    return

                if action == "delete-direct-skill":
                    delete_agent_direct_skill(agent_code, body.get("link_path"))
                    self.respond_ok("普通 Skill 已删除")
                    return

                if action == "move-direct-to-local":
                    destination_path = move_agent_direct_skill_to_local(agent_code, body.get("link_path"), body.get("root_path"))
                    self.respond_ok(f"普通 Skill 已移动到SKILL仓库：{destination_path}")
                    return

                if action == "cleanup-invalid":
                    removed = cleanup_invalid(agent_code)
                    self.respond_ok(f"已清理失效链接 {removed} 个")
                    return

                if action == "scan-default-to-local":
                    scan_agent_default_to_local(agent_code)
                    self.respond_ok("已扫描 agent 当前配置目录并写入SKILL仓库")
                    return

                if action == "find-similar":
                    min_similarity = _parse_similarity(body.get("min_similarity", 0.5))
                    pairs = find_similar_skills(agent_code, min_similarity)
                    self.write_json({"ok": True, "similar": pairs, "state": build_state(self.server_url())})
                    return

            raise AppError("接口不存在。", HTTPStatus.NOT_FOUND)
        except AppError as exc:
            self.write_json({"ok": False, "error": exc.message}, exc.status)
        except Exception as exc:
            self.write_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_DELETE(self) -> None:
        try:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path == "/api/scan-roots":
                remove_scan_root(query.get("path", [""])[0])
                self.respond_ok("扫描源已移除")
                return

            if parsed.path == "/api/links":
                remove_agent_link(query.get("path", [""])[0])
                self.respond_ok("软链接已移除")
                return

            if parsed.path == "/api/local-skills":
                removed_links = remove_local_skill(query.get("path", [""])[0])
                self.respond_ok(f"SKILL已删除，并清理软链接 {removed_links} 个")
                return

            if parsed.path == "/api/agents":
                delete_agent(query.get("agent_code", [""])[0])
                self.respond_ok("Agent 已删除")
                return

            raise AppError("接口不存在。", HTTPStatus.NOT_FOUND)
        except AppError as exc:
            self.write_json({"ok": False, "error": exc.message}, exc.status)
        except Exception as exc:
            self.write_json({"ok": False, "error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)


def _parse_similarity(raw_similarity: object) -> float:
    try:
        min_similarity = float(raw_similarity)
    except (TypeError, ValueError):
        raise AppError("min_similarity 必须是数字。")
    if min_similarity < 0.2 or min_similarity > 1.0:
        raise AppError("min_similarity 范围必须在 0.2 到 1.0 之间。")
    return min_similarity
