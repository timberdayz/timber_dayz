# 采集组件协作规则

本文档描述 V2 架构下正式采集组件如何衔接、哪些属于顶层阶段、哪些属于 `export` 内部 helper。

## 核心结论

正式采集的顶层执行链只保留：

1. `login`
2. `export`

其他组件不再作为正式采集的独立顶层阶段，而是 `export` 内部可复用能力。

## 顶层阶段

### `login`

职责：

- 进入平台登录态
- 处理验证码/短信码门禁
- 让统一 login gate 确认已登录

它不是 `export` 的内部业务步骤，而是所有后续采集动作的统一门禁。

### `export`

职责：

- 承载一个数据域的完整正式采集流程
- 在内部调用导航、日期、筛选、导出、下载确认等 helper
- 以文件真实落地作为正式完成信号

## `export` 内部 helper 槽位

以下槽位是 `export` 内部复用能力，不是正式采集的独立顶层阶段：

- `navigation`
- `shop_switch`
- `date_picker`
- `filters`

这些 helper 可以单独维护、单独测试，但正式调度和正式执行不应把它们当成与 `login/export` 同级的采集阶段。

## 推荐的 `export` 结构

新的正式导出组件应尽量收敛成以下结构：

1. `wait_navigation_ready()`
2. `ensure_subtype_selected()`（如需要）
3. `ensure_popup_closed()`
4. `ensure_time_selected()`
5. `ensure_filters_applied()`
6. `click_search()`
7. `wait_search_results_ready()`
8. `ensure_export_menu_open()`
9. `click_export_target()`
10. `wait_export_progress_ready()`（如需要）
11. `wait_export_complete()`

## 组件衔接规则

组件之间不能通过“点过按钮”这种隐式动作衔接，必须通过可观察完成信号衔接。

典型信号包括：

- `login_gate`
- `navigation_ready`
- `date_picker_ready`
- `filters_ready`
- `export_complete`

推荐命名：

- `detect_*`：只读观察
- `ensure_*`：收敛到目标状态
- `wait_*`：确认完成信号

## 参数契约

正式组件统一围绕这些关键上下文字段工作：

- `platform`
- `account`
- `data_domain`
- `sub_domain`
- `granularity`
- `time_selection`
- `task.download_dir`
- `task.screenshot_dir`

其中：

- `time_selection` 决定页面侧如何选时间
- `granularity` 只负责输出命名、入库分类、调度粒度

## 验证码恢复规则

验证码和 OTP 恢复不应由每个组件私自发明新协议，必须复用共享恢复契约：

- 输入只能二选一：
  - `captcha_code`
  - `otp`
- 组件测试链通过测试目录恢复
- 正式采集链通过 Redis 恢复
- 两条链都要求同一执行上下文继续运行

## 一句话

V2 下正式采集只认 `login -> export` 两级主链，其他组件都属于 `export` 内部可复用 helper。
