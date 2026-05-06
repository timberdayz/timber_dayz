from __future__ import annotations


def test_schema_module_imports() -> None:
    import modules.core.db.schema as schema  # noqa: F401


def test_schema_public_symbols_preserve_identity() -> None:
    from modules.core.db import Base as package_base
    from modules.core.db.schema import Base, CatalogFile, DimPlatform, FactOrderAmount
    from modules.core.db.schema_parts.base import Base as split_base
    from modules.core.db.schema_parts.dimensions import DimPlatform as split_dim_platform
    from modules.core.db.schema_parts.facts import (
        CatalogFile as split_catalog_file,
        FactOrderAmount as split_fact_order_amount,
    )

    assert Base is package_base
    assert Base is split_base
    assert DimPlatform is split_dim_platform
    assert CatalogFile is split_catalog_file
    assert FactOrderAmount is split_fact_order_amount


def test_schema_collection_slice_public_symbols_preserve_identity() -> None:
    from modules.core.db.schema import (
        ApprovalInstance,
        CollectionTask,
        TaskCenterTask,
        TrainingProgram,
    )
    from modules.core.db.schema_parts.collection import (
        ApprovalInstance as split_approval_instance,
        CollectionTask as split_collection_task,
        TaskCenterTask as split_task_center_task,
        TrainingProgram as split_training_program,
    )

    assert CollectionTask is split_collection_task
    assert TaskCenterTask is split_task_center_task
    assert ApprovalInstance is split_approval_instance
    assert TrainingProgram is split_training_program


def test_schema_platform_slice_public_symbols_preserve_identity() -> None:
    from modules.core.db.schema import MainAccount, PlatformAccount, ShopAccount
    from modules.core.db.schema_parts.platform import (
        MainAccount as split_main_account,
        PlatformAccount as split_platform_account,
        ShopAccount as split_shop_account,
    )

    assert PlatformAccount is split_platform_account
    assert MainAccount is split_main_account
    assert ShopAccount is split_shop_account


def test_schema_data_platform_slice_public_symbols_preserve_identity() -> None:
    from modules.core.db.schema import DataFile, FieldMapping, MappingSession
    from modules.core.db.schema_parts.data_platform import (
        DataFile as split_data_file,
        FieldMapping as split_field_mapping,
        MappingSession as split_mapping_session,
    )

    assert DataFile is split_data_file
    assert FieldMapping is split_field_mapping
    assert MappingSession is split_mapping_session


def test_schema_business_slice_public_symbols_preserve_identity() -> None:
    from modules.core.db.schema import JournalEntry, POHeader, SystemConfig
    from modules.core.db.schema_parts.business import (
        JournalEntry as split_journal_entry,
        POHeader as split_po_header,
        SystemConfig as split_system_config,
    )

    assert POHeader is split_po_header
    assert JournalEntry is split_journal_entry
    assert SystemConfig is split_system_config


def test_schema_metadata_contains_representative_tables() -> None:
    from modules.core.db.schema import Base

    assert Base.metadata.tables, "Schema import should register tables into Base.metadata"

    required_table_names = [
        "core.dim_platforms",
        "core.dim_shops",
        "core.accounts",
        "catalog_files",
        "core.data_quarantine",
        "fact_order_amounts",
        "core.collection_tasks",
        "task_center_tasks",
        "core.employee_tasks",
        "approval_instances",
    ]

    missing = [name for name in required_table_names if name not in Base.metadata.tables]
    assert not missing, f"Missing tables: {missing}"


def test_schema_metadata_table_keys_are_unique() -> None:
    from modules.core.db.schema import Base

    table_keys = list(Base.metadata.tables.keys())
    assert len(table_keys) == len(set(table_keys))
