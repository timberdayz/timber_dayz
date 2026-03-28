from pathlib import Path
import types

from tools.test_component import ComponentTester


def _write_component(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("class Dummy:\n    pass\n", encoding="utf-8")


def test_component_tester_lists_only_active_components(monkeypatch, tmp_path: Path):
    comp_dir = tmp_path / "components"
    _write_component(comp_dir / "login.py")
    _write_component(comp_dir / "products_export.py")
    _write_component(comp_dir / "recorder_test_login.py")
    _write_component(comp_dir / "export.py")
    _write_component(comp_dir / "analytics_config.py")

    fake_module = types.SimpleNamespace(__path__=[str(comp_dir)])

    monkeypatch.setattr(
        "modules.apps.collection_center.component_loader.PYTHON_COMPONENT_PLATFORMS",
        {"shopee": "fake.shopee.components"},
    )
    monkeypatch.setattr(
        "tools.test_component.list_active_component_names",
        lambda: ["shopee/login"],
    )
    monkeypatch.setattr("importlib.import_module", lambda name: fake_module)

    tester = ComponentTester(platform="shopee")

    assert tester.list_components() == ["login"]
