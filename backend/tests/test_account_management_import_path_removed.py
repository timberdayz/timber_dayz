from pathlib import Path

from backend.main import app

RUNTIME_FILES = [
    Path("frontend/src/api/accounts.js"),
    Path("frontend/src/stores/accounts.js"),
    Path("frontend/src/views/AccountManagement.vue"),
]


def test_runtime_files_do_not_reference_import_from_local():
    for path in RUNTIME_FILES:
        text = path.read_text(encoding="utf-8")
        assert "importFromLocal" not in text
        assert "import-from-local" not in text


def test_accounts_api_no_longer_uses_legacy_list_endpoint():
    text = Path("frontend/src/api/accounts.js").read_text(encoding="utf-8")

    assert "api.get('/accounts/', { params })" not in text
    assert "listShopAccounts" in text


def test_account_management_import_from_local_route_removed():
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/accounts/import-from-local" not in paths


def test_account_management_list_route_still_available():
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/accounts/" not in paths
