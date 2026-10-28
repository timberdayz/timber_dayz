"""D8 回归测试: traffic 域清理(域归一 SSOT + 影子配置合并 + 白名单收敛 + 采集侧命名收敛)。

覆盖
----
D8-1 域归一 SSOT
  1. canonical 集合只含 canonical 域,traffic 不在其中
  2. 别名归一: traffic / TRAFFIC / "  Traffic  " -> analytics
  3. 未知域原样返回(不抹成空串), 便于诊断
  4. 有效性与 canonical 自检是两个概念
  5. token 集合: 全量扫描用(含别名), 按域取用(只含该域的别名)

D8-2 影子配置合并
  6. data_standardizer 三张按域配置表里不再有 traffic,analytics 取并集
  7. event_listeners 刷新目标表里不再有 traffic
  8. deduplication_fields_config 三张表里不再有 traffic, 且别名查询等价

D8-3 白名单收敛
  9. validators / file_naming 白名单只留 canonical 域
 10. StandardFileName.parse 内部归一: 历史 __traffic__ 文件仍能解析且归到 analytics
 11. StandardFileName.generate 归一: 不再产出 traffic 命名的文件
 12. catalog_scanner 从路径/文件名推断域时归一, 历史 traffic 命名不丢

D8-6 兜底转换走 SSOT
 13. ingestion_worker 文件名/内容兜底: 新旧行为逐条一致
 14. refresh_registry 兜底: traffic 域与 traffic 表名都归到 analytics
"""

from pathlib import Path

import pandas as pd


# ======================================================================
# D8-1 域归一 SSOT
# ======================================================================
def test_canonical_domains_exclude_traffic():
    from modules.core.data_domains import CANONICAL_DATA_DOMAINS, DataDomain

    assert "traffic" not in CANONICAL_DATA_DOMAINS
    assert "analytics" in CANONICAL_DATA_DOMAINS
    assert DataDomain.ANALYTICS == "analytics"
    assert DataDomain.ANALYTICS.value == "analytics"


def test_legacy_alias_is_normalized_to_analytics():
    from modules.core.data_domains import normalize_data_domain

    assert normalize_data_domain("traffic") == "analytics"
    assert normalize_data_domain("TRAFFIC") == "analytics"
    assert normalize_data_domain("  Traffic  ") == "analytics"
    assert normalize_data_domain("analytics") == "analytics"


def test_unknown_domain_is_kept_for_diagnostics():
    from modules.core.data_domains import normalize_data_domain

    # 未知域不能被抹成空串 —— 调用方还要用它做「跳过无效数据域」的日志
    assert normalize_data_domain("unknown_domain") == "unknown_domain"
    assert normalize_data_domain("") == ""
    assert normalize_data_domain(None) == ""


def test_validity_and_canonicality_are_distinct():
    from modules.core.data_domains import (
        canonicalize_data_domain,
        is_canonical_data_domain,
        is_valid_data_domain,
    )

    # traffic 是合法域(它是 analytics 的历史别名), 但它本身不是 canonical 形态
    assert is_valid_data_domain("traffic") is True
    assert is_canonical_data_domain("traffic") is False
    assert canonicalize_data_domain("traffic") == "analytics"
    assert canonicalize_data_domain("nope") is None

    assert is_valid_data_domain("unknown_domain") is False
    assert is_valid_data_domain("") is False
    assert is_valid_data_domain(None) is False
    assert is_canonical_data_domain("analytics") is True


def test_domain_token_helpers():
    from modules.core.data_domains import data_domain_tokens, data_domain_tokens_for

    # 全量扫描 token: canonical + 全部历史别名
    assert "traffic" in data_domain_tokens()
    assert "analytics" in data_domain_tokens()

    # 按域取 token: 只含指向该域的别名
    assert data_domain_tokens_for("analytics") == ("analytics", "traffic")
    assert data_domain_tokens_for("products") == ("products",)
    assert data_domain_tokens_for("nope") == ()


# ======================================================================
# D8-2 影子配置合并
# ======================================================================
def test_data_standardizer_domain_tables_have_no_traffic_entry():
    from backend.services.data_standardizer import (
        DATE_FIELDS_BY_DOMAIN,
        DATETIME_FIELDS_BY_DOMAIN,
        NUMERIC_FIELDS_BY_DOMAIN,
    )

    for table in (DATE_FIELDS_BY_DOMAIN, DATETIME_FIELDS_BY_DOMAIN, NUMERIC_FIELDS_BY_DOMAIN):
        assert "traffic" not in table

    # 原 traffic 的数值字段并入 analytics(同一业务域,取并集)
    assert "page_views" in NUMERIC_FIELDS_BY_DOMAIN["analytics"]
    assert "unique_visitors" in NUMERIC_FIELDS_BY_DOMAIN["analytics"]
    assert "conversion_rate" in NUMERIC_FIELDS_BY_DOMAIN["analytics"]
    assert "click_rate" in NUMERIC_FIELDS_BY_DOMAIN["analytics"]


def test_data_standardizer_normalizes_domain_before_lookup():
    from backend.services.data_standardizer import standardize_row

    row = standardize_row({"metric_date": "2025-09-25", "page_views": "1,234"}, "traffic")
    # traffic 别名归一到 analytics, 因此 page_views 走数值标准化
    assert row["page_views"] == 1234.0


def test_event_listeners_pipeline_targets_have_no_traffic_entry():
    from backend.services.event_listeners import DATA_INGESTED_PIPELINE_TARGETS

    assert "traffic" not in DATA_INGESTED_PIPELINE_TARGETS
    assert "analytics" in DATA_INGESTED_PIPELINE_TARGETS


def test_deduplication_config_has_no_traffic_entry_and_alias_queries_match():
    from backend.services.deduplication_fields_config import (
        DEFAULT_DEDUPLICATION_FIELDS,
        DEDUPLICATION_STRATEGY,
        UPSERT_UPDATE_FIELDS,
        get_default_deduplication_fields,
        get_deduplication_strategy,
        get_upsert_update_fields,
    )

    assert "traffic" not in DEDUPLICATION_STRATEGY
    assert "traffic" not in UPSERT_UPDATE_FIELDS
    assert "traffic" not in DEFAULT_DEDUPLICATION_FIELDS

    # 用别名查,结果必须与 canonical 域完全一致
    assert get_default_deduplication_fields("traffic") == get_default_deduplication_fields("analytics")
    assert get_deduplication_strategy("traffic") == get_deduplication_strategy("analytics")
    assert get_upsert_update_fields("traffic") == get_upsert_update_fields("analytics")


# ======================================================================
# D8-3 白名单收敛
# ======================================================================
def test_whitelists_only_contain_canonical_domains():
    from modules.core.file_naming import StandardFileName
    from modules.core.validators import VALID_DATA_DOMAINS

    assert "traffic" not in VALID_DATA_DOMAINS
    assert "traffic" not in StandardFileName.KNOWN_DATA_DOMAINS
    # canonical 域仍然全部在白名单里
    for domain in ("analytics", "products", "orders", "services", "inventory", "purchase", "finance"):
        assert domain in VALID_DATA_DOMAINS


def test_validators_normalize_alias_but_keep_unknown_visible():
    from modules.core.validators import is_valid_data_domain, normalize_data_domain

    assert normalize_data_domain("traffic") == "analytics"
    assert is_valid_data_domain("traffic") is True
    assert is_valid_data_domain("purchase") is True
    assert is_valid_data_domain("unknown_domain") is False


def test_standard_file_name_parse_normalizes_legacy_traffic():
    from modules.core.file_naming import StandardFileName

    meta = StandardFileName.parse("shopee_traffic_monthly_20250925_100234.xlsx")
    assert meta["data_domain"] == "analytics"
    assert meta["source_platform"] == "shopee"
    assert meta["granularity"] == "monthly"
    # 白名单收紧后,历史 traffic 文件仍要能通过 validate
    assert StandardFileName.validate("shopee_traffic_monthly_20250925_100234.xlsx") is True

    # 其它域的解析不受影响
    meta2 = StandardFileName.parse("tiktok_services_agent_daily_20250925_001033.xlsx")
    assert meta2["data_domain"] == "services"
    assert meta2["sub_domain"] == "agent"


def test_standard_file_name_generate_never_emits_traffic():
    from modules.core.file_naming import StandardFileName

    name = StandardFileName.generate("shopee", "traffic", "monthly", timestamp="20250925_100234")
    assert "traffic" not in name
    assert "analytics" in name


def test_catalog_scanner_normalizes_legacy_traffic_paths():
    from modules.services.catalog_scanner import KNOWN_DATA_DOMAINS, _infer_domain_from_path

    assert "traffic" not in KNOWN_DATA_DOMAINS
    assert _infer_domain_from_path(Path("downloads/shopee/traffic/x")) == "analytics"
    assert _infer_domain_from_path(Path("downloads/shopee/analytics/x")) == "analytics"


# ======================================================================
# D8-6 兜底转换走 SSOT
# ======================================================================
class _FakeCatalogFile:
    def __init__(self, file_name="", file_path="", data_domain=None):
        self.file_name = file_name
        self.file_path = file_path
        self.data_domain = data_domain


def _legacy_domain_from_name(cf):
    """迁移前的原始实现 —— 差分测试基准。"""
    name = (cf.file_name or "").lower()
    path = (cf.file_path or "").lower()
    text = f"{name} {path}"
    if (
        "__analytics__" in name
        or " analytics " in text
        or name.endswith("_analytics.xlsx")
        or "__traffic__" in name
        or " traffic " in text
        or name.endswith("_traffic.xlsx")
    ):
        cf.data_domain = "analytics"
        return
    if "__services__" in name or "__service__" in name or " service " in text:
        cf.data_domain = "service"
        return
    if "__orders__" in name or "__order__" in name or " order " in text:
        cf.data_domain = "orders"
        return


def test_ingestion_worker_name_fallback_matches_legacy_behavior():
    from modules.services.ingestion_worker import _try_set_domain_from_name

    cases = [
        ("20250925_100000__acc__shop__traffic__monthly__x.xlsx", "data/raw/x"),
        ("20250925_100000__acc__shop__analytics__monthly__x.xlsx", "data/raw/x"),
        ("shopee_traffic.xlsx", "data/raw/x"),
        ("shopee_analytics.xlsx", "data/raw/x"),
        ("shopee_traffic_monthly_20250925.xlsx", "data/raw/x"),
        ("x.txt", "downloads/shopee/traffic/y/z.xlsx"),
        ("20250925_100000__acc__shop__services__agent__daily__x.xlsx", "data/raw/x"),
        ("20250925_100000__acc__shop__orders__daily__x.xlsx", "data/raw/x"),
        ("", ""),
    ]
    for file_name, file_path in cases:
        new_cf = _FakeCatalogFile(file_name=file_name, file_path=file_path)
        _try_set_domain_from_name(new_cf)
        old_cf = _FakeCatalogFile(file_name=file_name, file_path=file_path)
        _legacy_domain_from_name(old_cf)
        assert new_cf.data_domain == old_cf.data_domain, (file_name, file_path)


def test_ingestion_worker_dataframe_fallback_normalizes_traffic():
    from modules.services.ingestion_worker import _try_set_domain_from_df

    expectations = {
        "traffic": "analytics",
        "analytics": "analytics",
        "products": "products",
        "nope": None,
    }
    for raw, expected in expectations.items():
        cf = _FakeCatalogFile(data_domain=None)
        _try_set_domain_from_df(cf, pd.DataFrame({"data_type": [raw]}))
        assert cf.data_domain == expected, (raw, cf.data_domain)


def test_refresh_registry_fallback_maps_traffic_to_analytics():
    from backend.services.data_pipeline.refresh_registry import _infer_refresh_domain

    assert _infer_refresh_domain(source_table_name="x", data_domain="traffic") == "analytics"
    assert _infer_refresh_domain(source_table_name="x", data_domain="analytics") == "analytics"
    assert _infer_refresh_domain(source_table_name="x", data_domain="orders") == "orders"
    assert _infer_refresh_domain(source_table_name="x", data_domain="") is None
    # 历史 traffic 表名仍然要能推断出 analytics
    assert (
        _infer_refresh_domain(
            source_table_name="b_class.fact_shopee_traffic_monthly", data_domain=None
        )
        == "analytics"
    )
    assert (
        _infer_refresh_domain(
            source_table_name="b_class.fact_shopee_analytics_monthly", data_domain=None
        )
        == "analytics"
    )
