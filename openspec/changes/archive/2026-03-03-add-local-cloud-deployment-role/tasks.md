# Tasks: 本地与云端部署角色区分

## 1. 后端：按环境变量决定是否启动采集调度器

- [x] 1.1 在 `backend/main.py`（或采集调度器挂载处）读取 `ENABLE_COLLECTION` 或 `DEPLOYMENT_ROLE`；若为 false 或 cloud，则不创建、不启动 CollectionScheduler
- [x] 1.2 在 .env.example 或部署文档中说明 ENABLE_COLLECTION / DEPLOYMENT_ROLE 的取值与含义（本地=true/local，云端=false/cloud）

## 2. Docker：方案 A（沿用 Dockerfile.collection）

- [x] 2.1 确认现有 `Dockerfile.collection` 可用于作为「带 Playwright 的后端」镜像（与当前采集服务一致），无需修改 Dockerfile.backend 增加构建参数
- [x] 2.2 新增 `docker-compose.collection-dev.yml`：覆盖 **backend** 服务，`build.dockerfile: Dockerfile.collection`，保持端口 8001；可选增加 `environment.ENABLE_COLLECTION: "true"`、`shm_size: "2gb"`
- [x] 2.3 在文档中注明：本机采集开发使用 Dockerfile.collection 通过 collection-dev 覆盖接入，CI 双镜像时 full 镜像由 Dockerfile.collection 构建

## 3. CI：双镜像构建与推送（方案 A）

- [x] 3.1 默认镜像由 Dockerfile.backend 构建，打主 tag（如 xihong-erp:${TAG}）并推送，供云端使用
- [x] 3.2 增加一次构建：使用 **Dockerfile.collection** 构建，打 -full tag（如 xihong-erp:${TAG}-full）并推送到同一镜像仓库，供本地/服务器采集环境使用
- [x] 3.3 在 CI 或部署文档中说明：云端拉主 tag，本地采集环境拉 -full tag

## 4. 文档：部署与日常运作流程

- [x] 4.1 在 `docs/deployment/` 下新增或更新文档，包含「本地与云端部署角色」说明
- [x] 4.2 部署核心流程：发布新版本（打 tag、push、CI 两镜像）、云端部署步骤、本地采集环境部署步骤（拉 -full、环境变量、Cron）
- [x] 4.3 日常运作核心流程：四时段采集与数据同步、错峰本地→云端同步、云端只读；可配核对清单（避免角色混用、漏配）

## 5. 验收

- [x] 5.1 验收：云端使用默认镜像且 ENABLE_COLLECTION=false 时，采集调度器不启动，应用正常提供 API 与看板
- [x] 5.2 验收：本地使用 -full 镜像且 ENABLE_COLLECTION=true 时，采集调度器可正常启动并执行任务
- [x] 5.3 验收：CI 对同一 tag 产出两个镜像并推送，文档与流程可被他人按步骤执行

## 6. 本机开发/测试：采集模式一键启动

- [x] 6.1 在 run.py 中增加参数 `--collection`；当与 `--use-docker` 同时使用时，将 `docker-compose.collection-dev.yml` 加入 compose 文件列表（与 base、dev、metabase 等一并使用），使 backend 使用 Dockerfile.collection，保持单后端、端口 8001
- [x] 6.2 提供 `docker-compose.collection-dev.yml`（见 2.2），在文档中说明「采集测试」时使用 `python run.py --use-docker --with-metabase --collection` 或等价 compose 组合启动
- [x] 6.3 在 docs/deployment/ 及 run.py 帮助中说明：开发环境下采集测试使用 **`python run.py --use-docker --with-metabase --collection`** 启动项目，与正式采集环境一致、仅一个后端
