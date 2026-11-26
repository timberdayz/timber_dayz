"""访问权限角色体系不许被「归属角色退休」误伤。

背景
----
系统里有**两套都叫「角色」**的东西，中文名还几乎撞车：

* **访问权限角色**（admin 管理员 / manager **主管** / operator **操作员** / finance 财务）
  —— 决定**谁能登录系统、能看到哪些页面、能不能改配置**；
* **归属角色**（``a_class.employee_shop_assignments.role`` = supervisor / operator）
  —— 决定某人在某家店拿提成时被归成哪一类，**2026-11-26 已整条退休**。

两者的中文名撞车（manager 叫"主管"、operator 叫"操作员"）⇒
清理归属角色时，最危险的误伤就是**把访问权限体系一起删掉**：
那会让所有人瞬间失去（或获得）页面访问权。

本守护把访问权限体系钉死
------------------------
它是"防误删"守护，断言的是**现状必须保持**（不是"某功能还没做"）：

1. 后端 ``core.dim_users`` ↔ ``DimRole`` 的多对多角色关系仍在；
2. 前端 ``rolePermissions.js`` 的四个访问角色（admin/manager/operator/finance）仍在；
3. 前端 ``authRoles.js`` 的角色归一（含中文名映射）仍在；
4. 后端鉴权依赖 ``require_admin`` / ``get_current_user`` 仍在；
5. 归属侧的角色已经退休（``supervisor`` 不再出现在归属相关代码里）。
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_dim_users_keeps_role_relationship():
    """账号与角色是多对多关系，访问权限体系不可动。"""
    schema_source = _read("modules/core/db/schema_parts/business.py")
    assert 'roles = relationship("DimRole"' in schema_source, (
        "core.dim_users 的 roles 关系（账号 ↔ 角色）被删了 —— "
        "访问权限体系不可被归属角色退休误伤"
    )
    assert "user_roles" in schema_source, "账号-角色关联表 user_roles 不见了"


def test_frontend_access_roles_still_configured():
    """前端四个访问角色必须齐全。"""
    role_config = _read("frontend/src/config/rolePermissions.js")
    assert (
        "export const ROLE_CONFIG" in role_config
    ), "frontend/src/config/rolePermissions.js 的 ROLE_CONFIG 不见了"
    for role_code in ("admin", "manager", "operator", "finance"):
        assert f"{role_code}: {{" in role_config, f"访问角色 {role_code} 不见了"


def test_frontend_role_normalisation_kept():
    """角色归一（含中文名映射）必须保留。"""
    auth_roles = _read("frontend/src/utils/authRoles.js")
    assert (
        "ROLE_ALIASES" in auth_roles or "normalizeRoleCode" in auth_roles
    ), "frontend/src/utils/authRoles.js 的角色归一逻辑不见了"


def test_backend_auth_dependencies_kept():
    """后端鉴权依赖必须保留。"""
    auth_source = _read("backend/dependencies/auth.py")
    assert "require_admin" in auth_source, "require_admin 鉴权依赖不见了"
    assert "get_current_user" in auth_source, "get_current_user 鉴权依赖不见了"


def test_assignment_role_is_retired():
    """归属角色已退休：supervisor 不得再出现在归属链路里。"""
    for relative in (
        "backend/services/employee_task_sources.py",
        "backend/services/employee_task_policy.py",
        "backend/domains/business/routers/hr_commission.py",
        "backend/schemas/hr.py",
    ):
        source = _read(relative)
        assert (
            "supervisor" not in source
        ), f"{relative} 里仍然存在 supervisor —— 归属角色应当已整条退休"
