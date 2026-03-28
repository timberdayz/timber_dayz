from pathlib import Path

from modules.services.data_validator import DataValidator
from modules.services.mapping_engine import SmartMappingEngine


def test_data_validator_shop_foreign_key_targets_core_dim_shops():
    validator = DataValidator()

    assert validator.validation_rules["foreign_keys"]["shop_id"]["table"] == "core.dim_shops"


def test_mapping_engine_shop_foreign_key_pattern_targets_core_dim_shops():
    engine = SmartMappingEngine()

    assert engine.foreign_key_patterns["shop_id"]["target_table"] == "core.dim_shops"


def test_data_management_center_uses_core_dim_shops_for_overview_counts():
    source = Path("modules/apps/data_management_center/app.py").read_text(encoding="utf-8", errors="ignore")

    assert '_count("core.dim_shops")' in source
    assert '_count("dim_shops")' not in source


def test_operational_metrics_sql_qualifies_core_dim_shops():
    source = Path("sql/metabase_questions/business_overview_operational_metrics.sql").read_text(
        encoding="utf-8",
        errors="ignore",
    )

    assert "FROM core.dim_shops ds" in source
    assert "FROM dim_shops ds" not in source
