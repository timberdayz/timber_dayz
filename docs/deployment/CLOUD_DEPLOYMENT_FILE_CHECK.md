# 云端部署文件符合性检查报告

基于当前部署流程（`.github/workflows/deploy-production.yml`）与本地仓库结构，对云端服务器 `/opt/xihong_erp` 进行文件符合性检查。检查时间：2026-03-13。

---

## 1. 检查结论摘要

| 类别 | 状态 | 说明 |
|------|------|------|
| Compose 文件 | 通过 | 所需及可选 compose 均存在 |
| 部署脚本 | 通过 | deploy_remote_production.sh 存在且可执行 |
| .env | 通过 | 存在 |
| config/（根目录 yaml/py） | 已修复 | 原缺 2 个文件，已通过 SSH 补传 |
| sql/init | 通过 | 01-init.sql 存在 |
| nginx | 通过 | nginx.prod.conf、nginx/ssl 存在 |

---

## 2. 部署要求与云端对照

### 2.1 必需文件（无则部署/运行会失败）

| 路径 | 用途 | 云端状态 |
|------|------|----------|
| docker-compose.yml | 基础 compose | 存在 |
| docker-compose.prod.yml | 生产 overlay | 存在 |
| docker-compose.metabase.yml | Metabase 服务 | 存在 |
| deploy_remote_production.sh | 远程部署脚本 | 存在、可执行 |
| .env | 环境变量（人工维护） | 存在 |
| nginx/nginx.prod.conf | Nginx 生产配置 | 存在 |
| config/metabase_config.yaml | Metabase 配置、init_metabase.py | 存在 |
| sql/init/01-init.sql | Postgres 初始化（如 metabase_app） | 存在 |

### 2.2 可选但推荐（4 核 8G 或云优化）

| 路径 | 用途 | 云端状态 |
|------|------|----------|
| docker-compose.cloud.yml | 云服务器优化 | 存在 |
| docker-compose.cloud-4c8g.yml | 4c8g overlay | 存在 |
| docker-compose.metabase.4c8g.yml | Metabase 4c8g 限制 | 存在 |
| nginx/ssl/ | SSL 证书目录 | 存在（空目录亦可） |

### 2.3 config/ 根目录（workflow 会同步的 *.yaml / *.py）

Workflow 会同步 `config/*.yaml` 与 `config/*.py`（仅 config 根目录，不含子目录）。  
以下为本地 config 根目录与云端对比结果。

**检查时云端缺失（已在本轮补传）：**

| 文件 | 说明 | 处理 |
|------|------|------|
| accounts_config.yaml | 配置校验与业务使用（config_validator、config_schemas） | 已通过 SSH 上传至云端 config/ |
| proxy_config.yaml | 代理配置（proxy_manager 默认读取） | 已通过 SSH 上传至云端 config/ |

**其余 config 根目录文件云端均已存在：**

- metabase_config.yaml, miaoshou_config.yaml, multi_region_routing.yaml, multi_region_routing_example.yaml  
- platform_priorities.yaml, exchange_rates.yaml, shop_aliases.yaml  
- field_mappings.yaml, field_mappings_v2.yaml, field_mappings_enhanced.yaml  
- data_collection.yaml, simple_config.yaml  
- proxy_config.py, proxy_manager.py, browser_fingerprints.py  

---

## 3. 与部署流程的对应关系

- **Compose / 脚本 / nginx**：由 GitHub Actions 在 “Sync compose files to production server” 步骤中通过 SCP 上传；本地与 workflow 一致则云端会保持最新。
- **config/**：同一步骤中上传 `config/metabase_config.yaml` 及 `config/*.yaml`、`config/*.py`；若某次部署中 SCP 失败，对应文件可能未更新或缺失（本次缺失的 2 个已用本机 SSH 补传）。
- **.env**：不通过 Git/SCP 同步，需人工将本地 `.env.production` 与云端 `.env` 保持一致。

---

## 4. 建议

1. **后续部署**：若再次出现 config 下某文件 SCP 失败，可在本机用同一密钥执行一次补传，例如：
   ```powershell
   scp -i "C:\Users\18689\.ssh\github_actions_deploy" -o StrictHostKeyChecking=no config/accounts_config.yaml config/proxy_config.yaml deploy@134.175.222.171:/opt/xihong_erp/config/
   ```
2. **4 核 8G**：若使用 4c8g overlay，需按 `docs/deployment/CLOUD_4C8G_REFERENCE.md` 在部署后手动追加 overlay 或配置 `CLOUD_PROFILE=4c8g`，否则 Metabase 内存限制可能不生效。
3. **定期核对**：每次大版本发布或变更 compose/config 后，可再次运行本检查（或重跑 “Sync compose files” 后对比）确保云端与仓库一致。

---

## 5. 检查方式说明

本次检查通过本机 SSH 密钥（与 `scripts/sync_templates_to_cloud.ps1` 所用一致）连接 `deploy@134.175.222.171`，在 `/opt/xihong_erp` 下执行 `ls` 等命令列出文件，并与本地仓库及 `deploy-production.yml` 中上传清单比对。缺失的 `accounts_config.yaml`、`proxy_config.yaml` 已通过同密钥 SCP 上传至云端 `config/`。
