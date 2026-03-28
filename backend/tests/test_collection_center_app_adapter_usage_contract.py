import pytest

from modules.components.base import ExecutionContext
from modules.services.platform_adapter import get_adapter


def _ctx(platform: str):
    return ExecutionContext(
        platform=platform,
        account={"username": "u"},
        logger=None,
        config={},
    )


def test_get_adapter_rejects_legacy_surface_by_default():
    with pytest.raises(NotImplementedError, match="legacy platform adapter surface is disabled"):
        get_adapter("miaoshou", _ctx("miaoshou"))


def test_get_adapter_can_be_explicitly_enabled_for_legacy_debug_paths():
    adapter = get_adapter("miaoshou", _ctx("miaoshou"), allow_legacy_surface=True)

    assert adapter.platform_id == "miaoshou"
