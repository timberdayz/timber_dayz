import os

from fastapi import FastAPI

from backend.app.bootstrap import (
    register_collector_routes,
    register_common_routes,
    register_development_routes,
    register_production_routes,
)


def resolve_runtime_mode(settings, runtime_mode: str | None = None) -> str:
    if runtime_mode:
        normalized = runtime_mode.strip().lower()
    else:
        normalized = os.getenv("APP_RUNTIME_MODE", "").strip().lower()

    if normalized in {"production", "collector", "development"}:
        return normalized

    environment = os.getenv("ENVIRONMENT", settings.ENVIRONMENT).strip().lower()
    deployment_role = os.getenv("DEPLOYMENT_ROLE", "").strip().lower()
    enable_collection = os.getenv("ENABLE_COLLECTION", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if deployment_role == "collector":
        return "collector"
    if environment == "production" and not enable_collection:
        return "production"
    return "development"


def register_mode_routes(app: FastAPI, logger, runtime_mode: str) -> None:
    register_common_routes(app, logger)
    if runtime_mode == "production":
        logger.info("Dashboard router source: PostgreSQL")
        register_production_routes(app)
        return
    if runtime_mode == "collector":
        register_collector_routes(app, logger)
        return

    logger.info("Dashboard router source: PostgreSQL")
    register_collector_routes(app, logger)
    register_production_routes(app)
    register_development_routes(app)


def bootstrap_app(app: FastAPI, logger, settings, runtime_mode: str | None = None) -> FastAPI:
    if getattr(app.state, "_bootstrap_registered", False):
        return app

    resolved_mode = resolve_runtime_mode(settings, runtime_mode)
    app.state.runtime_mode = resolved_mode
    register_mode_routes(app, logger, resolved_mode)
    app.state._bootstrap_registered = True
    return app
