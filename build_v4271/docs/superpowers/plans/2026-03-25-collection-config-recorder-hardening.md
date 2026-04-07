# Collection Config And Recorder Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正采集配置、子域调度、账号能力适配、录制到正式运行链路中的关键衔接问题，使配置行为和正式采集行为一致、可预测、可验证。

**Architecture:** 保持现有 FastAPI + Vue 3 + Playwright 组件运行架构不变，只修正配置层、调度层、运行时参数层和组件版本治理层的契约不一致。优先做“行为收口”而不是新建并行机制，避免继续放大 `sub_domains`、日期参数和稳定版治理的分叉。

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, Vue 3, Element Plus, Playwright, pytest

---

### Task 1: 统一账号能力适配规则

**Files:**
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/services/collection_scheduler.py`
- Modify: `backend/routers/collection_config.py`
- Modify: `backend/schemas/collection.py`
- Test: `backend/tests/test_collection_account_capability_alignment.py`
- Test: `backend/tests/test_collection_scheduler_capability_filter.py`

- [ ] **Step 1: 写失败测试，锁定“手动任务与定时任务能力过滤不一致”**

```python
async def test_scheduler_filters_domains_by_account_capabilities():
    ...
    assert created_task.data_domains == ["orders"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_collection_account_capability_alignment.py backend/tests/test_collection_scheduler_capability_filter.py -q`
Expected: FAIL，定时调度仍直接使用原始 `config.data_domains`

- [ ] **Step 3: 在调度器复用 `TaskService.filter_domains_by_account_capability()`**

```python
filtered_domains, unsupported = task_service.filter_domains_by_account_capability(
    account_info, config.data_domains
)
if not filtered_domains:
    continue
```

- [ ] **Step 4: 补齐配置页账号返回字段，至少暴露 capability/shop_type 所需信息**

```python
CollectionAccountResponse(..., shop_type=..., capabilities=...)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest backend/tests/test_collection_account_capability_alignment.py backend/tests/test_collection_scheduler_capability_filter.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routers/collection_tasks.py backend/services/collection_scheduler.py backend/routers/collection_config.py backend/schemas/collection.py backend/tests/test_collection_account_capability_alignment.py backend/tests/test_collection_scheduler_capability_filter.py
git commit -m "fix: align collection capability filtering across manual and scheduled tasks"
```

### Task 2: 收口定时配置，支持多时间点且避免单选 UI 误导

**Files:**
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `frontend/src/api/collection.js`
- Modify: `backend/routers/collection_schedule.py`
- Test: `backend/tests/test_collection_schedule_contract.py`
- Test: `frontend/src/views/collection/CollectionConfig.vue` (manual QA notes in plan execution)

- [ ] **Step 1: 写失败测试，锁定多时间点 Cron 的接口契约**

```python
async def test_schedule_update_accepts_multi_hour_cron():
    ...
    assert response["cron"] == "0 6,12,18,22 * * *"
```

- [ ] **Step 2: 运行测试确认当前后端契约可承载**

Run: `pytest backend/tests/test_collection_schedule_contract.py -q`
Expected: PASS 或最小改动后 PASS；若失败则先修后端

- [ ] **Step 3: 调整前端配置 UI，把“单个时间”改为“执行频率/Cron 模式”**

```vue
<el-select v-model="form.schedule_cron">
  <el-option label="每天 4 次" value="0 6,12,18,22 * * *" />
</el-select>
```

- [ ] **Step 4: 保留简单预设，不新增复杂 Cron 编辑器**

```text
仅提供仓库已经验证过的 preset，避免先引入高自由度输入
```

- [ ] **Step 5: 手工验证配置页创建/编辑/查看时多时间点表达正确**

Run: 前端本地页面验收
Expected: UI 不再暗示“只能单时点”

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/collection/CollectionConfig.vue frontend/src/api/collection.js backend/routers/collection_schedule.py backend/tests/test_collection_schedule_contract.py
git commit -m "fix: expose multi-time collection schedule presets"
```

### Task 3: 将子数据域改为“按数据域绑定”的可扩展注册机制

**Files:**
- Modify: `backend/services/component_name_utils.py`
- Modify: `backend/schemas/collection.py`
- Modify: `backend/services/component_runtime_resolver.py`
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `backend/services/collection_scheduler.py`
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `frontend/src/api/collection.js`
- Test: `backend/tests/test_collection_domain_subtype_scope.py`
- Test: `backend/tests/test_component_runtime_resolver_domain_subtype_scope.py`

- [ ] **Step 1: 写失败测试，锁定“平铺 `sub_domains` 无法表达多数据域子类型”的问题**

```python
def test_domain_subtypes_are_scoped_per_data_domain():
    ...
    assert resolved_keys == ["orders", "services:agent", "services:ai_assistant", "products:basic"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_collection_domain_subtype_scope.py backend/tests/test_component_runtime_resolver_domain_subtype_scope.py -q`
Expected: FAIL，当前平铺数组无法表达域级绑定，运行时仍会错误展开

- [ ] **Step 3: 引入数据域子类型 SSOT 注册表，不再把 `services` 特判写死**

```python
DATA_DOMAIN_SUB_TYPES = {
    "services": ["agent", "ai_assistant"],
}
```

- [ ] **Step 4: 将配置模型从平铺 `sub_domains` 收口为按域绑定的结构**

```python
domain_subtypes = {
    "services": ["agent", "ai_assistant"],
}
```

- [ ] **Step 5: 在 resolver、scheduler、executor 中统一按 `domain -> subtypes` 展开**

```python
subtype_list = domain_subtypes.get(domain) or [None]
```

- [ ] **Step 6: 前端配置页按注册表动态渲染子类型区域，只对选中的有子类型数据域展示**

```vue
<section v-for="domain in selectedSubtypeDomains" :key="domain">
```

- [ ] **Step 7: 运行测试确认通过**

Run: `pytest backend/tests/test_collection_domain_subtype_scope.py backend/tests/test_component_runtime_resolver_domain_subtype_scope.py -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/services/component_name_utils.py backend/schemas/collection.py backend/services/component_runtime_resolver.py modules/apps/collection_center/executor_v2.py backend/services/collection_scheduler.py frontend/src/views/collection/CollectionConfig.vue frontend/src/api/collection.js backend/tests/test_collection_domain_subtype_scope.py backend/tests/test_component_runtime_resolver_domain_subtype_scope.py
git commit -m "refactor: model collection subtypes per data domain"
```

### Task 4: 修正配置页“执行配置”与任务创建参数不一致

**Files:**
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `frontend/src/api/collection.js`
- Test: `backend/tests/test_collection_config_run_payload.py`

- [ ] **Step 1: 写失败测试，锁定配置页执行时丢失域级子类型信息**

```python
def test_run_config_payload_uses_domain_subtypes_mapping():
    ...
    assert payload["domain_subtypes"] == {"services": ["agent", "ai_assistant"]}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_collection_config_run_payload.py -q`
Expected: FAIL，当前页面仍传错误字段或丢失域级子类型映射

- [ ] **Step 3: 修正前端执行配置 payload**

```javascript
domain_subtypes: row.domain_subtypes || {}
```

- [ ] **Step 4: 顺带修正日期字段命名，统一传 `start_date/end_date`**

```javascript
date_range: { start_date: ..., end_date: ... }
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest backend/tests/test_collection_config_run_payload.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/collection/CollectionConfig.vue frontend/src/api/collection.js backend/tests/test_collection_config_run_payload.py
git commit -m "fix: align config-run payload with task creation contract"
```

### Task 5: 统一日期契约，保持“快捷日期预设优先、时间范围留扩展位”

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/services/collection_scheduler.py`
- Modify: `frontend/src/views/collection/CollectionConfig.vue`
- Modify: `frontend/src/views/collection/CollectionTasks.vue`
- Test: `backend/tests/test_collection_date_range_contract.py`

- [ ] **Step 1: 写失败测试，锁定预设日期与运行时键名不一致**

```python
def test_executor_accepts_preset_resolved_date_range_contract():
    ...
    assert params["params"]["date_from"] == "2026-03-01"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest backend/tests/test_collection_date_range_contract.py -q`
Expected: FAIL，执行器主路径仍读 `start/end`

- [ ] **Step 3: 在执行器统一兼容读取，但以 `start_date/end_date` 为正式主契约**

```python
date_from = date_range.get("start_date") or date_range.get("start") or date_range.get("date_from")
date_to = date_range.get("end_date") or date_range.get("end") or date_range.get("date_to")
```

- [ ] **Step 4: 前端维持今天/昨天/最近7天/最近28或30天为主入口，不新增新的日期能力**

```text
保留时间范围 schema 字段作为未来扩展位，但当前 UI 主流程只走 preset
```

- [ ] **Step 5: 运行测试确认通过**

Run: `pytest backend/tests/test_collection_date_range_contract.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add modules/apps/collection_center/executor_v2.py backend/routers/collection_tasks.py backend/services/collection_scheduler.py frontend/src/views/collection/CollectionConfig.vue frontend/src/views/collection/CollectionTasks.vue backend/tests/test_collection_date_range_contract.py
git commit -m "fix: normalize collection preset date range contract"
```

### Task 6: 收紧录制到 stable 运行的治理闭环

**Files:**
- Modify: `backend/routers/component_recorder.py`
- Modify: `backend/routers/component_versions.py`
- Modify: `frontend/src/views/ComponentRecorder.vue`
- Modify: `frontend/src/views/ComponentVersions.vue`
- Test: `backend/tests/test_component_recorder_stable_handoff.py`
- Test: `backend/tests/test_component_versions_promote_route.py`

- [ ] **Step 1: 写失败测试，锁定录制后必须经过测试/提稳才能进入正式采集**

```python
async def test_runtime_manifest_resolution_blocks_draft_component():
    ...
    with pytest.raises(NoStableComponentVersionError):
        await resolver.resolve_task_manifests(...)
```

- [ ] **Step 2: 运行测试确认现有阻断逻辑仍成立**

Run: `pytest backend/tests/test_component_recorder_stable_handoff.py backend/tests/test_component_versions_promote_route.py -q`
Expected: PASS 或补齐后 PASS

- [ ] **Step 3: 在录制页明确展示“草稿 -> 测试 -> stable -> 正式采集”的闭环提示**

```text
录制保存后不能直接用于正式采集
```

- [ ] **Step 4: 在版本页强化 promote 操作入口与说明**

```text
只有 stable 会进入正式运行和定时调度
```

- [ ] **Step 5: 手工验证录制后的用户路径**

Run:
1. 录制组件
2. 保存草稿
3. 测试
4. Promote stable
Expected: 用户路径清晰，无“录完即可投产”的误导

- [ ] **Step 6: Commit**

```bash
git add backend/routers/component_recorder.py backend/routers/component_versions.py frontend/src/views/ComponentRecorder.vue frontend/src/views/ComponentVersions.vue backend/tests/test_component_recorder_stable_handoff.py backend/tests/test_component_versions_promote_route.py
git commit -m "fix: clarify draft-to-stable collection component handoff"
```

### Task 7: 最终验证

**Files:**
- Test: `backend/tests/test_collection_*`
- Test: `backend/tests/test_component_*`
- Test: `backend/tests/test_transition_gates.py`
- Test: `backend/tests/test_runtime_gate_contract.py`

- [ ] **Step 1: 运行采集相关后端测试**

Run: `pytest backend/tests/test_collection_* backend/tests/test_component_* backend/tests/test_transition_gates.py backend/tests/test_runtime_gate_contract.py -q`
Expected: PASS

- [ ] **Step 2: 做前端人工验收**

Run:
1. 打开 `/collection-config`
2. 创建 services 配置
3. 创建多时间点定时配置
4. 从配置页执行
5. 打开 `/component-recorder`
Expected: 子域、定时、录制提示都与后端行为一致

- [ ] **Step 3: 记录验证结果**

```text
写入 progress.md / findings.md
```

- [ ] **Step 4: Commit**

```bash
git add progress.md findings.md
git commit -m "test: verify collection config and recorder hardening"
```

Plan complete and saved to `docs/superpowers/plans/2026-03-25-collection-config-recorder-hardening.md`. Ready to execute?
