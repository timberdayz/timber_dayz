import importlib.util
from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[3]
SCRIPT_PATH = ROOT_DIR / "scripts" / "ensure_b_class_compat.py"


def load_script_module():
    if not SCRIPT_PATH.exists():
        raise FileNotFoundError(f"Missing compatibility script: {SCRIPT_PATH}")

    spec = importlib.util.spec_from_file_location("ensure_b_class_compat", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_compat_script_extracts_expected_b_class_table_names():
    script = load_script_module()
    sql_text = """
    SELECT * FROM b_class.fact_shopee_orders_daily
    UNION ALL
    SELECT * FROM b_class.fact_tiktok_orders_weekly
    """
    names = script.extract_b_class_table_names(sql_text)
    assert names == {"fact_shopee_orders_daily", "fact_tiktok_orders_weekly"}


def test_compat_script_declares_default_raw_columns():
    script = load_script_module()
    columns = script.DEFAULT_RAW_TABLE_COLUMNS
    assert "platform_code VARCHAR(32) NOT NULL" in columns
    assert "raw_data JSONB NOT NULL" in columns
    assert "data_hash VARCHAR(64) NOT NULL" in columns
