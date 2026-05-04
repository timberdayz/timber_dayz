from backend.routers import (
    auth,
    backup,
    maintenance,
    notification_config,
    notifications,
    permission,
    permissions,
    rate_limit,
    rate_limit_config,
    roles,
    security,
    system,
    system_logs,
    system_monitoring,
    users,
)


def register_platform_routes(app) -> None:
    app.include_router(system_monitoring.router, prefix="/api", tags=["系统监控"])
    app.include_router(auth.router, prefix="/api", tags=["认证管理"])
    app.include_router(users.router, prefix="/api", tags=["用户管理"])
    app.include_router(roles.router, prefix="/api", tags=["角色管理"])
    app.include_router(permissions.router, tags=["权限管理"])
    app.include_router(permission.router, tags=["权限管理"])
    app.include_router(notifications.router, prefix="/api", tags=["通知管理"])
    app.include_router(system.router, tags=["系统配置"])
    app.include_router(system_logs.router, tags=["系统日志"])
    app.include_router(security.router, tags=["安全设置"])
    app.include_router(backup.router, tags=["数据备份"])
    app.include_router(maintenance.router, tags=["系统维护"])
    app.include_router(notification_config.router, tags=["通知配置"])
    app.include_router(rate_limit.router, prefix="/api", tags=["限流管理"])
    app.include_router(rate_limit_config.router, tags=["限流配置管理"])
