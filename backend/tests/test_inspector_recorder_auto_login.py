import types

import pytest

from modules.components.base import ExecutionContext
from modules.components.login.base import LoginResult
from modules.platforms.miaoshou.components.miaoshou_login import MiaoshouMiaoshouLogin
from modules.utils.login_status_detector import LoginStatus
from tools.launch_inspector_recorder import InspectorRecorder


class _FakePage:
    def __init__(self, url: str = "about:blank"):
        self.url = url

    async def wait_for_timeout(self, ms: int):
        return None


class _DetectorResult:
    def __init__(self, status: str, confidence: float, reason: str = "stub"):
        self.status = LoginStatus(status)
        self.confidence = confidence
        self.reason = reason
        self.detected_by = "stub"
        self.detection_time_ms = 1
        self.matched_pattern = None


@pytest.mark.asyncio
async def test_inspector_recorder_auto_login_executes_python_login_component(monkeypatch):
    recorder = InspectorRecorder(
        {
            "platform": "miaoshou",
            "component_type": "export",
            "account_info": {
                "account_id": "acc-1",
                "login_url": "https://erp.91miaoshou.com/login",
            },
        }
    )
    page = _FakePage()
    calls: list[str] = []

    async def _safe_goto(_page, url):
        _page.url = url

    monkeypatch.setattr(recorder, "_safe_goto", _safe_goto)

    class _Detector:
        def __init__(self, platform: str, debug: bool = False):
            self.platform = platform

        async def detect(self, page, wait_for_redirect: bool = True):
            if calls:
                return _DetectorResult("logged_in", 0.95, "post-login")
            return _DetectorResult("not_logged_in", 0.95, "pre-login")

        def needs_login(self, result):
            return result.status.value != "logged_in"

        def clear_cache(self):
            return None

    class _FakeLoginComponent:
        def __init__(self, ctx: ExecutionContext):
            self.ctx = ctx

        async def run(self, page):
            calls.append("run")
            page.url = "https://erp.91miaoshou.com/welcome"
            return LoginResult(success=True, message="ok")

    class _Loader:
        def load(self, path: str):
            assert path == "miaoshou/login"
            return {
                "name": "login",
                "platform": "miaoshou",
                "type": "login",
                "_python_component_class": _FakeLoginComponent,
            }

    monkeypatch.setattr(
        "modules.utils.login_status_detector.LoginStatusDetector",
        _Detector,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.component_loader.ComponentLoader",
        _Loader,
    )

    await recorder._auto_login(page)

    assert calls == ["run"]
    assert page.url.endswith("/welcome")


@pytest.mark.asyncio
async def test_inspector_recorder_auto_login_requires_confirmed_logged_in(monkeypatch):
    recorder = InspectorRecorder(
        {
            "platform": "miaoshou",
            "component_type": "export",
            "account_info": {
                "account_id": "acc-1",
                "login_url": "https://erp.91miaoshou.com/login",
            },
        }
    )
    page = _FakePage()

    async def _safe_goto(_page, url):
        _page.url = url

    monkeypatch.setattr(recorder, "_safe_goto", _safe_goto)

    class _Detector:
        def __init__(self, platform: str, debug: bool = False):
            self.platform = platform

        async def detect(self, page, wait_for_redirect: bool = True):
            return _DetectorResult("not_logged_in", 0.95, "still on login page")

        def needs_login(self, result):
            return True

        def clear_cache(self):
            return None

    class _FakeLoginComponent:
        def __init__(self, ctx: ExecutionContext):
            self.ctx = ctx

        async def run(self, page):
            page.url = "https://erp.91miaoshou.com/login"
            return LoginResult(success=False, message="not logged in")

    class _Loader:
        def load(self, path: str):
            return {
                "name": "login",
                "platform": "miaoshou",
                "type": "login",
                "_python_component_class": _FakeLoginComponent,
            }

    monkeypatch.setattr(
        "modules.utils.login_status_detector.LoginStatusDetector",
        _Detector,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.component_loader.ComponentLoader",
        _Loader,
    )

    with pytest.raises(RuntimeError, match="login was not confirmed"):
        await recorder._auto_login(page)


@pytest.mark.asyncio
async def test_miaoshou_login_reused_session_short_circuits():
    component = MiaoshouMiaoshouLogin(
        ExecutionContext(
            platform="miaoshou",
            account={"login_url": "https://erp.91miaoshou.com/login"},
            logger=None,
            config={"reused_session": True},
        )
    )
    page = _FakePage("https://erp.91miaoshou.com/welcome")

    result = await component.run(page)

    assert result.success is True
    assert result.message == "already logged in"
