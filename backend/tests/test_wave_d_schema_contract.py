from modules.core.db import CatalogFile, EntityAlias, StagingRawData


def test_wave_d_tables_bind_to_target_schemas():
    assert EntityAlias.__table__.schema == "b_class"
    assert EntityAlias.__table__.fullname == "b_class.entity_aliases"

    assert StagingRawData.__table__.schema == "b_class"
    assert StagingRawData.__table__.fullname == "b_class.staging_raw_data"


def test_staging_raw_data_fk_targets_public_catalog_files():
    """FK 必须指向 **public** schema 的 catalog_files。

    断言的是 ORM 的**真实绑定关系**（FK 指向哪张表），不是 ``target_fullname``
    的字符串形式 —— 后者取决于 FK 声明里有没有写 schema 前缀，而 SQLAlchemy
    对没写前缀的 FK 会按目标表自身的 schema 解析（``CatalogFile`` 没设 schema
    ⇒ 落在 public，search_path 也是 ``"$user", public``）。
    """
    fk_tables = {fk.column.table for fk in StagingRawData.__table__.foreign_keys}

    assert CatalogFile.__table__ in fk_tables
    # CatalogFile 落在 public（default schema）
    assert CatalogFile.__table__.schema in (None, "public")
