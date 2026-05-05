def register_data_platform_routes(app, logger) -> None:
    from backend.domains.data_platform.routes import (
        register_data_platform_routes as _impl,
    )

    return _impl(app, logger)


__all__ = ["register_data_platform_routes"]
