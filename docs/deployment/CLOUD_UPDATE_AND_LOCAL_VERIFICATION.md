# 云端部署更新与本地 Docker 验证指南

本文档说明：**在数据表与 Metabase 模型/Question 发生较大变更后**，如何安全地更新云端部署，以及如何在本地用 Docker 做与生产一致的验证，**避免问题只在 CI/CD 阶段才暴露**。

---

## 一、云端部署更新（有大量数据表与 Metabase 变更时）

### 1.1 部署流程回顾

云端更新由 **Git tag 触发** 的 `Deploy to Production` 完成，顺序为：

| 阶段 | 内容 | 与 DB/Metabase 的关系 |
|------|------|------------------------|
| **Validate** | 外键、迁移、API 契约、前端 API、数据库字段 | 迁移在临时库执行，通过才进入构建 |
| **Build** | 构建 Backend/Frontend 镜像并推送 | 镜像内含 migrations、config、sql、init_metabase.py |
| **Sync** | 上传 compose、deploy 脚本、nginx 配置 | 服务器拿到最新脚本与配置 |
| **Phase 0.5** | 清洗 .env | - |
| **Phase 1** | 启动 PostgreSQL、Redis | 已有数据时沿用现有库 |
| **Phase 2** | **智能数据库迁移**（见下） | 新库用快照，已有库用 `alembic upgrade heads` |
| **Phase 2.5** | Bootstrap（角色等） | 幂等 |
| **Phase 3** | 启动 Metabase | 已有 Metabase 应用库时沿用 |
| **Phase 3.5** | **init_metabase.py**（Models/Questions 创建或更新） | 幂等，按名称匹配 |
| **Phase 4/4b/5** | Backend、Celery、Frontend、Nginx | 应用层 |

因此：**数据表变更** 靠 Phase 2 的迁移；**Metabase 模型/Question 变更** 靠 Phase 3.5 的 `init_metabase.py`。两者都会在每次部署时自动执行。

### 1.2 你需要纳入版本的内容（必须提交到 Git）

在打 tag 前，确保以下内容已提交且与预期一致：

- **数据库**
  - `modules/core/db/schema.py`（表结构）
  - `migrations/versions/*.py`（新增或修改的迁移）
  - 若使用快照迁移：对应快照文件与 revision 链
- **Metabase**
  - `config/metabase_config.yaml`（Models/Questions 清单与 display_name）
  - `sql/metabase_models/*.sql`、`sql/metabase_questions/*.sql`（有改动则提交）
- **部署与初始化**
  - `scripts/deploy_remote_production.sh`（含 Phase 3.5）
  - `scripts/init_metabase.py`
  - `Dockerfile.backend`（已包含 init_metabase.py 与 sql 拷贝）

### 1.3 云端「已有大量数据」时的注意点

- **数据库**
  - 部署脚本会检测 `alembic_version`：**已有库只做增量迁移**（`alembic upgrade heads`），不会重跑快照。
  - 若你本地/云端曾手动改过表结构，务必用 Alembic 生成并提交迁移，保证 `alembic upgrade heads` 与当前 schema 一致。
- **Metabase**
  - `init_metabase.py` 按 **名称** 匹配：同名 Model/Question 会更新，不存在则创建；**不会删**云端已存在但配置里已删的资源（需在 Metabase UI 手动删）。
  - 后端已支持「按名称查 Question ID」：部署后无需再在 .env 里配 `METABASE_QUESTION_*`，只要 Phase 3.5 成功即可。

### 1.4 推荐发布步骤

```bash
# 1. 在 main 上合并完所有变更（含 migrations、metabase_config、sql、deploy 脚本）
git checkout main
git pull origin main

# 2. 本地按「二、本地 Docker 验证」跑一遍，确认通过后再打 tag
python scripts/verify_deploy_phase35_local.py
# 以及（可选）本地生产 compose 全栈验证

# 3. 打 tag 并推送（触发 CI：验证 → 构建 → 部署）
git tag v4.x.x
git push origin v4.x.x
```

---

## 本地与云端数据库关系

- **本地 Docker Postgres** 与 **云端 Postgres** **无数据同步**，仅靠**同一套迁移文件**在各自环境执行以保持结构一致。
- **CI 与云端首次部署**：使用全新库，在临时/新库上执行 `alembic upgrade heads`。
- **本地方式 B**：默认使用持久化卷的 Postgres，库中可能已有历史数据与 schema；若要从零复现 CI 门禁，请先运行**临时库迁移门禁**（见下）再运行方式 B。
- **补表兜底**：当迁移失败且检测到缺失表时，部署脚本会先创建缺失表所在的 schema（如 `core`、`a_class`、`c_class`），再执行 `Base.metadata.create_all` 补表，避免 `schema "core" does not exist` 等错误；表/字段的增删改仍应通过迁移完成，补表只建缺失表、不改已有表结构。

---

## 二、本地 Docker 化部署验证（在 CI/CD 前发现问题）

目标：在**推 tag / 触发 CI 之前**，用与生产一致的顺序在本地跑一遍：迁移、Bootstrap、Metabase 启动、Phase 3.5、健康与接口检查，减少在 CI/CD 中才暴露的问题。

### 2.1 方式 A：日常开发栈 + Phase 3.5 与接口验证（推荐先做）

适用：已用 `python run.py --use-docker --with-metabase` 起好本地环境。

```bash
# 1. 启动本地 Docker 全栈（含 Metabase）
python run.py --use-docker --with-metabase

# 2. 等待后端与 Metabase 就绪后，执行 Phase 3.5 等效 + 集成检查
python scripts/verify_deploy_phase35_local.py --metabase-url http://localhost:8080 --backend-url http://localhost:8001
```

- 会执行：Metabase 健康 → `init_metabase.py` → Backend 健康 → Metabase 代理健康 → Dashboard KPI（按名称查 Question）。
- **不覆盖**：Phase 2 迁移、Phase 2.5 Bootstrap（本地 dev 通常已做过或不需要）。

适合：**确认 Metabase 与后端按名称查 Question、Dashboard 数据正常**，以及 config/sql 与 init_metabase.py 的变更无误。

### 2.2 方式 B：本地「生产 compose」全流程验证（与生产最接近）✅ 已实现

适用：想在本地完整走一遍与服务器相同的顺序（迁移 → Bootstrap → Metabase → Phase 3.5 → 应用），**部署云端 Linux 前必跑**。

**前提**：本机已安装 Docker、Docker Compose v2，以及项目根目录存在 `.env`（可选；脚本会生成 `.env.cleaned`）。

**一键执行**（推荐部署前执行，**不要**加 `--no-build`，否则旧镜像可能缺少 `init_metabase.py`）：

```bash
python scripts/verify_deploy_full_local.py
```

**可选**：跳过构建以节省时间（仅当确认当前 backend 镜像已含 `init_metabase.py` 时）：

```bash
python scripts/verify_deploy_full_local.py --no-build
```

**发布前若需与 CI 完全对齐**：可先运行 `python scripts/validate_migrations_fresh_db.py`（临时库门禁，在全新临时 Postgres 上跑 `alembic upgrade heads`，不碰开发库），再运行 `verify_deploy_full_local.py`。本方案**不提供**会清空开发库的 `--fresh-db`，避免误伤本地数据。

**脚本行为**：使用 `docker-compose.yml` + `docker-compose.prod.yml` + `docker-compose.metabase.yml` + `docker-compose.verify-local.yml`（覆盖 `DATABASE_URL=postgres:5432` 与宿主机端口 8001/8080），按顺序执行：

1. Phase 0.5：清洗 `.env` → `.env.cleaned`  
2. Phase 1：启动 PostgreSQL、Redis，等待健康  
3. Phase 2：`alembic upgrade heads`（**失败则终止验证**，与 CI 一致）  
4. Phase 2.5：`bootstrap_production.py`  
5. Phase 3：启动 Metabase，等待健康  
6. Phase 3.5：`init_metabase.py`（需 backend 镜像内含该脚本，否则请去掉 `--no-build` 重新构建）  
7. Phase 4：启动 Backend，等待健康  
8. **结构一致性检查**：`scripts/verify_schema_consistency.py`（默认 `--ignore-schema`，只校验表名存在；严格校验 schema 一致请单独运行不加 `--ignore-schema`）  
9. 集成检查：`/health`、`/api/metabase/health`、`/api/dashboard/business-overview/kpi`  

**说明**：若出现 `Can't locate revision identified by 'xxx'`，表示当前库的迁移链与代码中 `migrations/versions` 不一致，需在本地执行 `alembic history` 与 `alembic current` 排查；Phase 2 迁移失败时脚本会退出，不再继续后续阶段。结构一致性检查若失败（表缺失或 schema 与 schema.py 不一致），可先以 `--ignore-schema` 仅校验表名存在，或更新 schema.py 与迁移结果一致后重跑严格检查。

### 2.3 本地验证清单（手动或半自动）

在打 tag 前，建议至少完成以下项（可勾选）：

- [ ] **临时库迁移门禁**：执行 `python scripts/validate_migrations_fresh_db.py` 通过（在全新临时 Postgres 上跑 `alembic upgrade heads`，不碰开发库）。
- [ ] **迁移**：本地临时库或本地 Docker 库执行 `alembic upgrade heads` 无报错，表数量/关键表存在符合预期。
- [ ] **Metabase 配置**：`config/metabase_config.yaml` 与 `sql/metabase_models/*.sql`、`sql/metabase_questions/*.sql` 已提交且无语法/路径错误。
- [ ] **Phase 3.5 等效**：`python scripts/verify_deploy_phase35_local.py` 通过（Metabase 健康 → init_metabase.py → Backend 健康 → Dashboard KPI 返回数据）。
- [ ] **单元测试**：`pytest tests/test_metabase_question_service.py -v` 通过。
- [ ] **（可选）本地生产流程**：按 2.2 在本地用生产 compose 跑通迁移 → Bootstrap → Metabase → Phase 3.5 → 应用 → 健康/接口检查。

### 2.4 与 CI 的对应关系

| 本地验证项 | CI 中对应 |
|------------|-----------|
| **临时库迁移门禁**（`python scripts/validate_migrations_fresh_db.py`） | CI 的 **Validate Database Migrations**（临时 PostgreSQL + `alembic upgrade heads`） |
| 迁移可执行、表完整 | `validate` job：临时 PostgreSQL + `alembic upgrade heads` + 关键表检查 |
| init_metabase.py + Dashboard KPI | 部署阶段 Phase 3.5 + 应用启动后由业务/健康检查间接覆盖 |
| API 契约、前端 API、数据库字段 | `validate` job：validate_api_contracts、validate_frontend_api_methods、validate_database_fields |

临时库门禁仅使用临时容器，不触碰开发库数据；本方案不提供清空开发库的 `--fresh-db`。

本地先做 2.1 + 2.3 的「Phase 3.5 + 迁移 + 清单」，再打 tag，可以大幅降低在 CI/CD 中才暴露问题的概率。

### 2.5 部署验证后的数据迁移

完成本变更验证与云端部署修复后，若需将**本地数据库数据上传到云端**，推荐使用**做法一（完整库迁移）**：

1. 在本地 `.env` 或环境中配置 **`CLOUD_DATABASE_URL`**（云端 PostgreSQL 连接串，需本机可访问或经 SSH 隧道映射）。
2. 执行：`./scripts/migrate_data.sh --mode full --source local --target cloud`（可先加 `--dry-run` 预览）。

**注意**：Windows 上需在 **Git Bash** 或 **WSL** 下执行 `./scripts/migrate_data.sh`。详见 `docs/guides/DATA_MIGRATION_GUIDE.md`。

---

## 三、常见问题

**Q：云端已有库，这次发布新增了迁移，会重复执行吗？**  
A：不会。部署脚本检测到 `alembic_version` 存在后，只执行 `alembic upgrade heads`，只会跑尚未应用的迁移。

**Q：Metabase 里我删掉了某个 Question，但 config 里还留着，部署会怎样？**  
A：`init_metabase.py` 会按名称创建缺失的 Question；若你希望云端也删掉，需在 Metabase UI 手动删除，或后续在脚本中扩展「按 config 同步删除」逻辑。

**Q：如何确认本次部署是否执行了 Phase 3.5？**  
A：在服务器上查看部署日志，搜索 `Phase 3.5` 和 `init_metabase.py`；或部署后调用 Dashboard KPI 等接口，能按名称拿到数据即说明 Phase 3.5 与后端按名称解析均生效。

**Q：本地没有 bash，无法直接跑 deploy_remote_production.sh？**  
A：生产部署在 GitHub Actions 的 Linux 环境中执行该脚本；本地用「方式 A」的 `verify_deploy_phase35_local.py` 即可覆盖 Phase 3.5 与集成验证。若需完整顺序，可用 WSL 或 Git Bash 按 2.2 执行等价步骤。

**Q：部署后服务器镜像太多占空间，如何只保留最近几个？**  
A：在服务器 `.env`（或部署所用环境变量）中设置 **`KEEP_IMAGES_COUNT=2`**（或其它数字）。`deploy_remote_production.sh` 在部署成功后会按该数量保留最新的 backend/frontend 镜像并清理更旧的；未设置时脚本默认保留 5 个。模板见 `env.production.example` 中的「部署与镜像清理」小节。

---

## 四、相关文件与命令速查

| 用途 | 文件/命令 |
|------|-----------|
| 部署脚本（服务器执行） | `scripts/deploy_remote_production.sh` |
| Metabase 初始化（Phase 3.5） | `scripts/init_metabase.py` |
| **方式 B：本地生产流程验证（推荐部署前执行）** | `python scripts/verify_deploy_full_local.py` |
| 方式 B 使用的 Compose 覆盖 | `docker-compose.verify-local.yml`（端口 8001/8080 + DATABASE_URL 覆盖） |
| 本地 Phase 3.5 + 集成验证（方式 A） | `python scripts/verify_deploy_phase35_local.py` |
| **临时库迁移门禁**（与 CI Validate Database Migrations 等价） | `python scripts/validate_migrations_fresh_db.py`（可选 `--port 5433`） |
| 仅集成测试（后端已起） | `python scripts/test_metabase_question_integration.py --base-url http://localhost:8001` |
| Metabase 服务按名称查 Question 单元测试 | `pytest tests/test_metabase_question_service.py -v` |
| CI/CD 流程说明 | `docs/CI_CD_DEPLOYMENT_GUIDE.md` |

以上流程可以保证：**数据表与 Metabase 的变更都通过 Git 纳入版本，云端更新由同一套脚本自动执行迁移与 init_metabase；本地先用 Docker 做 Phase 3.5 与（可选）全流程验证，再打 tag，避免只在 CI/CD 才发现问题。**
