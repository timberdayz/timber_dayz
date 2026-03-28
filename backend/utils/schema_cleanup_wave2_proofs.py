from __future__ import annotations

from pathlib import Path

from modules.core.db import DimShop, EntityAlias, StagingRawData


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATABASE_CONFIG_PATH = PROJECT_ROOT / "backend/models/database.py"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _count_refs(paths: list[Path], literals: list[str]) -> tuple[int, list[str]]:
    total = 0
    matched: list[str] = []
    for path in paths:
        content = _read_text(path)
        count = sum(content.count(literal) for literal in literals)
        if count:
            total += count
            matched.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
    return total, matched


def _search_path_has_public_before_target(target_schema: str) -> bool:
    content = _read_text(DATABASE_CONFIG_PATH)
    marker = "search_path=public,b_class,a_class,c_class,core,finance"
    if marker not in content:
        return False
    order = ["public", "b_class", "a_class", "c_class", "core", "finance"]
    return order.index("public") < order.index(target_schema)


def collect_wave2_candidate_proofs() -> dict[str, dict[str, object]]:
    candidates = {
        "entity_aliases": {
            "expected_target_schema": "b_class",
            "model": EntityAlias,
            "runtime_read_files": [],
            "runtime_write_files": [],
            "historical_target_files": [
                PROJECT_ROOT / "sql/migrate_tables_to_schemas.sql",
                PROJECT_ROOT / "docs/DATABASE_SCHEMA_SEPARATION_GUIDE.md",
                PROJECT_ROOT / "docs/DATABASE_SCHEMA_SEPARATION_TASK_UPDATE.md",
            ],
            "target_literals": ["b_class.entity_aliases", "entity_aliases SET SCHEMA b_class"],
            "risk_level": "medium",
            "blocker_reason": "target schema is documented, but runtime proof is still missing",
        },
        "staging_raw_data": {
            "expected_target_schema": "b_class",
            "model": StagingRawData,
            "runtime_read_files": [],
            "runtime_write_files": [],
            "historical_target_files": [
                PROJECT_ROOT / "sql/migrate_tables_to_schemas.sql",
                PROJECT_ROOT / "docs/DATABASE_SCHEMA_SEPARATION_GUIDE.md",
                PROJECT_ROOT / "docs/DATABASE_SCHEMA_SEPARATION_TASK_UPDATE.md",
            ],
            "target_literals": ["b_class.staging_raw_data", "staging_raw_data SET SCHEMA b_class"],
            "risk_level": "medium",
            "blocker_reason": "target schema is documented, but runtime proof is still missing",
        },
        "dim_shops": {
            "expected_target_schema": "core",
            "model": DimShop,
            "runtime_read_files": [
                PROJECT_ROOT / "backend/routers/hr_commission.py",
                PROJECT_ROOT / "backend/routers/performance_management.py",
                PROJECT_ROOT / "backend/routers/sales_campaign.py",
                PROJECT_ROOT / "backend/routers/target_management.py",
                PROJECT_ROOT / "backend/services/clearance_ranking_service.py",
                PROJECT_ROOT / "backend/services/c_class_data_service.py",
                PROJECT_ROOT / "sql/metabase_questions/business_overview_operational_metrics.sql",
            ],
            "runtime_write_files": [
                PROJECT_ROOT / "backend/services/shop_sync_service.py",
                PROJECT_ROOT / "backend/routers/account_management.py",
                PROJECT_ROOT / "backend/routers/target_management.py",
            ],
            "historical_target_files": [
                PROJECT_ROOT / "docs/COMPLETE_TABLES_MIGRATION_SUMMARY.md",
                PROJECT_ROOT / "docs/DATABASE_TABLE_CLASSIFICATION_RECOMMENDATIONS.md",
            ],
            "target_literals": ["core.dim_shops"],
            "risk_level": "high",
            "blocker_reason": "runtime proof shows live read and write paths, so schema cleanup needs deeper runtime proof first",
        },
    }

    report: dict[str, dict[str, object]] = {}
    for table_name, config in candidates.items():
        model = config["model"]
        model_schema = model.__table__.schema or "public"
        read_count, read_files = _count_refs(config["runtime_read_files"], [table_name, model.__name__, "DimShop" if table_name == "dim_shops" else model.__name__])
        write_count, write_files = _count_refs(config["runtime_write_files"], [table_name, model.__name__, "DimShop(" if table_name == "dim_shops" else model.__name__])
        historical_count, historical_files = _count_refs(config["historical_target_files"], config["target_literals"])

        report[table_name] = {
            "expected_target_schema": config["expected_target_schema"],
            "model_schema": model_schema,
            "model_fullname": model.__table__.fullname,
            "risk_level": config["risk_level"],
            "search_path_public_before_target": _search_path_has_public_before_target(
                config["expected_target_schema"]
            ),
            "runtime_read_file_count": len(read_files),
            "runtime_read_files": read_files,
            "runtime_write_file_count": len(write_files),
            "runtime_write_files": write_files,
            "historical_target_ref_count": historical_count,
            "historical_target_files": historical_files,
            "ready_for_wave2_migration": False,
            "blocker_reason": config["blocker_reason"],
        }

    return report
