"""下线跟投收益模块：删除跟投相关的 4 张业务表。

背景
----
「跟投收益」模块（店铺跟投本金 → 月度跟投结算 → 月结跟投明细）没有真实业务
投资人：业务已确认整个模块可以删除。跟投的代码（service / router / schema）、
权限点 ``my-follow-investment-income``、投资人角色 ``investor`` 与审批模板
``follow_investment_settlement_approval`` 已在本批次一并下线。

本迁移做一件事
--------------
删掉跟投模块留下的 4 张表：

* ``finance.monthly_profit_follow_details``（月结跟投收益明细）
* ``finance.follow_investment_details``（店铺月度跟投结算明细）
* ``finance.follow_investment_settlements``（店铺月度跟投结算头）
* ``finance.follow_investments``（店铺跟投本金）

删表顺序（有讲究，不能乱）
--------------------------
``finance.monthly_profit_follow_details.source_settlement_id`` 有指向
``finance.follow_investment_settlements.id`` 的外键，且**没有 ondelete**
（实测本地库 ``pg_constraint.confdeltype = 'a'``，即 NO ACTION）⇒ 必须**先删前者**，
否则会直接撞外键。其余三张表之间只有 ``follow_investment_details →
follow_investment_settlements`` 这一条带 ``ON DELETE CASCADE`` 的外键 ⇒
子表先删、父表后删即可。

数据说明
--------
生产/本地库上这 4 张表**各有 1 行数据**（本地库 2026-11-21 实测），且跟投本金
记录 ``finance.follow_investments.remark = 'codex real-data regression sample'``
—— 这是**回归测试样本数据，不是真实投资人记录**（业务已确认没有真实跟投投资人）
⇒ 随模块下线一并清除，不做数据迁移、不做留痕表。

⚠️ 不可逆
--------
drop 掉的表与其中的样本数据**无法**通过 downgrade 找回：downgrade 只重建
**空表结构**（保证 schema 可回滚、后续迁移仍能跑通），不重建样本数据
（把样本行塞回库里比留着空表更糟）。此做法沿用 ``20261240`` 的处理方式。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261241_drop_follow_investment"
down_revision = "current_schema_20261240_hr_employee_lifecycle"
branch_labels = None
depends_on = None


FINANCE_SCHEMA = "finance"

#: 被删除的表 —— **按删除顺序排列**（子表在前、父表在后）。
#:
#: ``monthly_profit_follow_details`` 必须排第一：它的 ``source_settlement_id``
#: 外键指向 ``follow_investment_settlements`` 且没有 ondelete ⇒ 先删它才不撞外键。
DROPPED_TABLES = (
    "monthly_profit_follow_details",
    "follow_investment_details",
    "follow_investment_settlements",
    "follow_investments",
)

#: downgrade 时重建的空表 DDL —— **按创建顺序排列**（父表在前、子表在后）。
#:
#: 字段、默认值、约束、索引与被删除前完全一致（取自本地库实测 DDL，
#: 并与 ``20260805_current_schema_baseline.py`` 的建表语句对齐）。
RECREATE_TABLE_STATEMENTS: dict[str, list[str]] = {
    "follow_investments": [
        "CREATE TABLE finance.follow_investments ("
        "id integer NOT NULL, "
        "investor_user_id bigint NOT NULL, "
        "platform_code character varying(32) NOT NULL, "
        "shop_id character varying(64) NOT NULL, "
        "contribution_amount double precision DEFAULT 0 NOT NULL, "
        "contribution_date date NOT NULL, "
        "withdraw_date date, "
        "capital_type character varying(32) "
        "DEFAULT 'working_capital'::character varying NOT NULL, "
        "status character varying(32) DEFAULT 'active'::character varying NOT NULL, "
        "remark text, "
        "created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL, "
        "updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        "CREATE SEQUENCE finance.follow_investments_id_seq "
        "AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
        "ALTER SEQUENCE finance.follow_investments_id_seq "
        "OWNED BY finance.follow_investments.id",
        "ALTER TABLE ONLY finance.follow_investments ALTER COLUMN id "
        "SET DEFAULT nextval('finance.follow_investments_id_seq'::regclass)",
        "ALTER TABLE ONLY finance.follow_investments "
        "ADD CONSTRAINT follow_investments_pkey PRIMARY KEY (id)",
        "CREATE INDEX ix_follow_investments_user "
        "ON finance.follow_investments USING btree (investor_user_id, status)",
        "CREATE INDEX ix_follow_investments_shop "
        "ON finance.follow_investments "
        "USING btree (platform_code, shop_id, contribution_date)",
        "ALTER TABLE ONLY finance.follow_investments "
        "ADD CONSTRAINT follow_investments_investor_user_id_fkey "
        "FOREIGN KEY (investor_user_id) REFERENCES core.dim_users(user_id)",
    ],
    "follow_investment_settlements": [
        "CREATE TABLE finance.follow_investment_settlements ("
        "id integer NOT NULL, "
        "profit_basis_id integer NOT NULL, "
        "period_month character varying(16) NOT NULL, "
        "platform_code character varying(32) NOT NULL, "
        "shop_id character varying(64) NOT NULL, "
        "profit_basis_amount double precision DEFAULT 0 NOT NULL, "
        "distribution_ratio double precision DEFAULT 0 NOT NULL, "
        "distributable_amount double precision DEFAULT 0 NOT NULL, "
        "status character varying(32) DEFAULT 'draft'::character varying NOT NULL, "
        "approved_by character varying(64), "
        "approved_at timestamp with time zone, "
        "paid_at timestamp with time zone, "
        "created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL, "
        "updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        "CREATE SEQUENCE finance.follow_investment_settlements_id_seq "
        "AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
        "ALTER SEQUENCE finance.follow_investment_settlements_id_seq "
        "OWNED BY finance.follow_investment_settlements.id",
        "ALTER TABLE ONLY finance.follow_investment_settlements ALTER COLUMN id "
        "SET DEFAULT nextval('finance.follow_investment_settlements_id_seq'::regclass)",
        "ALTER TABLE ONLY finance.follow_investment_settlements "
        "ADD CONSTRAINT follow_investment_settlements_pkey PRIMARY KEY (id)",
        "CREATE INDEX ix_follow_investment_settlements_period "
        "ON finance.follow_investment_settlements USING btree (period_month, status)",
        "CREATE INDEX ix_follow_investment_settlements_shop "
        "ON finance.follow_investment_settlements USING btree (platform_code, shop_id)",
        "ALTER TABLE ONLY finance.follow_investment_settlements "
        "ADD CONSTRAINT follow_investment_settlements_profit_basis_id_fkey "
        "FOREIGN KEY (profit_basis_id) REFERENCES finance.shop_profit_basis(id)",
    ],
    "follow_investment_details": [
        "CREATE TABLE finance.follow_investment_details ("
        "id integer NOT NULL, "
        "settlement_id integer NOT NULL, "
        "investor_user_id bigint NOT NULL, "
        "contribution_amount_snapshot double precision DEFAULT 0 NOT NULL, "
        "occupied_days integer DEFAULT 0 NOT NULL, "
        "weighted_capital double precision DEFAULT 0 NOT NULL, "
        "share_ratio double precision DEFAULT 0 NOT NULL, "
        "estimated_income double precision DEFAULT 0 NOT NULL, "
        "approved_income double precision DEFAULT 0 NOT NULL, "
        "paid_income double precision DEFAULT 0 NOT NULL, "
        "payment_status character varying(32) "
        "DEFAULT 'pending'::character varying NOT NULL, "
        "paid_at timestamp with time zone, "
        "created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL, "
        "updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        "CREATE SEQUENCE finance.follow_investment_details_id_seq "
        "AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
        "ALTER SEQUENCE finance.follow_investment_details_id_seq "
        "OWNED BY finance.follow_investment_details.id",
        "ALTER TABLE ONLY finance.follow_investment_details ALTER COLUMN id "
        "SET DEFAULT nextval('finance.follow_investment_details_id_seq'::regclass)",
        "ALTER TABLE ONLY finance.follow_investment_details "
        "ADD CONSTRAINT follow_investment_details_pkey PRIMARY KEY (id)",
        "CREATE INDEX ix_follow_investment_details_settlement "
        "ON finance.follow_investment_details USING btree (settlement_id)",
        "CREATE INDEX ix_follow_investment_details_user "
        "ON finance.follow_investment_details "
        "USING btree (investor_user_id, settlement_id)",
        "ALTER TABLE ONLY finance.follow_investment_details "
        "ADD CONSTRAINT follow_investment_details_settlement_id_fkey "
        "FOREIGN KEY (settlement_id) "
        "REFERENCES finance.follow_investment_settlements(id) ON DELETE CASCADE",
        "ALTER TABLE ONLY finance.follow_investment_details "
        "ADD CONSTRAINT follow_investment_details_investor_user_id_fkey "
        "FOREIGN KEY (investor_user_id) REFERENCES core.dim_users(user_id)",
    ],
    "monthly_profit_follow_details": [
        "CREATE TABLE finance.monthly_profit_follow_details ("
        "id integer NOT NULL, "
        "settlement_id integer NOT NULL, "
        "investor_user_id bigint, "
        "source_settlement_id integer, "
        "amount double precision DEFAULT 0 NOT NULL, "
        "status character varying(32) DEFAULT 'approved'::character varying NOT NULL, "
        "remark text, "
        "created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL, "
        "updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL)",
        "CREATE SEQUENCE finance.monthly_profit_follow_details_id_seq "
        "AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1",
        "ALTER SEQUENCE finance.monthly_profit_follow_details_id_seq "
        "OWNED BY finance.monthly_profit_follow_details.id",
        "ALTER TABLE ONLY finance.monthly_profit_follow_details ALTER COLUMN id "
        "SET DEFAULT nextval('finance.monthly_profit_follow_details_id_seq'::regclass)",
        "ALTER TABLE ONLY finance.monthly_profit_follow_details "
        "ADD CONSTRAINT monthly_profit_follow_details_pkey PRIMARY KEY (id)",
        "CREATE INDEX ix_monthly_profit_follow_details_settlement "
        "ON finance.monthly_profit_follow_details USING btree (settlement_id)",
        "ALTER TABLE ONLY finance.monthly_profit_follow_details "
        "ADD CONSTRAINT monthly_profit_follow_details_settlement_id_fkey "
        "FOREIGN KEY (settlement_id) "
        "REFERENCES finance.monthly_profit_settlements(id) ON DELETE CASCADE",
        "ALTER TABLE ONLY finance.monthly_profit_follow_details "
        "ADD CONSTRAINT monthly_profit_follow_details_investor_user_id_fkey "
        "FOREIGN KEY (investor_user_id) REFERENCES core.dim_users(user_id)",
        "ALTER TABLE ONLY finance.monthly_profit_follow_details "
        "ADD CONSTRAINT monthly_profit_follow_details_source_settlement_id_fkey "
        "FOREIGN KEY (source_settlement_id) "
        "REFERENCES finance.follow_investment_settlements(id)",
    ],
}


def _has_table(schema: str, table: str) -> bool:
    """表是否已存在（downgrade 幂等的前提）。"""
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table, schema=schema)


def upgrade() -> None:
    """删除跟投模块的 4 张表（子表在前、父表在后，避免撞外键）。"""
    bind = op.get_bind()
    for table in DROPPED_TABLES:
        # ⚠️ 不用 CASCADE：万一还有意料之外的引用，宁可报错停下，也不静默删掉别的表。
        bind.execute(sa.text(f"DROP TABLE IF EXISTS {FINANCE_SCHEMA}.{table}"))


def downgrade() -> None:
    """重建这 4 张**空表**（结构可回滚；样本数据不可回滚，见文件头说明）。"""
    bind = op.get_bind()
    for table, statements in RECREATE_TABLE_STATEMENTS.items():
        if _has_table(FINANCE_SCHEMA, table):
            continue
        for statement in statements:
            bind.execute(sa.text(statement))
