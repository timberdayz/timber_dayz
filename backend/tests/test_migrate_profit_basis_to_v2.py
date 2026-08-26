from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).parents[2] / "scripts" / "migrate_profit_basis_to_v2.py"


def load_script():
    spec = importlib.util.spec_from_file_location("migrate_profit_basis_to_v2", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_batch_fingerprint_is_stable_and_changes_with_payload():
    script = load_script()
    payload = {"2026-07": {"basis_rows": 2, "impact": "10.00"}}

    first = script.compute_batch_fingerprint(payload)
    second = script.compute_batch_fingerprint({"2026-07": {"impact": "10.00", "basis_rows": 2}})

    assert first == second
    assert len(first) == 64
    assert first != script.compute_batch_fingerprint({"2026-07": {"basis_rows": 3}})


def test_apply_fails_closed_for_paid_payroll_or_approved_settlement():
    script = load_script()
    report = {
        "months": [
            {
                "period_month": "2026-07",
                "payroll_locked": True,
                "payroll_statuses": ["paid"],
                "settlement_status": "approved",
                "missing_labor_allocation": False,
            }
        ]
    }

    with pytest.raises(script.MigrationSafetyError, match="paid|approved"):
        script.validate_apply_report(report)


def test_protected_history_requires_explicit_admin_migration_context():
    script = load_script()
    report = {
        "months": [
            {
                "period_month": "2026-07",
                "payroll_locked": True,
                "payroll_statuses": ["paid"],
                "settlement_status": "approved",
                "missing_labor_allocation": False,
                "locked_basis_rows": 0,
            }
        ]
    }

    script.validate_apply_report(
        report,
        allow_protected=True,
        migration_batch_id="V2-20260826-001",
        actor_user_id=1,
        reason="统一V2口径历史重算",
    )

    with pytest.raises(script.MigrationSafetyError, match="migration batch"):
        script.validate_apply_report(report, allow_protected=True)


def test_apply_fails_closed_when_labor_allocation_is_missing():
    script = load_script()
    report = {
        "months": [
            {
                "period_month": "2026-08",
                "payroll_locked": False,
                "payroll_statuses": ["draft"],
                "settlement_status": "draft",
                "missing_labor_allocation": True,
            }
        ]
    }

    with pytest.raises(script.MigrationSafetyError, match="labor allocation"):
        script.validate_apply_report(report)


def test_apply_fails_closed_when_profit_basis_snapshot_is_locked():
    script = load_script()
    report = {
        "months": [
            {
                "period_month": "2026-03",
                "payroll_locked": False,
                "payroll_statuses": ["draft"],
                "settlement_status": "draft",
                "locked_basis_rows": 1,
                "missing_labor_allocation": False,
            }
        ]
    }

    with pytest.raises(script.MigrationSafetyError, match="locked profit-basis"):
        script.validate_apply_report(report)


def test_dry_run_does_not_call_write_or_backup(monkeypatch, tmp_path):
    script = load_script()
    calls = []
    monkeypatch.setattr(script, "export_backup", lambda *args, **kwargs: calls.append("backup"))
    monkeypatch.setattr(script, "apply_migration", lambda *args, **kwargs: calls.append("apply"))

    report = {"months": [], "batch_fingerprint": "abc"}
    result = script.run(report=report, apply=False, backup_dir=tmp_path)

    assert result["mode"] == "dry-run"
    assert calls == []


def test_backup_manifest_links_dump_hash_and_batch_fingerprint(tmp_path):
    script = load_script()
    dump = tmp_path / "backup.dump"
    dump.write_bytes(b"postgres backup")

    manifest_path = script.write_backup_manifest(
        dump,
        {"months": [{"period_month": "2026-08"}], "batch_fingerprint": "fingerprint"},
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["backup_file"] == "backup.dump"
    assert manifest["batch_fingerprint"] == "fingerprint"
    assert manifest["backup_sha256"] == hashlib.sha256(b"postgres backup").hexdigest()


def test_sql_contract_contains_expected_sources_and_v2_marker():
    source = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "finance.shop_profit_basis" in source
    assert "finance.employee_labor_cost_allocations" in source
    assert "a_class.payroll_records" in source
    assert "finance.monthly_profit_settlements" in source
    assert "A_PRE_COMMISSION_LABOR_V2" in source
    assert "estimated_profit_basis_impact_amount" in source
    assert "source.id AS basis_id" in source
    assert "IS NOT DISTINCT FROM" in source
    assert "pg_dump" in source
    assert "--allow-protected" in source
    assert "--reopen-protected" in source
    assert "fact_audit_logs" in source
