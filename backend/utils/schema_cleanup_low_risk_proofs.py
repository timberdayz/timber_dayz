from __future__ import annotations

from pathlib import Path

from modules.core.db import PerformanceConfig, SalesCampaign, SalesCampaignShop, TargetBreakdown


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _count_literal_refs(paths: list[Path], literal: str) -> tuple[int, list[str]]:
    matched_files: list[str] = []
    total = 0
    for path in paths:
        content = _read_text(path)
        count = content.count(literal)
        if count:
            matched_files.append(str(path.relative_to(PROJECT_ROOT)).replace("\\", "/"))
            total += count
    return total, matched_files


def collect_low_risk_candidate_proofs() -> dict[str, dict[str, object]]:
    candidates = {
        "performance_config": {
            "expected_target_schema": "a_class",
            "model": PerformanceConfig,
            "runtime_files": [
                PROJECT_ROOT / "backend/routers/performance_management.py",
            ],
        },
        "sales_campaigns": {
            "expected_target_schema": "a_class",
            "model": SalesCampaign,
            "runtime_files": [
                PROJECT_ROOT / "backend/routers/sales_campaign.py",
                PROJECT_ROOT / "backend/services/sales_campaign_service.py",
            ],
        },
        "sales_campaign_shops": {
            "expected_target_schema": "a_class",
            "model": SalesCampaignShop,
            "runtime_files": [
                PROJECT_ROOT / "backend/routers/sales_campaign.py",
                PROJECT_ROOT / "backend/services/sales_campaign_service.py",
            ],
        },
        "target_breakdown": {
            "expected_target_schema": "a_class",
            "model": TargetBreakdown,
            "runtime_files": [
                PROJECT_ROOT / "backend/routers/target_management.py",
                PROJECT_ROOT / "backend/routers/performance_management.py",
                PROJECT_ROOT / "backend/services/postgresql_dashboard_service.py",
                PROJECT_ROOT / "backend/services/target_sync_service.py",
                PROJECT_ROOT / "sql/api_modules/business_overview_shop_racing_module.sql",
            ],
        },
    }

    report: dict[str, dict[str, object]] = {}
    for table_name, config in candidates.items():
        model = config["model"]
        expected_target_schema = config["expected_target_schema"]
        runtime_files = config["runtime_files"]
        model_schema = model.__table__.schema or "public"
        model_fullname = model.__table__.fullname

        target_literal = f"{expected_target_schema}.{table_name}"
        public_literal = f"public.{table_name}"
        target_refs, target_files = _count_literal_refs(runtime_files, target_literal)
        public_refs, public_files = _count_literal_refs(runtime_files, public_literal)

        ready_for_wave1 = model_schema == expected_target_schema and public_refs == 0
        blocker_reason = ""
        if not ready_for_wave1:
            blocker_reason = (
                f"model schema is {model_schema}, expected {expected_target_schema}; "
                "cleanup would be unsafe before ORM/runtime alignment"
            )

        report[table_name] = {
            "expected_target_schema": expected_target_schema,
            "model_schema": model_schema,
            "model_fullname": model_fullname,
            "runtime_files": [str(path.relative_to(PROJECT_ROOT)).replace("\\", "/") for path in runtime_files],
            "target_schema_sql_refs": target_refs,
            "target_schema_files": target_files,
            "public_schema_sql_refs": public_refs,
            "public_schema_files": public_files,
            "ready_for_wave1": ready_for_wave1,
            "blocker_reason": blocker_reason,
        }

    return report
