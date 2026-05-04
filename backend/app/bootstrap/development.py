from backend.domains.platform.development import (
    register_development_support_routes,
)


def register_development_routes(app) -> None:
    register_development_support_routes(app)
