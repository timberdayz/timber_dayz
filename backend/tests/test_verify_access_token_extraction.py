"""契约测试：访问令牌提取单点门禁(scripts/verify_access_token_extraction.py)。"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_access_token_extraction.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("verify_access_token_extraction", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gate():
    return _load_gate()


def test_gate_script_exists():
    assert SCRIPT.exists()


def test_repository_has_single_token_extraction_point(gate):
    violations = gate.scan(ROOT, ["backend"])
    assert violations == [], "存在自行提取令牌的实现：\n" + "\n".join(violations)


def test_detects_manual_cookie_read(gate, tmp_path):
    target = tmp_path / "backend" / "svc" / "thing.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "def read(request):\n"
        "    return request.cookies.get('access_token')\n",
        encoding="utf-8",
    )
    violations = gate.scan(tmp_path, ["backend"])
    assert any("cookie access_token" in v for v in violations), violations


def test_detects_manual_header_read(gate, tmp_path):
    target = tmp_path / "backend" / "svc" / "thing.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "def read(request):\n"
        "    return request.headers.get('Authorization', '')\n",
        encoding="utf-8",
    )
    violations = gate.scan(tmp_path, ["backend"])
    assert any("Authorization header" in v for v in violations), violations


def test_ssot_module_is_allowed(gate, tmp_path):
    ssot = tmp_path / gate.SSOT_MODULE
    ssot.parent.mkdir(parents=True, exist_ok=True)
    ssot.write_text(
        "def extract_access_token(request):\n"
        "    return request.cookies.get('access_token')\n",
        encoding="utf-8",
    )
    violations = gate.scan(tmp_path, ["backend"])
    assert violations == [], violations


def test_comments_are_not_flagged(gate, tmp_path):
    target = tmp_path / "backend" / "svc" / "thing.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# 历史说明：以前这里写的是 request.cookies.get('access_token')\n"
        "def read(request):\n"
        "    return None\n",
        encoding="utf-8",
    )
    violations = gate.scan(tmp_path, ["backend"])
    assert violations == [], violations


def test_ssot_function_handles_all_sources():
    """SSOT 函数必须覆盖 cookie / header / query 三种来源。"""
    from backend.dependencies.auth import extract_access_token

    class _Cookies(dict):
        def get(self, key, default=None):
            return dict.get(self, key, default)

    class _Request:
        def __init__(self, cookies=None, headers=None):
            self.cookies = _Cookies(cookies or {})
            self.headers = headers or {}

    class _WebSocket:
        def __init__(self, cookies=None):
            self.cookies = _Cookies(cookies or {})

    class _Credentials:
        def __init__(self, token):
            self.credentials = token

    # query 优先
    assert (
        extract_access_token(
            request=_Request(cookies={"access_token": "c"}),
            websocket=_WebSocket({"access_token": "w"}),
            query_token="q",
        )
        == "q"
    )
    # cookie 优先于 header
    assert (
        extract_access_token(
            request=_Request(
                cookies={"access_token": "c"}, headers={"Authorization": "Bearer h"}
            )
        )
        == "c"
    )
    # header 兜底
    assert (
        extract_access_token(
            request=_Request(headers={"Authorization": "Bearer h"})
        )
        == "h"
    )
    # credentials 兜底
    assert extract_access_token(credentials=_Credentials("t")) == "t"
    # websocket cookie
    assert extract_access_token(websocket=_WebSocket({"access_token": "w"})) == "w"
    # 全都没有
    assert extract_access_token(request=_Request()) is None
