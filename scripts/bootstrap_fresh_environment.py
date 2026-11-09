#!/usr/bin/env python3
"""全新环境的**两段式引导**入口 —— 让「空库从零建库」成为可执行流程。

为什么需要它
------------
``current_schema_20261116_add_tiktok_export_store_name_aliases`` 是数据修复型迁移，
它要求 6 个 TikTok 出口账号**已经存在**（fail-closed 前置检查）。空库上这些账号不存在
⇒ 整条链在该步中止。

实测（临时 Postgres，无种子）::

    [阶段1] alembic upgrade current_schema_20261115_add_sku_platform_pricing -> 退出码 0
    [阶段2] run_current_schema_migrations.py                                 -> 退出码 1
            RuntimeError: TikTok 别名补录的前置检查未通过，拒绝继续：
            账号不存在: tiktok_sg_daone_mall_local（别名 DAONE Mall）；…… （共 6 条）

所以「从零建库」必须分成两段：

1. 先把链升到 **20261116 的前一个节点**（账号表此时已由更早的迁移建好）；
2. 注入引导账号（主账号 + 6 个店铺账号）；
3. 再把链升到 head。

本脚本是这段流程的**唯一实现**，三种调用方共用：

* 真实新环境：``python scripts/bootstrap_fresh_environment.py --manifest bootstrap.json``
* 临时库门禁：``scripts/validate_migrations_fresh_db.py``（占位值 profile）
* 本地重建：``scripts/rebuild_local_current_schema.py``（占位值 profile）

⚠ **绝不静默伪造业务数据**：真实环境必须提供运维清单（真实凭据 + 真实显示名）；
占位值 profile 只能在一次性临时库上用，脚本会明确告警。

用法::

    python scripts/bootstrap_fresh_environment.py --print-template > bootstrap.json
    python scripts/bootstrap_fresh_environment.py --manifest bootstrap.json
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from scripts.bootstrap_seed_manifest import (
        PRECHECK_TARGET_REVISION,
        BootstrapManifestError,
        apply_bootstrap_accounts,
        build_gate_rows,
        build_operator_rows,
        load_operator_manifest,
        required_manifest_template,
        verify_bootstrap_accounts,
    )
except ModuleNotFoundError:  # Direct `python scripts/...` execution on Windows.
    from bootstrap_seed_manifest import (  # type: ignore[no-redef]
        PRECHECK_TARGET_REVISION,
        BootstrapManifestError,
        apply_bootstrap_accounts,
        build_gate_rows,
        build_operator_rows,
        load_operator_manifest,
        required_manifest_template,
        verify_bootstrap_accounts,
    )


#: 子进程输出的尾部长度（部署日志要能看出真实原因，不是只留一句 failed (1)）。
OUTPUT_TAIL_LIMIT = 4000


class BootstrapError(RuntimeError):
    """两段式引导失败 —— 必须说清楚是哪一段、为什么。"""


def _tail(text: str, limit: int = OUTPUT_TAIL_LIMIT) -> str:
    text = (text or "").strip()
    return text[-limit:] if len(text) > limit else text


def _run(
    command: List[str],
    *,
    database_url: str,
    project_root: Path,
    runner: Callable[..., Any] = subprocess.run,
    timeout: int = 3600,
) -> None:
    """跑一条命令；失败时把子进程输出尾部带进异常。"""
    result = runner(
        command,
        cwd=str(project_root),
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = _tail(result.stderr or "") or _tail(result.stdout or "")
        raise BootstrapError(
            "命令失败 ({code}): {cmd}".format(
                code=result.returncode, cmd=" ".join(command)
            )
            + (":\n{detail}".format(detail=detail) if detail else "")
        )


def run_two_phase_bootstrap(
    database_url: str,
    *,
    main_row: Dict[str, Any],
    shop_rows: Sequence[Dict[str, Any]],
    project_root: Path = ROOT,
    log: Callable[[str], None] = print,
    runner: Callable[..., Any] = subprocess.run,
) -> Dict[str, Any]:
    """两段式引导：升到 20261116 的前一个节点 → 注入账号 → 升到 head。

    返回汇总信息（``inserted`` 是实际新增的账号行数）。
    任何一步失败都抛 :class:`BootstrapError`，并且**不会**把半截状态当成成功。
    """
    log("[INFO] 第一段迁移：升到 {rev}".format(rev=PRECHECK_TARGET_REVISION))
    _run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic-current.ini",
            "upgrade",
            PRECHECK_TARGET_REVISION,
        ],
        database_url=database_url,
        project_root=project_root,
        runner=runner,
    )
    log("[OK] 第一段迁移完成")

    log("[INFO] 注入引导账号（主账号 + {n} 个店铺账号）".format(n=len(shop_rows)))
    try:
        inserted = apply_bootstrap_accounts(database_url, main_row, list(shop_rows))
    except Exception as exc:  # noqa: BLE001 —— 失败必须说清楚是哪一步
        raise BootstrapError("注入引导账号失败: {exc}".format(exc=exc)) from exc
    problems = verify_bootstrap_accounts(database_url)
    if problems:
        raise BootstrapError("引导账号校验未通过：" + "；".join(problems))
    log("[OK] 引导账号就位（本次新增 {n} 行）".format(n=inserted))

    log("[INFO] 第二段迁移：升到 head")
    _run(
        [
            sys.executable,
            str(project_root / "scripts" / "run_current_schema_migrations.py"),
        ],
        database_url=database_url,
        project_root=project_root,
        runner=runner,
    )
    log("[OK] 第二段迁移完成")

    return {
        "inserted": inserted,
        "precheck_revision": PRECHECK_TARGET_REVISION,
        "shop_accounts": len(shop_rows),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="全新环境的两段式引导（空库 → head）")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL"))
    parser.add_argument(
        "--manifest",
        help="运维提供的引导清单（JSON）；真实环境必填",
    )
    parser.add_argument(
        "--allow-gate-profile",
        action="store_true",
        help="使用占位值（仅限一次性临时库；真实环境禁止）",
    )
    parser.add_argument(
        "--print-template",
        action="store_true",
        help="打印引导清单模板并退出",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.print_template:
        import json

        print(json.dumps(required_manifest_template(), ensure_ascii=False, indent=2))
        return 0

    if not args.database_url:
        print("[FAIL] 缺少 DATABASE_URL（--database-url 或环境变量）")
        return 2

    if args.manifest:
        try:
            manifest = load_operator_manifest(args.manifest)
            main_row, shop_rows = build_operator_rows(manifest)
        except BootstrapManifestError as exc:
            print("[FAIL] {exc}".format(exc=exc))
            return 2
        print("[INFO] 使用运维清单: {path}".format(path=args.manifest))
    elif args.allow_gate_profile:
        main_row, shop_rows = build_gate_rows()
        print(
            "[WARN] 使用**占位值**引导（--allow-gate-profile）—— "
            "仅限一次性临时库；真实环境必须提供 --manifest"
        )
    else:
        print(
            "[FAIL] 真实环境必须提供 --manifest <清单.json>；"
            "一次性临时库才允许 --allow-gate-profile\n"
            "清单模板：python scripts/bootstrap_fresh_environment.py --print-template"
        )
        return 2

    try:
        summary = run_two_phase_bootstrap(
            args.database_url,
            main_row=main_row,
            shop_rows=shop_rows,
        )
    except BootstrapError as exc:
        print("[FAIL] 两段式引导失败")
        print(str(exc))
        return 1
    print("[OK] 引导完成: {summary}".format(summary=summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
