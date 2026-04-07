# Docker Compose Profiles 说明

本文档说明西虹 ERP 各 Docker Compose Profile 的用途与对应命令，便于统一本地开发与云端部署流程。

## Profile 一览

| Profile      | 用途说明                     | 典型启动命令 |
|-------------|------------------------------|--------------|
| `dev`       | 仅基础设施（postgres、redis） | `docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev up -d` |
| `dev-full`  | 开发全栈（含 backend、celery-worker） | `python run.py --use-docker` 或同上加 `--profile dev-full up -d backend celery-worker` |
| `production`| 生产部署（backend、frontend、nginx、celery 等） | `docker-compose -f docker-compose.yml -f docker-compose.prod.yml --profile production up -d` |
| `full`      | 生产全栈（与 production 重叠，视具体 compose 定义） | 见 docker-compose.prod.yml |

## 本地开发（推荐）

```bash
# 一键启动（postgres + redis + backend，前端本地 npm run dev）
python run.py --use-docker

# 需要 Metabase 时
python run.py --use-docker --with-metabase
```

上述命令会：

- 使用 `docker-compose.yml` + `docker-compose.dev.yml`（及 Metabase 相关 compose）
- 使用 Profile：`dev`（先起 postgres/redis）、`dev-full`（再起 backend）
- 前端仍在本地以 `npm run dev` 运行，访问 `http://localhost:5173`

## 生产 / 云端部署

```bash
# 生产环境（按部署文档使用 prod/cloud compose）
docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml --profile production up -d
```

## 环境变量与 Profile

- 开发：默认使用 `.env`，可配合 `env.development.example` 复制为 `.env.development` 做覆盖。
- 生产：必须使用独立 `.env.production` 或等价配置，且 **不得** 使用开发默认密码。
- 与 Redis/DB 等相关的默认值（如 `redis_pass_2025`）仅作开发默认，生产须改用强密码并写入对应环境变量。

## 相关文档

- [CLAUDE.md](../CLAUDE.md) — 常用开发命令与架构说明
- [env.example](../env.example) / [env.production.example](../env.production.example) — 环境变量模板
