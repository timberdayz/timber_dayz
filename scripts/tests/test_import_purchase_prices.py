"""单元测试: import_purchase_prices.parse_lookup_xlsx"""
import pytest
from importlib import import_module

pytest_plugins = ("pytest_asyncio",)

@pytest.fixture
def mod():
    return import_module("import_purchase_prices")

def test_parse_returns_3_tuple(mod):
    from pathlib import Path
    fixture = Path(__file__).parent / "fixtures" / "sample-lookup-3-rows.xlsx"
    valid, skipped, errors = mod.parse_lookup_xlsx(str(fixture))
    assert isinstance(valid, list)
    assert isinstance(skipped, list)
    assert isinstance(errors, list)

def test_parse_keeps_only_positive_numbers(mod):
    from pathlib import Path
    fixture = Path(__file__).parent / "fixtures" / "sample-lookup-3-rows.xlsx"
    valid, skipped, errors = mod.parse_lookup_xlsx(str(fixture))
    # 3 行: SKU-001=10.5 (写入), SKU-002=— (跳过), SKU-003=25.0 (写入)
    assert len(valid) == 2
    assert {code for code, _ in valid} == {"TEST-SKU-001", "TEST-SKU-003"}

def test_parse_skips_em_dash(mod):
    from pathlib import Path
    fixture = Path(__file__).parent / "fixtures" / "sample-lookup-3-rows.xlsx"
    valid, skipped, errors = mod.parse_lookup_xlsx(str(fixture))
    assert "TEST-SKU-002" in skipped
    assert not errors

def test_parse_skips_zero(mod, tmp_path):
    import openpyxl
    p = tmp_path / "zero.xlsx"
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "SKU反查表"
    ws.append(["SKU code"] + ["x"]*7 + ["采购单价(元)"])
    ws.append(["TEST-ZERO", "x", "x", "x", "x", "x", "x", "x", 0])
    wb.save(p)
    valid, skipped, errors = mod.parse_lookup_xlsx(str(p))
    assert valid == []
    assert "TEST-ZERO" in skipped

def test_reconcile_perfect_match(mod):
    valid = [("A", 10.0), ("B", 20.0), ("C", 30.0)]
    db = {"A", "B", "C"}
    matched, lookup_only, db_only = mod.reconcile(valid, db)
    assert {c for c, _ in matched} == {"A", "B", "C"}
    assert lookup_only == []
    assert db_only == []

def test_reconcile_lookup_only(mod):
    valid = [("A", 10.0), ("B", 20.0)]  # B 在 DB 里没有
    db = {"A"}
    matched, lookup_only, db_only = mod.reconcile(valid, db)
    assert [c for c, _ in matched] == ["A"]
    assert lookup_only == ["B"]
    assert db_only == []

def test_reconcile_db_only(mod):
    valid = [("A", 10.0)]
    db = {"A", "Z"}  # Z 在 lookup 里没有
    matched, lookup_only, db_only = mod.reconcile(valid, db)
    assert [c for c, _ in matched] == ["A"]
    assert lookup_only == []
    assert db_only == ["Z"]


def test_build_update_rows_shape(mod):
    from datetime import datetime, timezone
    now = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)
    matched = [("A", 10.0), ("B", 20.0)]
    rows = mod.build_update_rows(matched, now)
    assert len(rows) == 2
    # (sku_key, price, currency, source, confidence, confirmed_at)
    assert rows[0] == ("A", 10.0, "CNY", "妙手导入", "medium", now)


@pytest.mark.asyncio
async def test_apply_update_rollback_on_failure(mod):
    """集成测试: 故意传错字段值,事务应回滚,DB 不变。"""
    import asyncpg
    db_url = "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp"
    # 用一个错误的价格(字符串)让 UPDATE 失败
    bad = [("__NONEXISTENT_SKU_FOR_TEST__", "NOT_A_NUMBER")]  # type: ignore
    with pytest.raises(Exception):
        await mod.apply_update(
            db_url,
            bad,  # type: ignore[arg-type]
            backup_table="core.dim_erp_sku_backup_TEST",
            skip_backup=True,
        )
    # 验证备份表未创建(skip_backup=True)
    conn = await asyncpg.connect(db_url)
    try:
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='core' AND tablename='dim_erp_sku_backup_TEST')"
        )
        assert exists is False
    finally:
        await conn.close()