def test_cloud_sync_routes_are_registered_in_main_app():
    from backend.main import app

    paths = {route.path for route in app.routes}

    assert "/api/cloud-sync/health" in paths
    assert "/api/cloud-sync/tables" in paths
    assert "/api/cloud-sync/tasks" in paths
    assert "/api/cloud-sync/events" in paths
