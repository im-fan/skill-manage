import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from skill_manage import paths as paths_module
from skill_manage.db import init_db, row_dicts
from skill_manage.errors import AppError
from skill_manage.utils.git import _format_git_error, _run_git, derive_repo_name


class SkillManageHomePathsTest(unittest.TestCase):
    def test_skill_manage_home_moves_db_and_logs_without_moving_packaged_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir).resolve()
            original_home = os.environ.get("SKILL_MANAGE_HOME")
            os.environ["SKILL_MANAGE_HOME"] = temp_dir
            try:
                reloaded_paths = importlib.reload(paths_module)
                self.assertEqual(reloaded_paths.DATA_DIR, temp_path / "data")
                self.assertEqual(reloaded_paths.LOGS_DIR, temp_path / "logs")
                self.assertEqual(reloaded_paths.DB_PATH, temp_path / "data" / "skill-manage.sqlite3")
                self.assertEqual(reloaded_paths.LOG_PATH, temp_path / "logs" / "skill-manage.log")
                self.assertEqual(reloaded_paths.HTML_PATH, REPO_ROOT / "web" / "skill-manage.html")
                self.assertEqual(reloaded_paths.SERVER_SCRIPT_PATH, REPO_ROOT / "src" / "skill-manage-server.py")
            finally:
                if original_home is None:
                    os.environ.pop("SKILL_MANAGE_HOME", None)
                else:
                    os.environ["SKILL_MANAGE_HOME"] = original_home
                importlib.reload(paths_module)


class SkillManageGitScanRootTest(unittest.TestCase):
    def test_init_db_migrates_scan_roots_to_allow_git_repo_mode(self) -> None:
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(
                """
                CREATE TABLE scan_roots (
                  path TEXT PRIMARY KEY,
                  mode TEXT NOT NULL CHECK(mode IN ('skill_root', 'skill_dir')),
                  note TEXT DEFAULT '',
                  status TEXT DEFAULT 'idle',
                  last_error TEXT DEFAULT '',
                  last_scan_at TEXT,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            init_db(conn)
            conn.execute(
                "INSERT INTO scan_roots (path, mode, git_url) VALUES (?, ?, ?)",
                ("/tmp/qts-skills", "git_repo", "git@gitee.com:qts_ng/qts-skills.git"),
            )
            rows = row_dicts(conn.execute("SELECT mode, git_url FROM scan_roots"))
            self.assertEqual(rows[0]["mode"], "git_repo")
            self.assertEqual(rows[0]["git_url"], "git@gitee.com:qts_ng/qts-skills.git")
        finally:
            conn.close()

    def test_gitee_ssh_url_derives_stable_repo_name(self) -> None:
        self.assertEqual(
            derive_repo_name("git@gitee.com:qts_ng/qts-skills.git"),
            "gitee.com_qts_ng_qts-skills",
        )

    def test_git_permission_error_has_actionable_message(self) -> None:
        message = _format_git_error(
            "clone",
            """
            git@gitee.com: Permission denied (publickey).
            fatal: Could not read from remote repository.
            """,
        )
        self.assertIn("Git 仓库无权限或 SSH key 未配置", message)
        self.assertIn("Permission denied", message)

    def test_git_http_forbidden_error_prefers_permission_message(self) -> None:
        message = _format_git_error(
            "clone",
            "fatal: unable to access 'https://gitee.com/qts_ng/qts-skills.git/': The requested URL returned error: 403",
        )
        self.assertIn("Git 仓库无权限", message)

    def test_git_cannot_read_remote_error_has_permission_or_access_message(self) -> None:
        message = _format_git_error(
            "clone",
            "fatal: Could not read from remote repository.\nPlease make sure you have the correct access rights",
        )
        self.assertIn("Git 仓库无权限或地址不可访问", message)

    def test_git_missing_repo_error_has_address_message(self) -> None:
        message = _format_git_error("clone", "ERROR: Repository not found.")
        self.assertIn("Git 仓库不存在或地址错误", message)

    def test_git_dns_error_has_network_message(self) -> None:
        message = _format_git_error("clone", "fatal: unable to access: Could not resolve host: gitee.com")
        self.assertIn("无法解析 Git 主机", message)

    def test_git_timeout_raises_actionable_app_error(self) -> None:
        with patch("skill_manage.utils.git.subprocess.run") as mocked_run:
            mocked_run.side_effect = subprocess.TimeoutExpired(["git", "clone"], 180, stderr=b"ssh: connect timed out")
            with self.assertRaises(AppError) as context:
                _run_git(["git", "clone"], timeout=180, action="clone")
        self.assertIn("Git 仓库拉取超时", context.exception.message)
        self.assertIn("ssh: connect timed out", context.exception.message)


if __name__ == "__main__":
    unittest.main()
