#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    # Keep typecheck actionable:
    # - ensure mypy is installed and configured
    # - run on a small "runtime surface" subset
    #
    # ⚠️ 每个目标都必须是**真实存在**的文件 ——
    #    曾经这里写着 `backend/routers/dashboard_api.py`，那个文件早已不存在，
    #    于是 mypy 直接报错、这道门禁**从来没有真正跑过**，
    #    漏导入一个名字（NameError）能一路混进主干而全量测试照样全绿。
    #    ⇒ 下面的目标列表由 `test_typecheck_gate_targets_exist` 守着。
    targets = [
        "backend/routers/dashboard_api_postgresql.py",
        "modules/core/db/schema.py",
        "modules/utils/email_otp_service.py",
        # 商品中心（款 / 货 / 归属）—— 本轮改动最重的运行时面。
        "backend/domains/business/routers/product_center.py",
        "backend/services/product_spu_lifecycle.py",
        "backend/services/product_spu_binding.py",
        "backend/schemas/product_center.py",
        "modules/core/db/schema_parts/dimensions.py",
    ]

    missing = [
        target
        for target in targets
        if not (repo_root / target).exists()
    ]
    if missing:
        print(
            "typecheck 目标不存在（门禁会静默失效）: %s" % ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    args = [
        sys.executable,
        "-m",
        "mypy",
        "--config-file",
        "pyproject.toml",
        "--explicit-package-bases",
        "--follow-imports=skip",
        *targets,
    ]
    return subprocess.call(args, cwd=str(repo_root))


if __name__ == "__main__":
    raise SystemExit(main())
