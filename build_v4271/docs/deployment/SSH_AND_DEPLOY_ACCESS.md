# SSH 凭证与部署网络访问说明

本文档说明项目中 **SSH 凭证** 和 **网络访问权限** 的配置位置与使用方式。**不包含任何实际密钥或密码**，仅描述配置来源与流程。

---

## 1. SSH 凭证存在哪里？

### 仅存在于 GitHub Secrets（仓库级）

项目中 **没有** 在代码或配置文件中保存 SSH 私钥、主机、用户或路径。所有生产/预发部署用的连接信息都来自 **GitHub 仓库的 Secrets**：

| 配置项 | 存储位置 | 说明 |
|--------|----------|------|
| SSH 私钥 | GitHub → Settings → Secrets and variables → Actions | 对应 Secret 名称：`PRODUCTION_SSH_PRIVATE_KEY` |
| 生产主机 | 同上 | `PRODUCTION_HOST`（如 IP 或域名） |
| SSH 用户 | 同上 | `PRODUCTION_USER`（可选，未设置时默认 `root`） |
| 部署路径 | 同上 | `PRODUCTION_PATH`（可选，未设置时默认 `/opt/xihong_erp`） |

- **生产环境**：使用 `PRODUCTION_*`（见 `.github/workflows/deploy-production.yml`）。
- **预发/Staging**：使用 `STAGING_SSH_PRIVATE_KEY`、`STAGING_HOST` 等（见 `.github/workflows/deploy-staging.yml`）。

### 本地 / 脚本里会不会出现凭证？

- **仓库内**：不会。私钥、主机、用户、路径均通过 `${{ secrets.XXX }}` 从 GitHub 注入，**不会**写进任何提交到 Git 的文件。
- **本地**：若你在本机用脚本或 SSH 连接服务器，需要自己在本机或 CI 外保存密钥/主机等；项目**不要求**在本地仓库里放 `.env` 或密钥文件来做部署。文档中的示例（如 `134.175.222.171`、`/opt/xihong_erp`）仅为说明格式，实际值以你在 GitHub Secrets 中配置的为准。

---

## 2. 部署时如何用这些凭证？

### 生产部署（push tag 或手动触发）

1. **检查**  
   `check-config` job 只检查 **是否配置**了 `PRODUCTION_SSH_PRIVATE_KEY` 和 `PRODUCTION_HOST`，不校验内容。

2. **注入 SSH 私钥**  
   - Step：`Set up SSH`  
   - 使用 Action：`webfactory/ssh-agent@v0.8.0`  
   - 将 `secrets.PRODUCTION_SSH_PRIVATE_KEY` 加入当前 job 的 ssh-agent，供后续 `ssh`/`scp` 使用。

3. **使用方式**  
   - 同一 job 的 `run` 脚本里通过环境变量拿到：  
     `PRODUCTION_HOST`、`PRODUCTION_USER`、`PRODUCTION_PATH`（由 step 的 `env` 从 secrets 注入）。  
   - 所有 `ssh`、`scp` 均使用当前环境中的默认 SSH（ssh-agent 已加载私钥），连接形式为：  
     `scp/ssh ... ${PRODUCTION_USER}@${PRODUCTION_HOST} ...`，目标路径为 `PRODUCTION_PATH`（如 `${PRODUCTION_PATH}/config/...`）。

因此：**谁有权限改仓库的 GitHub Secrets，谁就拥有部署用的 SSH 凭证和“网络访问权限”**；实际网络访问是 **GitHub Actions 的 runner 用这些凭证连接你的服务器**。

---

## 3. 网络访问权限指什么？

- **出站**：GitHub 的 runner（Ubuntu）执行 workflow 时，会从 GitHub 机房向你的服务器发起 **SSH（22）连接** 和 **SCP**。  
- **入站**：你的服务器需要 **对 GitHub 的 IP 或对公网开放 22 端口**（取决于你是否限制了来源 IP），以便 runner 能连上。  
- **项目内**：没有配置“只允许某 IP 段”的逻辑，防火墙/安全组需在**服务器或云控制台**自行配置。

总结：**网络访问权限 = 服务器允许 GitHub runner 通过 22 端口 SSH 进来；凭证 = 只有能登录该服务器的私钥（存在 GitHub Secrets 中）**。

---

## 4. 如何确认当前配置是否生效？

- 在 **GitHub 仓库**：Settings → Secrets and variables → Actions，查看是否存在：  
  `PRODUCTION_SSH_PRIVATE_KEY`、`PRODUCTION_HOST`（以及可选的 `PRODUCTION_USER`、`PRODUCTION_PATH`）。  
- 部署是否能用这些凭证，看 **Actions** 里 “Deploy to Production” workflow 的日志：  
  - 若在 “Sync compose files to production server” 或后续步骤报 SSH/SCP 错误，多半是密钥错误、主机错、或服务器 22 端口/防火墙未对 runner 开放。  
- 文档中提到的示例值（如 `134.175.222.171`、`deploy`、`/opt/xihong_erp`）仅作格式参考，真实值以你在 Secrets 中配置的为准。

---

## 5. 相关文件索引（便于你自查）

| 文件 | 用途 |
|------|------|
| `.github/workflows/deploy-production.yml` | 生产部署：读取 `PRODUCTION_*` secrets，用 webfactory/ssh-agent 加载私钥并执行 ssh/scp |
| `.github/workflows/deploy-staging.yml` | 预发部署：读取 `STAGING_*` secrets |
| `docs/CI_CD_DEPLOYMENT_GUIDE.md` | 部署流程与 Secrets 说明（含表格） |
| `docs/deployment/PRE_DEPLOYMENT_CHECKLIST.md` | 部署前检查清单（含 Secrets 项） |
| `scripts/pre_deployment_check.py` | 部署前检查脚本（会提示需配置的 Secrets 名称） |

---

**重要**：任何人都不应把 `PRODUCTION_SSH_PRIVATE_KEY` 或其它 Secret 的实际内容提交到仓库或写进文档；密钥只应存在于 GitHub Secrets 或你本机/运维工具的安全存储中。
