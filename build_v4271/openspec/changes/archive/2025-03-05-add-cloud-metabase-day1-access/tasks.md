# Tasks: 云端 Metabase 访问与首次初始化文档化 + Nginx 代理修复

## 0. Nginx 配置修复（P0 - 阻塞首次初始化）

- [x] 0.1 修复 `nginx/nginx.prod.conf` 中 `location ^~ /metabase/` 的 proxy_pass 变量 URI 重写问题：
  - 添加 `rewrite ^/metabase/(.*) /$1 break;` 手动剥离 `/metabase/` 前缀
  - 移除 `proxy_pass` 尾部斜杠（改为 `proxy_pass http://$metabase_upstream;`）
  - **根因**：Nginx 使用变量形式的 `proxy_pass` 时不会自动去除 location 前缀，Metabase 收到 `/metabase/app/dist/*.js` 后返回 SPA HTML fallback，浏览器因 `nosniff` 拒绝执行，导致白屏。
- [x] 0.2 同步修复 `location /app/`：添加 `rewrite ^(/app/.*)$ $1 break;` 确保变量 proxy_pass 正确传递路径。
- [x] 0.3 部署修复后验证（2026-03 已完成）：
  - 在服务器上重新加载 Nginx 配置：`docker exec xihong_erp_nginx nginx -s reload`
  - 确认 `curl -sI "http://www.xihong.site/metabase/app/dist/styles.9d1a2c7c0edb340b.js"` 返回 `Content-Type: text/javascript`
  - 确认浏览器可正常加载 Metabase 首次设置向导页面（`http://www.xihong.site/metabase/setup` 已成功显示 "Welcome to Metabase"）

## 1. 文档

- [x] 1.1 在 `docs/deployment/` 下新增或更新文档，包含「云端 Metabase 访问与首次初始化」小节（可新文件 `CLOUD_METABASE_ACCESS.md` 或合并进 `CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md`）。
- [x] 1.2 文档中明确：访问 URL 为 `http://<域名或IP>/metabase/`，生产不暴露 Metabase 独立端口；首次需在浏览器完成设置向导、管理员账号、PostgreSQL 数据源、API Key 创建并配置 `METABASE_API_KEY`。
- [x] 1.3 文档中说明：使用 IP 或非默认域名时须设置 `MB_SITE_URL` 与 Nginx `proxy_set_header Host` 与真实访问地址一致，并给出示例或引用现有 nginx.prod.conf / docker-compose.metabase.yml 配置说明。
- [x] 1.4 文档中增加「Nginx 变量 proxy_pass 陷阱」警告：当使用 `set $var` + `proxy_pass http://$var` 延迟 DNS 解析时，必须搭配 `rewrite` 手动剥离 location 前缀，否则上游收到带前缀的原始路径会返回错误内容。
- [x] 1.5 文档中增加「PostgreSQL 数据卷密码持久化」说明：数据卷已存在时修改 POSTGRES_PASSWORD 不会更新数据库内密码，需手动 `ALTER USER` 同步；数据源主机填 `postgres`，用户名填 `erp_user`。

## 2. 部署检查清单（可选）

- [x] 2.1 在部署检查清单或 `scripts/metabase_nginx_deployment_summary.md` 中增加一项：确认运维已知「通过 /metabase/ 访问」及「首次需完成 Metabase 初始化与 API Key 配置」。
- [x] 2.2 检查清单中增加一项：确认 Nginx 中所有使用变量的 `proxy_pass` 都搭配了正确的 `rewrite` 规则。

## 3. 验收

- [x] 3.1 运行 `npx openspec validate add-cloud-metabase-day1-access --strict` 通过。
- [x] 3.2 确认 deployment-ops spec 归档时能正确合并 ADDED Requirement。
- [x] 3.3 确认浏览器访问 `http://www.xihong.site/metabase/` 可正常加载 Metabase（无 MIME type 白屏错误）；`/metabase/setup` 首次设置向导已成功加载。
