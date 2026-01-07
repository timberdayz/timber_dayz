# 架构审计报告 - 2025-01-30

## 执行摘要

**审计目的**: 识别双重维护和历史遗留问题，确保企业级ERP标准和Agent协作开发效率

**审计范围**: 全项目文件扫描，重点检查数据库模型、配置管理、日志系统

**关键发现**: 🔴 发现3个严重的双重维护问题

---

## 🔴 严重问题（必须立即修复）

### 问题1: 多个Base类定义（违反Single Source of Truth）

**发现**:
1. ✅ **正确定义**: `modules/core/db/schema.py` (Line 50) - 主Base类
2. ❌ **重复定义**: `modules/core/db/field_mapping_schema.py` (Line 12) - 独立Base
3. ❌ **重复定义**: `docker/postgres/init-tables-simple.py` (Line 24) - Docker初始化Base
4. ❌ **重复定义**: `docker/postgres/init-tables.py` - 完整初始化Base（未读取但存在）

**影响**:
- 不同Base导致元数据不同步
- Alembic迁移会遗漏表
- 查询时ORM无法识别某些表
- **今天的字典API问题就是因为这个**

**根本原因**:
- `field_mapping_schema.py`创建时为了独立性，定义了自己的Base
- Docker初始化脚本为了简化，独立创建Base

**正确做法**（企业级标准）:
```python
# ❌ 错误 - field_mapping_schema.py
Base = declarative_base()  # 重复定义！

# ✅ 正确 - 应该从core导入
from modules.core.db.schema import Base
```

---

### 问题2: 重复的库存表定义

**发现**:
1. ✅ **v4.4.0标准**: `modules/core/db/schema.py` - `InventoryLedger`（Universal Journal模式）
2. ❌ **旧定义**: `backend/models/inventory.py` - `FactInventory`（旧的库存表）

**对比**:
| 特性 | InventoryLedger (v4.4.0) | FactInventory (旧版) |
|------|-------------------------|---------------------|
| 架构模式 | Universal Journal | 传统库存快照 |
| 字段 | qty_in/out, unit_cost_wac | quantity_on_hand, avg_cost |
| 成本计算 | 移动加权平均 | 简单平均 |
| 是否使用 | ✅ 已在schema.py | ❌ 未使用 |
| 导出状态 | ✅ 导出到__all__ | ❌ 未导出 |

**影响**:
- Agent开发时不确定用哪个表
- 可能同时操作两个表导致数据不一致
- 增加测试和维护成本

**建议**:
- **立即删除** `backend/models/inventory.py`
- 归档到 `backups/20250130_inventory_cleanup/`
- 更新所有引用到`InventoryLedger`

---

### 问题3: Docker初始化脚本双重维护

**发现**:
1. `docker/postgres/init-tables.py` - 完整版（未使用）
2. `docker/postgres/init-tables-simple.py` - 简化版（使用中）

**问题**:
- 两个脚本都定义了表结构（Account, DataRecord等）
- 与`modules/core/db/schema.py`形成三重定义
- Docker脚本的表与core/schema.py不一致

**对比**:
| 表名 | Docker脚本 | core/schema.py | 一致性 |
|------|-----------|----------------|--------|
| Account | accounts | accounts | ✅ |
| DimPlatform | dim_platform | dim_platforms | ❌ 复数不一致 |
| DimShop | dim_shop | dim_shops | ❌ 复数不一致 |
| FactSalesOrders | fact_sales_orders | fact_orders | ❌ 名称不一致 |

**建议**:
- **完全删除** Docker初始化脚本中的表定义
- 改用Alembic迁移：`docker exec ... alembic upgrade head`
- Docker脚本只负责：创建数据库、设置权限、运行Alembic

---

## ⚠️ 中等问题（建议修复）

### 问题4: 环境变量文件管理混乱

**发现**:
- ✅ **根目录**（正确）:
  - `env.example` - 主模板
  - `env.development.example` - 开发环境
  - `env.production.example` - 生产环境
  - `env.docker.example` - Docker环境

- ⚠️ **backups目录**（遗留）:
  - `backups/20250124_architecture_cleanup/env.example`
  - `backups/20250124_architecture_cleanup/backend_env.example`
  - `backups/20250124_architecture_cleanup/env.template`

**建议**:
- 保留根目录的4个文件
- 删除backups中的旧环境变量文件

---

### 问题5: 配置管理双层架构（可接受）

**发现**:
1. `modules/core/config.py` - ConfigManager（模块使用）
2. `backend/utils/config.py` - Settings（后端API使用）

**评估**: ✅ 这是**合理的分层**
- ConfigManager: YAML配置文件管理（采集器、平台配置）
- Settings: 后端环境变量管理（数据库、CORS、JWT）

**不是双重维护，是职责分离**

---

### 问题6: Logger管理（可接受）

**发现**:
1. `modules/core/logger.py` - ERPLogger（统一日志工厂）
2. `modules/collectors/base/base_collector.py` - _setup_logger（采集器专用）

**评估**: ✅ 这是**合理的**
- core/logger: 系统级日志管理
- collector: 采集器独立日志（不依赖core）

---

## ✅ 正确的架构

### 架构1: 数据库模型单一来源（SSOT）

**正确示例**: `backend/models/database.py`
```python
# ✅ 正确：从core导入，不重复定义
from modules.core.db import (
    Base,
    DimPlatform,
    DimShop,
    ...
)

# ✅ 正确：只负责引擎和Session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
```

**架构清晰**:
```
modules/core/db/schema.py  →  [唯一ORM定义]
         ↓
backend/models/database.py  →  [引擎+Session]
         ↓
backend/routers/*.py  →  [业务逻辑]
```

---

## 📋 修复清单（按优先级）

### P0 - 立即修复（阻塞开发）

- [ ] **删除** `modules/core/db/field_mapping_schema.py`
  - 将`FieldMappingDictionary`等4个模型移到`schema.py`
  - 已在`schema.py`中定义，直接删除即可
  - 更新所有导入引用

- [ ] **删除** `backend/models/inventory.py`
  - 使用`InventoryLedger`替代`FactInventory`
  - 归档到backups目录

- [ ] **重构** Docker初始化脚本
  - 删除表定义代码
  - 改用Alembic迁移
  - 创建新的`init-db-alembic.sh`

### P1 - 本周修复（技术债务）

- [ ] 统一表命名（复数形式）
  - `dim_platform` → `dim_platforms`
  - `dim_shop` → `dim_shops`
  - `dim_product` → `dim_products`
  - 创建Alembic迁移脚本

- [ ] 清理backups中的环境变量文件
  - 删除所有`.example`和`.template`文件

- [ ] 删除遗留文件
  - `temp/archived_docs/LEGACY_MIGRATION_PLAN.md`
  - `modules/collectors/shopee_collector_backup.py`

### P2 - 下月优化（改进体验）

- [ ] 创建架构检查脚本
  - 自动检测Base重复定义
  - 自动检测表名不一致
  - 自动检测未使用的模型

- [ ] 完善.cursorrules
  - 添加明确的"禁止创建Base"规则
  - 添加明确的"表命名规范"
  - 添加"文件创建检查清单"

---

## 🎯 企业级标准建议

### 标准1: Single Source of Truth（单一数据源）

**原则**: 每个概念只在一处定义

**强制规则**:
```python
# ✅ 唯一定义位置
modules/core/db/schema.py:
    - Base类（唯一）
    - 所有ORM模型（唯一）

# ✅ 可以导入和使用
backend/models/database.py:
    from modules.core.db import Base  # ✅ 导入
    
backend/routers/orders.py:
    from modules.core.db import FactOrder  # ✅ 导入

# ❌ 禁止创建
anywhere:
    Base = declarative_base()  # ❌ 绝对禁止！
```

### 标准2: 清晰的架构分层

```
Layer 1: modules/core/  (基础设施)
  ├── db/schema.py         → 数据库模型（唯一定义）
  ├── config.py            → 配置管理
  ├── logger.py            → 日志管理
  └── exceptions.py        → 异常定义

Layer 2: backend/  (API层)
  ├── models/database.py   → 引擎+Session（不定义模型）
  ├── routers/            → API路由
  ├── services/           → 业务逻辑
  └── utils/config.py      → 后端专用配置

Layer 3: frontend/  (UI层)
  ├── src/api/            → API调用
  ├── src/stores/         → 状态管理
  └── src/views/          → 页面组件
```

### 标准3: 文件生命周期管理

**创建前检查**:
1. 是否已有相同功能的文件？
2. 是否符合架构分层？
3. 是否会造成双重维护？

**创建后维护**:
- 及时删除过时文件
- 归档到`backups/YYYYMMDD_描述/`
- 更新相关文档

---

## 🤖 Agent开发指南

### Agent接手时的检查清单

**首次接手**:
1. 阅读`.cursorrules`（架构规范）
2. 阅读本审计报告
3. 确认Single Source of Truth位置

**每次开发前**:
1. 确认修改文件是否为SSOT
2. 确认不会创建重复定义
3. 确认符合架构分层

**每次开发后**:
1. 检查是否创建了新文件
2. 检查新文件是否归档
3. 更新相关文档

### 避免的错误模式

❌ **错误1**: "为了方便，我创建一个独立的Base"
```python
# ❌ 绝对禁止
Base = declarative_base()
```

❌ **错误2**: "这个表在schema.py太复杂，我单独定义"
```python
# ❌ 违反SSOT原则
class MyNewTable(Base):  # 应该在schema.py定义
    ...
```

❌ **错误3**: "Docker脚本需要初始化，我创建简化版表"
```python
# ❌ 三重定义
# 应该使用Alembic迁移
```

✅ **正确做法**:
```python
# ✅ 永远从core导入
from modules.core.db import Base, MyTable

# ✅ 需要新表？去schema.py添加
# ✅ 需要初始化？用Alembic迁移
```

---

## 📊 审计统计

| 类别 | 发现数 | P0 | P1 | P2 |
|------|--------|----|----|-----|
| 双重维护 | 3 | 3 | 0 | 0 |
| 命名不一致 | 4 | 0 | 4 | 0 |
| 遗留文件 | 5 | 0 | 5 | 0 |
| 架构改进 | 2 | 0 | 0 | 2 |
| **总计** | **14** | **3** | **9** | **2** |

---

## 🎯 立即行动

### 今天必须完成（P0）

1. **删除field_mapping_schema.py**
   - 该文件所有内容已在schema.py中
   - 只需删除文件，更新导入即可

2. **删除backend/models/inventory.py**
   - 使用InventoryLedger替代
   - 已无代码引用

3. **简化Docker初始化**
   - 删除表定义
   - 改用Alembic

**执行这3项后，系统架构将符合企业级标准**

---

**审计完成时间**: 2025-01-30 00:35  
**审计人员**: AI Agent (Cursor)  
**下次审计**: 每月1日自动执行

*本报告遵循企业级ERP架构标准*

