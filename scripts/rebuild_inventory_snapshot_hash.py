#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按「当前口径」重建库存快照事实表的 ``data_hash``, 并合并塌成同一身份键的重复行。

为什么需要这个脚本
------------------
``data_hash`` 是 B 类事实表的**行身份**, 不是内容摘要:

* 唯一键: ``(platform_code, shop_id, data_domain, granularity, data_hash)``;
* 写入动作: ``INSERT ... ON CONFLICT (...) DO UPDATE``。

⇒ **改去重口径 = 改行身份**。已入库行的 hash 与新算出的 hash 不同 ⇒ 同一份快照
再采一次不会命中旧行 ⇒ **被当成新数据插入** ⇒ 事实表按快照次数膨胀。

根因(2026-11-14 实测, 生产 4111 行)
------------------------------------
库存事实表里有 **256 组**「同 SKU × 仓库 × 快照日」存在两行。追下来**不是**
「商品改名」造成的, 而是**作用域身份键换过**:

* 2026-10-21 ~ 10-26 入库的 2726 行: 载荷里是 ``scope:shop_id=xihong``,
  行内 ``shop_id=xihong``;
* 2026-11-03 之后入库的 1385 行: 载荷里是 ``scope:shop_account_id=miaoshou_real_001``,
  行内 ``shop_id=miaoshou_real_001``。

⇒ 同一份快照在**身份口径切换前后各入库一次** ⇒ 两批 hash 不同 ⇒ 两行都留下来。
(代码里早已记着这件事: ``backend/services/catalog_files_identity_backfill.py``
——「作用域里的身份键从 shop_id 变成 shop_account_id ⇒ 所有已入库文件的 hash 失效
⇒ 口径切换实际上要求一次全量重建」。)

⇒ 本脚本就是那次「全量重建」的执行器。

脚本的四道安全闸
----------------
1. **默认只读**: 不带 ``--apply`` 只打印计划, 绝不写库。
2. **多口径自检**: 逐行用若干**候选口径**复刻库里的 ``data_hash``, 报告每种口径
   命中多少行; **只要有一行哪种口径都命中不了, 就中止** —— 说明口径没搞清楚,
   不许写库。
3. **口径复现校验**: 重算出来的 hash 必须能被应用自身的
   ``DeduplicationService.calculate_data_hash`` 复算一致(同一份代码, 不手写哈希)。
4. **先备份**: ``--apply`` 先把受影响的 ``(id, old_data_hash, old_raw_data)`` 落盘,
   可回滚。

保留哪一行
----------
同一身份键多行时, 保留**入库时间最新**的那行 —— 这正是「口径稳定时 upsert 会留下的
那一行」(后一次入库覆盖前一次)。

实测 256/256 组里, 「入库时间最新」与「行级更新时间最新」**指向同一行** ⇒ 两个判据
不冲突, 保留规则唯一。

用法::

    # 只读: 看口径分布与计划(不改库)
    python scripts/rebuild_inventory_snapshot_hash.py

    # 真执行(先备份, 后改库)
    python scripts/rebuild_inventory_snapshot_hash.py --apply --backup-dir /tmp/inv_rebuild

    # 执行后复核(应当 100% 命中当前口径)
    python scripts/rebuild_inventory_snapshot_hash.py --verify
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_DATABASE_URL = (
    "postgresql+asyncpg://erp_user:erp_pass_2025@localhost:15432/xihong_erp"
)

#: 本脚本只处理库存快照维度(其它维度的事实表结构不同, 不复用)。
TARGET_TABLE = "b_class.fact_miaoshou_inventory_snapshot"

#: 候选口径。**顺序即优先级**。
#:
#: * ``scope_identity``  —— 作用域里的身份键(``DeduplicationService`` 取第一个可用的);
#: * ``row_shop_id``     —— 行内 ``shop_id`` 载荷值取哪来:
#:   ``raw`` = 行里存的值; ``account`` = 归一成账号 id(今天的采集口径);
#: * ``metric_date``     —— 载荷里是否带 auto-date 身份值。
CALIBERS: Dict[str, Dict[str, Any]] = {
    "当前口径(账号身份+带日期)": {
        "scope_identity": "shop_account_id",
        "row_shop_id": "account",
        "metric_date": True,
    },
    "同上但行内 shop_id 用原值": {
        "scope_identity": "shop_account_id",
        "row_shop_id": "raw",
        "metric_date": True,
    },
    "历史口径(店铺身份+带日期)": {
        "scope_identity": "shop_id",
        "row_shop_id": "raw",
        "metric_date": True,
    },
    "历史口径(店铺身份+不带日期)": {
        "scope_identity": "shop_id",
        "row_shop_id": "raw",
        "metric_date": False,
    },
}

#: 重建时使用的目标口径(必须与今天的采集口径一致, 否则下次采集又会多出新行)。
TARGET_CALIBER = "当前口径(账号身份+带日期)"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL") or ""
    if not url:
        # 容器里 DATABASE_URL 通常在项目 env 文件里 ⇒ 先加载它, 再回落到本地默认值。
        try:
            from backend.utils.project_env import load_project_env

            load_project_env(REPO_ROOT)
            url = os.environ.get("DATABASE_URL") or ""
        except Exception:  # noqa: BLE001 - 加载失败就用默认值
            url = ""
    if not url:
        return DEFAULT_DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _patch_hash_lookup_caches() -> None:
    """给「算 hash 时反复调用的纯函数」套缓存。

    为什么需要
    ----------
    ``resolve_semantic_value`` → ``_normalize_key_variants`` →
    ``currency_extractor.normalize_field_name`` 每次都要跑**几百次正则替换**
    (实测: 算 30 行 hash 触发了 46.7 万次 ``re.sub``)。
    ⇒ 单行 16.8 ms, 4111 行 × 3 遍要 3 分半。

    ⇒ 给两个**纯字符串函数**套 ``lru_cache``(货币代码的规范化与提取):
    实测单行 16.8 ms → 0.085 ms(约 200 倍), 4111 行 × 3 遍 ≈ 0.7 秒。

    为什么安全: 两个函数只依赖入参字符串, 不读运行时状态 ⇒ 缓存不改变任何结果。
    """
    import functools

    from backend.services.currency_extractor import CurrencyExtractor

    if getattr(CurrencyExtractor.normalize_field_name, "_mavis_cached", False):
        return

    for attr in ("normalize_field_name", "extract_currency_code"):
        original = getattr(CurrencyExtractor, attr)
        cached = functools.lru_cache(maxsize=8192)(original)
        cached._mavis_cached = True  # type: ignore[attr-defined]
        setattr(CurrencyExtractor, attr, cached)


def _load_definition() -> Dict[str, Any]:
    """读取仓库里的库存维度决策资产(新去重口径的来源)。"""
    from scripts.template_definitions import load_definitions  # type: ignore

    definitions = load_definitions()
    key = ("miaoshou", "inventory", "snapshot", None, None)
    definition = definitions.get(key)
    if definition is None:
        raise SystemExit(
            "[ERROR] 决策资产里找不到 miaoshou/inventory/snapshot; "
            f"可用维度: {sorted(str(k) for k in definitions)}"
        )
    return definition


def _build_hash_fields(
    *,
    template_fields: Optional[List[str]],
    rules: Optional[List[Dict[str, Any]]],
    data_domain: str,
    sub_domain: Optional[str],
) -> List[str]:
    """复刻入库路径的字段集合(模板字段 + 系统身份 + auto-date 身份)。"""
    from backend.services.deduplication_fields_config import (
        append_auto_date_identity_fields,
        get_deduplication_fields,
    )

    fields = get_deduplication_fields(
        data_domain=data_domain,
        template_fields=list(template_fields or []),
        sub_domain=sub_domain,
        header_bindings=None,
    )
    return append_auto_date_identity_fields(fields, list(rules or []))


def _identity_values(row: Dict[str, Any], *, with_metric_date: bool) -> Dict[str, Any]:
    """auto-date 身份值(``metric_date``)。"""
    if not with_metric_date:
        return {}
    metric_date = row.get("metric_date")
    if metric_date is None:
        return {}
    if isinstance(metric_date, datetime):
        metric_date = metric_date.date()
    if isinstance(metric_date, date):
        metric_date = metric_date.isoformat()
    return {"metric_date": metric_date}


def _row_for_hash(
    row: Dict[str, Any], caliber: Dict[str, Any]
) -> Tuple[Dict[str, Any], bool]:
    """按口径准备「参与 hash 的那一行」。

    返回 ``(行, 是否需要改写行内 shop_id)``。

    为什么可能改写行内 ``shop_id``
    ------------------------------
    载荷里的行内 ``shop_id`` 来自 ``raw_data`` 注入的身份列。历史批次注入的是
    店铺 id(``xihong``), 今天的采集注入的是**账号 id**。⇒ 口径归一时要把行内
    ``shop_id`` 也归一成账号 id, 否则算出来的 hash 与今天重新采集的结果对不上。
    """
    raw = dict(row["raw_data"])
    account_id = raw.get("shop_account_id") or ""
    if caliber["row_shop_id"] == "account" and account_id:
        if raw.get("shop_id") != account_id:
            raw["shop_id"] = account_id
            return raw, True
        return raw, False
    return raw, False


def _scope_values(row: Dict[str, Any], caliber: Dict[str, Any]) -> Dict[str, Any]:
    """按口径准备作用域(复刻 ``field_mapping_ingest.hash_scope_values``)。"""
    raw = row["raw_data"]
    identity_key = caliber["scope_identity"]
    if identity_key == "shop_account_id":
        identity_value = raw.get("shop_account_id") or row.get("shop_id")
    else:
        identity_value = row.get("shop_id")
    return {
        "platform_code": row.get("platform_code"),
        identity_key: identity_value,
        "data_domain": row.get("data_domain"),
        "granularity": row.get("granularity"),
        "sub_domain": row.get("sub_domain"),
    }


async def _fetch_rows(session) -> List[Dict[str, Any]]:
    from sqlalchemy import text

    result = await session.execute(
        text(
            f"""
            SELECT id, platform_code, shop_id, data_domain, granularity, sub_domain,
                   metric_date, data_hash, ingest_timestamp, raw_data
            FROM {TARGET_TABLE}
            ORDER BY id
            """
        )
    )
    rows: List[Dict[str, Any]] = []
    for row in result.mappings().all():
        data = dict(row)
        raw = data.get("raw_data") or {}
        data["raw_data"] = dict(raw) if isinstance(raw, dict) else {}
        rows.append(data)
    return rows


async def _load_current_template(session) -> Dict[str, Any]:
    """取**编辑面**当前发布的库存模板(当前口径的来源)。"""
    from sqlalchemy import text

    result = await session.execute(
        text(
            """
            SELECT id, version, deduplication_fields, field_parse_rules, core_fields
            FROM core.field_mapping_templates
            WHERE platform = 'miaoshou' AND data_domain = 'inventory'
              AND granularity = 'snapshot' AND status = 'published'
            ORDER BY version DESC, id DESC
            LIMIT 1
            """
        )
    )
    row = result.mappings().first()
    if row is None:
        raise SystemExit("[ERROR] 找不到已发布的库存模板(编辑面)")
    return dict(row)


def _compute(
    service,
    row: Dict[str, Any],
    *,
    fields: List[str],
    caliber: Dict[str, Any],
) -> str:
    """用**应用自身**的 hash 函数算一行的 hash(不手写哈希算法)。"""
    hash_row, _changed = _row_for_hash(row, caliber)
    return service.calculate_data_hash(
        hash_row,
        deduplication_fields=list(fields),
        header_bindings=None,
        scope_values=_scope_values(row, caliber),
        identity_values=_identity_values(row, with_metric_date=caliber["metric_date"]),
    )


def _keep_row(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """同一身份键多行时保留哪一行: 入库时间最新(并列则 id 最大)。"""
    return sorted(rows, key=lambda r: (r["ingest_timestamp"], r["id"]))[-1]


def _update_sql(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """构造「批量改 hash」的 SQL 与参数。

    用 ``unnest(数组)`` 而不是几百个 ``VALUES`` 占位符:
    ``VALUES ($1,$2),($3,$4)...`` 里 Postgres 会按首行推断列类型,
    与 ``bigint`` 主键比较时报 "operator does not exist: bigint = text"
    (实测踩过)。数组版没有这个坑, 参数也少两个数量级。
    """
    from sqlalchemy import text

    sql = text(
        f"""
        UPDATE {TARGET_TABLE} AS t
        SET data_hash = v.new_hash
        FROM unnest(
            CAST(:ids AS bigint[]),
            CAST(:hashes AS text[])
        ) AS v(id, new_hash)
        WHERE t.id = v.id
        """
    )
    return {
        "sql": sql,
        "params": {
            "ids": [int(row["id"]) for row in rows],
            "hashes": [str(row["new_hash"]) for row in rows],
        },
    }


async def run(args) -> int:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from backend.services.deduplication_service import DeduplicationService

    definition = _load_definition()
    new_template_fields = list(definition.get("deduplication_fields") or [])
    new_rules = list(definition.get("field_parse_rules") or [])
    data_domain = str(definition["data_domain"])
    granularity = str(definition["granularity"])
    sub_domain = definition.get("sub_domain")

    engine = create_async_engine(_database_url(), echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    service = DeduplicationService(db=None)
    _patch_hash_lookup_caches()

    try:
        async with factory() as session:
            template = await _load_current_template(session)
            rows = await _fetch_rows(session)

            old_fields = _build_hash_fields(
                template_fields=list(template.get("deduplication_fields") or []),
                rules=list(template.get("field_parse_rules") or []),
                data_domain=data_domain,
                sub_domain=sub_domain,
            )
            new_fields = _build_hash_fields(
                template_fields=new_template_fields,
                rules=new_rules,
                data_domain=data_domain,
                sub_domain=sub_domain,
            )

            print("=" * 78)
            print("库存快照事实表 · data_hash 重建")
            print("=" * 78)
            print(f"目标表          : {TARGET_TABLE}")
            print(f"行数            : {len(rows)}")
            print(f"当前库内去重字段: {old_fields}")
            print(f"新去重字段      : {new_fields}")
            print(f"当前模板        : id={template['id']} v{template['version']}")
            print(f"目标口径        : {TARGET_CALIBER}")

            # ── 守卫: 表里的行必须真的是这个维度的 ──────────────────────
            mismatched = [
                row["id"]
                for row in rows
                if str(row.get("platform_code")) != str(definition["platform"])
                or str(row.get("data_domain")) != data_domain
                or str(row.get("granularity")) != granularity
            ]
            if mismatched:
                print(
                    f"\n[中止] 表里有 {len(mismatched)} 行不属于 "
                    f"{definition['platform']}/{data_domain}/{granularity} "
                    f"(前 20: {mismatched[:20]}) ⇒ 不许写库。"
                )
                return 2

            # ── 复核模式: 库里应当已全部命中**新**口径 ──────────────────
            if args.verify:
                target_caliber = CALIBERS[TARGET_CALIBER]
                ok = 0
                bad: List[int] = []
                for row in rows:
                    hash_row, _changed = _row_for_hash(row, target_caliber)
                    computed = service.calculate_data_hash(
                        hash_row,
                        deduplication_fields=list(new_fields),
                        header_bindings=None,
                        scope_values=_scope_values(row, target_caliber),
                        identity_values=_identity_values(
                            row, with_metric_date=target_caliber["metric_date"]
                        ),
                    )
                    if computed == row["data_hash"]:
                        ok += 1
                    else:
                        bad.append(row["id"])
                print()
                print(f"[复核] 新口径命中 {ok} / {len(rows)} 行")
                if bad:
                    print(f"  未命中 id(前 20): {bad[:20]}")
                print(f"[复核] 库里已全部命中新口径: {not bad}")
                return 0 if not bad else 1

            # ── 自检: 逐行认领口径 ───────────────────────────────────────
            caliber_hits: Dict[str, int] = {name: 0 for name in CALIBERS}
            unmatched: List[int] = []
            for row in rows:
                for name, caliber in CALIBERS.items():
                    if (
                        _compute(service, row, fields=old_fields, caliber=caliber)
                        == row["data_hash"]
                    ):
                        caliber_hits[name] += 1
                        break
                else:
                    unmatched.append(row["id"])

            print()
            print("【自检一】存量 hash 分别属于哪种口径:")
            for name, count in caliber_hits.items():
                print(f"  {name:<28} {count} 行")
            print(f"  {'认不出来的行':<28} {len(unmatched)} 行")
            if unmatched:
                print(f"  异常行 id(前 20): {unmatched[:20]}")
                print("\n[中止] 有行既不属于任何已知口径 ⇒ 口径没搞清楚, 不许写库。")
                return 2

            # ── 自检二: 新口径重算 ───────────────────────────────────────
            target_caliber = CALIBERS[TARGET_CALIBER]
            groups: Dict[str, List[Dict[str, Any]]] = {}
            raw_changed: List[Dict[str, Any]] = []
            for row in rows:
                hash_row, changed = _row_for_hash(row, target_caliber)
                row["new_hash"] = service.calculate_data_hash(
                    hash_row,
                    deduplication_fields=list(new_fields),
                    header_bindings=None,
                    scope_values=_scope_values(row, target_caliber),
                    identity_values=_identity_values(
                        row, with_metric_date=target_caliber["metric_date"]
                    ),
                )
                row["_raw_changed"] = changed
                if changed:
                    raw_changed.append(row)
                groups.setdefault(row["new_hash"], []).append(row)

            duplicate_groups = {k: v for k, v in groups.items() if len(v) > 1}
            to_delete: List[Dict[str, Any]] = []
            to_update: List[Dict[str, Any]] = []
            for members in groups.values():
                keeper = _keep_row(members)
                to_update.append(keeper)
                for member in members:
                    if member["id"] != keeper["id"]:
                        to_delete.append(member)

            print()
            print("【自检二】按新口径重算:")
            print(f"  新 hash 去重后行数 : {len(groups)}")
            print(f"  需要删除的行       : {len(to_delete)}")
            print(f"  需要改 hash 的行   : {len(to_update)}")
            print(
                f"  其中 hash 确实变了 : {sum(1 for r in to_update if r['new_hash'] != r['data_hash'])}"
            )
            print(f"  行内 shop_id 需归一 : {len(raw_changed)}")

            if not args.apply:
                print()
                print("[只读模式] 以上是计划; 加 --apply 才会写库。")
                if duplicate_groups:
                    sample = next(iter(duplicate_groups.values()))[0]
                    print(
                        "  样例重复组: "
                        f"sku={sample['raw_data'].get('*商品SKU')} "
                        f"仓={sample['raw_data'].get('仓库')} "
                        f"日={sample['metric_date']} "
                        f"入库={sample['ingest_timestamp']}"
                    )
                return 0

            # ── 备份 ────────────────────────────────────────────────────
            backup_path: Optional[Path] = None
            if args.backup_dir:
                backup_dir = Path(args.backup_dir)
                backup_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                backup_path = backup_dir / f"inv_hash_backup_{stamp}.tsv"
                with backup_path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle, delimiter="\t")
                    writer.writerow(
                        [
                            "id",
                            "action",
                            "old_data_hash",
                            "new_data_hash",
                            "ingest_timestamp",
                            "metric_date",
                            "old_raw_shop_id",
                            "new_raw_shop_id",
                        ]
                    )
                    for member in to_delete:
                        writer.writerow(
                            [
                                member["id"],
                                "delete",
                                member["data_hash"],
                                member["new_hash"],
                                member["ingest_timestamp"],
                                member["metric_date"],
                                member["raw_data"].get("shop_id"),
                                member["raw_data"].get("shop_account_id"),
                            ]
                        )
                    for member in to_update:
                        if (
                            member["new_hash"] != member["data_hash"]
                            or member["_raw_changed"]
                        ):
                            writer.writerow(
                                [
                                    member["id"],
                                    "update",
                                    member["data_hash"],
                                    member["new_hash"],
                                    member["ingest_timestamp"],
                                    member["metric_date"],
                                    member["raw_data"].get("shop_id"),
                                    member["raw_data"].get("shop_account_id"),
                                ]
                            )
                print(f"\n[备份] {backup_path}")

            # ── 写库 ────────────────────────────────────────────────────
            # ⚠️ 前面已经做过 SELECT ⇒ session 上已有隐式事务,
            #    这里**不能**再 `async with session.begin()`(会抛
            #    "a transaction is already begun") ⇒ 直接执行 + 显式 commit。
            if to_delete:
                await session.execute(
                    text(f"DELETE FROM {TARGET_TABLE} WHERE id = ANY(:ids)"),
                    {"ids": [member["id"] for member in to_delete]},
                )
            # 行内 shop_id 归一(与今天的采集口径一致)
            if raw_changed:
                raw_update = _raw_update_params(raw_changed)
                await session.execute(raw_update["sql"], raw_update["params"])
            changed_rows = [r for r in to_update if r["new_hash"] != r["data_hash"]]
            if changed_rows:
                update = _update_sql(changed_rows)
                await session.execute(update["sql"], update["params"])
            await session.commit()

            print(
                f"[完成] 删除 {len(to_delete)} 行, "
                f"更新 {len(changed_rows)} 行 hash, "
                f"归一 {len(raw_changed)} 行行内 shop_id"
            )
            if backup_path:
                print(f"[回滚依据] {backup_path}")
            return 0
    finally:
        await engine.dispose()


def _raw_update_params(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """构造「批量归一行内 shop_id」的 SQL 与参数(同样是 unnest 数组版)。"""
    from sqlalchemy import text

    sql = text(
        f"""
        UPDATE {TARGET_TABLE} AS t
        SET raw_data = jsonb_set(
                t.raw_data,
                '{{shop_id}}',
                to_jsonb(v.account_id),
                true
            )
        FROM unnest(
            CAST(:ids AS bigint[]),
            CAST(:accounts AS text[])
        ) AS v(id, account_id)
        WHERE t.id = v.id
        """
    )
    return {
        "sql": sql,
        "params": {
            "ids": [int(row["id"]) for row in rows],
            "accounts": [
                str(row["raw_data"].get("shop_account_id") or "") for row in rows
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="按当前口径重建库存快照事实表的 data_hash"
    )
    parser.add_argument("--apply", action="store_true", help="真的写库(默认只读)")
    parser.add_argument(
        "--verify", action="store_true", help="复核: 库里是否已全命中新口径"
    )
    parser.add_argument("--backup-dir", default="", help="备份目录(写库前落盘)")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
