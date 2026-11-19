"""HR 员工生命周期 —— 在职状态与发钱边界的**唯一判定点**（SSOT）。

背景（2026-11-20 审视结论）
--------------------------
「员工状态」此前是一个自由字符串字段，同时兼职三件事：

1. 展示事实 —— 这个人还在不在职（列表、标签用）
2. 业务开关 —— 这个人能不能发工资（薪资链路用）
3. 软删除标记 —— 这条档案要不要继续出现在列表里

三件事的规则本不相同，第 2 件事的真实边界其实是**时间**（这个人最后拿到哪个月的钱），
不是状态。于是现状同时踩了两个方向的错：

* **误伤**：员工离职当月的加班费 / 奖金录不进去
  （``_employee_identity_allows_salary`` 一刀切要求 ``status == 'active'``）
* **漏发**：离职之后仍可能被生成新的工资单（没有月份边界）

本模块把这三件事拆成三个**互不相干**的正交概念，并成为它们唯一的判定入口：

===================  ==========================================  ====================
概念                 字段                                        业务含义
===================  ==========================================  ====================
用工身份             ``employee_identity_type``                 visitor（访客）/ employee（正式员工）
在职状态             ``status``                                  active / probation / leave / inactive
发钱边界             ``last_payroll_month``                     最后可结算的工资月；``None`` = 无上限
===================  ==========================================  ====================

判定规则（唯一口径）
--------------------
* **在职**（active）：正常发薪，无上限
* **试用期**（probation）：**不发薪**（沿用现状口径），可参与考核
* **停薪留职**（leave）：不发薪
* **已离职**（inactive）：**只允许结算到 ``last_payroll_month`` 为止**；
  ``last_payroll_month`` 为空表示「没有可结算的月份」⇒ 任何月份都不生成
* **确认工资单 / 标记已发放**：**任何状态都允许** —— 离职结算是生命线，绝不能拦

固定薪资（``SalaryStructure``）另有一条规则：**只允许在职时修改**，
离职后冻结（离职结算改用月度人工录入，不动固定薪资）。

为什么要单独建这个模块
----------------------
它是「同一个业务事实只允许有一处真相」的落点：后端所有薪资相关判定
（生成 / 录入 / 修改 / 确认 / 发放）都必须调用这里的函数，
不允许任何一处自己写 ``status == 'active'``。

不在这里做的事
--------------
* 不改权限模型
* 不改结算口径（利润基数 × 可分配率 × 归属提成比 × 结算系数）
* 不改历史留痕策略
"""

from __future__ import annotations

from typing import Any, Optional

# ---------------------------------------------------------------------------
# 词表（唯一真源；后端枚举 + 前端 constants/hr.js 必须与之一致）
# ---------------------------------------------------------------------------

#: 在职状态词表。``status`` 字段的合法取值。
EMPLOYEE_STATUS_VOCABULARY: tuple[str, ...] = (
    "active",  # 在职
    "probation",  # 试用期（不发薪）
    "leave",  # 停薪留职（不发薪）
    "inactive",  # 已离职（只结算到最后发薪月）
)

#: 用工身份词表。
EMPLOYEE_IDENTITY_VOCABULARY: tuple[str, ...] = ("visitor", "employee")

#: 工资单状态词表。``void`` = 已作废（测试数据 / 业务作废），行保留、不可发放。
#:
#: ⚠️ ``approved`` 是**历史遗留值**：老版本工资单路由写过它，当前代码已不再产生，
#: 但环境里可能仍有残留的历史行 ⇒ 保留在词表里（只读展示 + 仍按锁定处理），
#: 前端 ``constants/hr.js`` 必须与本词表**逐值一致**（否则页面显示会与后端打架）。
PAYROLL_STATUS_VOCABULARY: tuple[str, ...] = (
    "draft",
    "confirmed",
    "paid",
    "void",
    "approved",
)

#: 已锁定的工资单状态：不可再改内容。
#:
#: ⚠️ ``approved`` 是**历史遗留值**：老版本工资单路由写过它（2026-11-05 口径收敛之前），
#: 当前词表里已无此值、现网代码也不会再写入它。但**仍然按「已锁定」处理** ——
#: 宁可多锁，不可漏锁：若某个环境残留了 ``approved`` 的历史工资单，
#: 漏掉它会让那个月被整月重算**静默改掉**用户以为锁住的工资单
#: （2026-11-05 那次口径收敛事故的同款后果）。
#:
#: ⇒ 锁定集合 ⊆ 工资单词表；作废 ``void`` **不在**锁定集合里
#:    （作废只冻结这一张单，不该把整个月钉死）。
PAYROLL_LOCKED_STATUSES: tuple[str, ...] = ("approved", "confirmed", "paid")

#: 已作废的工资单状态。
#:
#: ⚠️ **作废 ≠ 锁定**：作废只冻结「这一张单」，**不锁住整个月** ——
#: 同月其他人的工资单照常重算、照常确认发放。若把 ``void`` 塞进锁定集合，
#: 一张作废单就会把整个月钉死（这正是要避免的连带伤害）。
PAYROLL_VOIDED_STATUSES: tuple[str, ...] = ("void",)


# ---------------------------------------------------------------------------
# 基础谓词
# ---------------------------------------------------------------------------


def employee_status(employee: Any) -> str:
    """取员工在职状态；档案缺失时按「在职」处理（与历史口径一致）。"""
    return str(getattr(employee, "status", None) or "active")


def employee_identity(employee: Any) -> str:
    """取员工用工身份；档案缺失时按「正式员工」处理（与历史口径一致）。"""
    return str(getattr(employee, "employee_identity_type", None) or "employee")


def last_payroll_month(employee: Any) -> Optional[str]:
    """取发钱边界（最后可结算的工资月，YYYY-MM）；``None`` = 无上限或无可结算月份。"""
    value = getattr(employee, "last_payroll_month", None)
    if not value:
        return None
    return str(value).strip() or None


def is_payroll_voided(record: Any) -> bool:
    """工资单是否已作废。"""
    return str(getattr(record, "status", None) or "") in PAYROLL_VOIDED_STATUSES


def is_payroll_locked(record_or_status: Any) -> bool:
    """工资单是否已锁定（已确认 / 已发放，含历史遗留的 ``approved``）—— 不可再改内容。"""
    status = getattr(record_or_status, "status", record_or_status)
    return str(status or "") in PAYROLL_LOCKED_STATUSES


def is_salary_employee(employee: Any) -> bool:
    """是否可以进入薪资链路（固定薪资、月度人工录入）。

    沿用历史口径：**只有正式身份 + 在职**。试用期与停薪留职不发薪。
    注意：已离职员工**不在这里被拦** —— 离职结算由
    :func:`is_payroll_month_allowed` 按月份判断。
    """
    return (
        employee_identity(employee) == "employee"
        and employee_status(employee) == "active"
    )


# ---------------------------------------------------------------------------
# 发钱边界的唯一判定
# ---------------------------------------------------------------------------


def is_payroll_month_allowed(employee: Any, year_month: str) -> bool:
    """这个人、这个月，能不能算工资 / 录工资。

    * 在职 → 允许（无上限）
    * 试用期 / 停薪留职 → 不允许（沿用现状：试用不发薪）
    * 已离职 → 仅当 ``year_month <= last_payroll_month`` 时允许
    * 已离职且 ``last_payroll_month`` 为空 → 一律不允许（没有可结算的月份）
    """
    month = str(year_month or "").strip()
    if not month:
        return False
    status = employee_status(employee)
    if status == "active":
        return True
    if status in {"probation", "leave"}:
        return False
    if status == "inactive":
        boundary = last_payroll_month(employee)
        if not boundary:
            return False
        return month <= boundary
    return False


def payroll_month_rejection_reason(employee: Any, year_month: str) -> str:
    """给出人话版的拒绝原因（前端直接展示）。"""
    status = employee_status(employee)
    if status == "probation":
        return "试用期员工暂不参与薪资核算，转正后从转正月份起算"
    if status == "leave":
        return "停薪留职期间不发放工资"
    if status == "inactive":
        boundary = last_payroll_month(employee)
        if not boundary:
            return "该员工已离职且没有可结算的工资月份"
        return f"该员工最后发薪月为 {boundary}，{year_month} 不在可结算范围内"
    return f"该员工当前状态（{status}）不允许结算 {year_month} 的工资"


def assert_payroll_month_allowed(employee: Any, year_month: str) -> None:
    """不可结算时抛 :class:`ValueError`（调用方转成 409）。"""
    if not is_payroll_month_allowed(employee, year_month):
        raise ValueError(payroll_month_rejection_reason(employee, year_month))


# ---------------------------------------------------------------------------
# 结构化展示信息（后端唯一一份标签定义）
# ---------------------------------------------------------------------------


def employee_status_label(status: Optional[str]) -> str:
    """在职状态的中文标签。"""
    mapping = {
        "active": "在职",
        "probation": "试用期",
        "leave": "停薪留职",
        "inactive": "已离职",
    }
    key = str(status or "active")
    return mapping.get(key, key)


def employee_identity_label(identity: Optional[str]) -> str:
    """用工身份的中文标签。"""
    mapping = {"visitor": "访客", "employee": "正式员工"}
    key = str(identity or "employee")
    return mapping.get(key, key)


def payroll_status_label(status: Optional[str]) -> str:
    """工资单状态的中文标签。"""
    mapping = {
        "draft": "草稿",
        "confirmed": "已确认",
        "paid": "已发放",
        "void": "已作废",
        # 历史遗留值：老版本工资单用过 ``approved``，当前词表已不再产生，
        # 但仍要有中文名 —— 否则页面上会直接甩出英文原值。
        "approved": "已审批（历史状态）",
    }
    key = str(status or "")
    return mapping.get(key, key)
