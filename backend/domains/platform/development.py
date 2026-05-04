from backend.domains.platform.routers import performance as performance_router_module
from backend.domains.platform.routers import test_api as test_api_router_module


def register_development_support_routes(app) -> None:
    app.include_router(test_api_router_module.router, prefix="/api/test", tags=["测试诊断"])
    app.include_router(
        performance_router_module.router,
        prefix="/api",
        tags=["系统性能监控"],
    )
