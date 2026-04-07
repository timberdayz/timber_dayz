from modules.components.base import ExecutionContext
from modules.components.export.base import build_standard_output_root


def test_build_standard_output_root_prefers_downloads_path_from_context():
    ctx = ExecutionContext(
        platform="shopee",
        account={"label": "demo-account", "store_name": "demo-shop"},
        config={"downloads_path": "work/downloads", "shop_name": "demo-shop"},
    )

    path = build_standard_output_root(ctx, data_type="orders", granularity="monthly")

    assert str(path).replace("\\", "/").startswith("work/downloads/")


def test_build_standard_output_root_falls_back_to_downloads_dir(monkeypatch, tmp_path):
    import modules.components.export.base as export_base_module

    monkeypatch.setattr(export_base_module, "get_downloads_dir", lambda: tmp_path / "downloads", raising=False)

    ctx = ExecutionContext(
        platform="tiktok",
        account={"label": "demo-account", "store_name": "demo-shop"},
        config={"shop_name": "demo-shop"},
    )

    path = build_standard_output_root(ctx, data_type="services", granularity="daily")

    normalized = str(path).replace("\\", "/")
    assert normalized.startswith(str((tmp_path / "downloads")).replace("\\", "/"))
