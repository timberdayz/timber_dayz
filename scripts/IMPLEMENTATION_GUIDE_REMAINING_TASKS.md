# 剩余任务实施指南

**创建日期**: 2025-11-05  
**剩余任务**: 3个（FX转换、Redis缓存、单元测试）  
**预计工作量**: 24小时

---

## 任务1: FX转换服务集成（P1）

**工作量**: 4小时  
**优先级**: 重要

### 待修复位置（9处）

#### 文件: backend/routers/finance.py

**位置**: 第632行
```python
# 当前代码
base_amt=amount,  # TODO: FX转换

# 修复为
from backend.services.currency_converter import CurrencyConverter
converter = CurrencyConverter(db)
base_amt = await converter.convert_single(amount, currency, 'CNY', expense_date)
```

#### 文件: backend/routers/procurement.py

**位置1**: 第78行
```python
# 修复为
from backend.services.currency_converter import CurrencyConverter
converter = CurrencyConverter(db)
base_amt = await converter.convert_single(total_amt, currency, 'CNY', po_date)
```

**位置2-3**: 第110行、第424行
类似修复方案

### 简化方案（推荐）

创建同步FX转换辅助函数：

```python
# backend/utils/fx_helper.py
from sqlalchemy import select
from modules.core.db import DimExchangeRate
from decimal import Decimal

def simple_convert_to_cny(
    amount: Decimal,
    from_currency: str,
    rate_date: date,
    db: Session
) -> Decimal:
    """
    简化的CNY转换（同步版本）
    
    从dim_exchange_rates表查询汇率
    """
    if from_currency == 'CNY':
        return amount
    
    # 查询汇率
    rate_record = db.execute(
        select(DimExchangeRate).where(
            and_(
                DimExchangeRate.from_currency == from_currency,
                DimExchangeRate.to_currency == 'CNY',
                DimExchangeRate.rate_date <= rate_date
            )
        ).order_by(DimExchangeRate.rate_date.desc()).limit(1)
    ).scalar_one_or_none()
    
    if rate_record:
        return amount * Decimal(str(rate_record.rate))
    else:
        # 找不到汇率，记录警告并返回原值
        logger.warning(f"汇率未找到: {from_currency} -> CNY on {rate_date}")
        return amount  # 或返回None
```

然后在各处TODO调用：
```python
base_amt = simple_convert_to_cny(amount, currency, date, db)
```

---

## 任务2: Redis缓存策略（P1）

**工作量**: 4小时  
**优先级**: 重要

### 步骤1: 安装依赖

```bash
pip install redis aioredis fastapi-cache2
```

### 步骤2: 配置Redis连接

```python
# backend/utils/redis_client.py
from redis import asyncio as aioredis
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

async def init_redis():
    redis = aioredis.from_url(
        "redis://localhost",
        encoding="utf8",
        decode_responses=True
    )
    FastAPICache.init(RedisBackend(redis), prefix="xihong-erp:")
    return redis
```

### 步骤3: 集成到main.py

```python
# backend/main.py - lifespan函数中
async def lifespan(app: FastAPI):
    # 启动时
    from backend.utils.redis_client import init_redis
    try:
        await init_redis()
        logger.info("[OK] Redis缓存已启用")
    except Exception as e:
        logger.warning(f"[SKIP] Redis缓存未启用: {e}")
    
    yield
    # 关闭时...
```

### 步骤4: 应用缓存

```python
# backend/routers/field_mapping_dictionary.py
from fastapi_cache.decorator import cache

@router.get("/fields")
@cache(expire=3600)  # 1小时缓存
async def get_field_dictionary(...):
    pass
```

### 缓存策略

| API端点 | 缓存时间 | 更新策略 |
|---------|---------|---------|
| /field-mapping/dictionary/fields | 1小时 | 手动更新时清除 |
| /dashboard/overview | 5分钟 | 定时刷新 |
| /exchange-rates | 24小时 | 每日凌晨刷新 |

---

## 任务3: 单元测试（P2）

**工作量**: 12小时  
**优先级**: 建议

### 测试框架配置

```bash
# 已安装的依赖
pytest==7.4.3
pytest-asyncio==0.21.1

# 需要新增
pip install pytest-cov coverage
```

### 测试结构

```
tests/
├── __init__.py
├── conftest.py  # pytest配置和fixtures
├── unit/
│   ├── test_data_validator.py
│   ├── test_data_importer.py
│   ├── test_currency_converter.py
│   └── test_pattern_matcher.py
├── integration/
│   ├── test_field_mapping_api.py
│   ├── test_product_api.py
│   └── test_auth_api.py
└── e2e/
    └── test_field_mapping_flow.py
```

### 单元测试示例

```python
# tests/unit/test_data_validator.py
import pytest
from backend.services.data_validator_v2 import validate_product_metrics

def test_validate_success():
    """测试验证通过场景"""
    rows = [{
        "platform_code": "shopee",
        "shop_id": "test",
        "platform_sku": "SKU001",
        "metric_date": "2025-01-01"
    }]
    result = validate_product_metrics(rows)
    assert result["valid_count"] == 1
    assert result["error_count"] == 0

def test_validate_missing_required():
    """测试缺少必填字段"""
    rows = [{"platform_code": "shopee"}]
    result = validate_product_metrics(rows)
    assert result["error_count"] > 0

def test_validate_invalid_date():
    """测试无效日期"""
    rows = [{
        "platform_code": "shopee",
        "shop_id": "test",
        "platform_sku": "SKU001",
        "metric_date": "invalid-date"
    }]
    result = validate_product_metrics(rows)
    assert len(result["errors"]) > 0
```

### 运行测试

```bash
# 运行所有测试
pytest

# 运行并生成覆盖率报告
pytest --cov=backend --cov-report=html --cov-report=term

# 运行特定测试
pytest tests/unit/test_data_validator.py -v

# 查看覆盖率报告
open htmlcov/index.html
```

### 覆盖率目标

- 核心服务（data_validator, data_importer）: ≥80%
- API路由（routers/）: ≥70%
- 工具函数（utils/）: ≥60%

---

## 执行顺序建议

### 阶段1: 快速改进（已完成）✅
- [x] JWT密钥检查
- [x] 环境标识
- [x] 数据隔离区重新处理
- [x] 数据库索引
- [x] IP/User-Agent获取

### 阶段2: FX转换（下次会话）
- [ ] 创建simple_convert_to_cny辅助函数
- [ ] 修复9处TODO位置
- [ ] 测试FX转换功能

### 阶段3: Redis缓存（下次会话）
- [ ] 启动Redis服务
- [ ] 安装依赖
- [ ] 集成缓存中间件
- [ ] 应用到关键API

### 阶段4: 单元测试（持续）
- [ ] 配置pytest
- [ ] 编写核心服务测试
- [ ] 编写API集成测试
- [ ] 达到80%覆盖率

---

## 当前完成度

**总任务**: 9个  
**已完成**: 5个（56%）  
**剩余**: 4个

**已完成**:
- ✅ P0: JWT密钥检查
- ✅ P0: API速率限制（代码已准备，需安装依赖）
- ✅ P0: 数据隔离区重新处理
- ✅ P1: 数据库索引
- ✅ P2: IP/User-Agent获取

**待完成**:
- ⏳ P1: FX转换（4小时）
- ⏳ P1: Redis缓存（4小时）
- ⏳ P2: 单元测试（12小时）

---

**建议**: 先验证已完成的改动，再分批执行剩余任务

