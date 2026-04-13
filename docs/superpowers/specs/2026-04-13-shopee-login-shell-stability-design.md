# Shopee Login Shell Stability Design

**Date:** 2026-04-13

## Goal

修复 Shopee 登录流程在“已登录壳层页但主内容不是首页”时的误判问题，并为登录完成判定增加页面稳定等待，避免过早检查导致的假失败。

## Problem Summary

当前 Shopee 登录组件和运行时登录 gate 对“登录成功”的定义过窄：

- 登录组件优先把成功定义为到达首页或业务首页。
- 当 OTP 提交后落在带有卖家中心壳层、账号菜单、客服浮标，但主区域显示异常内容的页面时，组件会把该状态视为 `manual_intervention`，而不是“已登录但落点异常”。
- 运行时 `login_status_detector` 对 Shopee 的已登录信号主要依赖 URL 关键词和旧 selector，无法稳定识别上述壳层页面。
- 判定发生得过早时，页面可能仍在跳转、注水、渲染登录壳层或清理旧登录 DOM，从而产生早判误差。

## Evidence

- 失败任务 `07c5946b-bb59-4e5b-84e6-c03424775a16` 的截图显示：
  - 左上角已出现 Shopee 中国卖家中心壳层
  - 右上角存在账号标识
  - 右侧存在客服/消息浮标
  - 中间主区域为异常内容，而非登录表单
- 失败组件测试 `test_11e44aa11b25` 记录为：
  - `login gate not ready`
  - `url=https://seller.shopee.cn/account/signin?next=%2F`
  - `input[type='password']` 可见即直接判定未登录
- 后续成功任务与历史日志表明：
  - 一旦系统识别到 `/seller`、`/portal` 等 URL，会继续导航并成功完成产品/服务/客服采集。

## Options Considered

### Option A: Only relax login component success rules

只修改 `modules/platforms/shopee/components/login.py`，将壳层页视为成功。

优点：
- 变更最小
- 直接解决 OTP 恢复后组件失败

缺点：
- `login_status_detector` 与 runtime gate 仍然可能误判
- 组件测试和真实采集的判定语义继续分叉

### Option B: Align login component and runtime gate around shell-ready semantics

同时修改登录组件与 `modules/utils/login_status_detector.py`，引入“已登录壳层稳定就绪”的次级成功语义，并在判定前统一等待页面稳定。

优点：
- 组件执行、运行时 gate、组件测试三条链路语义一致
- 能覆盖首页缺失、异常落点、非首页跳转等场景

缺点：
- 需要新增更明确的测试，防止把真登录页放宽成已登录

### Option C: Always navigate away after shell detection

一旦识别为已登录壳层，就强制跳到固定业务页后再继续。

优点：
- 避开中间异常页

缺点：
- 强依赖固定业务 URL
- 对不同权限、区域和未来页面调整更脆弱

## Chosen Design

采用 **Option B**，并只在必要时使用轻量跳转恢复，而不是把强制跳转作为默认成功路径。

### 1. 登录组件接受“已登录壳层稳定就绪”

在 `modules/platforms/shopee/components/login.py` 中：

- 保留“首页稳定命中”作为第一优先成功路径。
- 将 `_session_shell_looks_ready()` 命中的语义从“人工介入”改为“已登录成功，但当前不是首页”。
- 当页面满足壳层成功条件时，不再抛 `manual_intervention`。
- 对 OTP 恢复、人工恢复和正常账号密码登录后的等待逻辑统一使用同一套结果枚举。

### 2. 明确增加页面稳定等待

登录完成判定前新增稳定等待，不再在页面刚切换 URL 或刚出现单个信号后立即判断：

- 至少等待短暂 settle 窗口
- 连续多次轮询命中相同成功态才视为稳定成功
- 如果 URL、登录表单 DOM、壳层元素仍在快速变化，则继续轮询

稳定等待的目标不是固定 sleep，而是“连续稳定命中”：

- 首页成功：连续命中主页 URL + DOM ready 条件
- 壳层成功：连续命中壳层菜单/账号区/客服浮标等信号，且不再出现 OTP / 滑块

### 3. Runtime gate 识别壳层已登录信号

在 `modules/utils/login_status_detector.py` 中补强 Shopee 配置：

- 新增壳层已登录 selector，如顶部账号菜单、全托管服务入口、右侧客服/消息浮标等稳定信号
- 保持登录表单 selector，但避免单个密码框在混合页面中直接压倒更强的已登录证据
- 对 URL 未命中首页但元素与 cookie 已表明登录成功的页面，返回 `LOGGED_IN`

### 4. 保守边界

以下场景仍然不能视为成功：

- OTP 弹窗仍在
- 滑块验证码仍在
- 页面仅有登录表单，没有壳层登录信号
- 壳层信号与登录信号都不稳定，连续轮询仍无法确认

## File Impact

- Modify: `modules/platforms/shopee/components/login.py`
- Modify: `modules/utils/login_status_detector.py`
- Modify: `modules/apps/collection_center/runtime_session.py` only if shared stability waiting belongs there after implementation review
- Modify: `tests/unit/test_shopee_login.py`
- Modify: `tests/unit/test_login_status_detector.py`
- Modify: `backend/tests/test_collection_runtime_session.py` if runtime gate stability needs direct coverage
- Modify: `backend/tests/test_runtime_gate_contract.py` only if gate semantics change externally

## Test Strategy

### Login component tests

新增或扩展用例覆盖：

- OTP 后落在“已登录壳层 + 主内容异常页”时视为成功
- 页面先短暂保留登录表单 DOM、后进入已登录壳层时，不应过早失败
- 真正仍在登录页时，仍然返回失败或验证码分支

### Detector tests

新增或扩展用例覆盖：

- Shopee 壳层页 selector 命中时返回已登录
- URL 未命中标准首页但 cookie + 壳层元素命中时返回已登录
- 仅密码框可见且无壳层信号时返回未登录

### Runtime gate tests

必要时覆盖：

- `check_login_gate_ready()` 在稳定等待后才做最终判断
- 壳层页被接受为 `login confirmed`

## Success Criteria

- 复现截图对应场景时，不再因 `manual_intervention` 或 `login not confirmed` 提前失败。
- 登录成功但主内容异常时，后续导航仍能进入目标业务页并继续采集。
- 真正未登录场景仍然保持失败，不引入明显误判。
