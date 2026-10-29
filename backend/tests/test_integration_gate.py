#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""集成测试开关的单元测试。

对应的问题(2026-10-29):
``test_user_registration_integration.py`` 曾经**假通过**且**往真实业务库写测试用户**。
根因是它没有开关、默认打 ``http://localhost:8001``(那台本地服务连的是真实库),
并且用 ``return True/False`` 表示结果(pytest 只把抛异常当失败)。

这里把开关本身钉住, 保证它以后不会被人"顺手改回去"。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from integration_gate import (  # noqa: E402
    BASE_URL_VAR,
    DISPOSABLE_VAR,
    RUN_FLAG,
    IntegrationGateError,
    integration_disposable,
    integration_enabled,
    integration_requested,
    require_integration_ready,
    resolve_base_url,
    skip_reason,
)

_GATE_VARS = (RUN_FLAG, DISPOSABLE_VAR, BASE_URL_VAR)


@pytest.fixture(autouse=True)
def _clean_gate_env(monkeypatch):
    """每个用例都从「全都没开」的状态出发。"""
    for name in _GATE_VARS:
        monkeypatch.delenv(name, raising=False)
    yield


def test_integration_is_disabled_by_default():
    """默认状态: 既没请求运行, 也没确认目标可丢弃。"""
    assert integration_requested() is False
    assert integration_disposable() is False
    assert integration_enabled() is False


def test_single_flag_is_not_enough(monkeypatch):
    """只给「运行」开关不够 —— 必须同时确认目标可丢弃。"""
    monkeypatch.setenv(RUN_FLAG, "1")
    assert integration_requested() is True
    assert integration_enabled() is False

    monkeypatch.setenv(DISPOSABLE_VAR, "yes")
    assert integration_enabled() is True


def test_base_url_has_no_default():
    """**没有默认地址** —— 旧实现的默认 ``http://localhost:8001`` 连的是真实业务库。"""
    with pytest.raises(IntegrationGateError) as exc_info:
        resolve_base_url()
    assert BASE_URL_VAR in str(exc_info.value)


def test_base_url_is_normalised(monkeypatch):
    """尾部斜杠要去掉, 免得拼出 ``//api``。"""
    monkeypatch.setenv(BASE_URL_VAR, "http://127.0.0.1:8001/")
    assert resolve_base_url() == "http://127.0.0.1:8001"


def test_base_url_must_be_http(monkeypatch):
    monkeypatch.setenv(BASE_URL_VAR, "127.0.0.1:8001")
    with pytest.raises(IntegrationGateError):
        resolve_base_url()


def test_require_ready_fails_when_not_enabled():
    """没开启就调用 ⇒ 硬失败(而不是静默跳过或假装通过)。"""
    with pytest.raises(IntegrationGateError):
        require_integration_ready()


def test_require_ready_fails_without_base_url(monkeypatch):
    """两个开关都给了但没给地址 ⇒ 仍然硬失败。"""
    monkeypatch.setenv(RUN_FLAG, "1")
    monkeypatch.setenv(DISPOSABLE_VAR, "1")
    with pytest.raises(IntegrationGateError):
        require_integration_ready()


def test_require_ready_returns_base_url(monkeypatch):
    monkeypatch.setenv(RUN_FLAG, "1")
    monkeypatch.setenv(DISPOSABLE_VAR, "1")
    monkeypatch.setenv(BASE_URL_VAR, "http://127.0.0.1:8001")
    assert require_integration_ready() == "http://127.0.0.1:8001"


def test_skip_reason_mentions_every_missing_switch():
    reason = skip_reason()
    assert RUN_FLAG in reason
    assert DISPOSABLE_VAR in reason
    assert BASE_URL_VAR in reason


def test_integration_module_is_skipped_by_default():
    """默认状态下, 集成测试模块在**导入阶段**就跳过 ⇒ 一个字节都不会写进任何库。"""
    sys.modules.pop("test_user_registration_integration", None)
    with pytest.raises(BaseException) as exc_info:
        importlib.import_module("test_user_registration_integration")
    assert type(exc_info.value).__name__ == "Skipped", (
        f"期望 pytest 的 Skipped 异常, 实际 {type(exc_info.value).__name__}"
    )


def test_integration_module_declares_integration_marker(monkeypatch):
    """集成测试模块必须带 ``integration`` 专项标记, 便于 ``-m`` 过滤。"""
    monkeypatch.setenv(RUN_FLAG, "1")
    monkeypatch.setenv(DISPOSABLE_VAR, "1")
    monkeypatch.setenv(BASE_URL_VAR, "http://127.0.0.1:65535")
    sys.modules.pop("test_user_registration_integration", None)
    module = importlib.import_module("test_user_registration_integration")
    marks = module.pytestmark
    if not isinstance(marks, (list, tuple)):
        marks = [marks]
    marker_names = {getattr(mark, "name", None) for mark in marks}
    assert "integration" in marker_names
