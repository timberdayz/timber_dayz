# Operation Score Minimal Closure Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让“运营得分”具备最小可用闭环：可在目标管理页录入运营目标与实际值，参与绩效重算，并在绩效管理页显示结果。

**Architecture:** 保持现有后端绩效公式不变，只补齐前端 operation 目标的 `achieved_value` 录入/展示链路，并用一条可验证的 operation 目标完成端到端验证。后端仅补必要校验，避免大范围改动。

**Tech Stack:** Vue 3 + Element Plus + Pinia + Vite；FastAPI + SQLAlchemy Async + Pydantic；PostgreSQL

---

## File Structure

### Existing files to modify
- `F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/views/target/TargetManagement.vue`
  - 补 operation 表单的 `achieved_value` 输入、回显、重置、提交和列表展示
- `F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/target_management.py`
  - 为 operation 目标补最小必要校验，避免创建出无法计算的配置
- `F:/Vscode/python_programme/AI_code/xihong_erp/backend/tests/test_target_management_extended_fields.py`
  - 补充 `achieved_value` 在接口层的回归测试
- `F:/Vscode/python_programme/AI_code/xihong_erp/backend/tests/test_add_performance_income_acceptance.py`
  - 补一条 operation 目标参与绩效计算的验收测试

### Files to inspect while implementing
- `F:/Vscode/python_programme/AI_code/xihong_erp/backend/domains/business/routers/performance_management.py`
- `F:/Vscode/python_programme/AI_code/xihong_erp/backend/schemas/target.py`
- `F:/Vscode/python_programme/AI_code/xihong_erp/modules/core/db/schema.py`

---

### Task 1: 补齐前端 operation 目标的 achieved_value 录入链路

**Files:**
- Modify: `F:/Vscode/python_programme/AI_code/xihong_erp/frontend/src/views/target/TargetManagement.vue`

- [ ] **Step 1: 在 operation 表单中加入 failing expectation 注释和定位点**

检查并标记以下位置，准备统一修改：
- operation 表单区（约 623-657 行）
- form 默认值定义（约 1570-1586 行）
- reset/open edit 逻辑（约 1304-1318, 2085-2099, 2123-2137 行）
- submit payload（约 2408-2428 行）
- operation 列表列定义（约 474-483 行）

Run: 无
Expected: 能明确所有 `achieved_value` 应补的位置

- [ ] **Step 2: 在 form 默认值中新增 `achieved_value`**

示例：
```ts
achieved_value: 0,
```

需要同步修改：
- reactive form 初始定义
- resetForm / openCreate / openEdit 前的默认清空逻辑

- [ ] **Step 3: 在 operation 表单新增“实际值”输入项**

在 `target_type === 'operation'` 区域，新增：
```vue
<el-form-item label="实际值" prop="achieved_value">
  <el-input-number v-model="form.achieved_value" :min="0" :precision="2" class="erp-w-full" />
</el-form-item>
```

要求：
- 放在“目标值”后更直观
- 不改变现有 `manual_score` / `penalty` 逻辑

- [ ] **Step 4: 在编辑回显和重置逻辑中接入 `achieved_value`**

示例：
```ts
form.achieved_value = row.achieved_value || 0
```

同时在 reset/openCreate 中重置：
```ts
form.achieved_value = 0
```

- [ ] **Step 5: 在 payload 中提交 `achieved_value`**

在 submit payload 中新增：
```ts
achieved_value: form.metric_code ? Number(form.achieved_value) || 0 : undefined,
```

要求：
- 与 `target_value` 保持相同风格
- 不影响 shop/product/campaign 类型提交

- [ ] **Step 6: 在 operation 列表增加 `achieved_value` 展示列**

示例：
```vue
<el-table-column prop="achieved_value" label="实际值" width="120" align="right" />
```

要求：
- 放在“目标值”后
- 与现有列表视觉风格一致

- [ ] **Step 7: 本地静态检查并人工自查**

Run:
```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp
rg -n "achieved_value" frontend/src/views/target/TargetManagement.vue
```

Expected:
- 表单、默认值、回显、payload、列表列都能搜到 `achieved_value`

- [ ] **Step 8: Commit**

```bash
git add frontend/src/views/target/TargetManagement.vue
git commit -m "feat: add achieved value input for operation targets"
```

---

### Task 2: 为 operation 目标补最小后端校验

**Files:**
- Modify: `F:/Vscode/python_programme/AI_code/xihong_erp/backend/routers/target_management.py`
- Inspect: `F:/Vscode/python_programme/AI_code/xihong_erp/backend/schemas/target.py`

- [ ] **Step 1: 写出期望的校验规则**

operation 目标至少应满足：
- `metric_code` 非空
- `target_value` 非空
- `max_score` 非空
- 若不是 `manual_score`，建议 `achieved_value` 非空

注：这里建议先做“最小必需校验”，避免过严影响现有使用。

- [ ] **Step 2: 在 create/update 入口增加 operation 校验分支**

建议在保存前统一校验：
```python
if request.target_type == "operation":
    ...
```

推荐策略：
- 缺 `metric_code` / `target_value` / `max_score` -> 400
- 非 manual 模式且 `achieved_value is None` -> 400

- [ ] **Step 3: 错误信息使用仓库既有 error_response 风格**

要求：
- 不抛裸异常
- 使用仓库统一错误结构
- 错误描述明确指出 operation 目标缺少哪个字段

- [ ] **Step 4: Run targeted grep/self-review**

Run:
```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp
rg -n "target_type == \"operation\"|achieved_value|max_score|metric_code" backend/routers/target_management.py
```

Expected:
- create/update 两个路径都能看到 operation 校验

- [ ] **Step 5: Commit**

```bash
git add backend/routers/target_management.py
git commit -m "feat: validate operation target required fields"
```

---

### Task 3: 补接口层回归测试

**Files:**
- Modify: `F:/Vscode/python_programme/AI_code/xihong_erp/backend/tests/test_target_management_extended_fields.py`

- [ ] **Step 1: 写 failing test - 创建 operation 目标时保存 achieved_value**

示例测试目标：
```python
def test_create_operation_target_persists_achieved_value(...):
    ...
    assert data["achieved_value"] == 85.0
```

- [ ] **Step 2: 跑单测确认失败**

Run:
```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp
pytest backend/tests/test_target_management_extended_fields.py -q
```

Expected:
- 新增测试先失败

- [ ] **Step 3: 以最小修改让测试通过**

如果前两任务已完成，这里应主要是对测试夹具/断言做适配，而非继续扩展实现。

- [ ] **Step 4: 再跑单测确认通过**

Run:
```powershell
pytest backend/tests/test_target_management_extended_fields.py -q
```

Expected:
- 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_target_management_extended_fields.py
git commit -m "test: cover achieved value for operation targets"
```

---

### Task 4: 补绩效计算验收测试

**Files:**
- Modify: `F:/Vscode/python_programme/AI_code/xihong_erp/backend/tests/test_add_performance_income_acceptance.py`
- Inspect: `F:/Vscode/python_programme/AI_code/xihong_erp/backend/domains/business/routers/performance_management.py`

- [ ] **Step 1: 写 failing test - operation 目标参与店铺绩效计算**

优先用两种轻量案例之一：
1. `higher_better`
   - `target_value=100`
   - `achieved_value=85`
   - `max_score=20`
   - 期望 `operation_score=17`
2. `manual_score`
   - `manual_score_value=18`
   - `max_score=20`
   - 期望 `operation_score=18`

- [ ] **Step 2: 跑该测试确认失败**

Run:
```powershell
cd F:\Vscode\python_programme\AI_code\xihong_erp
pytest backend/tests/test_add_performance_income_acceptance.py -q
```

Expected:
- 新增场景失败

- [ ] **Step 3: 校正实现或测试数据夹具**

要求：
- 优先修测试夹具和目标构造
- 不要改动现有绩效公式，除非发现真实 bug

- [ ] **Step 4: 再跑该测试确认通过**

Run:
```powershell
pytest backend/tests/test_add_performance_income_acceptance.py -q
```

Expected:
- 新场景 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_add_performance_income_acceptance.py
git commit -m "test: verify operation score enters performance calculation"
```

---

### Task 5: 手工验收当前库的最小闭环

**Files:**
- Use app + current database
- Inspect result via API and DB

- [ ] **Step 1: 创建一条 operation 目标**

推荐数据：
```text
target_type = operation
metric_code = exam_score
metric_direction = higher_better
target_value = 100
achieved_value = 85
max_score = 20
period_start = 2026-04-01
period_end = 2026-04-30
```

- [ ] **Step 2: 执行绩效重算**

Run:
```powershell
# 方式一：从页面点击“重新计算”
# 方式二：调用接口 POST /performance/scores/calculate?period=2026-04
```

Expected:
- 本月店铺绩效重算成功

- [ ] **Step 3: 检查 operation_score 是否落表**

SQL:
```sql
select platform_code, shop_id, period, operation_score, score_details
from c_class.performance_scores
where period = '2026-04'
order by updated_at desc
limit 20;
```

Expected:
- `operation_score` 不再恒为 0
- `score_details.operation.status = calculated`

- [ ] **Step 4: 检查绩效页是否显示运营得分**

Expected:
- “运营得分”列出现数值而非 `—`
- 若毛利/重点产品仍未补齐，则总分可能仍不是完整展示；这属于后续链路问题，不影响本任务验收

- [ ] **Step 5: 记录验收结果到文档/进度文件**

记录：
- 使用了哪条 operation 目标
- 实际算出的 operation_score
- 绩效页展示情况
- 还阻塞总分 complete 的其他维度缺口

---

## Risks / Notes

- 当前 `PerformanceManagement` 页面会在 `summary.status != complete` 时隐藏总分/排名/系数，因此本任务完成后，仍可能只看到运营得分恢复，而总分继续为 `—`。
- 若业务希望后续自动取数，建议另开二期计划，不要混入本次最小闭环。
- 若 operation 目标需要按店铺差异化考核，后续应明确是单条全局 operation 目标，还是支持按店铺拆分/按店铺时间拆分。

## Definition of Done

- 目标管理页可创建/编辑带 `achieved_value` 的 operation 目标
- 后端会校验 operation 目标的关键字段
- operation 目标可参与绩效重算，`operation_score` 有数值
- 前端目标管理页与绩效页可看到运营得分相关结果

