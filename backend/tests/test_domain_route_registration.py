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
    assert "/api/shop-account-aliases" in paths


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


def test_development_support_registration_exposes_diagnostic_routes():
    from backend.domains.platform.development import register_development_support_routes

    app = FastAPI()
    register_development_support_routes(app)

    paths = _paths_for(app)
    assert "/api/test/test-db" in paths
    assert "/api/system/performance/test/health" in paths
