"""Regression: purchase 数据域必须在 catalog 白名单中。

Sep 14 task (73s, partial_success) 真实失败链：
  1. download → save_as → data/raw/2026/miaoshou_purchase_daily_*.xlsx ✅
  2. StandardFileName.parse → {'data_domain': 'purchase', 'granularity': 'daily'} ✅
  3. is_valid_data_domain('purchase') → False → return None ❌
  4. catalog_scanner.register_single_file 返回 None → catalog_registered_count == 0
  5. executor_v2.py:4550 命中 PARTIAL_SUCCESS 分支

修复：把 'purchase' 加入 VALID_DATA_DOMAINS 和 KNOWN_DATA_DOMAINS。
"""


def test_valid_data_domains_includes_purchase():
    """VALID_DATA_DOMAINS 必须包含 'purchase'（catalog 注册白名单）。

    catalog_scanner.py:693 的 is_valid_data_domain 失败 → return None →
    catalog_registered_count == 0 → 命中 PARTIAL_SUCCESS 分支。
    """
    from modules.core.validators import VALID_DATA_DOMAINS
    assert 'purchase' in VALID_DATA_DOMAINS, (
        "VALID_DATA_DOMAINS missing 'purchase' → catalog_scanner skips "
        "miaoshou_purchase_daily_*.xlsx registration → partial_success"
    )


def test_is_valid_data_domain_accepts_purchase():
    from modules.core.validators import is_valid_data_domain
    assert is_valid_data_domain('purchase') is True
    assert is_valid_data_domain('Purchase') is True   # 大小写归一
    assert is_valid_data_domain('  purchase  ') is True  # 空格归一


def test_is_valid_data_domain_still_rejects_unknown():
    from modules.core.validators import is_valid_data_domain
    # 防止白名单被过度放宽
    assert is_valid_data_domain('unknown_domain') is False
    assert is_valid_data_domain('') is False


def test_standard_filename_known_data_domains_includes_purchase():
    """StandardFileName.KNOWN_DATA_DOMAINS 必须包含 'purchase'。

    file_naming.py 的 KNOWN_DATA_DOMAINS 是独立副本（不是 catalog_scanner.py:56 的别名），
    必须单独更新，否则 StandardFileName.validate('miaoshou_purchase_daily_*.xlsx') 返回 False。
    """
    from modules.core.file_naming import StandardFileName
    assert 'purchase' in StandardFileName.KNOWN_DATA_DOMAINS


def test_standard_filename_validate_accepts_miaoshou_purchase_daily():
    """回归测试：实际生产文件名 miaoshou_purchase_daily_*.xlsx 必须 validate 通过。

    标准格式：{platform}_{data_domain}[_{sub_domain}]_{granularity}_{timestamp}.{ext}
    """
    from modules.core.file_naming import StandardFileName

    assert StandardFileName.validate(
        'miaoshou_purchase_daily_20260914_130803.xlsx'
    ) is True


def test_standard_filename_parse_miaoshou_purchase_daily_returns_purchase_domain():
    """parse 必须正确提取 data_domain='purchase', granularity='daily'。"""
    from modules.core.file_naming import StandardFileName

    meta = StandardFileName.parse('miaoshou_purchase_daily_20260914_130803.xlsx')
    assert meta['source_platform'] == 'miaoshou'
    assert meta['data_domain'] == 'purchase'
    assert meta['sub_domain'] == ''
    assert meta['granularity'] == 'daily'
    assert meta['timestamp'] == '20260914_130803'


def test_standard_filename_generate_miaoshou_purchase_daily_roundtrip():
    """generate → parse 闭环一致。"""
    from modules.core.file_naming import StandardFileName

    filename = StandardFileName.generate(
        source_platform='miaoshou',
        data_domain='purchase',
        granularity='daily',
        sub_domain='',
        timestamp='20260914_130803',
    )
    assert filename == 'miaoshou_purchase_daily_20260914_130803.xlsx'
    meta = StandardFileName.parse(filename)
    assert meta['data_domain'] == 'purchase'
    assert meta['granularity'] == 'daily'


def test_catalog_scanner_known_data_domains_alias_remains_in_sync():
    """catalog_scanner.KNOWN_DATA_DOMAINS = VALID_DATA_DOMAINS（catalog_scanner.py:56 别名）。

    防止未来有人重构掉别名导致两边白名单漂移。
    """
    from modules.services.catalog_scanner import KNOWN_DATA_DOMAINS
    from modules.core.validators import VALID_DATA_DOMAINS
    assert KNOWN_DATA_DOMAINS is VALID_DATA_DOMAINS or set(KNOWN_DATA_DOMAINS) == set(VALID_DATA_DOMAINS), (
        "catalog_scanner.KNOWN_DATA_DOMAINS 必须是 VALID_DATA_DOMAINS 的别名/相等集合，"
        "否则 is_valid_data_domain 与 file_metadata 白名单会漂移"
    )


def test_valid_granularities_still_contains_daily_for_purchase_files():
    """实际生产文件用 daily 粒度（executor fallback from task_granularity='daily'）。

    防止有人把 daily 从白名单里移除。
    """
    from modules.core.validators import VALID_GRANULARITIES
    from modules.core.file_naming import StandardFileName
    assert 'daily' in VALID_GRANULARITIES
    assert 'daily' in StandardFileName.KNOWN_GRANULARITIES