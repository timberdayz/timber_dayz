# Tasks: 网页登录验证码统一优化

## 1. 执行器与验证码契约

- [ ] 1.1 确认 executor_v2 中 VerificationRequired、verification_required、verification_type、screenshot_path 已支持「任务 paused + 前端回传」流程；若 verification_type 未区分 OTP 与图形验证码，则扩展为支持 `graphical_captcha`（及既有 OTP 类型）
- [ ] 1.2 约定恢复任务时验证码注入方式：任务恢复或「提交验证码」API 将用户输入的验证码写入任务/会话上下文（如 config['captcha_code'] 或 config['otp']），执行器在重试或继续时将该值传入登录组件
- [ ] 1.3 文档化：在数据采集或执行器文档中说明「验证码类型、检测时机、人工回填与可选打码」的契约，并注明检测逻辑有头/无头一致、应对按无头生产设计（人工回填为主、打码可选）
- [ ] 1.4 后端持久化：将任务置为 paused 并抛出 VerificationRequired 时，将 verification_type、screenshot_path（或可访问截图 URL）写入任务记录（任务表或任务详情接口可返回），以便前端仅凭轮询任务列表/详情即可展示截图与输入框，不依赖 WebSocket

## 2. 妙手登录组件改造

- [ ] 2.1 在点击「立即登录」后，短轮询（如 2–3 秒内）检测是否仍停留在登录页且出现「请输入验证码」及图形验证码输入框/图片（通过 Playwright 选择器）
- [ ] 2.2 若检测到图形验证码：若 config 中已有 captcha_code（或 otp 用于图形码），则填入并再次点击登录，然后按现有逻辑判断是否跳转成功；否则抛出 VerificationRequired(verification_type="graphical_captcha", screenshot_path=...)，并附上可选的验证码区域截图
- [ ] 2.3 避免在未检测到验证码时长时间傻等；若超时仍停留在登录页且无验证码元素，按现有「登录失败」逻辑处理

## 3. 各平台登录组件与 OTP/验证码统一

- [ ] 3.1 TikTok/Shopee 等已支持 OTP 的登录组件：统一从 config（或任务恢复时的上下文）读取 OTP/验证码，与 executor 注入的 key 一致（如 config['otp'] 或 config['captcha_code']）
- [ ] 3.2 为「图形验证码」增加与 OTP 同路径的「从 config 读取 → 填入 → 继续」逻辑，便于前端/API 统一「提交验证码」后写入同一上下文

## 4. 前端：验证码输入与回传（轮询为主）

- [ ] 4.1 主路径：用户通过轮询任务列表/详情发现任务为 paused；在采集任务页该任务行点击「继续」，打开验证码弹窗（从任务接口取 screenshot_path 或 error_screenshot_path 展示截图、验证码输入框、提交按钮）；支持 OTP 与图形验证码同一弹窗，按 verification_type 区分文案
- [ ] 4.2 用户输入验证码并提交后，调用后端「提交验证码/恢复任务」API，将验证码与 task_id 传入；后端将验证码写入该任务上下文并触发恢复执行（或重试登录步骤）
- [ ] 4.3 WebSocket 为可选增强：若已建立任务 WebSocket，收到 verification_required 时可自动弹出同一验证码弹窗；不依赖此路径，系统须在仅轮询前提下完成「发现暂停 → 展示截图 → 回传 → 恢复」

## 5. 可选：第三方打码服务

- [ ] 5.1 若产品决定接入 2Captcha 等：新增配置项（如 ENABLE_CAPTCHA_SOLVER、CAPTCHA_API_KEY）、适配模块（如 captcha_solver.py）在检测到图形验证码时截取图片并调用 API，轮询结果后填入
- [ ] 5.2 合规与文档：在配置或文档中说明打码服务的使用场景、数据合规与开关；默认关闭，人工回填优先

## 6. 验收与文档

- [ ] 6.1 验收：妙手登录页出现图形验证码时，任务能暂停并展示截图与输入框，用户输入正确验证码后任务恢复并完成登录（需人工在有验证码环境下验证）
- [ ] 6.2 验收：TikTok/Shopee OTP 流程在新前端下可用，且与「提交验证码」API 行为一致
- [ ] 6.3 在数据采集或运维文档中补充「登录验证码处理」说明（类型、检测时机、人工回填、可选打码、有头/无头一致与按无头设计）
