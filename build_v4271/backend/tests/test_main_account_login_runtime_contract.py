from modules.apps.collection_center.executor_v2 import _resolve_session_scope


def test_resolve_session_scope_prefers_main_account_id_for_session_owner():
    session_owner_id, shop_account_id, reuse_enabled = _resolve_session_scope(
        "shopee_sg_hongxi_local",
        {
            "main_account_id": "hongxikeji:main",
            "shop_account_id": "shopee_sg_hongxi_local",
            "account_id": "shopee_sg_hongxi_local",
        },
    )

    assert session_owner_id == "hongxikeji:main"
    assert shop_account_id == "shopee_sg_hongxi_local"
    assert reuse_enabled is True


def test_resolve_session_scope_disables_reuse_when_main_account_missing():
    session_owner_id, shop_account_id, reuse_enabled = _resolve_session_scope(
        "miaoshou_real_001",
        {
            "account_id": "miaoshou_real_001",
        },
    )

    assert session_owner_id == ""
    assert shop_account_id == "miaoshou_real_001"
    assert reuse_enabled is False
