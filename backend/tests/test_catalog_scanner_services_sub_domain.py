from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from modules.core.db import CatalogFile
from modules.core.file_naming import StandardFileName
from modules.services.catalog_scanner import register_single_file
from modules.services.metadata_manager import MetadataManager


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def test_register_single_file_keeps_services_sub_domain_empty_when_metadata_is_missing(
    tmp_path,
    monkeypatch,
):
    import backend.services.platform_table_manager as platform_table_manager_module
    from modules.services import catalog_scanner as catalog_scanner_module

    engine = create_engine(f"sqlite:///{tmp_path / 'catalog.db'}", future=True)
    CatalogFile.__table__.create(engine)
    monkeypatch.setattr(catalog_scanner_module, "_get_engine", lambda: engine)
    monkeypatch.setattr(
        platform_table_manager_module,
        "get_platform_table_manager",
        lambda _session: type(
            "_NoopTableManager",
            (),
            {"ensure_table_exists": staticmethod(lambda **_kwargs: "fact_shopee_services_daily")},
        )(),
    )

    raw_dir = tmp_path / "data" / "raw" / "2026"
    raw_dir.mkdir(parents=True, exist_ok=True)

    file_path = raw_dir / StandardFileName.generate(
        source_platform="shopee",
        data_domain="services",
        granularity="daily",
        timestamp="20260413_184710",
        ext="xlsx",
    )
    file_path.write_text("demo", encoding="utf-8")

    MetadataManager.create_meta_file(
        file_path,
        business_metadata={
            "source_platform": "shopee",
            "data_domain": "services",
            "sub_domain": "",
            "date_from": "2026-04-12",
            "date_to": "2026-04-12",
        },
        collection_info={
            "method": "python_component",
            "collection_platform": "shopee",
            "account": "acc",
            "shop_id": "shop",
            "original_path": r"temp\downloads\task-1\shopee\acc\shop\services\daily\traffic_overview.xlsx",
            "collected_at": datetime.now().isoformat(),
        },
    )

    file_id = register_single_file(str(file_path))

    assert file_id is not None

    with Session(engine) as session:
        record = session.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        ).scalar_one()

    assert record.data_domain == "services"
    assert record.sub_domain in (None, "")
