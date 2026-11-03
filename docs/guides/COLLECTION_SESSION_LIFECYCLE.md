# 采集会话架构与账号身份（规范性业务规则）

## 0. 本文档定位

- **规范性文档**：本文定义「采集会话 / 账号身份」这套业务概念的**唯一权威语义**。代码实现、巡店面板、采集执行器都必须以此为准。
- **上位文档**：[`COLLECTION_SESSION_AND_FINGERPRINT.md`](COLLECTION_SESSION_AND_FINGERPRINT.md) 定义账号级指纹与存储路径。本文定义**会话载体、保存语义、并发与 IP 隔离**。
- **冲突处理**：本文与仓库其他文档冲突时以本文为准，并在同一任务内同步更新冲突文档。
- **状态**：**生效版 v3.1**（2026-11-03 实现回填）。
- **版本沿革**：v1/v2 确立了「会话文件覆盖写入」语义；v3 按业务决策改为**单一载体（profile）+ IP 隔离**，会话文件废除；v3.1 是**实现回填** —— 把 v3 已定稿的业务语义对应到已落地的代码与文件位置，**业务语义未变**。

---

## 1. 背景：2026-11-02 会话复用失效事故（事实记录）

真实本地采集（`config_run_id=235`）中，三个店铺任务全部要求重新登录 + 验证码回填。

审查结论（已用仓库真实代码可执行复现）：

| 事实 | 证据 |
|---|---|
| 会话文件里的认证 cookie 已过期 | `data/sessions/shopee/shopee KR/storage_state.json` 19 个 cookie 中 11 个过期；`SPC_SI` / `SPC_SEC_SI` 过期于 2026-06-23，`SPC_CNSC_SESSION` / `SPC_SC_OFFLINE_TOKEN` 过期于 2026-06-22 |
| 采集流程登录成功后写回的新会话被**无条件丢弃** | `session_manager.py:452-456`：旧文件带 `protected`/`manual_seeded` 且新写入不是"人工"时，直接 `selected_state = old_state` |
| 新会话质量分更高也进不去 | 复现：新 state 质量分 38 > 旧 state 29，场景 A（自动写回）仍然丢弃；场景 B（人工保存）成功写入 |
| 文件"看起来刚保存"但内容是旧的 | 文件 mtime = 20:23:54（采集期间被写过），但 `metadata.saved_at` 仍是 00:28、cookie 仍是 6 月那批 —— 写回的是旧内容 |
| 保护标记会自我传染 | `session_manager.py:493-496`：只要旧的是受保护会话，新的**自动**写入也会被继承打上 `manual_seeded=True` / `protected=True` |
| 三个任务共用同一份会话文件 | `core.shop_accounts` 中三个店铺的 `main_account_id` 均为 `shopee KR` |

**根本原因**：把"登录态"做成了**两份可独立演化的副本**（会话文件 + profile），再给两份副本加了一套"打分择优 + 来源优先级"的仲裁规则。于是仲裁规则本身成了故障源。

**结论**：登录态不该有副本，更不该需要仲裁。**只保留一份，让它由浏览器自己维护。**

---

## 2. 术语定义

| 术语 | 定义 | 边界 |
|---|---|---|
| **主账号** `main_account_id` | 平台侧的**登录单元**，也是**设备单元** | 一个主账号 = 一台"电脑" = 一个 profile 目录 |
| **店铺** `shop_account_id` | 业务与采集单元 | **不持有独立登录态**，只引用主账号的 profile |
| **profile** | `profiles/<platform>/<main_account_id>/`，Chromium 用户目录 | **唯一的登录态载体** |
| **登录态** | profile 内 Chromium 维护的 cookie / localStorage / IndexedDB | 由 Chromium 自己读写，不需要应用层"保存" |
| **快照** | 从 profile context 导出的 `storage_state`（cookie + localStorage） | **仅内存**，用于并行扇出；不是权威登录态 |

---

## 3. 唯一载体：profile

**会话文件（`data/sessions/<platform>/<account>/storage_state.json`）废除。**

| | 旧：会话文件 | 新：profile |
|---|---|---|
| 物理形态 | 一个 JSON 文件 | Chromium 用户目录（Cookies SQLite / Local Storage / **IndexedDB** / Service Worker / Cache / Preferences / Local State） |
| 谁维护 | 应用层 `SessionManager.save_session` | **Chromium 自己** |
| 写入时机 | 需要显式保存，还可能互相覆盖 | 登录成功即自动持久化 |
| 仲裁 | 需要"人工优先 / 质量分回退"等规则 | **不需要** —— 只有一份 |
| 并发 | 可并发（独立 context） | profile 只能开一次；并发在快照层解决 |
| 设备真实性 | 只有 cookie + localStorage，**缺 IndexedDB** | 完整浏览器环境 |
| 可移植性 | 明文 JSON，可跨机搬运 | 绑定本机（Chromium 加密存储） |

**为什么 profile 更接近真实环境**：主流风控（Akamai / DataDome / PerimeterX / Cloudflare）用 **localStorage + IndexedDB 组合**生成持久设备标识。同一份 cookie 出现在「IndexedDB 为空的新 context」上，会被判定为「cookie 被复制 / 异地使用」→ 风险分上升 → 验证码变多。仓库自己的代码也已承认这一点（`runtime_session.py:702-704`：profile 模式下刻意不覆盖 UA / locale / 时区，让 Chromium 复用 profile 原生环境）。

**平台与路径**：

| 平台 | profile 目录 | 说明 |
|---|---|---|
| shopee | `profiles/shopee/<main_account_id 去空格>` | 例：`shopee KR` → `shopeeKR` |
| tiktok | `profiles/tiktok/<main_account_id 去空格>` | 例：`Tiktok 1店` → `Tiktok1店` |
| 全部 | 统一用 `SessionManager.get_persistent_profile_path(platform, main_account_id)` | **单一命名规则来源**，取代现有 `safe_session_account_dirname` / `work_tag` / `slugify` 三套并存的规则 |

---

## 4. 核心规则

> **一句话：账号 = 一台电脑；这台电脑的浏览器目录（profile）就是这个账号在平台上的全部身份。登录成功，Chromium 自己就把它记住了 —— 应用层不需要"保存"这个动作。**

### R1 — 真相源唯一

profile 是唯一的权威登录态载体。**不再有第二份副本，也不再需要任何"谁覆盖谁"的仲裁规则。**

### R2 — 登录即持久

采集在 profile context 里完成登录后，Chromium 自行把新 cookie 写回 profile。**应用层不执行任何"保存会话"动作。**

### R3 — 人工确认即成立

巡店面板的「打开巡店」用**同一个 profile** 开一个 headed 浏览器；用户在浏览器里登录，Chromium 自动持久化。

**「保存会话」按钮废除**（语义上被「打开巡店」完全覆盖）。程序**不判定**登录态是否成立 —— 用户亲眼所见即成立。

### R4 — 读取即信任

采集直接打开 profile 并跑登录组件的已登录检测：

- 已登录 → 直接采集；
- 未登录 → 完整登录（可能需要验证码），成功后按 R2 自动持久化。

**不做"有效期预判"**，也不用质量分。复用了什么、是否过期，由平台的实际响应决定。

### R5 — 并行扇出用内存快照

并行采集（同任务多数据域）：

1. `launch_persistent_context(profile)` —— **profile 只开一次**
2. 在该 context 内完成登录
3. 从该 context 导出 `storage_state` **内存快照**
4. 关闭 profile context
5. 每个数据域：`browser.new_context(storage_state=内存快照)` → 并发采集

**快照只在内存中传递，不落盘。** 快照是派生产物，可随时从 profile 重新生成。

### R6 — 账号级串行（跨进程）

同一个 `main_account_id` 的 profile 目录**不能被两个浏览器进程同时打开**（Chromium 对 user_data_dir 加独占锁）。

- 同一账号的采集任务必须**串行**；
- 现有的 `MainAccountSessionCoordinator` 是**进程内** `asyncio.Lock`，而生产 celery 是 `--concurrency=4`（prefork 4 子进程），**跨进程无效** → 必须换成**跨进程锁（Redis）**。

### R7 — 正常关闭才能落盘

Chromium 的 cookie / localStorage 写入 profile 是**异步刷盘**的，发生在 context 正常关闭时。

- 采集结束、巡店窗口关闭，必须**正常关闭 context / 浏览器**，不能 `kill` 进程；
- 异常退出后 profile 可能停留在旧状态 → 表现为"登录了但没记住"，重跑一次即可自愈。

### R8 — 指纹沿用 profile 原生环境

profile 模式下**不注入** `user_agent` / `locale` / `timezone_id` 等运行时覆盖项，沿用 Chromium 从 profile 读到的原生环境（与 `normalize_persistent_profile_context_options` 现有行为一致）。

理由：profile 模式下 UA、语言、时区、字体、屏幕、IndexedDB 全部来自同一台"电脑"，**内部自洽**；强行注入反而会让 UA 与 Accept-Language / 时区对不上，比原生更露馅。

**推论**：顺序采集路径与并行采集路径的指纹行为必须**一致**（都以 profile 原生环境为准）。

---

## 5. IP 隔离与代理规则

### P1 — IP 绑账号

代理配置挂在**账号**上（`core.shop_accounts`），**一账号一 IP**。

理由：IP 隔离要解决的是"同一账号不该从多个 IP 出现"。IP 必须与该账号的设备身份（profile）绑定，而不是与某个快照绑定。

### P2 — 登录与使用同 IP

账号的**登录**（人工巡店登录 / 采集首次完整登录）与**后续使用**必须走同一个 IP。

平台可能把 cookie 与登录 IP 关联；换 IP 使用同一 cookie 比"同设备同 IP"更可疑。

### P3 — 快照继承账号 IP

R5 的内存快照由 profile context 派生，而 profile context 用的就是账号的代理 → 快照天然继承该账号的 IP。**不得把一个账号的快照用于另一个账号或另一个 IP。**

### P4 — 代理链路必须打通

现状代理链路**三层全断**，必须补齐：

| 断点 | 位置 | 修法 |
|---|---|---|
| 调用点恒传 `None` | `executor_v2._open_runtime_bundle(proxy=None)` 及各调用点 | 从账号配置解析代理并传入 |
| 账号配置无 `proxy_required` 字段 | `core.shop_accounts` 表 | 在账号配置上新增代理字段（`proxy_enabled` / `proxy_server` / `proxy_region` 等），或规范放入 `extra_config` jsonb |
| context options 白名单丢弃 `proxy` | `runtime_session._build_playwright_context_options_from_fingerprint` 的 `allowed` 集合 | 加入 `proxy`；或改为在 profile / browser 层注入 |
| **profile 模式完全没传 proxy** | `runtime_session.py:758` `launch_persistent_context(user_data_dir=..., **launch_options, **context_options)` | 显式传入 `proxy=proxy` |

**两种模式的代理注入位置**：

- profile 模式 → `launch_persistent_context(proxy=...)`（浏览器进程级，Playwright 原生支持）
- context 模式（并行扇出） → `browser.new_context(proxy=...)`；**注意 Chromium 下 per-context proxy 会让 Playwright 另起浏览器进程**，4 路并发即 4 个进程，资源开销上升 → 优先用「浏览器级全局代理 + 同账号同 IP」的方式，避免 per-context proxy。

---

## 6. 废除清单

以下能力**已废除**（代码已删除）。落地位置按**函数名 / 模块路径**标注 —— 行号会随后续提交漂移，函数名才稳定。

| 废除项 | 已落地位置（函数 / 模块） | 理由 |
|---|---|---|
| **会话文件整体**（`data/sessions/**`） | `modules/utils/sessions/session_manager.py` —— `SessionManager.save_session` / `load_session` / `restore_session` / `get_session_path` / `get_session_metadata` / `list_sessions` / `cleanup_expired_sessions` / `delete_session` / `is_session_valid` 这一族会话文件 API 已整体删除 | 登录态副本是本次事故的根源；profile 已能完整承载 |
| **人工会话保护**（旧的是人工 + 新的是自动 → 保留旧的） | 同上 —— 随会话文件 API 族一并删除 | 无第二份副本，不再需要仲裁 |
| **保护标记自我传染** | 同上 —— 随会话文件 API 族一并删除 | 同上 |
| **质量分回退保护**（`session_quality_score` / `session_meets_quality_gate`） | `modules/utils/sessions/session_manager.py` —— `session_quality_score` / `session_meets_quality_gate` 已随会话文件 API 族删除 | 同上；且分数不看有效期，过期会话拿 29 分照样"合格" |
| **30 天过期门禁** | `SessionManager.cleanup_expired_sessions` / `is_session_valid`（随会话文件 API 族删除） | 读取即信任（R4） |
| **巡店「保存会话」按钮与 `pwcli state-save`** | `scripts/pwcli_helpers.ps1` 的 `Save-Pwcli*State` 系列函数已删；`modules/utils/pwcli_native.py` 的 `command_state_save` 已删 | profile 自动持久化，导出动作无意义（R3） |
| **`pwcli open` 打开后回写会话** | `modules/utils/pwcli_native.py` 的 `command_open` 不再回写会话 | 打开不是登录成功；网络抖动时抓到的信息可能残缺 |
| **profile 引导落盘**（`_bootstrap_session_from_profile_sync` 写盘） | `modules/apps/collection_center/runtime_session.py` —— `_bootstrap_session_from_profile_sync` 的写盘路径已删 | profile 本身就是引导源，无需再复制一份 |
| **顺序采集路径的 storage_state 优先** | `modules/apps/collection_center/runtime_session.py` —— `choose_runtime_strategy` 对 `formal_collection` 恒返回 `persistent_profile` | 统一走 profile |
| **三套并存的目录命名规则** | 统一为 `modules/utils/sessions/session_manager.py` 的 `SessionManager.get_persistent_profile_path`（取代 `safe_session_account_dirname` / `SessionManager._safe_filename` / `pwcli_account_inventory.work_tag`） | 单一命名规则来源 |

---

## 7. 目标流程

### 7.1 人工巡店

```
巡店面板「打开巡店」
  └─ pwcli open --headed --account-id <main_account_id>
       └─ launch_persistent_context(profiles/<platform>/<main_account_id>, proxy=账号代理)
            └─ 用户在浏览器里自行登录（含验证码）
                 └─ 正常关闭浏览器 → Chromium 写回 profile   R2/R7
```

面板动作收敛为两个：**打开巡店** / **跳过（清除状态）**。「保存会话」按钮移除。

### 7.2 采集（顺序）

```
采集任务启动
  └─ 跨进程锁 acquire(platform, main_account_id)        R6
       └─ launch_persistent_context(profile, proxy)      R8
            └─ 登录组件：已登录检测
                 ├─ 已登录 ──────────────► 采集
                 └─ 未登录 → 完整登录
                        └─ 成功 ────────► 采集（Chromium 自动持久化）  R2
  └─ 正常关闭 context → profile 落盘                    R7
  └─ 释放锁
```

### 7.3 采集（并行）

```
采集任务启动
  └─ 跨进程锁 acquire(platform, main_account_id)        R6
       └─ launch_persistent_context(profile, proxy)
            └─ 登录组件（已登录 / 完整登录）
                 └─ 导出内存快照                          R5
       └─ 正常关闭 profile context                        R7
       └─ 每个数据域：browser.new_context(storage_state=内存快照) → 并发采集
  └─ 释放锁
```

### 7.4 数据流（不变）

采集产出文件 → `catalog_files`（`status=pending`）→ `auto_ingest_pending_files` 认领 → 模板/契约校验 → 落 raw → `raw → semantic → mart → api → backend router → frontend`。

---

## 8. 诊断字段

会话相关的诊断字段随载体一并调整：

| 旧字段 | 新字段 | 说明 |
|---|---|---|
| `session_quality_score` | — | 质量分废除 |
| `session_quality_gate_passed` | — | 质量门槛概念废除 |
| `session_quality_source` | `session_source` | 取值 `profile`（登录态来自 profile） |
| `session_manual_seeded` | — | 人工播种概念废除（profile 由人工登录建立，但这是常态不是标记） |
| `session_protected` | — | 会话保护概念废除 |
| — | `session_profile_path` | 当前使用的 profile 目录 |
| — | `session_reused` | 本次是否复用了 profile 中已有的登录态 |
| — | `session_proxy` | 生效的代理标识（脱敏） |

**前端**（`frontend/src/domains/collection/views/collection/CollectionTasks.vue`）会话诊断展示已同步收敛：删除「质量来源」「质量评分」「质量门槛」「人工播种」「会话保护」五项，新增「会话载体」（`session_profile_path`）、「是否复用」（`session_reused`）、「出口代理」（`session_proxy`）三项，保留「会话来源」（`session_source`）。

---

## 9. 已确认的业务决策

| # | 决策点 | 裁定 |
|---|---|---|
| D1 | `pwcli open` 打开平台后是否回写会话？ | **不回写**（打开 ≠ 登录成功；网络抖动可能残缺） |
| D2 | 人工保存会话时程序是否校验登录态？ | **不校验**，用户确认即成立（D3 后已无"保存"动作） |
| D3 | profile 引导出的内容能否落盘为会话文件？ | **会话文件已废除**，该问题消失 |
| D4 | 同一主账号的多个采集任务是否允许并发？ | **不允许，账号级串行**（R6，需跨进程锁） |
| **D5** | 会话文件保留还是废除？ | **彻底废除，只用 profile**。先看效果 |
| **D6** | 巡店「保存会话」按钮？ | **改成「打开巡店」**，登录态由 profile 自动存 |
| **D7** | IP 隔离（代理链路）是否本次一起做？ | **一起做**：修三层断点 + 账号配置加 proxy 字段 |
| ~~S1~~ | 人工保存时备份旧文件为 `storage_state.prev.json` | **否决**（会话文件已废除，该项自动失效） |

### 9.1 已知代价

| 代价 | 说明 | 退路 |
|---|---|---|
| **登录态绑本机** | profile 是 Chromium 加密目录，换机 / 重建 profile 需重新登录 | 人工巡店重新登录一次 |
| **异常退出可能丢登录态** | cookie 刷盘发生在 context 正常关闭时（R7） | 重跑一次采集自愈 |
| **代理链路首次接通有风险** | 代理参数错误会导致连不上平台 | 先在单账号灰度验证，再全量 |
| **per-context proxy 开销** | Chromium 下 per-context proxy 会另起浏览器进程 | 优先用浏览器级全局代理 |

---

## 10. 验收口径

| 场景 | 期望 |
|---|---|
| A. 新账号首次采集 | profile 目录自动创建；需登录 + 验证码；登录成功后 **profile 内 cookie 有效期在未来** |
| B. 紧接着再采集同一主账号 | **免验证码**，直接复用 profile 登录态 |
| C. 人工巡店登录后采集 | 巡店打开的浏览器与采集用的是**同一个 profile 目录**；采集复用成功 |
| D. 巡店面板 | 只剩「打开巡店」「跳过」两个动作；无「保存会话」按钮 |
| E. `data/sessions/` | 不再产生新的会话文件；目录可整体删除 |
| F. 账号级串行 | 同一 `main_account_id` 的两个任务不重叠（跨进程也成立） |
| G. IP 隔离 | 账号 A 的任务出站 IP = 账号 A 配置的代理；账号 B 不同；登录与使用同 IP |
| H. 指纹一致 | 顺序与并行路径的 UA / locale / 时区都来自 profile 原生环境，不再被运行时注入覆盖 |
| I. 异常退出 | 强杀浏览器后重跑，登录态自愈（Chromium 重新拿 cookie） |

### 10.1 验收实测记录（2026-11-03，main `180b2f6c`，本机 Windows）

> **验收状态**：自动化能验的都验完了；**「登录一次 → 后续免验证码」这一段需要账号持有人配合，已按用户决定移交用户自行验证**
> （操作手册见 `docs/superpowers/plans/2026-11-02-collection-profile-only-architecture.md` §10.4.2）。
>
> 环境：Docker 栈（postgres 15432 / redis 16379 / celery-worker / celery-beat）+ **本机**后端
> `python run.py --local`（后端端口 **8001**，路由 740 条）。
> 验收账号：`shopee_sg_eternalbloom_local` → 主账号 **`shopee KR`** → profile `profiles/shopee/shopeeKR/`。

| 场景 | 实测结果 | 结论 |
|---|---|---|
| A. 首次采集需登录 | 采集任务真实跑到 `status=verification_required` / `verification_type=otp`；Shopee 登录页已**自动填好**主账号 `Leslieshop:main` 与密码；OTP 发往 `+86 191****371` | ✅ 前半段符合；「登录成功后 cookie 有效期在未来」**待人工回填 OTP 后**验 |
| B. 紧接着再采集免验证码 | 依赖 A 的登录成功 | ⏸ **待人工**（OTP 只能由账号持有人提供） |
| C. 巡店登录 → 采集复用 | 面板 `account_id` **就是** `main_account_id`（`build_inspection_accounts`）；巡店侧 `pwcli_native.runtime_account_profile_dir` = `profiles/<平台>/<主账号ID去空格>` → `profiles/shopee/shopeeKR`；采集侧 `SessionManager.get_persistent_profile_path` **同一目录** | ✅ 路径一致（代码核对 + 运行时探针实测） |
| D. 巡店面板无「保存会话」 | 全仓 grep：生产代码里「保存会话」按钮、`Save-Pwcli*State`、`pwcli state-save` **全部清零**（只剩测试与文档里的「已删除」记录） | ✅ |
| E. `data/sessions/` 不新增 | 采集前后均为 **19 个 `storage_state.json`（1.47 MB）**，无新增 | ✅ |
| E'. `data/sessions/` 磁盘清理 | **用户 2026-11-03 决定「立刻备份并删除」** → 整体改名保留在 `data/sessions.bak-20261103/`（19 个文件 / 1,536,719 bytes，可随时改名还原）；**原 `data/sessions/` 已不存在**（且有测试断言该目录不得存在） | ✅ |
| E''. `_alt` 旁路 profile | **用户 2026-11-03 决定删除** → `profiles/shopee/虾皮巴西东朗照明主体_alt/` 已移入回收站；主 profile `profiles/shopee/shopeeKR/` 完好 | ✅ |
| F. 同主账号串行 | 本机后端持有 collection leader lock（`leader_lock: acquired`），容器 worker 处于 standby | ✅ |
| G. IP 隔离（流量经代理） | 本地假代理 `127.0.0.1:18888` 实收 **12 条**请求行，含 `CONNECT seller.shopee.cn:443`、`CONNECT seller.shopee.sg:443`、`CONNECT patronus.idata.shopeemobile.com:443` | ✅ 链路通；**真实出口 IP 待真凭据补验** |
| H. 指纹不被运行时覆盖 | 运行时探针 `user_agent=null` / `runtime_locale=null` → 取 profile 原生环境，未被注入覆盖 | ✅ |
| I. 异常退出自愈 | — | ⏸ 未验（需人工中断浏览器） |

**诊断字段实测值**（运行时探针，走生产代码 `open_persistent_runtime_bundle` → `_runtime_session_diagnostics`）：

| 字段 | 实测值 |
|---|---|
| `session_profile_path` | `profiles/shopee/shopeeKR`（主账号 ID 目录，非店铺账号 ID） |
| `session_reused` | `true` |
| `session_source` | `profile`（对外单值） |
| `session_proxy` | `http://127.0.0.1:18888`（脱敏后不含凭据） |

凭据脱敏实测：`http://user:pass@proxy.example.com:8080` → `http://proxy.example.com:8080`；
`http://user:pass`（缺 host）→ `http://***`。

**两条必须记住的口径（实测得出，写下来避免误判）**：

1. **`login_gate_result` 只在「登录门通过后」才落库。**
   登录未完成（等 OTP）时，`core.collection_task_logs` 里**只有**「任务已创建」「等待验证码回填」两行，
   `session_reused` / `session_source` / `session_profile_path` / `session_proxy` 全部拿不到。
   → 验收取证 SQL 必须挑**登录成功过的那次任务**，不能拿首次登录的任务当证据。
2. **`session_reused` 是「载体判据」，不是「登录态有效性判据」。**
   判据 = Chromium 的 cookie 库文件存在（`Default/Network/Cookies`）。
   实测：profile 有 cookie 库 → `session_reused=true`，但 cookie 已过期，采集仍要求重新登录（OTP）。
   → 它的语义是「**有**可复用的载体」，不代表「**当前有效**」；后者由 `login_gate_ready` 回答。

**本机跑验收的三个前提**（踩过一次，记下来）：

1. 后端端口是 **8001**（不是 8000）；`run.py --local` 会自动选端口，日志里有。
2. `.env` 里的 `CLOUD_DATABASE_URL` 指向**不存在的**云库（`127.0.0.1:15433`）→ 启动检查判定 `error` → 后端直接退出。
   本地验收需在 **`.env.local`** 里把它置空（`.env.local` 在 `.env` 之后加载且 `override=True`，能覆盖 `.env`）。
3. **采集任务由本机 API 进程内 `asyncio.create_task` 执行，不走 Celery。**
   Docker celery worker **没有挂载 `profiles/`** → 采集必须由本机后端执行；容器里执行会看不到主机的登录态。

---

## 11. 变更记录

| 日期 | 版本 | 说明 |
|---|---|---|
| 2026-11-02 | 草案 v1 | 基于会话复用失效事故重写会话语义：确立"最后写入者胜出"，废除来源优先级与质量分回退保护 |
| 2026-11-02 | 生效版 v2 | 落定 D1~D4：人工保存即确认、`pwcli open` 不回写、profile 引导不落盘、同账号串行 |
| 2026-11-02 | **生效版 v3** | 架构升级为**单一载体（profile）**：会话文件废除（D5）、巡店「保存会话」改为「打开巡店」（D6）、IP 隔离链路一并打通（D7）、新增 R7 正常关闭落盘与 P1~P4 代理规则 |
| 2026-11-03 | **生效版 v3.1** | **实现回填**（**业务语义未变**，只把 v3 已定稿的语义对应到已落地的代码与文件位置）：① **会话文件体系废除落地** —— `session_manager.py` 会话文件 API 族整体删除、`runtime_session.py` profile 引导落盘删除、正式采集恒走 profile；② **诊断字段收敛** —— 废止 `session_quality_*` / `session_manual_seeded` / `session_protected`，前端改为「会话载体 / 是否复用 / 出口代理」三项；③ **代理链路打通** —— `extra_config->'proxy'` → `resolve_account_proxy` → 浏览器 `proxy=` 注入，凭据只随 `proxy=` 下传；④ **巡店面板动作收敛为「打开巡店」**（原「保存会话」按钮与 `pwcli state-save` 已删） |
| 2026-11-03 | 验收回填（业务语义未变） | §10 补 **10.1 验收实测记录**：本机真实采集跑到「等 OTP」→ 证明首采需人工登录；本地假代理实收 12 条 `CONNECT` → 证明流量经代理；诊断字段探针实测 `session_profile_path=profiles/shopee/shopeeKR` / `session_reused=true` / `session_source=profile` / `session_proxy=http://127.0.0.1:18888`。同时记下两条口径：`login_gate_result` 只在登录门通过后落库、`session_reused` 是「载体存在」而非「登录态有效」。**磁盘清理落地**：`data/sessions/` 已备份为 `data/sessions.bak-20261103/` 后移除，`_alt` 旁路 profile 已删除。「登录一次→免验证码」一段移交用户自行验证（手册见实施计划 §10.4.2） |
