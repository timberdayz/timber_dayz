from __future__ import annotations

import inspect
from importlib import import_module

SLICE_MODULE_NAMES = (
    "dimensions",
    "facts",
    "collection",
    "platform",
    "data_platform",
    "business",
)
NON_ORM_PUBLIC_EXPORTS = {"Base", "JSON_COMPAT", "user_roles"}
HELPER_LEAK_NAMES = {
    "BigInteger",
    "Boolean",
    "CheckConstraint",
    "Column",
    "Date",
    "DateTime",
    "Float",
    "ForeignKey",
    "ForeignKeyConstraint",
    "Index",
    "Integer",
    "JSON",
    "JSONB",
    "Numeric",
    "Optional",
    "String",
    "Table",
    "Text",
    "UniqueConstraint",
    "date",
    "datetime",
    "func",
    "relationship",
    "text",
    "timezone",
}


def _slice_orm_class_names() -> set[str]:
    from modules.core.db.schema_parts.base import Base

    class_names: set[str] = set()
    for module_name in SLICE_MODULE_NAMES:
        module = import_module(f"modules.core.db.schema_parts.{module_name}")
        for name, value in vars(module).items():
            if inspect.isclass(value) and issubclass(value, Base) and value is not Base:
                class_names.add(name)
    return class_names


def _expected_public_export_names() -> set[str]:
    return _slice_orm_class_names() | NON_ORM_PUBLIC_EXPORTS


def test_schema_module_imports() -> None:
    import modules.core.db.schema as schema  # noqa: F401


def test_schema_public_export_surface_is_explicit_and_minimal() -> None:
    import modules.core.db as db_package
    import modules.core.db.schema as schema

    expected_exports = _expected_public_export_names()

    assert hasattr(schema, "__all__")
    assert set(schema.__all__) == expected_exports
    assert hasattr(db_package, "__all__")
    assert set(db_package.__all__) == expected_exports

    schema_public_names = {name for name in dir(schema) if not name.startswith("_")}
    package_public_names = {name for name in dir(db_package) if not name.startswith("_")}
    assert schema_public_names >= expected_exports
    assert package_public_names >= expected_exports

    leaked_from_schema = HELPER_LEAK_NAMES & schema_public_names
    leaked_from_package = HELPER_LEAK_NAMES & package_public_names
    assert not leaked_from_schema, f"Unexpected helper exports in schema: {sorted(leaked_from_schema)}"
    assert not leaked_from_package, f"Unexpected helper exports in package: {sorted(leaked_from_package)}"


def test_schema_re_exports_every_slice_orm_class() -> None:
    import modules.core.db as db_package
    import modules.core.db.schema as schema
    from modules.core.db.schema_parts.base import Base, JSON_COMPAT
    from modules.core.db.schema_parts.business import user_roles

    expected_exports = _expected_public_export_names()

    for export_name in sorted(expected_exports - {"Base", "JSON_COMPAT"}):
        assert getattr(schema, export_name) is getattr(db_package, export_name)

    for module_name in SLICE_MODULE_NAMES:
        module = import_module(f"modules.core.db.schema_parts.{module_name}")
        for name, value in vars(module).items():
            if inspect.isclass(value) and issubclass(value, Base) and value is not Base:
                assert getattr(schema, name) is value
                assert getattr(db_package, name) is value

    assert schema.Base is Base
    assert schema.JSON_COMPAT is JSON_COMPAT
    assert schema.user_roles is user_roles
    assert db_package.Base is Base
    assert db_package.JSON_COMPAT is JSON_COMPAT
    assert db_package.user_roles is user_roles


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
