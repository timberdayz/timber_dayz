from pathlib import Path

from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.login import MiaoshouLogin


def _ctx():
    return ExecutionContext(
        platform="miaoshou",
        account={
            "username": "u",
            "password": "p",
            "login_url": "https://erp.91miaoshou.com",
        },
        logger=None,
        config={},
    )


def test_miaoshou_login_canonical_file_is_not_a_passive_alias_shell():
    source = Path(
        "modules/platforms/miaoshou/components/login.py"
    ).read_text(encoding="utf-8")

    assert "from modules.platforms.miaoshou.components.miaoshou_login import" not in source
    assert "class MiaoshouLogin" in source
    assert "async def run(" in source


def test_miaoshou_login_success_detection_rejects_root_public_page():
    component = MiaoshouLogin(_ctx())

    assert component._login_looks_successful("https://erp.91miaoshou.com/") is False


def test_miaoshou_stable_login_file_does_not_keep_placeholder_success_logic():
    source = Path(
        "modules/platforms/miaoshou/components/login_v1_0_3.py"
    ).read_text(encoding="utf-8")

    assert "returning success placeholder without post-login gate" not in source
    assert 'return LoginResult(success=True, message="ok")' not in source


def test_miaoshou_login_component_no_longer_depends_on_legacy_login_form_css():
    source = Path(
        "modules/platforms/miaoshou/components/login.py"
    ).read_text(encoding="utf-8")

    assert "#J_loginRegisterForm" not in source
    assert "input.account-input" not in source
    assert "get_by_role(" in source
