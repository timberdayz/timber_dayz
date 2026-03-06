# 云端 .env 更新清单

更新云端 `/opt/xihong_erp/.env` 后，按此清单操作可避免数据库连接失败等问题。

## 一、必须检查的变量（密码含 @ 或 % 时）

| 变量 | 要求 | 示例 |
|------|------|------|
| `POSTGRES_PASSWORD` | 与 PostgreSQL 实际密码一致（注意大小写） | `AXYSh20%@7j*GrtQjcF7K4dc` |
| `DATABASE_URL` | **必须**使用 URL 编码：`%`→`%25`，`@`→`%40` | `postgresql://erp_user:AXYSh20%25%407j*GrtQjcF7K4dc@postgres:5432/xihong_erp` |
| `METABASE_DB_PASS` | 与 `POSTGRES_PASSWORD` 一致 | `AXYSh20%@7j*GrtQjcF7K4dc` |

> **原因**：`docker-compose` 不再用 `POSTGRES_PASSWORD` 拼接 `DATABASE_URL`，而是直接使用 `.env` 中的 `DATABASE_URL`。密码中的 `@` 在 URL 中有特殊含义，必须编码为 `%40`，否则会导致连接失败。

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
| `password authentication failed for user "erp_user"` | `POSTGRES_PASSWORD` 与 `DATABASE_URL` 中密码不一致，或 `DATABASE_URL` 未正确编码 | 统一密码，确保 `DATABASE_URL` 中 `%`→`%25`、`@`→`%40` |
| backend 反复 Restarting | 同上，或 Postgres 尚未就绪 | 检查日志，确认密码一致后等待 1–2 分钟再观察 |
| `fe_sendauth: no password supplied` | `DATABASE_URL` 中密码被截断或解析错误 | 检查 `@` 是否已编码为 `%40` |

## 四、相关文件

- 本地配置模板：` .env.production`
- docker-compose 变更：`docker-compose.yml` 中 backend 的 `DATABASE_URL` 已改为优先使用 `.env` 中的值
