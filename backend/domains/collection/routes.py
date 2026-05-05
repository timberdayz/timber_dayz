from backend.domains.collection.routers import account_alignment, collection, component_recorder


def register_collection_routes(app, logger) -> None:
    app.include_router(collection.router, prefix="/api/collection", tags=["数据采集"])
    app.include_router(
        component_recorder.router, prefix="/api/collection", tags=["组件录制"]
    )

    try:
        from backend.domains.collection.routers import collection_websocket
        from backend.domains.collection.routers import (
            component_versions,
            main_accounts,
            platform_shop_discoveries,
            shop_account_aliases,
            shop_accounts,
        )

        app.include_router(
            collection_websocket.router, prefix="/api/collection", tags=["采集WebSocket"]
        )
        app.include_router(main_accounts.router, prefix="/api", tags=["主账号管理"])
        app.include_router(shop_accounts.router, prefix="/api", tags=["店铺账号管理"])
        app.include_router(
            shop_account_aliases.router, prefix="/api", tags=["店铺别名管理"]
        )
        app.include_router(
            platform_shop_discoveries.router, prefix="/api", tags=["平台店铺ID发现"]
        )
        app.include_router(component_versions.router, prefix="/api", tags=["组件版本管理"])
    except ImportError as exc:
        logger.warning(f"Collection WebSocket router not loaded: {exc}")

    app.include_router(account_alignment.router, prefix="/api", tags=["账号对齐"])
