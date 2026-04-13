from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = ROOT / "migrations" / "versions"


def test_training_migration_chain_files_exist():
    expected = {
        "20260412_add_training_management_tables.py",
        "20260413_merge_training_heads.py",
        "20260413_add_training_feishu_integration.py",
    }

    actual = {path.name for path in VERSIONS_DIR.glob("*.py")}

    missing = expected - actual
    assert not missing, f"missing training migration files: {sorted(missing)}"
