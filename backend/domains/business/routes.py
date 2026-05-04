from backend.routers import (
    approval_center,
    config_management,
    dashboard_api_postgresql,
    data_consistency,
    data_flow,
    database_design_validator,
    expense_management,
    hr_management,
    inventory_domain,
    inventory_overview,
    monthly_profit_settlement,
    mv,
    performance_management,
    profit_basis,
    raw_layer,
    raw_layer_export,
    sales_campaign,
    target_management,
    task_center,
    training,
)
from backend.routers import employee_tasks, follow_investment


def register_business_routes(app) -> None:
    app.include_router(dashboard_api_postgresql.router, tags=["Dashboard"])
    app.include_router(config_management.router, tags=["A类数据管理", "配置管理"])
    app.include_router(hr_management.router, tags=["HR管理"])
    app.include_router(inventory_domain.router, tags=["库存管理"])
    app.include_router(inventory_overview.router, tags=["库存总览"])
    app.include_router(profit_basis.router, tags=["利润结算基准"])
    app.include_router(follow_investment.router, tags=["跟投收益"])
    app.include_router(monthly_profit_settlement.router, tags=["月度利润结算中心"])
    app.include_router(training.router, prefix="/api", tags=["培训管理"])
    app.include_router(sales_campaign.router, prefix="/api", tags=["销售战役管理"])
    app.include_router(target_management.router, prefix="/api", tags=["目标管理"])
    app.include_router(expense_management.router, prefix="/api", tags=["费用管理"])
    app.include_router(performance_management.router, prefix="/api", tags=["绩效管理"])
    app.include_router(raw_layer.router, tags=["原始数据层"])
    app.include_router(raw_layer_export.router, tags=["原始数据层"])
    app.include_router(data_flow.router, tags=["数据流转追踪"])
    app.include_router(data_consistency.router, tags=["数据一致性验证"])
    app.include_router(database_design_validator.router, tags=["数据库设计规范验证"])
    app.include_router(mv.router, prefix="/api", tags=["遗留物化视图管理"])
    app.include_router(task_center.router, prefix="/api", tags=["任务中心"])
    app.include_router(employee_tasks.router, prefix="/api", tags=["员工任务中心"])
    app.include_router(approval_center.router, prefix="/api", tags=["审批中心"])
