# TikTok Edge Profile Semi-Automatic Collection Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 TikTok 正式采集新增“本机专用 Edge Profile + CDP 接管 + 人工验证暂停恢复”的半自动运行模式，同时保持现有 TikTok canonical 组件和其他平台运行方式不变。

**Architecture:** 在正式采集运行时新增 TikTok 专用 `edge_profile_attached` 策略，由单独的 Edge 附着层负责查找本机 Edge、启动带专用 profile 的浏览器、建立 CDP 连接并产出可复用的 page/context。执行器继续复用现有 TikTok login/export 组件，但当检测到登录失效或图形验证时，不再直接硬失败，而是进入可恢复的暂停状态，等待操作者在同一 Edge 窗口里完成处理后继续。

**Tech Stack:** Python, FastAPI backend, Playwright async/sync API, Windows Edge local runtime, pytest

---

## File Map

**Create:**
- `modules/apps/collection_center/edge_runtime.py`
- `backend/tests/test_edge_runtime.py`
- `backend/tests/test_tiktok_runtime_strategy.py`
- `backend/tests/test_tiktok_pause_resume_runtime.py`

**Modify:**
- `modules/apps/collection_center/runtime_session.py`
- `modules/apps/collection_center/executor_v2.py`
- `modules/apps/collection_center/browser_config_helper.py`
- `backend/routers/collection_tasks.py`
- `backend/tests/test_browser_config_helper.py`
- `backend/tests/test_collection_queue_runner.py`
- `backend/tests/test_component_tester_runtime_config.py`
- `docs/guides/COLLECTION_TEST_ENVIRONMENT_BASELINE.md`

**Reference:**
- `docs/superpowers/specs/2026-04-16-tiktok-edge-profile-semi-automatic-collection-design.md`
- `modules/utils/pwcli_native.py`
- `modules/platforms/tiktok/components/login.py`
- `modules/platforms/tiktok/components/products_export.py`
- `modules/platforms/tiktok/components/analytics_export.py`
- `modules/platforms/tiktok/components/services_agent_export.py`

## Design Rules

- TikTok 正式采集默认新增 `edge_profile_attached`，但只限 `platform == "tiktok"` 的正式运行路径。
- Shopee、Miaoshou 继续保持当前 Playwright 官方浏览器基线。
- 专用 Edge Profile 只能是本机本地配置，不得写死到仓库源码常量里。
- 不允许自动回退到用户日常个人 Edge Profile。
- TikTok 登录失效、图形验证、二次验证应进入“暂停恢复”而不是普通终态失败。
- 现有 TikTok canonical 组件只复用 page/context，不负责 Edge 启动和 CDP 附着。
- 保持导出成功门禁不变：
  - `file_path` 返回
  - 文件存在
  - 文件非空
- 文档必须明确 TikTok 是正式采集基线的例外，不得让“全仓统一使用 Playwright 官方浏览器”继续误导后续实现者。

## Task 1: Define TikTok Runtime Strategy Contract

**Files:**
- Modify: `modules/apps/collection_center/runtime_session.py`
- Modify: `modules/apps/collection_center/executor_v2.py`
- Test: `backend/tests/test_tiktok_runtime_strategy.py`

- [ ] **Step 1: Write the failing runtime-strategy tests**

```python
def test_choose_runtime_strategy_allows_tiktok_edge_profile_attached_by_default():
    decision = choose_runtime_strategy(
        platform="tiktok",
        session_owner_id="main-1",
        has_storage_state=True,
        has_persistent_profile=True,
        force_persistent_profile=False,
        execution_kind="formal_collection",
        component_type="export",
        parallel_mode=False,
    )
    assert decision.mode == "edge_profile_attached"


def test_choose_runtime_strategy_keeps_shopee_on_existing_flow():
    decision = choose_runtime_strategy(
        platform="shopee",
        session_owner_id="main-1",
        has_storage_state=True,
        has_persistent_profile=True,
        force_persistent_profile=False,
        execution_kind="formal_collection",
        component_type="export",
        parallel_mode=False,
    )
    assert decision.mode != "edge_profile_attached"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_tiktok_runtime_strategy.py -q`
Expected: FAIL because the runtime strategy layer does not know `edge_profile_attached`

- [ ] **Step 3: Implement the strategy contract**

Implementation requirements:
- extend the runtime strategy decision model to support `edge_profile_attached`
- make TikTok formal collection default to `edge_profile_attached`
- keep non-TikTok platforms on current strategy behavior
- keep explicit existing modes valid where already used by tests or tooling

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_tiktok_runtime_strategy.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/apps/collection_center/runtime_session.py modules/apps/collection_center/executor_v2.py backend/tests/test_tiktok_runtime_strategy.py
git commit -m "feat: add tiktok edge-profile runtime strategy"
```

## Task 2: Build Local Edge Attachment Provider

**Files:**
- Create: `modules/apps/collection_center/edge_runtime.py`
- Test: `backend/tests/test_edge_runtime.py`

- [ ] **Step 1: Write the failing attachment-provider tests**

```python
def test_edge_runtime_build_launch_command_uses_edge_and_profile_dir(tmp_path):
    command = build_edge_launch_command(
        executable_path="C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        port=9222,
        profile_dir=tmp_path / "tiktok-main",
        headed=True,
    )
    assert "--remote-debugging-port=9222" in command
    assert any(str(tmp_path / "tiktok-main") in part for part in command)


def test_edge_runtime_metadata_marks_browser_type_as_edge():
    metadata = build_edge_runtime_metadata(
        port=9222,
        pid=123,
        executable_path="C:/msedge.exe",
        profile_dir="C:/profiles/tiktok-main",
        headed=True,
    )
    assert metadata["browser_type"] == "edge"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_edge_runtime.py -q`
Expected: FAIL because `edge_runtime.py` does not exist yet

- [ ] **Step 3: Implement the Edge attachment provider**

Implementation requirements:
- resolve local Edge executable path on Windows
- build Edge launch command with:
  - `--remote-debugging-port=<port>`
  - `--user-data-dir=<profile_dir>`
  - `--no-first-run`
  - `--no-default-browser-check`
- allow headed default for TikTok formal collection
- provide helpers for:
  - executable resolution
  - launch command creation
  - process startup
  - debug-port readiness check
  - CDP attach
  - runtime metadata construction
- do not mix TikTok business logic into this file

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_edge_runtime.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/apps/collection_center/edge_runtime.py backend/tests/test_edge_runtime.py
git commit -m "feat: add local edge runtime provider for tiktok"
```

## Task 3: Open Runtime Bundles From Attached Edge

**Files:**
- Modify: `modules/apps/collection_center/runtime_session.py`
- Modify: `modules/apps/collection_center/executor_v2.py`
- Test: `backend/tests/test_tiktok_runtime_strategy.py`
- Test: `backend/tests/test_component_tester_runtime_config.py`

- [ ] **Step 1: Add failing bundle-opening test**

Target behavior:
- when runtime mode is `edge_profile_attached`, the executor asks the Edge provider for an attached browser/context/page bundle
- runtime diagnostics include:
  - `runtime_session_mode == "edge_profile_attached"`
  - `session_source == "edge_profile_attached"`
  - local Edge executable path
  - dedicated profile path

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `python -m pytest backend/tests/test_tiktok_runtime_strategy.py backend/tests/test_component_tester_runtime_config.py -q`
Expected: FAIL because runtime bundles only support `storage_state_fanout` and `persistent_profile`

- [ ] **Step 3: Implement attached runtime bundle support**

Implementation requirements:
- add a runtime-session helper that opens bundles from attached Edge
- keep the returned object shape compatible with the executor:
  - `context`
  - `page`
  - `mode`
  - `reused_session`
  - `profile_path`
  - `context_options`
- annotate diagnostics with Edge-specific metadata
- avoid forcing `browser_type.launch()` for TikTok when attached Edge is selected

- [ ] **Step 4: Run targeted tests to verify pass**

Run: `python -m pytest backend/tests/test_tiktok_runtime_strategy.py backend/tests/test_component_tester_runtime_config.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/apps/collection_center/runtime_session.py modules/apps/collection_center/executor_v2.py backend/tests/test_tiktok_runtime_strategy.py backend/tests/test_component_tester_runtime_config.py
git commit -m "feat: open tiktok runtime bundles from attached edge"
```

## Task 4: Add Dedicated TikTok Edge Profile Resolution

**Files:**
- Modify: `modules/apps/collection_center/runtime_session.py`
- Modify: `backend/routers/collection_tasks.py`
- Test: `backend/tests/test_tiktok_runtime_strategy.py`
- Test: `backend/tests/test_collection_queue_runner.py`

- [ ] **Step 1: Write the failing configuration tests**

Target behavior:
- TikTok task runtime can resolve a machine-local dedicated Edge profile directory
- if the dedicated profile path is missing, the system returns a clear configuration error
- the runtime never silently points at the user's normal daily Edge profile

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest backend/tests/test_tiktok_runtime_strategy.py backend/tests/test_collection_queue_runner.py -q`
Expected: FAIL because there is no dedicated TikTok Edge profile contract yet

- [ ] **Step 3: Implement profile resolution**

Implementation requirements:
- introduce one local-config-driven resolver for TikTok Edge profile path
- keep the path machine-local and out of committed repo defaults
- surface clear error messages for:
  - missing Edge executable
  - missing dedicated profile path
  - inaccessible profile path
- expose enough details for task diagnostics and troubleshooting

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest backend/tests/test_tiktok_runtime_strategy.py backend/tests/test_collection_queue_runner.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/apps/collection_center/runtime_session.py backend/routers/collection_tasks.py backend/tests/test_tiktok_runtime_strategy.py backend/tests/test_collection_queue_runner.py
git commit -m "feat: resolve dedicated tiktok edge profile settings"
```

## Task 5: Convert Login/Verification Failure Into Pause-Resume Recovery

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `backend/routers/collection_tasks.py`
- Test: `backend/tests/test_tiktok_pause_resume_runtime.py`

- [ ] **Step 1: Write the failing pause-resume tests**

```python
@pytest.mark.asyncio
async def test_tiktok_login_required_enters_paused_recovery_state():
    result = await run_tiktok_formal_collection_with_login_gate_failure(...)
    assert result.status == "paused"
    assert result.error_message == "verification_or_login_required"


@pytest.mark.asyncio
async def test_tiktok_verification_pause_preserves_runtime_metadata():
    result = await run_tiktok_formal_collection_with_verification_required(...)
    assert result.details["runtime_session_mode"] == "edge_profile_attached"
    assert result.details["resume_supported"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest backend/tests/test_tiktok_pause_resume_runtime.py -q`
Expected: FAIL because TikTok login/verification still resolves to normal error/failure paths

- [ ] **Step 3: Implement pause-resume semantics**

Implementation requirements:
- detect TikTok-specific verification/login-required conditions during formal execution
- preserve the attached Edge window and context instead of closing them immediately
- return a paused task outcome with machine-actionable diagnostics
- expose resume eligibility and required operator action
- keep non-TikTok failure handling unchanged

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest backend/tests/test_tiktok_pause_resume_runtime.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/apps/collection_center/executor_v2.py backend/routers/collection_tasks.py backend/tests/test_tiktok_pause_resume_runtime.py
git commit -m "feat: pause tiktok tasks for manual verification recovery"
```

## Task 6: Resume TikTok Tasks From The Same Attached Session

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py`
- Modify: `backend/routers/collection_tasks.py`
- Test: `backend/tests/test_tiktok_pause_resume_runtime.py`

- [ ] **Step 1: Extend failing tests for same-session continuation**

Target behavior:
- resume continues from the same attached Edge runtime state
- executor does not unnecessarily rebuild a fresh Playwright browser
- resumed task can continue to existing TikTok login/export components

- [ ] **Step 2: Run tests to verify failure**

Run: `python -m pytest backend/tests/test_tiktok_pause_resume_runtime.py -q`
Expected: FAIL because paused TikTok tasks cannot yet continue through the same attached session

- [ ] **Step 3: Implement resume path**

Implementation requirements:
- persist enough runtime metadata to reconnect or continue the same attached Edge session
- keep resume flow focused on TikTok attached runtime only
- re-enter the executor with the preserved page/context contract
- avoid broad queue-runner rewrites unrelated to TikTok

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest backend/tests/test_tiktok_pause_resume_runtime.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/apps/collection_center/executor_v2.py backend/routers/collection_tasks.py backend/tests/test_tiktok_pause_resume_runtime.py
git commit -m "feat: resume paused tiktok edge-profile tasks"
```

## Task 7: Keep Browser Baseline Rules Correct For Non-TikTok Platforms

**Files:**
- Modify: `modules/apps/collection_center/browser_config_helper.py`
- Test: `backend/tests/test_browser_config_helper.py`

- [ ] **Step 1: Add failing tests for TikTok exception scoping**

Target behavior:
- general browser config helper still strips `channel` and `executable_path` for normal platforms
- TikTok attached Edge path does not depend on weakening the general helper

- [ ] **Step 2: Run tests to verify failure or missing coverage**

Run: `python -m pytest backend/tests/test_browser_config_helper.py -q`
Expected: FAIL on new exception-scoping assertions or reveal missing coverage

- [ ] **Step 3: Implement the minimal helper changes**

Implementation requirements:
- preserve current official-browser enforcement for standard paths
- ensure TikTok attached Edge runtime bypasses this helper by architecture, not by weakening the default rule globally
- keep helper semantics simple and explicit

- [ ] **Step 4: Run tests to verify pass**

Run: `python -m pytest backend/tests/test_browser_config_helper.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add modules/apps/collection_center/browser_config_helper.py backend/tests/test_browser_config_helper.py
git commit -m "test: scope tiktok edge exception outside global browser helper"
```

## Task 8: Update Runtime Docs To Record The TikTok Exception

**Files:**
- Modify: `docs/guides/COLLECTION_TEST_ENVIRONMENT_BASELINE.md`

- [ ] **Step 1: Write the documentation delta**

Document:
- baseline remains Playwright official browser for general collection/testing
- TikTok formal collection is an explicit exception
- the exception is:
  - local-machine only
  - dedicated Edge profile only
  - semi-automatic only
  - not the default baseline for other platforms

- [ ] **Step 2: Review docs against `.cursorrules` and AGENTS guidance**

Check:
- wording does not contradict current repository constraints
- exception scope is limited to TikTok formal collection

- [ ] **Step 3: Save the doc update**

Expected content:
- clear rationale for the TikTok exception
- instructions for future maintainers not to generalize the exception across all platforms

- [ ] **Step 4: Sanity-read the final text**

Expected: documentation now explains both the default baseline and the TikTok carve-out without ambiguity

- [ ] **Step 5: Commit**

```bash
git add docs/guides/COLLECTION_TEST_ENVIRONMENT_BASELINE.md
git commit -m "docs: record tiktok edge-profile formal collection exception"
```

## Task 9: End-to-End Verification On This Machine

**Files:**
- Modify: none required unless verification reveals gaps
- Test: targeted runtime and TikTok tests

- [ ] **Step 1: Run focused unit and integration tests**

Run:

```bash
python -m pytest backend/tests/test_edge_runtime.py backend/tests/test_tiktok_runtime_strategy.py backend/tests/test_tiktok_pause_resume_runtime.py backend/tests/test_browser_config_helper.py backend/tests/test_collection_queue_runner.py backend/tests/test_component_tester_runtime_config.py -q
```

Expected: PASS

- [ ] **Step 2: Run targeted TikTok component regression tests**

Run:

```bash
python -m pytest backend/tests/test_tiktok_login_component.py backend/tests/test_tiktok_products_export_component.py backend/tests/test_tiktok_analytics_export_component.py backend/tests/test_tiktok_services_agent_export_component.py -q
```

Expected: PASS

- [ ] **Step 3: Perform a local headed smoke run with the dedicated Edge profile**

Manual validation goals:
- attached Edge launches correctly
- dedicated TikTok profile is reused
- login-valid path proceeds automatically
- verification/login-required path pauses instead of failing terminally
- operator can continue in the same Edge window

- [ ] **Step 4: Capture any machine-specific setup notes**

Document:
- local Edge executable discovery result
- dedicated TikTok profile location convention
- any resume limitations discovered in the smoke run

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "feat: add tiktok edge-profile semi-automatic formal collection"
```

## Validation Checklist

- [ ] TikTok formal collection defaults to `edge_profile_attached`
- [ ] Non-TikTok platforms remain on the current browser baseline
- [ ] Attached Edge runtime returns usable `context` and `page`
- [ ] TikTok canonical components still drive business flow
- [ ] Login/verification state pauses instead of hard failing
- [ ] Resume continues in the same attached runtime session
- [ ] Export success gate still requires a real non-empty file
- [ ] Repository docs now describe TikTok as an explicit exception, not a new universal baseline

## Risks

- 本机 Edge profile 目录锁和并发占用可能导致 attach/reconnect 复杂度上升
- TikTok 验证页面的实际状态信号可能比当前组件覆盖面更复杂
- 如果暂停后进程生命周期管理不清晰，可能留下僵尸 Edge 进程或失效调试端口
- 文档 carve-out 如果写得不精确，后续可能被误读成“所有平台都可以直接切系统浏览器”

## Rollback Strategy

- 恢复 TikTok formal collection 到当前 `storage_state_fanout` / `persistent_profile` 流程
- 删除或停用 `edge_profile_attached` 运行时模式
- 保留新增测试，但将 TikTok 专用策略断言回滚为旧行为
- 恢复文档中的全局基线描述，仅保留 TikTok 设计 spec 作为历史记录

Plan complete and saved to `docs/superpowers/plans/2026-04-16-tiktok-edge-profile-semi-automatic-collection.md`. Ready to execute?
