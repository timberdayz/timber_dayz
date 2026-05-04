from backend.domains.platform.routers.performance import router as performance_router
from backend.domains.platform.routers.roles import router as roles_router
from backend.domains.platform.routers.users import router as users_router
from backend.domains.platform.routers.system_monitoring import (
    router as system_monitoring_router,
)
from backend.domains.platform.routers.test_api import router as test_api_router

__all__ = [
    "performance_router",
    "roles_router",
    "users_router",
    "system_monitoring_router",
    "test_api_router",
]
