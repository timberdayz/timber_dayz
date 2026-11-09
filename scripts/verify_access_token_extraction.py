#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""门禁：访问令牌(access_token)提取必须只有一个真相点。

背景（SSOT）
------------
登录优化把 access_token 搬进了 httpOnly cookie，前端不再持有令牌。
但令牌提取逻辑当时散落成 5 份副本：

- ``backend/dependencies/auth.py``
- ``backend/domains/platform/routers/users_me.py``
- ``backend/domains/platform/routers/auth.py``
- ``backend/domains/platform/routers/notification_websocket.py``
- ``backend/domains/collection/routers/collection_websocket.py``

每份副本的来源优先级还不一样（HTTP 三份 cookie→header，
WebSocket 两份 query→cookie），于是同一套登录态在不同通道表现不一致：
采集任务实时通道因为只认 query 参数而必然被拒（close "Token required"）。

本门禁把「令牌提取只有一个真相点」变成机器可判定的规则：
除 SSOT 模块外，任何文件都不得直接读取 cookie/header 取令牌，
必须调用 ``backend.dependencies.auth.extract_access_token``。

用法
----
    python scripts/verify_access_token_extraction.py
    python scripts/verify_access_token_extraction.py --root .
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 唯一真相点：只有这里的实现允许直接读 cookie / header
SSOT_MODULE = "backend/dependencies/auth.py"

# 允许的读取模式（正则）。命中即视为「自行提取令牌」。
TOKEN_READ_PATTERNS = [
    (re.compile(r"""cookies\.get\(\s*["']access_token["']"""), "cookie access_token"),
    (re.compile(r"""cookies\[\s*["']access_token["']"""), "cookie access_token"),
    (re.compile(r"""headers\.get\(\s*["']Authorization["']"""), "Authorization header"),
    (re.compile(r"""headers\[\s*["']Authorization["']"""), "Authorization header"),
]

SKIP_DIR_NAMES = {
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
}
TEST_DIR_NAMES = {"tests", "test"}


def _iter_files(root: Path, targets: list[str]) -> list[Path]:
    out: list[Path] = []
    for target in targets:
        base = (root / target).resolve()
        if base.is_file():
            out.append(base)
            continue
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if any(part in SKIP_DIR_NAMES for part in p.parts):
                continue
            out.append(p)
    return sorted(set(out))


def scan(root: Path, targets: list[str]) -> list[str]:
    violations: list[str] = []
    for path in _iter_files(root, targets):
        rel = path.relative_to(root).as_posix()
        if rel == SSOT_MODULE:
            continue
        if any(part in TEST_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except Exception:  # noqa: BLE001
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            # 注释与文档字符串不算实现
            if stripped.startswith("#"):
                continue
            for pattern, label in TOKEN_READ_PATTERNS:
                if pattern.search(line):
                    violations.append(
                        f"{rel}:{lineno} 自行读取令牌({label})，"
                        f"应改用 {SSOT_MODULE}::extract_access_token"
                    )
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="访问令牌提取单点门禁")
    parser.add_argument("--root", default=".", help="仓库根目录")
    parser.add_argument("--target", action="append", default=None, help="扫描目标")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    targets = args.target or ["backend"]
    violations = scan(root, targets)

    if violations:
        print(f"[token-gate] 发现 {len(violations)} 处自行提取令牌的实现：")
        for v in violations:
            print(f"  - {v}")
        return 1
    print(f"[token-gate] OK：令牌提取只在 {SSOT_MODULE} 一处")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
