from pathlib import Path


def test_operational_metrics_sql_uses_current_operating_cost_contract():
    text = Path(
        "sql/api_modules/business_overview_operational_metrics_module.sql"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "platform_code" in text
    # 2026-08-05(commit 2a5af9fd「feat: project labor costs from payroll」)起:
    # 成本口径 = 其他经营成本(semantic 层)+ 薪资链路投影的人力成本(mart 层)
    assert "semantic.shop_month_other_operating_cost" in text
    assert "mart.shop_month_labor_cost" in text
    for column in (
        "other_operating_cost",
        "pre_commission_labor_cost",
        "performance_labor_cost",
        "commission_labor_cost",
        "total_labor_cost",
        "cost_status",
        "estimated_expenses",
    ):
        assert column in text
    # 第三批-C：月度目标改读真 SSOT a_class.target_breakdown 的「店铺 × 月」档位
    assert "a_class.target_breakdown" in text
    assert "breakdown_type = 'shop'" in text
    # 第三批-C：a_class.sales_targets_a 已下线，视图资产里不能再读它
    assert "FROM a_class.sales_targets_a" not in text
    # 旧的中文字段名（年月/店铺ID/目标销售额/目标订单数）已全部退场
    for legacy_column in (
        '"\u5e74\u6708"',
        '"\u5e97\u94faID"',
        '"\u76ee\u6807\u9500\u552e\u989d"',
        '"\u76ee\u6807\u8ba2\u5355\u6570"',
    ):
        assert legacy_column not in text
    # 旧的手工成本明细列(租金/营销费用/水电费/AI Token费用/其他成本/成本合计/
    # 删除时间)已不在这个视图里 —— 它们属于 a_class.operating_costs 明细层
    # (只看可执行语句: 文件头的注释里仍留着一份旧口径说明)
    executable = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("--")
    )
    for legacy_column in (
        '"\u79df\u91d1"',
        '"\u8425\u9500\u8d39\u7528"',
        '"\u6c34\u7535\u8d39"',
        '"AI Token\u8d39\u7528"',
        '"\u5176\u4ed6\u6210\u672c"',
        '"\u6210\u672c\u5408\u8ba1"',
        '"\u5220\u9664\u65f6\u95f4"',
    ):
        assert legacy_column not in executable
    assert "information_schema.columns" not in text


def test_target_completion_service_prefers_current_sales_target_columns():
    service_text = Path("backend/services/postgresql_dashboard_service.py").read_text(
        encoding="utf-8",
        errors="replace",
    )
    sql_text = Path(
        "sql/api_modules/business_overview_comparison_module.sql"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "target_sales_amount" in service_text
    assert "target_quantity" in service_text
    assert "year_month" in service_text
    # 第三批-C：a_class.sales_targets_a 已下线 —— 服务与视图资产里都不能再读它
    assert "FROM a_class.sales_targets_a" not in service_text
    assert "FROM a_class.sales_targets_a" not in sql_text
    # 真 SSOT 是 target_breakdown 的「店铺 × 月」档位
    assert "a_class.target_breakdown" in service_text
    assert "a_class.target_breakdown" in sql_text
    assert "breakdown_type = 'shop'" in sql_text
    # 旧的中文字段名（年月/目标销售额/目标订单数/目标单量）已全部退场
    for legacy_column in (
        '"\u5e74\u6708"',
        '"\u76ee\u6807\u9500\u552e\u989d"',
        '"\u76ee\u6807\u8ba2\u5355\u6570"',
        '"\u76ee\u6807\u5355\u91cf"',
    ):
        assert legacy_column not in service_text
        assert legacy_column not in sql_text
    assert "mart.shop_month_kpi" in sql_text


def test_sales_targets_a_contract_migrated_into_target_breakdown():
    """第三批-C：a_class.sales_targets_a 已下线，店铺月度目标改由 target_breakdown 承接。

    身份键 (platform_code + shop_id + 年月) 的语义不变，只是物理载体从
    影子表 sales_targets_a 迁到了真 SSOT a_class.target_breakdown 的
    「店铺 × 月」档位行 (breakdown_type='shop' + period_label='YYYY-MM')。
    """
    schema_text = Path("modules/core/db/schema_parts/business.py").read_text(
        encoding="utf-8",
        errors="replace",
    )
    schema_export_text = Path("modules/core/db/schema.py").read_text(
        encoding="utf-8",
        errors="replace",
    )
    legacy_migration_text = Path(
        "migrations/versions/20260610_add_platform_code_to_sales_targets_a.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )
    migration_text = Path(
        "current_migrations/versions/20261215_migrate_sales_targets_a.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )
    sync_text = Path("backend/services/target_sync_service.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    # 1) ORM 里已经没有 SalesTargetA 模型了（退役模型不得复活）
    assert "class SalesTargetA" not in schema_text
    assert '__tablename__ = "sales_targets_a"' not in schema_text
    assert "uq_sales_targets_a_platform_shop_month" not in schema_text
    assert "SalesTargetA" not in schema_export_text

    # 2) 身份键由 target_breakdown 承接
    assert "class TargetBreakdown" in schema_text
    assert "platform_code = Column(String(32)" in schema_text
    assert "shop_id = Column(String(64)" in schema_text
    assert "period_label = Column(" in schema_text

    # 3) 活跃迁移链里负责「迁事实 + 校验 + 删表」
    assert "DROP TABLE IF EXISTS a_class.sales_targets_a" in migration_text
    assert "a_class.target_breakdown" in migration_text
    assert "breakdown_type = 'shop'" in migration_text
    assert "to_char(" in migration_text  # period_label 归一为 'YYYY-MM'

    # 4) 历史迁移链保持只读归档（不被回改）
    assert "20260609_operating_costs_labor_cost" in legacy_migration_text
    assert "op.add_column" in legacy_migration_text
    assert "_resolve_sales_targets_a_identity_columns" in legacy_migration_text

    # 5) 同步服务不再读写影子表
    assert "FROM a_class.sales_targets_a" not in sync_text
    assert "INTO a_class.sales_targets_a" not in sync_text
    assert "SalesTargetA" not in sync_text
    assert "TargetBreakdown" in sync_text


def test_operating_costs_columns_are_unified_english_names():
    """第三批-B：ORM 声明的列名与物理列名一一同名（不再有中文映射层）。"""
    schema_text = Path("modules/core/db/schema_parts/business.py").read_text(
        encoding="utf-8",
        errors="replace",
    )
    migration_text = Path(
        "current_migrations/versions/20261214_unify_operating_costs_columns.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    for column in (
        "shop_id",
        "year_month",
        "rent_amount",
        "marketing_amount",
        "utility_amount",
        "ai_token_amount",
        "labor_amount",
        "other_amount",
        "total_amount",
        "remark",
        "attachments",
        "is_locked",
        "deleted_at",
        "deleted_by",
    ):
        assert f"{column} = Column(" in schema_text

    for old, new in (
        ("店铺ID", "shop_id"),
        ("年月", "year_month"),
        ("营销费用", "marketing_amount"),
        ("AI Token费用", "ai_token_amount"),
        ("成本合计", "total_amount"),
        ("是否锁定", "is_locked"),
        ("删除时间", "deleted_at"),
        ("删除人", "deleted_by"),
    ):
        assert f'("{old}", "{new}")' in migration_text

    assert (
        'revision = "current_schema_20261214_unify_operating_costs_columns"'
        in migration_text
    )
    assert (
        'down_revision = "current_schema_20261213_employee_performance_coefficient"'
        in migration_text
    )
