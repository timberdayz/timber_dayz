# 数据采集：按账号持久化会话与指纹

## 概述

主采集执行器（executor_v2）按**账号**持久化/复用浏览器会话，并按**账号**使用固定设备指纹，与业界「一账号一指纹、会话复用」一致，用于降低登录与验证码频率、避免多账号同指纹风控。

## 会话持久化

- **存储路径**：`data/sessions/<platform>/<account_id>/storage_state.json`（由 SessionManager 管理，文件内容为带包装的 session_data，其中 `storage_state` 字段用于注入 Playwright context）。
- **行为**：
  - 任务启动时优先按 `platform + account_id` 加载该账号的会话（有效期与 SessionManager 一致，默认 max_age_days=30）；若存在且有效则注入 `browser.new_context(storage_state=...)` 并执行登录组件，并传入 `config['reused_session']=True`。
  - 登录组件在复用会话时须先做**已登录检测**（如已在后台工作台页）；若已登录则跳过，若已登出或需安全验证则执行完整登录。仅在本轮**成功完成登录**后才将会话保存/覆盖到该账号路径；任务失败且未成功登录时不覆盖已有会话。
  - 若会话文件不存在、已过期或损坏，则视为无可用会话，直接走完整登录并在成功后保存新会话。
- **安全**：`data/sessions` 与 `profiles` 目录不进入 VCS、仅后端节点访问、权限按现有规范管理；会话文件仅限采集服务使用。

## 按账号固定指纹

- **来源**：执行器创建 browser context 时**统一**按 `platform + account_id` 从 **DeviceFingerprintManager** 获取或生成该账号的指纹（user_agent、viewport、locale、timezone_id 等），注入 `new_context(...)`，与录制、PersistentBrowserManager 等路径一致，实现「一账号一指纹」。主采集不混用 config/browser_fingerprints.py。
- **回退**：若 account_id 缺失或无法规范为字符串，则记录告警并回退到全局默认指纹与完整登录。

## 执行器统一建 context

- 浏览器进程由上层（如 collection router）启动（launch），仅将 `browser` 与任务参数传入执行器；**顺序与并行两种模式**均由执行器内部创建带指纹与可选会话的 browser context，不依赖上层预先创建的 context。

## 登录组件契约

- 复用会话时执行器传入 `config['reused_session']=True`。各平台登录组件（当前主采集为 shopee、tiktok、miaoshou）按统一契约实现：先做已登录检测（如 URL/元素判断已在工作台），已登录则跳过并返回 success=True，未登录或需安全验证则执行完整登录并返回相应 success。执行器据此决定是否触发完整登录与 save_session。

## 代理预留

- 在账号配置与执行器/浏览器配置层保留 proxy 相关字段（如 `proxy_required`、`proxy`）的读取与传递；执行器创建 context 时**暂不**注入 proxy，当前采集在住宅 IP 环境下无需启用。若未来需要多 IP/代理，可在此扩展并传入 context 的 proxy。

## 运维提醒

- **避免同一账号并发执行采集任务**，以防会话文件 load/save 竞态。若需支持同账号并发，可后续通过任务排队或账号级锁处理。

## 2026-04 对齐更新

- `SessionManager`、`PersistentBrowserManager`、`pwcli` 账号模式现在统一以仓库根目录为锚点，不再依赖当前工作目录。
- 账号级会话命名统一优先使用 `account_id`，缺失时才回退到 `username`、`store_name`、`name`、`label`。
- `pwcli` 人工调试如果要与正式采集共享账号级持久会话，必须带账号参数：
  - `Open-PwcliTiktok -AccountId '<account_id>'`
  - `Open-PwcliShopee -AccountId '<account_id>'`
  - `Save-PwcliTiktokState -AccountId '<account_id>'`
  - `Save-PwcliShopeeState -AccountId '<account_id>'`
- 不带 `AccountId` 的 `pwcli` 会话仍可用于临时探索，但它属于平台级共享调试空间，不应视为正式账号级持久会话来源。
- TikTok 如果打开后仍然回到登录页，优先判断为“该账号当前会话失效，需要重新登录刷新”，而不是继续排查会话命名空间。
