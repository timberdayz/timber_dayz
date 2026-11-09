#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Contract test: the unified ORM Base exposes the current fact-source tables.

⚠️ 旧版契约测的是「SQLite ``create_all`` + 一堆旧表名」
（``dim_platforms`` / ``dim_shops`` / ``dim_products`` / ``dim_currency_rates`` /
``collection_tasks`` / ``component_versions`` …）——
事实源已经换成 PostgreSQL 分段（``core`` / ``a_class`` / ``b_class`` / ``c_class`` /
``finance`` / ``ops`` / ``semantic``），旧表名大部分**不存在**了，
SQLite 也早已不是建表目标 ⇒ 那条断言整条作废（长期红，没人跑）。

现在锁的是**现行**契约：
1. ORM SSOT（``modules/core/db/schema.py``）必须暴露当前事实源的核心表；
2. 表必须按业务分段落位，采集/模板类表在 ``core`` 下。
"""

from modules.core.db import Base


def test_metadata_contains_expected_tables():
    tables = set(Base.metadata.tables.keys())
    expected = {
        # 采集链路（core 分段）
        "core.collection_tasks",
        "core.collection_task_logs",
        "core.collection_configs",
        "core.collection_source_identifiers",
        # 模板与字段语义
        "core.field_mapping_templates",
        # 目标管理（a_class 分段）
        "a_class.sales_targets",
        "a_class.target_breakdown",
        # 仍在 public 的历史事实表
        "fact_order_amounts",
        "fact_product_metrics",
        "catalog_files",
    }
    missing = expected - tables
    assert not missing, f"Missing tables in metadata: {missing}"


def test_tables_are_grouped_into_business_schemas():
    tables = Base.metadata.tables
    schemas = {table.schema or "public" for table in tables.values()}

    for expected in (
        "core",
        "a_class",
        "b_class",
        "c_class",
        "finance",
        "ops",
        "semantic",
    ):
        assert expected in schemas, f"缺少业务分段: {expected}"

    # 采集与模板类表必须落在 core（业务事实源的位置约定）
    for name in (
        "core.collection_tasks",
        "core.field_mapping_templates",
        "core.collection_source_identifiers",
    ):
        assert name in tables, f"采集/模板表不在 core 分段: {name}"
