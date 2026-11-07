import re
from pathlib import Path


def test_operational_metrics_sql_uses_current_operating_cost_contract():
    text = Path(
        "sql/api_modules/business_overview_operational_metrics_module.sql"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "platform_code" in text
    assert '"\u5e74\u6708"' in text
    assert '"\u5e97\u94faID"' in text
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
    assert '"\u5e74\u6708"' in service_text
    assert '"\u76ee\u6807\u9500\u552e\u989d"' in service_text
    assert '"\u76ee\u6807\u8ba2\u5355\u6570"' in service_text
    assert '"\u76ee\u6807\u5355\u91cf"' in service_text
    assert '"\u5e74\u6708"' in sql_text
    assert '"\u76ee\u6807\u9500\u552e\u989d"' in sql_text
    assert '"\u76ee\u6807\u8ba2\u5355\u6570"' in sql_text
    assert "mart.shop_month_kpi" in sql_text


def test_sales_targets_a_contract_includes_platform_code_identity():
    schema_text = Path("modules/core/db/schema_parts/business.py").read_text(
        encoding="utf-8",
        errors="replace",
    )
    migration_text = Path(
        "migrations/versions/20260610_add_platform_code_to_sales_targets_a.py"
    ).read_text(
        encoding="utf-8",
        errors="replace",
    )
    sync_text = Path("backend/services/target_sync_service.py").read_text(
        encoding="utf-8",
        errors="replace",
    )

    assert "platform_code = Column(String(32)" in schema_text
    # 约束语义不变(platform_code + shop_id + year_month 唯一),
    # 只是 black 格式化后拆成了多行 ⇒ 用正则而不是逐字匹配
    assert re.search(
        r"UniqueConstraint\(\s*"
        r'"platform_code",\s*'
        r'"shop_id",\s*'
        r'"year_month",\s*'
        r'name="uq_sales_targets_a_platform_shop_month",?\s*'
        r"\)",
        schema_text,
    )
    assert "20260609_operating_costs_labor_cost" in migration_text
    assert "op.add_column" in migration_text
    assert "platform_code" in migration_text
    assert "_resolve_sales_targets_a_identity_columns" in migration_text
    assert '"店铺ID", "年月"' in migration_text
    assert '"shop_id", "year_month"' in migration_text
    assert "uq_sales_targets_shop_month" in migration_text
    assert "uq_sales_targets_a_platform_shop_month" in migration_text
    assert "ON CONFLICT (platform_code," in sync_text
