# 采集测试环境基线

适用范围:
- `pwcli + agent` 页面探索
- 组件版本管理页测试
- `tools/test_component.py` 本地组件测试
- 本地正式采集调试

本文档定义采集测试环境的统一基线，目标是减少“录制能用、测试失败、生产异常”的环境漂移问题。

如果本文件与更高优先级规则冲突，优先级顺序为：
- 用户指令
- `AGENTS.md`
- `.cursorrules`
- 本文件

---

## 1. 核心原则

### 1.1 录制、测试、生产环境尽量同构

以下维度必须尽量一致：
- Playwright 官方浏览器
- 每账号独立 profile
- 每账号独立设备指纹
- locale / timezone / viewport
- 登录态恢复方式

禁止出现：
- 录制用 A 浏览器
- 组件测试用 B 浏览器
- 生产执行用 C 浏览器

### 1.2 上下文稳定优先于“临时修补”

如果 `pwcli` 使用持久化 profile 正常，而组件测试器异常，优先检查：
- 是否走了同一套持久化 profile
- 是否走了同一套指纹
- 是否只恢复了 `storage_state` 而没有复用完整 profile

不要优先猜测页面选择器错误或网络异常。

### 1.3 条件等待优先于固定等待

关键阶段不得只靠固定 `sleep` 判断成功，必须依赖：
- URL 信号
- 页面特征元素
- 对话框状态
- 文件落地状态

---

## 2. 浏览器基线

### 2.1 浏览器来源

统一使用 Playwright 官方浏览器，不允许通过 `channel` 或 `executable_path` 切到系统安装的 Chrome / Edge。

原因：
- 避免录制、测试、生产使用不同浏览器内核/通道
- 降低本地机器差异导致的问题
- 保持问题复现一致性

### 2.2 浏览器通道约束

采集测试路径中：
- 不设置 `channel`
- 不设置 `executable_path`
- 不设置 `executablePath`
- 不设置自定义 `browser`

如果必须切到 branded channel，只能作为临时排障手段，不能作为默认基线。

---

## 3. Profile 基线

### 3.1 一账号一套持久化 profile

强制要求：
- 一个账号对应一个独立 profile
- 不同账号不得共享同一个 profile
- profile 应长期稳定复用，不频繁重建

### 3.2 组件测试与 `pwcli` 对齐

如果 `pwcli` 工作流依赖持久化 profile 正常工作，则组件测试也应优先复用同一账号 profile。

对于以下组件，默认应优先使用持久化 profile：
- `login`
- `export`
- `date_picker`
- `filters`

如果 login 测试不使用持久化 profile，很容易出现：
- 登录后白屏
- 首页初始化异常
- 验证码回填后状态不连续

### 3.3 Profile 清理策略

仅在以下情况才清理或重建 profile：
- 已确认 profile 污染
- 同账号长期稳定复现白屏/脚本初始化失败
- 删除缓存后问题消失可证明 profile 状态异常

禁止把“每次失败都重建 profile”当作默认流程。

---

## 4. 指纹基线

### 4.1 每账号稳定指纹

一个账号对应一套长期稳定指纹，包含：
- user agent
- viewport
- locale
- timezone
- permissions

### 4.2 请求头最小化

对电商站点，`extra_http_headers` 只允许保留最低风险、最低必要内容。

当前基线：
- 保留 `Accept-Language`

禁止默认注入：
- `Cache-Control`
- `Accept-Encoding`
- `Upgrade-Insecure-Requests`
- 其他会增加 CORS 预检或改变浏览器默认行为的 header

原因：
- 这类 header 可能导致跨域脚本被拦截
- 会触发 CORS 预检失败
- 容易造成页面白屏或第三方 SDK 初始化异常

---

## 5. 登录成功判断基线

### 5.1 登录成功必须用双信号

禁止只看单一 URL。

推荐至少满足：
1. URL 已进入登录后页面
2. 首页关键元素可见

例如：
- `/welcome`
- `待办事项`
- `常用功能`
- 页面主导航

### 5.2 验证码回填后的判断

验证码回填后不得立即用一次短等待下结论。

必须等待：
- 错误提示出现
或
- 首页关键元素出现

超时后才失败。

---

## 6. 验证码交互基线

### 6.1 前端验证码框状态

前端验证码回填框只应在 `verification_required` 状态下展示。

一旦轮询状态离开 `verification_required`，应立即关闭：
- `verification_submitted`
- `running`
- `completed`
- `failed`

### 6.2 后端验证码状态

后端验证码状态文件应清晰区分：
- `verification_required`
- `verification_submitted`
- `verification_resolved`
- `verification_failed`

不要把“验证码已提交但登录失败”误判成“再次要求验证码”。

---

## 7. 故障分级基线

### 7.1 阻断型问题

这些应优先修复：
- 页面白屏
- 关键脚本因 CORS / CSP / 资源失败而未加载
- 登录表单不可见
- 首页信号无法出现
- 下载文件未落地

### 7.2 非阻断型问题

这些默认只记录 warning，不直接判组件失败：
- `Uncaught (in promise) undefined`
- 某些 service worker warning
- 第三方 SDK 非关键 warning

除非有证据表明它们直接导致页面关键功能不可用。

---

## 8. 电商站点风险控制基线

### 8.1 目标不是“绕过识别”，而是减少异常特征

优化方向应是：
- 环境稳定
- 上下文稳定
- 操作节奏合理
- 不引入额外异常 header / 脚本 / 通道

而不是对抗式伪装。

### 8.2 风险最小化措施

- 一个账号一套稳定 profile
- 一个账号一套稳定指纹
- 避免高频重复登录
- 避免一个账号多窗口并发跑
- 避免频繁切换浏览器环境
- 尽量复用正常登录态

### 8.3 禁止默认启用的高风险做法

- 随意修改浏览器 header
- 频繁切换 `channel`
- 多账号共享 profile
- 每次测试都从零新建设备环境
- 频繁清理 cookies / storage / cache

---

## 9. 失败证据基线

每次失败至少保留：
- 当前 URL
- 页面截图
- 控制台日志
- `progress.json`
- `result.json`

如果涉及验证码，还要保留：
- `verification_state.json`
- `verification_response.json`
- `verification_screenshot.png`

---

## 10. 执行建议

### 10.1 新问题排查顺序

1. 先看是否与 `pwcli` 环境一致
2. 再看是否复用了正确 profile
3. 再看指纹上下文是否注入了异常 header
4. 再看页面是否存在阻断型控制台错误
5. 最后才看组件逻辑本身

### 10.2 当前默认建议

- 继续使用 Playwright 官方浏览器
- 继续使用每账号独立持久化 profile
- 继续使用稳定指纹
- 继续使用 `pwcli + agent`
- 组件测试优先与 `pwcli` 的上下文模型对齐
