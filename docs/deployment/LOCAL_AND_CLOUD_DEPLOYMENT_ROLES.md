# 本地与云端部署角色说明（ENABLE_COLLECTION / DEPLOYMENT_ROLE）

> 对应 OpenSpec 变更：`add-local-cloud-deployment-role`  
> 目标：同一套代码库，清晰区分「本地采集环境」与「云端运作环境」，并配合双镜像（默认 + full）与本地→云端同步。

---

## 1. 部署角色与环境变量

### 1.1 核心原则

- **单后端**：本地与云端环境都只运行一个后端容器（或进程），不出现「起两个后端再停一个」的流程。
- **角色由环境变量决定**：
  - `ENABLE_COLLECTION`：是否启用采集调度器。
  - `DEPLOYMENT_ROLE`：角色标识，`local`=本地/采集环境，`cloud`=云端/只读环境。

### 1.2 行为约定

- 当满足以下任一条件时，**不启动采集调度器**：
  - `ENABLE_COLLECTION` 显式为 `false` / `0`
  - `DEPLOYMENT_ROLE=cloud`
- 仅当：
  - `ENABLE_COLLECTION=true`（或未设置但默认为 true），**且**
  - `DEPLOYMENT_ROLE` 不是 `cloud`  
  时，后端才会创建并启动 `CollectionScheduler`，加载定时采集配置。

> 代码位置：`backend/main.py` 中初始化 `CollectionScheduler` 的逻辑。

---

## 2. 镜像策略：默认镜像 vs full 镜像

### 2.1 镜像类型

- **默认镜像（backend）**
  - Dockerfile：`Dockerfile.backend`
  - 特点：不包含 Playwright / 浏览器依赖，适合云端只跑 API 与看板。
- **full 镜像（backend-full）**
  - Dockerfile：`Dockerfile.collection`
  - 特点：内置 Playwright 与浏览器依赖，供本地/采集环境使用。

### 2.2 CI 构建（双镜像）

> 触发：`push` 到 `main/develop`，或打 tag `v*`。

- `.github/workflows/docker-build.yml`
  - 使用 `Dockerfile.backend` 构建默认 backend 镜像。
  - 使用 `Dockerfile.collection` 再构建 **backend-full 镜像**，在同一镜像名下带 `-full` 后缀 tag，例如：
    - `ghcr.io/<owner>/<repo>/backend:4.22.4`
    - `ghcr.io/<owner>/<repo>/backend:4.22.4-full`
    - `ghcr.io/<owner>/<repo>/backend:v4.22.4`
    - `ghcr.io/<owner>/<repo>/backend:v4.22.4-full`
- `.github/workflows/deploy-production.yml`
  - 在发布 tag（`v*`）时，同样构建并推送：
    - 默认 backend 镜像（Dockerfile.backend）
    - full backend 镜像（Dockerfile.collection，带 `-full` tag）

> 前者用于云端生产部署，后者供本地/采集服务器拉取使用。

---

## 3. 典型部署流程

### 3.1 发布新版本（CI）

1. 在本地打 tag，例如：
   ```bash
   git tag v4.22.4
   git push origin v4.22.4
   ```
2. GitHub Actions `deploy-production.yml` 被触发：
   - 通过一系列 **Release Gate** 校验（迁移测试、API 契约验证等）。
   - 使用 `Dockerfile.backend` 构建并推送默认 backend 镜像。
   - 使用 `Dockerfile.collection` 构建并推送 backend-full 镜像（带 `-full` 后缀）。

### 3.2 云端生产环境部署（只读）

- 目标：只跑 API / 看板，不在云端拉起采集。
- 关键配置：
  - 镜像：**默认 backend 镜像**（不包含 Playwright）。
  - 环境变量：
    - `ENABLE_COLLECTION=false`
    - 或者 `DEPLOYMENT_ROLE=cloud`
    - `DATABASE_URL` 指向 **云端 PostgreSQL**。
- 效果：
  - `CollectionScheduler` 不会启动。
  - 云端仅处理 API 请求和前端看板，数据库只读（写操作来自同步后的数据和日常业务）。

### 3.3 本地 / 采集环境部署

- 目标：负责 **数据采集与同步**，不直接对外提供 SaaS。
- 关键配置：
  - 镜像：**backend-full**（由 `Dockerfile.collection` 构建，tag 带 `-full`）。
  - 环境变量：
    - `ENABLE_COLLECTION=true`
    - 或 `DEPLOYMENT_ROLE=local`
    - `DATABASE_URL` 指向 **本地 PostgreSQL**（采集库）。
    - `CLOUD_DATABASE_URL` 指向 **云端 PostgreSQL**（同步目标库，用于本地→云端同步脚本）。
- 效果：
  - 本机/服务器定时执行采集任务（由 `CollectionScheduler` 驱动）。
  - 数据落入本地 `b_class`，随后通过独立脚本同步到云端库（详见 `add-local-to-cloud-sync` 提案）。

---

## 4. 日常运作流程（推荐节奏）

> 与 `add-local-to-cloud-sync` 配合使用时的典型生产节奏。

### 4.1 采集与同步时段

- **采集时段**（示例）：
  - 每天：`06:00 / 12:00 / 18:00 / 22:00`
  - 由本地/采集环境的 `CollectionScheduler` 触发采集任务。
- **同步时段**（与采集错峰）：
  - 每天：`06:30 / 12:30 / 18:30 / 22:30`
  - 在本地环境通过 Cron 执行本地→云端同步脚本（将 `b_class` 增量推送到云端库）。

### 4.2 云端职责

- 云端只读云端数据库，不执行采集、不执行同步脚本。
- 前端/看板通过云端 API 阅读最新同步后的数据。

---

## 5. 本机采集开发与验证

开发环境下，可以直接使用 `run.py` 启动**完整采集环境**（单后端 + Playwright）进行验证。

### 5.1 启动命令

```bash
python run.py --use-docker --with-metabase --collection
```

- 后端使用 `Dockerfile.collection`（等价于拉取 backend-full 镜像）。
- Compose 组合：`docker-compose.yml` + `docker-compose.dev.yml` + `docker-compose.collection-dev.yml` + Metabase 相关文件。
- `docker-compose.collection-dev.yml` 中为 backend 注入：
  - `ENABLE_COLLECTION="true"`
  - `shm_size: "2gb"`

### 5.2 等价 docker-compose 命令（排查用）

```bash
docker-compose \
  -f docker-compose.yml \
  -f docker-compose.dev.yml \
  -f docker-compose.collection-dev.yml \
  -f docker-compose.metabase.yml \
  -f docker-compose.metabase.dev.yml \
  --profile dev-full up -d
```

停止与日志参考：`docs/deployment/LOCAL_COLLECTION_DEV.md`。

---

## 6. 核对清单（避免常见错误）

### 6.1 云端环境

- [ ] 使用 **默认 backend 镜像**（无 Playwright）。
- [ ] `ENABLE_COLLECTION=false` 或 `DEPLOYMENT_ROLE=cloud`。
- [ ] `DATABASE_URL` 指向云端库。
- [ ] 未在云端配置本地→云端同步脚本的 Cron。

### 6.2 本地 / 采集环境

- [ ] 使用 **backend-full 镜像**（`-full` tag 或等价本地构建）。  
- [ ] `ENABLE_COLLECTION=true` 或 `DEPLOYMENT_ROLE=local`。
- [ ] `DATABASE_URL` 指向本地采集库。
- [ ] 已配置 `CLOUD_DATABASE_URL`（云端库连接串）。
- [ ] 已配置 4 个采集时段的调度（见 collection scheduler）。
- [ ] 已配置与采集错峰的 4 个本地→云端同步 Cron。

### 6.3 本机开发（可选）

- [ ] 本机可通过 `python run.py --use-docker --with-metabase --collection` 启动完整采集环境。
- [ ] 采集任务在本机能正常执行，调度与云端部署设计一致。

