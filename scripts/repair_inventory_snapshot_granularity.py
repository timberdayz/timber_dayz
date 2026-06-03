from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Iterable

from sqlalchemy import create_engine, text


def find_repair_candidates(rows: Iterable[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if str(row.get("data_domain") or "").lower() == "inventory"
        and str(row.get("granularity") or "").lower() != "snapshot"
    ]


def _snapshot_name(file_name: str) -> str:
    target = file_name
    for token in ("monthly", "weekly", "daily"):
        target = target.replace(f"_inventory_{token}_", "_inventory_snapshot_")
    return target


def repair_inventory_record(row: dict, *, apply_changes: bool = False) -> dict:
    updated = dict(row)
    original_path = Path(str(row["file_path"]))
    target_name = _snapshot_name(str(row["file_name"]))
    target_path = original_path.with_name(target_name)
    meta_path = original_path.with_suffix(".meta.json")
    target_meta_path = target_path.with_suffix(".meta.json")

    updated["granularity"] = "snapshot"
    updated["file_name"] = target_name
    updated["file_path"] = str(target_path)
    updated["meta_file_path"] = str(target_meta_path)

    if not apply_changes:
        return updated

    if original_path.exists():
        original_path.rename(target_path)

    if meta_path.exists():
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
        payload.setdefault("business_metadata", {})
        payload["business_metadata"]["granularity"] = "snapshot"
        target_meta_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if target_meta_path != meta_path and meta_path.exists():
            meta_path.unlink()

    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair inventory records written with non-snapshot granularity.")
    parser.add_argument("--dry-run", action="store_true", help="Only print intended changes.")
    parser.add_argument("--apply", action="store_true", help="Apply changes to files and catalog_files rows.")
    args = parser.parse_args()
    apply_changes = bool(args.apply and not args.dry_run)
    mode = "apply" if apply_changes else "dry-run"
    print(f"repair_inventory_snapshot_granularity: {mode}")

    url = os.getenv("DATABASE_URL", "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp")
    engine = create_engine(url)
    updated_rows = []

    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, file_name, file_path, data_domain, granularity
                FROM public.catalog_files
                WHERE data_domain = 'inventory' AND granularity <> 'snapshot'
                ORDER BY id
                """
            )
        ).mappings().all()

        candidates = find_repair_candidates(rows)
        print(f"repair candidates: {len(candidates)}")

        for row in candidates:
            fixed = repair_inventory_record(dict(row), apply_changes=apply_changes)
            updated_rows.append(fixed)
            print(
                f"id={row['id']} {row['file_name']} -> {fixed['file_name']} "
                f"({row['granularity']} -> {fixed['granularity']})"
            )

            if apply_changes:
                conn.execute(
                    text(
                        """
                        UPDATE public.catalog_files
                        SET file_name = :file_name,
                            file_path = :file_path,
                            granularity = :granularity
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": row["id"],
                        "file_name": fixed["file_name"],
                        "file_path": fixed["file_path"],
                        "granularity": fixed["granularity"],
                    },
                )

    print(f"updated rows: {len(updated_rows)}")


if __name__ == "__main__":
    main()
