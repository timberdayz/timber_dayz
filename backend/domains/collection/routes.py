from backend.domains.collection.routers import (
    account_alignment,
    collection,
    component_recorder,
)


def register_collection_routes(app, logger) -> None:
    app.include_router(collection.router, prefix="/api/collection", tags=["数据采集"])
    app.include_router(
        component_recorder.router, prefix="/api/collection", tags=["组件录制"]
    )

    try:
        from backend.domains.collection.routers import collection_websocket
        from backend.domains.collection.routers import (
            component_versions,
        )

        app.include_router(
            collection_websocket.router,
            prefix="/api/collection",
            tags=["采集WebSocket"],
        )
        app.include_router(
            component_versions.router, prefix="/api", tags=["组件版本管理"]
        )
    except ImportError as exc:
        logger.warning(f"Collection WebSocket router not loaded: {exc}")

    # ⚠️⚠️ 这里**不再**挂载主账号 / 店铺账号 / 店铺别名 / 平台店铺ID发现 /
    #    仓名别名这 5 组 router（2026-11-13 去重复挂载，批次 C1）。
    #
    #    它们虽住在 ``backend/domains/collection/routers/`` 目录下，
    #    但业务上属于**平台运营主数据**（路径都在 ``/api/`` 下，tags 也是
    #    「主账号管理」「店铺账号管理」…），归 **platform 域**。
    #
    #    为什么必须由 platform 侧挂、而不是反过来删 platform 侧的：
    #    ``backend/app/runtime.py`` 的 ``register_mode_routes`` 先注册
    #    common（platform）再按运行模式注册 collector（collection），
    #    且 **production 模式根本不注册 collection 域** ⇒
    #    账号类接口在生产上**只由 platform 提供**。
    #    ⇒ 唯一挂载点必须是 platform，collection 侧重复挂载才是多余的。
    #
    #    实测（2026-11-13）：改前 development/collector 模式各有
    #    **24 条 (路径, 方法) 重复注册、涉及 17 条路径**；production 模式 0 条。
    #    守护用例见 ``backend/tests/test_router_unique_mount_points.py``。

    app.include_router(account_alignment.router, prefix="/api", tags=["账号对齐"])
