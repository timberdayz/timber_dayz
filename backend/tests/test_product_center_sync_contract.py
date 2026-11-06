"""商品中心「采集机 → 云端」同步脚本的契约测试。

背景
----
``scripts/sync_product_center_to_cloud.py`` 的 ``PRODUCT_CENTER_TABLES`` 曾经
**漏掉了 ``finance.sku_pricing_policies``**（库龄档位规则表）。

这张表**没有任何外键** —— 不引用别的表，也没有别的表引用它 —— 于是：

- ``TRUNCATE ... CASCADE`` 其它表时**不会**把它一起清掉；
- 它自己也不在 INSERT 清单里，所以**永远不会被同步覆盖**。

结果：云端的档位规则表停留在「从未被同步过」的状态（空表，或某次手工导入的旧规则）。
两种后果都是静默失败：

1. 空表 → 云端所有 SKU 落进 ``missing_pricing_policy`` → **最低售价整体算不出来**，
   定价护栏同时失效；
2. 旧规则 → 云端按过期档位算出与本地不一致的最低售价，**表面看一切正常**。

复现与防护
----------
本文件把「规则表必须在清单里」「必须在依赖之前」「关键表不能为空」这三条钉成契约，
防止以后再有人往清单里加表时把它漏掉。
"""

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "sync_product_center_to_cloud.py"


def _load_sync_module():
    """直接加载脚本模块（脚本本身是 CLI，不是一个包）。"""
    spec = importlib.util.spec_from_file_location(
        "sync_product_center_to_cloud_under_test", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sync_table_list_contains_pricing_policy_table():
    """档位规则表必须在同步清单里 —— 漏了云端底线就整体失效。"""
    module = _load_sync_module()
    tables = set(module.PRODUCT_CENTER_TABLES)
    assert ("finance", "sku_pricing_policies") in tables


def test_pricing_policy_table_is_synced_before_dependent_tables():
    """规则表要排在依赖它的表之前（父先子后的插入顺序）。"""
    module = _load_sync_module()
    names = [table for _schema, table in module.PRODUCT_CENTER_TABLES]
    policy_at = names.index("sku_pricing_policies")
    profiles_at = names.index("sku_operating_profiles")
    assert policy_at < profiles_at, (
        "sku_pricing_policies 必须排在 sku_operating_profiles 之前"
    )


def test_truncate_order_is_reversed_insert_order():
    """TRUNCATE 顺序必须与插入顺序相反（先删子表）。"""
    module = _load_sync_module()
    assert module.TRUNCATE_ORDER == list(reversed(module.PRODUCT_CENTER_TABLES))


def test_critical_tables_cover_pricing_policy_and_master_data():
    """关键表清单要包含规则表与主数据 —— 这些表为空时业务无法工作。"""
    module = _load_sync_module()
    critical = set(module.CRITICAL_TABLES)
    assert ("finance", "sku_pricing_policies") in critical
    assert ("core", "dim_erp_sku") in critical
    assert ("core", "dim_spu") in critical


def test_sync_script_refuses_to_truncate_when_source_critical_table_is_empty():
    """破坏性操作之前必须拦：源表为空时拒绝清空云端。

    TRUNCATE 一旦提交就撤不回来，所以这个闸门必须在 truncate 之前，
    而不是复制完成之后才发现。
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    gate_at = source.find("[GATE] source")
    # 用只出现在**实际语句**里的关键字定位 —— "TRUNCATE" 在文件头 docstring 里也出现过
    truncate_at = source.find("RESTART IDENTITY CASCADE")
    abort_at = source.find("[ABORT] 本地源表为空")
    assert gate_at != -1, "缺少源表非空闸门"
    assert truncate_at != -1, "找不到 TRUNCATE 语句"
    assert abort_at != -1, "缺少源表为空时的中止分支"
    assert gate_at < truncate_at, "闸门必须早于 TRUNCATE"
    assert abort_at < truncate_at, "中止分支必须早于 TRUNCATE"


def test_sync_script_verifies_critical_tables_after_copy():
    """复制完成后要核对关键表：行数对得上不等于能用（内容可能是空的）。"""
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "[CHECK]" in source
    assert "CRITICAL_TABLES" in source
