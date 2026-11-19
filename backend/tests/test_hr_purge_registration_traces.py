"""演练：清残留测试账号时，**只**删它自己的注册审批链痕迹（2026-11-20 生产实测补做）。

背景（v7.35.0 首次部署被这条挡住）
--------------------------------
生产部署时迁移在删 347 个残留测试账号之前停住了，报：
「残留测试账号仍被业务表仍被引用，拒绝删除：``core.employee_task_logs.actor_user_id``（16 行）；
``core.employee_tasks.created_by``（16 行）；``public.approval_action_logs.actor_user_id``（16 行）；
``public.approval_instances.applicant_user_id``（16 行）」。

生产只读核对查清了：那 16 个账号（``user_id`` 371~390，全是 ``ratelimit_test_`` /
``approval_workflow_`` / ``approve_test_`` 这类）**走过注册审批**，于是留下
「注册审批链」五张表上的痕迹。它们**只**记录「这个账号存在过、注册过、被拒过」，
不是业务记录 ⇒ 应当与账号一起清；但**必须证明这一点**才能删。

本文件就是那道**证明**，跑在隔离临时库上：

1. 复刻生产形状（测试账号走注册审批 + 管理员也在同一个审批实例上留了 ``reject`` 动作）
   ⇒ 迁移必须成功，且**只**删测试账号自己的痕迹，管理员的行一根不动；
2. 反向用例：测试账号创建了一个**不属于它自己注册审批**的待办
   ⇒ 迁移必须**报错停下**、且**什么都没删**（失败关闭，不误伤业务数据）。

⚠️ 需要真实 PostgreSQL；没有可达库时**跳过**（不制造环境性红）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from backend.utils.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CURRENT_CHAIN_CONFIG = "alembic-current.ini"
BASELINE_REVISION = "current_schema_20260805"
PREV_REVISION = "current_schema_20261239_cost_floor_caliber_closure"

#: 候选账号的用户名 —— 必须命中迁移的残留测试账号前缀。
TEST_USERNAME = "ratelimit_test_probe"
#: 真实账号 —— 不命中前缀、状态 active ⇒ 绝不能被当成候选清理掉。
ADMIN_USERNAME = "probe_admin_real"

REGISTRATION_TEMPLATE = "user_registration_approval"

#: 迁移链 ``20261116_add_tiktok_export_store_name_aliases`` 要求这 6 个 TikTok
#: 店铺账号**先存在**，否则 fail-closed 拒绝升级（与批次 9 演练同款前置）。
TIKTOK_EXPORT_ALIAS_ACCOUNTS = (
    ("DAONE Mall", "tiktok_sg_daone_mall_local", "SG"),
    ("DAWIE Mall", "tiktok_my_dawie_mall_local", "MY"),
    ("Explorers Mall", "tiktok_ph_explorers_mall_local", "PH"),
    ("Malaysia(Flora Mall)", "tiktok_my_flora_mall_local", "MY"),
    ("Philippines(DAJU Mall)", "tiktok_ph_daju_mall_local", "PH"),
    ("Singapore(HX Home)", "tiktok_sg_hx_home_local", "SG"),
)
REHEARSAL_MAIN_ACCOUNT_ID = "rehearsal-main-account"


def _seed(engine) -> None:
    """补上迁移链需要的种子数据（基线版本的 ``core.dim_platforms`` 只有 5 个列）。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO core.main_accounts (
                    platform, main_account_id, username, password_encrypted, main_account_name
                ) VALUES (
                    'tiktok', :main_account_id, 'rehearsal', 'x', 'Rehearsal Main Account'
                )
                """
            ),
            {"main_account_id": REHEARSAL_MAIN_ACCOUNT_ID},
        )
        for store_name, shop_account_id, shop_region in TIKTOK_EXPORT_ALIAS_ACCOUNTS:
            conn.execute(
                text(
                    """
                    INSERT INTO core.shop_accounts (
                        platform, shop_account_id, main_account_id, store_name,
                        shop_region, enabled, business_role
                    ) VALUES (
                        'tiktok', :shop_account_id, :main_account_id, :store_name,
                        :shop_region, TRUE, 'operating_store'
                    )
                    """
                ),
                {
                    "shop_account_id": shop_account_id,
                    "main_account_id": REHEARSAL_MAIN_ACCOUNT_ID,
                    "store_name": store_name,
                    "shop_region": shop_region,
                },
            )
        conn.execute(
            text(
                "INSERT INTO core.dim_platforms (platform_code, name, is_active) "
                "VALUES ('shopee','Shopee',TRUE), ('tiktok','TikTok',TRUE)"
            )
        )


def _run_alembic(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", CURRENT_CHAIN_CONFIG, *args],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=1800,
    )


@pytest.fixture(scope="module")
def admin_engine():
    """连到管理库（用来建/删临时库）。没有可达 PG 时**跳过**。"""
    try:
        settings = get_settings()
        base_url = make_url(settings.DATABASE_URL)
        engine = create_engine(
            base_url.set(database="postgres"),
            isolation_level="AUTOCOMMIT",
            future=True,
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - 环境性跳过
        pytest.skip("本地没有可达的 PostgreSQL，跳过迁移演练：{0}".format(exc))
    yield engine
    engine.dispose()


@pytest.fixture()
def rehearsal_db(admin_engine):
    """隔离临时库：升到本迁移的上一版，把种子数据留给用例自己写。"""
    settings = get_settings()
    base_url = make_url(settings.DATABASE_URL)
    database_name = "hr_purge_rehearsal_{0}".format(uuid.uuid4().hex[:10])
    temp_url = base_url.set(database=database_name).render_as_string(
        hide_password=False
    )
    env = os.environ.copy()
    env["DATABASE_URL"] = temp_url
    engine = create_engine(temp_url, future=True)
    try:
        with admin_engine.connect() as conn:
            conn.execute(
                text('DROP DATABASE IF EXISTS "{0}" WITH (FORCE)'.format(database_name))
            )
            conn.execute(text('CREATE DATABASE "{0}"'.format(database_name)))
        completed = _run_alembic(["upgrade", BASELINE_REVISION], env)
        assert completed.returncode == 0, completed.stderr
        _seed(engine)
        completed = _run_alembic(["upgrade", PREV_REVISION], env)
        assert completed.returncode == 0, completed.stderr
        yield engine, env
    finally:
        engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(
                text('DROP DATABASE IF EXISTS "{0}" WITH (FORCE)'.format(database_name))
            )


def _insert_account(engine, username: str, status: str, is_active: bool) -> int:
    with engine.begin() as conn:
        user_id = conn.execute(
            text(
                "INSERT INTO core.dim_users "
                "(username, email, full_name, password_hash, is_active, is_superuser, status) "
                "VALUES (:username, :email, :username, 'x', :is_active, false, :status) "
                "RETURNING user_id"
            ),
            {
                "username": username,
                "email": "{0}@probe.local".format(username),
                "is_active": is_active,
                "status": status,
            },
        ).scalar_one()
    return int(user_id)


def _insert_registration_chain(
    engine,
    applicant_user_id: int,
    actor_user_id: int,
    instance_status: str,
    action_type: str,
) -> None:
    """复刻生产形状：注册审批实例 + 动作日志 + 步骤 + 待办 + 待办日志。"""
    stamp = "20260514081310597282"
    approval_id = "approval:{0}:user:{1}:{2}".format(
        REGISTRATION_TEMPLATE, applicant_user_id, stamp
    )
    with engine.begin() as conn:
        instance_id = conn.execute(
            text(
                "INSERT INTO public.approval_instances "
                "(approval_id, template_code, applicant_user_id, business_key, status) "
                "VALUES (:approval_id, :template, :applicant, :business_key, :status) "
                "RETURNING id"
            ),
            {
                "approval_id": approval_id,
                "template": REGISTRATION_TEMPLATE,
                "applicant": applicant_user_id,
                "business_key": "user:{0}".format(applicant_user_id),
                "status": instance_status,
            },
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO public.approval_action_logs "
                "(approval_pk, actor_user_id, action_type) "
                "VALUES (:pk, :actor, :action)"
            ),
            {"pk": instance_id, "actor": actor_user_id, "action": action_type},
        )
        conn.execute(
            text(
                "INSERT INTO public.approval_steps "
                "(approval_pk, step_order, approver_type, approver_user_id, status) "
                "VALUES (:pk, 1, 'user', :approver, :status)"
            ),
            {"pk": instance_id, "approver": actor_user_id, "status": instance_status},
        )
        task_pk = conn.execute(
            text(
                "INSERT INTO core.employee_tasks "
                "(task_id, task_type, task_category, title, status, owner_user_id, "
                " source_type, source_module, source_record_type, source_record_id, "
                " created_by) "
                "VALUES (:task_id, 'approval_pending', 'approval', "
                " 'Approval pending: User Registration Approval', 'pending', :owner, "
                " 'approval', 'approval-center', 'approval_instance', :source_record_id, "
                " :created_by) RETURNING id"
            ),
            {
                "task_id": "approval-task:approval:{0}:user:{1}:{2}:1".format(
                    REGISTRATION_TEMPLATE, applicant_user_id, stamp
                ),
                "owner": actor_user_id,
                "source_record_id": approval_id,
                "created_by": applicant_user_id,
            },
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO core.employee_task_logs (task_pk, actor_user_id, action, message) "
                "VALUES (:task_pk, :actor, 'created', 'task created')"
            ),
            {"task_pk": task_pk, "actor": applicant_user_id},
        )


def _counts(engine) -> dict:
    with engine.connect() as conn:
        return {
            "users": conn.execute(
                text("SELECT count(*) FROM core.dim_users")
            ).scalar_one(),
            "instances": conn.execute(
                text("SELECT count(*) FROM public.approval_instances")
            ).scalar_one(),
            "action_logs": conn.execute(
                text("SELECT count(*) FROM public.approval_action_logs")
            ).scalar_one(),
            "steps": conn.execute(
                text("SELECT count(*) FROM public.approval_steps")
            ).scalar_one(),
            "tasks": conn.execute(
                text("SELECT count(*) FROM core.employee_tasks")
            ).scalar_one(),
            "task_logs": conn.execute(
                text("SELECT count(*) FROM core.employee_task_logs")
            ).scalar_one(),
        }


def test_purge_removes_only_the_test_accounts_own_registration_traces(rehearsal_db):
    """正向：测试账号连同**它自己的**注册审批链痕迹一起清掉，真实账号的行一根不动。"""
    engine, env = rehearsal_db
    admin_id = _insert_account(engine, ADMIN_USERNAME, "active", True)
    test_id = _insert_account(engine, TEST_USERNAME, "rejected", False)

    # 测试账号自己的注册审批（动作人 = 它自己，状态 rejected）
    _insert_registration_chain(
        engine,
        applicant_user_id=test_id,
        actor_user_id=test_id,
        instance_status="rejected",
        action_type="submit",
    )
    # 真实账号自己的注册审批（**绝不能**被清）
    _insert_registration_chain(
        engine,
        applicant_user_id=admin_id,
        actor_user_id=admin_id,
        instance_status="approved",
        action_type="submit",
    )
    # 管理员在**测试账号**的审批实例上留下的 reject 动作（生产实测存在）
    with engine.begin() as conn:
        instance_id = conn.execute(
            text(
                "SELECT id FROM public.approval_instances WHERE applicant_user_id = :uid"
            ),
            {"uid": test_id},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO public.approval_action_logs "
                "(approval_pk, actor_user_id, action_type) VALUES (:pk, :actor, 'reject')"
            ),
            {"pk": instance_id, "actor": admin_id},
        )

    before = _counts(engine)
    assert before["instances"] == 2

    completed = _run_alembic(["upgrade", "head"], env)
    assert completed.returncode == 0, "迁移应当成功：\n{0}\n{1}".format(
        completed.stdout, completed.stderr
    )

    after = _counts(engine)
    # 测试账号没了，它的注册审批链也没了
    assert after["users"] == 1
    assert after["instances"] == 1, "真实账号的审批实例必须保留"
    assert after["action_logs"] == 1, "只剩真实账号自己那条 submit"
    assert after["steps"] == 1, "真实账号的审批步骤必须保留"
    assert after["tasks"] == 1, "真实账号的待办必须保留"
    assert after["task_logs"] == 1, "真实账号的待办日志必须保留"

    with engine.connect() as conn:
        remaining = (
            conn.execute(text("SELECT username FROM core.dim_users")).scalars().all()
        )
    assert remaining == [ADMIN_USERNAME]

    # 留痕表里有被清掉的账号身份
    with engine.connect() as conn:
        logged = (
            conn.execute(text("SELECT username FROM core.dim_user_purge_log"))
            .scalars()
            .all()
        )
    assert TEST_USERNAME in logged


def test_purge_refuses_when_a_test_account_owns_a_foreign_task(rehearsal_db):
    """反向（防误伤）：测试账号有**不属于它自己注册审批**的待办 ⇒ 迁移必须停下、什么都不删。"""
    engine, env = rehearsal_db
    admin_id = _insert_account(engine, ADMIN_USERNAME, "active", True)
    test_id = _insert_account(engine, TEST_USERNAME, "rejected", False)
    _insert_registration_chain(
        engine,
        applicant_user_id=test_id,
        actor_user_id=test_id,
        instance_status="rejected",
        action_type="submit",
    )
    # ⚠️ 一个**不属于**该账号注册审批的待办（业务待办）
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO core.employee_tasks "
                "(task_id, task_type, task_category, title, status, owner_user_id, "
                " source_type, source_module, created_by) "
                "VALUES ('probe:business-task:1', 'manual', 'manual', '业务待办', "
                " 'pending', :owner, 'manual', 'probe', :created_by)"
            ),
            {"owner": admin_id, "created_by": test_id},
        )

    before = _counts(engine)
    completed = _run_alembic(["upgrade", "head"], env)

    assert completed.returncode != 0, "迁移必须失败（不许默默删掉业务待办）"
    combined = "{0}\n{1}".format(completed.stdout, completed.stderr)
    assert "注册审批链痕迹核对失败" in combined, combined[-2000:]

    # 失败关闭：数据库里什么都没少
    after = _counts(engine)
    assert after == before, "迁移失败后必须原样回滚，不得留下半清理状态"
