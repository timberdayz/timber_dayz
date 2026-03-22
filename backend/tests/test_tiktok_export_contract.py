import json
from pathlib import Path

from modules.components.base import ExecutionContext
from modules.platforms.tiktok.components.export import TiktokExporterComponent


def _ctx():
    return ExecutionContext(
        platform="tiktok",
        account={"label": "acc", "store_name": "shop", "region": "SG"},
        logger=None,
        config={"shop_region": "MY"},
    )


def test_tiktok_export_manifest_prefers_runtime_shop_region(tmp_path: Path):
    component = TiktokExporterComponent(_ctx())
    target = tmp_path / "export.xlsx"
    target.write_text("dummy", encoding="utf-8")

    component._write_manifest(
        target=target,
        cfg=component.ctx.config or {},
        account_label="acc",
        shop_name="shop",
        data_type="products",
    )

    manifest = json.loads((Path(str(target) + ".json")).read_text(encoding="utf-8"))

    assert manifest["region"] == "MY"


def test_tiktok_export_infers_analytics_domain_not_traffic():
    component = TiktokExporterComponent(_ctx())

    assert component._infer_data_type("https://seller.tiktokshopglobalselling.com/data-overview", "products") == "analytics"
