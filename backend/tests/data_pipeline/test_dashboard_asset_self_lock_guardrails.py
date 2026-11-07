"""看板资产**自锁循环**的守护测试。

背景（2026-11-07 实测事故）
--------------------------
    迁移重建了看板资产（事实已是新的）
      → 记账（``ops.dashboard_asset_state``）没回写
      → 模块被判 ``refreshing``
      → 修复方把「自己正在制造的 refreshing」当成失败条件
      → 任务失败 ⇒ 退避重排
      → 安全网每 5 分钟又排一次
      → 每 2~5 分钟一轮，攒出 **859 次 failed** 的修复任务。

这里守的是**四个断点**，任何一个被改回去，自锁就会复活：

1. 状态机：**没有「没人能修」的状态** —— 刷新资产的定义漂移不再⇒``refreshing``；
2. 状态机：缺失对象是 ``drift``（可自愈），不是 ``refreshing``（修不掉）；
3. 口径：验收方（``refresh_validation``）与运行期门禁（API）对同一批状态
   给**同一个**结论；
4. 安全网：只修可自愈的状态 + 连续失败熔断 + 僵尸 run 回收。
"""

from __future__ import annotations

import pytest

from backend.services.data_pipeline import dashboard_bootstrap
from backend.services.data_pipeline import refresh_validation


def _module_state(
    *,
    core_applied: str | None,
    refresh_applied: str | None,
    status: str = "ready",
) -> dict:
    return {
        "status": status,
        "asset_fingerprint_applied": core_applied,
        "details_json": {"refresh_fingerprint_applied": refresh_applied},
    }


def _all_objects(module_name: str = "business_overview") -> set[str]:
    return set(
        dashboard_bootstrap._module_core_plan(module_name)
        + dashboard_bootstrap._module_refresh_plan(module_name)
    )


# ── 断点 1：定义漂移不再制造死区 ───────────────────────────────────────────


def test_refresh_fingerprint_drift_does_not_keep_module_in_refreshing():
    """刷新资产的文件指纹对不上，**不得**把模块钉在 ``refreshing``。

    为什么：物化资产文件是「存在则 REFRESH / 不存在则 CREATE」
    ⇒ 对**已存在**的对象从不重建定义 ⇒ 任何自愈路径都消不掉这个差值。
    拿它当状态判据 = 制造一个「没人能修、却被无限重试」的死区。
    """
    core_fp = dashboard_bootstrap._compute_targets_fingerprint(
        dashboard_bootstrap._module_core_plan("business_overview")
    )
    report = dashboard_bootstrap._build_module_report(
        module_name="business_overview",
        module_state=_module_state(
            core_applied=core_fp,
            refresh_applied="stale-fingerprint-from-before-the-migration",
        ),
        existing_objects=_all_objects(),
        active_refresh_run=None,
    )

    assert report["status"] == "ready"
    assert report["ready"] is True
    # 漂移仍然**可见**（运维可查），但不参与状态判定。
    assert report["refresh_fingerprint_drift"] is True


def test_refresh_fingerprint_aligned_is_not_reported_as_drift():
    core_fp = dashboard_bootstrap._compute_targets_fingerprint(
        dashboard_bootstrap._module_core_plan("business_overview")
    )
    refresh_fp = dashboard_bootstrap._compute_targets_fingerprint(
        dashboard_bootstrap._module_refresh_plan("business_overview")
    )
    report = dashboard_bootstrap._build_module_report(
        module_name="business_overview",
        module_state=_module_state(core_applied=core_fp, refresh_applied=refresh_fp),
        existing_objects=_all_objects(),
        active_refresh_run=None,
    )

    assert report["refresh_fingerprint_drift"] is False


def test_active_refresh_run_still_marks_module_refreshing():
    """真有一趟刷新在跑时，仍然要显示「正在刷新」（这是有用的提示）。"""
    core_fp = dashboard_bootstrap._compute_targets_fingerprint(
        dashboard_bootstrap._module_core_plan("business_overview")
    )
    refresh_fp = dashboard_bootstrap._compute_targets_fingerprint(
        dashboard_bootstrap._module_refresh_plan("business_overview")
    )
    report = dashboard_bootstrap._build_module_report(
        module_name="business_overview",
        module_state=_module_state(core_applied=core_fp, refresh_applied=refresh_fp),
        existing_objects=_all_objects(),
        active_refresh_run={"run_id": "run-active"},
    )

    assert report["status"] == "refreshing"
    assert report["ready"] is True


# ── 断点 2：缺失对象 = 可自愈的 drift ─────────────────────────────────────


def test_missing_refresh_object_is_drift_not_refreshing():
    """刷新资产缺失 = 硬伤：页面直接读不到数据。

    旧口径把它算成 ``refreshing``（页面照常展示、其实是空的），
    而修复路径对「已存在的普通视图」是跳过的 ⇒ 同样修不掉 ⇒ 死区。
    """
    core_fp = dashboard_bootstrap._compute_targets_fingerprint(
        dashboard_bootstrap._module_core_plan("business_overview")
    )
    refresh_fp = dashboard_bootstrap._compute_targets_fingerprint(
        dashboard_bootstrap._module_refresh_plan("business_overview")
    )
    existing = _all_objects()
    existing.remove("semantic.fact_orders_atomic")

    report = dashboard_bootstrap._build_module_report(
        module_name="business_overview",
        module_state=_module_state(core_applied=core_fp, refresh_applied=refresh_fp),
        existing_objects=existing,
        active_refresh_run=None,
    )

    assert report["status"] == "drift"
    assert report["ready"] is False
    assert "semantic.fact_orders_atomic" in report["refresh_missing_objects"]


# ── 断点 3：验收口径与运行期门禁同源 ─────────────────────────────────────


@pytest.mark.parametrize("status", ["ready", "refreshing"])
def test_validation_accepts_available_module_statuses(status):
    """``refreshing`` 是**可用**状态 —— 修复方不能把它当成失败条件。"""
    assert (
        refresh_validation._module_status_is_ready({"status": status}) is True
    )


@pytest.mark.parametrize("status", ["drift", "failed", ""])
def test_validation_rejects_unavailable_module_statuses(status):
    assert refresh_validation._module_status_is_ready({"status": status}) is False


def test_validation_and_runtime_gate_share_one_status_source():
    """验收方与 API 门禁必须用**同一份**可用状态定义。

    两边各写一份常量迟早分叉 ⇒ 分叉的表现就是：修复方自己判自己失败
    ⇒ 退避重排 ⇒ 自锁复活。
    """
    from backend.domains.business.routers import (
        dashboard_api_postgresql as router_module,
    )

    assert (
        dashboard_bootstrap.DASHBOARD_ASSET_AVAILABLE_STATUSES
        is refresh_validation.DASHBOARD_ASSET_AVAILABLE_STATUSES
    )
    for status in ("ready", "refreshing", "drift", "failed", "unknown"):
        module_report = {"status": status, "ready": status != "drift"}
        validation_says_ready = refresh_validation._module_status_is_ready(
            module_report
        )
        gate_says_ready = status in dashboard_bootstrap.DASHBOARD_ASSET_AVAILABLE_STATUSES
        assert validation_says_ready == gate_says_ready, status


# ── 断点 4：安全网只修可自愈的状态 + 熔断 ─────────────────────────────────


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def mappings(self):
        return self._rows


class _FakeSession:
    """只回放安全网需要的两条查询。"""

    def __init__(self, *, repair_rows=None, reaped_ids=None):
        self._repair_rows = repair_rows or []
        self._reaped_ids = reaped_ids or []
        self.executed: list[str] = []
        self.committed = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.executed.append(sql)
        if "UPDATE ops.pipeline_run_log" in sql:
            return _FakeResult([(row_id,) for row_id in self._reaped_ids])
        if "FROM core.refresh_queue_tasks" in sql:
            return _FakeResult(list(self._repair_rows))
        return _FakeResult([])

    async def commit(self):
        self.committed += 1

    async def close(self):
        return None


def _install_safety_net(monkeypatch, task_module, *, module_status, session):
    enqueued: list[dict] = []

    class _FakeQueueService:
        def __init__(self, db):
            self.db = db

        async def recover_stale_running_tasks(self, timeout_seconds: int):
            return 0

        async def enqueue_refresh(
            self, *, trigger_type, pipeline_name, targets, context=None
        ):
            enqueued.append(
                {
                    "trigger_type": trigger_type,
                    "pipeline_name": pipeline_name,
                    "targets": list(targets),
                    "context": context,
                }
            )
            return type("Task", (), {"job_id": "refresh-safety-net-1"})()

    async def _fake_inspect_dashboard_assets(_db):
        return {
            "ready": module_status == "ready",
            "modules": {
                "business_overview": {
                    "status": module_status,
                    "core_missing_objects": [],
                }
            },
        }

    monkeypatch.setattr(task_module, "AsyncSessionLocal", lambda: session)
    monkeypatch.setattr(task_module, "RefreshQueueService", _FakeQueueService)
    monkeypatch.setattr(
        task_module, "inspect_dashboard_assets", _fake_inspect_dashboard_assets
    )
    return enqueued


@pytest.mark.asyncio
async def test_safety_net_does_not_enqueue_repair_for_refreshing_module(monkeypatch):
    """``refreshing`` 说明正有一趟刷新在跑 ⇒ 再排一次只会并发。"""
    from backend.tasks import refresh_queue_tasks as task_module

    session = _FakeSession()
    enqueued = _install_safety_net(
        monkeypatch, task_module, module_status="refreshing", session=session
    )

    result = await task_module._async_dashboard_refresh_safety_net()

    assert result["enqueued_repairs"] == 0
    assert enqueued == []


@pytest.mark.asyncio
async def test_safety_net_enqueues_repair_for_drifted_module(monkeypatch):
    """``drift`` 是可自愈状态（对象缺失 ⇒ 修复任务会用资产文件建回来）。"""
    from backend.tasks import refresh_queue_tasks as task_module

    session = _FakeSession()
    enqueued = _install_safety_net(
        monkeypatch, task_module, module_status="drift", session=session
    )

    result = await task_module._async_dashboard_refresh_safety_net()

    assert result["enqueued_repairs"] == 1
    assert enqueued[0]["pipeline_name"] == "dashboard_safety_net_repair"


@pytest.mark.asyncio
async def test_safety_net_circuit_breaks_after_repeated_failures(monkeypatch):
    """连续失败到阈值 ⇒ 熔断（暂停自动重试，等人工介入）。"""
    from backend.tasks import refresh_queue_tasks as task_module

    session = _FakeSession(
        repair_rows=[
            {"status": "failed", "created_at": None, "last_error": "boom"},
            {"status": "failed", "created_at": None, "last_error": "boom"},
            {"status": "failed", "created_at": None, "last_error": "boom"},
        ]
    )
    queue_service = _install_safety_net(
        monkeypatch, task_module, module_status="drift", session=session
    )

    result = await task_module._async_dashboard_refresh_safety_net()

    assert result["enqueued_repairs"] == 0
    assert result["circuit_open_modules"] == ["business_overview"]
    assert queue_service == []


@pytest.mark.asyncio
async def test_safety_net_resumes_after_a_successful_repair(monkeypatch):
    """成功过一次 ⇒ 连续失败计数归零 ⇒ 熔断自动解除。"""
    from backend.tasks import refresh_queue_tasks as task_module

    session = _FakeSession(
        repair_rows=[
            {"status": "completed", "created_at": None, "last_error": None},
            {"status": "failed", "created_at": None, "last_error": "boom"},
            {"status": "failed", "created_at": None, "last_error": "boom"},
        ]
    )
    enqueued = _install_safety_net(
        monkeypatch, task_module, module_status="drift", session=session
    )

    result = await task_module._async_dashboard_refresh_safety_net()

    assert result["enqueued_repairs"] == 1
    assert result["circuit_open_modules"] == []
    assert len(enqueued) == 1


@pytest.mark.asyncio
async def test_safety_net_reaps_stale_running_refresh_runs(monkeypatch):
    """永久 ``running`` 的看板刷新 run 必须被回收。

    否则它会把模块**永久**钉在 ``refreshing``（页面永远挂提示）。
    """
    from backend.tasks import refresh_queue_tasks as task_module

    session = _FakeSession(reaped_ids=[1, 2, 3])
    _install_safety_net(
        monkeypatch, task_module, module_status="ready", session=session
    )

    result = await task_module._async_dashboard_refresh_safety_net()

    assert result["reaped_stale_refresh_runs"] == 3
    assert any(
        "UPDATE ops.pipeline_run_log" in sql for sql in session.executed
    )
