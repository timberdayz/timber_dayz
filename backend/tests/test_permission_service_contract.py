from backend.services.permission_service import PermissionService


def test_permission_service_does_not_expose_removed_data_browser_permission():
    permissions = PermissionService.get_all_permissions()
    permission_ids = {item["id"] for item in permissions}

    assert "data-browser" not in permission_ids
