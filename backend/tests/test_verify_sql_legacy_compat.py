from pathlib import Path

import pytest

from scripts.verify_sql_legacy_compat import verify_sql_legacy_compat


def test_verify_sql_legacy_compat_flags_offending_changed_sql(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sql_root = tmp_path / "sql" / "api_modules"
    sql_root.mkdir(parents=True)
    sql_file = sql_root / "offender.sql"
    sql_file.write_text('SELECT COALESCE("营销费用", 0) FROM foo;\n', encoding="utf-8")
    changed_files = tmp_path / "changed_files.txt"
    changed_files.write_text("sql/api_modules/offender.sql\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    with pytest.raises(RuntimeError, match="offender.sql"):
        verify_sql_legacy_compat(changed_files)


def test_verify_sql_legacy_compat_ignores_unchanged_sql_when_changed_list_is_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql_root = tmp_path / "sql" / "api_modules"
    sql_root.mkdir(parents=True)
    unchanged_file = sql_root / "legacy.sql"
    unchanged_file.write_text('SELECT COALESCE("营销费用", 0) FROM foo;\n', encoding="utf-8")
    changed_file = sql_root / "safe.sql"
    changed_file.write_text("SELECT 1;\n", encoding="utf-8")
    changed_files = tmp_path / "changed_files.txt"
    changed_files.write_text("sql/api_modules/safe.sql\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    assert verify_sql_legacy_compat(changed_files) is True


def test_verify_sql_legacy_compat_skips_when_changed_list_has_no_sql_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    changed_files = tmp_path / "changed_files.txt"
    changed_files.write_text("README.md\nfrontend/src/App.vue\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)

    assert verify_sql_legacy_compat(changed_files) is True
