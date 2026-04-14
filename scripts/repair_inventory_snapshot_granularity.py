from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable


def find_repair_candidates(rows: Iterable[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if str(row.get("data_domain") or "").lower() == "inventory"
        and str(row.get("granularity") or "").lower() != "snapshot"
    ]


def _snapshot_name(file_name: str) -> str:
    return file_name.replace("_inventory_monthly_", "_inventory_snapshot_")


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
    args = parser.parse_args()
    mode = "dry-run" if args.dry_run else "apply"
    print(f"repair_inventory_snapshot_granularity: {mode}")


if __name__ == "__main__":
    main()
