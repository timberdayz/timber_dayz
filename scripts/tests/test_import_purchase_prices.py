"""单元测试: import_purchase_prices.parse_lookup_xlsx"""
import pytest
from importlib import import_module

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