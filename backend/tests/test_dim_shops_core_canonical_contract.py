from modules.core.db import DimShop


def test_dim_shop_model_is_bound_to_core_schema():
    assert DimShop.__table__.schema == "core"
    assert DimShop.__table__.fullname == "core.dim_shops"
