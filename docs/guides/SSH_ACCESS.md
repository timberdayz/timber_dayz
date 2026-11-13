# SSH 访问：账号、钥匙与通道

> **这份文档是 SSH 访问的真源（律 1：真源只能一个，而且必须写在纸上）。**
> 账号、钥匙、用途、默认端口、常见误判 —— 全在这里。
> 改任何一项，都要同步改这份文档 + 相关脚本 + 守护测试（见 §7）。
>
> 2026-11-13 新建。起因是一次真实的误判，过程记在 §5。

---

## 0. 先记住这一句

> **本机（以及任何 agent）能用的生产身份只有一个：`deploy@134.175.222.171`，
> 用 `~/.ssh/github_actions_deploy` 这把钥匙。**
>
> `root@` 是**流水线**的身份，私钥只存在 GitHub Actions Secret 里，
> **本机刻意不持有** —— 那是设计，不是"环境缺东西"。

---

## 1. 四条通道，一张表

| 通道 | 账号 @ 目标 | 私钥从哪来 | 干什么 | 谁能发起 |
|---|---|---|---|---|
| **GitHub 代码** | `git@ssh.github.com:443` | 本机 `~/.ssh/github_actions_deploy` | fetch / push 代码与 tag | 人、agent（本机有钥匙） |
| **生产运维**（只读核查） | `deploy@134.175.222.171` | 本机 `~/.ssh/github_actions_deploy` | 看容器状态、读部署日志、只读 SQL | 人、agent（本机有钥匙） |
| **云端同步隧道** | `deploy@134.175.222.171` | 本机 `~/.ssh/github_actions_deploy`（经 `CLOUD_SYNC_SSH_KEY` 传入） | 采集机 → 云端 PG 的 15433 通道 | 采集机脚本自动拉起 |
| **生产部署** | `root@134.175.222.171`（`PRODUCTION_USER` secret 可改） | **GitHub Actions Secret `PRODUCTION_SSH_PRIVATE_KEY`** | 跑 `deploy_remote_production.sh` | **只有流水线**；人/agent 都不能直接用 |

**同一把钥匙，两个身份**：`github_actions_deploy` 既是 GitHub 代码通道的钥匙，
也是生产 `deploy@` 的钥匙。只有**部署通道**用的是另一把（存在 GitHub Secret 里，本机没有）。

---

## 2. 机器可读配置口径

> 下面这一段是**契约**：`tests/test_ssh_access_contract.py` 会逐条比对
> **脚本里的默认值** 与 **这里写的值**，不一致就红。
> 改端口/改账号时，**两处一起改**。

```
CLOUD_SYNC_SSH_HOST=134.175.222.171
CLOUD_SYNC_SSH_USER=deploy
CLOUD_SYNC_TUNNEL_HOST=127.0.0.1
CLOUD_SYNC_TUNNEL_PORT=15433
CLOUD_SYNC_REMOTE_DB_HOST=127.0.0.1
CLOUD_SYNC_REMOTE_DB_PORT=15435
```

私钥路径走环境变量 `CLOUD_SYNC_SSH_KEY`，默认值是 `%USERPROFILE%\.ssh\github_actions_deploy`。
**路径随机器不同，文件名才是契约** ⇒ 所以脚本里不许把绝对路径写死（守护测试会拦）。

两个真源脚本（默认值必须一致，否则「一个跑一个跳」）：

- `scripts/start_collection_formal.ps1`（采集启动时拉隧道）
- `scripts/watch_cloud_sync_tunnel.ps1`（看门狗自愈）

---

## 3. 每条通道怎么用

### 3.1 GitHub 代码通道

- GitHub 的 **HTTPS 端点从本网络不可达**（DNS 通、TCP/443 超时）⇒ 代码通道只能走 **SSH-443**。
- 本机已永久配置好：

```powershell
git config --get core.sshCommand
# => ssh -i C:/Users/18689/.ssh/github_actions_deploy -o IdentitiesOnly=yes
git remote -v
# fetch 与两个 push URL（GitHub SSH-443 + CNB HTTPS）见 docs/guides/RELEASE_CHECKLIST.md
```

- **双镜像纪律**（先 CNB 建 parity → 再 GitHub 触发部署、**绝不回填 tag**）不在本文档，
  见 `docs/guides/RELEASE_CHECKLIST.md`。

### 3.2 生产运维通道（`deploy@`）—— agent 唯一能用的生产入口

2026-11-13 实测权限：

```
uid=1002(deploy) gid=1002(deploy) groups=1002(deploy),27(sudo),999(docker)
```

- 在 **docker 组** ⇒ `docker ps` / `docker logs` / `docker exec` **免密可用**。
- 在 sudo 组，但 **sudo 需要交互输入密码** ⇒ agent 无法交互 ⇒
  **优先用 docker 组权限，不要指望 sudo**。

常用只读核查命令：

```powershell
# 容器状态
ssh -i "$env:USERPROFILE\.ssh\github_actions_deploy" deploy@134.175.222.171 `
  "docker ps --format '{{.Names}}\t{{.Status}}'"

# 生产库只读查询（psql 在容器里）
ssh -i "$env:USERPROFILE\.ssh\github_actions_deploy" deploy@134.175.222.171 `
  "docker exec -i xihong_erp_postgres psql -U erp_user -d xihong_erp -A -F ' | '"

# nginx 访问/错误日志
ssh -i "$env:USERPROFILE\.ssh\github_actions_deploy" deploy@134.175.222.171 `
  "docker exec xihong_erp_nginx sh -c 'tail -n 50 /var/log/nginx/access.log'"
```

⚠️ 只读优先：核查用 `SELECT` / `docker ps` / `tail`；**不要**在生产上跑写操作
（改数据、重启容器、删文件）—— 那些要走发版流程。

### 3.3 云端同步隧道（`deploy@`）

```
采集机本机 127.0.0.1:15433  ──SSH──▶  生产机 127.0.0.1:15435  ──▶  云端 PostgreSQL
```

- 采集机的 `CLOUD_DATABASE_URL` 指向 `127.0.0.1:15433`（宿主上的隧道端口）。
  容器里连不到宿主回环 ⇒ 代码里统一做主机名改写（`normalize_cloud_database_url`）。
- **远端 15435 只监听 `127.0.0.1`**（2026-11-13 实测）⇒ 隧道**必须由采集机发起**，
  生产机自己连不了自己的 15435。
- ⚠️ **生产上的「云端」就是它自己**（连接串主机名是 `postgres`，非回环）⇒
  **生产侧不需要隧道**，隧道是**采集机**用的。别在生产机上找隧道，也别据此说"隧道挂了"。
- 看门狗 `scripts/watch_cloud_sync_tunnel.ps1` 负责自愈：
  端口通就不动；不通就清掉僵死 ssh 进程再拉一条。

### 3.4 生产部署通道（`root@`）—— 只有流水线能用

- 流水线用 GitHub Secret `PRODUCTION_SSH_PRIVATE_KEY` + `PRODUCTION_HOST` +
  `PRODUCTION_HOST_KEY`（host key 固定，不做 `StrictHostKeyChecking=no`），
  以 `PRODUCTION_USER`（默认 `root`）执行 `scripts/deploy_remote_production.sh`。
- **本机没有、也不该有 root 私钥** ⇒ 所以"本机登不上 root"是**预期结果**，
  不构成"环境缺私钥"的结论。
- ⚠️ **不要连续重试 root@**：连续失败可能触发主机侧风控/封禁。
  要核查生产，就走 §3.2 的 `deploy@` 只读通道。

---

## 4. 自检清单（复制即用）

```powershell
# ① 隧道是否活着（本机端口在听 = 隧道在）
Get-NetTCPConnection -LocalPort 15433 -State Listen -ErrorAction SilentlyContinue

# ② 隧道进程长什么样（应能看到 -i <key> 与 deploy@<host>）
Get-CimInstance Win32_Process -Filter "Name='ssh.exe'" |
  Where-Object { $_.CommandLine -and $_.CommandLine.Contains('-L ') } |
  Select-Object ProcessId, CommandLine

# ③ 能不能登机（能读到容器列表 = 通道正常）
ssh -i "$env:USERPROFILE\.ssh\github_actions_deploy" -o BatchMode=yes `
  -o ConnectTimeout=12 deploy@134.175.222.171 "docker ps --format '{{.Names}}'"

# ④ 配置到底从哪读（三个 env 文件，后面的覆盖前面的）
#    .env → .env.local → .env.collection.local
Select-String -Path .env,.env.local,.env.collection.local -Pattern '^CLOUD_SYNC_(SSH_|TUNNEL_|REMOTE_DB_)'
```

判读：

| 现象 | 结论 |
|---|---|
| ① 有监听 + ② 有 ssh 进程 | 隧道正常，不需要做任何事 |
| ① 有监听但 ③ 登不上 | 隧道在但**运维通道**有问题 → 检查账号/钥匙 |
| ① 没监听 | 隧道断了 → 看门狗会自动拉起；再不行手动跑 `scripts/watch_cloud_sync_tunnel.ps1` |
| ③ 能登机 | **部署侧核验能力是有的**（别再写"无法登机"） |

---

## 5. 常见误判 → 真相

| 现象 | 容易得出的错误结论 | 真相 |
|---|---|---|
| `root@134.175.222.171` → `Permission denied (publickey,password)` | "本机没有生产 SSH 私钥" | **交互式账号是 `deploy@`**；root 私钥只在 GitHub Actions Secret 里。**换 `deploy@` + `github_actions_deploy` 就好**（2026-11-13 实测：隧道当时正在跑，7 个容器全 healthy） |
| 因为 root 登不上 ⇒ 认为"部署侧无法核验" | "只能靠 HTTP 直观测" | `deploy@` **能登机**并读容器/日志/只读 SQL ⇒ 核验能力是有的 |
| `deploy@` 也 Permission denied | "隧道坏了" | 先核对账号是不是 `deploy`、私钥路径是不是 `CLOUD_SYNC_SSH_KEY` 指向的那个 |
| 本机 15433 不通 | "云端挂了" | 隧道断了而已；看门狗会自愈，云端本身多半没事 |
| 在生产机上找不到 SSH 隧道 | "生产需要隧道" | 生产的"云端"= 它自己，**不需要**隧道 |
| `ssh` 报 `Permission denied` 就连续重试 | — | 会踩风控；**停手**，按 §4 顺序排查 |

### 2026-11-13 事故记录（一句话版）

agent 拿 `root@` + 本机两把钥匙试连 → 两次 `Permission denied` →
判定"本机没有生产 SSH 私钥" → 写下"部署类核验无法登机" →
后续多轮判断都建立在这个错误前提上（少了一个真正的生产观测入口）。
**真实原因只是账号用错**（隧道与运维都用 `deploy@`），钥匙一直都在本机、隧道一直在跑。
⇒ 教训：**账号/钥匙/用途必须写在纸上**（就是这份文档）+ 用守护测试钉住（§7）。

---

## 6. 红线

- **不用口令**：隧道与运维一律 key 登录；脚本里不许出现 `sshpass`（守护测试会拦）。
- **私钥路径不写死**：一律走环境变量（`CLOUD_SYNC_SSH_KEY`），路径随机器不同。
- **不连续重试 `root@`**：连不上就停手查文档，别刷。
- **不把私钥内容写进任何文档、日志、提交、聊天**。
- **不用 `root@` 做交互式核查**：用 `deploy@` 的只读通道；需要写操作就走发版流程。
- **主机地址与账号不是秘密**（仓库里本来就有），**私钥才是**。
- 生产核查默认**只读**：`SELECT` / `docker ps` / `tail`。

---

## 7. 变更纪律

改「账号 / 钥匙 / 端口 / 目标主机」中的任何一项，必须**同时**改这四处：

1. 本文档（§1 表格 + §2 配置块）
2. `scripts/start_collection_formal.ps1`
3. `scripts/watch_cloud_sync_tunnel.ps1`
4. 守护测试：`tests/test_ssh_access_contract.py`（本文档 ↔ 脚本 一致性）
   与 `tests/test_cloud_sync_tunnel_watchdog.py`（两个脚本彼此一致性）

改完跑：

```powershell
python -m pytest -q tests/test_ssh_access_contract.py tests/test_cloud_sync_tunnel_watchdog.py
```

两份守护测试都已进 CI 的「根契约测试」清单 ⇒ **文档与代码漂移会直接让 CI 变红**。
