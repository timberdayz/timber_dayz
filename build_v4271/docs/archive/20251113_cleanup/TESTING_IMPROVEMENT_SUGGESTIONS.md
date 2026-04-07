# 测试改进建议文档

**创建日期**: 2025-11-05  
**适用版本**: v4.6.2+  
**测试标准**: 企业级测试金字塔（单元70% + 集成20% + E2E10%）

---

## 当前状态

**测试文件**: 4个（backend/tests/）
- batch_import_test.py
- concurrent_test.py
- stability_test.py
- test_performance.py

**缺失的测试**:
- 单元测试: 0%
- API集成测试: 0%
- 前端E2E测试: 0%

---

## 1. 单元测试建议（目标80%覆盖率）

### 1.1 核心服务测试（P0 - 紧急）

**data_validator测试**:
```python
# tests/unit/test_data_validator.py
import pytest
from backend.services.data_validator_v2 import validate_product_metrics

def test_validate_success():
    rows = [{
        "platform_code": "shopee",
        "shop_id": "test",
        "platform_sku": "SKU001",
        "metric_date": "2025-01-01"
    }]
    result = validate_product_metrics(rows)
    assert result["valid_count"] == 1
    assert result["error_count"] == 0
```

**data_importer测试**:
```python
# tests/unit/test_data_importer.py
def test_bulk_insert():
    rows = [...]
    result = bulk_insert_orders(rows, db)
    assert result["imported"] > 0
```

---

## 2. API集成测试（目标70%覆盖率）

### 2.1 字段映射API测试（P0 - 紧急）

```python
# tests/integration/test_field_mapping_api.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_get_field_dictionary():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/field-mapping/dictionary/fields")
        assert response.status_code == 200
        data = response.json()
        assert "fields" in data

@pytest.mark.asyncio
async def test_suggest_mappings():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/api/field-mapping/suggest-mappings",
            json={
                "columns": ["订单号", "销售额"],
                "domain": "orders"
            }
        )
        assert response.status_code == 200
```

---

## 3. E2E测试（目标50%关键流程）

### 3.1 字段映射完整流程（P1 - 重要）

**使用Playwright**:
```python
# tests/e2e/test_field_mapping_flow.py
from playwright.sync_api import sync_playwright

def test_field_mapping_complete_flow():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        # 1. 登录
        page.goto("http://localhost:5173")
        page.fill("#username", "admin")
        page.fill("#password", "password")
        page.click("button[type=submit]")
        
        # 2. 打开字段映射
        page.click("text=字段映射")
        
        # 3. 选择文件
        page.set_input_files("#file-input", "test.xlsx")
        
        # 4. 预览数据
        page.click("text=预览数据")
        page.wait_for_selector(".preview-table")
        
        # 5. 确认入库
        page.click("text=确认入库")
        page.wait_for_selector("text=入库成功")
        
        browser.close()
```

---

## 4. 测试工具配置

### 4.1 pytest配置

```ini
# pytest.ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    --cov=backend
    --cov-report=html
    --cov-report=term
    --verbose
```

### 4.2 覆盖率配置

```ini
# .coveragerc
[run]
source = backend
omit = 
    */tests/*
    */migrations/*
    */__pycache__/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise NotImplementedError
```

---

## 5. 实施计划

**第1周（核心服务）**:
- [ ] data_validator单元测试
- [ ] data_importer单元测试
- [ ] currency_converter单元测试

**第2周（API测试）**:
- [ ] 字段映射API集成测试
- [ ] 数据入库API集成测试
- [ ] 数据看板API集成测试

**第3-4周（E2E测试）**:
- [ ] 字段映射完整流程
- [ ] 数据采集完整流程
- [ ] 产品管理完整流程

---

## 6. 验收标准

- 核心服务覆盖率 ≥ 80%
- API路由覆盖率 ≥ 70%
- 关键流程E2E测试通过
- CI自动测试集成

---

**最后更新**: 2025-11-05

