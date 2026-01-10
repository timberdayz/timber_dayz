# CI/CD 自动部署指南（v4.21.0 - 方案 A 长期稳定版）

## [OVERVIEW] 概述

本文档说明西虹 ERP 系统的 CI/CD 自动部署流程。完成方案 A 优化后，实现：

- [OK] **本地开发/测试** → `git push` → 仅构建镜像（不自动部署）
- [OK] **正式上线** → `git tag vX.Y.Z && git push origin vX.Y.Z` → 同一个 workflow 内完成构建 + 部署生产

## [NOTE] 方案 A 核心改进（v4.21.0）

**之前的问题**：

- 构建和部署分属不同 workflow，使用 `workflow_run` 触发时无法可靠获取 tag（`IMAGE_TAG` 可能为空）
- 导致镜像拉取失败：`Error response from daemon: manifest unknown`

**方案 A 的优势**：

- [OK] 构建和部署在同一个 workflow 内完成，tag 来源唯一且可靠（直接从 `GITHUB_REF_NAME` 获取）
- [OK] 避免了 `workflow_run` 跨 workflow 传参不稳定的问题
- [OK] 构建成功后才部署，顺序严格，可回滚（部署旧 tag）

---

## [WORKFLOW] 用户操作流程

### 日常开发/测试

```bash
# 1. 本地开发和测试
# ... 编写代码 ...

# 2. 提交并推送到 GitHub（不触发生产部署）
git add .
git commit -m "feat: 添加新功能"
git push origin main
```

**结果**：

- [OK] GitHub Actions 自动触发 `Docker Build and Push` workflow
- [OK] 构建并推送镜像到 `ghcr.io`（标签：`main-<sha>`, `latest` 等）
- [SKIP] **不触发**生产部署（安全）

### 正式上线（方案 A：推荐流程）

```bash
# 1. 确保代码已合并到 main 分支并测试通过
git checkout main
git pull origin main

# 2. 打版本标签并推送（自动触发构建+部署）
git tag v4.21.0
git push origin v4.21.0
```

**结果**：

- [OK] GitHub Actions 自动触发 `Deploy to Production` workflow
- [OK] 在同一个 workflow 内完成：
  1. **验证阶段（发布门禁）**：执行 `Validate Data Flow` 的关键校验（失败会阻断发布）
  2. **构建阶段**：构建 Backend 和 Frontend 镜像，推送到 `ghcr.io`（标签：`v4.21.0`, `4.21.0` 等）
  3. **部署阶段**：服务器自动拉取镜像并部署到生产环境
- [OK] Tag 来源唯一且可靠（直接从 `GITHUB_REF_NAME` 获取，不会出现 `IMAGE_TAG` 为空的问题）

### 手动部署/回滚（紧急情况）

如果需要部署指定版本或回滚到之前的版本，可以通过 GitHub Actions 手动触发：

1. 打开 GitHub 仓库 → Actions → `Deploy to Production`
2. 点击 "Run workflow"
3. 输入参数：
   - `image_tag`: 例如 `v4.20.5`（要部署的版本）
   - `confirm`: `DEPLOY`
4. 点击 "Run workflow" 按钮

**注意**：手动部署**不会重新构建镜像**，只部署指定 tag 的镜像（适用于回滚或重试）

---

## [PROCESS] 自动部署流程（方案 A）

### 方案 A 架构：构建和部署在同一 workflow 内

**核心变化**：

- [OK] `push tag v*` 触发 `Deploy to Production` workflow
- [OK] 在同一个 workflow 内先完成 build & push，再执行 deploy
- [OK] Tag 直接从 `GITHUB_REF_NAME` 获取，100% 可靠
- [OK] `Docker Build and Push` workflow 不再响应 `push tag v*`，避免重复构建

### 1. 构建阶段（`Deploy to Production` → `build-and-push` job）

**触发条件**：

- `push` `v*` 标签（**自动触发构建+部署**）
- 手动触发 `workflow_dispatch`（**仅部署，不构建**）

**执行步骤**（仅 tag push 时）：

1. 检出代码（使用 tag ref）
2. 设置 Docker Buildx
3. 登录到 `ghcr.io`
4. 提取元数据（tags: `vX.Y.Z`, `X.Y.Z`, `vX.Y`, `X.Y`, `sha-xxx`）
5. 构建 Backend 镜像（`Dockerfile.backend`）
6. 构建 Frontend 镜像（`Dockerfile.frontend`）
7. 推送到 `ghcr.io`（多标签推送，确保部署时能找到）

### 2. 部署阶段（`Deploy to Production` → `deploy-tag` 或 `deploy-manual` job）

**触发条件**：

- **Tag Push 触发**：`deploy-tag` job（依赖 `build-and-push`）
- **手动触发**：`deploy-manual` job（独立运行，不构建镜像）

**Tag Push 流程**：

1. 等待 `build-and-push` job 成功完成
2. 使用 `GITHUB_REF_NAME`（例如 `v4.21.0`）作为镜像 tag
3. 执行部署步骤（见下方）

**手动触发流程**：

1. 直接使用用户输入的 `image_tag`
2. 不构建镜像（假设镜像已存在）
3. 执行部署步骤

**执行步骤**：

#### 2.1 检查配置

- 验证必要的 GitHub Secrets 已配置
- 验证部署确认（手动触发时）

#### 2.2 同步 Compose 文件到服务器

- [OK] 方案 A1：直接使用 `scp` 上传 compose 文件（简单、稳定）
- [OK] 上传文件：`docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.cloud.yml`, `docker-compose.metabase.yml`
- [NOTE] compose 文件很小（几 KB 到几十 KB），对带宽影响很小

#### 2.3 备份当前部署

- 备份 `docker-compose.config.yaml`
- 备份当前运行的容器列表

#### 2.4 分阶段部署服务

**阶段 0.5：环境变量清洗** ⭐ 新增（v4.21.0+）

```bash
# 清洗 .env 文件（去除 CRLF 和尾随空格）
sed -e 's/\r$//' -e 's/[ \t]*$//' "${PRODUCTION_PATH}/.env" > "${PRODUCTION_PATH}/.env.cleaned"
# 所有后续 docker-compose 命令统一使用 --env-file "${PRODUCTION_PATH}/.env.cleaned"
```

**阶段 1：基础设施层**

```bash
# 启动 PostgreSQL 和 Redis
docker-compose ... --env-file "${PRODUCTION_PATH}/.env.cleaned" up -d postgres redis
# 等待健康检查通过
```

**阶段 2：数据库迁移**

```bash
# 执行数据库迁移（Alembic）
docker-compose ... --env-file "${PRODUCTION_PATH}/.env.cleaned" run --rm --no-deps backend alembic upgrade head
# 失败时阻断部署
```

**阶段 2.5：Bootstrap 初始化** ⭐ 新增（v4.21.0+）

```bash
# 执行 Day-1 Bootstrap（创建基础角色、可选管理员账号）
docker-compose ... --env-file "${PRODUCTION_PATH}/.env.cleaned" run --rm --no-deps backend \
  python3 /app/scripts/bootstrap_production.py
# 失败时阻断部署
```

**Bootstrap 功能**：
- 验证环境变量（CRLF检查、默认值检查）
- 创建基础角色（admin, manager, operator, finance）- 幂等
- 可选：创建管理员账号（需显式启用，默认关闭）

**阶段 3：Metabase（生产必需组件）**

```bash
# 启动 Metabase（必须在 Nginx 之前启动）
docker-compose -f docker-compose.metabase.yml --profile production up -d metabase
# 等待健康检查通过（最多60秒）
```

**阶段 4：应用层**

```bash
# 启动 Backend、Celery Worker、Celery Beat、Celery Exporter
docker-compose ... --env-file "${PRODUCTION_PATH}/.env.cleaned" up -d backend celery-worker celery-beat celery-exporter
# 等待 Backend 健康检查通过
```

**阶段 4b：前端层**

```bash
# 启动 Frontend
docker-compose ... --env-file "${PRODUCTION_PATH}/.env.cleaned" up -d frontend
# 等待健康检查通过
```

**阶段 5：网关层（最后启动）**

```bash
# 启动 Nginx（依赖所有上游服务）
docker-compose ... --env-file "${PRODUCTION_PATH}/.env.cleaned" up -d nginx
# 等待健康检查通过
```

**部署后清理**：

```bash
# 部署成功后删除 .env.cleaned（避免敏感信息残留）
rm -f "${PRODUCTION_PATH}/.env.cleaned"
```

#### 2.5 健康检查验证

- Backend 健康检查（容器内部）
- Frontend 健康检查（容器内部）
- Nginx 健康检查（端口 80）
- 外部健康检查（`PRODUCTION_URL`，支持 HTTP/HTTPS 降级）

---

#### 2.4 镜像拉取（带容错机制）

**Tag 拉取策略**：

- [OK] 先尝试主 tag（例如 `v4.21.0`）
- [OK] 如果失败，自动尝试不带 `v` 前缀的 tag（例如 `4.21.0`）
- [OK] 确保无论构建时推送哪种格式的 tag，部署都能成功

**重试机制**：

- 每个 tag 最多重试 3 次，每次间隔 5 秒
- 如果都失败，显示可用的 tag 列表并退出

## [CONFIG] 关键配置

### GitHub Secrets（必需）

| Secret                       | 说明                         | 示例                                     |
| ---------------------------- | ---------------------------- | ---------------------------------------- |
| `PRODUCTION_SSH_PRIVATE_KEY` | 生产服务器 SSH 私钥          | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `PRODUCTION_HOST`            | 生产服务器地址               | `134.175.222.171`                        |
| `PRODUCTION_USER`            | SSH 用户                     | `deploy`                                 |
| `PRODUCTION_PATH`            | 部署路径                     | `/opt/xihong_erp`                        |

### 服务器端环境变量（.env 文件）

**必需变量**：

```bash
# 数据库配置
DATABASE_URL=postgresql://user:password@postgres:5432/xihong_erp

# 安全配置（必须使用强随机值，不能使用默认值）
SECRET_KEY=your-32-char-random-string  # ⚠️ 不能使用默认值
JWT_SECRET_KEY=your-32-char-random-string  # ⚠️ 不能使用默认值

# 其他配置...
```

**Bootstrap 相关变量**（可选）：

```bash
# 管理员创建（可选，默认关闭）
BOOTSTRAP_CREATE_ADMIN=false  # 必须显式设置为 true 才会创建
BOOTSTRAP_ADMIN_USERNAME=admin  # 可选，默认 admin
BOOTSTRAP_ADMIN_PASSWORD=your-secure-password  # 必须设置（如果启用创建）
BOOTSTRAP_ADMIN_EMAIL=admin@xihong.com  # 可选，默认 admin@xihong.com
```

**注意事项**：
- `.env` 文件会在部署时自动清洗（去除 CRLF 和尾随空格）
- 所有 secrets 必须来自服务器 `.env` 文件或 secrets 文件，不能硬编码
- 生产环境禁止使用默认占位符（如 `your-secret-key-change-this`）
| `PRODUCTION_URL`             | 生产环境 URL（用于健康检查） | `https://www.xihong.site`                |
| `GITHUB_TOKEN`               | GitHub Token（自动提供）     | -                                        |

### 服务器环境要求

- [OK] Docker 和 Docker Compose 已安装
- [OK] 部署用户（`deploy`）在 `docker` 组中
- [OK] `.env` 文件权限允许部署用户读取（推荐：`600` 或 `640`）
- [OK] 网络连接正常（可以访问 `ghcr.io` 拉取镜像）

**Secrets 文件权限建议**：

```bash
# 设置 .env 文件权限（仅所有者可读写）
chmod 600 .env

# 或使用 secrets 文件（更安全）
chmod 600 .secrets
```

**注意**：`.env.cleaned` 文件会在部署时自动创建，部署成功后自动删除。

---

## [IMPROVEMENTS] 关键改进点

### v4.21.0（方案 A：长期稳定版）

#### 1. [FIX] 解决 IMAGE_TAG 为空的问题（核心修复）

- [BEFORE] 构建和部署分属不同 workflow，使用 `workflow_run` 触发时无法可靠获取 tag
- [NOW] 构建和部署在同一个 workflow 内完成，tag 直接从 `GITHUB_REF_NAME` 获取，100% 可靠

#### 2. [FIX] 避免重复构建

- [BEFORE] `push tag v*` 同时触发 `Docker Build and Push` 和 `Deploy to Production`，导致重复构建
- [NOW] `Docker Build and Push` 不再响应 `push tag v*`，只有 `Deploy to Production` 响应（并在内部构建）

#### 3. [IMPROVE] 镜像拉取容错机制

- [OK] 先尝试带 `v` 前缀的 tag（例如 `v4.21.0`）
- [OK] 如果失败，自动尝试不带 `v` 前缀的 tag（例如 `4.21.0`）
- [OK] 确保无论构建时推送哪种格式的 tag，部署都能成功

### v4.20.0（历史改进）

#### 1. 解决并行竞态问题

- [OK] **之前**：`docker-build` 和 `deploy-production` 并行运行，可能导致部署时镜像不存在
- [OK] **现在**：构建和部署在同一个 workflow 内，顺序严格，不会出现竞态

#### 2. 整合 Metabase 到生产部署

- [OK] **之前**：Metabase 未启动，导致 Nginx 启动失败（无法解析 `metabase:3000`）
- [OK] **现在**：分阶段启动，确保 Metabase 在 Nginx 之前启动并健康

#### 3. 提升可追溯性

- [OK] **之前**：使用 `latest` 标签，无法确定生产环境运行的具体版本
- [OK] **现在**：直接使用 `vX.Y.Z` 标签，可以明确知道生产环境运行的版本

#### 4. 服务启动顺序优化

- [OK] **之前**：所有服务同时启动，可能导致依赖服务未就绪
- [OK] **现在**：按依赖关系分阶段启动，确保每个阶段的服务健康后再启动下一阶段

---

## [NOTES] 注意事项

### 1. 发布策略（方案 A）

- [RECOMMEND] **推荐**：使用 `push tag (v*)` 自动部署（最安全，可控）
  - 同一个 workflow 内完成构建+部署，tag 来源可靠
  - 构建成功后才部署，顺序严格
- [SKIP] **不推荐**：`push main` 自动部署（风险高，除非有强门禁）

### 2. 版本号规范（Semantic Versioning）

**版本号格式**：`v主版本号.次版本号.修订号`

- **主版本号**（5.0.0）：不兼容的 API 修改
- **次版本号**（4.21.0）：向后兼容的功能新增
- **修订号**（4.20.6）：向后兼容的问题修复

**示例**：

- `v4.20.4` → `v4.20.5`：修复 bug（补丁版本）
- `v4.20.5` → `v4.21.0`：添加新功能（小版本）
- `v4.21.0` → `v5.0.0`：重大变更（大版本）

### 3. Metabase 必需性

- [REQUIRED] **Metabase 是生产必需组件**，必须在 Nginx 之前启动
- [WARN] 如果 Metabase 未启动，Nginx 会因无法解析 `metabase:3000` 而启动失败

### 4. 镜像标签

- [OK] 生产部署使用不可变标签（`vX.Y.Z`），不使用 `latest`
- [OK] 构建时同时推送带 `v` 前缀和不带 `v` 前缀的 tag（`v4.21.0` 和 `4.21.0`）
- [OK] 部署时自动容错，确保无论哪种格式的 tag 都能拉取成功

### 5. 回滚流程

- [OK] 如果部署失败，查看 `backups/pre_deploy_<timestamp>/` 目录
- [OK] 手动回滚：使用 GitHub Actions 手动触发，输入上一个稳定版本的 tag（例如 `v4.20.5`）
- [OK] 或者重新推送旧 tag：`git tag v4.20.5 && git push origin v4.20.5`（会触发自动部署）

---

## [TIMELINE] 部署时间线（方案 A）

```
T=0s      [Deploy to Production 触发（push tag v4.21.0）]
          ├─ Job: validate（发布门禁）
          │  ├─ Validate API Contracts
          │  ├─ Validate Frontend API Methods
          │  └─ Validate Database Fields
          └─ Job: build-and-push（依赖 validate）
             ├─ 构建 Backend 镜像（~5-10分钟）
             ├─ 构建 Frontend 镜像（~3-5分钟）
             └─ 推送到 ghcr.io（标签：v4.21.0, 4.21.0, v4.21, 4.21 等）

T=10min   [build-and-push job 成功]
          └─ Job: deploy-tag（依赖 validate + build-and-push）
             ├─ 同步 Compose 文件（~30秒，SCP 上传）
             ├─ 备份当前部署（~10秒）
             ├─ 拉取镜像（~2-5分钟，取决于网络，带容错机制）
             ├─ 阶段1：基础设施层（~30秒）
             ├─ 阶段2：Metabase（~60-120秒）
             ├─ 阶段3：应用层（~60-90秒）
             ├─ 阶段4：前端层（~30-60秒）
             └─ 阶段5：网关层（~30-60秒）

T=15-20min [部署完成，服务可用]
```

**注意**：手动触发（`workflow_dispatch`）只执行 `deploy-manual` job，不构建镜像，时间线缩短为：

```
T=0s      [Deploy to Production 手动触发]
          └─ Job: deploy-manual（独立运行）
             ├─ 同步 Compose 文件（~30秒）
             ├─ 备份当前部署（~10秒）
             ├─ 拉取镜像（~2-5分钟，使用用户输入的 tag）
             └─ ... 后续部署步骤相同 ...

T=5-10min [部署完成，服务可用]
```

---

## [TROUBLESHOOTING] 故障排查

### 问题 1：部署失败 "IMAGE_TAG is empty" 或 "Failed to pull image with tag vX.Y.Z"

**原因**（方案 A 已修复）：

- [FIXED] 之前：`workflow_run` 触发时无法可靠获取 tag（`head_ref` 可能为空）
- [OK] 现在：方案 A 中 tag 直接从 `GITHUB_REF_NAME` 获取，不会出现此问题

**如果仍然出现**：

1. 检查 workflow 日志，确认 `build-and-push` job 是否成功
2. 确认镜像已推送到 `ghcr.io`：访问 `https://github.com/<org>/<repo>/pkgs/container/<image_name>`
3. 检查镜像标签是否存在：`docker pull ghcr.io/<org>/<repo>/backend:vX.Y.Z`
4. 使用手动触发，指定正确的 tag

### 问题 2：镜像拉取失败 "manifest unknown"

**原因**：镜像标签不存在或格式不匹配
**解决**（方案 A 已包含容错机制）：

1. [OK] 部署脚本会自动尝试多个 tag 格式（`v4.21.0` → `4.21.0`）
2. 如果都失败，检查构建日志，确认镜像是否成功推送
3. 检查镜像仓库，确认可用标签列表
4. 使用手动触发，指定已存在的 tag

### 问题 3：Nginx 启动失败 "host not found in upstream 'metabase:3000'"

**原因**：Metabase 服务未启动或未加入同一网络
**解决**：

1. 检查 Metabase 容器是否运行：`docker ps | grep metabase`
2. 检查网络连通性：`docker network inspect xihong_erp_erp_network`
3. 手动启动 Metabase：`docker-compose -f docker-compose.metabase.yml --profile production up -d metabase`
4. 等待 Metabase 健康后再启动 Nginx

### 问题 4：健康检查失败

**原因**：服务启动时间过长或配置错误
**解决**：

1. 查看容器日志：`docker logs xihong_erp_backend`（替换容器名）
2. 检查健康检查配置：`docker inspect <container_name> | grep -A 10 Healthcheck`
3. 手动验证健康端点：`docker exec xihong_erp_backend curl http://localhost:8000/health`
4. 检查环境变量配置：`docker exec xihong_erp_backend env | grep DATABASE`

### 问题 5：构建失败或超时

**原因**：构建时间过长或资源不足
**解决**：

1. 检查构建日志，确认失败的具体步骤
2. 优化 Dockerfile，使用多阶段构建和缓存
3. 增加构建超时时间（GitHub Actions 默认 6 小时，通常足够）
4. 检查 Docker 镜像层缓存是否有效

---

## [REFERENCES] 相关文档

- [Agent 开始指南](AGENT_START_HERE.md) - Agent 接手必读
- [部署和运维规范](DEVELOPMENT_RULES/DEPLOYMENT.md) - 详细部署规范
- [架构指南](architecture/V4_6_0_ARCHITECTURE_GUIDE.md) - 系统架构说明

---

## [SUMMARY] 总结

### 用户操作变化（方案 A）

**日常开发**：

```bash
git add .
git commit -m "feat: 添加新功能"
git push origin main
```

- [OK] 触发构建和测试，**不触发生产部署**（安全）

**正式上线**：

```bash
git tag v4.21.0
git push origin v4.21.0
```

- [OK] 自动触发 `Deploy to Production` workflow
- [OK] 在同一个 workflow 内完成构建+部署（tag 来源可靠）
- [OK] 构建成功后才部署（顺序严格）

**手动部署/回滚**：

- [OK] 通过 GitHub Actions 手动触发，指定 tag（不重新构建）

### 关键改进（v4.21.0 - 方案 A）

1. [FIX] **解决 IMAGE_TAG 为空的问题**：构建和部署在同一 workflow 内，tag 直接从 `GITHUB_REF_NAME` 获取
2. [FIX] **避免重复构建**：`Docker Build and Push` 不再响应 `push tag v*`
3. [IMPROVE] **镜像拉取容错机制**：自动尝试多个 tag 格式（`v4.21.0` → `4.21.0`）
4. [OK] **整合 Metabase**：确保启动顺序（Metabase 在 Nginx 之前）
5. [OK] **使用 tag 而非 latest**：提升可追溯性，便于回滚
6. [OK] **分阶段启动**：确保每个阶段的服务健康后再启动下一阶段

### [IMPORTANT] 重要提醒

- [WARN] **`push tag` 就是上线**，确保代码已测试通过！
- [WARN] **版本号规范**：遵循 Semantic Versioning（`v主版本号.次版本号.修订号`）
- [WARN] **Metabase 是生产必需组件**，必须在部署流程中启动
- [WARN] **回滚操作**：使用手动触发或重新推送旧 tag

---

**最后更新**：2025-01-XX（v4.21.0 - 方案 A 长期稳定版）
