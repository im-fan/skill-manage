from __future__ import annotations

import argparse
import ipaddress
import logging
import os
import webbrowser
from http.server import ThreadingHTTPServer

from .config import DEFAULT_HOST, DEFAULT_PORT, HTML_FILENAME
from .db import db_conn, init_db
from .http_server import SkillManageHandler
from .paths import DB_PATH, HTML_PATH, ensure_runtime_dirs
from .repositories.agent_targets import ensure_agent_targets

logger = logging.getLogger(__name__)
ALLOW_REMOTE_ENV = "SKILL_MANAGE_ALLOW_REMOTE"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=f"Local server for {HTML_FILENAME}")
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Bind host, default: {DEFAULT_HOST}")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Bind port, default: {DEFAULT_PORT}")
    parser.add_argument("--open", action="store_true", help="Open the page in the default browser after startup")
    return parser.parse_args()


def build_startup_log_lines(host: str, port: int) -> list[str]:
    url = f"http://{host}:{port}/"
    return [
        f"服务启动成功，监听端口: {port}，访问地址: {url}",
        f"HTML: {HTML_PATH}",
        f"SQLite3: {DB_PATH}",
    ]


def is_loopback_host(host: str) -> bool:
    normalized = str(host or "").strip()
    if not normalized:
        return False
    if normalized.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def validate_bind_host(host: str, *, allow_remote: bool | None = None) -> None:
    if is_loopback_host(host):
        return
    if allow_remote is None:
        allow_remote = os.environ.get(ALLOW_REMOTE_ENV, "").strip() == "1"
    if allow_remote:
        return
    raise ValueError(
        f"默认仅允许绑定本机回环地址。请使用 127.0.0.1 / localhost / ::1，"
        f"如需显式开放远程访问，请设置 {ALLOW_REMOTE_ENV}=1。"
    )


def configure_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def main() -> None:
    configure_logging()
    args = parse_args()
    try:
        validate_bind_host(args.host)
    except ValueError as exc:
        raise SystemExit(str(exc))
    ensure_runtime_dirs()
    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)

    server = ThreadingHTTPServer((args.host, args.port), SkillManageHandler)
    for line in build_startup_log_lines(args.host, args.port):
        logger.info(line)

    if args.open:
        webbrowser.open(f"http://{args.host}:{args.port}/")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("服务已停止。")
