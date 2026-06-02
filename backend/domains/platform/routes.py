from backend.domains.platform.routers import (
    auth,
    backup,
    maintenance,
    notification_config,
    notifications,
    reference,
    rbac_admin,
    rate_limit,
    rate_limit_config,
    security,
    system,
    system_logs,
    system_monitoring,
    tiktokshop_oauth,
    users,
)
from backend.domains.collection.routers import (
    main_accounts,
    platform_shop_discoveries,
    shop_account_aliases,
    shop_accounts,
)


def register_platform_routes(app) -> None:
    app.include_router(system_monitoring.router, prefix="/api", tags=["系统监控"])
    app.include_router(auth.router, prefix="/api", tags=["认证管理"])
    app.include_router(users.router, prefix="/api", tags=["用户管理"])
    app.include_router(reference.router, prefix="/api", tags=["参考目录"])
    app.include_router(main_accounts.router, prefix="/api", tags=["主账号管理"])
    app.include_router(shop_accounts.router, prefix="/api", tags=["店铺账号管理"])
    app.include_router(shop_account_aliases.router, prefix="/api", tags=["店铺别名管理"])
    app.include_router(
        platform_shop_discoveries.router, prefix="/api", tags=["平台店铺ID发现"]
    )
    app.include_router(rbac_admin.router, tags=["RBAC 管理"])
    app.include_router(notifications.router, prefix="/api", tags=["通知管理"])
    app.include_router(system.router, tags=["系统配置"])
    app.include_router(system_logs.router, tags=["系统日志"])
    app.include_router(security.router, tags=["安全设置"])
    app.include_router(backup.router, tags=["数据备份"])
    app.include_router(maintenance.router, tags=["系统维护"])
    app.include_router(notification_config.router, tags=["通知配置"])
    app.include_router(rate_limit.router, prefix="/api", tags=["限流管理"])
    app.include_router(rate_limit_config.router, tags=["限流配置管理"])

    # Public OAuth callback endpoints (no /api prefix by design)
    app.include_router(tiktokshop_oauth.router, tags=["TikTok Shop OAuth"])
