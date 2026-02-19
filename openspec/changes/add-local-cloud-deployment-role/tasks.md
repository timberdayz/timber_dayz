# Tasks: 本地与云端部署角色区分

## 1. 后端：按环境变量决定是否启动采集调度器

- [ ] 1.1 在 `backend/main.py`（或采集调度器挂载处）读取 `ENABLE_COLLECTION` 或 `DEPLOYMENT_ROLE`；若为 false 或 cloud，则不创建、不启动 CollectionScheduler
- [ ] 1.2 在 .env.example 或部署文档中说明 ENABLE_COLLECTION / DEPLOYMENT_ROLE 的取值与含义（本地=true/local，云端=false/cloud）

## 2. Docker：构建参数控制 Playwright

- [ ] 2.1 在用于生产后端（及采集）的 Dockerfile 中增加 `ARG INSTALL_PLAYWRIGHT=false`
- [ ] 2.2 仅在 INSTALL_PLAYWRIGHT=true 时执行 Playwright 及浏览器依赖安装（如 `pip install playwright`、`playwright install chromium`），否则跳过
- [ ] 2.3 确认该 Dockerfile 为 CI 与本地构建实际使用的文件（Dockerfile.backend 或根 Dockerfile 的 target），并在文档中注明

## 3. CI：双镜像构建与推送

- [ ] 3.1 云端用镜像构建命令中显式传入 `--build-arg INSTALL_PLAYWRIGHT=false`（或确认默认即为 false），打主 tag（如 xihong-erp:${TAG}）并推送
- [ ] 3.2 增加一次构建：`--build-arg INSTALL_PLAYWRIGHT=true`，打 -full tag（如 xihong-erp:${TAG}-full）并推送到同一镜像仓库
- [ ] 3.3 在 CI 或部署文档中说明：云端拉主 tag，本地采集环境拉 -full tag

## 4. 文档：部署与日常运作流程

- [ ] 4.1 在 `docs/deployment/` 下新增或更新文档，包含「本地与云端部署角色」说明
- [ ] 4.2 部署核心流程：发布新版本（打 tag、push、CI 两镜像）、云端部署步骤、本地采集环境部署步骤（拉 -full、环境变量、Cron）
- [ ] 4.3 日常运作核心流程：四时段采集与数据同步、错峰本地→云端同步、云端只读；可配核对清单（避免角色混用、漏配）

## 5. 验收

- [ ] 5.1 验收：云端使用默认镜像且 ENABLE_COLLECTION=false 时，采集调度器不启动，应用正常提供 API 与看板
- [ ] 5.2 验收：本地使用 -full 镜像且 ENABLE_COLLECTION=true 时，采集调度器可正常启动并执行任务
- [ ] 5.3 验收：CI 对同一 tag 产出两个镜像并推送，文档与流程可被他人按步骤执行
