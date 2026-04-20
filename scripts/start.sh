#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
APP_SCRIPT="$PROJECT_ROOT/src/skill-manage-server.py"
REQUIREMENTS_FILE="$PROJECT_ROOT/requirements.txt"
HOST="${SKILL_MANAGE_HOST:-${SKILL_MANAGER_HOST:-127.0.0.1}}"
PORT="${SKILL_MANAGE_PORT:-${SKILL_MANAGER_PORT:-8765}}"
PYTHON_BIN="${SKILL_MANAGE_PYTHON:-${SKILL_MANAGER_PYTHON:-python3}}"
LOG_FILE="$PROJECT_ROOT/logs/skill-manage.log"

if [[ ! -f "$APP_SCRIPT" ]]; then
  echo "service script not found: $APP_SCRIPT" >&2
  exit 1
fi

mkdir -p "$PROJECT_ROOT/logs"
export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

check_python_env() {
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "启动失败，需检查 Python 环境。" >&2
    echo "未找到 Python 可执行文件: $PYTHON_BIN" >&2
    exit 1
  fi

  if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import sys

if sys.version_info < (3, 10):
    raise SystemExit(1)
PY
  then
    echo "启动失败，需检查 Python 环境。" >&2
    echo "当前 Python 版本低于 3.10，或 Python 环境异常。" >&2
    exit 1
  fi
}

has_installable_requirements() {
  "$PYTHON_BIN" - <<'PY' "$REQUIREMENTS_FILE"
from pathlib import Path
import sys

requirements_file = Path(sys.argv[1])
if not requirements_file.exists():
    raise SystemExit(1)

has_requirements = any(
    line.strip() and not line.lstrip().startswith("#")
    for line in requirements_file.read_text(encoding="utf-8").splitlines()
)
raise SystemExit(0 if has_requirements else 1)
PY
}

install_dependencies() {
  echo "项目依赖清单:"
  echo "- Python 3.10+"

  if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
    echo "启动失败，需检查 Python 环境。" >&2
    echo "缺少依赖文件: $REQUIREMENTS_FILE" >&2
    exit 1
  fi

  if has_installable_requirements; then
    if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
      echo "启动失败，需检查 Python 环境。" >&2
      echo "当前 Python 环境缺少 pip，无法自动安装依赖。" >&2
      exit 1
    fi

    echo "- 第三方依赖: 见 $REQUIREMENTS_FILE"
    echo "开始安装第三方依赖..."
    "$PYTHON_BIN" -m pip install -r "$REQUIREMENTS_FILE"
  else
    echo "- 第三方依赖: 无"
    echo "未检测到需要安装的第三方依赖。"
  fi
}

check_python_env
install_dependencies

existing_pids="$(lsof -ti "tcp:$PORT" 2>/dev/null || true)"
if [[ -n "$existing_pids" ]]; then
  while IFS= read -r pid; do
    [[ -z "$pid" ]] && continue
    command_line="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$command_line" == *"skill-manage-server.py"* ]]; then
      kill "$pid" 2>/dev/null || true
    else
      echo "port $PORT is occupied by another process: $command_line" >&2
      exit 1
    fi
  done <<< "$existing_pids"
  sleep 1
fi

export SKILL_MANAGE_APP_SCRIPT="$APP_SCRIPT"
export SKILL_MANAGE_HOST_VALUE="$HOST"
export SKILL_MANAGE_PORT_VALUE="$PORT"
export SKILL_MANAGE_PYTHON_VALUE="$PYTHON_BIN"
export SKILL_MANAGE_LOG_FILE="$LOG_FILE"

new_pid="$("$PYTHON_BIN" - <<'PY'
import os
import subprocess
from pathlib import Path

app_script = Path(os.environ["SKILL_MANAGE_APP_SCRIPT"]).resolve()
host = os.environ["SKILL_MANAGE_HOST_VALUE"]
port = os.environ["SKILL_MANAGE_PORT_VALUE"]
python_bin = os.environ["SKILL_MANAGE_PYTHON_VALUE"]
log_file = Path(os.environ["SKILL_MANAGE_LOG_FILE"]).resolve()

command = [python_bin, str(app_script), "--host", host, "--port", port]

with open(log_file, "ab") as log_handle:
    process = subprocess.Popen(
        command,
        cwd=str(app_script.parent),
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=log_handle,
        start_new_session=True,
    )

print(process.pid)
PY
)"

echo "skill-manage started"
echo "pid: $new_pid"
echo "url: http://$HOST:$PORT/"
echo "log: $LOG_FILE"
