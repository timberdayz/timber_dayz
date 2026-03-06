# Change: 云端 Metabase 访问与首次初始化文档化 + Nginx 代理修复

## Why

系统同步到云端后，云端 Metabase 因**未完成首次初始化**（设置向导、管理员账号、PostgreSQL 数据源、API 密钥）导致看板与后端代理不可用；同时运维与用户常误以为「Metabase 端口未暴露」而无法访问，实际上生产环境**设计上不暴露** Metabase 独立端口，仅通过 Nginx 路径 `/metabase/` 访问，该访问方式与首次配置步骤缺少成文说明。

此外，实际部署中发现 Nginx 子路径代理存在**致命配置缺陷**，导致 Metabase 白屏无法完成首次初始化。

### 根因：Nginx 变量 proxy_pass 不自动去除 location 前缀

`nginx.prod.conf` 中 Metabase 代理使用了变量形式的 `proxy_pass`：

```nginx
location ^~ /metabase/ {
    set $metabase_upstream "metabase:3000";
    proxy_pass http://$metabase_upstream/;   # ← 使用变量
}
```

**Nginx 官方行为**：当 `proxy_pass` 中包含变量时，URI 重写（自动去除 location 前缀）**不生效**。即使写了尾部斜杠 `/`，Nginx 也不会将 `/metabase/app/dist/styles.js` 重写为 `/app/dist/styles.js`，而是原样转发 `/metabase/app/dist/styles.js` 给 Metabase。

Metabase 的静态资源仅在 `/app/dist/...` 路径上提供服务，收到 `/metabase/app/dist/...` 后找不到对应文件，按 SPA 规则返回 `index.html`（`Content-Type: text/html`）。浏览器因 `X-Content-Type-Options: nosniff` 拒绝执行 MIME 为 `text/html` 的脚本，导致白屏。

**验证结果**：

| 请求路径 | Content-Type | 结果 |
|---------|-------------|------|
| `http://localhost:3000/app/dist/styles...js` | `text/javascript` | 正确 JS |
| `http://localhost:3000/metabase/app/dist/styles...js` | `text/html` | HTML fallback |

### 教训与规范

> **规则**：在 Nginx 中使用变量形式的 `proxy_pass`（为延迟 DNS 解析）时，**必须**搭配 `rewrite` 手动剥离 location 前缀。这是 Nginx 的已知行为差异，非 bug。

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
