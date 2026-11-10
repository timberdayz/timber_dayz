"""当前采集范围的读取入口（数据新鲜度分档的 SSOT）。

为什么要有这个模块
------------------
「这条链现在还在不在采」这件事，仓库里**从来没有被定义过**：
``source_freshness_service`` 只能一刀切地按粒度阈值判 ``stale`` ⇒
「曾采过、现已停采」的链和「正在采、只是慢了」的链混在一起拉高整体红灯。

本模块给出**唯一**口径：**当前采集范围 = 数据库里实际生效的采集配置**。
这正是采集器自己用的那一份 —— 执行侧
``backend/services/collection_config_execution.py::create_tasks_for_config``
就是从下面这两张表推任务的：

- ``core.collection_configs``（配置级）
  - ``platform``      —— 平台
  - ``data_domains``  —— 配置声明的域清单（**JSON 数组**，如 ``["products","analytics"]``）
  - ``is_active``     —— 配置是否启用（执行侧只认这一列）
- ``core.collection_config_shop_scopes``（店铺级）
  - ``config_id``     —— 归属配置
  - ``data_domains``  —— 该店铺实际采的域（**JSON 数组**）—— **执行侧真正用的列**
  - ``enabled``       —— 该店铺范围是否参与（执行侧按 ``enabled`` 过滤）

口径细则
--------
1. 只有 ``is_active`` 的配置算「生效」。
2. 配置**有**店铺范围行时，域集合取**启用**的店铺范围行的并集
   （店铺范围是配置的细化，不额外加域）；店铺范围行**全部停用**时该配置不贡献任何域
   （与执行侧「没有启用的 scope 就不建任务」一致）。
3. 配置**没有**任何店铺范围行时，域集合退回配置自身的 ``data_domains``
   （配置还没展开到店铺这一步）。
4. ``DEFAULT_CONFIG_DATA_DOMAINS``（``backend/services/collection_contracts.py``）
   是**可选域全集**，不是当前采集范围 —— 它只在**数据库读不到**时兜底，
   且兜底会在结论里显式标注（``source = "fallback_default_domains"``）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.collection_contracts import DEFAULT_CONFIG_DATA_DOMAINS

__all__ = [
    "COLLECTION_SCOPE_SQL",
    "SCOPE_SOURCE_DATABASE",
    "SCOPE_SOURCE_FALLBACK",
    "SCOPE_STATUS_IN_SCOPE",
    "SCOPE_STATUS_OUT_OF_SCOPE",
    "SCOPE_STATUS_UNKNOWN",
    "CollectionScope",
    "fallback_collection_scope",
    "load_collection_scope",
    "normalize_scope_domains",
]

#: 采集范围的来源标记。
SCOPE_SOURCE_DATABASE = "database"
SCOPE_SOURCE_FALLBACK = "fallback_default_domains"

#: 一条链与「当前采集范围」的关系。
SCOPE_STATUS_IN_SCOPE = "in_scope"  # 还在采
SCOPE_STATUS_OUT_OF_SCOPE = "out_of_scope"  # 曾采过、现已不在当前采集范围
SCOPE_STATUS_UNKNOWN = "unknown"  # 判不了（歧义宁可落 unknown，也不猜一个）

#: 一行 = 一个生效配置 + 它的店铺范围行（LEFT JOIN，enabled 单独取列）。
COLLECTION_SCOPE_SQL = """
SELECT c.id, c.platform, c.data_domains, s.data_domains, s.enabled
FROM core.collection_configs c
LEFT JOIN core.collection_config_shop_scopes s
       ON s.config_id = c.id
WHERE c.is_active IS TRUE
ORDER BY c.id, s.id
"""

_EXPECTED_COLUMN_COUNT = 5


def normalize_scope_domains(raw: Any) -> list[str]:
    """把 ``data_domains`` 归一成字符串列表。

    ⚠️ 用原生 SQL 读 ``core.collection_configs.data_domains``（JSON 列）时，
    驱动默认把 JSON **当字符串**返回（仓库既有代码
    ``backend/services/data_pipeline/order_source_governance.py`` 也是这么处理的）
    ⇒ 这里必须能吃 JSON 文本，否则 ``["products"]`` 会被当成一个域名字符串。
    """
    if raw is None:
        return []
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        text_value = raw.strip()
        if text_value.startswith("[") or text_value.startswith("{"):
            try:
                raw = json.loads(text_value)
            except (TypeError, ValueError):
                raw = [text_value]
        else:
            raw = [text_value]
    if isinstance(raw, dict):
        raw = list(raw.keys())
    if not isinstance(raw, (list, tuple, set)):
        return []

    domains: list[str] = []
    for item in raw:
        value = str(item or "").strip().lower()
        if value and value not in domains:
            domains.append(value)
    return domains


@dataclass(frozen=True)
class CollectionScope:
    """「当前采集范围」的一份快照。

    - ``domains_by_platform``：平台 → 该平台当前生效的域集合
    - ``source``：``database``（读到了数据库）或 ``fallback_default_domains``（兜底）
    - ``platform_known``：是否知道「哪些平台配了采集配置」。
      读不到任何生效配置时为 ``False`` ⇒ **任何平台都不能判 out_of_scope**
      （否则空配置表会把告警整体静音）。
    """

    domains_by_platform: Mapping[str, frozenset[str]] = field(default_factory=dict)
    source: str = SCOPE_SOURCE_FALLBACK
    detail: str = ""
    config_count: int = 0
    shop_scope_count: int = 0
    platform_known: bool = False

    def domains_for(self, platform: str | None) -> frozenset[str]:
        """该平台当前生效的域集合。"""
        if self.source == SCOPE_SOURCE_FALLBACK:
            return frozenset(DEFAULT_CONFIG_DATA_DOMAINS)
        key = str(platform or "").strip().lower()
        if not key:
            return frozenset()
        return frozenset(self.domains_by_platform.get(key, frozenset()))

    def has_platform(self, platform: str | None) -> bool:
        """该平台是否有生效的采集配置。"""
        key = str(platform or "").strip().lower()
        if not key:
            return False
        if self.source == SCOPE_SOURCE_FALLBACK:
            # 兜底时我们根本不知道平台清单 ⇒ 一律当作「有配置」，让域集合说了算。
            return True
        if not self.platform_known:
            return False
        return key in self.domains_by_platform

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "detail": self.detail,
            "config_count": self.config_count,
            "shop_scope_count": self.shop_scope_count,
            "platform_known": self.platform_known,
            "domains_by_platform": {
                platform: sorted(domains)
                for platform, domains in sorted(self.domains_by_platform.items())
            },
        }


def fallback_collection_scope(reason: str) -> CollectionScope:
    """数据库读不到时的兜底范围（代码里的「可选域全集」）。"""
    return CollectionScope(
        domains_by_platform={},
        source=SCOPE_SOURCE_FALLBACK,
        detail=reason or "collection scope unavailable in database",
        config_count=0,
        shop_scope_count=0,
        platform_known=True,
    )


def _build_scope(rows: Iterable[Any]) -> CollectionScope:
    """把 ``COLLECTION_SCOPE_SQL`` 的结果行归成一份范围快照。

    每行是 ``(config_id, platform, config_data_domains, scope_data_domains, scope_enabled)``。
    行宽不符的（例如下游复用同一个 session 时读到了别处的结果）**直接跳过**，
    不猜 —— 猜错会把「还在采的链」判成停采。
    """
    per_config: dict[Any, dict[str, Any]] = {}
    order: list[Any] = []

    for row in rows:
        try:
            values = list(row)
        except TypeError:
            continue
        if len(values) != _EXPECTED_COLUMN_COUNT:
            continue
        config_id, platform, config_domains, scope_domains, scope_enabled = values
        platform_key = str(platform or "").strip().lower()
        if not platform_key:
            continue

        entry = per_config.get(config_id)
        if entry is None:
            entry = {
                "platform": platform_key,
                "config_domains": set(normalize_scope_domains(config_domains)),
                "scope_domains": set(),
                "has_scope_rows": False,
                "enabled_scope_rows": 0,
            }
            per_config[config_id] = entry
            order.append(config_id)

        if scope_domains is None:
            continue
        entry["has_scope_rows"] = True
        if not scope_enabled:
            continue
        entry["scope_domains"].update(normalize_scope_domains(scope_domains))
        entry["enabled_scope_rows"] += 1

    domains_by_platform: dict[str, set[str]] = {}
    shop_scope_count = 0
    for config_id in order:
        entry = per_config[config_id]
        platform_key = entry["platform"]
        bucket = domains_by_platform.setdefault(platform_key, set())
        shop_scope_count += entry["enabled_scope_rows"]
        if entry["has_scope_rows"]:
            bucket.update(entry["scope_domains"])
        else:
            # 配置还没展开到店铺这一步 ⇒ 用配置自身的域清单。
            bucket.update(entry["config_domains"])

    return CollectionScope(
        domains_by_platform={
            platform: frozenset(domains)
            for platform, domains in domains_by_platform.items()
        },
        source=SCOPE_SOURCE_DATABASE,
        detail=(
            "core.collection_configs + core.collection_config_shop_scopes"
            f"（{len(order)} 个生效配置 / {shop_scope_count} 个生效店铺范围）"
        ),
        config_count=len(order),
        shop_scope_count=shop_scope_count,
        platform_known=bool(domains_by_platform),
    )


async def load_collection_scope(db: AsyncSession) -> CollectionScope:
    """从数据库读当前采集范围；读不到就兜底（并标注用的是兜底）。"""
    try:
        result = await db.execute(text(COLLECTION_SCOPE_SQL))
        rows = result.fetchall()
    except Exception as exc:  # noqa: BLE001 —— 读不到就兜底，不让巡检整体挂掉
        return fallback_collection_scope(
            f"collection scope read failed: {type(exc).__name__}"
        )

    scope = _build_scope(rows)
    if not scope.platform_known:
        # 读到了表但没有任何生效配置 ⇒ 判不了「停采」（可能是空环境/尚未配置）。
        return CollectionScope(
            domains_by_platform=scope.domains_by_platform,
            source=SCOPE_SOURCE_DATABASE,
            detail=f"{scope.detail}；没有任何生效配置 ⇒ 无法判定采集范围",
            config_count=scope.config_count,
            shop_scope_count=scope.shop_scope_count,
            platform_known=False,
        )
    return scope
