from backend.domains.business.routes import register_business_routes


def register_production_routes(app) -> None:
    register_business_routes(app)
