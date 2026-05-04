from backend.domains.collection.routes import register_collection_routes as register_collection_domain_routes


def register_collector_routes(app, logger) -> None:
    register_collection_domain_routes(app, logger)
