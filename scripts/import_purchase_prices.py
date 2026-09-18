"""商品中心 SKU 采购价批量录入脚本.

读取 product-catalog skill 的 sku-reverse-lookup.xlsx,批量写入
PostgreSQL core.dim_erp_sku.default_purchase_cost 及其元数据。

详见 docs/superpowers/specs/2026-09-18-purchase-price-import-design.md
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import openpyxl


SHEET_NAME = "SKU反查表"
COL_SKU_CODE = 0  # 第 1 列 (0-indexed)
COL_PRICE = 8     # 第 9 列 (0-indexed)
EM_DASH = "—"
SOURCE_VALUE = "妙手导入"
CONFIDENCE_VALUE = "medium"
CURRENCY_VALUE = "CNY"


@dataclass(frozen=True)
class ParsedRow:
    sku_code: str
    price: float


def parse_lookup_xlsx(path: str) -> tuple[list[tuple[str, float]], list[str], list[str]]:
    """读取 xlsx 并按过滤规则分类.

    Returns:
        (valid, skipped, errors)
        - valid:   [(sku_code, price), ...]   # 价格 > 0 的数字
        - skipped: [sku_code, ...]             # 被跳过的 SKU code(— / 0 / 空)
        - errors:  [message, ...]              # 解析错误信息(字符串型非 — 等)
    """
    valid: list[tuple[str, float]] = []
    skipped: list[str] = []
    errors: list[str] = []

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if SHEET_NAME not in wb.sheetnames:
        errors.append(f"xlsx 找不到 sheet '{SHEET_NAME}',实际 sheets: {wb.sheetnames}")
        return valid, skipped, errors
    ws = wb[SHEET_NAME]

    rows = ws.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        errors.append("xlsx 没有表头行")
        return valid, skipped, errors

    if len(header) < 9 or header[COL_SKU_CODE] != "SKU code" or header[COL_PRICE] != "采购单价(元)":
        errors.append(
            f"xlsx 表头不符,期望第1列='SKU code' 第9列='采购单价(元)',实际: {header[:9]}"
        )
        return valid, skipped, errors

    for row in rows:
        if row is None:
            continue
        sku_code = row[COL_SKU_CODE]
        price = row[COL_PRICE]
        if sku_code is None or str(sku_code).strip() == "":
            continue
        sku_code_str = str(sku_code).strip()
        if price is None or (isinstance(price, str) and price.strip() == ""):
            skipped.append(sku_code_str)
            continue
        if isinstance(price, str):
            if price.strip() == EM_DASH:
                skipped.append(sku_code_str)
                continue
            errors.append(f"{sku_code_str}: 价格是字符串 '{price=}' 非数字,且非 — ")
            continue
        if isinstance(price, (int, float)):
            if price <= 0:
                skipped.append(sku_code_str)
                continue
            valid.append((sku_code_str, float(price)))
            continue
        errors.append(f"{sku_code_str}: 价格类型未知 {type(price).__name__}")

    return valid, skipped, errors


async def fetch_db_sku_keys(db_url: str) -> set[str]:
    """从 core.dim_erp_sku 读所有 sku_key."""
    import asyncpg
    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch('SELECT sku_key FROM core.dim_erp_sku')
        return {r["sku_key"] for r in rows if r["sku_key"]}
    finally:
        await conn.close()


def reconcile(
    valid: list[tuple[str, float]],
    db_keys: set[str],
) -> tuple[list[tuple[str, float]], list[str], list[str]]:
    """比对 xlsx 有效条目与 DB sku_key.

    Returns:
        (matched, lookup_only, db_only)
    """
    lookup_keys = {code for code, _ in valid}
    matched = [(code, price) for code, price in valid if code in db_keys]
    lookup_only = sorted(lookup_keys - db_keys)
    db_only = sorted(db_keys - lookup_keys)
    return matched, lookup_only, db_only


def build_update_rows(
    matched: list[tuple[str, float]],
    now: datetime,
) -> list[tuple[str, float, str, str, str, datetime]]:
    """把 matched 展开成 executemany 需要的行.

    每行: (sku_key, price, currency, source, confidence, confirmed_at)
    """
    return [
        (sku_code, price, CURRENCY_VALUE, SOURCE_VALUE, CONFIDENCE_VALUE, now)
        for sku_code, price in matched
    ]


async def create_backup_table(db_url: str, backup_table: str) -> None:
    """全表快照备份(覆盖原表前必做)。"""
    import asyncpg
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute(f"DROP TABLE IF EXISTS {backup_table}")
        await conn.execute(
            f"CREATE TABLE {backup_table} AS SELECT * FROM core.dim_erp_sku"
        )
    finally:
        await conn.close()


async def apply_update(
    db_url: str,
    matched: list[tuple[str, float]],
    backup_table: str,
    skip_backup: bool = False,
) -> int:
    """事务内 UPDATE。失败自动 ROLLBACK。返回成功行数."""
    import asyncpg
    if not skip_backup:
        await create_backup_table(db_url, backup_table)

    now = datetime.now(timezone.utc)
    rows = build_update_rows(matched, now)

    conn = await asyncpg.connect(db_url)
    try:
        async with conn.transaction():
            await conn.executemany(
                """
                UPDATE core.dim_erp_sku
                SET default_purchase_cost = $2,
                    purchase_cost_currency = $3,
                    purchase_cost_source = $4,
                    purchase_cost_confidence = $5,
                    purchase_cost_confirmed_at = $6
                WHERE sku_key = $1
                """,
                rows,
            )
    finally:
        await conn.close()
    return len(rows)