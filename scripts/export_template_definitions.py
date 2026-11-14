#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把库里的 published 模板导出成仓库里的**决策资产定义**。

为什么需要它
------------
批次 3 要把「模板是什么」放进 Git, 但仓库里不能凭空手写一份定义 ——
那样就和库里的真实模板对不上。所以需要一个**单向导出**工具:

    库里的 published 模板  ->  templates/definitions/*.json

导出只取**决策资产**(列清单 / 核心字段清单 / 解析规则 / 维度 …),
不取运行时状态(版本号 / 命中次数 / 审计字段) —— 理由见
:mod:`scripts.template_definitions`。

用法
----
    python scripts/export_template_definitions.py            # 导出到 templates/definitions
    python scripts/export_template_definitions.py --dry-run  # 只打印将要写什么
    python scripts/export_template_definitions.py --out DIR  # 导出到别的目录

注意
----
* 只导出 ``status == 'published'`` 的模板 —— archived 的历史版本不进 Git。
* **只读**: 本脚本不写数据库。
* 导出会**覆盖**同名文件; 如果库里的模板变了, 重新导出即可得到新定义。
  (这正是「决策进 Git」的含义: 改模板 = 改文件 = 一次可 review 的提交。)
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from scripts.template_definitions import (
        DEFINITIONS_DIR,
        DECISION_FIELDS,
        RUNTIME_ONLY_FIELDS,
        TemplateDefinitionError,
        build_definition_payload,
        definition_file_name,
        dimension_key,
        dimension_key_text,
        dump_definition,
    )
except ModuleNotFoundError:  # 直接 `python scripts/...` 执行(Windows)
    from template_definitions import (  # type: ignore[no-redef]
        DEFINITIONS_DIR,
        DECISION_FIELDS,
        RUNTIME_ONLY_FIELDS,
        TemplateDefinitionError,
        build_definition_payload,
        definition_file_name,
        dimension_key,
        dimension_key_text,
        dump_definition,
    )


async def _export(out_dir: Path, dry_run: bool) -> int:
    from sqlalchemy import select

    from backend.models.database import AsyncSessionLocal
    from modules.core.db import FieldMappingTemplate

    out_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(FieldMappingTemplate).where(
                        FieldMappingTemplate.status == "published"
                    )
                )
            )
            .scalars()
            .all()
        )

        if not rows:
            print("[WARN] 库里没有 published 模板, 未导出任何文件")
            return 1

        written: List[Path] = []
        for row in sorted(
            rows,
            key=lambda item: (
                item.platform or "",
                item.data_domain or "",
                str(item.granularity or ""),
                str(item.sub_domain or ""),
            ),
        ):
            payload = build_definition_payload(row)
            file_name = definition_file_name(payload)
            path = out_dir / file_name
            content = dump_definition(payload)

            if dry_run:
                print(
                    f"[DRY-RUN] {file_name}  <- {dimension_key_text(dimension_key(payload))}"
                )
                continue

            # [*] 显式 newline="\n": Windows 上 Path.write_text 默认会把 \n
            #     翻成 \r\n ⇒ 提交进 Git 后每个文件都是 CRLF, diff 全是噪音。
            path.write_text(content, encoding="utf-8", newline="\n")
            written.append(path)
            print(f"[OK] {file_name}")

    if not dry_run:
        print(f"\n已导出 {len(written)} 份定义到 {out_dir}")
        print(f"定义字段: {list(DECISION_FIELDS)}")
        print(f"运行时状态字段(不进 Git): {list(RUNTIME_ONLY_FIELDS)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="导出 published 模板为仓库决策资产定义"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFINITIONS_DIR,
        help=f"输出目录(默认: {DEFINITIONS_DIR})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要写哪些文件, 不落盘",
    )
    args = parser.parse_args()

    from backend.utils.project_env import load_project_env

    load_project_env(REPO_ROOT)
    try:
        return asyncio.run(_export(args.out, args.dry_run))
    except TemplateDefinitionError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
