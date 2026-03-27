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
    executor._infer_sub_domain_from_path = lambda file_path: ""

    processed = await CollectionExecutorV2._process_files(
        executor,
        [str(download_file)],
        platform="shopee",
        data_domains=["orders"],
        granularity="monthly",
    )

    assert processed
    assert Path(processed[0]).parent.parent == raw_dir
