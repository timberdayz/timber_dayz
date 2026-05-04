from backend.domains.data_platform.routes import (
    register_data_platform_routes,
)
from backend.domains.platform.routes import register_platform_routes


def register_common_routes(app, logger) -> None:
    register_data_platform_routes(app, logger)
    try:
        from backend.routers import notification_websocket

        app.include_router(notification_websocket.router, prefix="/api", tags=["通知WebSocket"])
    except ImportError as exc:
        logger.warning(f"Notification WebSocket router not loaded: {exc}")
    register_platform_routes(app)
