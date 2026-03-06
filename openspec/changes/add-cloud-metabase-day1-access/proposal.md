# Change: 云端 Metabase 访问与首次初始化文档化 + Nginx 代理修复

## Why

系统同步到云端后，云端 Metabase 因**未完成首次初始化**（设置向导、管理员账号、PostgreSQL 数据源、API 密钥）导致看板与后端代理不可用；同时运维与用户常误以为「Metabase 端口未暴露」而无法访问，实际上生产环境**设计上不暴露** Metabase 独立端口，仅通过 Nginx 路径 `/metabase/` 访问，该访问方式与首次配置步骤缺少成文说明。

此外，实际部署中发现 Nginx 子路径代理存在**致命配置缺陷**，导致 Metabase 白屏无法完成首次初始化。本文档完整记录问题发现、根因分析与修复过程，供后续部署与排查参考。

---

## 问题发现与排查（完整记录）

### 1. 现象描述

- **用户可见**：浏览器访问 `http://www.xihong.site/metabase/` 或 `http://www.xihong.site/metabase/setup` 时，页面**白屏**，无法进入 Metabase 首次设置向导。
- **浏览器控制台**：出现 MIME type 相关错误，例如：
  ```
  Refused to execute script from '.../metabase/app/dist/styles.xxx.js' 
  because its MIME type ('text/html') is not a valid JavaScript MIME type.
  ```
- **网络面板**：对 `/metabase/app/dist/*.js`、`*.css` 的请求返回 `200 OK`，但 `Content-Type` 为 `text/html` 而非 `text/javascript` / `text/css`。

### 2. 根因：Nginx 变量 proxy_pass 不自动去除 location 前缀

**错误配置**（修复前）：

```nginx
location ^~ /metabase/ {
    set $metabase_upstream "metabase:3000";
    proxy_pass http://$metabase_upstream/;   # ← 使用变量
}
```

**为何使用变量**：Metabase 在独立 docker-compose 文件中，Nginx 启动时 Metabase 可能尚未就绪。使用 `set $var` + `resolver` 可在**请求时**解析 DNS，避免 Nginx 启动失败。这是常见做法。

**Nginx 官方行为**（关键）：

- 当 `proxy_pass` 使用**字面量**（如 `proxy_pass http://metabase:3000/;`）时，Nginx 会**自动**将 `/metabase/xxx` 重写为 `/xxx` 再转发。
- 当 `proxy_pass` 使用**变量**（如 `proxy_pass http://$metabase_upstream/;`）时，**URI 重写不生效**。即使写了尾部斜杠 `/`，Nginx 仍会原样转发完整 URI。

因此，Metabase 实际收到的是 `/metabase/app/dist/styles.xxx.js`，而非 `/app/dist/styles.xxx.js`。

### 3. 错误链：从 Nginx 到白屏

| 步骤 | 环节 | 行为 |
|-----|------|------|
| 1 | 浏览器 | 请求 `http://www.xihong.site/metabase/app/dist/styles.xxx.js` |
| 2 | Nginx | 原样转发 `/metabase/app/dist/...` 给 Metabase（因变量 proxy_pass 不重写） |
| 3 | Metabase | 仅提供 `/app/dist/...` 路径；收到 `/metabase/app/dist/...` 时**找不到文件** |
| 4 | Metabase | 按 SPA 规则返回 `index.html` 作为 fallback（`Content-Type: text/html`） |
| 5 | 浏览器 | 期望 JS，收到 HTML；因 `X-Content-Type-Options: nosniff` **拒绝执行** |
| 6 | 用户 | 页面白屏，控制台报 MIME type 错误 |

### 4. 验证对比（修复前 vs 修复后）

| 请求路径 | 修复前 Content-Type | 修复后 Content-Type |
|---------|---------------------|---------------------|
| `/metabase/app/dist/styles.xxx.js` | `text/html`（SPA fallback） | `text/javascript` |
| `/metabase/setup` | 可能白屏（依赖 JS 加载失败） | 正常加载首次设置向导 |

### 5. 次要问题：`/app/` 路径回退

当 Metabase 前端将 `base` 解析为 `/` 而非 `/metabase/` 时，浏览器会直接请求 `/app/dist/*` 而非 `/metabase/app/dist/*`。若 Nginx 未配置 `location /app/`，这些请求可能被其他规则（如 frontend 静态）处理，导致 404 或错误内容。因此需单独配置 `location /app/` 代理到 Metabase，且同样使用 `rewrite` 配合变量 `proxy_pass`。

### 6. 教训与规范（避免复现）

> **规则**：在 Nginx 中使用变量形式的 `proxy_pass`（为延迟 DNS 解析）时，**必须**搭配 `rewrite` 手动剥离 location 前缀。这是 Nginx 的已知行为差异，非 bug。

**检查清单**（新增或修改 Nginx 子路径代理时）：

1. 若使用 `set $var` + `proxy_pass http://$var`，检查是否添加了对应的 `rewrite ... break;`。
2. 用 `curl -sI "http://<host>/metabase/app/dist/xxx.js"` 验证 `Content-Type` 为 `text/javascript`，而非 `text/html`。
3. 在浏览器中访问 `/metabase/setup`，确认无白屏、无控制台 MIME 错误。

### 7. 验证结果（2026-03 云端部署）

修复并重新加载 Nginx 后，已确认：

- 浏览器访问 `http://www.xihong.site/metabase/setup` 可正常加载 Metabase 首次设置向导（"Welcome to Metabase" 页面）。
- 静态资源 `Content-Type` 正确，无 MIME type 白屏错误。
- 管理员可在此页面完成：创建账号、连接 PostgreSQL、创建 API Key 等首次初始化步骤。

### 8. 排查速查表（供后续运维参考）

| 现象 | 可能原因 | 排查命令 / 操作 |
|------|----------|-----------------|
| 白屏 + 控制台 MIME type 错误 | 变量 proxy_pass 未重写 URI，Metabase 返回 HTML fallback | `curl -sI "http://<host>/metabase/app/dist/xxx.js"` 看 Content-Type |
| 白屏 + 无控制台错误 | Host / MB_SITE_URL 不匹配，Metabase 返回空 body | 检查 `proxy_set_header Host` 与 `MB_SITE_URL` 是否与访问域名一致 |
| 404 或错误页面 | `/app/` 路径未代理到 Metabase | 确认 `location /app/` 存在且 rewrite 正确 |
| Nginx 启动失败 | Metabase 未就绪导致 upstream 解析失败 | 使用变量 + resolver 延迟 DNS 解析 |
| 数据源连接「错误的密码或用户名」 | ① 主机/用户名填错（postgresql、metabase_user、postgres.xihong.site）<br>② PostgreSQL 数据卷密码与 .env 不一致 | ① 主机填 `postgres`，用户名填 `erp_user`<br>② 执行 `ALTER USER erp_user WITH PASSWORD '...'` 同步密码，见「9. PostgreSQL 数据卷密码持久化问题」 |

### 9. PostgreSQL 数据卷密码持久化问题（2026-03 云端部署）

**现象**：Metabase 添加 xihong_erp 数据源时，使用 `.env.production` 中的 `POSTGRES_PASSWORD` 连接失败，报「错误的密码或用户名」。容器内 `docker exec xihong_erp_postgres env | grep POSTGRES` 显示密码与 .env 一致，但 TCP 连接认证仍失败。

**根因**：PostgreSQL 官方镜像仅在**首次初始化**（数据目录为空）时使用 `POSTGRES_PASSWORD` 创建用户并设置密码。若数据卷已有数据（如之前部署用过默认密码 `erp_pass_2025`），后续修改 `.env` 中的 `POSTGRES_PASSWORD` **不会**更新数据库中已有用户的密码。容器环境变量与数据库内实际密码不一致。

**验证**：用旧密码 `erp_pass_2025` 测试连接也失败，说明数据库密码可能是其他历史值。

**修复**：在 postgres 容器内执行 `ALTER USER` 将密码同步为当前 .env 值：

```bash
docker exec -it xihong_erp_postgres psql -U erp_user -d xihong_erp -c \
  "ALTER USER erp_user WITH PASSWORD 'AxYSh2O%@7j*GrtQjcF7K4dc';"
```

若 `erp_user` 本地连接需密码，可改用超级用户：`psql -U postgres`。

**教训**：首次部署或更换 PostgreSQL 密码后，若数据卷已存在，需手动执行 `ALTER USER` 同步密码，否则 Metabase、Backend 等服务的 TCP 连接会认证失败。

**数据源配置要点**（避免再次填错）：
- **主机地址**：必须填 `postgres`（Docker 服务名），勿填 `postgresql`、`postgress`、`postgres.xihong.site` 或 `localhost`
- **用户名**：`erp_user`（连接 xihong_erp 业务库），勿填 `metabase_user`（metabase_user 仅用于 Metabase 内部 metabase_app 库）

## What Changes

- **Nginx 配置修复**（`nginx/nginx.prod.conf`）：
  - `location ^~ /metabase/`：添加 `rewrite ^/metabase/(.*) /$1 break;`，手动剥离 `/metabase/` 前缀后再转发给 Metabase，并移除 `proxy_pass` 中的尾部斜杠。
  - `location /app/`：同样添加 `rewrite` 确保变量 `proxy_pass` 正确传递路径。
- **部署与运维文档**：新增或扩展「云端 Metabase 访问与首次初始化」小节，明确：
  - 云端 Metabase **仅通过** `http://<域名或IP>/metabase/` 访问（不暴露 3000/8080 端口，由 Nginx 反向代理）。
  - 首次部署后必须由管理员在浏览器中完成：设置向导、创建管理员账号、添加 PostgreSQL 数据源（与后端业务库一致）、在 Metabase 管理界面创建 API Key 并配置到服务器 `.env` 的 `METABASE_API_KEY`。
  - 使用 IP 或非默认域名时，须设置 `MB_SITE_URL` 与 Nginx 的 `proxy_set_header Host` 与真实访问地址一致，避免白屏或重定向错误。
  - **Nginx 变量 proxy_pass 陷阱**：当使用 `set $var` + `proxy_pass http://$var` 时，必须用 `rewrite` 手动剥离 location 前缀，否则上游收到带前缀的路径会返回错误内容。
- **deployment-ops 规格**：新增需求「部署文档 SHALL 描述云端 Metabase 访问 URL 与首次初始化步骤」，并包含至少一个场景（维护者阅读文档后可完成首次配置）。

## Impact

- **Affected specs**: deployment-ops（ADDED 一条 Requirement）
- **Affected code**: `nginx/nginx.prod.conf`（修复 Metabase 代理的 URI 重写）
- **Affected docs**: `docs/deployment/` 下现有文档（如 `CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md`）或新增 `docs/deployment/CLOUD_METABASE_ACCESS.md`；可选在 `scripts/metabase_nginx_deployment_summary.md` 或部署检查清单中增加「Metabase 访问与初始化」项。

## Non-Goals

- 不在此变更中实现 Metabase 设置向导或 API Key 的**自动化**（仍为人工在浏览器中完成）。
- 不变更 Metabase 的默认端口与路由逻辑。
