from fastapi.routing import APIRoute

from backend.domains.business.routers import performance_management


def test_personal_workbench_routes_are_typed_and_admin_protected():
    routes = {
        (route.path, tuple(sorted(route.methods or []))): route
        for route in performance_management.router.routes
        if isinstance(route, APIRoute)
    }

    for path, methods in [
        ("/performance/personal-workbench", ("GET",)),
        ("/performance/personal-workbench", ("PUT",)),
        ("/performance/personal-workbench/scope", ("GET",)),
        ("/performance/personal-workbench/scope", ("PUT",)),
        ("/performance/personal-workbench/entries", ("GET",)),
        ("/performance/personal-workbench/entries", ("PUT",)),
        ("/performance/personal-workbench/scope/revoke", ("POST",)),
    ]:
        route = routes[(path, methods)]
        assert route.response_model is not None
        assert any(
            getattr(dependency.call, "__name__", "") == "require_admin"
            for dependency in route.dependant.dependencies
        )
