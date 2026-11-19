"""契约守护：人力生命周期口径的**跨模块一致性**（2026-11-20）。

为什么要有这个文件
------------------
本次改造把「员工状态」拆成了三个互不相干的概念（用工身份 / 在职状态 / 发钱边界），
并落到 ``backend/services/hr_employee_lifecycle.py`` 这一个判定点上。
但**光有判定点不够** —— 真正的风险是「同一个业务事实，两处各写一份」：

* 前端 ``frontend/src/constants/hr.js`` 与后端词表各写一份 ⇒ 改了一边，页面显示就错；
* 「已锁定」集合在工资单服务、人力成本分摊、月结服务三处各判一次
  ⇒ 曾经出过「界面显示已锁定、后台却允许整月重算」的静默改账事故；
* 「作废」引入后，若它被当成「锁定」，一张作废单就会把**整个月**钉死；
* 若作废**不可撤销**，因为「一人一月只有一张工资单」，
  一次误作废就会让那个人那个月永远发不出钱。

本守护把上面这些**跨文件、跨语言**的约定钉死。全部是**纯源码断言**（不碰数据库），
所以可以进 CI 根契约清单，每次流水线都跑。

⚠️ 规则本身写在文件里等于没写 —— 所以本文件必须进 CI 清单，
   且每次改动相关源码后都要重新验证（见文件末尾的「自我入册」断言）。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Set

import pytest

from backend.services.hr_employee_lifecycle import (
    EMPLOYEE_IDENTITY_VOCABULARY,
    EMPLOYEE_STATUS_VOCABULARY,
    PAYROLL_LOCKED_STATUSES,
    PAYROLL_STATUS_VOCABULARY,
    PAYROLL_VOIDED_STATUSES,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SSOT_MODULE = PROJECT_ROOT / "backend" / "services" / "hr_employee_lifecycle.py"
LOCK_SERVICE = PROJECT_ROOT / "backend" / "services" / "payroll_period_lock_service.py"
GENERATION_SERVICE = (
    PROJECT_ROOT / "backend" / "services" / "payroll_generation_service.py"
)
HR_SALARY_ROUTER = (
    PROJECT_ROOT / "backend" / "domains" / "business" / "routers" / "hr_salary.py"
)
HR_EMPLOYEE_ROUTER = (
    PROJECT_ROOT / "backend" / "domains" / "business" / "routers" / "hr_employee.py"
)
USERS_ADMIN_ROUTER = (
    PROJECT_ROOT / "backend" / "domains" / "platform" / "routers" / "users_admin.py"
)
HR_SCHEMAS = PROJECT_ROOT / "backend" / "schemas" / "hr.py"
FRONTEND_CONSTANTS = PROJECT_ROOT / "frontend" / "src" / "constants" / "hr.js"
FRONTEND_EMPLOYEE_TAB = (
    PROJECT_ROOT
    / "frontend"
    / "src"
    / "domains"
    / "business"
    / "views"
    / "hr"
    / "EmployeeTab.vue"
)
FRONTEND_EMPLOYEE_SALARY = (
    PROJECT_ROOT
    / "frontend"
    / "src"
    / "domains"
    / "business"
    / "views"
    / "hr"
    / "EmployeeSalary.vue"
)
CI_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"

GUARD_RELATIVE = "backend/tests/test_hr_lifecycle_contract.py"


def _read(path: Path) -> str:
    assert path.exists(), "文件必须存在: {0}".format(path.relative_to(PROJECT_ROOT))
    return path.read_text(encoding="utf-8", errors="replace")


def _js_object(source: str, const_name: str) -> Dict[str, str]:
    """从前端常量文件里抽出 ``export const NAME = { ... }`` 的键值对。"""
    match = re.search(
        r"export const {0}\s*=\s*\{{(.*?)\}}".format(re.escape(const_name)),
        source,
        re.S,
    )
    assert match, "前端常量必须存在: {0}".format(const_name)
    return dict(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*'([^']*)'", match.group(1)))


# ---------------------------------------------------------------------------
# 1) 词表：前后端必须逐值一致
# ---------------------------------------------------------------------------


def test_frontend_and_backend_employee_status_vocabulary_match():
    """在职状态词表：前端 constants/hr.js 与后端 SSOT 必须逐值一致。"""
    labels = _js_object(_read(FRONTEND_CONSTANTS), "EMPLOYEE_STATUS_LABEL")
    assert set(labels) == set(
        EMPLOYEE_STATUS_VOCABULARY
    ), "在职状态词表前后端不一致: 前端 {0} / 后端 {1}".format(
        sorted(labels), sorted(EMPLOYEE_STATUS_VOCABULARY)
    )


def test_frontend_and_backend_identity_vocabulary_match():
    """用工身份词表：前端 constants/hr.js 与后端 SSOT 必须逐值一致。"""
    labels = _js_object(_read(FRONTEND_CONSTANTS), "EMPLOYEE_IDENTITY_LABEL")
    assert set(labels) == set(EMPLOYEE_IDENTITY_VOCABULARY)


def test_frontend_and_backend_payroll_vocabulary_match():
    """工资单词表：前端 constants/hr.js 与后端 SSOT 必须逐值一致。

    ⚠️ 后端的锁定集合里多了一个历史遗留值 ``approved``（不在词表内），
    但**词表**本身必须完全一致 —— 否则页面会把不存在的状态显示出来。
    """
    labels = _js_object(_read(FRONTEND_CONSTANTS), "PAYROLL_STATUS_LABEL")
    assert set(labels) == set(
        PAYROLL_STATUS_VOCABULARY
    ), "工资单词表前后端不一致: 前端 {0} / 后端 {1}".format(
        sorted(labels), sorted(PAYROLL_STATUS_VOCABULARY)
    )


def test_no_page_hardcodes_its_own_status_mapping():
    """页面不许自己写状态映射表 —— 只能走 ``constants/hr.js``。

    背景：改造前「薪资页」和「用户页」各写一份中文映射，薪资页还直接把英文
    ``inactive`` 直接甩到界面上 ⇒ 同一个状态两种说法。
    """
    for page in (FRONTEND_EMPLOYEE_TAB, FRONTEND_EMPLOYEE_SALARY):
        source = _read(page)
        assert not re.search(
            r"status\s*==\s*'active'\s*\?[^:]*:\s*'在", source
        ), "{0} 不应自己写状态中文映射".format(page.name)
        assert (
            "employeeStatusLabel(" in source or "payrollStatusLabel(" in source
        ), "{0} 应通过 constants/hr.js 渲染状态文案".format(page.name)


# ---------------------------------------------------------------------------
# 2) 锁定态：作废**不**锁月；历史遗留 approved 仍按锁定处理
# ---------------------------------------------------------------------------


def test_void_is_not_a_locked_status():
    """作废 ≠ 锁定。

    ⚠️ 若把 ``void`` 塞进锁定集合，一张作废单就会把**整个月**钉死
    （同月其他人的工资单再也重算不了）—— 这正是要避免的连带伤害。
    """
    assert "void" not in PAYROLL_LOCKED_STATUSES
    assert PAYROLL_VOIDED_STATUSES == ("void",)
    assert set(PAYROLL_LOCKED_STATUSES) & set(PAYROLL_VOIDED_STATUSES) == set()


def test_legacy_approved_payroll_status_stays_locked():
    """历史遗留的 ``approved`` 工资单仍按「已锁定」处理。

    老版本工资单路由写过 ``approved``；现网代码不再写入，但若某环境残留，
    漏掉它会让那个月被整月重算**静默改掉**用户以为锁住的工资单。
    ⇒ 宁可多锁，不可漏锁。

    它仍然留在词表里（只读展示 + 按锁定处理），但**不是**可写入的新状态 ——
    写入口只有 draft / confirmed / paid / void。
    """
    assert "approved" in PAYROLL_LOCKED_STATUSES
    assert "approved" in PAYROLL_STATUS_VOCABULARY
    assert set(PAYROLL_LOCKED_STATUSES) <= set(
        PAYROLL_STATUS_VOCABULARY
    ), "锁定集合必须是词表的子集"

    lock_source = _read(LOCK_SERVICE)
    assert (
        "from backend.services.hr_employee_lifecycle import PAYROLL_LOCKED_STATUSES"
        in (lock_source)
    ), "锁定集合必须转发 SSOT，不许就地写一份字面量"

    salary_source = _read(HR_SALARY_ROUTER)
    assert (
        'PayrollRecord.status.in_(("confirmed", "paid"))' not in salary_source
    ), "薪资路由不许硬编码锁定集合字面量，必须引用 SSOT 常量"


def test_generation_service_skips_void_records_instead_of_rewriting_them():
    """刷新工资单时，已作废的单必须被**跳过**，不得被改写金额。

    背景：``(employee_code, year_month)`` 上有唯一索引 ⇒ 一人一月只有一张工资单。
    作废单占着坑位，所以刷新既不能改写它，也不能新建替代单。
    """
    source = _read(GENERATION_SERVICE)
    assert "is_payroll_voided" in source, "生成服务必须识别作废工资单"
    assert (
        "void_conflicts" in source and "void_conflict_details" in source
    ), "生成服务必须把「因作废而跳过」单独报出来，不能混进锁定冲突"


# ---------------------------------------------------------------------------
# 3) 作废可进可出：作废端点 + 撤销作废端点
# ---------------------------------------------------------------------------


def test_void_and_unvoid_endpoints_both_exist():
    """作废与**撤销作废**必须成对存在。

    没有撤销作废 ⇒ 误作废一次，那个人那个月就永远发不出钱
    （唯一索引 ⇒ 建不出第二张工资单），而界面只说「已作废」，用户完全不知道
    这里是个死胡同。
    """
    source = _read(HR_SALARY_ROUTER)
    assert '"/payroll-records/{record_id}/void"' in source
    assert '"/payroll-records/{record_id}/unvoid"' in source
    assert 'action="void_payroll_record"' in source
    assert 'action="unvoid_payroll_record"' in source


def test_unvoid_restores_draft_and_clears_void_trail():
    """撤销作废 = 恢复成草稿，并清空作废留痕（审计日志里保留全过程）。"""
    source = _read(HR_SALARY_ROUTER)
    unvoid_body = source.split('"/payroll-records/{record_id}/unvoid"', 1)[1]
    unvoid_body = unvoid_body.split("@router.", 1)[0]
    assert 'record.status = "draft"' in unvoid_body
    assert "record.void_reason = None" in unvoid_body
    assert "record.voided_at = None" in unvoid_body
    assert "record.voided_by = None" in unvoid_body


def test_void_trail_is_part_of_the_payroll_response_contract():
    """作废留痕字段必须在正式契约里（``backend/schemas/hr.py``），不许临时拼。"""
    source = _read(HR_SCHEMAS)
    assert "void_reason" in source
    assert "voided_at" in source
    assert "voided_by" in source
    assert "class PayrollRecordVoidRequest" in source
    assert "class PayrollRecordUnvoidRequest" in source


def test_frontend_exposes_void_and_unvoid_actions():
    """薪资页必须同时提供「作废」与「撤销作废」两个入口。"""
    source = _read(FRONTEND_EMPLOYEE_SALARY)
    assert "voidPayroll" in source
    assert "unvoidPayroll" in source
    assert "api.voidHrPayrollRecord" in source
    assert "api.unvoidHrPayrollRecord" in source


# ---------------------------------------------------------------------------
# 4) 离职结算：删除守卫不许连历史一起删
# ---------------------------------------------------------------------------


def test_delete_employee_guard_only_blocks_future_active_assignments():
    """删除员工只拦「未来仍有 active 归属」，历史归属保留。

    背景：改造前守卫不分月、不分状态地查全量归属 ⇒ 叶大望（110 条归属）这类
    人根本删不掉；而保留历史归属恰恰是「这个人的业绩归哪个店」的唯一凭据。
    """
    source = _read(HR_EMPLOYEE_ROUTER)
    guard = source.split("async def delete_employee", 1)
    assert len(guard) == 2, "hr_employee.py 必须仍有 delete_employee 端点"
    body = guard[1].split("@router.", 1)[0]
    assert (
        "last_payroll_month" in body or "year_month" in body
    ), "删除守卫必须按月份判断，只拦未来的 active 归属"


# ---------------------------------------------------------------------------
# 5) 账号绑定：冲突必须点名占用者，绝不静默覆盖
# ---------------------------------------------------------------------------


def test_binding_conflict_names_the_occupying_account():
    """员工已被别人绑定时，必须点名占用者，绝不静默覆盖。"""
    source = _read(USERS_ADMIN_ROUTER)
    assert (
        "occupied_by_departed_employee" in source
    ), "未绑定账号接口必须报告「被已离职员工占着」的账号"
    assert "blocked_by_employee" in source
    assert "请先解除关联" in source, "绑定冲突必须给出可执行的下一步提示"


def test_frontend_keeps_the_top_level_occupied_accounts_key():
    """前端 API 层不许把后端的顶层 ``occupied_by_departed_employee`` 丢掉。

    背景：该键在响应信封的**顶层**，不在 ``data`` 里；只取 ``data`` 会静默丢字段
    ⇒ 页面拿不到「哪些号要处理」的清单，且没有任何报错。
    """
    source = _read(PROJECT_ROOT / "frontend" / "src" / "api" / "users.js")
    unlinked = source.split("getUnlinkedUsers", 1)[1]
    unlinked = unlinked.split("},", 1)[0]
    assert (
        "res?.data ?? res" not in unlinked
    ), "getUnlinkedUsers 只取 data 会丢掉顶层键 occupied_by_departed_employee"
    assert "occupied_by_departed_employee" in source


# ---------------------------------------------------------------------------
# 6) 自我入册：没人调用的守护不是守护
# ---------------------------------------------------------------------------


def test_guard_itself_is_in_ci_root_contract_list():
    """本守护必须进 CI 根契约清单，否则「守着一条规则，但从不被执行」。"""
    ci_text = _read(CI_WORKFLOW)
    assert (
        GUARD_RELATIVE in ci_text
    ), "{0} 不在 CI 根契约清单里 ⇒ 这份守护在 CI 上不会跑".format(GUARD_RELATIVE)


def test_ssot_module_is_the_single_source_for_the_vocabularies():
    """三套词表必须只在 SSOT 模块里定义一次。

    背景：本次改造之前，「在职 / 可发薪 / 软删除」三个判断都挂在同一个自由
    字符串 ``status`` 上，且各处各写各的 ⇒ 同一个状态在三个地方有三种含义。
    """
    source = _read(SSOT_MODULE)
    for name in (
        "EMPLOYEE_STATUS_VOCABULARY",
        "EMPLOYEE_IDENTITY_VOCABULARY",
        "PAYROLL_STATUS_VOCABULARY",
    ):
        assert (
            source.count("{0}: tuple[str, ...]".format(name)) == 1
        ), "{0} 必须在 SSOT 模块里只定义一次".format(name)

    other_sources: Dict[str, str] = {
        "backend/schemas/hr.py": _read(HR_SCHEMAS),
        "frontend/src/constants/hr.js": _read(FRONTEND_CONSTANTS),
    }
    forbidden: Set[str] = {
        "'active'",
        "'probation'",
        "'inactive'",
        "'visitor'",
    }
    for name, text in other_sources.items():
        for literal in forbidden:
            # 允许出现在「引用 SSOT 常量」的注释/导入语境之外的**定义**位置
            assert not re.search(
                r"(STATUS|IDENTITY)_(VOCABULARY|LABEL)\s*[:=][^=]*=\s*\{{[^}}]*"
                + re.escape(literal),
                text,
            ), "{0} 不许自己定义状态词表字面量 {1}".format(name, literal)
