from io import BytesIO

import run


class _FakeResponse:
    def __init__(self, status=200, body=b'{"status":"ready"}'):
        self.status = status
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_wait_for_service_uses_http_readiness_probe(monkeypatch):
    calls = []

    def fake_urlopen(url, timeout):
        calls.append((url, timeout))
        return _FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(run.time, "sleep", lambda _seconds: None)

    assert run.wait_for_service(8001, "后端API", 1) is True
    assert calls == [("http://127.0.0.1:8001/healthz/ready", 2)]
