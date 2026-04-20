from __future__ import annotations

import sys

from ..db import db_conn, init_db
from ..paths import DB_PATH, HTML_PATH, PROJECT_ROOT, SERVER_SCRIPT_PATH
from ..repositories.agent_links import fetch_agent_entries
from ..repositories.agent_targets import ensure_agent_targets, fetch_agents, fetch_agent_targets
from ..repositories.local_skills import fetch_local_skills
from ..repositories.operation_logs import fetch_operation_logs_page
from ..repositories.scan_roots import fetch_scan_roots
from .agents import scan_agent_folder
from .local_skills import sync_local_skill_status


def build_state(server_url: str) -> dict:
    with db_conn() as conn:
        init_db(conn)
        ensure_agent_targets(conn)
        sync_local_skill_status(conn)
        agents = fetch_agents(conn)
        targets = fetch_agent_targets(conn)
        for agent in agents:
            scan_agent_folder(conn, agent["agent_code"], agent["configured_path"])
        targets = fetch_agent_targets(conn)
        agents = fetch_agents(conn)
        return {
            "runtime": {
                "server_url": server_url,
                "html_path": str(HTML_PATH),
                "app_dir": str(PROJECT_ROOT),
                "db_path": str(DB_PATH),
                "python_version": sys.version.split()[0],
                "script_path": str(SERVER_SCRIPT_PATH),
            },
            "scanRoots": fetch_scan_roots(conn),
            "localSkills": fetch_local_skills(conn),
            "agents": agents,
            "agentTargets": targets,
            "agentEntries": fetch_agent_entries(conn),
            "operationLogs": fetch_operation_logs_page(conn),
        }
