from modules.components.base import ExecutionContext
from modules.platforms.miaoshou.components.login import MiaoshouLogin


def _ctx():
    return ExecutionContext(
        platform="miaoshou",
        account={"username": "u", "password": "p", "login_url": "https://erp.91miaoshou.com"},
        logger=None,
        config={},
    )


def test_miaoshou_login_success_detection_accepts_dashboard_urls():
    component = MiaoshouLogin(_ctx())

    assert component._login_looks_successful("https://erp.91miaoshou.com/welcome") is True
    assert component._login_looks_successful("https://erp.91miaoshou.com/dashboard") is True


def test_miaoshou_login_success_detection_rejects_login_urls():
    component = MiaoshouLogin(_ctx())

    assert component._login_looks_successful("https://erp.91miaoshou.com/?redirect=%2Fwelcome") is False
    assert component._login_looks_successful("https://erp.91miaoshou.com/login") is False
    assert component._login_looks_successful("https://erp.91miaoshou.com/account/login") is False
