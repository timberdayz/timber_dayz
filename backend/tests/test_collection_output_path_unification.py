from pathlib import Path

import pytest

from modules.core.db.schema import CatalogFile
from modules.core.file_naming import StandardFileName
from backend.services import file_path_resolver as resolver_module
from backend.services.file_path_resolver import FilePathResolver
from modules.apps.collection_center import executor_v2 as executor_module
from modules.apps.collection_center.executor_v2 import CollectionExecutorV2


def test_catalog_file_defaults_to_data_raw_source():
    source_column = CatalogFile.__table__.c.source

    assert source_column.default is not None
    assert source_column.default.arg == "data/raw"


def test_file_path_resolver_rebuilds_standard_filename_into_data_raw_year_dir(tmp_path, monkeypatch):
    raw_dir = tmp_path / "data" / "raw"
    monkeypatch.setattr(resolver_module, "get_data_raw_dir", lambda: raw_dir, raising=False)

    filename = StandardFileName.generate(
        source_platform="shopee",
        data_domain="orders",
        granularity="monthly",
        timestamp="20260327_123456",
    )

    resolver = FilePathResolver()

    rebuilt = resolver.rebuild_file_path(filename)

    assert rebuilt == str(raw_dir / "2026" / filename).replace("\\", "/")


def test_standard_file_name_parse_supports_orders_sub_domain_variants():
    parsed = StandardFileName.parse("miaoshou_orders_tiktok_weekly_20260331_140511.xls")

    assert parsed["source_platform"] == "miaoshou"
    assert parsed["data_domain"] == "orders"
    assert parsed["sub_domain"] == "tiktok"
    assert parsed["granularity"] == "weekly"


def test_file_path_resolver_prefers_data_raw_before_legacy_temp_outputs(tmp_path, monkeypatch):
    raw_dir = tmp_path / "data" / "raw"
    legacy_dir = tmp_path / "temp" / "outputs"
    downloads_dir = tmp_path / "downloads"
    input_dir = tmp_path / "data" / "input"

    monkeypatch.setattr(resolver_module, "get_data_raw_dir", lambda: raw_dir, raising=False)
    monkeypatch.setattr(resolver_module, "get_downloads_dir", lambda: downloads_dir, raising=False)
    monkeypatch.setattr(resolver_module, "get_data_input_dir", lambda: input_dir, raising=False)
    monkeypatch.setattr(resolver_module, "get_output_dir", lambda: legacy_dir, raising=False)

    filename = StandardFileName.generate(
        source_platform="tiktok",
        data_domain="services",
        granularity="daily",
        sub_domain="agent",
        timestamp="20260327_123456",
    )

    raw_file = raw_dir / "2026" / filename
    legacy_file = legacy_dir / "legacy" / filename
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    legacy_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text("raw", encoding="utf-8")
    legacy_file.write_text("legacy", encoding="utf-8")

    resolver = FilePathResolver()

    locations = resolver.find_file_locations(filename)

    assert locations
    assert Path(locations[0]).resolve() == raw_file.resolve()


@pytest.mark.asyncio
async def test_executor_process_files_uses_configured_data_raw_dir(tmp_path, monkeypatch):
    raw_dir = tmp_path / "custom-raw-root"
    download_file = tmp_path / "download.xlsx"
    download_file.write_text("demo", encoding="utf-8")

    monkeypatch.setattr(executor_module, "get_data_raw_dir", lambda: raw_dir, raising=False)

    import modules.services.catalog_scanner as catalog_scanner_module
    from modules.services.metadata_manager import MetadataManager

    monkeypatch.setattr(catalog_scanner_module, "register_single_file", lambda file_path: 123)
    monkeypatch.setattr(
        MetadataManager,
        "create_meta_file",
        staticmethod(
            lambda file_path, business_metadata, collection_info: Path(str(file_path) + ".meta.json")
        ),
    )

    executor = CollectionExecutorV2.__new__(CollectionExecutorV2)
    executor._infer_data_domain_from_path = lambda file_path, data_domains, idx: data_domains[idx]
    executor._infer_sub_domain_from_path = lambda file_path, data_domain=None: ""

    processed = await CollectionExecutorV2._process_files(
        executor,
        [str(download_file)],
        platform="shopee",
        data_domains=["orders"],
        granularity="monthly",
    )

    assert processed
    assert Path(processed[0]).parent.parent == raw_dir


def test_executor_infers_orders_sub_domain_from_download_path():
    executor = CollectionExecutorV2.__new__(CollectionExecutorV2)

    inferred = CollectionExecutorV2._infer_sub_domain_from_path(
        executor,
        r"temp\downloads\task-1\miaoshou\acc\shop\orders\tiktok\manual\export.xls",
        data_domain="orders",
    )

    assert inferred == "tiktok"


def test_executor_infers_services_ai_assistant_without_collapsing_to_agent():
    executor = CollectionExecutorV2.__new__(CollectionExecutorV2)

    inferred = CollectionExecutorV2._infer_sub_domain_from_path(
        executor,
        r"temp\downloads\task-1\tiktok\acc\shop\services\ai_assistant\daily\export.xlsx",
        data_domain="services",
    )

    assert inferred == "ai_assistant"


def test_executor_infers_analytics_from_traffic_overview_path_without_false_services_match():
    executor = CollectionExecutorV2.__new__(CollectionExecutorV2)

    inferred = CollectionExecutorV2._infer_data_domain_from_path(
        executor,
        r"temp\downloads\task-1\shopee\zewei_toys.sg\zewei_toys.sg__1407964586\analytics\daily\traffic_overview_20260412_20260412.xlsx",
        data_domains=["services", "services", "analytics"],
        index=0,
    )

    assert inferred == "analytics"


def test_executor_does_not_infer_orders_sub_domain_from_platform_segment_for_non_orders_domain():
    executor = CollectionExecutorV2.__new__(CollectionExecutorV2)

    inferred = CollectionExecutorV2._infer_sub_domain_from_path(
        executor,
        r"temp\downloads\task-1\shopee\zewei_toys.sg\zewei_toys.sg__1407964586\analytics\daily\traffic_overview_20260412_20260412.xlsx",
        data_domain="analytics",
    )

    assert inferred == ""


@pytest.mark.asyncio
async def test_executor_process_files_rejects_invalid_services_platform_sub_domain(tmp_path, monkeypatch):
    raw_dir = tmp_path / "custom-raw-root"
    download_root = tmp_path / "temp" / "downloads" / "task-1" / "tiktok" / "acc" / "shop" / "services" / "monthly"
    download_root.mkdir(parents=True, exist_ok=True)
    download_file = download_root / "service_export.xlsx"
    download_file.write_text("demo", encoding="utf-8")

    monkeypatch.setattr(executor_module, "get_data_raw_dir", lambda: raw_dir, raising=False)

    import modules.services.catalog_scanner as catalog_scanner_module
    from modules.services.metadata_manager import MetadataManager

    registered = []
    monkeypatch.setattr(catalog_scanner_module, "register_single_file", lambda file_path: registered.append(file_path))
    monkeypatch.setattr(
        MetadataManager,
        "create_meta_file",
        staticmethod(lambda file_path, business_metadata, collection_info: Path(str(file_path) + ".meta.json")),
    )

    executor = CollectionExecutorV2.__new__(CollectionExecutorV2)
    executor._infer_data_domain_from_path = lambda file_path, data_domains, idx: "services"
    executor._infer_sub_domain_from_path = lambda file_path, data_domain=None: "tiktok"

    processed = await CollectionExecutorV2._process_files(
        executor,
        [str(download_file)],
        platform="tiktok",
        data_domains=["services"],
        granularity="monthly",
        account={"label": "acc", "shop_id": "shop"},
        date_range={"start_date": "2026-04-12", "end_date": "2026-04-12"},
    )

    assert processed == []
    assert registered == []
    assert not any(raw_dir.rglob("*.xlsx"))
    rejected_files = list((tmp_path / "temp").rglob("service_export.xlsx"))
    assert rejected_files


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "data_domain", "download_relative_path", "expected_prefix"),
    [
        (
            "shopee",
            "products",
            Path("temp/downloads/task-1/shopee/acc/shop/products/daily/parentskudetail.20260412_20260412.xlsx"),
            "shopee_products_daily_",
        ),
        (
            "shopee",
            "analytics",
            Path("temp/downloads/task-1/shopee/acc/shop/analytics/daily/traffic_overview_20260412_20260412.xlsx"),
            "shopee_analytics_daily_",
        ),
        (
            "tiktok",
            "products",
            Path("temp/downloads/task-1/tiktok/acc/shop/products/daily/product_list.xlsx"),
            "tiktok_products_daily_",
        ),
        (
            "tiktok",
            "analytics",
            Path("temp/downloads/task-1/tiktok/acc/shop/analytics/daily/Overview_My Business Performance_20260413105132.xlsx"),
            "tiktok_analytics_daily_",
        ),
    ],
)
async def test_executor_process_files_does_not_add_platform_sub_domain_for_products_or_analytics(
    tmp_path,
    monkeypatch,
    platform: str,
    data_domain: str,
    download_relative_path: Path,
    expected_prefix: str,
):
    raw_dir = tmp_path / "custom-raw-root"
    download_file = tmp_path / download_relative_path
    download_file.parent.mkdir(parents=True, exist_ok=True)
    download_file.write_text("demo", encoding="utf-8")

    monkeypatch.setattr(executor_module, "get_data_raw_dir", lambda: raw_dir, raising=False)

    captured = {}

    import modules.services.catalog_scanner as catalog_scanner_module
    from modules.services.metadata_manager import MetadataManager

    monkeypatch.setattr(catalog_scanner_module, "register_single_file", lambda file_path: 123)

    def _capture_meta(file_path, business_metadata, collection_info):
        captured["business_metadata"] = business_metadata
        captured["collection_info"] = collection_info
        return Path(str(file_path) + ".meta.json")

    monkeypatch.setattr(
        MetadataManager,
        "create_meta_file",
        staticmethod(_capture_meta),
    )

    executor = CollectionExecutorV2.__new__(CollectionExecutorV2)

    processed = await CollectionExecutorV2._process_files(
        executor,
        [str(download_file)],
        platform=platform,
        data_domains=[data_domain],
        granularity="daily",
        account={"label": "acc", "shop_id": "shop"},
        date_range={"start_date": "2026-04-12", "end_date": "2026-04-12"},
    )

    assert processed
    generated_name = Path(processed[0]).name
    assert generated_name.startswith(expected_prefix)

    parsed = StandardFileName.parse(generated_name)
    assert parsed["source_platform"] == platform
    assert parsed["data_domain"] == data_domain
    assert parsed["sub_domain"] == ""
    assert parsed["granularity"] == "daily"

    assert captured["business_metadata"]["source_platform"] == platform
    assert captured["business_metadata"]["data_domain"] == data_domain
    assert captured["business_metadata"]["sub_domain"] == ""
    assert captured["collection_info"]["collection_platform"] == platform
    assert captured["collection_info"]["original_path"] == str(download_file)


@pytest.mark.asyncio
async def test_executor_process_files_normalizes_miaoshou_orders_into_business_platform_files(tmp_path, monkeypatch):
    raw_dir = tmp_path / "custom-raw-root"
    download_root = tmp_path / "temp" / "downloads" / "task-1" / "miaoshou" / "acc" / "shop" / "orders" / "tiktok" / "manual"
    download_root.mkdir(parents=True, exist_ok=True)
    download_file = download_root / "export.xls"
    download_file.write_text("demo", encoding="utf-8")

    monkeypatch.setattr(executor_module, "get_data_raw_dir", lambda: raw_dir, raising=False)

    captured = {}

    import modules.services.catalog_scanner as catalog_scanner_module
    from modules.services.metadata_manager import MetadataManager

    monkeypatch.setattr(catalog_scanner_module, "register_single_file", lambda file_path: 123)

    def _capture_meta(file_path, business_metadata, collection_info):
        captured["business_metadata"] = business_metadata
        captured["collection_info"] = collection_info
        return Path(str(file_path) + ".meta.json")

    monkeypatch.setattr(
        MetadataManager,
        "create_meta_file",
        staticmethod(_capture_meta),
    )

    executor = CollectionExecutorV2.__new__(CollectionExecutorV2)
    executor._infer_data_domain_from_path = lambda file_path, data_domains, idx: "orders"

    processed = await CollectionExecutorV2._process_files(
        executor,
        [str(download_file)],
        platform="miaoshou",
        data_domains=["orders"],
        granularity="weekly",
        account={"label": "acc", "shop_id": "shop"},
        date_range={"start_date": "2026-03-08", "end_date": "2026-03-14"},
    )

    assert processed
    assert Path(processed[0]).name.startswith("tiktok_orders_weekly_")
    assert captured["business_metadata"]["source_platform"] == "tiktok"
    assert captured["business_metadata"]["sub_domain"] == ""
    assert captured["collection_info"]["collection_platform"] == "miaoshou"


def test_inventory_domain_resolves_snapshot_even_when_task_granularity_is_monthly():
    from modules.apps.collection_center.landing_semantics import resolve_business_granularity

    assert resolve_business_granularity(data_domain="inventory", task_granularity="monthly") == "snapshot"


def test_orders_domain_keeps_task_granularity():
    from modules.apps.collection_center.landing_semantics import resolve_business_granularity

    assert resolve_business_granularity(data_domain="orders", task_granularity="monthly") == "monthly"


@pytest.mark.asyncio
async def test_executor_process_files_forces_inventory_snapshot_granularity(tmp_path, monkeypatch):
    raw_dir = tmp_path / "custom-raw-root"
    download_file = tmp_path / "inventory_source.xlsx"
    download_file.write_text("demo", encoding="utf-8")

    monkeypatch.setattr(executor_module, "get_data_raw_dir", lambda: raw_dir, raising=False)

    captured = {}

    import modules.services.catalog_scanner as catalog_scanner_module
    from modules.services.metadata_manager import MetadataManager

    monkeypatch.setattr(catalog_scanner_module, "register_single_file", lambda file_path: 123)

    def _capture_meta(file_path, business_metadata, collection_info):
        captured["file_path"] = file_path
        captured["business_metadata"] = business_metadata
        captured["collection_info"] = collection_info
        return Path(str(file_path) + ".meta.json")

    monkeypatch.setattr(
        MetadataManager,
        "create_meta_file",
        staticmethod(_capture_meta),
    )

    executor = CollectionExecutorV2.__new__(CollectionExecutorV2)
    executor._infer_data_domain_from_path = lambda file_path, data_domains, idx: "inventory"
    executor._infer_sub_domain_from_path = lambda file_path, data_domain=None: ""

    processed = await CollectionExecutorV2._process_files(
        executor,
        [str(download_file)],
        platform="miaoshou",
        data_domains=["inventory"],
        granularity="monthly",
        account={"label": "acc", "shop_id": "shop"},
        date_range={"start_date": "2026-04-12", "end_date": "2026-04-12"},
    )

    assert processed
    generated_name = Path(processed[0]).name
    parsed = StandardFileName.parse(generated_name)

    assert parsed["data_domain"] == "inventory"
    assert parsed["granularity"] == "snapshot"
    assert captured["business_metadata"]["granularity"] == "snapshot"
