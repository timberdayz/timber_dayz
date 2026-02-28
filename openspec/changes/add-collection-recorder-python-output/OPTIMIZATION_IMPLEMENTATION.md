# 采集录制与解析优化实施说明（已实施）

本文档记录已完成的优化项：消除步骤重复（方案 A + C）、生成器 selector 归一化、步骤间等待、Inspector 加固去重。

---

## 已实施的修改

### 1. Trace 解析器：方案 A + 方案 C

**文件**：`backend/utils/trace_parser.py`

- **方案 A**：仅处理 `event_type == 'action'` 或 `'action' in event`，已移除对 `before`/`after` 的处理，同一操作只产生一条 action。
- **方案 C**：新增 `DEDUP_TIME_WINDOW_MS = 500` 与 `_deduplicate_actions(actions)`，在 500ms 时间窗内对相同 `(action_type, selector, value)` 只保留第一条；在 `_extract_actions` 中 sort 后调用去重再返回。

### 2. 生成器：selector 归一化

**文件**：`backend/services/steps_to_python.py`

- 新增 `_selector_from_selectors(selectors)`：从 Inspector 的 `selectors` 列表（`[{type, value}, ...]`）按优先级 role > text > label > placeholder > css 推导出单个 selector 字符串。
- 在处理每条 step 时，若 `selector` 为空且 `step.get("selectors")` 非空，则 `selector = _selector_from_selectors(step["selectors"])`，使生成的 Python 包含真实 locator/expect/click/fill 代码。

### 3. 生成器：步骤间等待

**文件**：`backend/services/steps_to_python.py`

- 在每步代码输出后，若当前步为 `navigate` 或 `goto`，则插入 `await page.wait_for_load_state("domcontentloaded", timeout=10000)`，再进入下一步，减少导航未完成即执行下一步的偶发失败。

### 4. Inspector：加固去重

**文件**：`tools/launch_inspector_recorder.py`

- 在 `_handle_normal_event` 中，在原有「与上一步同 action+description 则合并/跳过」基础上，增加对最近 2～3 步的检查：若存在相同 `action` 且主 selector（`_get_primary_selector(selectors)`）相同，则对 fill 更新 value 并 return，对 click 直接 return，避免同一操作因事件多次触发产生多条步骤。

---

## 优化后效果

- **步骤重复**：Trace 解析不再因 before/after 重复计数；时间窗去重进一步合并残留重复；Inspector 事件层同 selector 同 action 在最近几步内合并/跳过。
- **生成代码可执行**：有 `selectors` 无 `selector` 的步骤能推导出 selector，生成 locator + expect + click/fill，测试组件可正常执行。
- **步骤衔接**：navigate/goto 后增加 wait_for_load_state，符合《采集脚本编写规范》的等待策略。

与提案及《采集脚本编写规范》的符合性见前文分析总结。
