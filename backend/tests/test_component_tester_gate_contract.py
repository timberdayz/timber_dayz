from pathlib import Path
import types

import pytest

from tools.test_component import ComponentTestResult, ComponentTester, TestStatus as _TestStatus


class _DetectorResult:
    def __init__(self, status: str, confidence: float):
        self.status = types.SimpleNamespace(value=status)
        self.confidence = confidence
        self.reason = "stub"
        self.detected_by = "stub"
        self.detection_time_ms = 1
        self.matched_pattern = "stub"


class _FakePage:
    def __init__(self, url: str):
        self.url = url


@pytest.mark.asyncio
async def test_component_tester_blocks_export_until_login_ready(monkeypatch):
    tester = ComponentTester(platform="miaoshou", account_id="acc-1")
    result = ComponentTestResult(
        component_name="export",
        platform="miaoshou",
        status=_TestStatus.PENDING,
    )

    class _Detector:
        def __init__(self, platform: str, debug: bool = False):
            self.platform = platform

        async def detect(self, page, wait_for_redirect: bool = True):
            return _DetectorResult("not_logged_in", 0.95)

    monkeypatch.setattr(
        "modules.utils.login_status_detector.LoginStatusDetector",
        _Detector,
    )

    ok = await tester._check_login_gate(
        page=_FakePage("https://erp.91miaoshou.com/login"),
        result=result,
        component_name="miaoshou/login",
    )

    assert ok is False
    assert result.phase == "login"
    assert "login gate not ready" in result.error


def test_component_tester_marks_export_failed_without_downloaded_file(tmp_path: Path):
    tester = ComponentTester(platform="miaoshou", account_id="acc-1")
    result = ComponentTestResult(
        component_name="export",
        platform="miaoshou",
        status=_TestStatus.PENDING,
    )

    ok = tester._check_export_complete_gate(
        file_path=str(tmp_path / "missing.xlsx"),
        result=result,
        component_name="miaoshou/export",
    )

    assert ok is False
    assert result.phase == "export"
    assert result.error == "download file missing"
