import re
from pathlib import Path


def _read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def test_backend_health_version_comes_from_release_metadata():
    """版本必须**来自发布元数据**，不能是源码里写死的字符串。

    ⚠️ 旧断言是 ``VERSION 文件内容 == "v4.27.2"`` —— 把某个历史发版号钉死，
    每次发版都要改测试（改成 v7.19.3 也只是一次性糊弄）⇒ 长期红，没人跑。

    现行契约（``backend/main.py::_load_app_version``）：
    1. 优先读环境变量 ``APP_VERSION`` / ``IMAGE_TAG`` / ``RELEASE_VERSION``（发版流水线注入）；
    2. 环境变量没有才回落读 ``VERSION`` 文件；
    3. ``VERSION`` 只需是**合法版本号**，不钉死具体值。

    这样发版时 ``VERSION`` 由流水线更新即可，测试不用跟着改。
    """
    source = _read("backend/main.py")
    dockerfile = _read("Dockerfile.backend")
    version_file = Path("VERSION")

    assert version_file.exists(), "expected a VERSION file for release observability"
    version_text = version_file.read_text(encoding="utf-8").strip()
    assert re.fullmatch(
        r"v\d+\.\d+\.\d+", version_text
    ), f"VERSION 文件内容必须是 vX.Y.Z 形式，实际是 {version_text!r}"

    # 版本解析顺序：环境变量优先，VERSION 文件兜底
    assert "APP_VERSION" in source
    assert "IMAGE_TAG" in source
    assert "RELEASE_VERSION" in source
    assert "VERSION" in source
    # 应用与系统路由必须用**解析出来的** APP_VERSION（不是源码里写死的版本号）
    assert "create_fastapi_app(APP_VERSION" in source
    assert "version=APP_VERSION" in source

    # 镜像必须把 VERSION 带进去
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
