# 商品中心 SKU 采购价批量录入 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 `sku-reverse-lookup.xlsx` 读取采购价,批量写入 PostgreSQL `core.dim_erp_sku.default_purchase_cost` 及其元数据字段。先本地库验证,后云端库验证。

**Architecture:** 单次执行的 Python 脚本 `scripts/import_purchase_prices.py`(asyncpg + openpyxl),dry-run 默认开,通过 `--apply` 切换真写。脚本接受 `--database-url` 参数,本地库从 `.env` 读,云端库显式覆盖。事务内 UPSERT,失败回滚;执行前先 `CREATE TABLE ... AS SELECT` 做全表快照备份。

**Tech Stack:** Python 3.11+ / asyncpg / openpyxl / pytest / PostgreSQL 15(Docker 本地 + 云端)

---

## 文件结构

| 文件 | 职责 | 创建/修改 |
|---|---|---|
| `scripts/import_purchase_prices.py` | 导入脚本(xlsx 读、过滤、对账、备份、事务写入、验证) | **Create** |
| `scripts/tests/test_import_purchase_prices.py` | 单元测试 + 集成测试(xlsx 解析、对账过滤、CLI 参数解析) | **Create** |
| `scripts/tests/fixtures/sample-lookup-3-rows.xlsx` | 测试用 xlsx fixture | **Create** |
| `output/purchase_price_reconciliation_20260918.csv` | 对账报告(执行时生成) | Runtime output |
| `output/purchase_price_import_dryrun_20260918.csv` | dry-run 预览 | Runtime output |
| `output/purchase_price_import_log_20260918.txt` | 执行日志 | Runtime output |
| `output/purchase_price_sample_check_20260918.csv` | 抽样核对 | Runtime output |
| `core.dim_erp_sku_backup_20260918` | 数据库临时备份表 | Runtime DDL |

---

## 全局约束

1. **数据契约**: 写入字段 = `default_purchase_cost` + `purchase_cost_currency` + `purchase_cost_source` + `purchase_cost_confidence` + `purchase_cost_confirmed_at`;不修改任何其它字段
2. **货币恒为 CNY**,**source 恒为 `妙手导入`**,**confidence 恒为 `medium`**,**confirmed_at 恒为执行时刻 UTC**
3. **跳过规则**: 数字 > 0 写入;数字 = 0 跳过;字符串 `—` (U+2014) 跳过;字符串其它报错退出;空跳过
4. **事务原子性**: 所有 UPDATE 在同一事务,失败自动 ROLLBACK
5. **备份先行**: 真写前必先 `CREATE TABLE core.dim_erp_sku_backup_YYYYMMDD AS SELECT * FROM core.dim_erp_sku`
6. **退出码**: 0 成功 / 1 对账差异(不阻断) / 2 执行错误
7. **本地先、云端后**: 阶段 1 跑本地库验证;阶段 2 需用户 review 后人工触发 `--database-url` 指向云端
8. **不动其它字段**: SPU、品类、售价、规格、状态等一律不改
9. **不改 schema**: 备份表不进 Base.metadata、不进 Alembic
10. **不自动 commit**: 工作区改动留给用户

---

## Task 1: 写脚本骨架 + xlsx 解析 + 过滤逻辑(带测试)

**Files:**
- Create: `scripts/import_purchase_prices.py`
- Create: `scripts/tests/test_import_purchase_prices.py`
- Create: `scripts/tests/fixtures/sample-lookup-3-rows.xlsx`(在 Task 1 步骤 2 用脚本生成)

**Interfaces:**
- Consumes: 无(项目其它部分)
- Produces: 函数 `parse_lookup_xlsx(path: str) -> tuple[list[tuple[str, float]], list[str], list[str]]`
  - 返回 3 元组: (有效条目列表, 跳过的 SKU code 列表, 错误信息列表)

- [ ] **Step 1: 在项目根跑 pytest,确认测试基础设施可用**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp"
python -m pytest scripts/tests/ --collect-only 2>&1 | head -20
```

Expected: "no tests ran" 或 "collected 0 items" (目录可访问)。

- [ ] **Step 2: 生成 fixture xlsx**

```bash
mkdir -p "/f/Vscode/python_programme/AI_code/xihong_erp/scripts/tests/fixtures"
python -X utf8 <<'PY'
import openpyxl
wb = openpyxl.Workbook()
ws = wb.active
ws.title = "SKU反查表"
ws.append(["SKU code", "SPU code", "系列代号", "一级 code", "一级中文", "二级 code", "二级中文", "中文商品名", "采购单价(元)"])
ws.append(["TEST-SKU-001", "XH-TEST-001", "T01", "TOYS_HOBBIES", "玩具爱好", "TOYS_DOLLS_FIGURES", "玩偶手办", "测试商品1", 10.5])
ws.append(["TEST-SKU-002", "XH-TEST-001", "T01", "TOYS_HOBBIES", "玩具爱好", "TOYS_DOLLS_FIGURES", "玩偶手办", "测试商品2", "—"])
ws.append(["TEST-SKU-003", "XH-TEST-002", "T02", "TOOLS_HOME_IMPROVEMENT", "工具家装园艺", "TOOLS_HAND_POWER", "手动与电动工具", "测试商品3", 25.0])
wb.save("/f/Vscode/python_programme/AI_code/xihong_erp/scripts/tests/fixtures/sample-lookup-3-rows.xlsx")
print("[OK] fixture written")
PY
```

Expected: `[OK] fixture written`,无 traceback。

- [ ] **Step 3: 写失败的测试**

`scripts/tests/test_import_purchase_prices.py`:

```python
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
```

- [ ] **Step 4: 跑测试确认失败**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && PYTHONPATH=scripts python -m pytest scripts/tests/test_import_purchase_prices.py -v 2>&1 | tail -20
```

Expected: `ModuleNotFoundError: No module named 'import_purchase_prices'` 或 `ImportError`.

- [ ] **Step 5: 写最小实现** — `scripts/import_purchase_prices.py`:

```python
"""商品中心 SKU 采购价批量录入脚本.

读取 product-catalog skill 的 sku-reverse-lookup.xlsx,批量写入
PostgreSQL core.dim_erp_sku.default_purchase_cost 及其元数据。

详见 docs/superpowers/specs/2026-09-18-purchase-price-import-design.md
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import openpyxl


SHEET_NAME = "SKU反查表"
COL_SKU_CODE = 0  # 第 1 列 (0-indexed)
COL_PRICE = 8     # 第 9 列 (0-indexed)
EM_DASH = "\u2014"
SOURCE_VALUE = "妙手导入"
CONFIDENCE_VALUE = "medium"
CURRENCY_VALUE = "CNY"


@dataclass(frozen=True)
class ParsedRow:
    sku_code: str
    price: float


def parse_lookup_xlsx(path: str) -> tuple[list[tuple[str, float]], list[str], list[str]]:
    """读取 xlsx 并按过滤规则分类.

    Returns:
        (valid, skipped, errors)
        - valid:   [(sku_code, price), ...]   # 价格 > 0 的数字
        - skipped: [sku_code, ...]             # 被跳过的 SKU code(— / 0 / 空)
        - errors:  [message, ...]              # 解析错误信息(字符串型非 — 等)
    """
    valid: list[tuple[str, float]] = []
    skipped: list[str] = []
    errors: list[str] = []

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    if SHEET_NAME not in wb.sheetnames:
        errors.append(f"xlsx 找不到 sheet '{SHEET_NAME}',实际 sheets: {wb.sheetnames}")
        return valid, skipped, errors
    ws = wb[SHEET_NAME]

    rows = ws.iter_rows(values_only=True)
    try:
        header = next(rows)
    except StopIteration:
        errors.append("xlsx 没有表头行")
        return valid, skipped, errors

    if len(header) < 9 or header[COL_SKU_CODE] != "SKU code" or header[COL_PRICE] != "采购单价(元)":
        errors.append(
            f"xlsx 表头不符,期望第1列='SKU code' 第9列='采购单价(元)',实际: {header[:9]}"
        )
        return valid, skipped, errors

    for row in rows:
        if row is None:
            continue
        sku_code = row[COL_SKU_CODE]
        price = row[COL_PRICE]
        if sku_code is None or str(sku_code).strip() == "":
            continue
        sku_code_str = str(sku_code).strip()
        if price is None or (isinstance(price, str) and price.strip() == ""):
            skipped.append(sku_code_str)
            continue
        if isinstance(price, str):
            if price.strip() == EM_DASH:
                skipped.append(sku_code_str)
                continue
            errors.append(f"{sku_code_str}: 价格是字符串 '{price='}' 非数字,且非 — ")
            continue
        if isinstance(price, (int, float)):
            if price <= 0:
                skipped.append(sku_code_str)
                continue
            valid.append((sku_code_str, float(price)))
            continue
        errors.append(f"{sku_code_str}: 价格类型未知 {type(price).__name__}")

    return valid, skipped, errors
```

- [ ] **Step 6: 跑测试确认通过**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && PYTHONPATH=scripts python -m pytest scripts/tests/test_import_purchase_prices.py -v 2>&1 | tail -20
```

Expected: `4 passed in 0.05s` 之类。

---

## Task 2: 对账逻辑(读 DB + 比对 xlsx vs DB)

**Files:**
- Modify: `scripts/import_purchase_prices.py` —— 增加 `reconcile()` 和 DB 连接函数
- Modify: `scripts/tests/test_import_purchase_prices.py` —— 增加对账测试

**Interfaces:**
- Consumes: `parse_lookup_xlsx()` 的输出
- Produces:
  - `async def fetch_db_sku_keys(db_url: str) -> set[str]`
  - `def reconcile(valid: list[tuple[str, float]], db_keys: set[str]) -> tuple[list[tuple[str, float]], list[str], list[str]]`
  - 返回 (matched, lookup_only, db_only)
    - matched: xlsx 有且 DB 也有 → 准备写入
    - lookup_only: xlsx 有但 DB 没有(数据缺失)
    - db_only: DB 有但 xlsx 没有(潜在漏录)

- [ ] **Step 1: 写失败的测试**(对账逻辑不需要 DB,纯函数)

在 `scripts/tests/test_import_purchase_prices.py` 末尾追加:

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && PYTHONPATH=scripts python -m pytest scripts/tests/test_import_purchase_prices.py::test_reconcile_perfect_match -v 2>&1 | tail -10
```

Expected: `AttributeError: module 'import_purchase_prices' has no attribute 'reconcile'`.

- [ ] **Step 3: 追加实现**

在 `scripts/import_purchase_prices.py` 文件尾追加(在 `parse_lookup_xlsx` 函数之后):

```python
async def fetch_db_sku_keys(db_url: str) -> set[str]:
    """从 core.dim_erp_sku 读所有 sku_key."""
    import asyncpg
    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch('SELECT sku_key FROM core.dim_erp_sku')
        return {r["sku_key"] for r in rows if r["sku_key"]}
    finally:
        await conn.close()


def reconcile(
    valid: list[tuple[str, float]],
    db_keys: set[str],
) -> tuple[list[tuple[str, float]], list[str], list[str]]:
    """比对 xlsx 有效条目与 DB sku_key.

    Returns:
        (matched, lookup_only, db_only)
    """
    lookup_keys = {code for code, _ in valid}
    matched = [(code, price) for code, price in valid if code in db_keys]
    lookup_only = sorted(lookup_keys - db_keys)
    db_only = sorted(db_keys - lookup_keys)
    return matched, lookup_only, db_only
```

- [ ] **Step 4: 跑测试确认通过**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && PYTHONPATH=scripts python -m pytest scripts/tests/test_import_purchase_prices.py -v 2>&1 | tail -15
```

Expected: `7 passed`.

---

## Task 3: 备份 + 事务写入(核心:事务原子性 + dry-run / apply 切换)

**Files:**
- Modify: `scripts/import_purchase_prices.py` —— 增加 `apply_update()`, `dry_run_report()`
- Modify: `scripts/tests/test_import_purchase_prices.py` —— 增加 apply 测试(用事务回滚,不真改 DB)

**Interfaces:**
- Produces:
    - `async def create_backup_table(db_url: str, backup_table: str) -> None`
    - `async def apply_update(db_url: str, matched: list[tuple[str, float]], backup_table: str, skip_backup: bool) -> int`
      - 返回成功更新的行数
      - 失败自动 ROLLBACK
    - `def build_update_rows(matched: list[tuple[str, float]], now: datetime) -> list[tuple[str, float, str, str, str, datetime]]`
      - 准备 executemany 的参数

- [ ] **Step 1: 写失败的测试**(纯函数部分 + 集成测试回滚)

追加到 `scripts/tests/test_import_purchase_prices.py`:

```python
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
```

(若项目未安装 pytest-asyncio,可改为手写 `asyncio.run` 调用,见 Step 3 备选方案)

- [ ] **Step 2: 跑测试确认失败**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && PYTHONPATH=scripts python -m pytest scripts/tests/test_import_purchase_prices.py::test_build_update_rows_shape -v 2>&1 | tail -10
```

Expected: `AttributeError: module 'import_purchase_prices' has no attribute 'build_update_rows'`.

- [ ] **Step 3: 追加实现**

在 `scripts/import_purchase_prices.py` 末尾追加:

```python
def build_update_rows(
    matched: list[tuple[str, float]],
    now: datetime,
) -> list[tuple[str, float, str, str, str, datetime]]:
    """把 matched 展开成 executemany 需要的行.

    每行: (sku_key, price, currency, source, confidence, confirmed_at)
    """
    return [
        (sku_code, price, CURRENCY_VALUE, SOURCE_VALUE, CONFIDENCE_VALUE, now)
        for sku_code, price in matched
    ]


async def create_backup_table(db_url: str, backup_table: str) -> None:
    """全表快照备份(覆盖原表前必做)。"""
    import asyncpg
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute(f"DROP TABLE IF EXISTS {backup_table}")
        await conn.execute(
            f"CREATE TABLE {backup_table} AS SELECT * FROM core.dim_erp_sku"
        )
    finally:
        await conn.close()


async def apply_update(
    db_url: str,
    matched: list[tuple[str, float]],
    backup_table: str,
    skip_backup: bool = False,
) -> int:
    """事务内 UPDATE。失败自动 ROLLBACK。返回成功行数."""
    import asyncpg
    if not skip_backup:
        await create_backup_table(db_url, backup_table)

    now = datetime.now(timezone.utc)
    rows = build_update_rows(matched, now)

    conn = await asyncpg.connect(db_url)
    try:
        async with conn.transaction():
                await conn.executemany(
                    """
                    UPDATE core.dim_erp_sku
                    SET default_purchase_cost = $2,
                        purchase_cost_currency = $3,
                        purchase_cost_source = $4,
                        purchase_cost_confidence = $5,
                        purchase_cost_confirmed_at = $6
                    WHERE sku_key = $1
                    """,
                    rows,
                )
    finally:
        await conn.close()
    return len(rows)
```

- [ ] **Step 4: 跑测试确认通过**(纯函数 + 集成回滚测试)

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && PYTHONPATH=scripts python -m pytest scripts/tests/test_import_purchase_prices.py -v 2>&1 | tail -15
```

Expected: 全部通过(若 `pytest-asyncio` 未装,集成测试报"async function not supported",暂时跳过该项,纯函数测试通过即可)。

- [ ] **Step 5: 若 pytest-asyncio 未装,装上**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && pip install pytest-asyncio 2>&1 | tail -5
```

然后在 `scripts/tests/test_import_purchase_prices.py` 顶部加:

```python
import pytest
pytest_plugins = ("pytest_asyncio",)

@pytest.fixture(autouse=True)
def _event_loop():
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
```

---

## Task 4: CLI + 验证查询 + 报告输出(完整可执行入口)

**Files:**
- Modify: `scripts/import_purchase_prices.py` —— 增加 `main()`, `verify_post_state()`, `write_reconciliation_csv()`, `write_dryrun_csv()`, `write_log()`, `write_sample_check()`

**Interfaces:**
- Produces:
  - `async def verify_post_state(db_url: str) -> dict`
    - 返回:`{total, filled, negative, zero, by_source: dict}`
  - `async def sample_check(db_url: str, sample_size: int = 10) -> list[dict]`
    - 返回抽样结果(含 sku_key, current_cost, currency, source, confidence, confirmed_at)
  - `async def run(args: argparse.Namespace) -> int`
    - 入口函数,根据 args.dry_run 决定是否真写

- [ ] **Step 1: 写验证函数测试**

追加:

```python
@pytest.mark.asyncio
async def test_verify_post_state_returns_dict(mod):
    db_url = "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp"
    result = await mod.verify_post_state(db_url)
    assert "total" in result
    assert "filled" in result
    assert "negative" in result
    assert "zero" in result
    assert result["negative"] == 0
    assert result["zero"] == 0
```

- [ ] **Step 2: 跑测试确认失败**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && PYTHONPATH=scripts python -m pytest scripts/tests/test_import_purchase_prices.py::test_verify_post_state_returns_dict -v 2>&1 | tail -10
```

Expected: `AttributeError`.

- [ ] **Step 3: 追加 verify + 报告 + CLI 实现**

```python
async def verify_post_state(db_url: str) -> dict:
    """执行后验证 DB 状态."""
    import asyncpg
    conn = await asyncpg.connect(db_url)
    try:
        total = await conn.fetchval("SELECT COUNT(*) FROM core.dim_erp_sku")
        filled = await conn.fetchval(
            "SELECT COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost IS NOT NULL"
        )
        negative = await conn.fetchval(
            "SELECT COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost < 0"
        )
        zero = await conn.fetchval(
            "SELECT COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost = 0"
        )
        rows = await conn.fetch(
            """SELECT purchase_cost_source, COUNT(*) AS n
               FROM core.dim_erp_sku
               WHERE default_purchase_cost IS NOT NULL
               GROUP BY purchase_cost_source"""
        )
        by_source = {r["purchase_cost_source"]: r["n"] for r in rows}
        return {
            "total": total,
            "filled": filled,
            "negative": negative,
            "zero": zero,
            "by_source": by_source,
        }
    finally:
        await conn.close()


async def sample_check(db_url: str, sample_size: int = 10) -> list[dict]:
    """抽取 N 个有采购价的 SKU 供人工核对."""
    import asyncpg
    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            """SELECT sku_key, default_purchase_cost, purchase_cost_currency,
                      purchase_cost_source, purchase_cost_confidence,
                      purchase_cost_confirmed_at
               FROM core.dim_erp_sku
               WHERE default_purchase_cost IS NOT NULL
               ORDER BY random()
               LIMIT $1""",
            sample_size,
        )
        return [dict(r) for r in rows]
    finally:
        await conn.close()


def write_reconciliation_csv(path: Path, lookup_only: list[str], db_only: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["kind", "sku_code"])
        for code in lookup_only:
            w.writerow(["lookup_only", code])
        for code in db_only:
            w.writerow(["db_only", code])


def write_dryrun_csv(path: Path, matched: list[tuple[str, float]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sku_code", "new_price", "currency", "source", "confidence"])
        for sku_code, price in matched:
            w.writerow([sku_code, price, CURRENCY_VALUE, SOURCE_VALUE, CONFIDENCE_VALUE])


def write_sample_csv(path: Path, samples: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        if not samples:
            return
        w = csv.DictWriter(f, fieldnames=list(samples[0].keys()))
        w.writeheader()
        for s in samples:
            w.writerow(s)


def make_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="商品中心 SKU 采购价批量录入")
    p.add_argument("--xlsx-path", default=r"F:\Work Tool\resource\skills\team-skills\product-catalog\sku-reverse-lookup.xlsx")
    p.add_argument("--database-url", default=None, help="PostgreSQL 连接 URL,默认从 settings.DATABASE_URL 读")
    p.add_argument("--apply", action="store_true", help="真实写入数据库(默认 dry-run)")
    p.add_argument("--skip-backup", action="store_true", help="跳过备份表创建(慎用)")
    p.add_argument("--backup-table", default=None, help="备份表名,默认 core.dim_erp_sku_backup_YYYYMMDD")
    p.add_argument("--output-dir", default="output", help="报告/日志输出目录")
    return p


def _resolve_db_url(arg: str | None) -> str:
    if arg:
        return arg
    # 从 .env 读(简单实现,避免 import 完整 settings)
    from pathlib import Path
    env = Path(".env")
    if env.exists():
        for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("无法从 .env 读 DATABASE_URL,请用 --database-url 显式指定")


async def run(args: argparse.Namespace) -> int:
    """主入口."""
    db_url = _resolve_db_url(args.database_url)
    today = datetime.now().strftime("%Y%m%d")
    backup_table = args.backup_table or f"core.dim_erp_sku_backup_{today}"
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    valid, skipped, errors = parse_lookup_xlsx(args.xlsx_path)
    if errors:
        for e in errors:
            print(f"[ERROR] {e}", file=sys.stderr)
        return 2

    print(f"[INFO] xlsx: {len(valid)} valid, {len(skipped)} skipped (—/0/empty)")

    db_keys = await fetch_db_sku_keys(db_url)
    matched, lookup_only, db_only = reconcile(valid, db_keys)
    print(f"[INFO] reconcile: matched={len(matched)} lookup_only={len(lookup_only)} db_only={len(db_only)}")

    write_reconciliation_csv(output_dir / f"purchase_price_reconciliation_{today}.csv", lookup_only, db_only)
    write_dryrun_csv(output_dir / f"purchase_price_import_dryrun_{today}.csv", matched)

    if not args.apply:
        print("[INFO] dry-run 模式,未写入数据库。带 --apply 真实执行")
        return 1 if (lookup_only or db_only) else 0

    # 真写
    print(f"[INFO] 备份表: {backup_table}")
    count = await apply_update(db_url, matched, backup_table, skip_backup=args.skip_backup)
    print(f"[INFO] 写入完成: {count} 行")

    state = await verify_post_state(db_url)
    print(f"[INFO] post-state: {state}")
    samples = await sample_check(db_url)
    write_sample_csv(output_dir / f"purchase_price_sample_check_{today}.csv", samples)

    return 0 if state["negative"] == 0 and state["zero"] == 0 else 2


def main() -> None:
    args = make_argparser().parse_args()
    code = asyncio.run(run(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 跑全部测试**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && PYTHONPATH=scripts python -m pytest scripts/tests/test_import_purchase_prices.py -v 2>&1 | tail -20
```

Expected: 全部通过。

---

## Task 5: dry-run 执行 + 用户 review

**Files:** 无文件改动(纯执行 + 报告)

**Gate:** 这一步的产物 `output/purchase_price_reconciliation_20260918.csv` 和 `output/purchase_price_import_dryrun_20260918.csv` 必须用户目视确认 OK,才能进入 Task 6。

- [ ] **Step 1: 执行 dry-run**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && PYTHONPATH=scripts python scripts/import_purchase_prices.py 2>&1 | tail -20
```

Expected: 退出码 1(若有对账差异)或 0;打印 `matched=~1085` 数量。

- [ ] **Step 2: 看对账报告**

```bash
ls -la "/f/Vscode/python_programme/AI_code/xihong_erp/output/" | grep "purchase_price"
wc -l "/f/Vscode/python_programme/AI_code/xihong_erp/output/purchase_price_reconciliation_20260918.csv"
head -20 "/f/Vscode/python_programme/AI_code/xihong_erp/output/purchase_price_reconciliation_20260918.csv"
```

Expected: 对账 CSV 存在;若 `lookup_only` 或 `db_only` 非空,人工 review 这 1 条差异是否合理。

- [ ] **Step 3: 看 dryrun 预览**

```bash
head -10 "/f/Vscode/python_programme/AI_code/xihong_erp/output/purchase_price_import_dryrun_20260918.csv"
```

Expected: 表头 + 几行 `(sku_code, new_price, CNY, 妙手导入, medium)`。

- [ ] **Step 4: 用户 review**

**STOP HERE**. 把以下信息呈现给用户:
- dry-run 退出码
- 对账报告行数(`lookup_only` / `db_only` 各几条)
- dry-run 预览首 5 行
- 是否批准进入 Task 6

---

## Task 6: 本地库真写(阶段 1)+ 验证

**Gate:** Task 5 用户批准 + 备份表创建成功

- [ ] **Step 1: 跑 --apply(本地库)**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && PYTHONPATH=scripts python scripts/import_purchase_prices.py --apply 2>&1 | tail -20
```

Expected:
- `[INFO] 备份表: core.dim_erp_sku_backup_20260918`
- `[INFO] 写入完成: NNN 行`
- `[INFO] post-state: {...}`
- 退出码 0

- [ ] **Step 2: 验证 DB 状态**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && python -X utf8 -c "
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
    print('total           :', await c.fetchval('SELECT COUNT(*) FROM core.dim_erp_sku'))
    print('filled          :', await c.fetchval('SELECT COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost IS NOT NULL'))
    print('negative (须0) :', await c.fetchval('SELECT COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost < 0'))
    print('zero (须0)     :', await c.fetchval('SELECT COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost = 0'))
    print('source 分布     :', await c.fetch('SELECT purchase_cost_source, COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost IS NOT NULL GROUP BY purchase_cost_source'))
    print('confidence 分布 :', await c.fetch('SELECT purchase_cost_confidence, COUNT(*) FROM core.dim_erp_sku WHERE default_purchase_cost IS NOT NULL GROUP BY purchase_cost_confidence'))
    print('backup 表存在?  :', await c.fetchval(\"SELECT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname='core' AND tablename='dim_erp_sku_backup_20260918')\"))
    await c.close()
asyncio.run(main())
"
```

- [ ] **Step 3: 抽样 10 条人工对比**

```bash
cat "/f/Vscode/python_programme/AI_code/xihong_erp/output/purchase_price_sample_check_20260918.csv"
```

把抽样的 10 个 SKU 在 xlsx 第 1/9 列人工找一遍,确认 DB 与 xlsx 一致。

- [ ] **Step 4: 备份表保留确认**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && python -X utf8 -c "
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect('postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp')
    n = await c.fetchval('SELECT COUNT(*) FROM core.dim_erp_sku_backup_20260918')
    print(f'备份表行数: {n} (期望与执行前 dim_erp_sku 行数一致,约 1121)')
    await c.close()
asyncio.run(main())
"
```

Expected: 1121 行(执行前的全表快照)。

---

## Task 7: 云端库真写(阶段 2,需用户手动批准)

**Gate:** Task 6 全部通过 + 用户明确批准

**前置确认**:用户需提供云端 DB 连接 URL(或从 `.env` 的 `CLOUD_DATABASE_URL` 读)。连接前用户需确认:
- URL 正确
- DB 名正确(`xihong_erp`)
- 写库权限 OK
- 与本地库表结构一致(同 schema / 同字段)

- [ ] **Step 1: 用户提供云端 URL 后,先做一次连通性测试**

```bash
python -X utf8 -c "
import asyncio, asyncpg
async def main():
    c = await asyncpg.connect('<CLOUD_DATABASE_URL>')
    n = await c.fetchval('SELECT COUNT(*) FROM core.dim_erp_sku')
    print(f'云端 dim_erp_sku 行数: {n} (期望接近 1121)')
    await c.close()
asyncio.run(main())
"
```

Expected: 连接成功,数字与本地接近(±允许业务差异)。

- [ ] **Step 2: 云端 dry-run**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && PYTHONPATH=scripts python scripts/import_purchase_prices.py --database-url "<CLOUD_DATABASE_URL>" 2>&1 | tail -10
```

Expected: 打印云端的 matched/lookup_only/db_only 数量。

- [ ] **Step 3: 把云端对账报告保存到 `output/purchase_price_reconciliation_20260918_cloud.csv`(手工改名或脚本生成)**

- [ ] **Step 4: 用户 review 云端对账后,跑云端 --apply**

```bash
cd "/f/Vscode/python_programme/AI_code/xihong_erp" && PYTHONPATH=scripts python scripts/import_purchase_prices.py --apply --database-url "<CLOUD_DATABASE_URL>" 2>&1 | tail -20
```

Expected:
- 云端备份表创建
- 写入完成
- post-state 正常
- 退出码 0

- [ ] **Step 5: 云端验证**(同 Task 6 Step 2,URL 换为云端)

- [ ] **Step 6: 抽样 10 条云端 vs xlsx 人工对比**

```bash
cat "/f/Vscode/python_programme/AI_code/xihong_erp/output/purchase_price_sample_check_20260918.csv"
```

注意:此 CSV 包含本地库数据。如云端库有差异,需重新抽样。在 Task 7 Step 4 后追加一段一次性脚本抽样云端即可。

---

## 任务依赖图

```
Task 1 (xlsx parse) ──► Task 2 (reconcile) ──► Task 3 (apply) ──► Task 4 (CLI) ──► Task 5 (dry-run)
                                                                                       │
                                                                       ┌───────────────┴───────────────┐
                                                                       ▼                               ▼
                                                              Task 6 (本地 --apply + 验证)       (Task 5 异常需 fix)
                                                                       │
                                                                       ▼
                                                              Task 7 (云端 --apply + 验证)
```

---

## 执行模式

- **Task 1-4**(代码 + 测试):由 subagent 串行执行,每 task 结束跑测试确认
- **Task 5**(dry-run + review):用户 review 后才能进 Task 6
- **Task 6**(本地真写):执行后用户 review 抽样,才能进 Task 7
- **Task 7**(云端真写):用户必须明确批准 + 提供 URL

---

## 自检(对照 spec)

| spec 章节 | 实施任务 |
|---|---|
| §1.1 单次脚本 + 直连 SQL | Task 4 main() 入口 |
| §1.2 成本 ≠ 售价 | 全局约束 #1(只写采购字段) |
| §1.3 本地先、云端后 | Task 6 / Task 7 拆分 |
| §2.1 数据源路径 | Task 4 argparse default |
| §2.2 跳过规则 | Task 1 parse_lookup_xlsx |
| §2.3 字段映射 | Task 3 build_update_rows |
| §3.1 单脚本 + 依赖 | Task 4 |
| §3.2 数据流 | Task 1→2→3→4 |
| §3.3 错误处理 / 退出码 | Task 4 main() |
| §4.1 备份保留 7 天 | Task 6 Step 4 + Task 4 default backup_table |
| §4.2 回滚方式 | 全局约束 #9(备份表留在 core) |
| §5.1 dry-run | Task 4 + Task 5 |
| §5.2 验证查询 | Task 4 verify_post_state + sample_check |
| §6 输出文件 | Task 4 write_*_csv |
| §7.1 CLI | Task 4 make_argparser |
| §7.3 退出码 | Task 4 main() 返回值 |
| §9 不做的事 | 全局约束 #8(不动其它字段) |

无遗漏,无需补充任务。