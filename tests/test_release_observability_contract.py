from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_backend_health_version_comes_from_release_metadata():
    source = _read("backend/main.py")
    dockerfile = _read("Dockerfile.backend")
    version_file = Path("VERSION")

    assert version_file.exists(), "expected a VERSION file for release observability"
    assert version_file.read_text(encoding="utf-8").strip() == "v4.27.2"
    assert '"version": "4.19.0"' not in source
    assert "APP_VERSION" in source
    assert "COPY VERSION /app/VERSION" in dockerfile


def test_nginx_exposes_backend_openapi_and_docs_routes():
    source = _read("nginx/nginx.prod.conf")

    assert "location = /openapi.json" in source
    assert "/api/openapi.json" in source
    assert "location = /docs" in source
    assert "location = /redoc" in source


def test_frontend_default_title_uses_xihong_branding():
    source = _read("frontend/index.html")

    assert "<title>西虹ERP系统</title>" in source
    assert "智能字段映射审核系统" not in source
