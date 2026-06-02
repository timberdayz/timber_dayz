from backend.services.permission_service import PermissionService


def test_permission_service_does_not_expose_removed_data_browser_permission():
    permissions = PermissionService.get_all_permissions()
    permission_ids = {item["id"] for item in permissions}

    assert "data-browser" not in permission_ids


def test_permission_service_does_not_expose_retired_frontend_page_permissions():
    permissions = PermissionService.get_all_permissions()
    permission_ids = {item["id"] for item in permissions}

    for retired_permission in {
        "product-management",
        "inventory-management",
        "inventory-dashboard-v3",
        "purchase-orders",
        "grn-management",
        "vendor-management",
        "invoice-management",
        "sales-dashboard-v3",
        "sales-analysis",
        "sales-reports",
        "inventory-reports",
        "finance-reports-detail",
        "vendor-reports",
        "custom-reports",
        "system-notifications",
        "user-guide",
        "video-tutorials",
        "faq",
    }:
        assert retired_permission not in permission_ids


def test_permission_service_keeps_current_route_and_action_permissions():
    permissions = PermissionService.get_all_permissions()
    permission_ids = {item["id"] for item in permissions}

    for current_permission in {
        "sales-dashboard",
        "order-management",
        "notifications",
        "campaign:read",
        "performance:config",
        "performance:read",
        "data-sync",
        "data-governance",
    }:
        assert current_permission in permission_ids
