# Change: 优化本地迁移验证与部署门禁

## Why

1. **CI 暴露迁移顺序问题、本地未复现**：打 tag 后 CI 的 "Validate Database Migrations" 在**全新临时库**上执行 `alembic upgrade heads`，曾出现 `schema "a_class" does not exist`（迁移在移动表到 `a_class` 时，该 schema 尚未被创建，因创建 schema 的迁移排在后面）。本地方式 B（`verify_deploy_full_local.py`）使用**持久化卷**的 Postgres，库中可能已有历史数据与 schema，无法复现「从零跑全量迁移」的失败。

2. **本地与云端 DB 关系未在文档中明确**：本地 Docker 的 Postgres 与云端 Postgres **无数据同步**，仅通过**同一套迁移文件**在各自环境执行以保持结构一致。文档未说明此点，易误解为「空库迁移会动云端或清空开发库」。

3. **Phase 2 迁移失败未阻断本地验证**：`verify_deploy_full_local.py` 中 Phase 2 若 `alembic upgrade heads` 返回非零，仅打 WARN 并继续，导致迁移真实失败时本地仍显示「验证完成」，与 CI 行为不一致。

4. **业界主流**：CI 用临时空库跑全量迁移；本地若要复现 CI 门禁，应采用**独立临时库**（不碰开发库），迁移脚本应**自包含依赖**（如先 CREATE SCHEMA 再 SET SCHEMA）。

## What Changes

### 1. 迁移脚本自包含依赖（修复 schema 顺序问题）

- **文件**：`migrations/versions/20260127_migrate_a_c_class_tables_to_schema.py`
- **变更**：在 `upgrade()` 中，在循环移动表到 `a_class` / `c_class` **之前**，先执行：
  - `CREATE SCHEMA IF NOT EXISTS a_class;`
  - `CREATE SCHEMA IF NOT EXISTS c_class;`
- **效果**：无论迁移链顺序如何，在全新库上从零执行到该迁移时，移动表前 schema 已存在，与后续「创建 a_class 的迁移」无顺序依赖，CI 与本地临时库门禁均通过。

### 2. 本地方式 B：Phase 2 迁移失败即失败

- **文件**：`scripts/verify_deploy_full_local.py`
- **变更**：Phase 2 执行 `alembic upgrade heads` 后，若 returncode != 0，则打印迁移输出并 `return 1` 退出，不再继续 Phase 2.5 及后续。
- **效果**：一旦迁移失败，本地验证与 CI 一致地失败，便于在推 tag 前发现问题。

### 3. 新增「临时库迁移门禁」脚本（与 CI 等价、不碰开发库）

- **新增文件**：`scripts/validate_migrations_fresh_db.py`
- **行为**：
  - 在本机启动一个**临时** Postgres 容器（如 `docker run --rm -d -e POSTGRES_USER=... -e POSTGRES_PASSWORD=... -e POSTGRES_DB=migration_test_db -p 5433:5432 postgres:15`），使用**非 5432 端口**（如 5433）避免与现有开发库冲突。
  - 等待 Postgres 就绪后，设置 `DATABASE_URL=postgresql://...@localhost:5433/migration_test_db`，在项目根目录执行 `alembic upgrade heads`。
  - 成功则退出码 0，失败则非 0；脚本结束时停止并删除该临时容器（`docker stop` 或容器已 `--rm`）。
- **约束**：不操作、不删除现有 compose 的 Postgres 卷或开发库数据；仅用于「从零跑全量迁移」的门禁，与 CI 的 Validate Database Migrations 等价。

### 4. 文档更新

- **文件**：`docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md`
- **变更**：
  - 新增小节「本地与云端数据库关系」：说明本地 Docker Postgres 与云端 Postgres **无数据同步**，仅靠**同一套迁移文件**在各自环境执行；CI 与云端首次部署使用全新库，本地方式 B 默认使用持久化卷的 Postgres。
  - 在「方式 B」小节补充：发布前若需与 CI 完全对齐，可先运行 `python scripts/validate_migrations_fresh_db.py`（临时库门禁），再运行 `verify_deploy_full_local.py`。
  - 在「本地验证清单」中增加一项：**[ ] 临时库迁移门禁**：执行 `python scripts/validate_migrations_fresh_db.py` 通过（在全新临时 Postgres 上跑 `alembic upgrade heads`，不碰开发库）。
  - 在「与 CI 的对应关系」表中明确：临时库迁移门禁 对应 CI 的 Validate Database Migrations；并说明不提供「清空开发库」的 --fresh-db，避免误伤本地数据。
  - 补充「部署验证后的数据迁移」：在完成本变更的验证与云端部署修复后，若需将本地数据库数据上传到云端，推荐使用**做法一（完整库迁移）**：配置好 `CLOUD_DATABASE_URL` 后执行 `./scripts/migrate_data.sh --mode full --source local --target cloud`，详见 `docs/guides/DATA_MIGRATION_GUIDE.md`。

### 5. 部署验证后的数据迁移（推荐流程，非代码变更）

- **说明**：以下为**推荐使用流程**，不修改仓库文件；具体文档变更见「4. 文档更新」4.5。
- **时机**：在完成本变更的验证（临时库门禁、方式 B 全流程）并修复云端部署问题（如迁移通过、服务健康）之后。
- **做法**：使用**做法一（完整库迁移）**将本地数据库全量迁移到云端。
- **步骤**：
  1. 在本地 `.env` 或环境中配置 **`CLOUD_DATABASE_URL`**（云端 PostgreSQL 连接串，需本机可访问或经 SSH 隧道映射）。
  2. 执行：`./scripts/migrate_data.sh --mode full --source local --target cloud`（可先加 `--dry-run` 预览）。
  3. 脚本会：用 `DATABASE_URL` 作本地源、`CLOUD_DATABASE_URL` 作云端目标，`pg_dump` 导出后 `pg_restore` 到云端；并可选验证数据。
- **参考**：`docs/guides/DATA_MIGRATION_GUIDE.md`（完整数据库迁移）、`scripts/migrate_data.sh`。

## Impact

### 受影响的 Spec

- **deployment-ops**：ADDED - 迁移脚本自包含 schema 依赖、本地验证 Phase 2 失败即失败、临时库迁移门禁脚本、部署文档本地/云端 DB 关系与门禁清单

### 受影响的文件

| 类型     | 文件/对象 | 修改内容 |
|----------|-----------|----------|
| 迁移     | `migrations/versions/20260127_migrate_a_c_class_tables_to_schema.py` | upgrade() 开头增加 CREATE SCHEMA IF NOT EXISTS a_class/c_class |
| 脚本     | `scripts/verify_deploy_full_local.py` | Phase 2 失败时 return 1，不继续 |
| 脚本     | `scripts/validate_migrations_fresh_db.py` | 新增：临时 Postgres + alembic upgrade heads |
| 文档     | `docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md` | 本地/云端 DB 关系、临时库门禁用法、清单与 CI 对应、部署验证后的数据迁移（做法一） |

### 依赖关系

- **无前置变更依赖**：可与当前 main 并行。
- **后置**：打 tag 前推荐先跑临时库门禁 + 方式 B，减少 CI 红。

## 潜在漏洞与建议

1. **迁移自包含覆盖范围**  
   当前仅修改 `20260127_migrate_a_c_class_tables_to_schema.py`。另一迁移 `20260131_migrate_public_tables_to_a_c_class.py` 同样会向 `a_class`/`c_class` 建表，但未在 `upgrade()` 开头创建 schema。当前迁移链中 20260131 在 20260127 之后执行，故仅修 20260127 即可消除 CI 报错。若需**完全符合 spec**（“任何移动表到 a_class/c_class 的迁移均应在 upgrade 开头创建 schema”）并增强鲁棒性（如未来分支/合并顺序变化），建议对 `20260131_migrate_public_tables_to_a_c_class.py` 同样在 `upgrade()` 开头增加 `CREATE SCHEMA IF NOT EXISTS a_class;` 与 `CREATE SCHEMA IF NOT EXISTS c_class;`。

2. **做法一（完整库迁移）在 Windows 上**  
   `scripts/migrate_data.sh` 为 bash 脚本，Windows 上需在 **Git Bash** 或 **WSL** 下执行；文档与验收 5.4 中可注明「Linux / Git Bash / WSL 下执行 `./scripts/migrate_data.sh`」。

3. **临时库门禁端口**  
   tasks 3.2 已要求脚本支持可选参数（如 `--port 5433`），端口冲突时用户可指定其他端口，无需再改提案。

## 非目标（Non-Goals）

- **不**增加会清空本地开发库的 `--fresh-db` 或对现有 compose Postgres 做 `down -v`；仅采用「临时容器」方案，保证开发数据安全。
- **不**修改 CI workflow 的迁移验证逻辑（CI 已正确使用临时 Postgres）。
- **不**做数据同步或备份恢复相关功能。
