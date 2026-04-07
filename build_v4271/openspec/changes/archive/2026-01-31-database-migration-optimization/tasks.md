# Tasks: 数据库迁移优化与幂等性保障

**实施状态**：Phase 1–4 实施已完成（2026-01-12）；剩余为测试环境验证与可选文档更新。详见 `proposal.md` 的 Outcome 节与 `IMPLEMENTATION_SUMMARY.md`。

## Phase 1: 立即修复（P0）

### 1.1 禁用分区表迁移

- [x] 修改 `migrations/versions/20251027_0008_partition_fact_tables.py`
  - [x] 将 `upgrade()` 函数改为跳过模式（直接 `pass`）
  - [x] 添加说明注释：分区表作为性能优化，后续手动执行
  - [x] 验证语法正确性

### 1.2 部署脚本智能迁移

- [x] 修改 `scripts/deploy_remote_production.sh`
  - [x] 添加 `smart_database_migrate()` 函数
  - [x] 检测 `alembic_version` 表是否存在（判断是否为新数据库，而非表数量）
  - [x] 新数据库：使用 Schema 快照迁移（`alembic upgrade v5_0_0_schema_snapshot`）+ `alembic upgrade heads`
  - [x] 已有数据库：尝试 `alembic upgrade heads`（复数，支持多头迁移），失败时直接检查表是否存在（不依赖 `verify_schema_completeness()`，可能因多头迁移失败）
  - [x] 缺失表处理：使用 `Base.metadata.create_all(bind=engine, tables=[...])` 补充缺失的表（只创建缺失的表，不覆盖已有表）
  - [x] 表创建顺序：使用一次性创建，SQLAlchemy 自动处理外键依赖顺序
  - [x] KeyError 防护：过滤掉不在 `Base.metadata.tables` 中的表名，防止 KeyError
  - [x] 错误处理：直接检查表是否存在，不依赖 `verify_schema_completeness()`（可能因多头迁移失败）
  - [x] 验证步骤：在标记迁移为最新前，直接检查表是否存在（不依赖 `verify_schema_completeness()`）
  - [x] 安全标记：检查 head 数量（使用 `grep -E "\(head\)" | wc -l` 准确统计），根据情况选择 `alembic stamp head` 或 `alembic stamp heads`
  - [x] 快照迁移 revision 验证：在部署前验证 revision ID 是否存在，不存在时提供降级方案
  - [x] 新数据库迁移错误处理：如果快照迁移失败，检查表是否已部分创建，提供清理或继续选项
  - [x] 添加错误处理和日志输出
  - [ ] 测试新数据库场景（待测试环境验证）
  - [ ] 测试已有数据库场景（待测试环境验证）
  - [ ] 测试迁移失败回退场景（待测试环境验证）

## Phase 2: Schema 快照迁移（P1）

### 2.1 创建 Schema 快照迁移自动生成脚本

- [x] 创建 `scripts/generate_schema_snapshot.py`
  - [x] 从 `modules/core/db/schema.py` 自动提取所有表定义
  - [x] 生成幂等表创建代码（包含存在性检查）
  - [x] 生成 `safe_print()` 函数
  - [x] 生成完整的迁移文件结构
  - [x] 设置 `down_revision = None`
  - [x] 明确设置 `revision = 'v5_0_0_schema_snapshot'`（确保 revision ID 正确）
  - [x] 添加验证逻辑（检查是否遗漏表）
  - [x] 测试脚本生成功能

### 2.2 生成 Schema 快照迁移文件

- [x] 运行 `scripts/generate_schema_snapshot.py` 生成快照迁移
- [x] 创建 `migrations/versions/20260112_v5_0_0_schema_snapshot.py`
  - [x] 验证生成的迁移文件完整性
  - [x] 手动审查和优化（如需要）
  - [x] 添加完整注释和文档
  - [x] 验证语法正确性
  - [ ] 在测试环境验证（创建表、跳过已存在表）（待测试环境验证）
  - [ ] 验证所有表都能正确创建（待测试环境验证）

### 2.3 归档旧迁移文件

- [x] 创建 `migrations/versions_archived/` 目录
- [x] 归档前验证迁移历史
  - [x] 检查所有迁移是否都已执行（通过脚本提取 revision 信息）
  - [x] 验证迁移链完整性（记录在索引文件中）
  - [x] 记录当前迁移状态（索引文件包含归档时间）
- [x] 移动所有旧迁移文件到归档目录
  - [x] 保留 `20260112_v5_0_0_schema_snapshot.py` 在新目录
  - [x] 移动所有 `2025*.py` 文件（55 个文件已归档）
  - [x] 移动所有 `2026010*.py` 和 `20260111*.py` 文件
- [x] 创建迁移文件引用索引（`migrations/versions_archived/INDEX.md`）
  - [x] 记录归档的迁移文件列表
  - [x] 记录每个迁移的 `revision` 和 `down_revision`
  - [x] 便于追溯历史
- [x] 验证归档后迁移历史完整性（快照迁移文件已确认存在）
- [ ] 更新文档说明归档策略（待后续更新）

## Phase 3: 幂等迁移模板与规范（P2）

### 3.1 创建幂等迁移模板

- [x] 创建 `migrations/templates/idempotent_migration.py.template`
  - [x] 包含表创建示例（带存在性检查）
  - [x] 包含字段添加示例（带存在性检查）
  - [x] 包含索引创建示例（带存在性检查）
  - [x] 包含 `safe_print()` 使用示例
  - [x] 包含 `downgrade()` 幂等示例
  - [x] 添加完整注释和最佳实践

### 3.2 更新开发规范

- [x] 更新 `.cursorrules`
  - [x] 添加"数据库迁移规范"章节
  - [x] 强制要求所有新迁移必须幂等
  - [x] 禁止使用 `INCLUDING ALL` 或 `INCLUDING INDEXES`
  - [x] 要求使用 `safe_print()` 替代 `print()`
  - [x] 禁止在生产环境使用 `init_db()`
  - [x] 添加迁移检查清单
- [x] 创建迁移最佳实践文档
  - [x] `docs/DEVELOPMENT_RULES/DATABASE_MIGRATION.md`
  - [x] 包含幂等性要求、模板使用、常见错误等
  - [x] 包含 Alembic autogenerate 使用指南
  - [x] **重要**：说明快照迁移后的**第一个**增量迁移的 `down_revision` 必须指向快照迁移（`v5_0_0_schema_snapshot`），后续迁移按正常链式指向前一个迁移
  - [x] 说明 autogenerate 的局限性和注意事项
  - [x] 说明何时使用 autogenerate，何时手动编写迁移

## 验证与测试

### 测试场景

- [ ] **新数据库部署测试**

  - [ ] 创建全新数据库
  - [ ] 运行快照迁移
  - [ ] 验证所有表创建成功
  - [ ] 验证迁移历史正确

- [ ] **已有数据库迁移测试**

  - [ ] 使用已有数据的数据库
  - [ ] 运行快照迁移
  - [ ] 验证跳过已存在的表
  - [ ] 验证补充缺失的表

- [ ] **增量迁移测试**

  - [ ] 创建新迁移（使用模板）
  - [ ] 验证幂等性（重复执行不报错）
  - [ ] 验证回滚功能

- [ ] **部署脚本测试**
  - [ ] 测试新数据库场景（检查 `alembic_version` 表不存在）
  - [ ] 测试已有数据库场景（检查 `alembic_version` 表存在）
  - [ ] 测试迁移失败回退场景（直接检查表是否存在，不依赖 `verify_schema_completeness()`）
  - [ ] 测试缺失表补充功能

## Phase 4: 数据迁移工具（P1）

### 4.1 创建统一数据迁移脚本

- [x] 创建 `scripts/migrate_data.sh`
  - [x] 支持完整数据库迁移（使用 pg_dump/pg_restore）
  - [x] 支持选择性表迁移（调用 Python 工具）
  - [x] 支持增量同步模式
  - [x] 添加数据验证功能
  - [x] 添加错误处理和日志输出
  - [x] 添加使用说明和示例

### 4.2 创建选择性表迁移工具

- [x] 创建 `scripts/migrate_selective_tables.py`
  - [x] 支持指定表列表迁移
  - [x] 支持增量迁移（只迁移新数据，基于时间戳或 ID）
  - [x] 支持数据验证（记录数、关键字段完整性）
  - [x] 支持外键关系处理
  - [x] 添加进度显示和日志输出
  - [x] 添加 dry-run 模式（预览模式）

### 4.3 创建数据迁移 API 端点

- [x] 创建 `backend/routers/data_migration.py`
  - [x] 实现 `POST /api/data/export` 端点
    - [x] 支持指定表列表导出
    - [x] 支持 JSON 格式导出
    - [x] 添加权限验证（仅管理员）
    - [x] [安全] 添加表名白名单验证（只允许 ORM 定义的表）
    - [x] [性能] 添加分页支持（limit/offset 参数）
  - [x] 实现 `POST /api/data/import` 端点
    - [x] 支持 JSON 格式导入
    - [x] 支持数据验证和错误报告
    - [x] 添加权限验证（仅管理员）
    - [x] [安全] 添加表名/列名白名单验证
    - [x] [功能] 添加冲突处理策略（on_conflict: skip/error，update 暂简化为 skip）
    - [x] [TODO] 后续扩展：实现真正的 UPSERT（需要获取主键信息）
  - [x] 添加 API 文档和示例
  - [x] [安全] 实现安全函数
    - [x] `get_allowed_tables()` - 获取白名单
    - [x] `validate_table_name()` - 验证表名
    - [x] `validate_column_names()` - 验证列名

### 4.4 创建数据迁移文档

- [x] 创建 `docs/guides/DATA_MIGRATION_GUIDE.md`

  - [x] 完整数据库迁移流程（初始部署）
  - [x] 选择性表迁移流程（日常同步）
  - [x] API 导出/导入流程（小数据量）
  - [x] 数据验证方法
  - [x] 常见问题和解决方案
  - [x] 最佳实践建议

- [ ] **数据迁移工具测试**
  - [ ] 测试完整数据库迁移（本地 → 云端）
  - [ ] 测试选择性表迁移（指定表列表）
  - [ ] 测试增量同步（只迁移新数据）
  - [ ] 测试 API 导出/导入（小数据量）
  - [ ] 测试数据验证功能

## 文档更新

- [ ] 更新 `CHANGELOG.md` 记录本次优化（待后续更新）
- [ ] 更新 `docs/CI_CD_DEPLOYMENT_GUIDE.md` 说明新的迁移策略（待后续更新）
- [x] 创建 `docs/DEVELOPMENT_RULES/DATABASE_MIGRATION.md` 迁移规范文档
- [x] 创建 `docs/guides/DATA_MIGRATION_GUIDE.md` 数据迁移指南
