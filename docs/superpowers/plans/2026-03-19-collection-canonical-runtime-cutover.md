# Collection Canonical Runtime Cutover Implementation Plan

Status: completed on 2026-03-20 and merged into `main`

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将正式采集运行路径收敛为唯一的 `stable -> file_path -> executor` 主路径，并切断旧模板/原始录制脚本进入正式采集的能力。

**Architecture:** 先新增一个正式运行解析层，将 `platform + component_type + data_domain + sub_domain` 解析成唯一的 stable 版本 manifest；再把手动任务、调度任务、顺序执行和并行执行统一切到 manifest 驱动；最后收缩适配器角色并修正文案，使录制保存只产生 `draft` 版本，正式运行只认 `stable`。本阶段不拆分 worker，不改数据库表结构，只重定义和强制执行现有版本字段语义。

**Tech Stack:** FastAPI, SQLAlchemy async, Playwright async, Vue 3, Element Plus, pytest

---

## File Structure

### New Files

- `backend/services/component_runtime_resolver.py`
  - 正式运行解析器
  - 负责基于 `ComponentVersion` 解析 stable 版本、校验 `file_path` 和构造 runtime manifest
- `tests/test_component_runtime_resolver.py`
  - 解析器单元测试
  - 覆盖无 stable、多 stable、路径缺失、正常解析等分支

### Modified Files

- `backend/routers/collection_tasks.py`
  - 手动任务 preflight 检查
  - 创建后台任务时传入 runtime manifest，而不是只传 data domain
- `backend/services/collection_scheduler.py`
  - 调度任务 preflight 检查
  - 缺 stable 时写日志并拒绝启动浏览器
- `modules/apps/collection_center/executor_v2.py`
  - 顺序执行与并行执行都改为消费 runtime manifest
  - 正式路径移除模块名兜底加载
- `modules/apps/collection_center/python_component_adapter.py`
  - 收缩为录制测试/验收/调试路径使用
  - 避免作为正式运行的最终组件选择器
- `backend/services/component_version_service.py`
  - 补充 stable-only 运行查询辅助方法
  - 将“正式可运行”语义固定到 stable
- `backend/routers/component_recorder.py`
  - 强化“保存即 draft”的接口语义与响应文案
- `frontend/src/views/ComponentRecorder.vue`
  - 强化“录制保存不等于正式发布”的文案
  - 保存后引导进入测试/验收/稳定版提升流程
- `frontend/src/views/ComponentVersions.vue`
  - 强化 stable-only 正式运行语义
  - 对非 stable 版本的操作提示更明确
- `modules/utils/collection_template_generator.py`
  - 标记为旧路径/调试用途，避免再被误解为正式运行生成器
- `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`
  - 补充“正式运行只认 stable file_path”的规则说明

### Existing Test Files To Extend

- `tests/test_executor_v2.py`
  - 执行器正式路径只消费 manifest 的回归测试
- `tests/test_collection_resume_api.py`
  - 确保验证码恢复路径不受 manifest 切换影响
- `tests/test_component_loader.py`
  - 验证 file_path 加载与组件类解析行为

---

### Task 1: Build The Stable Runtime Resolver

**Files:**
- Create: `backend/services/component_runtime_resolver.py`
- Create: `tests/test_component_runtime_resolver.py`
- Modify: `backend/services/component_version_service.py`

- [ ] **Step 1: Write failing resolver tests**

```python
def test_resolve_runtime_component_requires_stable_version():
    resolver = ComponentRuntimeResolver(db_session)
    with pytest.raises(NoStableComponentVersionError):
        resolver.resolve_export_component(
            platform="shopee",
            data_domain="orders",
            sub_domain=None,
        )


def test_resolve_runtime_component_rejects_multiple_stable_versions():
    create_component_version("shopee/orders_export", "1.0.0", is_stable=True)
    create_component_version("shopee/orders_export", "1.1.0", is_stable=True)
    resolver = ComponentRuntimeResolver(db_session)

    with pytest.raises(MultipleStableComponentVersionsError):
        resolver.resolve_export_component(
            platform="shopee",
            data_domain="orders",
            sub_domain=None,
        )
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_component_runtime_resolver.py -v`
Expected: FAIL because resolver module and error classes do not exist yet

- [ ] **Step 3: Implement the resolver and helper exceptions**

```python
@dataclass(frozen=True)
class RuntimeComponentManifest:
    component_name: str
    version: str
    file_path: str
    platform: str
    component_type: str
    data_domain: Optional[str] = None
    sub_domain: Optional[str] = None


class ComponentRuntimeResolver:
    def resolve_login_component(self, platform: str) -> RuntimeComponentManifest:
        ...

    def resolve_export_component(
        self, platform: str, data_domain: str, sub_domain: Optional[str]
    ) -> RuntimeComponentManifest:
        ...
```

- [ ] **Step 4: Add file existence and uniqueness validation**

```python
if len(stable_versions) > 1:
    raise MultipleStableComponentVersionsError(component_name)

if not stable_versions:
    raise NoStableComponentVersionError(component_name)

if not (project_root / version.file_path).exists():
    raise MissingStableComponentFileError(component_name, version.file_path)
```

- [ ] **Step 5: Add `ComponentVersionService` helpers for stable-only lookups**

```python
def get_all_stable_versions(self, component_name: str) -> List[ComponentVersion]:
    ...

def get_single_stable_version(self, component_name: str) -> Optional[ComponentVersion]:
    ...
```

- [ ] **Step 6: Run resolver tests to verify pass**

Run: `pytest tests/test_component_runtime_resolver.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/services/component_runtime_resolver.py backend/services/component_version_service.py tests/test_component_runtime_resolver.py
git commit -m "feat: add stable-only runtime resolver for collection components"
```

### Task 2: Preflight Manual And Scheduled Tasks

**Files:**
- Modify: `backend/routers/collection_tasks.py`
- Modify: `backend/services/collection_scheduler.py`
- Modify: `tests/test_component_runtime_resolver.py`

- [ ] **Step 1: Write failing preflight tests**

```python
async def test_create_task_rejects_when_export_component_has_no_stable(async_client):
    response = await async_client.post(
        "/api/collection/tasks",
        json={
            "platform": "shopee",
            "account_id": "acc-1",
            "data_domains": ["orders"],
            "granularity": "daily",
            "date_range": {"start": "2026-03-01", "end": "2026-03-02"},
        },
    )

    assert response.status_code == 400
    assert "stable" in response.json()["detail"].lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_component_runtime_resolver.py -k preflight -v`
Expected: FAIL because task creation does not preflight stable manifests yet

- [ ] **Step 3: Add manual-task preflight in `create_task`**

```python
resolver = ComponentRuntimeResolver.from_async_session(db)
runtime_manifests = await resolver.resolve_task_manifests(
    platform=request.platform,
    data_domains=filtered_domains,
    sub_domains=request.sub_domains,
)
```

- [ ] **Step 4: Persist runtime manifest references onto the task payload or background args**

```python
asyncio.create_task(
    _execute_collection_task_background(
        ...,
        runtime_manifests=runtime_manifests,
    )
)
```

- [ ] **Step 5: Add scheduler preflight before launching browser work**

```python
runtime_manifests = await resolver.resolve_task_manifests(
    platform=config.platform,
    data_domains=config.data_domains,
    sub_domains=config.sub_domains,
)
```

- [ ] **Step 6: Fail fast for missing stable versions and write explicit logs**

```python
task.status = "failed"
task.error_message = f"Stable component not ready: {exc.component_name}"
```

- [ ] **Step 7: Run preflight tests to verify pass**

Run: `pytest tests/test_component_runtime_resolver.py -k preflight -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/routers/collection_tasks.py backend/services/collection_scheduler.py tests/test_component_runtime_resolver.py
git commit -m "feat: add stable component preflight for collection task entrypoints"
```

### Task 3: Switch The Executor To Manifest-Driven Loading

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `tests/test_executor_v2.py`
- Modify: `tests/test_component_loader.py`

- [ ] **Step 1: Write failing executor tests for manifest-only runtime**

```python
async def test_execute_uses_manifest_file_path_for_login_and_export(monkeypatch):
    resolver_output = {
        "login": RuntimeComponentManifest(...),
        "exports": [RuntimeComponentManifest(component_name="shopee/orders_export", ...)],
    }
    executor = CollectionExecutorV2()
    result = await executor.execute(..., runtime_manifests=resolver_output)
    assert result.status in {"completed", "partial_success"}
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_executor_v2.py -k manifest -v`
Expected: FAIL because `execute()` and `execute_parallel_domains()` do not accept runtime manifests yet

- [ ] **Step 3: Add runtime manifest inputs to sequential and parallel executor paths**

```python
async def execute(..., runtime_manifests: Dict[str, Any], ...):
    ...

async def execute_parallel_domains(..., runtime_manifests: Dict[str, Any], ...):
    ...
```

- [ ] **Step 4: Load component classes by `file_path` for formal runtime**

```python
klass = self.component_loader.load_python_component_from_path(
    manifest.file_path,
    platform=manifest.platform,
    component_type=manifest.component_type,
)
```

- [ ] **Step 5: Remove formal runtime fallback to module-name export loading**

```python
if not manifest:
    raise StepExecutionError("runtime manifest missing for stable component execution")
```

- [ ] **Step 6: Ensure sequential and parallel export paths both reuse the same manifest objects**

```python
export_manifest = runtime_manifests["exports_by_domain"][full_domain_key]
```

- [ ] **Step 7: Keep captcha, session reuse, popup handling, and file processing unchanged**

```python
# No behavior change:
# - _wait_verification_and_continue
# - popup_handler.close_popups
# - _process_files
```

- [ ] **Step 8: Run executor and component-loader tests**

Run: `pytest tests/test_executor_v2.py tests/test_component_loader.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add modules/apps/collection_center/executor_v2.py tests/test_executor_v2.py tests/test_component_loader.py
git commit -m "feat: make collection executor consume stable runtime manifests"
```

### Task 4: Restrict The Adapter To Test And Debug Roles

**Files:**
- Modify: `modules/apps/collection_center/python_component_adapter.py`
- Modify: `modules/apps/collection_center/executor_v2.py`
- Test: `tests/test_executor_v2.py`

- [ ] **Step 1: Write a failing regression test that formal runtime no longer module-loads exports**

```python
async def test_formal_runtime_does_not_fallback_to_module_name_loading(monkeypatch):
    adapter = PythonComponentAdapter(platform="shopee", account={}, config={})
    with pytest.raises(RuntimeError):
        await formal_runtime_execute_without_manifest(...)
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `pytest tests/test_executor_v2.py -k fallback -v`
Expected: FAIL because formal runtime still has fallback behavior

- [ ] **Step 3: Split adapter responsibilities**

```python
class PythonComponentAdapter:
    # keep login/export module loading for recorder test and component test paths
    # do not let formal task execution rely on this path
```

- [ ] **Step 4: Add explicit comments and guardrails in adapter code**

```python
# NOTE:
# Formal collection runtime must resolve stable components by file_path before execution.
# This adapter remains for recorder test, component test, and debug flows.
```

- [ ] **Step 5: Run the focused fallback regression**

Run: `pytest tests/test_executor_v2.py -k fallback -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add modules/apps/collection_center/python_component_adapter.py modules/apps/collection_center/executor_v2.py tests/test_executor_v2.py
git commit -m "refactor: reserve adapter module loading for test and debug flows"
```

### Task 5: Make Recorder Save Draft-Only And Clarify Version Semantics

**Files:**
- Modify: `backend/routers/component_recorder.py`
- Modify: `frontend/src/views/ComponentRecorder.vue`
- Modify: `frontend/src/views/ComponentVersions.vue`
- Test: `backend/tests/test_component_recorder_lint.py`

- [ ] **Step 1: Write failing backend and UI-facing semantic checks**

```python
def test_save_component_creates_non_stable_version_by_default():
    ...
    assert version.is_stable is False
    assert "draft" in response["message"].lower()
```

- [ ] **Step 2: Run the backend recorder test**

Run: `pytest backend/tests/test_component_recorder_lint.py -k save_component -v`
Expected: FAIL because response semantics still imply generic save success, not explicit draft-only semantics

- [ ] **Step 3: Update recorder save response and comments**

```python
return {
    "success": True,
    "message": "组件已保存为草稿版本，请先测试并提升为稳定版后再用于正式采集",
    ...
}
```

- [ ] **Step 4: Update recorder page wording**

```vue
<p>录制保存后得到的是草稿版本，不会直接进入正式采集。</p>
```

- [ ] **Step 5: Update component versions page wording**

```vue
<p class="subtitle">只有稳定版本可用于正式采集和定时调度</p>
```

- [ ] **Step 6: Run recorder tests**

Run: `pytest backend/tests/test_component_recorder_lint.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/routers/component_recorder.py frontend/src/views/ComponentRecorder.vue frontend/src/views/ComponentVersions.vue backend/tests/test_component_recorder_lint.py
git commit -m "feat: mark recorder saves as draft-only and clarify stable runtime semantics"
```

### Task 6: Demote Legacy Script Paths To Debug Assets

**Files:**
- Modify: `modules/utils/collection_template_generator.py`
- Modify: `docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md`
- Modify: `docs/superpowers/specs/2026-03-19-collection-canonical-runtime-cutover-design.md`

- [ ] **Step 1: Add a failing documentation/test note checklist in the plan session log**

```text
Expected final state:
- template generator is documented as legacy/debug-only
- formal runtime docs point only to stable file_path execution
```

- [ ] **Step 2: Update the legacy generator docstring and runtime warnings**

```python
"""
Legacy debug-only generator.
Do not use for formal collection runtime assets.
"""
```

- [ ] **Step 3: Update the collection script guide**

```markdown
- 正式采集运行只认 `ComponentVersion` 当前 stable 的 `file_path`
- `temp/recordings/` 与原始回放脚本不得进入正式任务链路
```

- [ ] **Step 4: Re-read the design spec and ensure terminology matches implementation plan**

Run: `Get-Content docs\\superpowers\\specs\\2026-03-19-collection-canonical-runtime-cutover-design.md`
Expected: Terms align with `draft/candidate/stable` and `stable-only formal runtime`

- [ ] **Step 5: Commit**

```bash
git add modules/utils/collection_template_generator.py docs/guides/COLLECTION_SCRIPT_WRITING_GUIDE.md docs/superpowers/specs/2026-03-19-collection-canonical-runtime-cutover-design.md
git commit -m "docs: demote legacy collection script paths to debug-only assets"
```

### Task 7: Final Verification

**Files:**
- Modify: `docs/superpowers/plans/2026-03-19-collection-canonical-runtime-cutover.md`
- Test: `tests/test_component_runtime_resolver.py`
- Test: `tests/test_executor_v2.py`
- Test: `tests/test_component_loader.py`
- Test: `backend/tests/test_component_recorder_lint.py`

- [ ] **Step 1: Run focused backend tests**

Run: `pytest tests/test_component_runtime_resolver.py tests/test_executor_v2.py tests/test_component_loader.py backend/tests/test_component_recorder_lint.py -v`
Expected: PASS

- [ ] **Step 2: Run collection resume regression**

Run: `pytest tests/test_collection_resume_api.py -v`
Expected: PASS

- [ ] **Step 3: Verify no formal runtime path still falls back to module-name loading**

Run: `Get-ChildItem -Recurse -File | Select-String -Pattern '_load_component_class\\(\"export\"\\)|_load_component_class\\(\"login\"\\)' -Encoding utf8`
Expected: remaining hits are limited to recorder test/debug code, not formal runtime execution paths

- [ ] **Step 4: Verify docs and UI wording**

Run: `Get-Content frontend\\src\\views\\ComponentRecorder.vue -Encoding utf8 | Select-String -Pattern '草稿|稳定版|正式采集'`
Expected: wording clearly states recorder save is draft-only and formal runtime is stable-only

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-03-19-collection-canonical-runtime-cutover.md
git commit -m "chore: verify stable-only canonical collection runtime cutover"
```

---

## Notes For Execution

- 先做 `Task 1` 和 `Task 2`，不要先改执行器；否则入口和执行器会短暂失配。
- `Task 3` 完成前，不要切断旧路径；否则正式任务会无 manifest 可用。
- 如果发现 `sub_domain` 在并行路径中仍有额外隐式分支，不要临时打补丁，直接把它收进 manifest 映射里。
- 正式路径一律 fail fast；不要为“没有 stable 版本”增加回退逻辑。
- 本计划不包括 worker 拆分；不要在本分支顺手引入队列或进程架构调整。

## Verification Checklist

- [ ] 手动正式采集没有 stable 就直接失败
- [ ] 定时采集没有 stable 不启动浏览器
- [ ] 顺序执行和并行执行都只走 stable file_path
- [ ] 录制保存默认为 draft，不进入正式采集
- [ ] 旧模板生成器与原始回放脚本不再能进入正式运行链路
