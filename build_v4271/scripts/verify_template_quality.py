#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Template Quality Analyzer
-------------------------

Evaluates field-mapping templates and highlights templates that may require
manual review. The analysis focuses on:

- Confidence score distribution.
- Unmapped or placeholder standard fields.
- Template status and last update timestamp.

The script outputs a CSV report (`temp/reports/template_quality_*.csv`) and
prints a summary to the console.

Usage:
    python scripts/verify_template_quality.py
"""

from __future__ import annotations

import csv
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from sqlalchemy.orm import Session

from backend.models.database import SessionLocal
from modules.core.db import FieldMappingDictionary, FieldMappingTemplate, FieldMappingTemplateItem


def safe_print(text: str) -> None:
    """Print helper compatible with Windows GBK consoles."""
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.write(text.encode("gbk", errors="ignore").decode("gbk") + "\n")


def load_dictionary_codes(db: Session) -> set:
    """Return the set of valid standard field codes."""
    rows = db.query(FieldMappingDictionary.field_code).filter(FieldMappingDictionary.active.is_(True)).all()
    return {row.field_code for row in rows if row.field_code}


def analyze_templates(db: Session, valid_codes: set) -> List[Dict[str, object]]:
    """Analyze template quality metrics."""
    templates = (
        db.query(FieldMappingTemplate)
        .filter(FieldMappingTemplate.status != "archived")
        .order_by(
            FieldMappingTemplate.platform,
            FieldMappingTemplate.data_domain,
            FieldMappingTemplate.sub_domain,
            FieldMappingTemplate.granularity,
        )
        .all()
    )

    items_by_template: Dict[int, List[FieldMappingTemplateItem]] = {}
    if templates:
        item_rows = (
            db.query(FieldMappingTemplateItem)
            .filter(FieldMappingTemplateItem.template_id.in_([tpl.id for tpl in templates]))
            .all()
        )
        for item in item_rows:
            items_by_template.setdefault(item.template_id, []).append(item)

    results: List[Dict[str, object]] = []

    for tpl in templates:
        tpl_items = items_by_template.get(tpl.id, [])
        total_items = len(tpl_items)

        confidences = [item.confidence for item in tpl_items if item.confidence is not None]
        low_conf_items = [item for item in tpl_items if item.confidence is not None and item.confidence < 0.85]
        unmapped_items = [
            item for item in tpl_items if not item.standard_field or item.standard_field.strip() in {"", "未映射"}
        ]
        invalid_codes = [
            item for item in tpl_items if item.standard_field and item.standard_field not in valid_codes
        ]

        avg_confidence = statistics.mean(confidences) if confidences else None
        median_confidence = statistics.median(confidences) if confidences else None

        needs_review = any(
            [
                tpl.status != "published",
                bool(low_conf_items),
                bool(unmapped_items),
                bool(invalid_codes),
                (avg_confidence is not None and avg_confidence < 0.9),
            ]
        )

        results.append(
            {
                "template_id": tpl.id,
                "platform": tpl.platform or "",
                "data_domain": tpl.data_domain or "",
                "sub_domain": tpl.sub_domain or "",
                "granularity": tpl.granularity or "",
                "account": tpl.account or "",
                "template_name": tpl.template_name or "",
                "version": tpl.version or 1,
                "status": tpl.status or "",
                "field_count": total_items,
                "avg_confidence": round(avg_confidence, 4) if avg_confidence is not None else "",
                "median_confidence": round(median_confidence, 4) if median_confidence is not None else "",
                "low_confidence_count": len(low_conf_items),
                "unmapped_count": len(unmapped_items),
                "invalid_code_count": len(invalid_codes),
                "usage_count": tpl.usage_count or 0,
                "success_rate": round(tpl.success_rate, 4) if tpl.success_rate is not None else "",
                "updated_at": tpl.updated_at or tpl.created_at,
                "needs_review": "yes" if needs_review else "no",
            }
        )

    return results


def ensure_output_dir() -> Path:
    output_dir = Path("temp") / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def write_report(rows: List[Dict[str, object]]) -> Path:
    output_dir = ensure_output_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"template_quality_{timestamp}.csv"

    if not rows:
        output_path.write_text("No templates found.\n", encoding="utf-8")
        return output_path

    fieldnames = [
        "template_id",
        "platform",
        "data_domain",
        "sub_domain",
        "granularity",
        "account",
        "template_name",
        "version",
        "status",
        "field_count",
        "avg_confidence",
        "median_confidence",
        "low_confidence_count",
        "unmapped_count",
        "invalid_code_count",
        "usage_count",
        "success_rate",
        "updated_at",
        "needs_review",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def summarize(rows: List[Dict[str, object]]) -> None:
    total = len(rows)
    review_needed = sum(1 for row in rows if row["needs_review"] == "yes")
    avg_conf = [
        row["avg_confidence"]
        for row in rows
        if isinstance(row["avg_confidence"], (int, float))
    ]

    safe_print(f"[STATS] Templates analysed: {total}")
    safe_print(f"[STATS] Templates needing review: {review_needed}")
    if avg_conf:
        safe_print(f"[STATS] Average of template averages: {statistics.mean(avg_conf):.4f}")

    if review_needed:
        safe_print("[WARN] Templates flagged for review:")
        for row in rows:
            if row["needs_review"] == "yes":
                safe_print(
                    f"  - ID={row['template_id']} "
                    f"{row['platform']}/{row['data_domain']}/{row['sub_domain'] or '-'} "
                    f"{row['granularity'] or '-'} | status={row['status']} "
                    f"| avg_conf={row['avg_confidence']}"
                )
    else:
        safe_print("[OK] No templates require immediate attention.")


def main() -> None:
    safe_print("[INFO] Analysing field-mapping templates ...")
    db = SessionLocal()
    try:
        valid_codes = load_dictionary_codes(db)
        rows = analyze_templates(db, valid_codes)
        output_path = write_report(rows)
        safe_print(f"[OK] Template quality report created: {output_path}")
        summarize(rows)
    finally:
        db.close()


if __name__ == "__main__":
    main()


