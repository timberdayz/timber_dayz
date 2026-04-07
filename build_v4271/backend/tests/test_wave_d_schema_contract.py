from modules.core.db import ClearanceRanking, EntityAlias, StagingRawData


def test_wave_d_tables_bind_to_target_schemas():
    assert EntityAlias.__table__.schema == "b_class"
    assert EntityAlias.__table__.fullname == "b_class.entity_aliases"

    assert StagingRawData.__table__.schema == "b_class"
    assert StagingRawData.__table__.fullname == "b_class.staging_raw_data"

    assert ClearanceRanking.__table__.schema == "c_class"
    assert ClearanceRanking.__table__.fullname == "c_class.clearance_rankings"


def test_staging_raw_data_fk_targets_public_catalog_files():
    fk_targets = {fk.target_fullname for fk in StagingRawData.__table__.foreign_keys}

    assert "public.catalog_files.id" in fk_targets


def test_clearance_ranking_fk_targets_core_dim_shops():
    fk_targets = {fk.target_fullname for fk in ClearanceRanking.__table__.foreign_keys}

    assert "core.dim_shops.platform_code" in fk_targets
    assert "core.dim_shops.shop_id" in fk_targets
