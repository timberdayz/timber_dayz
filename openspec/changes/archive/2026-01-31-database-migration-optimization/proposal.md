# Change: 数据库迁移优化与幂等性保障

## Why

当前数据库迁移系统存在严重问题，导致**频繁部署失败**：

### 问题统计

1. **迁移文件过多且复杂**：

   - 50+ 个迁移文件，依赖关系复杂
   - 存在分支合并（`20260111_merge_all_heads.py`）
   - 迁移历史难以维护和追溯

2. **缺乏幂等性**：

   - 大部分迁移没有检查表/字段是否存在
   - 重复执行会导致 `DuplicateTable`、`DuplicateColumn` 错误
   - 本地和云端数据库状态不一致

3. **高级特性易出错**：

   - 分区表迁移（`20251027_0008_partition_fact_tables.py`）多次失败
   - PostgreSQL 分区表要求主键必须包含分区键，但迁移未正确处理
   - 物化视图、GIN 索引等高级特性在迁移中容易出错

4. **部署失败频率高**：

   - 最近多次部署因迁移错误失败
   - 错误类型：`FeatureNotSupported`、`DuplicateTable`、`UndefinedTable`
   - 每次修复都需要重新部署，影响上线效率

5. **数据迁移缺乏工具**：
   - Schema 同步（表结构）已自动化，但数据迁移（数据内容）需要手动操作
   - 本地开发数据无法便捷地迁移到云端
   - 云端数据无法便捷地迁移回本地
   - 缺乏统一的数据迁移工具和流程

### 根本原因

1. **迁移策略不当**：使用 `LIKE ... INCLUDING INDEXES` 复制主键，但分区表要求主键包含分区键
2. **缺乏状态检查**：迁移假设表/字段不存在，未做存在性检查
3. **ORM 与迁移不同步**：本地通过 `init_db()` 创建表，但迁移历史不完整
4. **缺乏"重置点"**：没有完整的 schema 快照作为新起点
5. **数据迁移工具缺失**：只有备份/恢复脚本，缺乏灵活的数据迁移工具

## What Changes

### Phase 1: 立即修复（P0 - 解决当前部署问题）

1. **禁用分区表迁移**：

   - 修改 `20251027_0008_partition_fact_tables.py` 的 `upgrade()` 函数为跳过模式
   - 分区表作为性能优化功能，不影响核心业务，后续可手动执行

2. **部署脚本智能迁移**：
   - 在 `scripts/deploy_remote_production.sh` 中添加智能迁移逻辑
   - 检测数据库状态（检查 `alembic_version` 表是否存在）
   - 全新数据库：使用 Schema 快照迁移（`alembic upgrade v5_0_0_schema_snapshot`），然后执行 `alembic upgrade heads`
   - 已有数据库：尝试增量迁移（`alembic upgrade heads`），失败时直接检查表是否存在（不依赖 `verify_schema_completeness()`，可能因多头迁移失败），使用 `Base.metadata.create_all(bind=engine, tables=[...])` 补充缺失的表，验证通过后根据 head 数量选择 `alembic stamp head` 或 `alembic stamp heads` 标记为最新

### Phase 2: Schema 快照迁移（P1 - 建立新起点）

1. **创建 Schema 快照迁移**：

   - 新文件：`migrations/versions/20260112_v5_0_0_schema_snapshot.py`
   - 包含截至 2026-01-12 的完整数据库结构
   - 所有表创建都是幂等的（检查是否存在）
   - 可作为独立起点，不依赖旧迁移历史（`down_revision = None`）
   - **重要**：快照迁移后的**第一个**增量迁移的 `down_revision` 必须指向 `v5_0_0_schema_snapshot`，后续迁移按正常链式指向前一个迁移
   - 创建自动生成脚本：`scripts/generate_schema_snapshot.py`（从 `schema.py` 自动生成）

2. **创建 autogenerate 使用指南**：

   - 更新 `docs/DEVELOPMENT_RULES/DATABASE_MIGRATION.md`
   - 说明如何使用 `alembic revision --autogenerate` 生成增量迁移
   - 说明 autogenerate 的局限性和注意事项

3. **归档旧迁移文件**：
   - 创建 `migrations/versions_archived/` 目录
   - 归档前验证所有迁移都已执行（检查迁移历史）
   - 移动所有旧迁移文件到归档目录
   - 保留新的快照迁移作为起点
   - 创建迁移文件引用索引（便于追溯）

### Phase 3: 幂等迁移模板与规范（P2 - 未来保障）

1. **创建幂等迁移模板**：

   - 新文件：`migrations/templates/idempotent_migration.py.template`
   - 包含表/字段/索引的存在性检查示例
   - 使用 `safe_print()` 避免编码问题

2. **创建 Alembic autogenerate 使用指南**：

   - 更新 `docs/DEVELOPMENT_RULES/DATABASE_MIGRATION.md`
   - 说明如何使用 `alembic revision --autogenerate` 生成增量迁移
   - 说明 autogenerate 的局限性（表重命名、数据迁移等）
   - 说明何时使用 autogenerate，何时手动编写迁移

3. **更新开发规范**：
   - 在 `.cursorrules` 中添加数据库迁移规范
   - 强制要求所有新迁移必须幂等
   - 禁止使用 `INCLUDING ALL` 或 `INCLUDING INDEXES`
   - 禁止在生产环境使用 `init_db()`
   - 推荐使用 autogenerate 生成增量迁移

### Phase 4: 数据迁移工具（P1 - 数据同步支持）

1. **创建统一数据迁移工具**：

   - 新文件：`scripts/migrate_data.sh` - 统一数据迁移脚本
   - 支持完整数据库迁移、选择性表迁移、增量同步
   - 支持本地 ↔ 云端双向迁移

2. **创建选择性表迁移工具**：

   - 新文件：`scripts/migrate_selective_tables.py` - Python 数据迁移工具
   - 支持指定表列表迁移
   - 支持增量迁移（只迁移新数据）
   - 支持数据验证

3. **创建数据迁移 API 端点**：

   - 新文件：`backend/routers/data_migration.py`
   - 提供 `/data/export` 和 `/data/import` 端点（挂载到 `/api` 路由器下）
   - 适合小数据量配置类数据的快速同步

4. **创建数据迁移文档**：
   - 新文件：`docs/guides/DATA_MIGRATION_GUIDE.md`
   - 包含完整迁移流程、最佳实践、常见问题

## Impact

### 受影响的代码位置

| 类型              | 文件数 | 修改点数 | 优先级 |
| ----------------- | ------ | -------- | ------ |
| 迁移文件修复      | 1      | 10+      | P0     |
| 部署脚本增强      | 1      | 80+      | P0     |
| Schema 快照迁移   | 1      | 500+     | P1     |
| 快照生成脚本      | 1      | 200+     | P1     |
| 迁移文件归档      | 50+    | 50+      | P1     |
| 数据迁移工具      | 3      | 300+     | P1     |
| 迁移模板创建      | 1      | 100+     | P2     |
| 开发规范更新      | 1      | 50+      | P2     |
| autogenerate 指南 | 1      | 100+     | P2     |

### 预期效果

| 指标             | 当前          | 优化后         | 改善       |
| ---------------- | ------------- | -------------- | ---------- |
| 部署成功率       | 60-70%        | 95%+           | 显著提升   |
| 迁移失败恢复时间 | 30-60 分钟    | <5 分钟        | 10 倍提升  |
| 新环境部署时间   | 10-20 分钟    | 3-5 分钟       | 3-4 倍提升 |
| 迁移文件维护成本 | 高（50+文件） | 低（1 个快照） | 显著降低   |

### 风险评估

| 风险                                     | 严重程度 | 缓解措施                                                                                                            |
| ---------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------- |
| 快照迁移遗漏表/字段                      | 高       | 从 `schema.py` 自动生成脚本，完整验证                                                                               |
| 旧迁移历史丢失                           | 中       | 归档前验证迁移历史，归档而非删除，创建引用索引                                                                      |
| 现有环境迁移冲突                         | 中       | 智能检测（检查 `alembic_version`），直接检查表是否存在（不依赖 `verify_schema_completeness()`，可能因多头迁移失败） |
| 新迁移不遵循规范                         | 低       | 模板 + 规范 + 代码审查 + autogenerate 指南                                                                          |
| `init_db()` 生产环境禁用                 | 高       | 使用 Schema 快照迁移替代，不使用 `init_db()`                                                                        |
| 表数量判断不准确                         | 中       | 检查 `alembic_version` 表而非表数量                                                                                 |
| `alembic upgrade head` vs `heads` 不一致 | 高       | 统一使用 `alembic upgrade heads`（复数）支持多头迁移                                                                |
| `alembic stamp head` 危险使用            | 高       | 仅在验证表结构完整后才使用 `stamp`，添加验证步骤                                                                    |
| 缺失表补充逻辑不完整                     | 中       | 使用 `Base.metadata.create_all()` 实际创建缺失的表，验证后标记                                                      |
| 快照迁移 revision ID 不确定              | 中       | 在生成脚本中明确设置 revision ID                                                                                    |
| `table.create()` 方法不存在              | 高       | 使用 `Base.metadata.create_all(bind=engine, tables=[...])` 创建表                                                   |
| 表创建顺序问题（外键依赖）               | 中       | 使用 `Base.metadata.create_all()` 一次性创建，SQLAlchemy 自动处理依赖顺序                                           |
| `alembic stamp heads` 行为不确定         | 中       | 检查 head 数量，根据情况选择 `stamp head` 或 `stamp heads`（使用准确的检测方式）                                    |
| `verify_schema_completeness()` 可能失败  | 中       | 验证步骤直接检查表是否存在，不依赖可能失败的函数                                                                    |
| HEAD_COUNT 检测不准确                    | 中       | 使用 `grep -E "\(head\)" \| wc -l` 或 Python 脚本准确统计 head 数量                                                 |
| `missing_table_objects` KeyError         | 中       | 过滤掉不在 metadata 中的表名，只创建在 `Base.metadata.tables` 中存在的表                                            |
| 快照迁移 revision ID 不存在              | 中       | 在部署前验证 revision 是否存在，不存在时提供降级方案（使用 `alembic upgrade heads`）                                |
| SQL 注入风险 - 表名/列名拼接             | 高       | 白名单验证 + 格式验证，只允许 ORM 定义的表和有效列名                                                                |
| 数据导入冲突处理缺失                     | 中       | 添加 `on_conflict` 参数支持 skip/update/error 策略                                                                  |
| 数据导出大表内存溢出                     | 低       | 添加分页支持（limit/offset），默认限制 10000 条                                                                     |

### 依赖变更

**无新增依赖**：所有修改基于现有工具（Alembic、SQLAlchemy）

### 迁移时间估计

| 阶段     | 预计时间   | 说明                                                       |
| -------- | ---------- | ---------------------------------------------------------- |
| Phase 1  | 2-3 小时   | 立即修复，解决当前问题（禁用分区表迁移，修复智能迁移逻辑） |
| Phase 2  | 2-3 天     | 创建快照迁移（含自动生成脚本），归档旧文件                 |
| Phase 3  | 1 天       | 创建模板，更新规范，添加 autogenerate 指南                 |
| Phase 4  | 1-2 天     | 创建数据迁移工具和文档                                     |
| **总计** | **5-7 天** | 分阶段实施，不影响当前开发                                 |

## Non-Goals

- **不重构现有迁移历史**：只创建新起点，不修改旧迁移文件（归档即可）
- **不强制分区表**：分区表作为可选优化，不在迁移中强制执行
- **不引入新工具**：基于现有 Alembic + SQLAlchemy 工具链
- **不改变 ORM 模型**：只优化迁移策略，不修改 `schema.py`
- **不使用 `init_db()` 在生产环境**：生产环境必须使用 Alembic 迁移，不使用 `init_db()`

## Success Criteria

1. ✅ **部署成功率 > 95%**：连续 10 次部署至少 9 次成功
2. ✅ **新环境部署 < 5 分钟**：从零到可用状态
3. ✅ **迁移失败恢复 < 5 分钟**：自动检测缺失表并使用快照迁移补充
4. ✅ **所有新迁移幂等**：可重复执行不报错
5. ✅ **文档完整**：迁移规范、模板、最佳实践文档齐全
6. ✅ **数据迁移工具可用**：支持本地 ↔ 云端双向数据迁移
7. ✅ **数据迁移文档完整**：包含完整流程、最佳实践、常见问题
8. ✅ **autogenerate 指南完整**：说明何时使用自动生成，何时手动编写

## Related Changes

- `add-production-day1-bootstrap`：Day-1 Bootstrap 包含数据库初始化
- `migrate-to-async-sqlalchemy`：异步架构迁移（已完成）

---

## Outcome / 实施结果（2026-01-12）

**状态**：Phase 1–4 实施已完成；剩余为测试环境验证与可选文档更新。

### 已完成

- **Phase 1（立即修复）**：分区表迁移已改为跳过模式；`scripts/deploy_remote_production.sh` 已实现智能迁移（检测 `alembic_version`、新库用快照、已有库增量 + 缺失表补充、head/heads 安全标记）。
- **Phase 2（Schema 快照）**：`scripts/generate_schema_snapshot.py` 已创建；`migrations/versions/20260112_v5_0_0_schema_snapshot.py` 已生成（幂等、106 张表）；旧迁移已归档至 `migrations/versions_archived/`，索引见 `INDEX.md`。
- **Phase 3（幂等模板与规范）**：`migrations/templates/idempotent_migration.py.template` 已创建；`.cursorrules` 与 `docs/DEVELOPMENT_RULES/DATABASE_MIGRATION.md` 已更新（幂等要求、禁止 INCLUDING ALL/INDEXES、禁止生产 init_db、autogenerate 指南）。
- **Phase 4（数据迁移工具）**：`scripts/migrate_data.sh`、`scripts/migrate_selective_tables.py` 已创建；`backend/routers/data_migration.py` 已实现 `/api/data/export`、`/api/data/import`（白名单、分页、冲突策略）；`docs/guides/DATA_MIGRATION_GUIDE.md` 已创建。

### 延后 / 可选

- **测试环境验证**：新数据库部署、已有数据库迁移、部署脚本回退等场景待实际环境验证。
- **数据迁移工具测试**：完整迁移、选择性表迁移、增量同步、API 导出/导入的端到端测试待执行。
- **文档更新**：`CHANGELOG.md`、`docs/CI_CD_DEPLOYMENT_GUIDE.md` 中迁移策略说明可后续补充。
