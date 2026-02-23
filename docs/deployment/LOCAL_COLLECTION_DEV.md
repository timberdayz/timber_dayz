# 本机采集环境测试（Docker）

**变更**: add-local-cloud-deployment-role（方案 A）

## 用途

在开发环境下，使用与正式采集环境一致的 Docker 化架构启动项目，便于：

- 验证采集环境的 Docker 化是否正常
- 减少未来部署到 Linux 服务器时因环境差异导致的问题

## 启动命令

```bash
python run.py --use-docker --with-metabase --collection
```

- **效果**：单后端、端口 8001，backend 使用 `Dockerfile.collection`（带 Playwright），具备采集与同步能力；前端、Postgres、Redis、Celery、Metabase 一并启动。
- **等价 Compose 命令**（排查时可手动执行）：
  ```bash
  docker-compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.collection-dev.yml -f docker-compose.metabase.yml -f docker-compose.metabase.dev.yml --profile dev-full up -d
  ```

## 停止与日志

- **停止**（采集模式）：
  ```bash
  docker-compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.collection-dev.yml -f docker-compose.metabase.yml -f docker-compose.metabase.dev.yml --profile dev-full down
  ```
- **查看后端日志**：
  ```bash
  docker-compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.collection-dev.yml logs -f backend
  ```

## 说明

- 本机采集开发使用 **Dockerfile.collection** 通过 **docker-compose.collection-dev.yml** 覆盖 backend 服务；CI 双镜像时 full 镜像由 Dockerfile.collection 构建。
- 环境变量 `ENABLE_COLLECTION=true` 由 collection-dev 覆盖注入，采集调度器会启动；云端部署时使用 `ENABLE_COLLECTION=false` 或 `DEPLOYMENT_ROLE=cloud` 则不启动调度器。
