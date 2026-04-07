# 本地与云端部署角色说明（ENABLE_COLLECTION / DEPLOYMENT_ROLE）

> Historical note：旧版说明曾把 Metabase 组合启动写进本机采集路径。
> 当前角色划分应以 PostgreSQL-first 为准，不再把 `--with-metabase`
> 或 `docker-compose.metabase*.yml` 当成默认启动路径。

## 角色边界

### 云端生产环境

- 使用默认 backend 镜像
- `ENABLE_COLLECTION=false` 或 `DEPLOYMENT_ROLE=cloud`
- 只负责 API、看板和业务读写
- 不执行采集、不执行 Playwright、不执行本地到云端同步脚本

### 本地 / 采集环境

- 使用 `backend-full` / collection 路径
- `ENABLE_COLLECTION=true` 或 `DEPLOYMENT_ROLE=local`
- 负责数据采集与同步
- 可运行 Playwright 与采集调度器

## 本机采集验证

```bash
python run.py --use-docker --collection
```

等价 Compose：

```bash
docker-compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.collection-dev.yml --profile dev-full up -d
```

## 核对清单

### 云端

- [ ] 使用默认 backend 镜像
- [ ] 已关闭 collection 角色
- [ ] `DATABASE_URL` 指向云端 PostgreSQL

### 本地 / 采集

- [ ] 使用 `backend-full` 或本地 `Dockerfile.collection`
- [ ] 已启用 collection 角色
- [ ] `DATABASE_URL` 指向本地采集库
- [ ] 如需同步，已配置 `CLOUD_DATABASE_URL`

## 历史资料

如需查看旧版本机 Metabase 组合说明，请查阅：

- `archive/metabase/README.md`
- `docs/development/METABASE_LEGACY_ASSET_STATUS.md`
