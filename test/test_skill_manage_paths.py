import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from skill_manage import paths as paths_module


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


if __name__ == "__main__":
    unittest.main()
