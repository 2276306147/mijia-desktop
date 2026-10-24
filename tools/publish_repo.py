#!/usr/bin/env python3
"""把当前目录发布为一个 GitHub 仓库（通过 REST API，无需 git push）。

用法：
    python tools/publish_repo.py --owner 2276306147 --repo mijia-desktop
    python tools/publish_repo.py --dry-run

依赖：本机已 `gh auth login`（脚本用 `gh auth token` 取令牌），无需 git 凭证。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "dist", "dist-nuitka", ".ruff_cache", ".tmp"}
SKIP_NAMES = {".DS_Store", "Thumbs.db", "build.log"}


def token() -> str:
    env = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if env:
        return env.strip()
    try:
        return subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f"无法获取 GitHub 令牌：{exc}\n请先执行 gh auth login")


def api(method: str, path: str, payload: dict | None = None, token_value: str = "") -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        data=body,
        method=method,
        headers={
            "Authorization": f"Bearer {token_value}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mijia-desktop-publisher",
        },
    )
    last: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            if exc.code in (403, 429) and attempt < 2:
                time.sleep(3)
                last = RuntimeError(f"{exc.code}: {detail}")
                continue
            raise RuntimeError(f"{method} {path} -> {exc.code}\n{detail}") from exc
        except urllib.error.URLError as exc:
            last = exc
            time.sleep(2)
    raise RuntimeError(f"{method} {path} 失败：{last}")


def collect(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_dir() or any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path.name in SKIP_NAMES:
            continue
        if path.stat().st_size == 4 and not path.suffix:
            continue  # 沙箱残留的空壳文件
        files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--owner", default="2276306147")
    parser.add_argument("--repo", default="mijia-desktop")
    parser.add_argument("--description", default="米家控制台 —— 基于 mijiaAPI 的 Windows 桌面客户端")
    parser.add_argument("--message", default="feat: 米家控制台 v1.0.0（Windows 桌面客户端）")
    parser.add_argument("--root", default=".")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    files = collect(root)
    total = sum(p.stat().st_size for p in files)
    print(f"待发布 {len(files)} 个文件，共 {total / 1024:.0f} KB")

    if args.dry_run:
        for path in files:
            print("  ", path.relative_to(root))
        return 0

    token_value = token()
    me = api("GET", "/user", token_value=token_value)
    owner = args.owner or me["login"]
    print(f"已认证为 {me['login']}，目标仓库 {owner}/{args.repo}")

    try:
        api(
            "POST",
            "/user/repos",
            {
                "name": args.repo,
                "description": args.description,
                "private": False,
                "auto_init": False,
                "has_issues": True,
            },
            token_value,
        )
        print("仓库已创建")
    except RuntimeError as exc:
        if "422" in str(exc):
            print("仓库已存在，继续发布")
        else:
            raise

    def upload(path: Path) -> dict:
        data = base64.b64encode(path.read_bytes()).decode()
        result = api(
            "POST",
            f"/repos/{owner}/{args.repo}/git/blobs",
            {"content": data, "encoding": "base64"},
            token_value,
        )
        return {"path": path.relative_to(root).as_posix(), "mode": "100644", "type": "blob", "sha": result["sha"]}

    with ThreadPoolExecutor(max_workers=8) as pool:
        tree = list(pool.map(upload, files))
    print(f"已上传 {len(tree)} 个 blob")

    tree_result = api("POST", f"/repos/{owner}/{args.repo}/git/trees", {"tree": tree}, token_value)
    commit = api(
        "POST",
        f"/repos/{owner}/{args.repo}/git/commits",
        {"message": args.message, "tree": tree_result["sha"]},
        token_value,
    )

    try:
        api(
            "POST",
            f"/repos/{owner}/{args.repo}/git/refs",
            {"ref": "refs/heads/main", "sha": commit["sha"]},
            token_value,
        )
    except RuntimeError:
        api(
            "PATCH",
            f"/repos/{owner}/{args.repo}/git/refs/heads/main",
            {"sha": commit["sha"], "force": True},
            token_value,
        )

    print(f"已推送 commit {commit['sha'][:8]}")
    print(f"仓库：https://github.com/{owner}/{args.repo}")
    print(f"Actions：https://github.com/{owner}/{args.repo}/actions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
