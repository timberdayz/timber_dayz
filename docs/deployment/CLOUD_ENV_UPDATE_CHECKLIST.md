# 云端 .env 更新清单

> 历史兼容说明：本文仍含旧版 Metabase 环境变量项。
> 当前生产主路径下，不应再把 Metabase 变量视为现役必需项。

更新云端 `/opt/xihong_erp/.env` 后，按此清单操作可避免数据库连接失败等问题。

## 一、必须检查的变量（密码含 @ 或 % 时）

| 变量 | 要求 | 示例 |
|------|------|------|
| `POSTGRES_PASSWORD` | 与 PostgreSQL 实际密码一致（注意大小写）；含特殊字符时用双引号 | `"AXYSh20%@7j*GrtQjcF7K4dc"` 或 `AXYSh20%@7j*GrtQjcF7K4dc` |
| `DATABASE_URL` | **必须**使用 URL 编码：`%`→`%25`，`@`→`%40`；含特殊字符时可用双引号 | `postgresql://erp_user:AXYSh20%25%407j*GrtQjcF7K4dc@postgres:5432/xihong_erp` |
| `METABASE_DB_PASS` | 与 `POSTGRES_PASSWORD` 一致 | 同上 |
| `SECRET_KEY` | 若含 `|`，必须用双引号包裹，否则部署时 `source .env` 会被 bash 当管道解析导致截断 | `"m1UuhoOYH1|B11-fOsh-..."` |

> **原因 1**：`docker-compose` 直接使用 `.env` 中的 `DATABASE_URL`，密码中的 `@` 在 URL 中必须编码为 `%40`。  
> **原因 2**：部署脚本会 `source .env`，若值中含 `|`、`*` 等未加引号，bash 会误解析（如 `|` 当管道），导致变量被截断或报错。

## 二、更新步骤

1. **本地准备**：确认 ` .env.production` 内容正确，`POSTGRES_PASSWORD`、`DATABASE_URL`、`METABASE_DB_PASS` 三者密码一致且 `DATABASE_URL` 已正确编码。

2. **覆盖云端 .env**（任选其一）：
   ```bash
   # 方式 A：scp 覆盖
   scp .env.production deploy@<服务器IP>:/opt/xihong_erp/.env

   # 方式 B：SSH 登录后手动编辑
   ssh deploy@<服务器IP>
   cd /opt/xihong_erp
   nano .env
   ```

3. **重启服务**：
   ```bash
   cd /opt/xihong_erp
   docker-compose down
   docker-compose up -d
   # 或按实际使用的 compose 组合，例如：
   # docker-compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.cloud.yml -f docker-compose.metabase.yml --profile production up -d
   ```

4. **验证**：
   ```bash
   docker-compose ps          # 确认 backend 为 healthy
   docker-compose logs backend --tail 50   # 无 "password authentication failed"
   ```

## 三、常见错误对照

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| `password authentication failed for user "erp_user"` | ① `.env` 中密码与 PostgreSQL 当前密码不一致（数据库曾用旧密码初始化）；② `DATABASE_URL` 未正确编码 | ① 在 Postgres 容器内执行 `ALTER USER erp_user PASSWORD 'AXYSh20%@7j*GrtQjcF7K4dc';` 与 `.env` 同步；② 确保 `DATABASE_URL` 中 `%`→`%25`、`@`→`%40` |
| backend 反复 Restarting | 同上，或 Postgres 尚未就绪 | 检查日志，确认密码一致后等待 1–2 分钟再观察 |
| `fe_sendauth: no password supplied` | `DATABASE_URL` 中密码被截断或解析错误 | 检查 `@` 是否已编码为 `%40` |
| 部署时 `source .env` 报错或 SECRET_KEY 无效 | `SECRET_KEY` 等含 `|` 未加引号，被 bash 当管道解析 | 用双引号包裹含 `|`、`*` 等字符的值，见 `.env.production` |

## 四、可选：与数据库密码同步

若数据库是早期用旧密码初始化的，改 `.env` 后需让 Postgres 与 `.env` 一致：

```bash
docker exec -it xihong_erp_postgres psql -U erp_user -d xihong_erp -c "ALTER USER erp_user PASSWORD 'AXYSh20%@7j*GrtQjcF7K4dc';"
```

（将单引号内密码改为与 `.env` 中 `POSTGRES_PASSWORD` 一致。）

## 五、相关文件

- 本地配置模板：`.env.production`（含特殊字符的值已用双引号，便于部署脚本 `source`）
- 部署脚本：`scripts/deploy_remote_production.sh`（Phase 0.5 会生成 `.env.cleaned` 并去掉值两侧双引号供 docker-compose 使用）
- docker-compose：`docker-compose.yml` 中 backend 的 `DATABASE_URL` 优先使用 `.env` 中的值
