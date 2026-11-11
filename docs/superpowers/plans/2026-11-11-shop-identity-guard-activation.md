# 店铺身份「保未来」守护落地（2026-11-11）

> 本文是 `docs/superpowers/plans/2026-11-10-shop-identity-future-proofing-and-observability.md`
> 的**收口执行记录**：前面几个批次把「工具」造出来了，这一份记录**把守卫真的立起来**。

## 1. 这一轮解决什么

批次 1~4.3 做完了「修当下」与「把工具备好」。但工具造好 ≠ 守卫生效。
截至本文写作时，三个决定「守卫生效与否」的开关**一个都没配**，
巡检在生产上永远 `skipped`，隧道是一条**一次性** ssh 进程。

这一轮做三件事：

| # | 事 | 之前 | 之后 |
|---|---|---|---|
| 1 | 生效日 / 阈值 / 通知开关 | 代码里有、env 里没有 | 本机与生产**都已配上** |
| 2 | 隧道 | 一次性 ssh 进程，死了没人管 | 看门狗脚本 + 计划任务，**每 2 分钟**自愈 |
| 3 | 巡检的「看不见」 | 云端不可达 ⇒ 静默跳过 | 写**本地** ops 台账 ⇒ 留痕可见 |

## 2. 三个参数为什么是这三个值

### 2.1 生效日 = `2026-12-01`（**不是** 2026-11-12）

云端 `semantic.fact_analytics_monthly_atomic` 逐月实测（2026-11-11，走 SSH 隧道只读）：

| 月份 | 总行 | unknown | 占比 |
|---|---|---|---|
| 2026-02 | 448 | 0 | 0% |
| 2026-03 | 527 | 31 | 5.88% |
| 2026-04 | 600 | 60 | 10.00% |
| 2026-05 | 620 | 62 | 10.00% |
| 2026-06 | 583 | 30 | 5.15% |
| 2026-07 | 586 | 30 | 5.12% |
| 2026-08 | 385 | 31 | 8.05% |
| 2026-09 | 600 | 30 | 5.00% |
| 2026-10 | 942 | 27 | 2.87% |
| **2026-11** | **127** | **72** | **56.69%** |

本地库同表 11 月是 32 行 / 0 unknown ⇒ **云端 11 月就是 2026-11 事故现场**。

分档是**按月**的（`boundary = 生效日.replace(day=1)`，生效日所在月整月算 `post_alignment`）：

* 若配 `2026-11-12` ⇒ 11 月整月进「新问题」档 ⇒ 该月 56.69% > 阈值 ⇒ 巡检**每小时都红** ⇒
  告警当场作废（天天红的告警等于没有告警）。
* 配 `2026-12-01` ⇒ 2026-02~11 全部 `known_legacy`（**不报警**）⇒ 12 月起才进入守护区间。

这就是「**歧义宁可落 unknown 报警，也不猜一个**」在**日期**上的同一条原则：
生效日之前是**已知历史遗留**（历史不修），生效日之后才算**新问题**。

### 2.2 阈值 = `0`（`SHOP_IDENTITY_SEMANTIC_UNKNOWN_RATE_THRESHOLD`）

默认 0.05（5%）会放过「新增月份只剩 1~2 行认不出」—— 而「认不出」这件事
**一行就足以污染一个月的结论**（语义层的 `shop_id` 落 `unknown` ⇒ 看板错、
对账对不上）。设 0 后：**只要有 1 行就报**；该月 0 行时比率为 0，不报。

### 2.3 矛盾行通知 = **开**（`SHOP_IDENTITY_CONFLICT_NOTIFY_ENABLED=1`）

复用批次 3.4 已有的三条通道（站内信 / webhook / 钉钉），通知失败**不影响**同步。
默认是关的；既然已经踩过一次「事实行认不出店」的事故，就不该让它**静默**。

## 3. 落地清单

| 文件 | 作用 |
|---|---|
| `backend/tasks/cloud_sync_integrity_tasks.py` | ① 新增**公开**入口 `resolve_cloud_database_url_from_env()`（私有名保留为委托别名）② 巡检**探活**：连不上云端时把结论写进**本地** `ops.pipeline_run_log`（`status='failed'`），且留痕失败**绝不掩盖**原异常 |
| `scripts/verify_semantic_unknown_by_month.py` | **只读**逐月看云端「认不出店」占比；口径**直接复用**巡检的 `collect_semantic_resolution` / `resolve_alignment_effective_date` / `resolve_semantic_unknown_rate_threshold` ⇒ 脚本看到的数字 = 巡检会判的数字 |
| `scripts/watch_cloud_sync_tunnel.ps1` | 隧道**看门狗**：探测 → 自愈（先清僵死 ssh 进程再重连）→ 留痕；`-InstallScheduledTask` 注册计划任务 |
| `docker-compose.prod.yml` / `.dev.yml` / `.collection-cloud-sync.yml` | 把三个开关与 `CLOUD_DATABASE_URL` **显式传进** celery worker / beat / collector ⇒ 配在 `.env` 里才真进得去容器 |
| `env.*.example` × 6 | 三个开关的**语义**与取值约束（留空 = 未启用 = 不误报） |
| `tests/test_verify_semantic_unknown_by_month_contract.py` | 14 条：口径不分叉 / 只读 / 零字面量连接串 / 脱敏 / 公开别名不分叉 |
| `tests/test_cloud_sync_integrity_local_trace.py` | 9 条：探活 → 留痕 → 原样抛出；留痕失败不掩盖原异常；脱敏 |
| `tests/test_cloud_sync_tunnel_watchdog.py` | 9 条：ssh 参数不漂移 / 幂等 / 不碰容器 / 不落明文口令 / 清僵尸进程 |
| `tests/test_shop_identity_compose_env_contract.py` | 11 条：三个开关必须成对传到 worker 与 beat；默认值必须为空 |

### 环境变量落地位置

| 位置 | 落地内容 | 生效方式 |
|---|---|---|
| 本机 `.env.collection.local`（采集机） | 三件套全配 | 采集侧进程读取；`backend-collector` 容器经 compose 拿到 |
| 生产 `/opt/xihong_erp/.env` | `CLOUD_DATABASE_URL`（= `DATABASE_URL`，生产上云端就是自己）+ 三件套 | **容器重建后生效** ⇒ 随 v7.21.0 部署一起生效 |

生产 `.env` 备份：`/opt/xihong_erp/.env.bak.20261111_114118`。

## 4. 为什么巡检要「留痕」而不是「弹窗」

2026-11-07 事故的直接成因是：**巡检永远 `skipped`**，云端停在 11-06 再也没动过，
而**没有任何一条记录**说明「我看不见」。

所以「看不见」这件事本身必须**留痕**：

* 云端不可达时，云端那侧的 ops 表**根本写不进去** ⇒ 只有**本地**台账能留下
  「巡检还活着、但它够不着云端」的证据；
* 留痕写的是既有 `ops.pipeline_run_log`（**不新增表、不加迁移**）；
* 留痕失败**绝不影响**巡检本身的结论（原异常照抛），否则「留痕」自己会变成新故障源；
* 留痕里的连接串口令**必须抹掉**（`redact_credentials`）——否则一次「连不上」
  就把 `postgresql://user:pass@host` 抄进了监控表。

「没配 `CLOUD_DATABASE_URL`」仍走 `skipped`（那是**未启用**，不是故障），
但生产侧现在**配上了**，所以这条路径不再被走到。

## 5. 隧道看门狗

采集机 → 云端靠一条 ssh 隧道：上游静默 ~90 秒后它自己会死（`ServerAliveInterval=30`
/ `ServerAliveCountMax=3`），**且不会自己复活**。

看门狗做三件事：

1. **探测**：`127.0.0.1:15433` 是否真的可连（ssh 进程一死，本地监听 socket 必然消失）；
2. **自愈**：不可连 ⇒ 先**清掉占着端口的僵死 ssh 进程**（不清理的话新进程会因为
   `ExitOnForwardFailure=yes` 直接退出）⇒ 再按**与 `Ensure-CloudSyncTunnel` 完全一致**的
   ssh 参数重连；
3. **留痕**：每次执行追加一行到 `logs/cloud-sync-tunnel-watchdog.log`。

**它只管隧道，不碰容器** —— 所以可以随时单独跑，不会打断采集。

> ⚠️ 实现约束：仓库 42 个 `.ps1` **全部无 BOM**，而 PowerShell 5.1 读无 BOM 脚本时
> 用系统 ANSI 代码页解码 ⇒ 中文注释会被误解码，甚至**破坏语法**。
> ⇒ 看门狗脚本**刻意保持纯 ASCII**（注释与输出都是英文），这是本仓库 `.ps1` 的安全写法。

### 已注册的计划任务

```
TaskName: XihongCloudSyncTunnelWatchdog
命令:     powershell -NoProfile -ExecutionPolicy Bypass -File scripts/watch_cloud_sync_tunnel.ps1
频率:     每 2 分钟
```

## 6. 验证记录

| 项 | 方法 | 结果 |
|---|---|---|
| 隧道自愈 | 手动杀掉 ssh 进程（pid 18608）后实跑看门狗 | 端口恢复可达，新 pid 53364，退出码 0 |
| 隧道幂等 | 端口已通时再跑一次 | 直接 `[OK] tunnel is up`，**未**起第二条隧道 |
| 计划任务 | `schtasks /Query` | `Status: Ready`，`Next Run Time` 每 2 分钟推进 |
| 巡检留痕 | 9 条单测（含「留痕失败不掩盖原异常」） | 全绿 |
| 脚本口径 | 14 条契约测试 | 全绿 |
| compose 契约 | 11 条契约测试 | 全绿 |
| 看门狗契约 | 9 条契约测试 | 全绿 |
| 生产 env | SSH 远端幂等写入 + 备份 | 四项全部就位，口令未回显 |

## 7. 遗留与待办

* **用户侧（无法代做）**：下一轮采集后核「**新增月份认不出 = 0**」。
  ⚠️ 该指标**只能从 2026-12 起算** —— 11 月云端是 56.69%，那是事故现场，不是新增问题。
* **v7.21.0 待办**：律 3 的候选名单副本物化视图（`shop_identity_resolution_candidates_v2_mv`）
  仍是**旧定义**（仓库资产脚本对已存在的副本只 `REFRESH`、**不改定义**）⇒ 需在部署流水线里
  先 `DROP` 旧副本再按资产重建；并加一条守护，防止「改了正本副本不跟」的静默分叉。
* **生产容器重建后**才能让新 `.env` 生效 ⇒ 随 v7.21.0 部署一并完成。
