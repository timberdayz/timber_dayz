"""Seed canonical SPU/SKU master data from the product-catalog Skill lookup workbook.

The workbook is an input artifact, never a runtime dependency.  Use --dry-run
(the default) to validate the file, and --apply to upsert approved rows.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import OrderedDict
from datetime import date
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from openpyxl import load_workbook
from sqlalchemy import select

from backend.models.database import AsyncSessionLocal
from modules.core.db import BridgeErpSkuKey, BridgeSpuSku, DimErpSku, DimSpu


EXPECTED_HEADERS = {
    "SKU code",
    "SPU code",
    "一级 code",
    "二级 code",
    "一级中文",
    "二级中文",
    "中文商品名",
}


def load_lookup(path: Path) -> tuple[list[dict], list[str]]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.active
    rows = sheet.iter_rows(values_only=True)
    headers = [str(value or "").strip() for value in next(rows)]
    missing = sorted(EXPECTED_HEADERS - set(headers))
    if missing:
        raise ValueError(f"lookup workbook missing headers: {', '.join(missing)}")
    index = {name: headers.index(name) for name in EXPECTED_HEADERS}
    seen_skus: set[str] = set()
    normalized: list[dict] = []
    duplicates: list[str] = []
    for raw in rows:
        sku = str(raw[index["SKU code"]] or "").strip()
        spu = str(raw[index["SPU code"]] or "").strip()
        if not sku or not spu:
            continue
        if sku in seen_skus:
            duplicates.append(sku)
            continue
        seen_skus.add(sku)
        normalized.append(
            {
                "sku_key": sku,
                "spu": spu,
                "spu_name": str(raw[index["中文商品名"]] or spu).strip()[:512],
                "category_l1_code": str(raw[index["一级 code"]] or "").strip() or None,
                "category_l2_code": str(raw[index["二级 code"]] or "").strip() or None,
            }
        )
    return normalized, duplicates


def validate_rows(rows: list[dict]) -> list[str]:
    errors: list[str] = []
    for row in rows:
        if not row["category_l2_code"]:
            errors.append(f"{row['sku_key']}: missing secondary category")
        if not row["spu"].startswith("XH-"):
            errors.append(f"{row['spu']}: invalid SPU prefix")
    return errors


async def apply_rows(rows: list[dict]) -> tuple[int, int, int]:
    grouped: OrderedDict[str, dict] = OrderedDict()
    for row in rows:
        grouped.setdefault(row["spu"], row)
    created_spu = created_sku = created_bindings = 0
    async with AsyncSessionLocal() as db:
        for spu_code, source in grouped.items():
            spu = await db.get(DimSpu, spu_code)
            if spu is None:
                spu = DimSpu(
                    spu=spu_code,
                    spu_name=source["spu_name"],
                    category_l1_code=source["category_l1_code"],
                    category_l2_code=source["category_l2_code"],
                    active=True,
                )
                db.add(spu)
                created_spu += 1
            for row in (item for item in rows if item["spu"] == spu_code):
                sku = (await db.execute(select(DimErpSku).where(DimErpSku.sku_key == row["sku_key"]))).scalar_one_or_none()
                if sku is None:
                    sku = DimErpSku(sku_key=row["sku_key"], sku_name=row["spu_name"], status="active", last_seen_at=None)
                    db.add(sku)
                    await db.flush()
                    created_sku += 1
                source_key = (await db.execute(select(BridgeErpSkuKey).where(BridgeErpSkuKey.source_system == "product-catalog", BridgeErpSkuKey.source_key_type == "sku", BridgeErpSkuKey.source_key == row["sku_key"]))).scalar_one_or_none()
                if source_key is None:
                    db.add(BridgeErpSkuKey(source_system="product-catalog", source_platform="erp", source_key_type="sku", source_key=row["sku_key"], sku_id=sku.sku_id, effective_from=date.today(), active=True))
                binding = (await db.execute(select(BridgeSpuSku).where(BridgeSpuSku.sku_id == sku.sku_id, BridgeSpuSku.effective_to.is_(None), BridgeSpuSku.binding_status == "active"))).scalar_one_or_none()
                if binding is None:
                    db.add(BridgeSpuSku(spu=spu_code, sku_id=sku.sku_id, effective_from=date.today(), binding_status="active"))
                    created_bindings += 1
        await db.commit()
    return created_spu, created_sku, created_bindings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookup", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows, duplicates = load_lookup(args.lookup)
    errors = validate_rows(rows)
    print(f"validated rows={len(rows)} duplicate_rows={len(duplicates)} errors={len(errors)}")
    if duplicates:
        print(f"duplicate SKU examples: {', '.join(duplicates[:10])}")
    if errors:
        for error in errors[:20]:
            print(error)
        return 2
    if not args.apply:
        print("dry-run only; pass --apply after review")
        return 0
    created_spu, created_sku, created_bindings = asyncio.run(apply_rows(rows))
    print(f"applied spus={created_spu} skus={created_sku} bindings={created_bindings}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
