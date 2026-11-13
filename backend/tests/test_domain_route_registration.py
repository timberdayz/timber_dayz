from fastapi import FastAPI


class _NullLogger:
    def warning(self, message: str) -> None:
        return None


def _paths_for(app: FastAPI) -> set[str]:
    return {route.path for route in app.routes if hasattr(route, "path")}


def test_collection_domain_registration_exposes_collection_routes():
    from backend.domains.collection.routes import register_collection_routes

    app = FastAPI()
    register_collection_routes(app, _NullLogger())

    paths = _paths_for(app)
    assert "/api/collection/configs" in paths
    # ⚠️ 账号类路由（店铺别名 / 店铺账号 / 主账号 / 平台店铺ID发现 / 仓名别名）
    #    **不再**由 collection 域挂载 —— 它们的唯一挂载点在 platform 域。
    #
    #    为什么不在 collection 侧：production 模式根本不注册 collection 域
    #    （backend/app/runtime.py register_mode_routes）⇒ 账号类接口在生产上
    #    只由 platform 提供；两边都挂 ⇒ 同一组接口注册两遍（OpenAPI 里出现
    #    重复 operation_id）。详见批次 C1 与
    #    backend/tests/test_router_unique_mount_points.py。
    assert "/api/shop-account-aliases" not in paths
    assert "/api/shop-accounts" not in paths


def test_data_platform_domain_registration_exposes_data_platform_routes():
    from backend.domains.data_platform.routes import register_data_platform_routes

    app = FastAPI()
    register_data_platform_routes(app, _NullLogger())

    paths = _paths_for(app)
    assert "/api/data-pipeline/status" in paths
    assert "/api/field-mapping/templates/list" in paths


def test_business_domain_registration_exposes_business_routes():
    from backend.domains.business.routes import register_business_routes

    app = FastAPI()
    register_business_routes(app)

    paths = _paths_for(app)
    assert "/api/dashboard/business-overview/kpi" in paths
    assert "/api/finance/follow-investments" in paths


def test_platform_domain_registration_exposes_platform_routes():
    from backend.domains.platform.routes import register_platform_routes

    app = FastAPI()
    register_platform_routes(app)

    paths = _paths_for(app)
    assert "/api/users/" in paths
    assert "/api/auth/login" in paths
    assert "/api/reference/shop-directory" in paths
    # ⚠️ 账号类 router 的**唯一挂载点**在 platform 域（批次 C1）：
    #    production 模式不注册 collection 域 ⇒ 这里必须提供这 5 组接口。
    assert "/api/shop-accounts" in paths
    assert "/api/main-accounts" in paths
    assert "/api/shop-account-aliases" in paths
    assert "/api/platform-shop-discoveries" in paths
    assert "/api/warehouse-name-aliases" in paths


def test_development_support_registration_exposes_diagnostic_routes():
    from backend.domains.platform.development import register_development_support_routes

    app = FastAPI()
    register_development_support_routes(app)

    paths = _paths_for(app)
    assert "/api/test/test-db" in paths
    assert "/api/system/performance/test/health" in paths
