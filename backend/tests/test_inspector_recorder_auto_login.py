import types

import pytest

from modules.components.base import ExecutionContext
from modules.components.login.base import LoginResult
from modules.platforms.miaoshou.components.login import MiaoshouLogin
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
async def test_inspector_recorder_auto_login_prefers_versioned_login_component(monkeypatch):
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

    class _FakeVersion:
        id = 91
        version = "1.0.2"
        file_path = "modules/platforms/miaoshou/components/login_v1_0_2.py"

    class _FakeVersionService:
        def __init__(self, db):
            self.db = db

        def select_version_for_use(self, component_name: str, force_version=None, enable_ab_test=True):
            assert component_name == "miaoshou/login"
            return _FakeVersion()

    class _FakeSession:
        def close(self):
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
            raise AssertionError("should prefer versioned login component from file_path")

        def load_python_component_from_path(self, file_path: str, version_id=None, platform=None, component_type=None):
            assert file_path.endswith("login_v1_0_2.py")
            assert version_id == 91
            assert platform == "miaoshou"
            assert component_type == "login"
            return _FakeLoginComponent

    monkeypatch.setattr(
        "modules.utils.login_status_detector.LoginStatusDetector",
        _Detector,
    )
    monkeypatch.setattr(
        "modules.apps.collection_center.component_loader.ComponentLoader",
        _Loader,
    )
    monkeypatch.setattr(
        "backend.models.database.SessionLocal",
        lambda: _FakeSession(),
    )
    monkeypatch.setattr(
        "backend.services.component_version_service.ComponentVersionService",
        _FakeVersionService,
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
    component = MiaoshouLogin(
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


class _FakePersistentContext:
    async def add_init_script(self, _script: str) -> None:
        return None


class _FakeChromium:
    def __init__(self, captured: dict):
        self._captured = captured

    async def launch_persistent_context(self, **kwargs):
        self._captured.update(kwargs)
        return _FakePersistentContext()


class _FakePlaywright:
    def __init__(self, captured: dict):
        self.chromium = _FakeChromium(captured)


def _patch_profile_and_fingerprint(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "modules.utils.sessions.session_manager.SessionManager.get_persistent_profile_path",
        lambda self, platform, account_id: tmp_path / platform / account_id,
    )
    monkeypatch.setattr(
        "modules.utils.sessions.device_fingerprint.DeviceFingerprintManager.get_or_create_fingerprint",
        lambda self, platform, account_id, account_info: {
            "viewport": {"width": 1280, "height": 720},
            "user_agent": "UA",
            "locale": "zh-CN",
            "timezone": "Asia/Shanghai",
        },
    )


@pytest.mark.asyncio
async def test_inspector_recorder_profile_path_uses_main_account_id(monkeypatch, tmp_path):
    """profile 路径必须按**主账号**维度（规则 B：profiles/<平台>/<主账号ID>/）。

    ``account_info['account_id']`` 是**店铺账号** ID —— 用它会生产出
    ``profiles/<平台>/<店铺账号ID>/``，而那正是 ``legacy_shop_artifact_cleanup``
    认定的「店铺级遗留物」目录；采集侧按主账号 ID 开 profile，读不到它，
    于是「巡店登录 → 采集复用」这条链路会断。
    """
    captured: dict = {}
    _patch_profile_and_fingerprint(monkeypatch, tmp_path)

    recorder = InspectorRecorder(
        {
            "platform": "miaoshou",
            "component_type": "export",
            "account_info": {
                "account_id": "shop-acc-1",
                "main_account_id": "main-acc-1",
                "login_url": "https://erp.91miaoshou.com/login",
            },
        }
    )

    await recorder._create_context(_FakePlaywright(captured))

    user_data_dir = str(captured["user_data_dir"]).replace("\\", "/")
    assert user_data_dir.endswith("miaoshou/main-acc-1")
    assert "shop-acc-1" not in user_data_dir


@pytest.mark.asyncio
async def test_inspector_recorder_profile_path_falls_back_to_shop_account_id(monkeypatch, tmp_path):
    """``main_account_id`` 缺失时回退到店铺账号 ID，并留下告警。

    回退是兜底，不是常态 —— 采集侧始终按主账号 ID 开 profile，
    所以这里必须显式告警，避免「录的时候登录态存到了另一个目录」。
    """
    captured: dict = {}
    _patch_profile_and_fingerprint(monkeypatch, tmp_path)

    recorder = InspectorRecorder(
        {
            "platform": "miaoshou",
            "component_type": "export",
            "account_info": {
                "account_id": "shop-acc-1",
                "login_url": "https://erp.91miaoshou.com/login",
            },
        }
    )

    await recorder._create_context(_FakePlaywright(captured))

    user_data_dir = str(captured["user_data_dir"]).replace("\\", "/")
    assert user_data_dir.endswith("miaoshou/shop-acc-1")
