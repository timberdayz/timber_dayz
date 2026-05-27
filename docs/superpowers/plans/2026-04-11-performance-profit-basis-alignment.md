# Performance Profit Basis Alignment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align employee performance and commission calculation with store performance results and the formal monthly `profit_basis_amount` snapshot.

**Architecture:** Keep monthly settlement as a downstream consumer. Update `HRIncomeCalculationService` so employee commissions read `finance.shop_profit_basis` first and employee performance scores inherit assigned store performance from `c_class.performance_scores`, with a compatibility fallback to weighted sales achievement when store performance is missing.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, pytest, existing HR/finance services

---

### Task 1: Lock Service Behavior With Tests

**Files:**
- Modify: `backend/tests/test_hr_income_calculation_service.py`
- Test: `backend/tests/test_hr_income_calculation_service.py`

- [ ] **Step 1: Write a failing test for snapshot-first profit basis loading**

```python
def test_calculate_month_prefers_shop_profit_basis_snapshot():
    ...
    assert result["commission_upserts"] == 1
    assert service._load_profit_basis_by_shop(...) uses snapshot rows before rebuild fallback
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_hr_income_calculation_service.py -k snapshot -q`
Expected: FAIL because the service still rebuilds profit basis directly.

- [ ] **Step 3: Write a failing test for employee performance inheriting store performance**

```python
def test_calculate_month_employee_performance_uses_store_total_score():
    ...
    assert perf.performance_score == pytest.approx(weighted_store_score)
    assert perf.achievement_rate == pytest.approx(weighted_sales_achievement)
```

- [ ] **Step 4: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_hr_income_calculation_service.py -k "store_total_score or snapshot" -q`
Expected: FAIL because the current service still sets `performance_score` from weighted achievement only.

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_hr_income_calculation_service.py
git commit -m "test: lock hr income alignment behavior"
```

### Task 2: Implement Snapshot-First Profit Basis Loading

**Files:**
- Modify: `backend/services/hr_income_calculation_service.py`
- Modify: `backend/services/profit_basis_service.py` (only if a helper extraction materially simplifies reuse)
- Test: `backend/tests/test_hr_income_calculation_service.py`

- [ ] **Step 1: Add snapshot-first loading logic**

Implement an internal loader that:
- queries `ShopProfitBasis` for the target month
- keys rows by `platform_code + shop_id`
- only falls back to `ProfitBasisService.build_profit_basis()` for shops missing from the snapshot

- [ ] **Step 2: Run targeted tests**

Run: `python -m pytest backend/tests/test_hr_income_calculation_service.py -k snapshot -q`
Expected: PASS

- [ ] **Step 3: Keep commission formula unchanged**

Ensure the formula remains:

```python
alloc_profit = profit_basis_amount * allocatable_profit_rate
commission_amount += alloc_profit * commission_ratio
```

- [ ] **Step 4: Run the full HR income service test file**

Run: `python -m pytest backend/tests/test_hr_income_calculation_service.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/hr_income_calculation_service.py backend/tests/test_hr_income_calculation_service.py
git commit -m "feat: use profit basis snapshots for hr income"
```

### Task 3: Implement Store-Performance-Driven Employee Performance

**Files:**
- Modify: `backend/services/hr_income_calculation_service.py`
- Modify: `backend/tests/test_hr_income_calculation_service.py`
- Modify: `backend/domains/business/routers/performance_management.py` (only if a small read-path adjustment is needed)

- [ ] **Step 1: Load assigned store performance rows inside HR income calculation**

Add a month-scoped loader for `PerformanceScore` keyed by `platform_code + shop_id`.

- [ ] **Step 2: Compute employee performance score from assigned store scores**

Use:
- store weight = store sales target from `score_details.sales.target`
- fallback weight = assigned store monthly sales
- final fallback = equal weight

Compatibility rule:
- if a store performance row exists and has a complete `total_score`, use it
- otherwise fallback to the existing weighted achievement-rate logic for that store

- [ ] **Step 3: Preserve employee `actual_sales` and `achievement_rate` fields**

Keep:
- `actual_sales` = weighted sales share aggregation
- `achievement_rate` = weighted sales achievement

Change only:
- `performance_score` = weighted employee store performance score

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest backend/tests/test_hr_income_calculation_service.py -k "store_total_score or calculate_month_upsert_writes" -q`
Expected: PASS

- [ ] **Step 5: Run acceptance coverage touching the orchestration route**

Run: `python -m pytest backend/tests/test_add_performance_income_acceptance.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/services/hr_income_calculation_service.py backend/tests/test_hr_income_calculation_service.py backend/tests/test_add_performance_income_acceptance.py
git commit -m "feat: derive employee performance from store performance"
```

### Task 4: Verify Downstream Compatibility

**Files:**
- Inspect: `backend/services/payroll_generation_service.py`
- Inspect: `backend/domains/business/routers/hr_commission.py`
- Inspect: `frontend/src/domains/business/views/hr/PerformanceManagement.vue`

- [ ] **Step 1: Verify payroll still consumes the same fields**

Run:

```bash
python -m pytest backend/tests/test_payroll_generation_service.py -q
```

Expected: PASS because payroll still reads `EmployeePerformance.performance_score` and `EmployeeCommission.commission_amount`.

- [ ] **Step 2: Verify HR commission and performance read APIs still pass**

Run:

```bash
python -m pytest backend/tests/test_hr_commission_profit_basis_routes.py backend/tests/test_performance_management_person_fallback.py -q
```

Expected: PASS

- [ ] **Step 3: Manually review person-group display assumptions**

Confirm that the current person-group UI can continue to display:
- `actual_sales`
- weighted sales achievement
- employee `performance_score`

- [ ] **Step 4: Commit**

```bash
git add backend/services/hr_income_calculation_service.py backend/tests/test_hr_commission_profit_basis_routes.py
git commit -m "test: verify downstream hr compatibility"
```

### Task 5: Final Verification And Notes

**Files:**
- Modify: `progress.md`
- Modify: `findings.md`

- [ ] **Step 1: Run the final verification batch**

Run:

```bash
python -m pytest backend/tests/test_hr_income_calculation_service.py backend/tests/test_add_performance_income_acceptance.py backend/tests/test_payroll_generation_service.py backend/tests/test_hr_commission_profit_basis_routes.py backend/tests/test_performance_management_person_fallback.py -q
```

Expected: PASS

- [ ] **Step 2: Record implementation notes**

Document:
- employee performance now inherits store performance
- HR commission now prefers `shop_profit_basis`
- remaining future work: personal add/subtract items and performance coefficient governance

- [ ] **Step 3: Commit**

```bash
git add progress.md findings.md
git commit -m "docs: record performance and profit basis alignment"
```

