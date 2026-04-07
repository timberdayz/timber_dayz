# Verification Final Acceptance Checklist

最后更新：2026-03-27

## 目标

用统一口径验收以下三条链路的验证码暂停、回填、继续能力：

1. Recorder
2. Component Test
3. Collection Task

验收时只关注真实用户路径，不讨论实现细节。

## 通用通过标准

以下 7 条适用于三条链路：

1. 遇到验证码时，页面必须出现共享验证码弹窗。
2. 图形验证码必须能直接看到截图；OTP 必须显示无截图输入模式。
3. 输入验证码后，页面必须出现“系统正在恢复执行”提示。
4. 提交失败时，弹窗内必须显示明确错误，不允许静默失败。
5. 截图加载失败时，弹窗内必须出现兜底提示，不允许空白块。
6. 验证超时后，页面必须给出超时提示。
7. 恢复后流程必须继续原上下文，而不是重新打开全新流程。

---

## 一、Recorder 链验收

页面：
- `#/component-recorder`

推荐场景：
- `miaoshou / export`

操作步骤：
1. 进入录制页。
2. 选择平台、组件类型、账号。
3. 点击开始录制。
4. 等待自动登录进入图形验证码或 OTP。
5. 在弹窗中输入验证码并提交。
6. 观察是否继续进入正式录制。
7. 停止录制，确认录制结果仍可正常产出。

必须通过的检查点：
1. 录制开始后先进入 `login_checking`，而不是直接打开 Inspector。
2. 验证码出现时弹出共享验证码弹窗。
3. 图形验证码截图能显示，或截图失败时显示兜底提示。
4. 提交后出现“系统正在恢复执行”提示。
5. 恢复成功后进入 `inspector_recording`。
6. 若回填错误，弹窗内出现错误提示，不应直接消失。
7. 停止录制后不出现 trace/steps 回退错误。

重点观察字段：
- `state`
- `verification_type`
- `verification_message`
- `verification_expires_at`

---

## 二、Component Test 链验收

页面：
- `#/component-versions`

推荐场景：
- `miaoshou/login`
- `miaoshou/orders_export` 或 `miaoshou/export`

操作步骤：
1. 打开组件版本管理页。
2. 选中一个需要验证码参与的组件版本。
3. 点击“测试组件”。
4. 等待自动登录进入验证码阶段。
5. 在共享验证码弹窗中输入验证码并提交。
6. 观察测试是否继续执行并最终结束。

必须通过的检查点：
1. 测试页不再出现旧的内嵌验证码卡片。
2. 验证码出现时弹出共享验证码弹窗。
3. 弹窗内显示 `verification_message` 和 `verification_expires_at`。
4. 提交后出现“系统正在恢复执行”提示。
5. 测试状态从 `verification_required` 推进到恢复中的后续状态。
6. 恢复成功后继续原测试，而不是要求重新发起测试。
7. 测试结束后，成功/失败提示仍然正常。

重点观察字段：
- `status`
- `verification_id`
- `verification_message`
- `verification_expires_at`
- `verification_attempt_count`

---

## 三、Collection Task 链验收

页面：
- `#/collection-tasks`

推荐场景：
- 单账号任务先验收
- 多账号暂停项再验收

操作步骤：
1. 创建一个真实采集任务。
2. 等待任务执行到验证码阶段。
3. 观察任务是否进入 `paused`。
4. 观察页面顶部是否出现“待回填验证码”列表。
5. 点击“立即回填”。
6. 在共享验证码弹窗中提交验证码。
7. 观察任务是否推进到 `verification_submitted` 并继续执行。

必须通过的检查点：
1. 暂停任务会出现在“待回填验证码”列表。
2. 待回填项至少按 `task_id + account` 区分。
3. 点击“立即回填”后弹出共享验证码弹窗。
4. 提交后提示“系统正在恢复执行”。
5. 任务状态推进到 `verification_submitted`。
6. 错误回填时，弹窗内有错误提示。
7. 多个暂停任务同时存在时，不会混成一条。

重点观察字段：
- `status`
- `verification_type`
- `verification_id`
- `verification_message`
- `verification_attempt_count`

---

## 四、失败分类记录

验收过程中如果失败，统一按以下分类记录：

1. `popup_missing`
页面应弹框但没有弹。

2. `screenshot_missing`
应显示图形验证码截图，但没有截图且没有兜底提示。

3. `resume_state_wrong`
提交后状态没有进入恢复中或 `verification_submitted`。

4. `context_restart`
提交后不是继续原流程，而是重开了新流程。

5. `error_not_visible`
提交失败后没有明确错误提示。

6. `multi_item_collision`
多账号或多任务待处理项混淆。

---

## 五、验收结论模板

每条链路验收结束后，按下面格式记录：

```text
链路：
结果：通过 / 失败
失败分类：
现象：
复现步骤：
截图/日志位置：
```

---

## 建议执行顺序

1. Recorder
2. Component Test
3. Collection Task（单账号）
4. Collection Task（多暂停项）

先把前三项跑通，再看是否还需要第二轮小修。
