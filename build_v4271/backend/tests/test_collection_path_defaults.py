import importlib.util
from pathlib import Path

from click.testing import CliRunner

from modules.apps.vue_field_mapping.backend.main import ScanRequest


def _load_etl_cli_module():
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "etl_cli.py"
    spec = importlib.util.spec_from_file_location("etl_cli_module", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_etl_cli_scan_defaults_to_data_raw(monkeypatch):
    module = _load_etl_cli_module()
    captured = {}

    def fake_scan_and_register(paths):
        captured["paths"] = [str(p).replace("\\", "/") for p in paths]

        class _Result:
            seen = 0
            registered = 0
            skipped = 0

        return _Result()

    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "modules.services.catalog_scanner":
            class _FakeCatalogScannerModule:
                scan_and_register = staticmethod(fake_scan_and_register)

            return _FakeCatalogScannerModule()
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)

    runner = CliRunner()
    result = runner.invoke(module.cli, ["scan"])

    assert result.exit_code == 0
    assert len(captured["paths"]) == 1
    assert captured["paths"][0].replace("\\", "/").endswith("/data/raw")


def test_vue_field_mapping_scan_request_defaults_to_data_raw():
    request = ScanRequest()

    assert request.directories == ["data/raw"]
