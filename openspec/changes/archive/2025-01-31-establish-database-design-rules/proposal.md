# 变更：建立数据库设计规则规范

## Why

经过数据库设计规则审查（`improve-data-sync-reliability`变更），我们发现：

1. **数据库设计缺少明确的规则规范**：
   - 虽然有技术规范文档（`docs/DEVELOPMENT_RULES/DATABASE_DESIGN.md`），但缺少OpenSpec格式的正式规范
   - 缺少明确的数据归属规则、字段必填规则、主键设计规则等
   - 导致后续开发中出现不一致和问题

2. **后端运作方式不清晰**：
   - 数据入库流程中的规则不明确（如shop_id获取逻辑）
   - 字段映射规则与数据库设计规则不一致
   - 事实表和物化视图的设计规则不明确

3. **问题根源**：
   - 数据同步可靠性问题可能源于数据库设计规则本身
   - 不停修复错误的设计方向，而不是从源头梳理规则
   - 需要建立明确的规则规范，指导后续开发

**核心目标**：从源头开始梳理后端的运作方式，建立明确的数据库设计规则规范，避免后续开发中的不一致和问题。

## What Changes

- **正式化数据库设计规范**：
  - 将现有的数据库设计规范草案（`openspec/specs/database-design/spec.md`）正式化
  - 补充完整的需求和场景定义
  - 确保规范覆盖所有关键设计决策

- **明确后端运作规则**：
  - 定义数据入库流程规则（shop_id获取、字段映射、数据验证等）
  - 定义字段映射规则与数据库设计规则的一致性要求
  - 定义事实表和物化视图的设计规则

- **建立经营数据和运营数据分离规则**：
  - 定义经营数据（miaoshou ERP）和运营数据（shopee/tiktok）的分离存储规则
  - 定义经营数据主键设计规则（自增ID主键+SKU为核心的唯一索引）
  - 定义运营数据主键设计规则（自增ID主键+shop_id为核心的唯一索引）
  - 定义店铺别名映射规则（AccountAlias表的使用）
  - 创建运营数据事实表（FactTraffic、FactService、FactAnalytics）

- **建立物化视图数据域集中规则**：
  - 定义物化视图主视图和辅助视图规则（主视图包含数据域所有核心字段，辅助视图用于特定分析场景）
  - 明确物化视图与数据域的对应关系（products域主视图、orders域主视图、traffic域主视图等）
  - 明确视图依赖关系（辅助视图依赖主视图或基础数据）
  - 确保前端优先使用主视图获取数据域的所有核心信息
  - 重构现有物化视图架构，创建数据域主视图

- **建立产品ID原子级设计规则**：
  - 定义产品ID冗余字段设计规则（在FactOrderItem等表中添加product_id字段，便于直接查询）
  - 定义以产品ID为原子级的销售明细物化视图设计规则（类似华为ISRP系统，每行代表一个产品实例）
  - 明确产品ID与SKU的关系（产品ID是每个产品实例的唯一标识，SKU是产品类型的标识）
  - 创建mv_sales_detail_by_product物化视图，以product_id为原子级，整合所有销售信息
  - 更新数据入库流程，自动关联product_id字段

- **建立规则执行机制**：
  - 创建规则验证工具（检查代码是否符合规范）
  - 创建规则文档（供开发人员参考）
  - 建立规则审查流程（确保新代码符合规范）

- **更新现有代码以符合规范**：
  - 审查现有代码是否符合新规范
  - 修复不符合规范的问题
  - 更新文档以反映新规范

## Impact

- **影响的规范**：
  - 正式化`openspec/specs/database-design/spec.md`
  - 可能需要更新`specs/data-sync/spec.md`（确保数据同步符合数据库设计规则）
  - 可能需要更新`specs/field-mapping/spec.md`（确保字段映射符合数据库设计规则）

- **影响的代码**：
  - `modules/core/db/schema.py`（数据库模型定义，需要明确经营数据和运营数据的分离，添加运营数据表，为FactOrderItem添加product_id字段）
  - `backend/services/data_ingestion_service.py`（数据入库服务，需要支持店铺别名映射，自动关联product_id）
  - `backend/services/data_importer.py`（数据导入服务，需要区分经营数据和运营数据，支持运营数据入库，自动关联product_id）
  - `backend/services/data_validator.py`（数据验证服务，需要验证主键设计规则，验证product_id关联）
  - `backend/services/materialized_view_service.py`（物化视图服务，需要区分主视图和辅助视图，更新刷新顺序）
  - `sql/materialized_views/`（物化视图SQL定义，需要创建数据域主视图，创建mv_sales_detail_by_product视图，明确视图依赖关系）
  - `modules/services/account_alignment.py`（账号对齐服务，需要支持店铺别名映射）
  - `frontend/src/api/`（前端API，需要优先使用主视图查询，支持以product_id查询销售明细）
  - `frontend/src/views/`（前端视图，需要更新查询逻辑，支持类似华为ISRP的销售明细展示）
  - 所有使用数据库模型的代码

- **影响的文档**：
  - `docs/DEVELOPMENT_RULES/DATABASE_DESIGN.md`（更新以符合OpenSpec规范）
  - `docs/field_mapping_v2/SHOP_AND_DATE_RESOLUTION.md`（更新以符合数据库设计规则）
  - 所有数据库相关的文档

## 非目标

- 不修改现有数据库结构（除非发现根本性问题）
- 不改变现有API接口（保持向后兼容）
- 不引入新的技术依赖

## 当前状态

- ✅ 数据库设计规则审查已完成（`improve-data-sync-reliability`变更）
- ✅ 数据库设计规范草案已创建（`openspec/specs/database-design/spec.md`）
- ✅ 审查报告已创建（`openspec/changes/improve-data-sync-reliability/db_design_review_report.md`）
- ❌ 数据库设计规范尚未正式化
- ❌ 后端运作规则尚未明确
- ❌ 规则执行机制尚未建立

