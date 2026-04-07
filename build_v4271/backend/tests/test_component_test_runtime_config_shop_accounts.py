from backend.routers.component_versions import _build_component_test_runtime_config
from backend.schemas.component_version import ComponentTestRequest


def test_build_component_test_runtime_config_sets_shop_account_id_when_provided():
    request = ComponentTestRequest(
        shop_account_id="shopee_sg_hongxi_local",
        time_mode="preset",
        date_preset="today",
    )

    logical_type, runtime_config = _build_component_test_runtime_config(
        request, "shopee/products_export"
    )

    assert logical_type == "export"
    assert runtime_config["shop_account_id"] == "shopee_sg_hongxi_local"
