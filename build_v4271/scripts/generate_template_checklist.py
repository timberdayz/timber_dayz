#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Template Coverage Checklist Generator
-------------------------------------

Generates a coverage report for field-mapping templates across all catalog
files. The output helps data stewards understand which platform / data
domain / sub-domain / granularity combinations still lack templates.

The script:
1. Scans `catalog_files` (Single Source of Truth) for existing combinations.
2. Calculates template availability from `field_mapping_templates`.
3. Produces a CSV report under `temp/reports/`.

Usage:
    python scripts/generate_template_checklist.py
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from backend.models.database import SessionLocal
from modules.core.db import CatalogFile, FieldMappingTemplate


def safe_print(text: str) -> None:
    """Print helper that tolerates Windows GBK consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.write(text.encode("gbk", errors="ignore").decode("gbk") + "\n")


def fetch_catalog_combinations(db: Session) -> Dict[Tuple[str, str, str, str], Dict[str, object]]:
    """
    Return catalog combinations with file statistics.

    Key: (platform, data_domain, sub_domain, granularity)
    Value: dict with total_files, pending_files, accounts (set)
    """
    rows = (
        db.query(
            func.coalesce(CatalogFile.source_platform, CatalogFile.platform_code, "").label("platform"),
            func.coalesce(CatalogFile.data_domain, "").label("data_domain"),
            func.coalesce(CatalogFile.sub_domain, "").label("sub_domain"),
            func.coalesce(CatalogFile.granularity, "").label("granularity"),
            func.coalesce(CatalogFile.account, "").label("account"),
            func.count(CatalogFile.id).label("total_files"),
            func.sum(
                case((CatalogFile.status == "pending", 1), else_=0)
            ).label("pending_files"),
            func.max(CatalogFile.last_processed_at).label("last_processed_at"),
        )
        .filter(CatalogFile.platform_code.isnot(None), CatalogFile.data_domain.isnot(None))
        .group_by(
            func.coalesce(CatalogFile.source_platform, CatalogFile.platform_code, ""),
            func.coalesce(CatalogFile.data_domain, ""),
            func.coalesce(CatalogFile.sub_domain, ""),
            func.coalesce(CatalogFile.granularity, ""),
            func.coalesce(CatalogFile.account, ""),
        )
        .all()
    )

    combinations: Dict[Tuple[str, str, str, str], Dict[str, object]] = {}

    for row in rows:
        key = (row.platform or "", row.data_domain or "", row.sub_domain or "", row.granularity or "")
        entry = combinations.setdefault(
            key,
            {
                "accounts": set(),
                "total_files": 0,
                "pending_files": 0,
                "last_processed_at": row.last_processed_at,
            },
        )
        entry["accounts"].add(row.account or "")
        entry["total_files"] += int(row.total_files or 0)
        entry["pending_files"] += int(row.pending_files or 0)
        if row.last_processed_at and (
            entry["last_processed_at"] is None or row.last_processed_at > entry["last_processed_at"]
        ):
            entry["last_processed_at"] = row.last_processed_at

    return combinations


def fetch_template_lookup(db: Session) -> Dict[Tuple[str, str, str, str], Dict[str, object]]:
    """
    Build a lookup of template coverage keyed by (platform, data_domain, sub_domain, granularity).
    """
    templates = (
        db.query(
            FieldMappingTemplate.id,
            FieldMappingTemplate.platform,
            FieldMappingTemplate.data_domain,
            FieldMappingTemplate.sub_domain,
            FieldMappingTemplate.granularity,
            FieldMappingTemplate.account,
            FieldMappingTemplate.template_name,
            FieldMappingTemplate.version,
            FieldMappingTemplate.status,
            FieldMappingTemplate.updated_at,
            FieldMappingTemplate.created_at,
        )
        .filter(FieldMappingTemplate.status != "archived")
        .all()
    )

    lookup: Dict[Tuple[str, str, str, str], Dict[str, object]] = {}

    for tpl in templates:
        key = (
            (tpl.platform or "").strip(),
            (tpl.data_domain or "").strip(),
            (tpl.sub_domain or "").strip(),
            (tpl.granularity or "").strip(),
        )
        record = lookup.get(key)
        tpl_updated_at = tpl.updated_at or tpl.created_at

        if record is None or (tpl_updated_at and tpl_updated_at > record.get("updated_at")):
            lookup[key] = {
                "template_id": tpl.id,
                "template_name": tpl.template_name or "",
                "version": tpl.version or 1,
                "status": tpl.status or "",
                "account": tpl.account or "",
                "updated_at": tpl_updated_at,
            }

    return lookup


def ensure_output_dir() -> Path:
    """Ensure the temp/reports directory exists."""
    output_dir = Path("temp") / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_report(rows: Dict[Tuple[str, str, str, str], Dict[str, object]], lookup: Dict[Tuple[str, str, str, str], Dict[str, object]]) -> Path:
    """Persist the template coverage report to CSV."""
    output_dir = ensure_output_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"template_checklist_{timestamp}.csv"

    fieldnames = [
        "platform",
        "data_domain",
        "sub_domain",
        "granularity",
        "accounts",
        "total_files",
        "pending_files",
        "has_template",
        "template_id",
        "template_name",
        "template_version",
        "template_status",
        "template_account",
        "template_updated_at",
        "last_processed_at",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for key, stats in sorted(rows.items()):
            template = lookup.get(key, {})
            writer.writerow(
                {
                    "platform": key[0],
                    "data_domain": key[1],
                    "sub_domain": key[2],
                    "granularity": key[3],
                    "accounts": ", ".join(sorted(filter(None, stats["accounts"]))),
                    "total_files": stats["total_files"],
                    "pending_files": stats["pending_files"],
                    "has_template": "yes" if template else "no",
                    "template_id": template.get("template_id", ""),
                    "template_name": template.get("template_name", ""),
                    "template_version": template.get("version", ""),
                    "template_status": template.get("status", ""),
                    "template_account": template.get("account", ""),
                    "template_updated_at": template.get("updated_at", ""),
                    "last_processed_at": stats.get("last_processed_at", ""),
                }
            )

    return output_path


def main() -> None:
    safe_print("[INFO] Generating template coverage checklist ...")

    db = SessionLocal()
    try:
        combinations = fetch_catalog_combinations(db)
        template_lookup = fetch_template_lookup(db)

        total_combos = len(combinations)
        covered = sum(1 for key in combinations if key in template_lookup)

        output_path = write_report(combinations, template_lookup)

        coverage_rate = (covered / total_combos * 100) if total_combos else 0.0

        safe_print(f"[OK] Coverage report created: {output_path}")
        safe_print(f"[STATS] Total combinations: {total_combos}")
        safe_print(f"[STATS] Covered combinations: {covered}")
        safe_print(f"[STATS] Coverage rate: {coverage_rate:.2f}%")

        missing = [
            key for key in sorted(combinations) if key not in template_lookup
        ]
        if missing:
            safe_print("[WARN] Combinations without templates:")
            for platform, data_domain, sub_domain, granularity in missing:
                safe_print(
                    f"  - platform={platform or '<none>'}, domain={data_domain or '<none>'}, "
                    f"sub_domain={sub_domain or '<none>'}, granularity={granularity or '<none>'}"
                )
        else:
            safe_print("[OK] All combinations have templates.")

    finally:
        db.close()


if __name__ == "__main__":
    main()


