#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Contract test: new unified ORM Base exposes required tables and can create schema in memory.
"""
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from modules.core.db import Base


def test_metadata_contains_expected_tables():
    tables = set(Base.metadata.tables.keys())
    expected = {
        'dim_platforms',
        'dim_shops',
        'dim_products',
        'dim_currency_rates',
        'fact_orders',
        'fact_order_items',
        'fact_product_metrics',
        'catalog_files',
    }
    missing = expected - tables
    assert not missing, f"Missing tables in metadata: {missing}"


def test_can_create_all_tables_in_memory():
    from sqlalchemy import inspect
    engine: Engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    expected = {
        'dim_platforms',
        'dim_shops',
        'dim_products',
        'dim_currency_rates',
        'fact_orders',
        'fact_order_items',
        'fact_product_metrics',
        'catalog_files',
    }
    missing = expected - tables
    assert not missing, f"Missing tables after create_all: {missing}"

