from fastapi import FastAPI

from backend.middleware.performance_logging import PerformanceLoggingMiddleware
from backend.middleware.request_id import RequestIDMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware


def create_fastapi_app(app_version: str, lifespan) -> FastAPI:
    return FastAPI(
        title="西虹ERP系统API",
        description="""
    智能跨境电商ERP系统后端API服务
    
    ## API响应格式标准
    
    所有API遵循统一的响应格式
    
    **成功响应**:
    ```json
    {
        "success": true,
        "data": {...},
        "message": "操作成功",
        "timestamp": "2025-01-16T10:30:00Z"
    }
    ```
    
    **错误响应**:
    ```json
    {
        "success": false,
        "error": {
            "code": 2001,
            "type": "BusinessError",
            "detail": "详细错误信息",
            "recovery_suggestion": "恢复建议"
        },
        "message": "用户友好的错误信息",
        "timestamp": "2025-01-16T10:30:00Z"
    }
    ```
    
    **分页响应**:
    ```json
    {
        "success": true,
        "data": [...],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 100,
            "total_pages": 5,
            "has_previous": false,
            "has_next": true
        },
        "timestamp": "2025-01-16T10:30:00Z"
    }
    ```
    
    详细文档:参见 `docs/API_CONTRACTS.md`
    """,
        version=app_version,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )


def configure_middlewares(app: FastAPI, settings, logger) -> None:
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(PerformanceLoggingMiddleware)

    csrf_enabled = str(getattr(settings, "CSRF_ENABLED", "") or "").lower() == "true"
    if not csrf_enabled:
        csrf_enabled = False

    if csrf_enabled:
        from backend.middleware.csrf import CSRFMiddleware

        app.add_middleware(CSRFMiddleware, enabled=True)
        logger.info("[Security] CSRF 保护已启用")
    else:
        logger.info("[Security] CSRF 保护已禁用(设置 CSRF_ENABLED=true 启用)")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)


def configure_rate_limit(app: FastAPI, logger) -> None:
    try:
        from backend.middleware.rate_limiter import limiter, rate_limit_handler
        from slowapi.errors import RateLimitExceeded

        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
        logger.info("[OK] API速率限制已启用")
    except ImportError:
        logger.warning("[SKIP] slowapi未安装,速率限制未启用")
