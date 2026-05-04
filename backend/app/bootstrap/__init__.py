from backend.app.bootstrap.collector import register_collector_routes
from backend.app.bootstrap.common import register_common_routes
from backend.app.bootstrap.development import register_development_routes
from backend.app.bootstrap.production import register_production_routes

__all__ = [
    "register_collector_routes",
    "register_common_routes",
    "register_development_routes",
    "register_production_routes",
]
