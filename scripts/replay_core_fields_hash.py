#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次 E 前置 · 新旧口径 hash **按实跑路径** 的离线回放报告。

要回答的问题
------------
翻 ``SYNC_CORE_FIELDS_HASH_ENABLED`` 开关前, 必须回答:
**已入库的行会不会被当成新数据?**
—— 会, 就得先回填; 不会, 才可以切。

为什么必须「按实跑路径」
----------------------
早先版本的回放脚本**自己拼** hash 的字段集合, 与真实入库路径有三处对不上:

1. 没传 ``identity_values``(auto-date 身份字段 + orders 身份值);
2. ``core_fields`` 用推导值 ``derive_core_fields(...)``,
   而入库用的是**版本表里存的清单**; ``field_parse_rules`` 也取错了表
   (variants 表 ⇒ 版本表);
3. 漏了 orders 域的 ``prepare_orders_rows_for_b_class`` 行改写。

于是「回放结论」不代表「切开关后的真实结果」。

现在回放与入库**共用同一个函数**
:func:`backend.services.data_ingestion_service.compute_ingestion_data_hashes`
—— 口径字段集合 / identity_values / orders 行改写 / 批次E 开关判定全在里面,
结论与实跑同源。

产出
----
1. **逐版本结论**: 同一批真实已入库文件, 分别在「开关关」与「开关开」两种状态下
   走实跑路径算一遍 ``data_hash``, 比对行级差异;
2. **回填方案**: 若存在差异, 给出需要回填的行数、涉及哪些表, 以及回填的 SQL 骨架
   (只出方案, **不执行**)。

开关
----
本脚本**不会**修改任何环境变量的持久配置, 只在进程内临时切换
(``SYNC_CORE_FIELDS_HASH_ENABLED``) 以对比两种口径; 脚本跑完不会打开生产开关。

用法::

    DATABASE_URL=postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp \\
        python scripts/replay_core_fields_hash.py

    # 只跑静态比对(不读文件, 不连库算 hash)
    python scripts/replay_core_fields_hash.py --static-only

    # 限制每个文件最多回放多少行(默认 200)
    python scripts/replay_core_fields_hash.py --limit 200
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://erp_user:erp_pass_2025@localhost:15432/xihong_erp"
)
HASH_ENV_KEY = "SYNC_CORE_FIELDS_HASH_ENABLED"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL") or ""
    if not url:
        return DEFAULT_DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


# ---------------------------------------------------------------------------
# 实跑路径的复刻: 读文件 → 规范化 → 交给 compute_ingestion_data_hashes
# ---------------------------------------------------------------------------


def _read_rows(
    file_path: Path, header_row: int, limit: int, data_domain: str
) -> List[Dict[str, Any]]:
    """按入库路径的方式读文件并规范化(列名必须与入库一致, 否则 hash 不可比)。"""
    from backend.services.excel_parser import ExcelParser

    df = ExcelParser.read_excel(file_path, header=header_row)
    if df is None or getattr(df, "empty", True):
        return []
    df.columns = [str(col).strip() for col in df.columns]
    df = df.dropna(how="all").fillna("")
    try:
        df, _report = ExcelParser.normalize_table(
            df,
            data_domain=data_domain or "products",
            file_size_mb=0,
            source_path=str(file_path),
            header_row=header_row,
        )
    except Exception:
        # 规范化失败时退回原始列名(并在报告里体现), 不静默吞掉
        pass
    return df.head(limit).to_dict("records")


def _scope_values(
    file_row: Dict[str, Any],
    *,
    data_domain: str,
    granularity: str,
    sub_domain: Optional[str],
) -> Dict[str, Any]:
    return {
        "platform_code": file_row.get("platform_code"),
        "shop_account_id": file_row.get("shop_account_id"),
        "platform_shop_id": file_row.get("platform_shop_id"),
        "shop_id": file_row.get("shop_id"),
        "data_domain": data_domain,
        "granularity": granularity,
        "sub_domain": sub_domain,
    }


def _compute_hashes_with_flag(
    *,
    rows: List[Dict[str, Any]],
    version: Dict[str, Any],
    file_row: Dict[str, Any],
    header_row: int,
    raw_importer: Any,
    dedup_service: Any,
    hash_enabled: bool,
) -> Tuple[List[str], List[str]]:
    """在指定开关状态下, 走实跑路径算一遍 hash。返回 (旧口径 hash, 新口径 hash)。"""
    from backend.services.data_ingestion_service import compute_ingestion_data_hashes

    data_domain = str(version["data_domain"] or "")
    sub_domain = version["sub_domain"]
    bindings = list(version["header_bindings"] or [])
    parse_rules = list(version["field_parse_rules"] or [])
    dedup_fields = list(version["deduplication_fields"] or [])
    core_fields = list(version["core_fields"] or []) or None

    scope = _scope_values(
        file_row,
        data_domain=data_domain,
        granularity=str(version["granularity"] or ""),
        sub_domain=sub_domain,
    )

    # 实跑路径给 raw_importer 挂的上下文, 回放必须一模一样
    setattr(raw_importer, "header_bindings", bindings)
    raw_importer.field_parse_rules = parse_rules
    setattr(raw_importer, "file_date_from", file_row.get("date_from"))
    setattr(raw_importer, "file_date_to", file_row.get("date_to"))

    previous = os.environ.get(HASH_ENV_KEY)
    try:
        if hash_enabled:
            os.environ[HASH_ENV_KEY] = "1"
        else:
            os.environ.pop(HASH_ENV_KEY, None)

        off = compute_ingestion_data_hashes(
            rows=[dict(row) for row in rows],
            deduplication_fields=dedup_fields,
            header_bindings=bindings,
            field_parse_rules=parse_rules,
            core_fields=core_fields,
            domain=data_domain,
            sub_domain=sub_domain,
            scope_values=scope,
            raw_importer=raw_importer,
            dedup_service=dedup_service,
        )
        on = compute_ingestion_data_hashes(
            rows=[dict(row) for row in rows],
            deduplication_fields=dedup_fields,
            header_bindings=bindings,
            field_parse_rules=parse_rules,
            core_fields=core_fields,
            domain=data_domain,
            sub_domain=sub_domain,
            scope_values=scope,
            raw_importer=raw_importer,
            dedup_service=dedup_service,
        )
    finally:
        if previous is None:
            os.environ.pop(HASH_ENV_KEY, None)
        else:
            os.environ[HASH_ENV_KEY] = previous

    return list(off.data_hashes), list(on.data_hashes)


async def run(args) -> int:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from backend.services.deduplication_service import DeduplicationService
    from backend.services.raw_data_importer import get_raw_data_importer

    engine = create_async_engine(_database_url(), echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    replay_rows: List[Dict[str, Any]] = []
    static_rows: List[Dict[str, Any]] = []

    try:
        async with session_factory() as session:
            version_result = await session.execute(
                text(
                    """
                    SELECT f.platform, f.data_domain, f.granularity, f.sub_domain,
                           v.id AS version_id, v.version_no, v.status,
                           v.deduplication_fields, v.header_bindings,
                           v.core_fields, v.field_parse_rules
                    FROM core.field_mapping_template_versions v
                    JOIN core.field_mapping_template_families f
                      ON f.id = v.family_id
                    WHERE v.status IN ('active', 'superseded')
                    ORDER BY f.platform, f.data_domain, f.granularity, v.version_no
                    """
                )
            )
            versions = [dict(row) for row in version_result.mappings().all()]

            variant_result = await session.execute(
                text(
                    """
                    SELECT v.template_version_id, v.header_row
                    FROM core.field_mapping_template_variants v
                    """
                )
            )
            header_row_by_version: Dict[int, int] = {}
            for row in variant_result.mappings().all():
                version_id = int(row["template_version_id"])
                if (
                    row.get("header_row") is not None
                    and version_id not in header_row_by_version
                ):
                    header_row_by_version[version_id] = int(row["header_row"])

            file_result = await session.execute(
                text(
                    """
                    SELECT id, platform_code, data_domain, granularity, sub_domain,
                           file_path, shop_id, shop_account_id, platform_shop_id,
                           status, date_from, date_to
                    FROM public.catalog_files
                    WHERE status = 'ingested' AND file_path IS NOT NULL
                    ORDER BY id DESC
                    """
                )
            )
            files_by_dimension: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
            for row in file_result.mappings().all():
                key = (
                    str(row["platform_code"] or ""),
                    str(row["data_domain"] or ""),
                    str(row["granularity"] or ""),
                )
                files_by_dimension.setdefault(key, dict(row))

            if args.static_only:
                for version in versions:
                    static_rows.append(
                        {
                            "label": (
                                f"{version['platform']}/{version['data_domain']}"
                                f"/{version['granularity']}"
                            ),
                            "version_id": int(version["version_id"]),
                            "dedup_fields": list(version["deduplication_fields"] or []),
                            "core_fields": list(version["core_fields"] or []),
                            "parse_rules": len(version["field_parse_rules"] or []),
                            "bindings": len(version["header_bindings"] or []),
                        }
                    )
                return _print_static(static_rows)

            dedup_service = DeduplicationService(db=None)
            raw_importer = get_raw_data_importer(session)

            for version in versions:
                key = (
                    str(version["platform"] or ""),
                    str(version["data_domain"] or ""),
                    str(version["granularity"] or ""),
                )
                file_row = files_by_dimension.get(key)
                label = f"{key[0]}/{key[1]}/{key[2]}"
                static_rows.append(
                    {
                        "label": label,
                        "version_id": int(version["version_id"]),
                        "dedup_fields": list(version["deduplication_fields"] or []),
                        "core_fields": list(version["core_fields"] or []),
                        "parse_rules": len(version["field_parse_rules"] or []),
                        "bindings": len(version["header_bindings"] or []),
                    }
                )
                if not file_row:
                    replay_rows.append(
                        {"label": label, "status": "没有已入库文件可回放"}
                    )
                    continue

                file_path = REPO_ROOT / str(file_row["file_path"])
                if not file_path.exists():
                    replay_rows.append(
                        {
                            "label": label,
                            "status": f"文件不存在: {file_row['file_path']}",
                        }
                    )
                    continue

                header_row = header_row_by_version.get(int(version["version_id"]), 0)
                try:
                    rows = _read_rows(
                        file_path,
                        header_row,
                        args.limit,
                        str(version["data_domain"] or ""),
                    )
                except Exception as exc:  # noqa: BLE001
                    replay_rows.append({"label": label, "status": f"读取失败: {exc}"})
                    continue
                if not rows:
                    replay_rows.append({"label": label, "status": "文件没有数据行"})
                    continue

                try:
                    off_hashes, on_hashes = _compute_hashes_with_flag(
                        rows=rows,
                        version=version,
                        file_row=file_row,
                        header_row=header_row,
                        raw_importer=raw_importer,
                        dedup_service=dedup_service,
                        hash_enabled=False,
                    )
                    off_hashes2, on_hashes2 = _compute_hashes_with_flag(
                        rows=rows,
                        version=version,
                        file_row=file_row,
                        header_row=header_row,
                        raw_importer=raw_importer,
                        dedup_service=dedup_service,
                        hash_enabled=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    replay_rows.append({"label": label, "status": f"计算失败: {exc}"})
                    continue

                changed = sum(
                    1 for old, new in zip(off_hashes, on_hashes) if old != new
                )
                # 自检: 同一开关状态下两次计算必须一致(否则说明有隐藏状态)
                self_consistent = off_hashes == off_hashes2 and on_hashes == on_hashes2
                replay_rows.append(
                    {
                        "label": label,
                        "status": "OK",
                        "file": str(file_row["file_path"]),
                        "header_row": header_row,
                        "rows": len(rows),
                        "changed": changed,
                        "self_consistent": self_consistent,
                        "sample_old": off_hashes[0] if off_hashes else "",
                        "sample_new": on_hashes[0] if on_hashes else "",
                    }
                )
    finally:
        await engine.dispose()

    return _print_report(static_rows, replay_rows)


def _print_static(static_rows: List[Dict[str, Any]]) -> int:
    print("=" * 78)
    print("批次 E 前置 · hash 口径静态盘点(未做实跑回放)")
    print("=" * 78)
    for row in static_rows:
        print(f"[{row['label']}] version={row['version_id']}")
        print(f"        dedup_fields={row['dedup_fields']}")
        print(f"        core_fields={row['core_fields']}")
        print(f"        绑定数={row['bindings']} 解析规则数={row['parse_rules']}")
    print(f"\n共 {len(static_rows)} 个模板版本。")
    return 0


def _print_report(
    static_rows: List[Dict[str, Any]], replay_rows: List[Dict[str, Any]]
) -> int:
    print("=" * 78)
    print("批次 E 前置 · 新旧口径 hash **实跑路径** 回放报告")
    print("=" * 78)

    print("\n【一】模板版本盘点")
    print("-" * 78)
    for row in static_rows:
        print(f"[{row['label']}] version={row['version_id']}")
        print(f"        dedup_fields={row['dedup_fields']}")
        print(f"        core_fields={row['core_fields']}")
        print(f"        绑定数={row['bindings']} 解析规则数={row['parse_rules']}")

    print("\n【二】实跑回放(开关关 vs 开关开, 同一函数同一条链)")
    print("-" * 78)
    total_rows = 0
    total_changed = 0
    inconsistent = 0
    for row in replay_rows:
        if row.get("status") != "OK":
            print(f"[跳过] {row['label']}: {row.get('status')}")
            continue
        total_rows += row["rows"]
        total_changed += row["changed"]
        if not row.get("self_consistent", True):
            inconsistent += 1
        flag = "一致" if row["changed"] == 0 else f"**变化 {row['changed']} 行**"
        print(f"[口径切换 {flag}] {row['label']}")
        print(
            f"        文件={row['file']} header_row={row['header_row']} "
            f"行数={row['rows']} hash 变化={row['changed']}"
        )
        if row["changed"]:
            print(f"        旧口径样本 hash={row['sample_old']}")
            print(f"        新口径样本 hash={row['sample_new']}")

    print(f"\n实跑回放合计: {total_rows} 行, 口径切换后 hash 变化 {total_changed} 行")
    if inconsistent:
        print(f"⚠️ 有 {inconsistent} 个维度两次计算结果不一致 ⇒ 结果不稳定, 结论不可用")

    print("\n【三】结论与回填方案")
    print("-" * 78)
    if total_changed == 0 and not inconsistent:
        print(
            "切换到 core_fields **不会**改任何一行的 data_hash ⇒ 无需回填, 可以切换。"
        )
        print("(仍建议保留显式开关, 出问题一键回退; 开关默认关闭。)")
        print("\n回填方案: 不需要。")
    else:
        print("存在差异 ⇒ 切换前必须先回填, 不要静默双写。")
        print("\n回填方案(只出方案, 不执行):")
        print("  1. 找出受影响的事实表与主键:")
        print("     SELECT 'fact_raw_data_<domain>_<granularity>' AS fact_table,")
        print("            id, data_hash, updated_at")
        print("       FROM public.fact_raw_data_<domain>_<granularity>")
        print("      WHERE <该版本对应的文件入库时间窗>;")
        print("  2. 按新口径重算这些行的 data_hash(用与回放脚本同一个函数),")
        print("     生成 (id, new_data_hash) 清单;")
        print("  3. 校验: 新旧清单逐行比对, 只允许 hash 不同的行进入回填清单;")
        print("  4. 回填: UPDATE ... SET data_hash = :new_hash WHERE id = :id;")
        print("     (分批 + 事务, 回填前先备份受影响行的 id/data_hash 到临时表)")
        print("  5. 回填后重跑本脚本, 确认 '口径切换 hash 变化' 归零。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="新旧口径 hash 实跑路径回放")
    parser.add_argument("--static-only", action="store_true", help="只做静态盘点")
    parser.add_argument("--limit", type=int, default=200, help="每个文件最多回放多少行")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
