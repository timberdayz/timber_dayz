from backend.routers import performance, test_api


def register_development_support_routes(app) -> None:
    app.include_router(test_api.router, prefix="/api/test", tags=["测试诊断"])
    app.include_router(
        performance.router,
        prefix="/api",
        tags=["系统性能监控"],
    )
