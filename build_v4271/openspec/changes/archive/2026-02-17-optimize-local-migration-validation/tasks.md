# Tasks: 优化本地迁移验证与部署门禁

## 1. 迁移脚本自包含依赖

- [x] 1.1 修改 `migrations/versions/20260127_migrate_a_c_class_tables_to_schema.py`
  - 在 `upgrade()` 开头（在循环移动表之前），获取 `conn = op.get_bind()` 后执行：
    - `conn.execute(text("CREATE SCHEMA IF NOT EXISTS a_class"))`
    - `conn.execute(text("CREATE SCHEMA IF NOT EXISTS c_class"))`
  - 确保与现有 `safe_print` 等逻辑无冲突，必要时在「Migrating A-class tables」打印之前执行

- [x] 1.2 本地验证：在全新临时库或 CI 环境执行 `alembic upgrade heads`，确认无 `schema "a_class" does not exist` 错误

- [x] 1.3 （可选，增强鲁棒性）对 `migrations/versions/20260131_migrate_public_tables_to_a_c_class.py` 同样在 `upgrade()` 开头增加 `CREATE SCHEMA IF NOT EXISTS a_class` 与 `CREATE SCHEMA IF NOT EXISTS c_class`，使「凡使用 a_class/c_class 的迁移」均自包含 schema，完全符合 spec

## 2. 本地方式 B：Phase 2 失败即失败

- [x] 2.1 修改 `scripts/verify_deploy_full_local.py`
  - Phase 2 中，当 `compose_run(["run", "--rm", "--no-deps", "backend", "alembic", "upgrade", "heads"], ...)` 的 returncode != 0 时：
    - 打印迁移输出（如 out[-1500:] 或全文）
    - `return 1` 退出，不再执行 Phase 2.5 及后续
  - 删除或改写当前「WARN 并继续」的分支

## 3. 新增临时库迁移门禁脚本

- [x] 3.1 新建 `scripts/validate_migrations_fresh_db.py`
  - 使用**非 5432 端口**（如 5433）启动临时 Postgres 容器（`docker run --rm -d ... -p 5433:5432 postgres:15`），环境变量 POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB 与 CI 一致（如 migration_test_user / migration_test_pass / migration_test_db）
  - 等待 Postgres 就绪（pg_isready 或重试连接）
  - 设置 `DATABASE_URL=postgresql://migration_test_user:migration_test_pass@localhost:5433/migration_test_db`，在项目根执行 `alembic upgrade heads`
  - 成功则 exit 0，失败则 exit 1 并打印输出
  - 脚本结束前停止并删除临时容器（`docker stop <container_id>`，或使用 `--rm` 的容器在 stop 后自动删除）
  - 脚本内不操作现有 compose 或 postgres_data 卷

- [x] 3.2 文档注释：在脚本顶部说明用途（与 CI Validate Database Migrations 等价，不碰开发库）、用法（`python scripts/validate_migrations_fresh_db.py`）、可选参数（如 `--port 5433`）

## 4. 文档更新

- [x] 4.1 在 `docs/deployment/CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md` 中新增小节「本地与云端数据库关系」
  - 说明：本地 Docker Postgres 与云端 Postgres **无数据同步**，仅靠**同一套迁移文件**在各自环境执行；CI 与云端首次部署使用全新库，本地方式 B 默认使用持久化卷的 Postgres

- [x] 4.2 在「方式 B」小节补充
  - 发布前若需与 CI 完全对齐，可先运行 `python scripts/validate_migrations_fresh_db.py`（临时库门禁），再运行 `verify_deploy_full_local.py`
  - 明确不提供会清空开发库的 --fresh-db

- [x] 4.3 在「本地验证清单」中增加
  - **[ ] 临时库迁移门禁**：执行 `python scripts/validate_migrations_fresh_db.py` 通过（在全新临时 Postgres 上跑 `alembic upgrade heads`，不碰开发库）

- [x] 4.4 在「与 CI 的对应关系」表或说明中
  - 增加一行：临时库迁移门禁（validate_migrations_fresh_db.py）对应 CI 的 Validate Database Migrations
  - 说明仅使用临时容器，不触碰开发库数据

- [x] 4.5 在文档中补充「部署验证后的数据迁移」
  - 在「本地与云端数据库关系」或「方式 B」后增加小节或段落：完成本变更验证与云端部署修复后，若需将本地数据上传到云端，推荐使用**做法一（完整库迁移）**：配置 `CLOUD_DATABASE_URL` 后执行 `./scripts/migrate_data.sh --mode full --source local --target cloud`，详见 `docs/guides/DATA_MIGRATION_GUIDE.md`
  - 注明：Windows 上需在 Git Bash 或 WSL 下执行 `./scripts/migrate_data.sh`

## 5. 验收

- [x] 5.1 在全新库（或 CI）上执行 `alembic upgrade heads` 通过，无 schema a_class 不存在错误
- [x] 5.2 本地执行 `python scripts/validate_migrations_fresh_db.py` 通过（临时容器起停正常、迁移成功）
- [x] 5.3 本地执行 `python scripts/verify_deploy_full_local.py` 时，若人为制造迁移失败（如临时注释 CREATE SCHEMA），验证脚本以非零退出并终止在 Phase 2
- [x] 5.4 （可选）验证并修复云端部署后，按文档执行做法一完整库迁移：配置 `CLOUD_DATABASE_URL` 后运行 `./scripts/migrate_data.sh --mode full --source local --target cloud`，确认本地数据可成功迁移到云端
