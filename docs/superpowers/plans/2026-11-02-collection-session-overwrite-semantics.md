# 采集会话覆盖写入语义实施计划

> **⚠️ 本计划已被作废（2026-11-02）。**
>
> 业务决策 D5 改为**彻底废除会话文件、只用持久化 profile**，本计划的「会话文件覆盖写入」语义不再需要。
> 取代计划：`docs/superpowers/plans/2026-11-02-collection-profile-only-architecture.md`
> 规范来源：`docs/guides/COLLECTION_SESSION_LIFECYCLE.md` 生效版 v3
>
> 本文件仅作历史留存，请勿执行。

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让"登录成功后的新会话"能够真正覆盖旧会话，废除"人工会话保护 / 质量分回退保护"，把 `docs/guides/COLLECTION_SESSION_LIFECYCLE.md` v2 的 R1~R6 规则落到代码。

**Architecture:** 收口到三处语义改动 ——（1）`SessionManager.save_session` 改为无条件覆盖写入，不再比较新旧、不再按来源分优先级；（2）写入门槛只认"确认登录成功"，人工保存由用户确认、采集写回由登录组件打标 `session_refreshed`；（3）读取侧不做有效性判定，复用失败交由登录兜底。账号级串行（`MainAccountSessionCoordinator`）**已存在**，本计划只补验证。

**Tech Stack:** Python 3 / Playwright async / pytest / FastAPI + SQLAlchemy async（仅涉及采集运行时与 SessionManager，不涉及数据库迁移）

---

## 0. 前置条件与约束

| 项 | 值 |
|---|---|
| 规范来源 | `docs/guides/COLLECTION_SESSION_LIFECYCLE.md`（生效版 v2） |
| 关联事实记录 | 同文档 §1（2026-11-02 会话复用失效事故） |
| 分支 | `feature/session-overwrite`，基于 `main`（当前 `4f62b3cd`） |
| worktree | `.worktrees/session-overwrite`（用 `superpowers:using-git-worktrees` 建） |
| 单文件测试 | `python -m pytest backend/tests/<file>.py -v` |
| 相关测试集合 | `python -m pytest backend/tests/test_session_manager_overwrite.py backend/tests/test_collection_session_reuse_contract.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_collection_runtime_session.py backend/tests/test_pwcli_native_session_alignment.py backend/tests/test_persistent_browser_manager_session_metadata.py backend/tests/test_recording_handler_manual_session_metadata.py backend/tests/test_collection_task_runtime_metadata.py backend/tests/test_collection_executor_reused_session_scope.py -v` |
| 提交规范 | 显式文件列表，禁止 `git add -A` / `git add .`；禁止 `git stash` |
| 前端 | **零改动**（诊断字段降级为纯记录字段，响应结构不变） |

**不在本计划范围内**（概念文档 §9.2 的建议加固项，单独排期）：S2 巡店面板非阻断提示、S3 登录判定收紧（`next=` 参数、采集入口改首页）。

---

## 1. 变更地图（文件 → 责任）

| 文件 | 责任 | 对应规则 |
|---|---|---|
| `modules/utils/sessions/session_manager.py` | `save_session` 无条件覆盖；`load_session` 取消 30 天门禁 | R1 R3 R4 R5 |
| `modules/platforms/shopee/components/login.py` | 完整登录成功时打标 `session_refreshed` | R2（程序确认） |
| `modules/platforms/tiktok/components/login.py` | 同上 | R2 |
| `modules/platforms/miaoshou/components/login.py` | 同上 | R2 |
| `modules/apps/collection_center/executor_v2.py` | 写回门槛改为 `session_refreshed`；清理 `manual_seeded` 优先分支 | R2 R3 |
| `modules/apps/collection_center/runtime_session.py` | profile 引导不落盘；清理 `manual_seeded` 门禁豁免 | R2 R3 |
| `modules/utils/pwcli_native.py` | `command_open` 不回写；`command_state_save` 用 `source=manual` | R2 D1 D2 |
| `backend/tests/test_session_manager_protection.py` | **删除**（内容迁入新文件后） | — |
| `backend/tests/test_session_manager_overwrite.py` | **新建**：覆盖语义契约测试 | — |

**保留不动**（仅作纯记录字段，响应结构与前端零改动）：`session_quality_source` / `session_quality_score` / `session_manual_seeded` / `session_protected`（`backend/domains/collection/routers/collection_tasks.py:462-463`、`executor_v2.py:1146-1148`、`frontend/src/domains/collection/views/collection/CollectionTasks.vue:369-382`）。

---

## Task 0: 建立 worktree 并确认基线

**Files:**
- 无代码改动

- [ ] **Step 1: 建 worktree**

```powershell
git worktree add .worktrees/session-overwrite -b feature/session-overwrite main
```

Expected: 输出 `Preparing worktree (new branch 'feature/session-overwrite')`，目录创建成功。

- [ ] **Step 2: 确认基线：相关测试全绿**

```powershell
Set-Location F:\Vscode\python_programme\AI_code\xihong_erp\.worktrees\session-overwrite
python -m pytest backend/tests/test_session_manager_protection.py backend/tests/test_collection_session_reuse_contract.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_pwcli_native_session_alignment.py -v
```

Expected: 全部 PASS（若基线本身有失败，**停下报告**，不要把基线失败算到本计划头上）。

- [ ] **Step 3: 提交（仅当 Step 2 需要修补基线时才做）**

---

## Task 1: `save_session` 改为无条件覆盖（R1 / R3 / R4）

**Files:**
- Modify: `modules/utils/sessions/session_manager.py:436-496`
- Create: `backend/tests/test_session_manager_overwrite.py`
- Delete: `backend/tests/test_session_manager_protection.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_session_manager_overwrite.py`：

```python
from __future__ import annotations

import json
from pathlib import Path

from modules.utils.sessions.session_manager import SessionManager


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _manual_state() -> dict:
    return {
        "cookies": [{"name": "JSESSIONID", "domain": "erp.example.com", "path": "/"}],
        "origins": [],
    }


def _auto_state() -> dict:
    return {
        "cookies": [
            {"name": "JSESSIONID", "domain": "erp.example.com", "path": "/"},
            {"name": "sessionid", "domain": ".tiktokshopglobalselling.com", "path": "/"},
        ],
        "origins": [{"origin": "https://erp.example.com", "localStorage": []}],
    }


def test_automatic_save_overwrites_manual_session_even_when_lower_quality(tmp_path: Path) -> None:
    """R1：来源不分高下，自动写入必须覆盖人工会话。"""
    manager = SessionManager(base_path=tmp_path / "sessions")
    manager.save_session("miaoshou", "acc-1", _manual_state(), metadata={"source": "manual"})

    manager.save_session("miaoshou", "acc-1", {"cookies": [], "origins": []}, metadata={"source": "collection"})

    payload = _read(manager.get_session_path("miaoshou", "acc-1"))
    assert payload["storage_state"] == {"cookies": [], "origins": []}
    assert payload["metadata"]["source"] == "collection"


def test_automatic_save_overwrites_manual_session_even_when_higher_quality(tmp_path: Path) -> None:
    """R1/R4：新会话质量更高时也必须覆盖（旧实现会因质量分回退保护丢弃新 state）。"""
    manager = SessionManager(base_path=tmp_path / "sessions")
    manager.save_session(
        "tiktok",
        "acc-1",
        {"cookies": [{"name": "ttwid", "domain": ".tiktokshopglobalselling.com", "path": "/"}], "origins": []},
        metadata={"source": "manual"},
    )

    manager.save_session("tiktok", "acc-1", _auto_state(), metadata={"source": "collection"})

    payload = _read(manager.get_session_path("tiktok", "acc-1"))
    names = {c["name"] for c in payload["storage_state"]["cookies"]}
    assert "sessionid" in names


def test_manual_save_overwrites_collection_session(tmp_path: Path) -> None:
    """R1：人工保存同样覆盖。"""
    manager = SessionManager(base_path=tmp_path / "sessions")
    manager.save_session("shopee", "acc-1", _auto_state(), metadata={"source": "collection"})

    manager.save_session("shopee", "acc-1", _manual_state(), metadata={"source": "manual"})

    payload = _read(manager.get_session_path("shopee", "acc-1"))
    assert payload["storage_state"] == _manual_state()
    assert payload["metadata"]["source"] == "manual"


def test_every_write_refreshes_saved_at(tmp_path: Path) -> None:
    """R1：每次写入都是新的一份，saved_at 必须刷新（旧实现保留旧 state 时不刷新）。"""
    manager = SessionManager(base_path=tmp_path / "sessions")
    path = manager.get_session_path("shopee", "acc-1")

    manager.save_session("shopee", "acc-1", _manual_state(), metadata={"source": "manual"})
    first = _read(path)["metadata"]["saved_at"]

    manager.save_session("shopee", "acc-1", _auto_state(), metadata={"source": "collection"})
    second = _read(path)["metadata"]["saved_at"]

    assert second > first


def test_metadata_keeps_diagnostic_fields_as_record_only(tmp_path: Path) -> None:
    """R7：诊断字段降级为纯记录，不含已废除的保护语义。"""
    manager = SessionManager(base_path=tmp_path / "sessions")
    manager.save_session(
        "shopee",
        "acc-1",
        _manual_state(),
        metadata={"source": "manual", "manual_seeded": True, "protected": True},
    )

    meta = _read(manager.get_session_path("shopee", "acc-1"))["metadata"]
    assert meta["source"] == "manual"
    assert meta["manual_seeded"] is True
    assert meta["protected"] is False
    assert "quality_score" in meta
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
python -m pytest backend/tests/test_session_manager_overwrite.py -v
```

Expected: `test_automatic_save_overwrites_manual_session_even_when_lower_quality` FAIL（当前实现保留旧 state）；`test_every_write_refreshes_saved_at` FAIL。

- [ ] **Step 3: 改 `save_session`**

把 `modules/utils/sessions/session_manager.py:436-496` 整段替换为：

```python
            old_metadata = existing_session.get("metadata") if isinstance(existing_session, dict) else {}
            old_metadata = old_metadata if isinstance(old_metadata, dict) else {}
            incoming_metadata = metadata if isinstance(metadata, dict) else {}

            # 会话语义（docs/guides/COLLECTION_SESSION_LIFECYCLE.md R1/R3/R4）：
            # 覆盖写入。不比较新旧、不按来源分优先级、不做质量分回退保护。
            # 来源只作为审计记录保存，不参与任何决策。
            selected_state = merged_storage_state

            current_time = time.time()
            # created_at 保留首次创建时间；会话新鲜度由 saved_at 驱动。
            created_at = current_time
            if existing_session and isinstance(existing_session.get("created_at"), (int, float)):
                created_at = float(existing_session.get("created_at"))

            merged_metadata: Dict[str, Any] = {}
            merged_metadata.update(old_metadata)
            merged_metadata.update(incoming_metadata)

            source = str(incoming_metadata.get("source") or "").strip().lower()
            if not source:
                source = str(old_metadata.get("source") or "").strip().lower()
            if not source:
                source = "collection"
            merged_metadata["source"] = source
            merged_metadata["saved_at"] = current_time
            merged_metadata["written_at"] = current_time
            task_id = incoming_metadata.get("task_id")
            if task_id:
                merged_metadata["task_id"] = task_id

            # 诊断字段：仅供排查与前端展示，任何分支都不得据此做选择。
            merged_metadata["quality_source"] = source
            merged_metadata["manual_seeded"] = source == "manual"
            merged_metadata["protected"] = False
            merged_metadata["quality_score"] = session_quality_score(normalized_platform, selected_state)
            merged_metadata["quality_gate_passed"] = bool(
                session_meets_quality_gate(normalized_platform, selected_state)
            )
```

同时删除 `old_score` / `new_score` / `merged_score` / `old_gate` / `merged_gate` / `old_protected` / `incoming_manual` 这几个只服务于旧分支的局部变量（`:440-446`），以及 `kept_old_state`（`:472`）。

> 注意：`:402-404` 的 tiktok merge **保留**。merge 是字段级合并（同名 cookie 以新值为准），不是"择优比较"，不违反 R4。

- [ ] **Step 4: 跑测试确认通过**

```powershell
python -m pytest backend/tests/test_session_manager_overwrite.py -v
```

Expected: 5 passed。

- [ ] **Step 5: 删除旧测试文件并跑相关测试集合**

```powershell
git rm backend/tests/test_session_manager_protection.py
python -m pytest backend/tests/test_collection_session_reuse_contract.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_persistent_browser_manager_session_metadata.py backend/tests/test_recording_handler_manual_session_metadata.py backend/tests/test_collection_task_runtime_metadata.py -v
```

Expected: 全部 PASS。**若有失败，逐条判断是不是"旧行为断言"**（断言 protected 优先 / saved_at 不刷新 / 质量分回退）—— 是则按新语义改断言，不是则停下报告。

- [ ] **Step 6: 提交**

```powershell
git add modules/utils/sessions/session_manager.py backend/tests/test_session_manager_overwrite.py
git commit -m "fix(session): 会话保存改为无条件覆盖，废除人工保护与质量分回退"
```

---

## Task 2: 读取侧取消 30 天门禁（R5）

**Files:**
- Modify: `modules/utils/sessions/session_manager.py:518-553`（`load_session`）
- Modify: `modules/utils/sessions/session_manager.py:663-676`（另一处 `load_session` 包装）
- Modify: `modules/apps/collection_center/runtime_session.py:245-253`、`:336-342`、`:352-357`
- Modify: `modules/apps/collection_center/executor_v2.py:231-240`、`:280-292`
- Test: `backend/tests/test_session_manager_overwrite.py`（追加）

- [ ] **Step 1: 写失败测试**（追加到 `test_session_manager_overwrite.py`）

```python
def test_expired_session_is_still_loaded(tmp_path: Path) -> None:
    """R5：读取不做有效性判定，过期与否交给登录组件兜底。"""
    manager = SessionManager(base_path=tmp_path / "sessions")
    manager.save_session("shopee", "acc-1", _manual_state(), metadata={"source": "manual"})

    path = manager.get_session_path("shopee", "acc-1")
    payload = _read(path)
    payload["metadata"]["saved_at"] = 1.0
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    loaded = manager.load_session("shopee", "acc-1")
    assert loaded is not None
    assert loaded["storage_state"] == _manual_state()
```

- [ ] **Step 2: 跑测试确认失败**

```powershell
python -m pytest backend/tests/test_session_manager_overwrite.py::test_expired_session_is_still_loaded -v
```

Expected: FAIL（当前 `max_age_days=30` 默认值把它判为过期返回 None）。

- [ ] **Step 3: 改默认值**

`session_manager.py`：

```python
    def load_session(
        self,
        platform: str,
        account_id: str,
        max_age_days: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
```

并把 docstring 里的"会话数据,失败或过期返回None"改为"会话数据,失败返回None"。

同文件 `:663-676` 的包装函数签名同步改为 `max_age_days: Optional[int] = None`。

`runtime_session.py` 三处与 `executor_v2.py` 两处的 `max_age_days: int = 30` 全部改为 `max_age_days: Optional[int] = None`（补 `Optional` 导入）。

> `cleanup_expired_sessions(max_age_days=30)` 是显式运维清理，**保留不改**。

- [ ] **Step 4: 跑测试确认通过**

```powershell
python -m pytest backend/tests/test_session_manager_overwrite.py -v
```

Expected: 6 passed。

- [ ] **Step 5: 跑相关测试**

```powershell
python -m pytest backend/tests/test_collection_session_reuse_contract.py backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_runtime_session.py backend/tests/test_component_tester_runtime_config.py -v
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```powershell
git add modules/utils/sessions/session_manager.py modules/apps/collection_center/runtime_session.py modules/apps/collection_center/executor_v2.py backend/tests/test_session_manager_overwrite.py
git commit -m "fix(session): 读取侧取消 30 天门禁，会话可用性交由登录兜底"
```

---

## Task 3: 登录组件打标 `session_refreshed`，写回门槛收紧（R2）

**Files:**
- Modify: `modules/platforms/shopee/components/login.py:444-560`
- Modify: `modules/platforms/tiktok/components/login.py`（登录成功返回点）
- Modify: `modules/platforms/miaoshou/components/login.py`（登录成功返回点）
- Modify: `modules/apps/collection_center/executor_v2.py:1312-1348`、`:3204-3240`
- Test: `backend/tests/test_session_manager_overwrite.py`（追加） + `backend/tests/test_collection_executor_session_alignment.py`（追加）

- [ ] **Step 1: 确认 config 对象共享（前置验证）**

在 `modules/platforms/shopee/components/login.py` 的 `run()` 里临时打印 `id(self.ctx.config)`，并在 `executor_v2.py:1199` 处打印 `id(params)`，跑一次采集确认两者一致。

**如果一致** → 按下面的 `config` 打标方案。
**如果不一致** → 改用 `LoginResult` 字段方案：在 `modules/components/login/base.py` 的 `LoginResult` 增加 `session_refreshed: bool = False`，由组件返回，executor 在 `_run_runtime_manifest_component` 分支直接读取 `login_result.session_refreshed`；`_execute_python_component` 分支（只返回 bool）改为同时返回结果对象。

> 仓库已有"共享 params 突变"的先例（`apply_verification_result_to_params(params, ...)` 用于回填验证码），因此 `config` 打标方案与既有约定一致。

- [ ] **Step 2: 写失败测试**（追加到 `test_session_manager_overwrite.py`）

```python
def test_session_refreshed_flag_marks_full_login_only():
    """R2：只有完整登录才置 session_refreshed；复用成功不置。"""
    from modules.platforms.shopee.components.login import ShopeeLogin

    login = ShopeeLogin.__new__(ShopeeLogin)
    config: dict = {}
    login._mark_session_refreshed(config)
    assert config["session_refreshed"] is True
    assert config["params"]["session_refreshed"] is True
```

- [ ] **Step 3: 跑测试确认失败**

```powershell
python -m pytest backend/tests/test_session_manager_overwrite.py::test_session_refreshed_flag_marks_full_login_only -v
```

Expected: FAIL（`AttributeError: 'ShopeeLogin' object has no attribute '_mark_session_refreshed'`）。

- [ ] **Step 4: shopee 登录组件打标**

在 `modules/platforms/shopee/components/login.py` 的类里加辅助方法：

```python
    @staticmethod
    def _mark_session_refreshed(config: Dict[str, Any]) -> None:
        """本轮执行了完整登录并成功 —— 标记为"新的确认登录态"（R2）。

        复用会话成功（已登录 / 跳转命中）**不**打标：那不是一次新的确认登录，
        写回只会用当时的浏览器快照覆盖既有文件（网络抖动时可能残缺）。
        """
        if not isinstance(config, dict):
            return
        config["session_refreshed"] = True
        inner = config.get("params")
        if isinstance(inner, dict):
            inner["session_refreshed"] = True
```

然后在 `run()` 里：

- `:448-451`（OTP 提交后 success）→ 调 `self._mark_session_refreshed(config)` 后再 return
- `:537-540`（凭据提交后 success）→ 同样打标
- `:509-513`（`reused_session` 跳转成功）→ **不打标**
- `:522-524` / `:529-531`（`_login_looks_successful` 命中）→ **不打标**
- `:467-469`（入口即 already logged in）→ **不打标**

tiktok 与 miaoshou 登录组件做同样处理（打标点 = 完整登录成功返回点；复用/已登录分支不打标）。

- [ ] **Step 5: executor 写回门槛**

`executor_v2.py:1312` 与 `:3204`，把条件从：

```python
        if save_session_after_login and session_platform and session_account_id:
```

改为：

```python
        session_refreshed = bool(
            params.get("session_refreshed")
            or (params.get("params") or {}).get("session_refreshed")
        )
        if save_session_after_login and session_platform and session_account_id and session_refreshed:
```

并在 `:1301` 的日志改为：

```python
        logger.info(
            "Task %s: [Python] Login completed successfully (reused_session=%s, session_refreshed=%s)",
            task_id,
            params.get("reused_session", False),
            session_refreshed,
        )
```

> `:3195` 的同类日志同步改。

- [ ] **Step 6: 跑测试确认通过**

```powershell
python -m pytest backend/tests/test_session_manager_overwrite.py backend/tests/test_collection_executor_session_alignment.py -v
```

Expected: 全部 PASS。

- [ ] **Step 7: 提交**

```powershell
git add modules/platforms/shopee/components/login.py modules/platforms/tiktok/components/login.py modules/platforms/miaoshou/components/login.py modules/apps/collection_center/executor_v2.py backend/tests/test_session_manager_overwrite.py backend/tests/test_collection_executor_session_alignment.py
git commit -m "fix(session): 仅完整登录成功后写回会话，复用成功不写回"
```

---

## Task 4: `pwcli open` 不回写会话（D1）

**Files:**
- Modify: `modules/utils/pwcli_native.py:648-665`（`command_open`）
- Test: `backend/tests/test_pwcli_native_session_alignment.py`（追加）

- [ ] **Step 1: 写失败测试**（追加到 `test_pwcli_native_session_alignment.py`）

```python
def test_command_open_does_not_write_back_storage_state(tmp_path, monkeypatch) -> None:
    """D1/R2：打开平台不是确认登录成功，不得回写会话文件。"""
    import modules.utils.pwcli_native as pwcli_native

    calls: list = []

    def _fake_save_default(*args, **kwargs):
        calls.append(args)
        return None

    monkeypatch.setattr(pwcli_native, "save_default_storage_state_from_context", _fake_save_default)
    # ... 按 test_pwcli_native_session_alignment.py 既有 fixture 构造 session/browser/page ...
    # 断言 calls == []
```

> 实施时先读该文件既有的 `command_open` 相关 fixture（如 `test_command_open_*`），复用同样的 stub 写法，不要另造一套。

- [ ] **Step 2: 跑测试确认失败**

```powershell
python -m pytest backend/tests/test_pwcli_native_session_alignment.py -k "does_not_write_back" -v
```

Expected: FAIL（当前 `command_open` 末尾无条件调用 `save_default_storage_state_from_context`）。

- [ ] **Step 3: 改 `command_open`**

`modules/utils/pwcli_native.py:659-661`：

```python
        if url:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # D1/R2：打开不是"确认登录成功"，不回写会话文件。
        # 打开时的浏览器快照可能因网络抖动而残缺，写回会污染已有会话。
```

（删除 `save_default_storage_state_from_context(metadata, context)` 这一行。）

> `:664` 的 `save_session(session, metadata)` **保留** —— 那是 pwcli 自身的进程元数据（pid/port），不是 storage_state。

- [ ] **Step 4: 跑测试确认通过**

```powershell
python -m pytest backend/tests/test_pwcli_native_session_alignment.py backend/tests/test_pwcli_helpers_session_targeting.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```powershell
git add modules/utils/pwcli_native.py backend/tests/test_pwcli_native_session_alignment.py
git commit -m "fix(pwcli): 打开平台不再回写会话文件"
```

---

## Task 5: 巡店「保存会话」语义（D2）

**Files:**
- Modify: `modules/utils/pwcli_native.py:325-348`（`save_default_storage_state_from_context`）、`:899-935`（`command_state_save`）
- Modify: `modules/apps/collection_center/handlers.py:96-98`（人工会话 metadata 常量）
- Test: `backend/tests/test_pwcli_native_session_alignment.py`（改写既有断言）

- [ ] **Step 1: 改既有断言为新语义**

`backend/tests/test_pwcli_native_session_alignment.py` 中 `test_save_default_storage_state_from_context_marks_account_state_as_manual_seeded`（约 `:139`）改为断言 `source == "manual"`，并新增"人工保存的会话必须覆盖既有会话"的断言。

- [ ] **Step 2: 跑测试确认失败**

```powershell
python -m pytest backend/tests/test_pwcli_native_session_alignment.py -v
```

Expected: FAIL（当前 metadata 是 `quality_source/manual_seeded/protected`）。

- [ ] **Step 3: 改实现**

`pwcli_native.py:913-924`：

```python
        elif state_mode == "session_manager" and default_state_path:
            save_default_storage_state_from_context(
                metadata,
                context,
                session_metadata={
                    "source": "manual",
                },
            )
            synced_default = True
            print(default_state_path)
```

`pwcli_native.py:931-932`：

```python
        if not synced_default:
            save_default_storage_state_from_context(metadata, context)
```

这一处在 `session_manager` 模式下会**再写一次**且丢掉 `source=manual`（新语义下会覆盖掉 metadata）。改为：

```python
        if not synced_default and state_mode != "session_manager":
            save_default_storage_state_from_context(metadata, context)
```

`modules/apps/collection_center/handlers.py:96-98`：

```python
    "source": "manual",
```

（替换 `quality_source` / `manual_seeded` / `protected` 三个键。）

- [ ] **Step 4: 跑测试确认通过**

```powershell
python -m pytest backend/tests/test_pwcli_native_session_alignment.py backend/tests/test_recording_handler_manual_session_metadata.py backend/tests/test_persistent_browser_manager_session_metadata.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```powershell
git add modules/utils/pwcli_native.py modules/apps/collection_center/handlers.py backend/tests/test_pwcli_native_session_alignment.py
git commit -m "fix(session): 人工保存会话改用 source=manual 语义并去掉重复写入"
```

---

## Task 6: profile 引导不落盘（D3）

**Files:**
- Modify: `modules/apps/collection_center/runtime_session.py:296-312`
- Test: `backend/tests/test_collection_runtime_session.py`（追加）

- [ ] **Step 1: 写失败测试**

```python
def test_bootstrap_from_profile_does_not_persist_session_file(tmp_path, monkeypatch) -> None:
    """D3/R2：引导出的内容未经登录确认，不得落盘为会话文件。"""
    from modules.apps.collection_center import runtime_session as rs

    manager = type("M", (), {})()
    saved: list = []
    manager.save_session = lambda *a, **k: saved.append(a) or True
    monkeypatch.setattr(rs, "SessionManager", lambda *a, **k: manager)

    # ... 构造 profile 引导路径使其走到 save_session 调用点 ...
    assert saved == []
```

> 实施时先读 `backend/tests/test_collection_runtime_session.py` 里既有的 bootstrap 测试，复用其 profile fixture。

- [ ] **Step 2: 跑测试确认失败**

```powershell
python -m pytest backend/tests/test_collection_runtime_session.py -k "bootstrap" -v
```

Expected: FAIL（当前会调用 `manager.save_session`）。

- [ ] **Step 3: 改实现**

`runtime_session.py:306-312`：

```python
    # D3/R2：profile 引导出的内容未经"确认登录成功"，只作为本轮运行起点，不落盘。
    # 若本轮确实完成了完整登录，由执行器按 R1 覆盖写入会话文件。
    return {"storage_state": storage_state}
```

（删除 `manager.save_session(...)` 调用。）

- [ ] **Step 4: 跑测试确认通过**

```powershell
python -m pytest backend/tests/test_collection_runtime_session.py backend/tests/test_collection_session_reuse_contract.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```powershell
git add modules/apps/collection_center/runtime_session.py backend/tests/test_collection_runtime_session.py
git commit -m "fix(session): profile 引导不再落盘为会话文件"
```

---

## Task 7: 清理 `manual_seeded` 优先分支（R3）

**Files:**
- Modify: `modules/apps/collection_center/executor_v2.py:943-958`（策略选择）、`:1021-1029`（session_source 标注）、`:2865-2870`（`_should_skip_post_login_session_persist`）
- Modify: `modules/apps/collection_center/runtime_session.py:355-370`、`:505-520`
- Test: `backend/tests/test_collection_executor_session_alignment.py`、`backend/tests/test_collection_runtime_session.py`

- [ ] **Step 1: 梳理当前依赖点**

```powershell
Select-String -Path modules\apps\collection_center\executor_v2.py,modules\apps\collection_center\runtime_session.py -Pattern 'manual_seeded|protected'
```

Expected: 命中 `executor_v2.py` 的 `:948`、`:1026`、`:1147-1148`、`:2867`；`runtime_session.py` 的 `:361-365`、`:513-514`。

- [ ] **Step 2: 改 `executor_v2.py:947-949`**

```python
                has_manual_storage_state=prefer_manual_storage_state,
```

（去掉 `or session_candidate.manual_seeded`。R3：来源不分高下，人工会话不再有优先权。）

- [ ] **Step 3: 改 `executor_v2.py:1021-1029`**

```python
            session_source=(
                "manual_storage_state"
                if str((session_candidate.metadata or {}).get("source") or "") == "manual"
                and effective_storage_state
                else ("storage_state" if effective_storage_state else "fresh_login")
            ),
```

（诊断用途，用 `source` 判断，不再用 `manual_seeded` 保护标记。）

- [ ] **Step 4: 改 `runtime_session.py:355-370` 与 `:505-520`**

- `:361-365` 的"manual_seeded 时跳过 tiktok 质量门禁"分支：按 R4，**质量门禁不再参与新旧选择**。该豁免改为**无条件跳过**（即 tiktok 引导内容不再因质量分不足被丢弃），或直接删除该门禁调用 —— 实施时按"读取即信任"（R5）统一处理：引导内容一律可用。
- `:513-514` 的 `manual_seeded` property：保留但改为读取 `source`：

```python
    @property
    def manual_seeded(self) -> bool:
        return str(self.metadata.get("source") or "").strip().lower() == "manual"
```

- [ ] **Step 5: 改 `executor_v2.py:2865-2870`**

```python
        if str(metadata.get("source") or "").strip().lower() == "manual":
            return False
        return True
```

（`_should_skip_post_login_session_persist` 仍只对 tiktok persistent profile 生效，这里只是把"人工会话"判据从保护标记换成 `source`。）

- [ ] **Step 6: 跑测试**

```powershell
python -m pytest backend/tests/test_collection_executor_session_alignment.py backend/tests/test_collection_runtime_session.py backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_task_runtime_metadata.py -v
```

Expected: 全部 PASS。**断言了旧优先级的用例按新语义改写**（如 `test_manual_seeded_session_is_not_skipped_for_tiktok`）。

- [ ] **Step 7: 提交**

```powershell
git add modules/apps/collection_center/executor_v2.py modules/apps/collection_center/runtime_session.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_collection_runtime_session.py backend/tests/test_collection_executor_reused_session_scope.py
git commit -m "refactor(session): 清理 manual_seeded 优先分支，来源不再参与选择"
```

---

## Task 8: 账号级串行（R6）验证

**Files:**
- Test: `backend/tests/test_main_account_session_coordinator.py`（既有）
- Verify: `modules/apps/collection_center/executor_v2.py:854`、`:5843`

- [ ] **Step 1: 确认 R6 已实现**

```powershell
Select-String -Path modules\apps\collection_center\executor_v2.py -Pattern 'main_account_session_coordinator.acquire'
```

Expected: 命中 `:854`（并行域路径）与 `:5843`（主执行路径）。**R6 不需要新代码**。

- [ ] **Step 2: 跑既有测试**

```powershell
python -m pytest backend/tests/test_main_account_session_coordinator.py backend/tests/test_collection_executor_session_alignment.py -v
```

Expected: 全部 PASS。

- [ ] **Step 3: 在概念文档 §10 验收表补一条实测结论**

在 `docs/guides/COLLECTION_SESSION_LIFECYCLE.md` 的 §10 追加一行实测记录（不新增代码）。

---

## Task 9: 文档同步

**Files:**
- Modify: `docs/guides/COLLECTION_SESSION_LIFECYCLE.md`（§7 审计元数据字段表 + §11 变更记录）
- Modify: `docs/guides/COLLECTION_SESSION_AND_FINGERPRINT.md`（会话持久化行为段落）
- Verify: `docs/ACTIVE_DOCS.md`（已在本轮更新，无需再改）

- [ ] **Step 1: 更新 §7 审计元数据表**

把字段表改为与实现一致：

| 字段 | 含义 |
|---|---|
| `written_at` / `saved_at` | 本次写入时刻 |
| `source` | `manual` / `collection`（**仅记录**） |
| `task_id` | 触发本次写入的采集任务（人工保存为空） |
| `quality_score` / `quality_gate_passed` / `quality_source` / `manual_seeded` / `protected` | **纯记录字段**，仅供前端诊断展示；任何分支不得据此做选择 |

- [ ] **Step 2: 更新 §11 变更记录**

追加一行：`2026-11-02 | 生效版 v2.1 | 按实施结果回填字段清单与 R6 实测结论`。

- [ ] **Step 3: 跑文档校验**

```powershell
python scripts/verify_rules_completeness.py
python scripts/verify_root_md_whitelist.py
python scripts/verify_utf8_source_hygiene.py
```

Expected: 全部 exit=0。

- [ ] **Step 4: 提交**

```powershell
git add docs/guides/COLLECTION_SESSION_LIFECYCLE.md docs/guides/COLLECTION_SESSION_AND_FINGERPRINT.md
git commit -m "docs(session): 回填会话语义实施结果"
```

---

## Task 10: 全量验收

**Files:**
- 无代码改动

- [ ] **Step 1: 跑会话相关测试全集**

```powershell
python -m pytest backend/tests/test_session_manager_overwrite.py backend/tests/test_collection_session_reuse_contract.py backend/tests/test_collection_executor_session_alignment.py backend/tests/test_collection_executor_reused_session_scope.py backend/tests/test_collection_runtime_session.py backend/tests/test_pwcli_native_session_alignment.py backend/tests/test_pwcli_helpers_session_targeting.py backend/tests/test_persistent_browser_manager_session_metadata.py backend/tests/test_recording_handler_manual_session_metadata.py backend/tests/test_collection_task_runtime_metadata.py backend/tests/test_main_account_session_coordinator.py backend/tests/test_session_storage_roots.py -v
```

Expected: 全部 PASS。

- [ ] **Step 2: 跑仓库总验收**

```powershell
python -m pytest backend/tests -q
```

Expected: 全部 PASS（基线 318 passed 附近；若有新增失败必须定位到本计划改动）。

- [ ] **Step 3: 跑发布前门禁**

```powershell
python scripts/verify_release_local.py --skip-build
```

Expected: exit=0。

- [ ] **Step 4: 真实采集验收（关键）**

在**本地**按下列顺序执行，验证概念文档 §10 的 A/B/C/D/E 场景：

1. 备份并清空当前那份已知过期的会话：
   `data/sessions/shopee/shopee KR/storage_state.json` → 改名备份为 `storage_state.json.bak-20261102`（不进 VCS，`data/` 已被忽略）。
2. 采集任务 A（`shopee_sg_eternalbloom_local`）→ 应要求登录 + 验证码 → 登录成功后**会话文件应被新内容覆盖**，`saved_at` = 本次时刻，cookie 有效期在未来。
3. 立刻再跑一次采集任务 A' → **应免验证码**。
4. 检查 `data/sessions/shopee/shopee KR/storage_state.json` 的 `metadata.source` 应为 `collection`。
5. 巡店面板「打开巡店」→ **会话文件的 mtime 与内容都不应变化**（D1）。
6. 巡店面板「保存会话」→ 会话文件应被覆盖，`metadata.source` 变为 `manual`。
7. 再跑一次采集 → 仍应免验证码。

**Expected**：第 2、3、6、7 步全部符合；第 5 步文件不变。若第 2 步登录后文件仍未被覆盖 → **停下报告**，说明 Task 1/3 有遗漏。

- [ ] **Step 5: 记录验收结论**

把 Task 10 Step 4 的实测结果写进 `docs/guides/COLLECTION_SESSION_LIFECYCLE.md` §10 表格的"实测"列。

- [ ] **Step 6: 提交**

```powershell
git add docs/guides/COLLECTION_SESSION_LIFECYCLE.md
git commit -m "docs(session): 记录覆盖写入语义的真实验收结论"
```

---

## 11. 合并与收尾

- [ ] **Step 1: 回到主仓合并 worktree**

```powershell
Set-Location F:\Vscode\python_programme\AI_code\xihong_erp
git merge --no-ff feature/session-overwrite
```

- [ ] **Step 2: 清理 worktree**

```powershell
git worktree remove .worktrees/session-overwrite
git branch -d feature/session-overwrite
```

- [ ] **Step 3: 复核工作区**

```powershell
git status --porcelain
git log --oneline -3
```

Expected: 工作区干净。

> **本计划只改 `main` 本地分支。发布（打 tag、推双远端）不在本计划范围内，需另行按 `docs/guides/RELEASE_CHECKLIST.md` 执行。**

---

## 附：风险与回退

| 风险 | 表现 | 处置 |
|---|---|---|
| `config` 对象在组件与 executor 间不是同一实例 | `session_refreshed` 传不回来 | Task 3 Step 1 会先验证；不一致则改走 `LoginResult` 字段方案 |
| 旧断言大量失败 | 相关测试文件红 | 逐条判断"旧行为断言" vs "真回归"；前者按新语义改写，后者停下报告 |
| TikTok merge 行为变化 | tiktok 采集复用异常 | Task 1 保留 merge；若仍异常，对比 merge 前后 storage_state 差异 |
| 真实采集仍要验证码 | §10 Step 4 第 3 步失败 | 说明会话写回链路未打通，按 Task 1/3 逐点复查，不要加临时补丁 |
