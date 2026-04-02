from pathlib import Path

from modules.apps.collection_center.executor_v2 import _resolve_session_scope


def test_execute_defines_reused_session_before_runtime_task_params_call():
    source = Path("modules/apps/collection_center/executor_v2.py").read_text(encoding="utf-8")

    reused_index = source.index("reused_session = False")
    build_params_index = source.index("params = _build_runtime_task_params(")

    assert reused_index < build_params_index


def test_resolve_session_scope_prefers_main_account_id_over_shop_account_id():
    session_owner_id, shop_account_id, use_scope = _resolve_session_scope(
        "shopee_sg_hongxi_local",
        {
            "account_id": "shopee_sg_hongxi_local",
            "main_account_id": "hongxikeji:main",
        },
    )

    assert session_owner_id == "hongxikeji:main"
    assert shop_account_id == "shopee_sg_hongxi_local"
    assert use_scope is True
