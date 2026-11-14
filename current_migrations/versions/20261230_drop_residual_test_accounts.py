"""删除两个**测试残留**主账号。

背景
----
账号管理页历史上被测试脚本写过两条脏数据：

* ``shopee / accept_main_1775126941575`` —— 主账号名与用户名都是
  ``playwright_smoke_admin``（Playwright 冒烟测试留下的），**没有**店铺账号；
* ``验证码测试账号 / 验证码测试账号`` —— ``platform`` 字段本身填的是
  「验证码测试账号」（根本不是平台代码），是建号时把测试名填进了平台列。

两条都不对应任何真实业务账号，且**没有** profile 目录
（``profiles/`` 下不存在对应目录 ⇒ 没有登录态会丢）。

业务已确认删除（2026-11-14，Walter：「残留账号进行删除」）。

删什么
------
只删 ``core.main_accounts`` 里这两行。指向它们的
``core.shop_accounts`` / ``core.collection_configs`` /
``core.collection_config_templates`` / ``core.platform_shop_discoveries`` /
``core.shop_account_aliases`` / ``core.shop_account_capabilities`` /
``core.collection_config_shop_scopes`` 的外键**全部是 ``ON DELETE CASCADE``**
⇒ 关联行由数据库自动清理，不需要在这里逐张表删。

幂等
----
按 ``(platform, main_account_id)`` **精确匹配**（不按名字、不按模糊）⇒
行不存在就删 0 行，重复执行安全；也绝不会误伤别的账号。

不可逆
------
这是**数据删除**：原值一旦删掉就**无法恢复**（downgrade 不会重建它们 ——
重建等于把脏数据塞回库里）。downgrade 只做 schema 层面的空转并写明原因。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261230_drop_residual_test_accounts"
down_revision = "current_schema_20261229_template_format_signature"
branch_labels = None
depends_on = None


_SCHEMA = "core"
_TABLE = f"{_SCHEMA}.main_accounts"

#: 要删的主账号：``(platform, main_account_id)`` **精确**匹配。
#:
#: ⚠️ platform 也要一起匹配 —— ``验证码测试账号`` 这条的平台列填的就是
#: 「验证码测试账号」本身，只按 ID 匹配会误伤同名 ID 的正常账号。
_RESIDUAL_ACCOUNTS = (
    ("shopee", "accept_main_1775126941575"),
    ("验证码测试账号", "验证码测试账号"),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("main_accounts", schema=_SCHEMA):
        return

    for platform, account_id in _RESIDUAL_ACCOUNTS:
        bind.execute(
            sa.text(
                f"delete from {_TABLE} "
                "where platform = :platform and main_account_id = :account_id"
            ),
            {"platform": platform, "account_id": account_id},
        )


def downgrade() -> None:
    """**刻意不做任何事**。

    这是一次**数据删除**：原行已被物理删除，无法从任何地方恢复。
    把它们重建回来等于把测试脏数据重新塞回库里 —— 比留着空迁移更糟。
    真正的回退方式是**从备份恢复**（迁移前的备份由发版流程保证存在）。
    """
    return None
