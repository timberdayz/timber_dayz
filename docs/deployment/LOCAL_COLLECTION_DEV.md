# 本机采集环境测试（Docker）

> Historical note：旧版本机采集环境文档曾附带 Metabase 组合方式。
> 当前本机采集环境应以 `collection` / `backend-full` 路径为准，
> 不再把 `--with-metabase` 或 `docker-compose.metabase*.yml` 当成默认步骤。

## 用途

在开发环境下，用与正式采集环境一致的 Docker 化方式验证：

- collection/full image 能否正常启动
- 采集与同步链路是否可用
- 本机与云端的角色边界是否符合当前部署设计

## 启动命令

```bash
python run.py --use-docker --collection
```

等价 Compose 命令：

```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.collection-dev.yml --profile dev-full up -d
```

## 停止与日志

```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.collection-dev.yml --profile dev-full down
docker-compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.collection-dev.yml logs -f backend
```

## 当前说明

- 本机采集开发使用 `Dockerfile.collection`
- `docker-compose.collection-dev.yml` 覆盖 backend 服务
- `ENABLE_COLLECTION=true` 用于本机采集环境
- 云端环境应使用 `ENABLE_COLLECTION=false` 或 `DEPLOYMENT_ROLE=cloud`

## 历史资料

如需查看旧版本机 Metabase 组合方式，请查阅：

- `archive/metabase/README.md`
- `docs/development/METABASE_LEGACY_ASSET_STATUS.md`
