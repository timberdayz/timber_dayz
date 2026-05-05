def register_collection_routes(app, logger) -> None:
    from backend.domains.collection.routes import register_collection_routes as _impl

    return _impl(app, logger)


__all__ = ["register_collection_routes"]
