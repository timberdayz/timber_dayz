# Tasks: 网页登录验证码统一优化

## 1. 执行器与验证码契约

- [x] 1.1 确认 executor_v2 中 VerificationRequiredError、verification_required、verification_type、screenshot_path 已支持「任务 paused + 前端回传」流程；若 verification_type 未区分 OTP 与图形验证码，则扩展为支持 `graphical_captcha`（及既有 OTP 类型）
- [x] 1.2 恢复/提交验证码 API 契约：`POST /tasks/{task_id}/resume` 接受请求体（如 `{ "captcha_code": "..." }` 或 `{ "otp": "..." }`）；若任务已非「等待验证」状态（已超时/失败/完成）则返回 4xx 并提示「验证已超时或任务已结束，请重新发起采集」；否则将验证码写入约定存储（如 **Redis keyed by task_id**）。**正在等待中的执行器**（同一进程、同一 page）从存储读取验证码，在**当前 page** 上填入并点击提交后继续。须实现「验证码暂停时进程与 page 保持存活并阻塞等待（轮询 Redis 等）」的架构，不得采用「paused 后进程退出再重新启动任务」——因现代化页面刷新会使验证失效
- [x] 1.3 文档化：在数据采集或执行器文档中说明「验证码类型、检测时机、人工回填与可选打码」的契约，并注明检测逻辑有头/无头一致、应对按无头生产设计（人工回填为主、打码可选）— 见 `docs/guides/COLLECTION_LOGIN_VERIFICATION.md`
- [x] 1.4 后端持久化：执行器在需要验证码时（进入阻塞等待前）通过**回调**将 `verification_type`、`screenshot_path` 写回任务表 `verification_type`、`verification_screenshot` 并将任务状态置为 paused；任务详情/列表接口返回上述字段。GET `/tasks/{task_id}/screenshot` 使用任务表字段 **`verification_screenshot`**（与 schema 一致）。多实例部署时截图须写入共享存储或约定单实例/亲和。执行器此处不 return，而是阻塞等待用户回传；**超时后**结束等待、置任务失败或 verification_timeout 并 return 释放浏览器
- [x] 1.5 登录阶段验证码暂停：`_execute_python_component` 对 `VerificationRequiredError` 不得吞掉，须 re-raise；执行器在「登录组件」调用块外增加 `except VerificationRequiredError`，捕获后通过回调持久化 verification_type、screenshot_path 并置任务为 paused，然后**阻塞等待**（轮询 Redis 等）直至用户提交或**超时**；超时后结束等待、置任务失败或 verification_timeout 并 return；收到回传后在**同一 page** 上填入并点击提交后继续，不 return 直至最终完成或失败
- [x] 1.6 若仍保留 YAML/Playwright 登录路径：在该路径的登录块外同样需捕获 `VerificationRequiredError` 后**持久化并阻塞等待**（与 1.5 一致），不在此处 return paused；若该路径已废弃可不实现
- [x] 1.7 导出阶段验证码：域循环内捕获 `VerificationRequiredError` 时同样通过回调持久化并阻塞等待（不 return），收到回传后在**同一 page** 上填入并继续该域导出，再继续后续域或结束
- [x] 1.8 **适配层不吞掉 VerificationRequiredError**：在 `PythonComponentAdapter.login()` 与 `export()` 中，在通用 `except Exception` 之前对 `VerificationRequiredError` 做 re-raise，使执行器能进入「验证码暂停 → 阻塞等待 → 同一 page 继续」流程；此为框架级修复，适用于所有平台（妙手/Shopee/TikTok 等），不针对单一采集脚本

## 2. 妙手登录组件改造

- [x] 2.1 在点击「立即登录」后，**缩短等待**并在短轮询（如 2–3 秒内）检测是否仍停留在登录页且出现「请输入验证码」及图形验证码输入框/图片（通过 Playwright 选择器）；避免固定 15 秒轮询后才报错
- [x] 2.2 若检测到图形验证码：若 config 中已有 captcha_code（或 otp 用于图形码），则填入并再次点击登录，然后按现有逻辑判断是否跳转成功；否则抛出 VerificationRequiredError(verification_type="graphical_captcha", screenshot_path=...)，并附上可选的验证码区域截图
- [x] 2.3 避免在未检测到验证码时长时间傻等；若超时仍停留在登录页且无验证码元素，按现有「登录失败」逻辑处理

## 3. 各平台登录组件与 OTP/验证码统一

- [x] 3.1 TikTok/Shopee 等已支持 OTP 的登录组件：统一从 config（或任务恢复时的上下文）读取 OTP/验证码，与 executor 注入的 key 一致（如 config.params['otp'] 或 config['captcha_code']）— TikTok 已改为优先 config.params.otp；妙手已支持 config.params.captcha_code/otp
- [x] 3.2 为「图形验证码」增加与 OTP 同路径的「从 config 读取 → 填入 → 继续」逻辑，便于前端/API 统一「提交验证码」后写入同一上下文— 妙手登录已实现

## 4. 前端：验证码输入与回传（轮询为主）

- [x] 4.1 主路径：用户通过轮询任务列表/详情发现任务为 paused；在采集任务页该任务行点击「继续」，打开验证码弹窗（从任务接口取 **verification_screenshot** 展示验证码截图，若无则兼容 error_screenshot_path；任务详情/列表接口须返回 verification_type、verification_screenshot）；支持 OTP 与图形验证码同一弹窗，按 verification_type 区分文案— `CollectionTasks.vue` 已对接 verification_type、getTaskScreenshotUrl、弹窗文案
- [x] 4.2 用户输入验证码并提交后，调用后端「提交验证码/恢复任务」API（请求体含 captcha_code 或 otp），后端将验证码写入约定存储（如 Redis）；**正在等待中的执行器**在同一 page 上读取并填入、点击提交后继续（同一进程、同一页面内恢复，非重新启动任务）— `resumeTask(taskId, { captcha_code }|{ otp })` 已按 verification_type 区分
- [x] 4.3 WebSocket 为可选增强：若已建立任务 WebSocket，收到 verification_required 时可自动弹出同一验证码弹窗；不依赖此路径，系统须在仅轮询前提下完成「发现暂停 → 展示截图 → 回传 → 恢复」— 轮询路径已满足；WebSocket onVerification 已更新为使用 getTaskScreenshotUrl 与 verification_type

## 5. 可选：第三方打码服务

- [ ] 5.1 若产品决定接入 2Captcha 等：新增配置项（如 ENABLE_CAPTCHA_SOLVER、CAPTCHA_API_KEY）、适配模块（如 captcha_solver.py）在检测到图形验证码时截取图片并调用 API，轮询结果后填入
- [ ] 5.2 合规与文档：在配置或文档中说明打码服务的使用场景、数据合规与开关；默认关闭，人工回填优先

## 6. 验收与文档

- [ ] 6.1 **人工验收**：妙手登录页出现图形验证码时，任务能暂停并展示截图与输入框，用户输入正确验证码后任务恢复并完成登录（需人工在有验证码环境下验证）— 见下方《人工验收清单》
- [ ] 6.2 **人工验收**：TikTok/Shopee OTP 流程在新前端下可用，且与「提交验证码」API 行为一致— 见下方《人工验收清单》
- [x] 6.3 验收：等待验证码超时后任务置为失败或 verification_timeout；用户超时后再调用 Resume 提交验证码时，接口返回 4xx 并提示重新发起采集— 已通过 `tests/test_collection_resume_api.py` 自动化验证
- [x] 6.4 在数据采集或运维文档中补充「登录验证码处理」说明（类型、检测时机、人工回填、可选打码、有头/无头一致、按无头设计、超时与多实例/部署约束）— 见 `docs/guides/COLLECTION_LOGIN_VERIFICATION.md`
