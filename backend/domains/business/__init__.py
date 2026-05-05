def register_business_routes(app) -> None:
    from backend.domains.business.routes import register_business_routes as _impl

    return _impl(app)


__all__ = ["register_business_routes"]
