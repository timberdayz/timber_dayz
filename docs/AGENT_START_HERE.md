# Agent快速上手指南 - v4.12.2

## Current Dashboard Architecture

- PostgreSQL Dashboard is the primary architecture for current dashboard work.
- Current flow: `b_class raw -> semantic -> mart -> api -> backend -> frontend`.
- Use `USE_POSTGRESQL_DASHBOARD_ROUTER=true` when validating the new dashboard path.
- Metabase is now a legacy fallback/debug path only.
- Do not add new dashboard requirements by extending `dashboard_api.py` + `MetabaseQuestionService`.

## Legacy Note

- This file still contains historical DSS/Metabase guidance below.
- When historical sections conflict with the PostgreSQL Dashboard design above, follow the PostgreSQL-first design.

**最后更新**: 2025-11-18  
**系统版本**: v4.12.2  
**架构状态**: ✅ 100% SSOT合规  
**新增**: 🎉 数据同步功能简化 + 降低40%复杂度 + FastAPI BackgroundTasks

---

## 🎯 30秒快速了解

### 系统概况
- **系统**: 现代化跨境电商ERP
- **数据库**: PostgreSQL 15+，约64张表（v4.6.0 DSS架构）
- **架构**: Single Source of Truth（SSOT）+ DSS（决策支持系统）架构
- **标准**: 参考SAP/Oracle ERP设计

### 核心原则（必须遵守）⭐⭐⭐
1. ✅ **SSOT**: 所有ORM模型在`modules/core/db/schema.py`定义
2. ✅ **DSS架构**: Metabase直接查询原始表（fact_raw_data_*），无需物化视图层
3. ❌ **禁止**: 创建新的Base类（`Base = declarative_base()`）
4. ❌ **禁止**: 在schema.py之外定义表
5. ❌ **禁止**: 在业务代码中写复杂SQL（使用Metabase Question）
6. ✅ **验证**: 每次修改后运行`python scripts/verify_architecture_ssot.py`

---

## 🆕 v4.12.2新增内容（必读）⭐⭐⭐

### 数据同步功能简化

**核心理念**: 降低项目复杂度，简化部署流程
- **FastAPI BackgroundTasks**: 数据同步使用FastAPI内置功能（无需Celery Worker）
- **Celery保留**: 仅用于定时任务（告警检查、数据库备份等）
  - ⚠️ 物化视图刷新任务已废弃（v4.6.0 DSS架构）
- **复杂度降低**: 减少40%的复杂度，降低30%的维护成本

**关键改进**:
- ✅ 数据同步无需启动Celery Worker
- ✅ 使用FastAPI BackgroundTasks（内置，无需额外依赖）
- ✅ 保留所有功能（并发控制、数据质量Gate、进度跟踪）
- ✅ 简化部署流程（只需启动FastAPI服务）

**关键文档**: 
- [数据同步简化报告](DATA_SYNC_SIMPLIFICATION_REPORT.md)

**注意事项**:
- ⚠️ 数据同步：使用FastAPI BackgroundTasks（无需Worker）
- ⚠️ 定时任务：仍需要Celery Worker + Beat（必需）

---

## 🆕 v4.11.3新增内容（必读）⭐⭐⭐

### C类数据核心字段优化计划

**核心理念**: 确保C类数据计算的准确性和可靠性
- **17个核心字段**: 定义C类数据计算所需的B类字段（orders域6个、products域8个、inventory域3个）
- **数据质量监控**: 3个API端点监控B类数据完整性和C类数据就绪状态
- **货币策略验证**: 自动验证货币字段是否符合策略（CNY本位币/无货币）

**关键功能**:
- ✅ 核心字段验证脚本（`scripts/verify_c_class_core_fields.py`）
- ✅ 缺失字段自动补充（`scripts/add_c_class_missing_fields.py`）
- ✅ 数据质量监控API（3个端点）
- ✅ 货币策略验证服务（`backend/services/currency_validator.py`）

**关键文档**: 
- [C类数据核心字段定义](C_CLASS_DATA_CORE_FIELDS.md)
- [货币策略文档](CURRENCY_POLICY.md)
- [数据质量保障指南](DATA_QUALITY_GUIDE.md)

---

## 🆕 v4.11.1新增内容（必读）⭐⭐⭐

### 完整数据流程设计

**核心理念**: 三层数据分类架构
- **A类数据**: 用户配置数据（销售战役、目标管理、绩效权重）
- **B类数据**: 业务数据（从Excel采集，需要字段映射）
- **C类数据**: 计算数据（系统自动计算，如达成率、健康度评分）

**数据流程**:
```
用户配置(A类) → 数据采集(B类) → 系统计算(C类) → 前端展示
```

**关键文档**: [核心数据流程设计](CORE_DATA_FLOW.md)

---

## ⚠️ v4.6.0 DSS架构重构（重要）⭐⭐⭐

### DSS架构（决策支持系统）

**核心理念**: Metabase直接查询原始表，无需物化视图层
- **数据存储**: 按data_domain+granularity分表（fact_raw_data_*）
- **数据查询**: Metabase直接查询PostgreSQL原始表
- **KPI计算**: Metabase Question中声明式定义
- **前端展示**: 通过Metabase Question API获取数据，前端自己渲染图表

**关键变更**:
- ⚠️ 物化视图已废弃（v4.6.0 DSS架构重构）
- ⚠️ 旧表（FactOrder, FactOrderItem, FactProductMetric）已废弃，但仍在使用中
- ✅ 新表（fact_raw_data_*）按data_domain+granularity分表存储

**关键文档**: 
- [DSS架构指南](openspec/changes/refactor-backend-to-dss-architecture/proposal.md)

---

## 🆕 v4.9.3新增内容（已废弃）⚠️

### 物化视图语义层架构（v4.6.0已废弃）

**注意**: 此架构已在v4.6.0 DSS架构重构中废弃，Metabase直接查询原始表。

**SSOT位置**:
```
sql/create_all_materialized_views.sql  ← 唯一定义位置
├── 16个物化视图定义
├── 索引定义
├── 刷新函数
└── 依赖管理
```

**严禁行为**:
```sql
-- ❌ 绝对禁止！在业务代码中写复杂SQL！
SELECT p.*, s.shop_name, plat.name 
FROM fact_product_metrics p
JOIN dim_shops s ON p.shop_id = s.shop_id
JOIN dim_platforms plat ON p.platform_code = plat.platform_code
WHERE ...

-- ✅ 正确！使用物化视图！
SELECT * FROM mv_product_management WHERE ...
```

**开发新看板流程**:
1. 检查是否有合适的物化视图（16个中选择）
2. 如果没有，在`sql/create_all_materialized_views.sql`添加新视图
3. 运行`python scripts/create_materialized_views.py`
4. 前端调用`MaterializedViewService`
5. 30分钟完成！

---

## 🔴 绝对禁止（Zero Tolerance）⭐⭐⭐

### 今天的教训（2025-01-30）

**问题**: 字典API返回空数组  
**根源**: `modules/core/db/field_mapping_schema.py`创建了独立Base  
**影响**: 元数据不同步，ORM无法识别version/status字段  
**修复**: 删除重复文件，统一到schema.py

### 永远不要做的事

```python
# ❌ 绝对禁止！永远不要创建新的Base类！
Base = declarative_base()

# ❌ 绝对禁止！永远不要在schema.py之外定义ORM模型！
class MyNewTable(Base):
    __tablename__ = "my_table"

# ❌ 绝对禁止！永远不要在Docker脚本中定义表结构！
# 应该使用Alembic迁移

# ❌ 绝对禁止！永远不要创建backup文件！
# myfile_backup.py, myfile_old.py
# 使用Git版本控制！

# ❌ 绝对禁止！永远不要在API/Service中写复杂SQL！
# 应该使用Metabase Question查询！
# v4.6.0 DSS架构：Metabase直接查询原始表，无需物化视图层
```

### 永远正确的做法

```python
# ✅ 永远从core导入Base和模型
from modules.core.db import Base, FactOrder, DimProduct

# ✅ 需要新表？编辑schema.py，然后Alembic迁移
# 1. 编辑 modules/core/db/schema.py
# 2. 添加到 modules/core/db/__init__.py
# 3. alembic revision --autogenerate -m "add table"
# 4. alembic upgrade head

# ✅ 需要新数据查询？在Metabase中创建Question
# 1. 在Metabase中创建Question（查询fact_raw_data_*表）
# 2. 记录Question ID
# 3. 在.env中配置METABASE_QUESTION_XXX_ID
# 4. 在backend/routers/dashboard_api.py中添加API端点
# 5. 前端通过API获取数据并渲染图表

# ✅ 删除旧文件？先归档
# Move-Item old.py backups/YYYYMMDD_cleanup/

# ✅ 查询产品数据？使用Metabase Question API
# v4.6.0 DSS架构：通过Metabase Question查询fact_raw_data_*表
from backend.services.metabase_question_service import get_metabase_service
service = get_metabase_service()
data = await service.query_question("product_query", params)
```

---

## 📂 系统架构（SSOT + DSS架构）

### 三层架构（v4.6.0 DSS架构）

```
Layer 1: modules/core/ (基础设施)
├── db/
│   ├── schema.py          ⭐ 唯一ORM定义（约64张表）
│   └── __init__.py        导出所有模型
├── config.py              ConfigManager
├── logger.py              ERPLogger
└── exceptions.py          统一异常

Layer 2: backend/ (业务层)
├── services/
│   └── metabase_question_service.py   ⭐ Metabase Question服务（SSOT）
├── routers/               API路由
│   └── dashboard_api.py   Dashboard API（通过Metabase Question查询）
├── models/database.py     engine + SessionLocal + get_db
└── utils/config.py        Settings（后端配置）

Layer 3: frontend/ (UI层)
├── src/api/              API客户端
├── src/stores/           Pinia状态
└── src/views/            Vue组件
```

### 依赖方向（强制）

```
Frontend → Backend API → MetabaseQuestionService → Metabase → PostgreSQL (fact_raw_data_*)
    ↓          ↓                    ↓                  ↓                    ↓
  Vue.js    FastAPI         Python Service      Metabase API        PostgreSQL
```

**禁止**:
- ❌ Frontend直接访问数据库
- ❌ Backend API直接写复杂SQL（应该使用Metabase Question）
- ❌ 跳过Metabase Question Service查询
- ❌ Core依赖Backend
- ❌ 在业务代码中定义ORM模型

**v4.6.0 DSS架构变更**:
- ⚠️ 物化视图层已废弃（不再需要）
- ✅ Metabase直接查询PostgreSQL原始表（fact_raw_data_*）
- ✅ KPI计算在Metabase Question中声明式定义

---

## 🎯 Metabase Question开发规范（v4.6.0 DSS架构）⭐⭐⭐

### 1. 查看现有Question

**在Metabase中查看**:
- 登录Metabase界面
- 查看所有Question列表
- 记录每个Question的ID

**Question ID配置**:
- 在`.env`文件中配置：`METABASE_QUESTION_XXX_ID=1`
- 在`backend/services/metabase_question_service.py`中映射

### 2. 使用现有Question

**步骤**:
1. 确认Question包含需要的字段
2. 在`backend/routers/dashboard_api.py`中添加API端点
3. 调用`MetabaseQuestionService.query_question()`
4. 前端调用API获取数据

**示例**:
```python
# 后端API
from backend.services.metabase_question_service import get_metabase_service

@router.get("/api/dashboard/business-overview/kpi")
async def get_business_overview_kpi(...):
    service = get_metabase_service()
    result = await service.query_question("business_overview_kpi", params)
    return success_response(data=result)
```

### 3. 创建新Question

**何时需要新Question**:
- ✅ 需要新的业务查询
- ✅ 需要新的数据维度组合
- ✅ 需要新的聚合计算

**步骤**:
1. **在Metabase中创建Question**:
   - 登录Metabase界面
   - 选择数据源（PostgreSQL）
   - 选择表（fact_raw_data_*）
   - 构建查询（拖拽式）
   - 保存Question

2. **记录Question ID**:
   - 查看Question URL中的ID
   - 在`.env`中配置：`METABASE_QUESTION_XXX_ID=1`

3. **添加API端点**:
   ```python
   # backend/routers/dashboard_api.py
   @router.get("/api/dashboard/my-new-query")
   async def get_my_new_query(...):
       service = get_metabase_service()
       result = await service.query_question("my_new_query", params)
       return success_response(data=result)
   ```

4. **前端调用**: 通过API获取数据并渲染图表

---

## ⚠️ 物化视图开发规范（v4.9.3，已废弃）⚠️

**注意**: 此规范已在v4.6.0 DSS架构重构中废弃，Metabase直接查询原始表。

**旧规范已归档**: 参见 `backups/20250201_phase6_cleanup/`

---

## 🔧 开发工作流

### 每次开发前（5分钟）

```bash
# 1. 拉取最新代码
git pull

# 2. 检查架构合规
python scripts/verify_architecture_ssot.py
# 期望输出: Compliance Rate: 100.0%

# 3. 检查Metabase连接状态
# 访问 http://localhost:8080 或检查 /api/metabase/health（端口从3000改为8080）

# 4. 阅读最新文档
# - README.md
# - CHANGELOG.md
# - docs/AGENT_START_HERE.md (本文档)
```

### 开发过程中

**添加新功能**:
1. 确认数据来源（fact_raw_data_*表 or Metabase Question）
2. 如需新表：编辑`schema.py` → Alembic迁移
3. 如需新查询：在Metabase中创建Question → 配置Question ID → 添加API端点
4. 实现业务逻辑（Service层）
5. 实现API（Router层）
6. 实现前端（Vue组件）

**修改现有功能**:
1. 找到相关文件（grep/codebase_search）
2. 确认是否影响SSOT
3. 修改并测试
4. 运行验证脚本

### 开发完成后（5分钟）

```bash
# 1. 验证架构合规
python scripts/verify_architecture_ssot.py

# 2. 验证Metabase连接
# 访问 http://localhost:8080 或检查 /api/metabase/health（端口从3000改为8080）

# 3. 清理临时文件
# 移动到 temp/ 或 backups/

# 4. 更新文档
# - CHANGELOG.md
# - 相关MD文档

# 5. Git提交
git add .
git commit -m "feat: add xxx"
```

---

## 📝 检查清单

### 架构理解检查（必须100%理解）
- [ ] 我是否理解了三层架构（Core → Backend → Frontend）？
- [ ] 我是否知道每个文件的唯一定义位置？
- [ ] 我是否了解禁止双维护的原则？
- [ ] **我是否知道Base类只能在schema.py定义？**
- [ ] **我是否知道所有ORM模型只能在schema.py定义？**
- [ ] **我是否知道Metabase Question在Metabase界面中创建？**
- [ ] **我是否知道查询数据应该使用Metabase Question API？**

### 任务分析检查
- [ ] 我要修改的功能在哪一层？
- [ ] 我是否需要创建新文件？（优先修改现有文件）
- [ ] 我要创建的文件是否会与现有文件冲突？
- [ ] **如果要添加新表，我会在schema.py添加并创建Alembic迁移吗？**
- [ ] **如果要添加新查询，我会在Metabase中创建Question吗？**
- [ ] **如果要查询数据，我会使用Metabase Question API吗？**

### 禁止行为检查（零容忍）
- [ ] 我是否会创建新的Base类？（**绝对禁止！**）
- [ ] 我是否会在schema.py之外定义ORM模型？（**绝对禁止！**）
- [ ] 我是否会在业务代码中写复杂SQL？（**应该使用Metabase Question！**）
- [ ] 我是否会在Docker脚本中定义表结构？（**绝对禁止！**）
- [ ] 我是否会创建新的配置类？（只能在core/config.py或backend/config.py）
- [ ] 我是否会创建新的logger文件？（只能在core/logger.py）
- [ ] 我是否会创建*_backup.py、*_old.py文件？（**用Git版本控制！**）

### 正确引用检查
- [ ] 我是否从`modules.core.db`导入模型？
- [ ] 我是否从`modules.core.logger`导入logger？
- [ ] 我是否从正确的位置导入配置？
- [ ] **我是否使用Metabase Question API查询数据？**
- [ ] **验证工具**: `python scripts/verify_architecture_ssot.py`
- [ ] **期望结果**: Compliance Rate: 100.0%

### 开发完成后检查（强制）
- [ ] **运行验证**: `python scripts/verify_architecture_ssot.py`
- [ ] **检查合规**: Compliance Rate = 100%？
- [ ] **Metabase连接**: 检查 `/api/metabase/health`
- [ ] **清理文件**: 临时文件移至temp/或删除
- [ ] **更新文档**: 相关MD文件已更新
- [ ] **更新CHANGELOG**: 重要文件删除/归档必须在CHANGELOG.md记录

---

## 🎯 常见任务快速指南

### 任务1: 开发新数据看板

**需求**: 开发"销售对比看板"

**步骤**:
1. **检查现有Question**: 在Metabase中查看是否已有满足需求的Question
   - 如果满足：直接使用现有Question
   - 如果不满足：继续步骤2

2. **创建新Question**（如需要）:
   - 在Metabase界面中创建Question
   - 选择数据源（PostgreSQL）
   - 选择表（fact_raw_data_*）
   - 构建查询（拖拽式）
   - 保存Question

3. **配置Question ID**:
   ```env
   # .env
   METABASE_QUESTION_SALES_COMPARISON=1
   ```

4. **添加API端点**:
   ```python
   # backend/routers/dashboard_api.py
   @router.get("/api/dashboard/sales-comparison")
   async def get_sales_comparison(...):
       service = get_metabase_service()
       result = await service.query_question("sales_comparison", params)
       return success_response(data=result)
   ```

5. **开发前端**:
   ```vue
   <!-- frontend/src/views/SalesComparison.vue -->
   <template>
     <!-- 图表和数据展示 -->
   </template>
   ```

**预计时间**: 30分钟 - 2小时

---

### 任务2: 添加新数据表

**需求**: 添加"营销活动"表

**步骤**:
1. **编辑schema.py**:
   ```python
   # modules/core/db/schema.py
   class MarketingCampaign(Base):
       __tablename__ = "marketing_campaigns"
       id = Column(Integer, primary_key=True)
       ...
   ```

2. **导出模型**:
   ```python
   # modules/core/db/__init__.py
   from .schema import ..., MarketingCampaign
   __all__ = [..., "MarketingCampaign"]
   ```

3. **创建迁移**:
   ```bash
   alembic revision --autogenerate -m "add marketing_campaigns"
   alembic upgrade head
   ```

4. **验证**:
   ```bash
   python scripts/verify_architecture_ssot.py
   ```

---

### 任务3: 修复bug

**需求**: 产品管理页面显示错误

**步骤**:
1. **定位问题**:
   - 前端错误？查看Vue组件
   - API错误？查看Router和Service
   - 数据错误？查看物化视图和基础表

2. **修复代码**:
   - 如果是Metabase Question问题：在Metabase界面中修改Question
   - 如果是Service问题：修改Service方法
   - 如果是API问题：修改Router

3. **测试**:
   ```bash
   # 验证架构
   python scripts/verify_architecture_ssot.py
   
   # 检查Metabase连接
   # 访问 http://localhost:8080 或检查 /api/metabase/health（端口从3000改为8080）
   ```

---

## 📚 重要文档索引

### 必读文档（开发前）⭐⭐⭐
1. **README.md** - 项目概览
2. **CHANGELOG.md** - 版本历史
3. **docs/AGENT_START_HERE.md** - 本文档
4. **docs/CORE_DATA_FLOW.md** - 核心数据流程设计（A类/B类/C类）⭐新增
5. **openspec/changes/refactor-backend-to-dss-architecture/proposal.md** - DSS架构指南（v4.6.0）⭐新增

### 参考文档（开发中）
1. **docs/ERP_UI_DESIGN_STANDARDS.md** - UI设计标准
2. **docs/FINAL_ARCHITECTURE_STATUS.md** - 架构审计报告
3. **docs/V4_6_0_ARCHITECTURE_GUIDE.md** - v4.6.0 DSS架构指南（如果存在）

### 版本文档（了解历史）
1. **docs/V4_9_3_COMPLETE_FINAL_REPORT.md** - v4.9.3完整报告（已废弃，v4.6.0 DSS架构）
2. **docs/V4_9_SERIES_COMPLETE_SUMMARY.md** - v4.9系列总结（已废弃，v4.6.0 DSS架构）
3. **docs/V4_8_0_MATERIALIZED_VIEW_COMPLETE.md** - 物化视图初次实现（已废弃，v4.6.0 DSS架构）

---

## 🎊 总结

**v4.6.0 DSS架构核心变化**:
- ✅ Metabase直接查询原始表（fact_raw_data_*）
- ✅ 按data_domain+granularity分表存储（最多16张表）
- ✅ KPI计算在Metabase Question中声明式定义
- ✅ 前端通过Metabase Question API获取数据并渲染图表
- ⚠️ 物化视图已废弃（v4.6.0 DSS架构重构）

**开发黄金法则**:
1. **SSOT**: 每个功能只在一处定义
2. **DSS架构**: 数据查询使用Metabase Question
3. **验证**: 每次修改后验证架构合规
4. **文档**: 同步更新相关文档

**记住**:
- ❌ 永远不要创建新的Base类
- ❌ 永远不要在schema.py之外定义表
- ❌ 永远不要在业务代码中写复杂SQL
- ✅ 永远使用Metabase Question API查询数据
- ✅ 永远验证架构合规

---

**准备好了吗？开始开发吧！** 🚀

**有问题？**
1. 阅读文档：`docs/`目录
2. 运行验证：`python scripts/verify_architecture_ssot.py`
3. 检查Metabase：访问 http://localhost:8080 或检查 `/api/metabase/health`（端口从3000改为8080）
