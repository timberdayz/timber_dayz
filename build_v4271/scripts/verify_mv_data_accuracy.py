#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Materialized View Quality Checker
---------------------------------

Validates materialized view freshness and basic consistency by comparing
actual row counts with the latest refresh log (`mv_refresh_log`) and by
reporting key metadata such as refresh duration and staleness.

Usage:
    python -m scripts.verify_mv_data_accuracy
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.models.database import SessionLocal


def safe_print(text_value: str) -> None:
    """Print helper compatible with Windows consoles."""
    try:
        print(text_value)
    except UnicodeEncodeError:
        sys.stdout.write(text_value.encode("gbk", errors="ignore").decode("gbk") + "\n")


def ensure_report_dir() -> Path:
    output_dir = Path("temp") / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def fetch_materialized_views(db: Session) -> List[str]:
    """Return a sorted list of materialized views in the public schema."""
    result = db.execute(
        text(
            """
            SELECT matviewname
            FROM pg_matviews
            WHERE schemaname = 'public'
            ORDER BY matviewname
            """
        )
    )
    return [row.matviewname for row in result]


def fetch_refresh_status(db: Session, view_name: str) -> Optional[Dict[str, Any]]:
    """Fetch the latest refresh status for a materialized view."""
    result = db.execute(
        text("SELECT * FROM get_mv_refresh_status(:view_name)"),
        {"view_name": view_name},
    ).mappings().first()

    if result is None:
        return None

    return dict(result)


def analyse_view(db: Session, view_name: str) -> Dict[str, Any]:
    """Collect statistics for a single materialized view."""
    try:
        row_count = db.execute(text(f'SELECT COUNT(*) FROM "{view_name}"')).scalar()
    except Exception as exc:  # noqa: BLE001
        return {
            "view_name": view_name,
            "error": str(exc),
        }

    refresh_status = fetch_refresh_status(db, view_name)

    row_count_logged = refresh_status.get("row_count") if refresh_status else None
    duration_seconds = refresh_status.get("duration_seconds") if refresh_status else None
    last_refresh = refresh_status.get("last_refresh") if refresh_status else None
    refresh_status_label = refresh_status.get("refresh_status") if refresh_status else "unknown"
    age_minutes = refresh_status.get("age_minutes") if refresh_status else None

    row_count_delta = None
    if row_count_logged is not None:
        row_count_delta = row_count - row_count_logged

    return {
        "view_name": view_name,
        "row_count": row_count,
        "logged_row_count": row_count_logged,
        "row_count_delta": row_count_delta,
        "last_refresh": last_refresh.isoformat() if isinstance(last_refresh, datetime) else last_refresh,
        "refresh_status": refresh_status_label,
        "duration_seconds": duration_seconds,
        "age_minutes": age_minutes,
    }


def write_report(rows: List[Dict[str, Any]]) -> Path:
    output_dir = ensure_report_dir()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"mv_quality_{timestamp}.csv"

    fieldnames = [
        "view_name",
        "row_count",
        "logged_row_count",
        "row_count_delta",
        "last_refresh",
        "refresh_status",
        "duration_seconds",
        "age_minutes",
        "error",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return output_path


def summarise(rows: List[Dict[str, Any]]) -> None:
    total = len(rows)
    errors = [row for row in rows if row.get("error")]
    stale = [row for row in rows if row.get("age_minutes") and row["age_minutes"] > 180]  # 3小时阈值
    mismatched = [
        row
        for row in rows
        if row.get("row_count_delta") not in (None, 0)
    ]

    safe_print(f"[STATS] 物化视图数量: {total}")
    safe_print(f"[STATS] 刷新失败/读取异常: {len(errors)}")
    safe_print(f"[STATS] 3小时未刷新: {len(stale)}")
    safe_print(f"[STATS] 行数差异: {len(mismatched)}")

    if errors:
        safe_print("[WARN] 下列视图读取失败:")
        for row in errors:
            safe_print(f"  - {row['view_name']}: {row.get('error')}")

    if stale:
        safe_print("[WARN] 下列视图长时间未刷新 (>180分钟):")
        for row in stale:
            safe_print(
                f"  - {row['view_name']} (age={row['age_minutes']}分钟, last_refresh={row.get('last_refresh')})"
            )

    if mismatched:
        safe_print("[WARN] 下列视图行数与刷新日志不一致:")
        for row in mismatched:
            safe_print(
                f"  - {row['view_name']}: 实际={row.get('row_count')} "
                f"日志={row.get('logged_row_count')} Δ={row.get('row_count_delta')}"
            )


def main() -> None:
    safe_print("[INFO] 开始检查物化视图数据质量 ...")
    db = SessionLocal()

    try:
        view_names = fetch_materialized_views(db)
        if not view_names:
            safe_print("[WARN] 未发现物化视图")
            return

        results: List[Dict[str, Any]] = []
        for name in view_names:
            stats = analyse_view(db, name)
            results.append(stats)

        output_path = write_report(results)
        safe_print(f"[OK] 物化视图质量报告: {output_path}")
        summarise(results)
    finally:
        db.close()


if __name__ == "__main__":
    main()


