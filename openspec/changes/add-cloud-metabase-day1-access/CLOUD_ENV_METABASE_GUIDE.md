# 云端服务器 .env 中 Metabase 相关配置指南

## 一、必须添加/修改的变量

在云端服务器 `/opt/xihong_erp/.env` 中，确保包含以下 Metabase 相关配置：

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `METABASE_API_KEY` | `mb_0lUMGFAhr8p5JZ33gGzXcYumwUtR0RjU6mrxCu4Ql18=` | **必须**。后端 Dashboard KPI、init_metabase 等调用 Metabase API 时使用。在 Metabase 管理后台 → 设置 → API 密钥 中生成。 |
| `METABASE_URL` | `http://metabase:3000` | 后端调用 Metabase 的地址（Docker 容器网络内）。 |
| `MB_SITE_URL` | `http://www.xihong.site/metabase/` | Metabase 容器环境变量，子路径访问时必填，否则前端白屏。若使用 docker-compose.metabase.yml 且通过 env_file 传入，需确保 .env 中有此变量。 |
| `VITE_METABASE_URL` | `/metabase` | 前端嵌入 Metabase 的路径（构建时注入，若 CI 已配置可省略）。 |

## 二、云端 .env 操作步骤

1. **SSH 登录服务器**：
   ```bash
   ssh deploy@<服务器IP>
   cd /opt/xihong_erp
   ```

2. **编辑 .env 文件**：
   ```bash
   nano .env
   # 或
   vim .env
   ```

3. **添加或修改以下行**（若已存在则更新值）：
   ```env
   # ==================== Metabase 配置 ====================
   METABASE_URL=http://metabase:3000
   VITE_METABASE_URL=/metabase
   MB_SITE_URL=http://www.xihong.site/metabase/
   METABASE_API_KEY=mb_0lUMGFAhr8p5JZ33gGzXcYumwUtR0RjU6mrxCu4Ql18=
   ```

4. **重启 backend 使配置生效**：
   ```bash
   docker restart xihong_erp_backend
   ```

5. **验证**：访问 Dashboard 页面，确认 KPI 等 Metabase 嵌入内容可正常加载。

## 三、与 .env.production 的对应关系

本地 ` .env.production` 是生产环境配置的参考模板。部署时：

- CI/CD 或部署脚本可能将 `.env.production` 同步到服务器，或使用 GitHub Secrets 注入部分变量。
- 若云端 .env 与 `.env.production` 结构不一致，需**手动**在云端添加 `METABASE_API_KEY` 等变量。
- 建议将 `.env.production` 作为单源，部署前对比云端 .env，确保 Metabase 相关变量齐全。

## 四、常见错误变量名（勿混淆）

| 错误/旧变量名 | 正确变量名 | 说明 |
|---------------|------------|------|
| `MB_API_KEY` | `METABASE_API_KEY` | 后端代码读取的是 `METABASE_API_KEY` |
| `MB_API_URL` | `METABASE_URL` | 后端使用 `METABASE_URL` |
| `MB_DATABASE_URL=redis://...` | 不适用 | Metabase 应用库用 PostgreSQL，非 Redis |
| `MBDS_*` | 非本项目 | 若为其他系统遗留，可移除或保留，与西虹 ERP 无关 |

## 五、安全检查

- `METABASE_API_KEY` 为敏感信息，勿提交到 Git。
- 云端 .env 文件权限建议：`chmod 600 .env`
- 定期轮换 API Key（在 Metabase 中重新生成后更新 .env 并重启 backend）。
