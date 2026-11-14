# -*- coding: utf-8 -*-
"""库存快照 ``data_hash`` 重建 —— 守护测试。

背景
----
2026-11-14 实测(生产 ``b_class.fact_miaoshou_inventory_snapshot``, 4111 行):

* 256 组「同 SKU × 仓库 × 快照日」存在两行;
* 根因不是「商品改名」, 而是**作用域身份键换过**:
  2026-10-21 ~ 10-26 入库的 2726 行载荷里是 ``scope:shop_id=xihong``,
  2026-11-03 之后入库的 1385 行是 ``scope:shop_account_id=miaoshou_real_001``;
* ⇒ 同一份快照在口径切换前后各入库一次 ⇒ 两批 hash 不同 ⇒ 两行都留下来。

⇒ ``data_hash`` 是事实表的**行身份**(唯一键 + ``ON CONFLICT DO UPDATE``),
口径一变就必须**同口径重建**, 否则下次采集又会多出新行。

本文件锁住三件事:

1. **镜像必须带上重建脚本**(白名单式 COPY 的老坑, v7.29.1 补过一次);
2. **决策资产里库存维度的清单口径**必须与业务拍板一致;
3. **重建脚本必须把两种历史口径归一到同一口径** —— 否则重建完还是两行。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

SCRIPT_PATH = REPO_ROOT / "scripts" / "rebuild_inventory_snapshot_hash.py"
DEFINITION_PATH = (
    REPO_ROOT / "templates" / "definitions" / "miaoshou__inventory__snapshot.json"
)


def _load_script():
    """按文件路径加载脚本(它是运维脚本, 不是包)。"""
    spec = importlib.util.spec_from_file_location(
        "rebuild_inventory_snapshot_hash", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 1. 镜像必须真的带上重建脚本
# ---------------------------------------------------------------------------


def test_backend_image_ships_inventory_hash_rebuild_script():
    """``Dockerfile.backend`` 必须登记重建脚本。

    为什么必须有这条
    ----------------
    ``Dockerfile.backend`` 对 ``scripts/`` 用的是**白名单式 COPY**
    (逐个 ``COPY scripts/xxx.py``, 避免整体复制让镜像膨胀)。
    ⇒ 新加的运维脚本**忘了登记就等于没上线**: 镜像构建成功、部署成功、
    业务不受影响, 但脚本在生产**根本不存在**。

    实测: v7.29.0 上线时 ``templates/`` 与 5 个新脚本全部漏登记(v7.29.1 补的洞)。
    """
    dockerfile = REPO_ROOT / "Dockerfile.backend"
    assert dockerfile.is_file(), "缺少 Dockerfile.backend"
    text = dockerfile.read_text(encoding="utf-8")
    assert (
        "COPY scripts/rebuild_inventory_snapshot_hash.py /app/scripts/rebuild_inventory_snapshot_hash.py"
        in text
    ), "Dockerfile.backend 没有登记重建脚本 —— 生产镜像里跑不了这次重建"


# ---------------------------------------------------------------------------
# 2. 决策资产里的库存维度口径必须与业务拍板一致
# ---------------------------------------------------------------------------


def _definition() -> Dict[str, Any]:
    import json

    assert DEFINITION_PATH.is_file(), "缺少库存维度的决策资产"
    return json.loads(DEFINITION_PATH.read_text(encoding="utf-8"))


def test_inventory_dedup_fields_are_stable_identity_only():
    """去重字段表只留**身份**, 不留可变的描述属性。

    业务拍板(2026-11-14): ``*商品名称`` / ``*规格`` 是**会被改**的描述属性,
    留在身份键里 ⇒ 妙手改个名/改个规格, 同一份快照就会变成新行。
    """
    definition = _definition()
    assert definition["deduplication_fields"] == ["*商品SKU", "仓库"], (
        "库存维度的去重字段表必须只含身份键(*商品SKU + 仓库); "
        f"实际 = {definition['deduplication_fields']}"
    )


def test_inventory_core_fields_match_business_decision():
    """核心字段清单必须与业务拍板逐条一致(13 项)。"""
    definition = _definition()
    core_fields = definition["core_fields"]
    by_name = {entry["raw_name"]: entry for entry in core_fields}

    assert len(core_fields) == 13, f"清单应当 13 项, 实际 {len(core_fields)} 项"

    # 必填: 身份 + 关键量(缺了下游算不出东西)
    required = {name for name, entry in by_name.items() if entry["required"]}
    assert required == {
        "*商品SKU",
        "仓库",
        "可用库存",
        "库存总量",
    }, f"必填项口径变了: {sorted(required)}"

    # 参与 hash 的字段必须与去重字段表一致(否则清单在说谎)
    in_hash = {name for name, entry in by_name.items() if entry["in_hash"]}
    assert in_hash == set(definition["deduplication_fields"]), (
        f"清单声明的 hash 字段 {sorted(in_hash)} 与去重字段表 "
        f"{definition['deduplication_fields']} 不一致"
    )

    # 语义键一个都不能瞎填(没有用户确认过的绑定 ⇒ 一律 None)
    for name, entry in by_name.items():
        assert entry["semantic_key"] is None, f"{name} 不该有语义键"


def test_inventory_unit_price_column_keeps_its_real_header():
    """单价列的**真实表头带换行**, 清单必须逐字写对。

    为什么关键: ``required`` 只在「列真的少了」时比对, 且比的是**逐字表头**。
    写成 ``*单价（元）``(没有换行) ⇒ 永远匹配不上 ⇒ **这项静默失效**;
    写成带换行的真实表头 ⇒ 妙手改这一列就会阻断整个库存维度。
    ⇒ 清单里统一记 ``required=false``, 且表头逐字正确。
    """
    definition = _definition()
    by_name = {entry["raw_name"]: entry for entry in definition["core_fields"]}
    assert "*单价\n（元）" in by_name, "清单里单价列的表头必须逐字正确(带换行)"
    assert (
        by_name["*单价\n（元）"]["required"] is False
    ), "单价列的表头带换行, 极易被平台改动 ⇒ 不设必填"


# ---------------------------------------------------------------------------
# 3. 重建脚本必须把两种历史口径归一到同一口径
# ---------------------------------------------------------------------------


def _row(shop_id: str, account_id: str, sku: str, warehouse: str) -> Dict[str, Any]:
    """造一行「库存快照事实行」(raw_data 里带注入的身份列)。"""
    return {
        "id": 1,
        "platform_code": "miaoshou",
        "shop_id": "xihong",
        "data_domain": "inventory",
        "granularity": "snapshot",
        "sub_domain": None,
        "metric_date": __import__("datetime").date(2026, 10, 1),
        "data_hash": "x" * 64,
        "ingest_timestamp": __import__("datetime").datetime(
            2026, 11, 5, tzinfo=__import__("datetime").timezone.utc
        ),
        "raw_data": {
            "*商品SKU": sku,
            "*商品名称": "某商品",
            "*规格": "",
            "仓库": warehouse,
            "shop_id": shop_id,
            "shop_account_id": account_id,
            "main_account_id": account_id,
            "store_name": "xihong",
            "platform_code": "miaoshou",
        },
    }


def test_rebuild_script_collapses_old_and_new_scope_calibers():
    """旧口径行(行内 shop_id=店铺 id)与新口径行(行内 shop_id=账号 id)
    在**归一之后**必须算出同一个 hash —— 否则重建完还是两行。

    这条是整套重建的**行为核心**: 它证明「口径归一」真的把两条历史口径
    压成了同一个身份, 而不只是改了 hash 字符串。
    """
    module = _load_script()
    from backend.services.deduplication_service import DeduplicationService

    service = DeduplicationService(db=None)
    caliber = module.CALIBERS[module.TARGET_CALIBER]
    fields = module._build_hash_fields(
        template_fields=["*商品SKU", "仓库"],
        rules=[
            {
                "strict": True,
                "value_kind": "single_date",
                "date_format": "yyyy-mm-dd",
                "target_field": "metric_date",
                "source_column": "__file_date_from__",
            }
        ],
        data_domain="inventory",
        sub_domain=None,
    )

    old_row = _row("xihong", "miaoshou_real_001", "SKU-1", "主仓")
    new_row = _row("miaoshou_real_001", "miaoshou_real_001", "SKU-1", "主仓")

    old_hash = module._compute(service, old_row, fields=fields, caliber=caliber)
    new_hash = module._compute(service, new_row, fields=fields, caliber=caliber)
    assert (
        old_hash == new_hash
    ), "两种历史口径归一后必须算出同一个 hash —— 否则重建后同一份快照还是两行"

    # 行内 shop_id 必须被归一(否则存的 raw_data 与它的 hash 对不上)
    normalized, changed = module._row_for_hash(old_row, caliber)
    assert changed is True
    assert normalized["shop_id"] == "miaoshou_real_001"


def test_rebuild_script_keeps_latest_ingest_row():
    """同一身份键多行时保留「入库时间最新」的那行。"""
    module = _load_script()
    import datetime as dt

    old = _row("xihong", "acct", "SKU-1", "主仓")
    old["id"] = 10
    old["ingest_timestamp"] = dt.datetime(2026, 10, 26, tzinfo=dt.timezone.utc)
    new = _row("acct", "acct", "SKU-1", "主仓")
    new["id"] = 11
    new["ingest_timestamp"] = dt.datetime(2026, 11, 5, tzinfo=dt.timezone.utc)

    assert module._keep_row([old, new])["id"] == 11
    assert module._keep_row([new, old])["id"] == 11


def test_rebuild_script_is_read_only_by_default():
    """默认**只读**: 不带 ``--apply`` 绝不能写库。

    为什么: 这是直接改生产事实表的脚本 ⇒ 误触发的代价是数据损坏。
    """
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "if not args.apply:" in source, "脚本必须有 --apply 闸门"
    assert "DELETE FROM" in source, "脚本应当真的能删重复行(否则重建没意义)"
    assert "backup_path" in source, "写库前必须先备份"
