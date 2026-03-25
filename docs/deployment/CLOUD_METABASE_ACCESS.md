# 云端 Metabase 访问与首次初始化

> 历史文档：Metabase 已不属于当前生产运行和部署主路径。
> 保留本文仅供历史排障或归档检索，不应再作为现役部署说明。

本文档描述云端 Metabase 的访问 URL、首次初始化步骤及常见问题，供首次部署或运维参考。

---

## 一、访问 URL

- **云端 Metabase** 仅通过 `http://<域名或IP>/metabase/` 访问，**不暴露** Metabase 独立端口（3000/8080）。
- 由 Nginx 反向代理 `/metabase/` 到 Metabase 容器；生产环境不直接映射 Metabase 宿主机端口。
- **示例**：`http://www.xihong.site/metabase/`、`http://134.175.222.171/metabase/`

---

## 二、首次初始化步骤

首次云端部署后，Metabase 需在**浏览器中手动**完成初始化，步骤如下：

1. **访问 Metabase**：打开 `http://<域名或IP>/metabase/` 或 `/metabase/setup`
2. **设置向导**：完成 Metabase 首次设置向导
3. **创建管理员账号**：填写邮箱、密码、姓名（建议使用与业务一致的管理员邮箱）
4. **添加 PostgreSQL 数据源**：
   - 主机地址：**`postgres`**（Docker 服务名，勿填 `postgresql`、`localhost` 或 `postgres.xihong.site`）
   - 端口：`5432`
   - 数据库名：`xihong_erp`
   - 用户名：**`erp_user`**（业务库用户，勿填 `metabase_user`）
   - 密码：与 `.env` 中 `POSTGRES_PASSWORD` 一致
   - Schema filters：建议 `public,b_class,a_class,c_class,core` 或留空使用全部
5. **创建 API Key**：在 Metabase 管理后台 → 设置 → 认证 → API 密钥 中生成 API Key
6. **配置 `METABASE_API_KEY`**：将 API Key 写入服务器 `/opt/xihong_erp/.env`，并**重新执行 Phase 3.5 或重新部署**，使 `init_metabase.py` 能创建 Models 和 Questions。

> **说明**：Phase 3.5（`init_metabase.py`）需要 `METABASE_API_KEY` 才能通过 Metabase API 创建/更新 Models 和 Questions。首次部署时 Metabase 尚未创建 API Key，Phase 3.5 会失败；完成上述步骤后重新部署即可。

---

## 三、使用 IP 或非默认域名时

当使用 IP 或非默认域名访问时，须设置 `MB_SITE_URL` 与 Nginx 的 `proxy_set_header Host` 与**真实访问地址**一致，否则可能出现白屏或重定向错误。

- **`MB_SITE_URL`**：在 `docker-compose.metabase.yml` 中通过环境变量传入，或 `.env` 中设置，例如：
  - 域名：`http://www.xihong.site/metabase/`（**必须带尾部斜杠**）
  - IP：`http://134.175.222.171/metabase/`
- **Nginx**：`proxy_set_header Host $host` 会传递请求的 Host，一般与 `MB_SITE_URL` 的域名/IP 一致即可。
- 详见：`docker-compose.metabase.yml`、`nginx/nginx.prod.conf`

---

## 四、Nginx 变量 proxy_pass 陷阱（重要）

当使用 `set $var` + `proxy_pass http://$var` 实现**延迟 DNS 解析**（避免 Nginx 启动时 Metabase 未就绪导致解析失败）时，Nginx **不会自动**去除 `location` 前缀。

- **问题**：上游会收到原始路径（如 `/metabase/app/dist/styles.xxx.js`），Metabase 期望 `/app/dist/...`，找不到文件时返回 SPA HTML fallback（`Content-Type: text/html`），浏览器因 `nosniff` 拒绝执行 JS，导致**白屏**。
- **解决**：必须使用 `rewrite` 手动剥离 location 前缀，例如：
  ```nginx
  location ^~ /metabase/ {
      rewrite ^/metabase/(.*) /$1 break;
      set $metabase_upstream metabase:3000;
      proxy_pass http://$metabase_upstream;
      # ...
  }
  ```
- **检查**：`curl -sI "http://<host>/metabase/app/dist/styles.9d1a2c7c0edb340b.js"` 应返回 `Content-Type: text/javascript`，而非 `text/html`。

> **规则**：所有使用变量的 `proxy_pass` 的 `location`，都必须配合 `rewrite ... break;` 正确传递路径，否则上游可能返回错误内容。

---

## 五、PostgreSQL 数据卷密码持久化

当 **PostgreSQL 数据卷已存在**（如之前部署用过旧密码）时，修改 `.env` 中的 `POSTGRES_PASSWORD` **不会**自动更新数据库内已有用户的密码。PostgreSQL 官方镜像仅在**首次初始化**（数据目录为空）时使用 `POSTGRES_PASSWORD` 创建用户。

- **现象**：Metabase 添加 xihong_erp 数据源时，使用 `.env` 中的 `POSTGRES_PASSWORD` 连接失败，报「错误的密码或用户名」。
- **修复**：在 postgres 容器内执行 `ALTER USER` 将密码同步为当前 `.env` 值：
  ```bash
  docker exec -it xihong_erp_postgres psql -U erp_user -d xihong_erp -c \
    "ALTER USER erp_user WITH PASSWORD '你的POSTGRES_PASSWORD值';"
  ```
  若需超级用户：`psql -U postgres`。
- **数据源配置要点**：主机填 `postgres`，用户名填 `erp_user`，与 `.env` 中 `POSTGRES_PASSWORD` 一致。

---

## 六、相关文档

- [云端 .env 更新清单](./CLOUD_ENV_UPDATE_CHECKLIST.md)
- [云端部署更新与本地验证](./CLOUD_UPDATE_AND_LOCAL_VERIFICATION.md)
- `openspec/changes/add-cloud-metabase-day1-access/CLOUD_ENV_METABASE_GUIDE.md`（Metabase .env 配置）
