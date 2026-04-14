from __future__ import annotations

import json
from pathlib import Path


def test_repair_script_targets_only_inventory_records_with_non_snapshot_granularity():
    from scripts.repair_inventory_snapshot_granularity import find_repair_candidates

    rows = [
        {"id": 1, "data_domain": "inventory", "granularity": "monthly"},
        {"id": 2, "data_domain": "inventory", "granularity": "snapshot"},
        {"id": 3, "data_domain": "orders", "granularity": "monthly"},
    ]

    candidates = find_repair_candidates(rows)

    assert [row["id"] for row in candidates] == [1]


def test_repair_script_updates_file_name_meta_and_catalog_record(tmp_path):
    from scripts.repair_inventory_snapshot_granularity import repair_inventory_record

    raw_dir = tmp_path / "data" / "raw" / "2026"
    raw_dir.mkdir(parents=True, exist_ok=True)

    wrong_file = raw_dir / "miaoshou_inventory_monthly_20260413_232430.xls"
    wrong_file.write_text("demo", encoding="utf-8")

    meta_path = wrong_file.with_suffix(".meta.json")
    meta_path.write_text(
        json.dumps(
            {
                "business_metadata": {
                    "source_platform": "miaoshou",
                    "data_domain": "inventory",
                    "granularity": "monthly",
                },
                "collection_info": {"method": "python_component"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    row = {
        "id": 1,
        "file_name": wrong_file.name,
        "file_path": str(wrong_file),
        "data_domain": "inventory",
        "granularity": "monthly",
    }

    repaired = repair_inventory_record(row, apply_changes=True)

    assert repaired["granularity"] == "snapshot"
    assert repaired["file_name"] == "miaoshou_inventory_snapshot_20260413_232430.xls"
    assert Path(repaired["file_path"]).exists()
    assert not wrong_file.exists()

    saved_meta = json.loads(Path(repaired["meta_file_path"]).read_text(encoding="utf-8"))
    assert saved_meta["business_metadata"]["granularity"] == "snapshot"
