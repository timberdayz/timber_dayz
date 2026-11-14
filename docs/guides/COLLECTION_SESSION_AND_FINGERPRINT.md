# 数据采集：按账号持久化会话与指纹

> 会话的**生命周期与载体语义**（profile 单一载体、禁止人工覆盖、禁止打开即回写）以
> [`COLLECTION_SESSION_LIFECYCLE.md`](COLLECTION_SESSION_LIFECYCLE.md) 为准；本文只定义存储路径与指纹策略。
> **冲突处理**：本文与 `COLLECTION_SESSION_LIFECYCLE.md` 冲突时**一律以后者为准**。
> 「账号浏览器运行环境」的语义真源**只有 R8 一处**（2026-11-14 二次修订：结论由
> 「注入**账号设备画像** + `machine_id` 隔离」改为「**不造账号差异**，
> 只做 *去 `HeadlessChrome`* 与 *locale/时区跟出口*」）。

## 概述

主采集执行器（executor_v2）按**账号**持久化/复用浏览器会话 —— 这与业界
「一账号一浏览器环境、会话复用」一致，用于降低登录与验证码频率。

⚠️ 注意口径：**账号之间分开的是「状态层」**（cookie / localStorage / IndexedDB /
缓存 / 平台自己的设备令牌），由「**一个账号一个独立 profile 目录**」天然隔开；
**不是**靠"每个账号造一套不同的浏览器指纹"。原因（实测，2026-11-14）：

* 同一台机器上两个**独立 profile** 的 14 项指纹（canvas / WebGL 像素 / 字体集合 /
  UA / platform / 核数 / 屏幕 / 时区 / 语言 …）**完全相同** ⇒ profile 不产生指纹隔离；
* 同型号同配置的电脑硬件指纹**大量重复**（全球几百万台）⇒ 平台不会拿"指纹相同"
  判"同一台电脑"；
* Chromium 的 `machine_id` **网页读不到** ⇒ 平台看不到它。

⇒ 按账号派生指纹（每人一个分辨率 / 浏览器版本 / 语言）**没有关联收益**，
反而造出「分布外」的异常特征。详见 R8。

## 会话持久化

- **存储路径**：登录态的**唯一载体**是 Chromium 持久 profile —— `profiles/<platform>/<main_account_id>/`，由 `SessionManager.get_persistent_profile_path` 解析（目录名净化规则：`isalnum() or _ or -`，即**空格被去掉、中文保留**，所以账号 `shopee KR` 的目录是 `profiles/shopee/shopeeKR`）。**会话文件体系（`data/sessions/**`）已整体废除**，读写、评分、过期清理能力一并下线。
- **行为**：
  - 采集启动时按 `platform + main_account_id` 打开该账号的持久 profile（`launch_persistent_context(user_data_dir=...)`）。**登录态由 Chromium 自己维护** —— 采集链路不复制、不仲裁、不落第二份快照。
  - 正式采集**恒走持久 profile**（`choose_runtime_strategy` 对 `formal_collection` 直接返回 `persistent_profile`），不再探测任何会话文件。
  - 登录组件在复用 profile 时须先做**已登录检测**（如已在后台工作台页）；已登录则跳过，若已登出或需安全验证则执行完整登录。
  - 并行采集走**内存快照扇出**：主 profile 打开一次，快照只在内存中分发，**不落盘**。
- **安全**：`profiles` 目录不进入 VCS、仅后端节点访问、权限按现有规范管理。profile 内直接存放认证 cookie，访问控制要求与会话文件时代同级。

## 浏览器运行环境（不落盘、不按账号派生）

> 语义真源：[`COLLECTION_SESSION_LIFECYCLE.md`](COLLECTION_SESSION_LIFECYCLE.md) 的 **R8**。
> 本节只说「有哪些参数、谁负责、从哪来」。

- **不落盘**：**没有** `.device_profile.json` 这类文件。浏览器运行环境是**运行时参数**，
  由 `modules/utils/sessions/account_browser_identity.py` 统一产出，**与账号无关**。
- **内容**：只有三项 ——
  1. **UA**：真实二进制版本 + 真实宿主 OS token，**去掉 `HeadlessChrome`**
     （采集跑 headless，带这个标记会被一眼认出自动化）；版本与 OS token **一字不动**。
  2. **locale / timezone_id / Accept-Language**：**跟随出口 IP 所在地区**。
     现在出口就是宿主 IP ⇒ 地区取宿主；代理资源到位后按账号各自的出口查。
  3. **不注入屏幕尺寸**：屏幕是**宿主级**事实（真人管多个店，显示器只有一台），
     按账号差异化会造出「分布外」的异常特征。
- **归属**：**不绑账号**。所有账号拿到**完全相同**的一份 —— 这正是我们要的：
  同机多账号在指纹层本来就该一样（我们改不动），差异只体现在状态层与出口。
- **消费方**：人工巡店（CDP `Emulation.setLocaleOverride` / `setTimezoneOverride`）、
  顺序采集、并行扇出**共用同一份**环境参数（R8.3）。
- **非 profile 模式**（录制 / 组件录制 / `PersistentBrowserManager`）：不挂载 profile，
  仍使用 `DeviceFingerprintManager` 生成显式设备人格（这条路径没有 profile 原生环境可沿用）。

## 执行器统一建 context

- 浏览器进程由上层（如 collection router）启动（launch），仅将 `browser` 与任务参数传入执行器；**顺序与并行两种模式**均由执行器内部创建带**浏览器运行环境**（UA 去 Headless + locale/时区跟出口）与可选会话的 browser context，不依赖上层预先创建的 context。

## 登录组件契约

- 复用会话时执行器传入 `config['reused_session']=True`。各平台登录组件（当前主采集为 shopee、tiktok、miaoshou）按统一契约实现：先做已登录检测（如 URL/元素判断已在工作台），已登录则跳过并返回 success=True，未登录或需安全验证则执行完整登录并返回相应 success。执行器据此决定是否触发完整登录。

## 代理（已实现）

- **配置来源**：账号级代理的**权威位在主账号** `core.main_accounts.extra_config->'proxy'`（jsonb，不加列、不写迁移），店铺级 `core.shop_accounts.extra_config->'proxy'` 仅作**回退**（历史数据仍在店铺侧）。由 `backend/services/account_loader_service.py` 的 `AccountLoaderService._build_runtime_account` 与 `backend/services/shop_account_loader_service.py` 的 `ShopAccountLoaderService._build_payload` 平铺透出为 `proxy_enabled` / `proxy_server` / `proxy_region` / `proxy_username` / `proxy_password`。
- **解析规则只有一份**：`backend/services/account_proxy_config.py` 的 `resolve_account_proxy`（`AccountLoaderService` 与 `ShopAccountLoaderService` 共用的单一定义源）。它只认账号自有代理，**绝不回退**遗留地区池链路，也**不走** `fallback_to_direct` 静默直连；代理配置坏了（拆不出主机）**显式失败**，不退回「没配代理」。
- **注入位置**：采集执行器把账号级代理注入浏览器 context 的 `proxy=` 参数 —— profile 模式走 `launch_persistent_context(proxy=...)`（**浏览器进程级全局代理，优先**），并行扇出走 `browser.new_context(proxy=...)`；`runtime_session._build_playwright_context_options_from_fingerprint` 的白名单已含 `proxy`，不会再被丢弃。
- **凭据边界**：凭据**只随 `proxy=` 参数下传**。账号字典在进入组件 config 之前由 `strip_account_proxy_credentials` 剔除 `proxy_username` / `proxy_password` 与 URL 内嵌凭据 —— **不写进日志、不进组件配置**。
- **诊断暴露**：诊断字段 `session_proxy` 用 `mask_proxy_server` 脱敏后暴露（只留 scheme + host，抹掉凭据）。

## 运维提醒

- **避免同一账号并发执行采集任务**。会话文件体系已废除，但 profile 目录是**同一份**登录态：同一 `main_account_id` 并发打开同一个 profile 会撞 Chromium 的 ProcessSingleton。该约束在 [`COLLECTION_SESSION_LIFECYCLE.md`](COLLECTION_SESSION_LIFECYCLE.md) R6 中升级为硬规则：同一 `main_account_id` 的采集任务必须账号级串行（跨进程账号锁）。

## 2026-04 对齐更新

- `SessionManager`、`PersistentBrowserManager`、`pwcli` 账号模式现在统一以仓库根目录为锚点，不再依赖当前工作目录。
- 账号级会话命名统一优先使用 `account_id`，缺失时才回退到 `username`、`store_name`、`name`、`label`。
- `pwcli` 人工调试如果要与正式采集共享账号级持久会话，必须带账号参数（`Open-*` 打开的浏览器用的就是正式采集那个 profile 目录）：
  - `Open-PwcliTiktok -AccountId '<account_id>'`
  - `Open-PwcliShopee -AccountId '<account_id>'`
  - 人工在浏览器里登录成功后**直接关闭浏览器即可** —— 登录态由 Chromium 自己写进 profile，无需再执行任何「保存会话」动作（`Save-Pwcli*State` 系列已随会话文件体系废除）。
- 不带 `AccountId` 的 `pwcli` 会话仍可用于临时探索，但它属于平台级共享调试空间，不应视为正式账号级持久会话来源。
- TikTok 如果打开后仍然回到登录页，优先判断为“该账号当前会话失效，需要重新登录刷新”，而不是继续排查会话命名空间。
