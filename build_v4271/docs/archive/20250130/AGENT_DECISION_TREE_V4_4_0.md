# Agent开发决策树 v4.4.0

**目标**: 避免双维护、架构混乱，确保Agent快速找到正确的修改位置

---

## 🎯 我要做什么？请选择场景

### 场景A：我要修改/新增数据库表

#### ✅ 唯一修改位置
- **文件**: `modules/core/db/schema.py`
- **规则**: 全部ORM模型只在此定义，其他地方只导入

#### 🚫 禁止的行为
- ❌ 在 `backend/models/` 创建新模型
- ❌ 创建 `_v2`、`_new`、`_temp` 等后缀表
- ❌ 重复定义Base类

#### 📋 检查清单
```python
# 1. 先检查是否已存在类似表
grep -r "class.*Expense" modules/core/db/schema.py

# 2. 如果已存在 → 扩展现有表
# 3. 如果不存在 → 新建，但要明确前缀：
#    - dim_xxx (维度表)
#    - fact_xxx (事实表)
#    - gl_xxx (总账)
#    - po_xxx (采购)
#    - grn_xxx (入库)

# 4. 更新导出
# 编辑 modules/core/db/__init__.py，添加到__all__
```

---

### 场景B：我要添加API接口

#### ✅ 决策树

```
我要添加什么API？
├─ 字段辞典CRUD → backend/routers/field_mapping_dictionary.py (复用)
├─ 采购/PO/GRN → backend/routers/procurement.py (新建已完成)
├─ 费用/P&L/汇率 → backend/routers/finance.py (扩展)
├─ 库存分析 → backend/routers/inventory.py (扩展)
├─ 销售分析 → backend/routers/dashboard_api.py (扩展)
└─ 其他新域 → backend/routers/{新域}.py (新建)
```

#### 🚫 禁止的行为
- ❌ 创建 `/api/xxx_v2/` 路由
- ❌ 在多个router中重复定义相同API
- ❌ 绕过 `backend/routers/` 直接在service暴露API

#### 📋 检查清单
```bash
# 1. 先检查是否已有相关API
grep -r "router.post.*expenses" backend/routers/

# 2. 如果已存在 → 扩展现有router
# 3. 如果不存在 → 新建router，并注册到main.py

# 4. 注册到main.py
# 编辑 backend/main.py
from backend.routers import xxx
app.include_router(xxx.router, prefix="/api/xxx", tags=["xxx"])
```

---

### 场景C：我要添加前端页面

#### ✅ 决策树

```
我要添加什么页面？
├─ 费用管理 → frontend/src/views/FinanceManagement.vue (新建已完成)
├─ 采购管理 → frontend/src/views/ProcurementManagement.vue (待新建)
├─ 字段映射 → frontend/src/views/FieldMappingEnhanced.vue (复用)
├─ 看板类 → frontend/src/views/{Domain}Dashboard.vue
└─ 其他 → frontend/src/views/{Module}.vue
```

#### 📋 检查清单
```bash
# 1. 检查是否已有页面
ls frontend/src/views/ | grep -i finance

# 2. 如果已存在 → 扩展现有页面
# 3. 如果不存在 → 新建，并注册路由

# 4. 注册路由
# 编辑 frontend/src/router/index.js
{
  path: '/xxx',
  name: 'Xxx',
  component: () => import('../views/Xxx.vue'),
  meta: { title: 'xxx', roles: [...] }
}
```

---

### 场景D：我要初始化种子数据

#### ✅ 决策树

```
我要初始化什么数据？
├─ 字段辞典 → scripts/init_field_mapping_dictionary.py (复用+扩展)
├─ 财务域辞典 → scripts/seed_finance_dictionary.py (新建已完成)
├─ 计算指标 → scripts/seed_finance_dictionary.py (已包含)
└─ 历史数据迁移 → scripts/migrate_historical_data.py (待新建)
```

#### 🚫 禁止的行为
- ❌ 创建 `init_xxx_v2.py`
- ❌ 重复初始化相同数据（检查是否已存在）

#### 📋 检查清单
```bash
# 1. 检查现有脚本
ls scripts/ | grep -E "init|seed"

# 2. 如果已有相关脚本 → 扩展现有脚本
# 3. 如果无 → 新建，命名规范：
#    - init_xxx.py (初始化表结构)
#    - seed_xxx.py (种子数据)

# 4. 在脚本中检查重复
existing = db.query(Model).filter_by(key=value).first()
if existing:
    print(f"[SKIP] {value} already exists")
    continue
```

---

## 🔍 常见Agent任务速查

### 任务1：新增费用类型

```
1. 确认位置：
   ✅ 方式A（推荐）：前端在线新增
      财务管理 → 字段映射 → 新增标准字段
   
   ✅ 方式B：后端脚本
      编辑 scripts/seed_finance_dictionary.py
      增加字段到expense_fields列表
      运行 python scripts/seed_finance_dictionary.py

2. 验证：
   GET /api/field-mapping/dictionary?data_domain=finance
   应该看到新增的字段

3. 使用：
   立即可用于费用导入的字段映射
```

### 任务2：创建采购订单

```
1. API调用：
   POST /api/procurement/po/create
   {
     "vendor_code": "V001",
     "po_date": "2025-01-29",
     "lines": [...]
   }

2. 数据流：
   po_headers (创建) → po_lines (创建) → 审批 → grn_headers → 
   grn_lines → inventory_ledger (过账)

3. 相关文件：
   - 后端：backend/routers/procurement.py
   - 模型：modules/core/db/schema.py (POHeader, POLine, ...)
   - 前端：frontend/src/views/ProcurementManagement.vue (待创建)
```

### 任务3：查询店铺P&L

```
1. API调用：
   GET /api/finance/pnl/shop?period_month=2025-01&shop_id=sg_3c

2. 数据源：
   mv_pnl_shop_month (物化视图)
   ├─ 收入：mv_sales_day_shop_sku
   ├─ 成本：inventory_ledger (movement_type='sale')
   └─ 费用：fact_expenses_allocated

3. 相关文件：
   - 后端：backend/routers/finance.py
   - SQL：sql/create_finance_materialized_views.sql
   - 前端：frontend/src/views/FinanceManagement.vue (Tab: P&L月报)
```

### 任务4：修正库存差异

```
1. 查找差异：
   SELECT 
       il.platform_sku,
       SUM(il.qty_in - il.qty_out) as ledger_qty,
       fpm.stock as snapshot_qty
   FROM inventory_ledger il
   LEFT JOIN fact_product_metrics fpm ON (
       il.platform_sku = fpm.platform_sku AND
       fpm.metric_date = CURRENT_DATE
   )
   GROUP BY il.platform_sku, fpm.stock
   HAVING SUM(il.qty_in - il.qty_out) != COALESCE(fpm.stock, 0);

2. 修正方式：
   方式A：调整库存流水（插入adjustment类型）
   INSERT INTO inventory_ledger (movement_type, qty_in, ...)
   VALUES ('adjustment', variance_qty, ...);
   
   方式B：刷新快照视图
   REFRESH MATERIALIZED VIEW mv_inventory_snapshot_day;

3. 相关文件：
   - 模型：modules/core/db/schema.py (InventoryLedger)
   - 后端：backend/routers/inventory.py
```

---

## 🧭 文件导航速查

### 核心架构文件（必读）

| 文件 | 用途 | 修改频率 |
|------|------|---------|
| `modules/core/db/schema.py` | 所有ORM模型 | 新表/扩展字段时 |
| `modules/core/db/__init__.py` | 模型导出 | 新增模型后 |
| `backend/routers/` | 所有API路由 | 新增API时 |
| `backend/main.py` | API注册 | 新增router后 |
| `frontend/src/router/index.js` | 前端路由 | 新增页面后 |

### v4.4.0新增文件

| 文件 | 用途 | 状态 |
|------|------|------|
| `migrations/versions/20250129_v4_4_0_finance_domain.py` | Alembic迁移 | ✅ 已创建 |
| `scripts/seed_finance_dictionary.py` | 财务辞典种子 | ✅ 已创建 |
| `scripts/deploy_v4_4_0_finance.py` | 一键部署 | ✅ 已创建 |
| `sql/create_finance_materialized_views.sql` | 物化视图SQL | ✅ 已创建 |
| `backend/routers/procurement.py` | 采购API | ✅ 已创建 |
| `backend/routers/finance.py` | 财务API | ✅ 已扩展 |
| `backend/services/expense_template_generator.py` | 模板生成 | ✅ 已创建 |
| `frontend/src/views/FinanceManagement.vue` | 财务前端 | ✅ 已创建 |
| `docs/V4_4_0_FINANCE_DOMAIN_GUIDE.md` | 完整指南 | ✅ 已创建 |

---

## 🤖 Agent开发工作流

### 新任务开始前（必做）

1. **读取本决策树** → 找到任务场景
2. **检查现有文件** → 避免重复创建
3. **确认修改位置** → 遵循Single Source of Truth
4. **检查依赖关系** → 先父表后子表

### 实施时（强制）

1. **小步提交** → 单次≤150行
2. **运行lint** → `read_lints([changed_files])`
3. **验证导入** → 确保from modules.core.db正确
4. **更新文档** → 修改后立即更新相关文档

### 完成后（必做）

1. **清理临时文件** → 移至temp/或backups/
2. **更新CHANGELOG** → 记录变更
3. **运行smoke测试** → 基本功能验证
4. **标记TODO完成** → 更新任务列表

---

## 📍 当前系统现状（v4.4.0）

### ✅ 已完成

- [x] 25张财务域新表（schema.py）
- [x] Alembic迁移脚本
- [x] 种子数据脚本（财务辞典）
- [x] 5个物化视图SQL
- [x] 采购管理API（procurement.py）
- [x] 财务管理API扩展（finance.py）
- [x] 字段辞典CRUD API（field_mapping_dictionary.py）
- [x] 费用导入模板生成器
- [x] 财务管理前端页面（Vue）
- [x] 完整文档

### 🚧 待完成（按优先级）

#### P0（必须）
- [ ] 运行Alembic迁移（创建表）
- [ ] 运行种子脚本（初始化辞典）
- [ ] 创建物化视图
- [ ] 前端映射页集成"新增字段"功能
- [ ] 测试费用导入+分摊流程

#### P1（重要）
- [ ] 实现FxConversionService（汇率转换）
- [ ] 完善GRN过账逻辑（platform_code/shop_id推导）
- [ ] 发票OCR集成
- [ ] 物化视图自动刷新（Celery任务）

#### P2（优化）
- [ ] 采购管理前端页面
- [ ] 库存龄分析看板
- [ ] 供应商表现看板
- [ ] 税务报表导出

---

## 🛠️ 立即可用的命令

### 部署v4.4.0

```bash
# 一键部署（推荐）
python scripts/deploy_v4_4_0_finance.py

# 手动步骤（出问题时使用）
cd migrations
alembic upgrade head

python scripts/seed_finance_dictionary.py

psql -U postgres -d xihong_erp -f sql/create_finance_materialized_views.sql
```

### 验证部署

```bash
# 检查表数量
psql -U postgres -d xihong_erp -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='public';"

# 应该看到：47+ 张表（22旧表 + 25新表）

# 检查辞典
psql -U postgres -d xihong_erp -c "SELECT data_domain, COUNT(*) FROM field_mapping_dictionary WHERE active=true GROUP BY data_domain;"
```

### 测试API

```bash
# 测试辞典API
curl http://localhost:8001/api/field-mapping/dictionary?data_domain=finance

# 测试P&L API
curl "http://localhost:8001/api/finance/pnl/shop?period_month=2025-01"

# 测试供应商API
curl http://localhost:8001/api/procurement/vendors/list
```

---

## 🎓 避免双维护的黄金法则

### 法则1：一个功能只在一处定义

```
✅ 正确：
FieldMappingDictionary → 在 modules/core/db/schema.py 定义
其他地方 → from modules.core.db import FieldMappingDictionary

❌ 错误：
在 backend/models/xxx.py 重新定义 FieldMappingDictionary
```

### 法则2：复用优于新建

```
✅ 正确：
需要SKU归一 → 复用 BridgeProductKeys
需要账号别名 → 复用 AccountAlias

❌ 错误：
新建 sku_aliases 表（功能重复）
新建 shop_mapping 表（功能重复）
```

### 法则3：扩展优于替换

```
✅ 正确：
需要version字段 → ALTER TABLE ADD COLUMN version

❌ 错误：
创建 field_mapping_dictionary_v2 表
```

### 法则4：物化视图优于新建聚合表

```
✅ 正确：
需要日销售聚合 → CREATE MATERIALIZED VIEW mv_sales_day_shop_sku

❌ 错误：
新建 fact_sales_day_summary 表（需要ETL维护）
```

---

## 🆘 遇到问题怎么办？

### 问题A：不知道改哪个文件

```
1. 查看本决策树 → 找到场景
2. 搜索现有代码：
   grep -r "关键词" backend/ modules/
3. 查看相关文档：
   - docs/V4_4_0_FINANCE_DOMAIN_GUIDE.md
   - docs/AGENT_START_HERE.md
```

### 问题B：担心造成双维护

```
1. 创建前必查：
   find . -name "*{功能名}*" -not -path "./backups/*"
   
2. 检查imports：
   grep -r "from.*{模块}" backend/ modules/
   
3. 遵循Single Source of Truth原则
```

### 问题C：不确定是否应该新建表

```
决策流程：
1. 这个数据已经在某个现有表中吗？
   → 是：扩展现有表（ADD COLUMN）
   → 否：继续下一步

2. 这个表的功能与现有表重复吗？
   → 是：复用现有表
   → 否：继续下一步

3. 这个表可以用物化视图替代吗？
   → 是：创建MV
   → 否：可以新建表

4. 新建表的命名符合规范吗？
   → 必须有前缀：dim_/fact_/gl_/po_/grn_
```

---

## ✅ Agent自检表（提交前）

- [ ] 我只修改了一个schema.py（没有重复定义模型）
- [ ] 我更新了__init__.py导出（如果新增了模型）
- [ ] 我的API路由在正确的router文件中（没有重复路由）
- [ ] 我注册了新router到main.py（如果新建了router）
- [ ] 我的脚本检查了重复数据（不会重复插入）
- [ ] 我运行了lint检查（无错误）
- [ ] 我更新了相关文档（CHANGELOG/GUIDE）
- [ ] 我没有创建带`_v2`、`_new`、`_temp`后缀的文件

---

**遵循本决策树，保证架构清晰、零双维护、Agent友好！**


