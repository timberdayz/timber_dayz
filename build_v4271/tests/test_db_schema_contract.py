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
        'fact_order_amounts',
        'fact_product_metrics',
        'catalog_files',
        'collection_tasks',
        'component_versions',
    }
    missing = expected - tables
    assert not missing, f"Missing tables in metadata: {missing}"


def test_can_create_all_tables_in_memory():
    from sqlalchemy import inspect
    engine: Engine = create_engine('sqlite:///:memory:')
    sqlite_tables = [
        Base.metadata.tables['dim_platforms'],
        Base.metadata.tables['dim_shops'],
        Base.metadata.tables['dim_products'],
        Base.metadata.tables['dim_currency_rates'],
        Base.metadata.tables['catalog_files'],
        Base.metadata.tables['collection_tasks'],
        Base.metadata.tables['collection_task_logs'],
        Base.metadata.tables['component_versions'],
    ]
    Base.metadata.create_all(engine, tables=sqlite_tables)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    expected = {
        'dim_platforms',
        'dim_shops',
        'dim_products',
        'dim_currency_rates',
        'catalog_files',
        'collection_tasks',
        'collection_task_logs',
        'component_versions',
    }
    missing = expected - tables
    assert not missing, f"Missing tables after create_all: {missing}"
