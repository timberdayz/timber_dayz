from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from modules.core.db import CatalogFile
from modules.services.catalog_scanner import register_single_file


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


def test_register_single_file_skips_temp_development_by_default(tmp_path, monkeypatch):
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
            {"ensure_table_exists": staticmethod(lambda **_kwargs: "fact_shopee_products_daily")},
        )(),
    )
    monkeypatch.delenv("ALLOW_DEV_CATALOG_REGISTRATION", raising=False)

    dev_dir = tmp_path / "temp" / "development"
    dev_dir.mkdir(parents=True, exist_ok=True)
    file_path = dev_dir / "shopee_products_daily_20250128_case3.xlsx"
    file_path.write_text("demo", encoding="utf-8")

    file_id = register_single_file(str(file_path))

    assert file_id is None
    with Session(engine) as session:
        records = session.execute(select(CatalogFile)).scalars().all()
    assert records == []


def test_register_single_file_allows_temp_development_when_opted_in(tmp_path, monkeypatch):
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
            {"ensure_table_exists": staticmethod(lambda **_kwargs: "fact_shopee_products_daily")},
        )(),
    )
    monkeypatch.setenv("ALLOW_DEV_CATALOG_REGISTRATION", "true")

    raw_dir = tmp_path / "temp" / "development" / "2026"
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_path = raw_dir / "shopee_products_daily_20260525_000001.xlsx"
    file_path.write_text("demo", encoding="utf-8")

    file_id = register_single_file(str(file_path))

    assert file_id is not None
    with Session(engine) as session:
        record = session.execute(select(CatalogFile).where(CatalogFile.id == file_id)).scalar_one()
    assert Path(record.file_path).name == file_path.name


def test_register_single_file_reuses_legacy_absolute_path_record(tmp_path, monkeypatch):
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
            {"ensure_table_exists": staticmethod(lambda **_kwargs: "fact_tiktok_analytics_daily")},
        )(),
    )
    monkeypatch.delenv("ALLOW_DEV_CATALOG_REGISTRATION", raising=False)

    raw_dir = tmp_path / "2026"
    raw_dir.mkdir(parents=True, exist_ok=True)
    file_path = raw_dir / "tiktok_analytics_daily_20260525_000001.xlsx"
    file_path.write_text("demo", encoding="utf-8")

    first_id = register_single_file(str(file_path))
    assert first_id is not None

    with Session(engine) as session:
        existing = session.execute(select(CatalogFile).where(CatalogFile.id == first_id)).scalar_one()
        existing.file_path = str(file_path).replace("/", "\\")
        existing.file_hash = "legacy_hash_value"
        session.commit()

    second_id = register_single_file(str(file_path))

    assert second_id == first_id
    with Session(engine) as session:
        records = session.execute(select(CatalogFile)).scalars().all()
        assert len(records) == 1
        assert records[0].file_path.replace("\\", "/").endswith(file_path.name)
