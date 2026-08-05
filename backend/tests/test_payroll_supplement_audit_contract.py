from pathlib import Path

from backend.schemas.hr import PayrollRecordManualUpdate
from modules.core.db import PayrollRecord


def test_payroll_record_supports_auditable_next_month_supplements():
    payload = PayrollRecordManualUpdate(
        overtime_pay=120,
        backfill_source_month="2025-07",
        backfill_note="补录上月加班",
    )

    assert payload.backfill_source_month == "2025-07"
    assert payload.backfill_note == "补录上月加班"
    assert "backfill_source_month" in PayrollRecord.__table__.c
    assert "backfill_note" in PayrollRecord.__table__.c

    migration = Path("migrations/versions/20260805_add_payroll_backfill_audit_fields.py")
    source = migration.read_text(encoding="utf-8")
    assert 'revision = "20260805_payroll_backfill_audit"' in source
    assert 'down_revision = "20260804_employee_labor_cost_allocations"' in source
    assert '"backfill_source_month"' in source
    assert '"backfill_note"' in source
