# 账号设备身份 SSOT 收口计划（2026-11-13 / 2026-11-14 修订）

> **2026-11-14 修订说明**
>
> 本文**方向已改**。原方向是「把所有账号对齐成**同一台电脑**的多个店」
> （A1 设备档案 / B1 同出口），与业务目标相反，已按用户澄清推翻并重写。
>
> **业务目标（现行）**：不同账号 = **不同浏览器指纹 + 不同出口 IP**，
> 目的就是**不让电商平台发现"一台电脑管理多个账号"**。
>
> 原方向产出的代码已全部回滚（`git checkout --`）：
> `docs/guides/COLLECTION_SESSION_AND_FINGERPRINT.md`、`modules/utils/sessions/device_fingerprint.py`、
> `modules/utils/sessions/legacy_shop_artifact_cleanup.py`、`modules/apps/collection_center/runtime_session.py`、
> `modules/apps/collection_center/executor_v2.py`、`backend/tests/test_device_fingerprint_headers.py`。
> 方向错误时新建的 `modules/utils/sessions/device_profile_manifest.py` 已**可恢复删除**。

---

## 1. 这一轮解决什么

| # | 事 | 之前 | 之后 |
|---|---|---|---|
| 1 | 设备侧的业务定义 | 两份权威文档相反（上位文档说注入、R8 说不注入） | **单一真源**：R8 = 账号设备画像（账号间不可关联） |
| 2 | 账号之间的指纹 | 旧「人造指纹池」UA 20 × viewport 12 ⇒ 组合上限 60，**实测已有两个账号完全撞车** | 每个主账号一套**自洽**画像，账号间必然不同 |
| 3 | `machine_id` | 6 个 profile **全部相同** `11608241`（机器级共享） | 按 account_id 确定性改写，**每账号独立** |
| 4 | 出口 IP | 权威位在店铺级；巡店与采集各自读 | 权威位上移到**主账号级**，巡店与采集同源（**资源未到位**） |
| 5 | 新增账号接入 | 无前置校验、不知是否已首登、白名单外账号**静默消失** | 有**前置体检 + 面板就绪徽标 + 白名单跳过原因** |
| 6 | 这条底线会不会被改坏 | 无守护 | 40 条契约测试，**已进 CI 根契约清单** |

---

## 2. 现状核对（实测，不是推测）

### 2.1 库与磁盘的事实（2026-11-13）

- 8 个主账号 / 52 个店铺账号；启用店铺 19 个；「启用 + 有 platform_shop_id」仅 **14/52**。
- **代理配置 0 条** ⇒ 当前所有账号仍共用同一个出口 IP（见 §6 缺口 1）。
- 6 个 profile 目录**全部**含 `Default/Network/Cookies`（27–44 KB）⇒ 都是真登录过的，无空壳。
- profile 目录名 = `main_account_id` 净化结果（去空格/冒号/`@`/括号，保留中文）：
  `shopee KR`→`shopeeKR`、`hongxikeji:main`→`hongxikejimain`、`Tiktok 1店`→`Tiktok1店`。
  ⇒ **新增 ID 若写成 `shopeeKR` / `Tiktok1店` / `hongxikejimain` 即撞车**（共用同一份登录态）。
- `profiles/shopee/Leslieshopmain` 已不存在但 `session.json` 仍引用 ⇒
  历史上该账号 ID 从 `Leslieshop:main` 改成 `shopee KR`，**登录态换过一次**。

### 2.2 设备标识隔离矩阵（决定性证据）

| 信号 | 实测结果 | 判定 |
|---|---|---|
| `machine_id` | 6 个 profile **全部相同** `11608241` | ❌ 一眼关联，必须隔离 |
| `client_id2` / `ablation_seed` | 各不同 | ✅ 天然按 profile 隔离 |
| `profile_color_seed` | 6 个相同 `-16033840` | ⚠️ 同类信号，需记账 |
| 旧注入方案（UA 池 20 × viewport 池 12） | `lcm(20,12)=60` ⇒ 组合上限 60；**实测 `hongxikeji:main` 与 `shopee KR` 完全撞车**（同 ua_index=14 / vp_index=6） | ❌ 必须换掉 |

### 2.3 `machine_id` 改写可行性（实测通过）

临时目录 + bundled Chromium（`ms-playwright/chromium-1181`），headless 与 headed **均验证**：
改写值被 Chromium **持久接受、不重新生成** ⇒ 只写一次、之后不再动。

---

## 3. 业务概念（这一轮的词汇表）

| 概念 | 业务含义 |
|---|---|
| **主账号（登录身份）** | 一个邮箱在电商平台的登录身份。**设备身份的绑定主体** |
| **店铺账号** | 同一登录身份下的多个店。**继承**主账号的画像与出口 |
| **设备画像** | 这个"人"用的那台电脑的浏览器人格：OS / 浏览器 / 版本 / 屏幕 / 时区 / 语言 |
| **机器标识（machine_id）** | Chromium 藏在配置里的"这台机器"编号；同机所有 profile 默认相同 |
| **出口 IP** | 账号访问外网的网络出口；巡店与采集必须同源，否则判定"环境突变" |
| **profile** | Chromium 用户数据目录，登录态（cookie）所在 |

**一句话**：一个登录身份 = 一台电脑 = 一套浏览器人格 = 一个出口 IP。

---

## 4. 设计决策（已定）

| # | 决策点 | 结论 | 依据 |
|---|---|---|---|
| D1 | 绑定粒度 | **主账号**（店铺账号继承） | 一个卖家用一台电脑管自己的多个店是真实的；致命的是"8 个主账号在同一 IP、同一 machine_id 下" |
| D2 | 画像注入方式 | **注入**，但必须**整套自洽** | 只改 UA 不改时区/语言/平台 = 头身不符，比不伪装更露馅 |
| D2b | 画像的 **OS 与地区** | **锁宿主**（OS = 宿主 OS；locale/时区 = 宿主地区） | ① Playwright 路径**改不了 `navigator.platform`** ⇒ 派 macOS 画像到 Windows 主机必然头身不符，且被字体/WebGL/canvas 立刻识破；② 平台会把**时区/语言**与**出口 IP 国家**交叉比对，而当前出口就是宿主 IP ⇒ 派 `de-DE/Europe/Berlin` = 自己制造三重矛盾。差异改由 **浏览器/版本/视口/`machine_id`/出口 IP** 承担 |
| D3 | 画像确定性 | 按 account_id **确定性派生** + 占用校验顺延 | 账号内稳定（设备人格不该隔几天变）、账号间不同、账号变多也不撞 |
| D4 | `machine_id` | 按 account_id uuid5 确定性派生，写入 `Local State` | 实测 Chromium 持久接受；幂等、失败不阻断 |
| D5 | IP 层 | **留接口不强制**（代理权威位上移主账号级） | 当前**没有代理资源**；强制会导致所有账号直连失败 |
| D6 | 并行扇出路径 | 不挂载 profile ⇒ **必须显式注入**；缺失**必须 WARN**，不得静默 | 静默 = 该账号本次采集用原生环境 ⇒ 撞指纹 |
| D7 | 旧指纹机制 | **保留**给非 profile 路径（录制 / 组件录制 / `PersistentBrowserManager`） | profile 模式不再使用；`data/device_fingerprints/` 26 文件**暂不清理** |

---

## 5. 规范口径（R8 及其小节）

真源：`docs/guides/COLLECTION_SESSION_LIFECYCLE.md`（生效版 v3.1 → 2026-11-14 修订）。

| 小节 | 内容 |
|---|---|
| **R8** | 账号设备画像（账号间**不可关联**）—— 四类信号对照表 |
| **R8.0** | 画像载体 = `profiles/<平台>/<账号>/.device_profile.json`，与登录态同生共死 |
| **R8.1** | 机器标识隔离：按 account_id 确定性改写 `Local State` → `user_experience_metrics.machine_id` |
| **R8.2** | 画像三条硬规则：账号间必须不同 / 账号内稳定 / 整套自洽 |
| **R8.3** | 三条路径同一套设备：人工巡店 / 顺序采集 / 并行采集 |
| **R8.4** | 出口同源：代理权威位在**主账号** `core.main_accounts.extra_config['proxy']` |

上位文档 `docs/guides/COLLECTION_SESSION_AND_FINGERPRINT.md`《按账号固定设备画像》整节已改写，
并在顶部加了冲突声明（以 R8 为准）。

术语表新增：**设备画像**、**机器标识**。验收项 **H** 改写为「账号间不可关联」口径。

---

## 6. 已知缺口（**必须留档，不许藏**）

| # | 缺口 | 性质 | 影响 | 解除条件 |
|---|---|---|---|---|
| **G1** | **IP 层无资源**（库里代理配置 **0 条**） | 资源缺口 | 所有账号**仍共用同一个出口 IP** ⇒ 平台仍可用"同一出口多账号"做关联 | 采购代理资源，写进主账号 `extra_config['proxy']` |
| **G2** | **深度指纹未覆盖**（canvas / WebGL / 字体 / GPU / 音频栈） | 技术债 | 同一台机器的这些信号仍跨账号一致 | V2：Chromium 启动参数级噪声注入（风险较高，需专门评估） |
| **G3** | 同一主账号下的**多个店铺账号共享画像与出口** | **刻意折中** | 平台若识别"这几个店共享指纹"，仍可能归成"一个老板" | 业务已确认接受（真实场景如此）；写进文档而非隐藏 |
| **G4** | 存量 9 个主账号的 `machine_id` **仍是 `11608241`** | 生效延迟 | **改写前**它们仍可被关联 | 下次巡店/采集时自动改写（幂等）；改写后即隔离 |
| **G5** | `profile_color_seed` 6 个相同 | 技术债 | 同类机器级信号 | 与 G2 一并处理 |
| **G6** | 存量账号 ID 规范不合规（`hongxikeji:main`、`shopee KR`、`Tiktok 1店`、`chenzeweinbnb@163.com`、含全角括号的） | 历史事实 | **改名会换 profile 目录 ⇒ 换登录态** ⇒ 成本高 | 体检脚本已记为 **WARN**；**不主动改名** |
| **G7** | 测试残留账号 `accept_main_1775126941575`（占一张巡店卡片）、`验证码测试账号`（platform 填成中文 ⇒ 永不入白名单） | 数据脏 | 噪声 | 待业务拍板（STATUS.md 未结项 #3） |
| **G8** | 旧指纹机制与 `data/device_fingerprints/` 26 文件仍在 | 已决策 | profile 模式已不用；非 profile 路径仍在用 | 暂不清理（决策 D7） |

---

## 7. 验收

见 `docs/superpowers/plans/2026-11-13-account-profile-device-identity-ssot-closure-execution.md`
（执行卡与实测证据）。

守护入口：

- `tests/test_account_device_isolation_contract.py`（25 条）—— 画像与隔离
- `tests/test_account_readiness_contract.py`（11 条）—— 就绪判据同源与可见性
- `tests/test_account_proxy_source_contract.py`（4 条）—— 代理权威位在主账号级

三者**已进 CI 根契约清单**（`ci.yml` 的 "Run root contract tests (no DB)" 步骤，57 → 60 条）。
不进清单的守护 = 没人主动执行的守护（仓库历史上有 221 个这种）。

> ⚠️ 代理契约**刻意做成纯同步文件**：`backend/tests/test_account_proxy_config.py` 含 9 个 async 用例，
> 在 CI 钉的 `pytest==7.4.3` / `pytest-asyncio==0.21.1` 下混进根契约清单会拿到**已关闭**的
> session 事件循环（`RuntimeError: Event loop is closed`）⇒ 断言移进纯同步新文件，
> 异步用例留在原文件由全量回归覆盖；根因记账到 V2（见 `STATUS.md`「当前未结」#8）。
