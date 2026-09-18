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


async def verify_post_state(db_url: str) -> dict:
    """执行后验证 DB 状态."""
    import asyncpg
    conn = await asyncpg.connect(db_url)
    try:
        total = await conn.fetchval("SELECT COUNT(*) FROM core.dim_erp_sku")
        filled = await conn.fetchval(
            "SELECT COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost IS NOT NULL"
        )
        negative = await conn.fetchval(
            "SELECT COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost < 0"
        )
        zero = await conn.fetchval(
            "SELECT COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost = 0"
        )
        rows = await conn.fetch(
            """SELECT purchase_cost_source, COUNT(*) AS n
               FROM core.dim_erp_sku
               WHERE default_purchase_cost IS NOT NULL
               GROUP BY purchase_cost_source"""
        )
        by_source = {r["purchase_cost_source"]: r["n"] for r in rows}
        return {
            "total": total,
            "filled": filled,
            "negative": negative,
            "zero": zero,
            "by_source": by_source,
        }
    finally:
        await conn.close()


async def sample_check(db_url: str, sample_size: int = 10) -> list[dict]:
    """抽取 N 个有采购价的 SKU 供人工核对."""
    import asyncpg
    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            """SELECT sku_key, default_purchase_cost, purchase_cost_currency,
                      purchase_cost_source, purchase_cost_confidence,
                      purchase_cost_confirmed_at
               FROM core.dim_erp_sku
               WHERE default_purchase_cost IS NOT NULL
               ORDER BY random()
               LIMIT $1""",
            sample_size,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def write_reconciliation_csv(path: Path, lookup_only: list[str], db_only: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "sku_code"])
        for code in lookup_only:
            w.writerow(["lookup_only", code])
        for code in db_only:
            w.writerow(["db_only", code])


def write_dryrun_csv(path: Path, matched: list[tuple[str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku_code", "new_price", "currency", "source", "confidence"])
        for sku_code, price in matched:
            w.writerow([sku_code, price, CURRENCY_VALUE, SOURCE_VALUE, CONFIDENCE_VALUE])


def write_sample_csv(path: Path, samples: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        if not samples:
            return
        w = csv.DictWriter(f, fieldnames=list(samples[0].keys()))
        w.writeheader()
        for s in samples:
            w.writerow(s)


def make_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="商品中心 SKU 采购价批量录入")
    p.add_argument("--xlsx-path", default=r"F:\Work Tool\resource\skills\team-skills\product-catalog\sku-reverse-lookup.xlsx")
    p.add_argument("--database-url", default=None, help="PostgreSQL 连接 URL,默认从 settings.DATABASE_URL 读")
    p.add_argument("--apply", action="store_true", help="真实写入数据库(默认 dry-run)")
    p.add_argument("--skip-backup", action="store_true", help="跳过备份表创建(慎用)")
    p.add_argument("--backup-table", default=None, help="备份表名,默认 core.dim_erp_sku_backup_YYYYMMDD")
    p.add_argument("--output-dir", default="output", help="报告/日志输出目录")
    return p


def _resolve_db_url(arg: str | None) -> str:
    if arg:
        return arg
    # 从 .env 读(简单实现,避免 import 完整 settings)
    from pathlib import Path
    env = Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("无法从 .env 读 DATABASE_URL,请用 --database-url 显式指定")


async def run(args: argparse.Namespace) -> int:
    """主入口."""
    db_url = _resolve_db_url(args.database_url)
    today = datetime.now().strftime("%Y%m%d")
    backup_table = args.backup_table or f"core.dim_erp_sku_backup_{today}"
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    valid, skipped, errors = parse_lookup_xlsx(args.xlsx_path)
    if errors:
        for e in errors:
            print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    print(f"[INFO] xlsx: {len(valid)} valid, {len(skipped)} skipped (—/0/empty)")

    db_keys = await fetch_db_sku_keys(db_url)
    matched, lookup_only, db_only = reconcile(valid, db_keys)
    print(f"[INFO] reconcile: matched={len(matched)} lookup_only={len(lookup_only)} db_only={len(db_only)}")

    write_reconciliation_csv(output_dir / f"purchase_price_reconciliation_{today}.csv", lookup_only, db_only)
    write_dryrun_csv(output_dir / f"purchase_price_import_dryrun_{today}.csv", matched)

    if not args.apply:
        print("[INFO] dry-run 模式,未写入数据库。带 --apply 真实执行")
        return 1 if (lookup_only or db_only) else 0

    # 真写
    print(f"[INFO] 备份表: {backup_table}")
    count = await apply_update(db_url, matched, backup_table, skip_backup=args.skip_backup)
    print(f"[INFO] 写入完成: {count} 行")

    state = await verify_post_state(db_url)
    print(f"[INFO] post-state: {state}")
    samples = await sample_check(db_url)
    write_sample_csv(output_dir / f"purchase_price_sample_check_{today}.csv", samples)

    return 0 if state["negative"] == 0 and state["zero"] == 0 else 2


def main() -> None:
    args = make_argparser().parse_args()
    code = asyncio.run(run(args))
    sys.exit(code)


if __name__ == "__main__":
    main()