"""「每月成本录入任务」与「归属角色」不得复活。

背景
----
2026-11-26 业务确认两件事：

1. **归属角色（supervisor / operator）退休** —— 它原本只支撑一件早期设计：
   把「每月成本录入」这个协同任务派给该店的"主管"。该设计过于早期，
   生产上最后一次生成是 2026-06-18（累计 2 条），此后归属表清空，
   每次录成本都会静默降级（异常被 catch 成 warning），**协作任务半年多没人收到**。
   ⇒ 业务拍板：**整条链路删除，避免遗留**。
2. 现实是**一家店可以同时有主管、多个总经理、操作员一起吃提成** ⇒
   "主管/操作员"这个二分法装不下现实，角色维度必须退休。

为什么需要守护
--------------
"删除"最常见的失败不是删不掉，而是**半年后又被谁加回来**：
后来的人看到"成本录入完不自动派任务了"，很可能顺手加回去；
看到 role 字段空着，也可能重新造一个角色下拉。
⇒ 删除必须钉在 CI 里，否则等于没删。

本守护断言（纯源码扫描，同步用例，可进根契约清单）
--------------------------------------------------
* 任务策略里不再有 ``monthly_cost_entry``；
* 派发链路里不再有 ``sync_monthly_cost_entry_task`` / ``resolve_shop_supervisor_user_id``；
* 成本录入接口本身**仍在**（删的是派任务，不是删功能）；
* 归属链路里不再有 ``supervisor`` 角色，也不再有按角色拆分的看板字段；
* 成本录入不再依赖"归属里有没有主管"（即 expense_management 不再引用该派发函数）。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_monthly_cost_task_policy_removed():
    """任务策略里不得再有 monthly_cost_entry。"""
    policy_source = _read("backend/services/employee_task_policy.py")
    assert (
        "monthly_cost_entry" not in policy_source
    ), "「每月成本录入」任务策略不得复活（该设计过于早期，业务已拍板删除）"


def test_supervisor_dispatch_chain_removed():
    """派发链路不得再有「找店主管」的两处函数。"""
    sources_source = _read("backend/services/employee_task_sources.py")
    assert (
        "resolve_shop_supervisor_user_id" not in sources_source
    ), "「按 supervisor 找店铺负责人」的函数不得复活"
    assert (
        "sync_monthly_cost_entry_task" not in sources_source
    ), "「每月成本录入任务」派发函数不得复活"


def test_expense_management_no_longer_dispatches_task():
    """成本录入不再触发任务派发，但录入功能本身必须还在。"""
    expense_source = _read("backend/domains/business/routers/expense_management.py")
    assert (
        "sync_monthly_cost_entry_task" not in expense_source
    ), "成本录入路径不得再派发「每月成本录入」任务"
    assert (
        "employee_task_sources" not in expense_source
    ), "成本录入路由不应再依赖 employee_task_sources 的任务派发"
    # 录入功能本身不许被顺手删掉：路由与成本写入仍必须在
    assert (
        "@router.post" in expense_source or "@router.put" in expense_source
    ), "费用管理路由被删了 —— 本次只允许删派任务，不允许删成本录入"


def test_assignment_role_retired_in_backend():
    """归属链路里不得再有 supervisor 角色与按角色拆分的看板字段。"""
    commission_source = _read("backend/domains/business/routers/hr_commission.py")
    assert "supervisor" not in commission_source, "归属路由里不得再出现 supervisor 角色"
    assert (
        "supervisor_profit" not in commission_source
    ), "看板不得再按 supervisor/operator 拆分（前端早已不消费该拆分）"
    assert (
        "operator_profit" not in commission_source
    ), "看板不得再按 supervisor/operator 拆分（前端早已不消费该拆分）"

    schema_source = _read("backend/schemas/hr.py")
    assert "role: Optional[str]" not in schema_source, "归属 schema 不得再有 role 字段"
