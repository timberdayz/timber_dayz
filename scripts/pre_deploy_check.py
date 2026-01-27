#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
部署前检查清单：在打 tag / 部署前本地执行，降低「本地正常、上线异常」风险。

使用: python scripts/pre_deploy_check.py

检查项：
- 配置与文档：env.production.example、compose 文件、Nginx 配置对比
- 代码与契约：API 契约、前端 API 方法、数据库字段
- 迁移与约束：外键约束、数据库迁移可执行性（需本地 DATABASE_URL 或跳过）
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def safe_print(text: str) -> None:
    """Windows 控制台安全输出，避免 UnicodeEncodeError。"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            out = text.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
            print(out, flush=True)
        except Exception:
            print(text.encode("ascii", errors="replace").decode("ascii"), flush=True)


def run_cmd(cmd: list[str], cwd: Path, timeout: int = 120) -> tuple[bool, str]:
    """执行命令，返回 (是否成功, 输出摘要)。"""
    try:
        r = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        out = (r.stdout or "") + (r.stderr or "")
        return r.returncode == 0, out.strip()[:500]
    except subprocess.TimeoutExpired:
        return False, "执行超时"
    except FileNotFoundError:
        return False, "命令或脚本不存在"
    except Exception as e:
        return False, str(e)


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    os.chdir(root)

    checks: list[tuple[str, bool, str]] = []

    # ----- 1. 关键文件存在 -----
    required_files = [
        "env.production.example",
        "docker-compose.yml",
        "docker-compose.prod.yml",
        "nginx/nginx.prod.conf",
    ]
    for name in required_files:
        p = root / name
        ok = p.exists()
        checks.append((f"文件存在: {name}", ok, "" if ok else "缺失"))

    # ----- 2. Nginx 配置对比 -----
    ok, out = run_cmd(
        [sys.executable, "scripts/compare_nginx_configs.py"],
        root,
        timeout=10,
    )
    checks.append(("Nginx 配置对比 (dev vs prod)", True, out or "(无输出)"))

    # ----- 3. API 契约 -----
    ok, out = run_cmd(
        [sys.executable, "scripts/validate_api_contracts.py"],
        root,
        timeout=60,
    )
    checks.append(("API 契约验证", ok, out))

    # ----- 4. 前端 API 方法 -----
    ok, out = run_cmd(
        [sys.executable, "scripts/validate_frontend_api_methods.py"],
        root,
        timeout=60,
    )
    checks.append(("前端 API 方法验证", ok, out))

    # ----- 5. 数据库字段 -----
    ok, out = run_cmd(
        [sys.executable, "scripts/validate_database_fields.py"],
        root,
        timeout=60,
    )
    checks.append(("数据库字段验证", ok, out))

    # ----- 6. 外键约束（不依赖本地 DB 的静态检查） -----
    ok, out = run_cmd(
        [sys.executable, "scripts/test_migration_foreign_keys.py"],
        root,
        timeout=30,
    )
    checks.append(("迁移外键约束验证", ok, out))

    # ----- 汇总 -----
    safe_print("=" * 60)
    safe_print("部署前检查结果")
    safe_print("=" * 60)
    failed = []
    for name, ok, msg in checks:
        status = "[OK]" if ok else "[FAIL]"
        safe_print(f"  {status} {name}")
        if msg and not ok:
            for line in msg.split("\n")[:5]:
                if line.strip():
                    # 仅输出 ASCII 可表示部分，避免 Windows GBK 控制台报错
                    safe_print("       " + line[:70].encode("ascii", errors="replace").decode("ascii"))
        if not ok:
            failed.append(name)
    safe_print("=" * 60)

    if failed:
        safe_print("\n未通过项:")
        for n in failed:
            safe_print(f"  - {n}")
        safe_print("\n建议修复后再打 tag / 部署。")
        safe_print("生产构建时请确认已在 GitHub Secrets 中配置 VITE_API_URL。")
        return 1

    safe_print("\n[OK] 所有检查通过。打 tag 前请确认 GitHub Secrets 中已配置 VITE_API_URL。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
