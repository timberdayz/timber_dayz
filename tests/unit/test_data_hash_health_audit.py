#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Data Hash 数据健康度巡检（P5）的自测。

巡检脚本最怕变成"永远绿的摆设" —— 这里用**构造样本**证明它能抓出问题：

1. 报告统计（重复组数 / 多余行数 / 指纹）；
2. 基线对比能区分「新增的重复」与「已修复的重复」；
3. 指纹是**稳定**的（同一业务键跨次巡检指纹不变 ⇒ 才能做增量对比）。

不依赖数据库。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIT_PATH = REPO_ROOT / "scripts" / "audit_data_hash_health.py"


def _load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


audit = _load_module("audit_data_hash_health", AUDIT_PATH)


def _domain(
    domain: str,
    *,
    duplicate_groups: int = 0,
    extra_rows: int = 0,
    fingerprints=None,
) -> dict:
    return {
        "domain": domain,
        "view": f"semantic.fact_{domain}_atomic",
        "available": True,
        "business_key_columns": ["platform_code", "shop_id", "metric_date"],
        "missing_key_columns": [],
        "total_rows": 100,
        "duplicate_groups": duplicate_groups,
        "extra_rows": extra_rows,
        "fingerprints": fingerprints if fingerprints is not None else [],
        "samples": [],
    }


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------
def test_report_sums_duplicates_across_domains():
    report = audit.build_report(
        [
            _domain("orders", duplicate_groups=3, extra_rows=5),
            _domain("products", duplicate_groups=1, extra_rows=1),
        ]
    )
    assert report["total_duplicate_groups"] == 4
    assert report["total_extra_rows"] == 6
    assert report["generated_at"]


def test_fingerprint_is_stable_and_distinct():
    values = ["shopee", "123", "2026-01-01"]
    assert audit._fingerprint(values) == audit._fingerprint(list(values))
    assert audit._fingerprint(values) != audit._fingerprint(
        ["shopee", "123", "2026-02-01"]
    )


def test_fingerprint_handles_none_values():
    assert audit._fingerprint(["a", None]) == audit._fingerprint(["a", None])
    assert audit._fingerprint(["a", None]) != audit._fingerprint(["a", "b"])


# ---------------------------------------------------------------------------
# 基线对比（增量检测）
# ---------------------------------------------------------------------------
def test_baseline_comparison_reports_new_and_fixed(tmp_path: Path):
    baseline_report = audit.build_report(
        [_domain("orders", duplicate_groups=2, fingerprints=["aaa", "bbb"])]
    )
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(baseline_report, ensure_ascii=False), encoding="utf-8"
    )

    current = audit.build_report(
        [_domain("orders", duplicate_groups=2, fingerprints=["bbb", "ccc"])]
    )
    diff = audit.compare_with_baseline(current, str(baseline_path))
    assert diff["baseline_total_duplicate_groups"] == 2
    assert diff["current_total_duplicate_groups"] == 2
    assert diff["new_duplicate_keys_total"] == 1
    assert diff["by_domain"]["orders"]["new_duplicate_keys"] == 1
    assert diff["by_domain"]["orders"]["fixed_duplicate_keys"] == 1
    assert diff["by_domain"]["orders"]["new_fingerprints"] == ["ccc"]


def test_baseline_comparison_when_domain_is_new(tmp_path: Path):
    baseline_report = audit.build_report([])
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(baseline_report, ensure_ascii=False), encoding="utf-8"
    )

    current = audit.build_report([_domain("orders", duplicate_groups=4)])
    diff = audit.compare_with_baseline(current, str(baseline_path))
    assert diff["new_duplicate_keys_total"] == 0
    assert diff["by_domain"]["orders"]["baseline_duplicate_groups"] == 0
    assert diff["by_domain"]["orders"]["current_duplicate_groups"] == 4


# ---------------------------------------------------------------------------
# 业务键定义
# ---------------------------------------------------------------------------
def test_business_keys_cover_all_domains():
    assert set(audit.BUSINESS_KEYS) == {"orders", "products", "services"}
    assert "order_id" in audit.BUSINESS_KEYS["orders"]["columns"]
    assert "product_id" in audit.BUSINESS_KEYS["products"]["columns"]
    assert "service_date" in audit.BUSINESS_KEYS["services"]["columns"]
    # 业务键必须带上平台与店铺，否则跨店铺的同一笔业务会被误判成重复
    for spec in audit.BUSINESS_KEYS.values():
        assert "platform_code" in spec["columns"]
        assert "shop_id" in spec["columns"]
