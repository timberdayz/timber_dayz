"""B5 护栏测试：库存域的**真实消费方**必须登记在册，且不得凭空编造。

锁住四件事
----------
1. **四个消费方齐全** —— 库存域必须登记 ``business_overview`` + 3 个真实消费方，
   每个 6 个语义键 ⇒ 24 行。
2. **不新增阻断** —— ``importance`` 一律 ``optional``
   （契约的 ``required`` 是运行时阻断源）。
3. **标识不得编** —— 每个 consumer 的代码锚点**必须真实存在**于仓库里，
   且 consumer 标识本身必须能在代码里搜到（不许凭空起名）。
4. **零功能影响** —— 新登记的 consumer **不得**被任何判定链传入
   （判定链只认 ``business_overview``）⇒ 本次只是「让影响面可查」。
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

MIGRATION_PATH = (
    REPO_ROOT
    / "current_migrations"
    / "versions"
    / "20261232_inventory_contract_consumers.py"
)
QUERY_SCRIPT_PATH = REPO_ROOT / "scripts" / "query_semantic_contract_impact.py"

#: 库存域已登记的 6 个语义键（与既有 ``business_overview`` 那 6 行一致）。
EXPECTED_SEMANTIC_KEYS = {
    "platform_sku",
    "sku_id",
    "product_id",
    "product_name",
    "warehouse_name",
    "metric_date",
}

#: 库存域的 4 个消费方。
EXPECTED_CONSUMERS = {
    "business_overview",
    "product_center",
    "sku_clearance_ranking",
    "low_stock_alert",
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_20261232", MIGRATION_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_registers_every_inventory_consumer():
    """三个待补登记的 consumer × 6 个语义键 = 18 行。"""
    module = _load_migration()

    assert set(module._INVENTORY_SEMANTIC_KEYS) == EXPECTED_SEMANTIC_KEYS
    assert len(module._INVENTORY_SEMANTIC_KEYS) == 6

    consumers = {consumer for consumer, _impact in module._CONSUMER_IMPACTS}
    assert consumers == EXPECTED_CONSUMERS - {"business_overview"}
    assert len(module._CONSUMER_IMPACTS) == 3

    # 补登记 + 既有的 business_overview ⇒ 4 个消费方 × 6 键 = 24 行。
    assert len(consumers | {"business_overview"}) * len(EXPECTED_SEMANTIC_KEYS) == 24


def test_migration_never_introduces_required_contracts():
    """``required`` 是运行时阻断源 —— 这次只是登记影响面，**不许**新增阻断。"""
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "'optional'" in source
    assert "'required'" not in source


def test_registered_consumers_are_backed_by_real_code_anchors():
    """每个 consumer 的影响面说明里提到的**代码锚点必须真实存在**。

    「不得编」不能靠人自觉 ⇒ 机器检查：说明里出现的每个 ``路径/文件.py``
    都必须在仓库里存在。
    """
    module = _load_migration()

    for consumer, impact in module._CONSUMER_IMPACTS:
        anchors = re.findall(r"[\w./-]+\.py", impact)
        assert anchors, "{0} 的影响面说明里必须写清代码锚点".format(consumer)
        for anchor in anchors:
            assert (
                REPO_ROOT / anchor
            ).is_file(), "{0} 的锚点 {1} 在仓库里不存在 —— 消费方标识不得凭空编".format(
                consumer, anchor
            )

        # consumer 标识本身也要能在代码里搜到（不许凭空起名）。
        assert consumer in _consumer_identifier_sources(consumer)


def _consumer_identifier_sources(consumer: str) -> str:
    """在仓库里搜 consumer 标识，返回命中的文本。"""
    hits = []
    for relative in (
        "backend/services/inventory/sku_clearance_service.py",
        "backend/tasks/scheduled_tasks.py",
        "backend/domains/business/routers/product_center.py",
        "sql/api_modules/sku_clearance_ranking_module.sql",
    ):
        path = REPO_ROOT / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if consumer in text:
            hits.append(text)
    return "\n".join(hits)


def test_new_consumers_are_not_passed_into_the_judgement_chain():
    """新登记的 consumer **不得**被判定链传入 ⇒ 本次改动零功能影响。

    ``semantic_field_contract_service`` 判定时按 consumer 过滤；
    全仓只有 ``business_overview`` 被真正传入过 ⇒ 新登记的行不会被读到。
    """
    service_source = (
        REPO_ROOT / "backend" / "services" / "semantic_field_contract_service.py"
    ).read_text(encoding="utf-8")
    assert 'consumer: str = "business_overview"' in service_source

    for consumer in ("product_center", "sku_clearance_ranking", "low_stock_alert"):
        # 除迁移与本测试外，不许有代码把这些 consumer 传给判定链。
        offenders = []
        for path in (REPO_ROOT / "backend").rglob("*.py"):
            if path.name == Path(__file__).name:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            if (
                'consumer="{0}"'.format(consumer) in text
                or "consumer='{0}'".format(consumer) in text
            ):
                offenders.append(str(path.relative_to(REPO_ROOT)))
        assert not offenders, "这些 consumer 不该被判定链传入：{0}".format(offenders)


def test_impact_query_script_is_read_only():
    """「影响面可查」这条验收没有治理看板 ⇒ 靠这个只读脚本。

    脚本必须**只发 SELECT** —— 不许顺手写一张表。
    """
    source = QUERY_SCRIPT_PATH.read_text(encoding="utf-8")
    assert "core.semantic_field_contracts" in source
    for forbidden in ("INSERT INTO", "UPDATE ", "DELETE FROM", "DROP "):
        assert forbidden not in source, "影响面查询脚本必须是只读的，发现：{0}".format(
            forbidden
        )
