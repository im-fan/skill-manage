from __future__ import annotations

import os
import re
import shutil
import subprocess
from urllib.parse import urlparse

from ..errors import AppError
from .paths import normalize_path


def derive_repo_name(git_url: str) -> str:
    """从 git URL 提取唯一目录名，包含 host 和 owner 以避免不同仓库同名冲突。

    git@github.com:user/repo.git   -> github.com_user_repo
    https://github.com/user/repo   -> github.com_user_repo
    """
    url = git_url.strip()
    if url.endswith(".git"):
        url = url[:-4]
    url = url.rstrip("/")

    host = ""
    path_part = ""

    if url.startswith("git@"):
        # SSH 格式: git@host:user/repo
        remainder = url[4:]
        host, separator, path_part = remainder.partition(":")
        if not separator or not host or not path_part:
            raise AppError("Git 仓库地址格式不合法，应类似 git@host:owner/repo.git。")
    elif "://" in url:
        # HTTP(S) 格式: https://host/user/repo
        parsed = urlparse(url)
        host = parsed.hostname or ""
        path_part = parsed.path.lstrip("/")
        if parsed.scheme not in {"http", "https", "ssh"} or not host or not path_part:
            raise AppError("Git 仓库地址格式不合法，支持 http/https/git@/ssh 协议。")
    else:
        path_part = url

    segments = [s for s in path_part.split("/") if s]
    if len(segments) < 2:
        raise AppError("Git 仓库地址格式不合法，应包含 owner/repo。")
    name = "_".join([host, *segments]) if host else "_".join(segments)
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    if not name:
        raise AppError("无法从 git URL 中提取仓库名。")
    return name


def resolve_local_path(git_url: str) -> str:
    """计算本地克隆路径: ~/.skill-manager/repos/<repo-name>"""
    from ..paths import RUNTIME_HOME

    repos_dir = RUNTIME_HOME / "repos"
    repos_dir.mkdir(parents=True, exist_ok=True)

    base_name = derive_repo_name(git_url)
    candidate = repos_dir / base_name
    index = 2
    while candidate.exists():
        git_config = candidate / ".git" / "config"
        if git_config.exists() and _git_config_matches(git_config, git_url):
            return normalize_path(str(candidate))
        candidate = repos_dir / f"{base_name}__{index}"
        index += 1
    return normalize_path(str(candidate))


def _git_config_matches(git_config_path, git_url: str) -> bool:
    """精确匹配 git config 中 [remote "origin"] 的 url 行。"""
    target = git_url.strip()
    target_no_git = target.removesuffix(".git")
    try:
        in_origin = False
        for line in git_config_path.read_text(errors="replace").splitlines():
            stripped = line.strip()
            if stripped == '[remote "origin"]':
                in_origin = True
            elif stripped.startswith("["):
                in_origin = False
            elif in_origin and stripped.startswith("url"):
                _, _, value = stripped.partition("=")
                value = value.strip()
                if value == target or value == target_no_git or value.removesuffix(".git") == target_no_git:
                    return True
    except OSError:
        pass
    return False


def _normalize_git_output(*parts) -> str:
    output_parts = []
    for part in parts:
        if isinstance(part, bytes):
            part = part.decode(errors="replace")
        if part:
            output_parts.append(str(part))
    return "\n".join(output_parts).strip()


def _compact_git_output(output: str, limit: int = 600) -> str:
    compact = "\n".join(line.strip() for line in output.splitlines() if line.strip())
    if not compact:
        return "Git 命令未返回错误详情。"
    if len(compact) > limit:
        return compact[:limit].rstrip() + "..."
    return compact


def _format_git_error(action: str, output: str) -> str:
    detail = _compact_git_output(output)
    lower_detail = detail.lower()

    if "permission denied" in lower_detail or "authentication failed" in lower_detail:
        return f"Git 仓库无权限或 SSH key 未配置，请确认当前机器有仓库访问权限。{detail}"
    if "could not read from remote repository" in lower_detail or "correct access rights" in lower_detail:
        return f"Git 仓库无权限或地址不可访问，请确认权限、SSH key 和仓库地址。{detail}"
    if "host key verification failed" in lower_detail:
        return f"Git 主机指纹校验失败，请先在终端完成 SSH known_hosts 确认。{detail}"
    if "unable to access" in lower_detail and ("403" in lower_detail or "forbidden" in lower_detail):
        return f"Git 仓库无权限，请确认当前账号或 Token 有访问权限。{detail}"
    if "repository not found" in lower_detail or "not found" in lower_detail or "does not appear to be a git repository" in lower_detail:
        return f"Git 仓库不存在或地址错误，请检查仓库地址。{detail}"
    if "could not resolve host" in lower_detail or "name or service not known" in lower_detail or "nodename nor servname provided" in lower_detail:
        return f"无法解析 Git 主机，请检查网络、DNS 或仓库地址。{detail}"
    if (
        "connection timed out" in lower_detail
        or "operation timed out" in lower_detail
        or "failed to connect" in lower_detail
        or "network is unreachable" in lower_detail
        or "connection refused" in lower_detail
    ):
        return f"连接 Git 仓库失败或超时，请检查网络、代理、防火墙或 Git 服务状态。{detail}"
    if "remote origin already exists" in lower_detail:
        return f"Git 本地仓库状态异常，origin 已存在。{detail}"
    if "couldn't find remote ref" in lower_detail or "ambiguous argument" in lower_detail or "unknown revision" in lower_detail:
        return f"Git 默认分支或远端引用异常，请检查仓库默认分支。{detail}"
    return f"Git 仓库拉取失败（{action}）。{detail}"


def _run_git(args: list[str], timeout: int, action: str, check: bool = True) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        output = _normalize_git_output(exc.stderr, exc.stdout)
        detail = _compact_git_output(output)
        raise AppError(f"Git 仓库拉取超时（{action}，超过 {timeout} 秒），请检查网络、代理、防火墙或 Git 服务状态。{detail}")
    if check and result.returncode != 0:
        raise AppError(_format_git_error(action, _normalize_git_output(result.stderr, result.stdout)))
    return result


def clone_or_pull(git_url: str, local_path: str) -> None:
    """目录不存在则 clone，已存在则 fetch + reset（兼容 shallow clone）。"""
    url = git_url.strip()
    if os.path.isdir(os.path.join(local_path, ".git")):
        _run_git(
            ["git", "-C", local_path, "fetch", "--depth", "1", "origin"],
            timeout=120,
            action="fetch",
        )
        # 确定默认分支
        ref_result = _run_git(
            ["git", "-C", local_path, "symbolic-ref", "refs/remotes/origin/HEAD", "--short"],
            timeout=10,
            action="default-branch",
            check=False,
        )
        if ref_result.returncode == 0:
            branch = ref_result.stdout.strip().removeprefix("origin/")
        else:
            probe = _run_git(
                ["git", "-C", local_path, "rev-parse", "--verify", "refs/remotes/origin/master"],
                timeout=10,
                action="default-branch",
                check=False,
            )
            branch = "master" if probe.returncode == 0 else "main"
        _run_git(
            ["git", "-C", local_path, "reset", "--hard", f"origin/{branch}"],
            timeout=30,
            action="reset",
        )
    else:
        if os.path.exists(local_path):
            shutil.rmtree(local_path, ignore_errors=True)
        _run_git(
            ["git", "clone", "--depth", "1", url, local_path],
            timeout=180,
            action="clone",
        )
