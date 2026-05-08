#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    base_args = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-m",
        "not slow and not requires_browser",
        "--ignore=tests/e2e",
        "--ignore=backend/tests/data_pipeline",
        "--ignore=backend/tests/archive",
    ]

    # 1) 快速单元测试（不触发 e2e / 浏览器 / 慢测）
    unit_args = base_args + [
        "tests/unit",
        "tests/test_tiktok_navigation.py",
    ]
    code = subprocess.call(unit_args, cwd=str(repo_root))
    if code != 0:
        return code

    # 2) 后端 contract 类测试（覆盖路由/约束/迁移契约，不跑 integration/security/e2e）
    backend_contract_args = base_args + [
        "backend/tests",
        "--ignore-glob=*frontend*",
        "--ignore-glob=*migration*",
        "--ignore=backend/tests/test_account_management_import_path_removed.py",
        "-k",
        "cache or ssot or import_path or legacy_shop_session_cleanup or dashboard_cache_singleflight_route or annual_summary_target_completion",
    ]
    return subprocess.call(backend_contract_args, cwd=str(repo_root))


if __name__ == "__main__":
    raise SystemExit(main())
