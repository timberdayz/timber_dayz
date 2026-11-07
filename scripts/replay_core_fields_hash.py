#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次 E 前置: 新旧口径 hash 离线回放报告。

要回答的问题
------------
批次 E 要把 hash 的字段来源从 ``deduplication_fields``(一串字符串)换成
**版本级清单** ``core_fields``(带 ``semantic_key`` / ``required`` / ``in_hash``)。

换成清单之后, **已入库的行会不会被当成新数据**?
—— 如果会, 就要先做回填; 如果不会, 就可以放心切换。

本脚本产出两份证据

1. **静态比对**: 每个模板版本的 hash **键集合**(旧 vs 清单口径)是否逐字一致。
   清单推导规则见 :mod:`backend.services.core_fields_service`
   (键名 = ``raw_name`` 优先, 否则 ``semantic_key`` ⇒ 与旧口径逐字等价)。
2. **实证回放**: 取**真实已入库文件**, 分别用
   **旧分支** (``deduplication_fields``) 与 **新分支** (``core_fields``)
   各算一遍 ``data_hash``, 比对行级差异。

   ⚠️ 两边必须走**不同的代码分支**才算数 ——
   早先的版本两边都传 ``deduplication_fields``, 实际都在跑旧分支,
   证不了新分支的等价性(已修正)。
3. **存量隐患**: 「重新保存模板」这条路的键集合 vs 存库口径。
   (:func:`normalize_deduplication_fields_for_template` 会把物理列名
   换成规范语义键 ⇒ 重存一次, hash 口径就变了。)

用法::

    DATABASE_URL=postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp \\
        python scripts/replay_core_fields_hash.py

    # 只跑静态比对(不碰文件)
    python scripts/replay_core_fields_hash.py --static-only
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DATABASE_URL = "postgresql+asyncpg://erp_user:erp_pass_2025@localhost:15432/xihong_erp"


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
# 静态比对
# ---------------------------------------------------------------------------


def _hash_identities_from_template_fields(
    deduplication_fields: List[str],
    *,
    data_domain: str,
    sub_domain: Optional[str],
    header_bindings: List[Dict[str, Any]],
    field_parse_rules: List[Dict[str, Any]],
) -> List[str]:
    """按**旧口径**拼出最终参与 hash 的字段(与入库路径完全一致)。"""
    from backend.services.deduplication_fields_config import (
        append_auto_date_identity_fields,
        get_deduplication_fields,
    )
    from backend.services.orders_ingestion_normalizer import (
        extend_orders_deduplication_fields,
    )

    fields = get_deduplication_fields(
        data_domain=data_domain,
        template_fields=deduplication_fields,
        sub_domain=sub_domain,
        header_bindings=header_bindings,
    )
    fields = append_auto_date_identity_fields(fields, field_parse_rules)
    if (data_domain or "").lower() == "orders":
        fields = extend_orders_deduplication_fields(data_domain, fields)
    return fields


def _hash_identities_from_core_fields(
    core_fields: List[Dict[str, Any]],
    *,
    data_domain: str,
    sub_domain: Optional[str],
    header_bindings: List[Dict[str, Any]],
    field_parse_rules: List[Dict[str, Any]],
) -> List[str]:
    """按**新口径**拼出最终参与 hash 的字段。"""
    from backend.services.core_fields_service import core_field_hash_identities

    return _hash_identities_from_template_fields(
        core_field_hash_identities(core_fields),
        data_domain=data_domain,
        sub_domain=sub_domain,
        header_bindings=header_bindings,
        field_parse_rules=field_parse_rules,
    )


def _hash_identities_after_resave(
    deduplication_fields: List[str],
    *,
    data_domain: str,
    sub_domain: Optional[str],
    header_bindings: List[Dict[str, Any]],
    field_parse_rules: List[Dict[str, Any]],
) -> List[str]:
    """按**保存口径**拼出最终参与 hash 的字段。

    这一口径是现在保存模板时走的路
    (:func:`normalize_deduplication_fields_for_template` 会把物理列名
    换成绑定里的规范语义键)。

    它与「存库口径」的差异是**存量隐患**: 同一份模板, 重新保存一次,
    hash 的字段来源就变了 ⇒ 同一批数据会被当成新数据。
    """
    from backend.services.template_save_readiness_service import (
        normalize_deduplication_fields_for_template,
    )

    normalized = normalize_deduplication_fields_for_template(
        deduplication_fields,
        header_bindings,
    )
    return _hash_identities_from_template_fields(
        normalized,
        data_domain=data_domain,
        sub_domain=sub_domain,
        header_bindings=header_bindings,
        field_parse_rules=field_parse_rules,
    )


# ---------------------------------------------------------------------------
# 实证回放
# ---------------------------------------------------------------------------


def _read_rows(file_path: Path, header_row: int, limit: int) -> List[Dict[str, Any]]:
    from backend.services.excel_parser import ExcelParser

    df = ExcelParser.read_excel(file_path, header=header_row)
    df.columns = [str(col).strip() for col in df.columns]
    df = df.dropna(how="all").fillna("")
    return df.head(limit).to_dict("records")


def _scope_values(file_row: Dict[str, Any], *, data_domain: str, granularity: str, sub_domain: Optional[str]) -> Dict[str, Any]:
    return {
        "platform_code": file_row.get("platform_code"),
        "shop_account_id": file_row.get("shop_account_id"),
        "platform_shop_id": file_row.get("platform_shop_id"),
        "shop_id": file_row.get("shop_id"),
        "data_domain": data_domain,
        "granularity": granularity,
        "sub_domain": sub_domain,
    }


async def run(args) -> int:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from backend.services.core_fields_service import derive_core_fields
    from backend.services.deduplication_service import DeduplicationService

    engine = create_async_engine(_database_url(), echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    dedup_service = DeduplicationService(db=None)

    static_rows: List[Dict[str, Any]] = []
    replay_rows: List[Dict[str, Any]] = []

    try:
        async with session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT f.platform, f.data_domain, f.granularity, f.sub_domain,
                           v.id AS version_id, v.version_no, v.status,
                           v.deduplication_fields, v.header_bindings
                    FROM core.field_mapping_template_versions v
                    JOIN core.field_mapping_template_families f
                      ON f.id = v.family_id
                    ORDER BY f.platform, f.data_domain, f.granularity, v.version_no
                    """
                )
            )
            versions = list(result.mappings().all())

            # 变体(拿 header_row / field_parse_rules)
            variant_result = await session.execute(
                text(
                    """
                    SELECT v.template_version_id, v.header_row, v.field_parse_rules
                    FROM core.field_mapping_template_variants v
                    """
                )
            )
            variants_by_version: Dict[int, List[Dict[str, Any]]] = {}
            for row in variant_result.mappings().all():
                variants_by_version.setdefault(int(row["template_version_id"]), []).append(dict(row))

            # 已入库文件(每个维度取最近一个)
            file_result = await session.execute(
                text(
                    """
                    SELECT id, platform_code, data_domain, granularity, sub_domain,
                           file_path, shop_id, shop_account_id, platform_shop_id, status
                    FROM public.catalog_files
                    WHERE status = 'ingested' AND file_path IS NOT NULL
                    ORDER BY id DESC
                    """
                )
            )
            files_by_dimension: Dict[tuple, Dict[str, Any]] = {}
            for row in file_result.mappings().all():
                key = (
                    str(row["platform_code"] or ""),
                    str(row["data_domain"] or ""),
                    str(row["granularity"] or ""),
                )
                files_by_dimension.setdefault(key, dict(row))

            # 域级契约里 required 的语义键(一次性取全, 后面按维度筛)
            contract_result = await session.execute(
                text(
                    """
                    SELECT DISTINCT data_domain, granularity, semantic_key
                    FROM core.semantic_field_contracts
                    WHERE importance = 'required'
                    """
                )
            )
            required_by_dimension: Dict[tuple, List[str]] = {}
            for row in contract_result.mappings().all():
                key = (
                    str(row["data_domain"] or ""),
                    str(row["granularity"] or ""),
                )
                required_by_dimension.setdefault(key, []).append(str(row["semantic_key"]))

        for version in versions:
            if version["status"] not in ("active", "superseded"):
                continue
            data_domain = str(version["data_domain"] or "")
            sub_domain = version["sub_domain"]
            dedup_fields = list(version["deduplication_fields"] or [])
            bindings = list(version["header_bindings"] or [])
            variants = variants_by_version.get(int(version["version_id"]), [])
            parse_rules: List[Dict[str, Any]] = []
            header_row = 0
            for variant in variants:
                if variant.get("field_parse_rules"):
                    parse_rules = list(variant["field_parse_rules"])
                    header_row = int(variant.get("header_row") or 0)
                    break
                if variant.get("header_row") is not None:
                    header_row = int(variant.get("header_row") or 0)

            required_keys = list(
                {
                    *required_by_dimension.get((data_domain, str(version["granularity"] or "")), []),
                    *required_by_dimension.get((data_domain, ""), []),
                }
            )

            core_fields = derive_core_fields(
                deduplication_fields=dedup_fields,
                header_bindings=bindings,
                data_domain=data_domain,
                sub_domain=sub_domain,
                required_semantic_keys=required_keys,
            )

            old_identities = _hash_identities_from_template_fields(
                dedup_fields,
                data_domain=data_domain,
                sub_domain=sub_domain,
                header_bindings=bindings,
                field_parse_rules=parse_rules,
            )
            new_identities = _hash_identities_from_core_fields(
                core_fields,
                data_domain=data_domain,
                sub_domain=sub_domain,
                header_bindings=bindings,
                field_parse_rules=parse_rules,
            )

            saved_identities = _hash_identities_after_resave(
                dedup_fields,
                data_domain=data_domain,
                sub_domain=sub_domain,
                header_bindings=bindings,
                field_parse_rules=parse_rules,
            )

            static_rows.append(
                {
                    "label": f"{version['platform']}/{data_domain}/{version['granularity']}",
                    "version_id": int(version["version_id"]),
                    "old": old_identities,
                    "saved": saved_identities,
                    "new": new_identities,
                    "same": old_identities == new_identities,
                    "resave_same": old_identities == saved_identities,
                    "core_fields": core_fields,
                }
            )

            if args.static_only:
                continue

            # 实证回放
            key = (
                str(version["platform"] or ""),
                data_domain,
                str(version["granularity"] or ""),
            )
            file_row = files_by_dimension.get(key)
            if not file_row:
                continue
            file_path = REPO_ROOT / str(file_row["file_path"])
            if not file_path.exists():
                continue
            try:
                rows = _read_rows(file_path, header_row, args.limit)
            except Exception as exc:  # noqa: BLE001
                replay_rows.append(
                    {
                        "label": key[0] + "/" + key[1] + "/" + key[2],
                        "status": f"读取失败: {exc}",
                    }
                )
                continue
            if not rows:
                continue

            scope = _scope_values(
                file_row,
                data_domain=data_domain,
                granularity=str(version["granularity"] or ""),
                sub_domain=sub_domain,
            )
            old_hashes = dedup_service.batch_calculate_data_hash(
                rows,
                deduplication_fields=old_identities,
                header_bindings=bindings,
                scope_values=scope,
            )
            # [*] 新口径: **同时**传字段集合(deduplication_fields)与清单(core_fields)。
            #     新分支用「清单驱动取值」, 字段集合仍复用旧口径算好的完整链
            #     (含 platform_code / shop_id / orders 扩展 / auto-date 身份字段)。
            new_hashes = dedup_service.batch_calculate_data_hash(
                rows,
                deduplication_fields=new_identities,
                header_bindings=bindings,
                scope_values=scope,
                core_fields=core_fields,
            )
            saved_hashes = dedup_service.batch_calculate_data_hash(
                rows,
                deduplication_fields=saved_identities,
                header_bindings=bindings,
                scope_values=scope,
            )
            changed = sum(1 for old, new in zip(old_hashes, new_hashes) if old != new)
            resave_changed = sum(1 for old, new in zip(old_hashes, saved_hashes) if old != new)
            replay_rows.append(
                {
                    "label": key[0] + "/" + key[1] + "/" + key[2],
                    "status": "OK",
                    "file": str(file_row["file_path"]),
                    "header_row": header_row,
                    "rows": len(rows),
                    "changed": changed,
                    "resave_changed": resave_changed,
                    "old_identities": old_identities,
                    "new_identities": new_identities,
                    "saved_identities": saved_identities,
                }
            )
    finally:
        await engine.dispose()

    # ── 输出报告 ─────────────────────────────────────────────────────────
    print("=" * 78)
    print("批次 E 前置 · 新旧口径 hash 离线回放报告")
    print("=" * 78)

    print("\n【一】静态比对: hash 身份清单(旧 vs 新)")
    print("-" * 78)
    static_mismatch = 0
    resave_mismatch = 0
    for row in static_rows:
        flag = "一致" if row["same"] else "不一致"
        if not row["same"]:
            static_mismatch += 1
        resave_flag = "一致" if row["resave_same"] else "不一致"
        if not row["resave_same"]:
            resave_mismatch += 1
        print(f"[新口径 {flag} / 重新保存后 {resave_flag}] {row['label']} (version {row['version_id']})")
        if not row["same"]:
            print(f"        存库口径: {row['old']}")
            print(f"        清单口径: {row['new']}")
        if not row["resave_same"]:
            print(f"        存库口径: {row['old']}")
            print(f"        保存口径: {row['saved']}")
    print(f"\n静态比对: {len(static_rows)} 个版本")
    print(f"  清单口径 vs 存库口径 不一致: {static_mismatch} 个")
    print(f"  保存口径 vs 存库口径 不一致: {resave_mismatch} 个  ← 存量隐患(重存一次口径就变)")

    print("\n【二】实证回放: 真实已入库文件按两套口径各算一遍 data_hash")
    print("-" * 78)
    if args.static_only:
        print("(已跳过 --static-only)")
    else:
        replay_total = 0
        replay_changed = 0
        replay_resave_changed = 0
        for row in replay_rows:
            if row.get("status") != "OK":
                print(f"[跳过] {row['label']}: {row.get('status')}")
                continue
            replay_total += row["rows"]
            replay_changed += row["changed"]
            replay_resave_changed += row["resave_changed"]
            flag = "一致" if row["changed"] == 0 else f"**变化 {row['changed']} 行**"
            resave_flag = (
                "一致" if row["resave_changed"] == 0 else f"**变化 {row['resave_changed']} 行**"
            )
            print(f"[清单口径 {flag} / 保存口径 {resave_flag}] {row['label']}  文件={row['file']}")
            print(
                f"        header_row={row['header_row']} 行数={row['rows']} "
                f"hash 变化(清单)={row['changed']} hash 变化(重存)={row['resave_changed']}"
            )
        print(f"\n实证回放: 共 {replay_total} 行")
        print(f"  切到清单口径后 hash 变化: {replay_changed} 行")
        print(f"  重新保存模板后 hash 变化: {replay_resave_changed} 行  ← 存量隐患")

    print("\n【结论】")
    print("-" * 78)
    if static_mismatch == 0 and (args.static_only or replay_changed == 0):
        print("切换到 core_fields **不会**改任何一行的 data_hash ⇒ 无需回填, 可以直接切换。")
        print("(仍建议保留显式开关, 便于出问题时一键回退。)")
    else:
        print("存在差异 ⇒ 切换前必须先出回填方案, 不要静默双写。")
        print("差异明细见上面的「不一致 / 变化」条目。")
    if resave_mismatch:
        print()
        print("⚠️ 另外发现存量隐患: 「重新保存模板」这条路会改 hash 口径")
        print("   (保存时会把物理列名换成规范语义键)。这不是本批次引入的,")
        print("   但会造成「同一份数据被当成新数据」⇒ 需要一并处理。")
    return 0


async def _required_semantic_keys(data_domain: str, granularity: str) -> List[str]:
    """域级契约里 ``importance='required'`` 的语义键(单维度查询, 供外部调用)。"""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(_database_url(), echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(
                text(
                    """
                    SELECT DISTINCT semantic_key
                    FROM core.semantic_field_contracts
                    WHERE data_domain = :data_domain
                      AND (granularity = :granularity OR granularity IS NULL)
                      AND importance = 'required'
                    """
                ),
                {"data_domain": data_domain, "granularity": granularity},
            )
            return [str(row[0]) for row in result.all()]
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="批次 E 前置 · hash 离线回放")
    parser.add_argument("--static-only", action="store_true", help="只做静态比对, 不读文件")
    parser.add_argument(
        "--limit",
        type=int,
        default=40,
        help=(
            "每个文件最多回放多少行。"
            "默认 40 —— 等价性是**逐行确定性**的(护栏测试已用合成数据证明),"
            "实证只需覆盖真实文件的头部行, 不必全量扫描。"
        ),
    )
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
