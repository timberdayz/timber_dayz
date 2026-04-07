# Canonical 采集组件交接说明

日期：2026-03-23

## 目的

本文件用于新线程继续推进 canonical 采集脚本优化，避免依赖当前会话记忆。

注意：
- 不再覆盖根目录 `task_plan.md / findings.md / progress.md`
- 后续线程优先以本文件和 `docs/guides/` 下的 canonical 文档为准

## 当前已完成

### 1. canonical 规则与入口收口

已完成：
- 批量注册只注册 canonical 组件
- 组件版本列表只默认暴露 canonical 组件
- 同一 canonical 组件只保留一个当前工作入口
- `tools/test_component.py` 的 `--list / --all` 也已收口到 canonical 组件

### 2. 核心文档已就位

后续线程优先参考：
- `docs/guides/COLLECTION_SCRIPT_REFERENCE.md`
- `docs/guides/CANONICAL_COLLECTION_COMPONENTS.md`
- `docs/guides/CANONICAL_RUNTIME_ISSUES.md`
- `docs/guides/CANONICAL_COMPONENT_STATUS.md`
- `docs/guides/CANONICAL_TEST_EXECUTION_CHECKLIST.md`
- `docs/guides/CANONICAL_COMPONENT_PRIORITY_LIST.md`
- `docs/guides/CANONICAL_FIRST_BATCH_READY.md`

### 3. 当前 canonical 回归状态

最近一次已验证通过：
- `63 passed`

回归集包括：
- canonical 注册/列表
- Shopee export 契约
- TikTok export 契约
- Miaoshou export/login 契约
- 三平台组合链路
- 第一批 login 契约
- `tools/test_component.py` canonical 列表行为

### 4. 当前第一批实际测试对象

当前第一批实际测试对象固定为：
- `shopee/login`
- `shopee/products_export`
- `tiktok/login`
- `tiktok/shop_switch`
- `tiktok/export`
- `miaoshou/login`
- `miaoshou/export`

## 当前真实运行结论

### 1. 组件测试接口当前可用

已确认：
- `/api/auth/login` 正常
- `/api/component-versions/{id}/test` 可正常返回 `test_id`

因此当前“组件测试失败”不应再笼统归因于接口 500。

### 2. 当前已定位的真实问题点

#### A. 历史一次真实 500

已定位过一次真实 500 根因：
- 平台账号密码解密失败
- 后端返回：`密码解密失败,请检查账号配置`

这个问题在当前运行态下并不稳定复现。

#### B. 当前 `miaoshou/login` 的真实失败点

已通过真实测试目录确认：
- 测试目录：`temp/component_tests/test_bf78f134e331/`
- 结果文件：`result.json`
- 截图：`temp/test_results/login_error_20260323_181208.png`

当前真实失败原因：
- `miaoshou/login` 的 selector 已过时
- 具体失败在：
  - `#J_loginRegisterForm`
  - `input.account-input`
  - `input.password-input`
  - `button.login`

### 3. 已修复的测试器问题

已修：
- `tools/test_component.py` 在测试 Python `login` 组件时，先导航到 `account.login_url`
- 不再在 `about:blank` 上直接做 readiness check

## 当前未完成

### 1. `miaoshou/login` 还未完成真实修复

建议：
- 直接重录 `miaoshou/login`
或
- 改写当前 `miaoshou_login.py` selector

### 2. “保存组件失败”这次录制保存异常还未拿到实时栈

现状：
- 已检查保存接口代码路径
- 但未拿到这次前端保存失败的实时后端异常日志

后续线程若要继续查：
- 需要在用户再次点击“保存组件”时抓实时日志

### 3. 第一批 7 个组件尚未完成逐个真实页面验收

当前只完成了：
- 测试入口收口
- 文档交接
- 部分真实问题定位

尚未完成：
- 按 `miaoshou -> shopee -> tiktok` 逐个验收修复

## 新线程建议起点

建议新线程直接从这里开始：

1. 先处理 `miaoshou/login`
   - 优先用 Playwright CLI / codegen 重录
   - 让它重新对齐当前页面 selector
2. 然后在前端真实测试 `miaoshou/login`
3. 再测 `miaoshou/export`
4. 再转 `shopee`
5. 最后处理 `tiktok`

如果要继续查“保存组件失败”：
- 需要在新线程中复现一次保存动作并抓实时后端日志

## 工作区注意事项

当前 `git status` 中存在非本轮 handoff 的变更：
- `backend/tests/data_pipeline/test_https_nginx_hook.py`
- `modules/platforms/miaoshou/components/login_v1_0_1.py`

后续线程应先确认这些是否为用户自己的工作，不要误改。
