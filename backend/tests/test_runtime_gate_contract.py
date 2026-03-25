import types

import pytest

from modules.apps.collection_center.executor_v2 import CollectionExecutorV2, StepExecutionError


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
async def test_executor_login_gate_requires_ready_status(monkeypatch):
    executor = CollectionExecutorV2()

    class _Detector:
        def __init__(self, platform: str, debug: bool = False):
            self.platform = platform

        async def detect(self, page, wait_for_redirect: bool = True):
            return _DetectorResult("not_logged_in", 0.95)

    monkeypatch.setattr(
        "modules.utils.login_status_detector.LoginStatusDetector",
        _Detector,
    )

    with pytest.raises(StepExecutionError, match="login gate not ready"):
        await executor._ensure_login_gate_ready(
            _FakePage("https://erp.91miaoshou.com/login"),
            "miaoshou",
        )


def test_executor_export_complete_requires_real_file(tmp_path):
    executor = CollectionExecutorV2()

    with pytest.raises(StepExecutionError, match="download file missing"):
        executor._ensure_export_complete(str(tmp_path / "missing.xlsx"))
