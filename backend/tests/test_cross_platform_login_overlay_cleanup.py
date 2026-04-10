import pytest

from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.login import MiaoshouLogin
from modules.platforms.shopee.components.login import ShopeeLogin
from modules.platforms.tiktok.components.login import TiktokLogin


def _ctx(platform: str) -> ExecutionContext:
    return ExecutionContext(
        platform=platform,
        account={"username": "u", "password": "p", "login_url": "https://example.com"},
        logger=None,
        config={},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("component_cls", "platform"),
    [
        (MiaoshouLogin, "miaoshou"),
        (ShopeeLogin, "shopee"),
        (TiktokLogin, "tiktok"),
    ],
)
async def test_login_cleanup_after_login_uses_shared_safe_notice_stabilizer(
    component_cls,
    platform: str,
) -> None:
    component = component_cls(_ctx(platform))
    calls: list[str | None] = []

    async def _fake_stabilize(page, *, label=None):  # noqa: ARG001
        calls.append(label)
        return 1

    component.stabilize_safe_notices = _fake_stabilize  # type: ignore[attr-defined]

    await component._cleanup_after_login(page=object())

    assert calls == ["post-login cleanup"]
