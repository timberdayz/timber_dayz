"""下线月度利润结算的旧快照结构：删除 5 张停写快照表 + 9 个废弃列。

背景
----
「月度利润结算中心」已改造成**只读的月度利润看板**：不再自算金额、不再审批、
不再冻结快照。代码侧（service / router / schema）的快照读写已在前一批下线，
但库里还留着「代码已经不再写、表还在」的遗留结构 —— 本迁移把它们删干净。

本迁移做两件事
--------------
1. 删掉 5 张停写快照表（都在 ``finance`` schema）：

   * ``finance.monthly_profit_personnel_details``（人员成本明细）
   * ``finance.monthly_profit_payroll_snapshots``（工资单快照）
   * ``finance.monthly_profit_shop_basis_snapshots``（店铺利润基数快照）
   * ``finance.monthly_profit_employee_commission_snapshots``（员工提成快照）
   * ``finance.monthly_profit_employee_performance_snapshots``（员工绩效快照）

2. 删掉 ``finance.monthly_profit_settlements`` 上 9 个语义已废弃的列：

   * 预算制 6 个：``personnel_target_ratio`` / ``follow_target_ratio`` /
     ``company_target_ratio`` / ``personnel_target_amount`` /
     ``follow_target_amount`` / ``company_target_amount``
   * 差异告警 2 个：``difference_amount`` / ``difference_ratio``
   * 跟投实际金额 1 个：``follow_actual_amount``

   业务已确认「预算在系统外人工做」「不审批」「不设目标额」⇒ 全部废弃。

保留什么
--------
``finance.monthly_profit_settlements`` **主表保留**（台账主记录 + 人工调整项
``finance.monthly_profit_adjustments`` 的外键目标）。以下列一律保留：
``id`` / ``period_month`` / ``net_profit_amount`` / ``personnel_actual_amount`` /
``company_actual_amount`` / ``adjustment_amount`` / ``status`` / ``locked_at`` /
``approved_by`` / ``approved_at`` / ``remark`` / ``created_at`` / ``updated_at``。
其中 ``status`` / ``approved_by`` / ``approved_at`` / ``locked_at`` 作为**历史台账
字段**保留 —— 库里有一条 2026-03 的 ``approved`` 记录要留痕。

删表顺序
--------
这 5 张表对外键的依赖**只有一个方向**：子表 → 父表
（``finance.monthly_profit_settlements``）。父表不删 ⇒ 5 张表之间没有任何外键
依赖 ⇒ 彼此的先后顺序不受约束；下面仍按「子表在前」的稳妥顺序排列。

⚠️ 不用 CASCADE
--------------
沿用 ``20261241`` 的口径：万一还有意料之外的引用，宁可报错停下，也不静默删掉
别的表。

⚠️ 不可逆
---------
drop 掉的表与其中的历史行**无法**通过 downgrade 找回：downgrade 只重建
**空表结构**（保证 schema 可回滚、后续迁移仍能跑通），不重建历史数据。
被删的 9 个列同理：downgrade 会按 ``double precision DEFAULT 0 NOT NULL``
原样加回，但列里的历史数值找不回来（且新加的列只能追加到表末尾，列顺序与
删除前不同 —— 列顺序无语义，不影响读写）。此做法沿用 ``20261241`` 的处理方式。

数据说明
--------
本地库 2026-11-21 实测：这 5 张表里留着 2026-03 月结批准时冻结的历史快照
（人员明细 0 行、工资单快照 9 行、店铺利润基数快照 51 行、员工提成快照 3 行、
员工绩效快照 3 行）。月结改为只读看板后**不再写入**、也不再读取 ⇒ 随结构
下线一并清除（月结历史台账已导出留存）。
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261242_drop_monthly_profit_snapshots"
down_revision = "current_schema_20261241_drop_follow_investment"
branch_labels = None
depends_on = None


FINANCE_SCHEMA = "finance"

#: 主台账表 —— **保留**，只删它上面 9 个废弃列。
SETTLEMENT_TABLE = "monthly_profit_settlements"

#: 被删除的表 —— **按删除顺序排列**（子表在前）。
#:
#: 这 5 张表都只指向 ``finance.monthly_profit_settlements``（子表 → 父表），
#: 父表不删 ⇒ 表与表之间没有外键依赖，顺序不受约束。
DROPPED_TABLES = (
    "monthly_profit_personnel_details",
    "monthly_profit_payroll_snapshots",
    "monthly_profit_shop_basis_snapshots",
    "monthly_profit_employee_commission_snapshots",
    "monthly_profit_employee_performance_snapshots",
)

#: ``finance.monthly_profit_settlements`` 上被删除的 9 个废弃列 —— **按删除顺序排列**。
#:
#: 预算制 6 个（3 个目标比例 + 3 个目标额）、差异告警 2 个、跟投实际金额 1 个。
#: 类型与默认值在被删前均为 ``double precision DEFAULT 0 NOT NULL``。
DROPPED_COLUMNS = (
    "personnel_target_ratio",
    "follow_target_ratio",
    "company_target_ratio",
    "personnel_target_amount",
    "follow_target_amount",
    "company_target_amount",
    "difference_amount",
    "difference_ratio",
    "follow_actual_amount",
)

#: downgrade 时加回那 9 个列用的类型与默认值 —— 与被删前**完全一致**。
COLUMN_DEFINITION = "double precision DEFAULT 0 NOT NULL"

#: downgrade 时重建的空表 DDL —— **按创建顺序排列**。
#:
#: 字段、默认值、约束、索引与被删除前完全一致（取自本地库实测 DDL，
#: 并与 ``20260805_current_schema_baseline.py`` 的建表语句逐句对齐）。
RECREATE_TABLE_STATEMENTS: dict[str, list[str]] = {
    "monthly_profit_personnel_details": [
        "CREATE TABLE finance.monthly_profit_personnel_details (\n    id integer NOT NULL,\n    settlement_id integer NOT NULL,\n    detail_type character varying(64) NOT NULL,\n    employee_code character varying(64),\n    platform_code character varying(32),\n    shop_id character varying(64),\n    source_module character varying(64),\n    source_record_id character varying(64),\n    amount double precision DEFAULT 0 NOT NULL,\n    remark text,\n    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL\n)",
        "CREATE SEQUENCE finance.monthly_profit_personnel_details_id_seq\n    AS integer\n    START WITH 1\n    INCREMENT BY 1\n    NO MINVALUE\n    NO MAXVALUE\n    CACHE 1",
        "ALTER SEQUENCE finance.monthly_profit_personnel_details_id_seq OWNED BY finance.monthly_profit_personnel_details.id",
        "ALTER TABLE ONLY finance.monthly_profit_personnel_details ALTER COLUMN id SET DEFAULT nextval('finance.monthly_profit_personnel_details_id_seq'::regclass)",
        "ALTER TABLE ONLY finance.monthly_profit_personnel_details\n    ADD CONSTRAINT monthly_profit_personnel_details_pkey PRIMARY KEY (id)",
        "CREATE INDEX ix_monthly_profit_personnel_details_settlement ON finance.monthly_profit_personnel_details USING btree (settlement_id)",
        "ALTER TABLE ONLY finance.monthly_profit_personnel_details\n    ADD CONSTRAINT monthly_profit_personnel_details_settlement_id_fkey FOREIGN KEY (settlement_id) REFERENCES finance.monthly_profit_settlements(id) ON DELETE CASCADE",
    ],
    "monthly_profit_payroll_snapshots": [
        "CREATE TABLE finance.monthly_profit_payroll_snapshots (\n    id integer NOT NULL,\n    settlement_id integer NOT NULL,\n    period_month character varying(16) NOT NULL,\n    snapshot_version integer DEFAULT 1 NOT NULL,\n    snapshot_status character varying(32) DEFAULT 'active'::character varying NOT NULL,\n    payroll_record_id bigint,\n    employee_code character varying(64) NOT NULL,\n    employee_name character varying(128),\n    base_salary numeric(15,2) DEFAULT 0 NOT NULL,\n    position_salary numeric(15,2) DEFAULT 0 NOT NULL,\n    performance_salary numeric(15,2) DEFAULT 0 NOT NULL,\n    overtime_pay numeric(15,2) DEFAULT 0 NOT NULL,\n    commission numeric(15,2) DEFAULT 0 NOT NULL,\n    allowances numeric(15,2) DEFAULT 0 NOT NULL,\n    bonus numeric(15,2) DEFAULT 0 NOT NULL,\n    gross_salary numeric(15,2) DEFAULT 0 NOT NULL,\n    social_insurance_personal numeric(15,2) DEFAULT 0 NOT NULL,\n    housing_fund_personal numeric(15,2) DEFAULT 0 NOT NULL,\n    income_tax numeric(15,2) DEFAULT 0 NOT NULL,\n    other_deductions numeric(15,2) DEFAULT 0 NOT NULL,\n    total_deductions numeric(15,2) DEFAULT 0 NOT NULL,\n    net_salary numeric(15,2) DEFAULT 0 NOT NULL,\n    social_insurance_company numeric(15,2) DEFAULT 0 NOT NULL,\n    housing_fund_company numeric(15,2) DEFAULT 0 NOT NULL,\n    total_cost numeric(15,2) DEFAULT 0 NOT NULL,\n    payroll_status character varying(32),\n    pay_date date,\n    remark text,\n    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n    created_by character varying(64)\n)",
        "CREATE SEQUENCE finance.monthly_profit_payroll_snapshots_id_seq\n    AS integer\n    START WITH 1\n    INCREMENT BY 1\n    NO MINVALUE\n    NO MAXVALUE\n    CACHE 1",
        "ALTER SEQUENCE finance.monthly_profit_payroll_snapshots_id_seq OWNED BY finance.monthly_profit_payroll_snapshots.id",
        "ALTER TABLE ONLY finance.monthly_profit_payroll_snapshots ALTER COLUMN id SET DEFAULT nextval('finance.monthly_profit_payroll_snapshots_id_seq'::regclass)",
        "ALTER TABLE ONLY finance.monthly_profit_payroll_snapshots\n    ADD CONSTRAINT monthly_profit_payroll_snapshots_pkey PRIMARY KEY (id)",
        "ALTER TABLE ONLY finance.monthly_profit_payroll_snapshots\n    ADD CONSTRAINT uq_monthly_profit_payroll_snapshots UNIQUE (settlement_id, snapshot_version, employee_code)",
        "CREATE INDEX ix_monthly_profit_payroll_snapshots_settlement ON finance.monthly_profit_payroll_snapshots USING btree (settlement_id, snapshot_status)",
        "ALTER TABLE ONLY finance.monthly_profit_payroll_snapshots\n    ADD CONSTRAINT monthly_profit_payroll_snapshots_settlement_id_fkey FOREIGN KEY (settlement_id) REFERENCES finance.monthly_profit_settlements(id) ON DELETE CASCADE",
    ],
    "monthly_profit_shop_basis_snapshots": [
        "CREATE TABLE finance.monthly_profit_shop_basis_snapshots (\n    id integer NOT NULL,\n    settlement_id integer NOT NULL,\n    period_month character varying(16) NOT NULL,\n    snapshot_version integer DEFAULT 1 NOT NULL,\n    snapshot_status character varying(32) DEFAULT 'active'::character varying NOT NULL,\n    platform_code character varying(32) NOT NULL,\n    shop_id character varying(256) NOT NULL,\n    shop_name character varying(256),\n    basis_version character varying(64),\n    orders_profit_amount double precision DEFAULT 0 NOT NULL,\n    a_class_cost_amount double precision DEFAULT 0 NOT NULL,\n    profit_basis_amount double precision DEFAULT 0 NOT NULL,\n    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n    created_by character varying(64)\n)",
        "CREATE SEQUENCE finance.monthly_profit_shop_basis_snapshots_id_seq\n    AS integer\n    START WITH 1\n    INCREMENT BY 1\n    NO MINVALUE\n    NO MAXVALUE\n    CACHE 1",
        "ALTER SEQUENCE finance.monthly_profit_shop_basis_snapshots_id_seq OWNED BY finance.monthly_profit_shop_basis_snapshots.id",
        "ALTER TABLE ONLY finance.monthly_profit_shop_basis_snapshots ALTER COLUMN id SET DEFAULT nextval('finance.monthly_profit_shop_basis_snapshots_id_seq'::regclass)",
        "ALTER TABLE ONLY finance.monthly_profit_shop_basis_snapshots\n    ADD CONSTRAINT monthly_profit_shop_basis_snapshots_pkey PRIMARY KEY (id)",
        "ALTER TABLE ONLY finance.monthly_profit_shop_basis_snapshots\n    ADD CONSTRAINT uq_monthly_profit_shop_basis_snapshots UNIQUE (settlement_id, snapshot_version, platform_code, shop_id)",
        "CREATE INDEX ix_monthly_profit_shop_basis_snapshots_settlement ON finance.monthly_profit_shop_basis_snapshots USING btree (settlement_id, snapshot_status)",
        "ALTER TABLE ONLY finance.monthly_profit_shop_basis_snapshots\n    ADD CONSTRAINT monthly_profit_shop_basis_snapshots_settlement_id_fkey FOREIGN KEY (settlement_id) REFERENCES finance.monthly_profit_settlements(id) ON DELETE CASCADE",
    ],
    "monthly_profit_employee_commission_snapshots": [
        "CREATE TABLE finance.monthly_profit_employee_commission_snapshots (\n    id integer NOT NULL,\n    settlement_id integer NOT NULL,\n    period_month character varying(16) NOT NULL,\n    snapshot_version integer DEFAULT 1 NOT NULL,\n    snapshot_status character varying(32) DEFAULT 'active'::character varying NOT NULL,\n    employee_code character varying(64) NOT NULL,\n    employee_name character varying(128),\n    platform_code character varying(32) NOT NULL,\n    shop_id character varying(256) NOT NULL,\n    shop_name character varying(256),\n    sales_amount double precision DEFAULT 0 NOT NULL,\n    commission_rate double precision DEFAULT 0 NOT NULL,\n    commission_amount double precision DEFAULT 0 NOT NULL,\n    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n    created_by character varying(64)\n)",
        "CREATE SEQUENCE finance.monthly_profit_employee_commission_snapshots_id_seq\n    AS integer\n    START WITH 1\n    INCREMENT BY 1\n    NO MINVALUE\n    NO MAXVALUE\n    CACHE 1",
        "ALTER SEQUENCE finance.monthly_profit_employee_commission_snapshots_id_seq OWNED BY finance.monthly_profit_employee_commission_snapshots.id",
        "ALTER TABLE ONLY finance.monthly_profit_employee_commission_snapshots ALTER COLUMN id SET DEFAULT nextval('finance.monthly_profit_employee_commission_snapshots_id_seq'::regclass)",
        "ALTER TABLE ONLY finance.monthly_profit_employee_commission_snapshots\n    ADD CONSTRAINT monthly_profit_employee_commission_snapshots_pkey PRIMARY KEY (id)",
        "ALTER TABLE ONLY finance.monthly_profit_employee_commission_snapshots\n    ADD CONSTRAINT uq_monthly_profit_employee_commission_snapshots UNIQUE (settlement_id, snapshot_version, employee_code, platform_code, shop_id)",
        "CREATE INDEX ix_monthly_profit_employee_commission_snapshots_settlement ON finance.monthly_profit_employee_commission_snapshots USING btree (settlement_id, snapshot_status)",
        "ALTER TABLE ONLY finance.monthly_profit_employee_commission_snapshots\n    ADD CONSTRAINT monthly_profit_employee_commission_snapshots_settlement_id_fkey FOREIGN KEY (settlement_id) REFERENCES finance.monthly_profit_settlements(id) ON DELETE CASCADE",
    ],
    "monthly_profit_employee_performance_snapshots": [
        "CREATE TABLE finance.monthly_profit_employee_performance_snapshots (\n    id integer NOT NULL,\n    settlement_id integer NOT NULL,\n    period_month character varying(16) NOT NULL,\n    snapshot_version integer DEFAULT 1 NOT NULL,\n    snapshot_status character varying(32) DEFAULT 'active'::character varying NOT NULL,\n    employee_code character varying(64) NOT NULL,\n    employee_name character varying(128),\n    actual_sales double precision DEFAULT 0 NOT NULL,\n    achievement_rate double precision DEFAULT 0 NOT NULL,\n    performance_score double precision DEFAULT 0 NOT NULL,\n    attendance_adjustment_score double precision DEFAULT 0 NOT NULL,\n    manual_adjustment_score double precision DEFAULT 0 NOT NULL,\n    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,\n    created_by character varying(64)\n)",
        "CREATE SEQUENCE finance.monthly_profit_employee_performance_snapshots_id_seq\n    AS integer\n    START WITH 1\n    INCREMENT BY 1\n    NO MINVALUE\n    NO MAXVALUE\n    CACHE 1",
        "ALTER SEQUENCE finance.monthly_profit_employee_performance_snapshots_id_seq OWNED BY finance.monthly_profit_employee_performance_snapshots.id",
        "ALTER TABLE ONLY finance.monthly_profit_employee_performance_snapshots ALTER COLUMN id SET DEFAULT nextval('finance.monthly_profit_employee_performance_snapshots_id_seq'::regclass)",
        "ALTER TABLE ONLY finance.monthly_profit_employee_performance_snapshots\n    ADD CONSTRAINT monthly_profit_employee_performance_snapshots_pkey PRIMARY KEY (id)",
        "ALTER TABLE ONLY finance.monthly_profit_employee_performance_snapshots\n    ADD CONSTRAINT uq_monthly_profit_employee_performance_snapshots UNIQUE (settlement_id, snapshot_version, employee_code)",
        "CREATE INDEX ix_monthly_profit_employee_performance_snapshots_settlement ON finance.monthly_profit_employee_performance_snapshots USING btree (settlement_id, snapshot_status)",
        "ALTER TABLE ONLY finance.monthly_profit_employee_performance_snapshots\n    ADD CONSTRAINT monthly_profit_employee_performance_snapshot_settlement_id_fkey FOREIGN KEY (settlement_id) REFERENCES finance.monthly_profit_settlements(id) ON DELETE CASCADE",
    ],
}


def _has_table(schema: str, table: str) -> bool:
    """表是否已存在（幂等的前提）。"""
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table, schema=schema)


def upgrade() -> None:
    """删除 5 张停写快照表，并删掉主台账表上的 9 个废弃列。"""
    bind = op.get_bind()
    for table in DROPPED_TABLES:
        # ⚠️ 不用 CASCADE：万一还有意料之外的引用，宁可报错停下，也不静默删掉别的表。
        bind.execute(sa.text(f"DROP TABLE IF EXISTS {FINANCE_SCHEMA}.{table}"))
    if _has_table(FINANCE_SCHEMA, SETTLEMENT_TABLE):
        for column in DROPPED_COLUMNS:
            bind.execute(
                sa.text(
                    f"ALTER TABLE {FINANCE_SCHEMA}.{SETTLEMENT_TABLE} "
                    f"DROP COLUMN IF EXISTS {column}"
                )
            )


def downgrade() -> None:
    """重建这 5 张**空表**并加回 9 个废弃列（数据不可回滚，见文件头说明）。"""
    bind = op.get_bind()
    for table, statements in RECREATE_TABLE_STATEMENTS.items():
        if _has_table(FINANCE_SCHEMA, table):
            continue
        for statement in statements:
            bind.execute(sa.text(statement))
    if _has_table(FINANCE_SCHEMA, SETTLEMENT_TABLE):
        for column in DROPPED_COLUMNS:
            bind.execute(
                sa.text(
                    f"ALTER TABLE {FINANCE_SCHEMA}.{SETTLEMENT_TABLE} "
                    f"ADD COLUMN IF NOT EXISTS {column} {COLUMN_DEFINITION}"
                )
            )
