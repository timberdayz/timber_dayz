from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, or_
from sqlalchemy.exc import SQLAlchemyError

from modules.core.db import SemanticFieldContract
from backend.services.semantic_field_registry import (  # [*] 批次 D: 唯一口径
    ANALYTICS_SEMANTIC_ALIASES as _REGISTRY_ANALYTICS_SEMANTIC_ALIASES,
    DOMAIN_SEMANTIC_ALIASES as _REGISTRY_DOMAIN_SEMANTIC_ALIASES,
    ORDER_SEMANTIC_ALIASES as _REGISTRY_ORDER_SEMANTIC_ALIASES,
    get_semantic_field_meta,
)
from backend.services.data_sync_status_semantics import (
    SEMANTIC_CONTRACT_STATUS_BREAKING_DRIFT,
    SEMANTIC_CONTRACT_STATUS_NON_BREAKING_DRIFT,
    SEMANTIC_CONTRACT_STATUS_NOT_CONFIGURED,
    SEMANTIC_CONTRACT_STATUS_READY,
)


@dataclass(frozen=True)
class SemanticContractDefinition:
    semantic_key: str
    importance: str
    consumer: str = "business_overview"
    impact_description: str | None = None


@dataclass
class SemanticContractResult:
    status: str
    should_block: bool
    missing_required_keys: list[str] = field(default_factory=list)
    missing_optional_keys: list[str] = field(default_factory=list)
    resolved_required_keys: list[str] = field(default_factory=list)
    resolved_optional_keys: list[str] = field(default_factory=list)
    extra_raw_fields: list[str] = field(default_factory=list)
    impact_descriptions: list[str] = field(default_factory=list)
    has_contract: bool = False
    # [*] 模板里绑定了 optional 语义键、但当前文件没有的原始列名。
    # 这类列的缺失不影响现有入库(例如「预估回款金额」), 属于非阻断漂移。
    optional_removed_raw_fields: list[str] = field(default_factory=list)
    # [*] 批次 F-3: 域级下限缺口 —— 域级契约的 required 里, **模板清单还没覆盖**的键。
    # 契约降级为「域级下限护栏」后, 这部分不再运行时阻断, 而是**引导用户去勾**
    # (用户勾了 ⇒ 进模板级 required ⇒ 才阻断)。
    below_domain_floor_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "semantic_contract_status": self.status,
            "missing_required_keys": self.missing_required_keys,
            "missing_optional_keys": self.missing_optional_keys,
            "resolved_required_keys": self.resolved_required_keys,
            "resolved_optional_keys": self.resolved_optional_keys,
            "extra_raw_fields": self.extra_raw_fields,
            "impact_descriptions": self.impact_descriptions,
            "has_semantic_contract": self.has_contract,
            "optional_removed_raw_fields": self.optional_removed_raw_fields,
            "below_domain_floor_keys": self.below_domain_floor_keys,
        }


#: [*] 批次 F-3: 契约 required 里**不参与运行时阻断**的语义键类别。
#:
#: 背景(规格 §3.4「角色降为域级下限护栏」):
#: 契约表的 required 里混着指标类(``page_views`` / ``visitor_count`` /
#: ``paid_amount`` / ``sales_volume`` / ``profit``)。这些字段缺失就把整批文件
#: 拦下来是**误伤** —— 指标缺失该由「模板级 required(用户勾的)」来管。
#:
#: ⇒ **身份/时间类**仍是硬要求(它们是「这一行是什么」的前提, 缺了整行无意义);
#: **指标类**降为域级下限(缺口可见、可引导, 但不拦批次)。
NON_BLOCKING_CONTRACT_KINDS: frozenset[str] = frozenset({"metric"})


def _semantic_kind(semantic_key: str) -> str:
    """语义键的类别(``identity`` / ``time`` / ``metric`` / ``dimension`` / ...)。"""
    meta = get_semantic_field_meta(semantic_key)
    return str(meta.get("kind") or "").strip().lower()


DEFAULT_CONTRACTS: dict[str, tuple[SemanticContractDefinition, ...]] = {
    "orders": (
        SemanticContractDefinition("order_id", "required", impact_description="业务概览订单数无法计算"),
        SemanticContractDefinition("shop_id", "required", impact_description="业务概览无法按店铺归属订单"),
        SemanticContractDefinition("order_date", "required", impact_description="业务概览无法按期间归集订单"),
        SemanticContractDefinition("sales_volume", "required", impact_description="业务概览销售数量无法计算"),
        SemanticContractDefinition("paid_amount", "required", impact_description="业务概览销售额和转化率无法计算"),
        SemanticContractDefinition("profit", "required", impact_description="业务概览利润指标无法计算"),
        SemanticContractDefinition("estimated_settlement_amount", "optional"),
        SemanticContractDefinition("settlement_time", "optional"),
        SemanticContractDefinition("cost_profit_rate", "optional"),
    ),
    "analytics": (
        SemanticContractDefinition("metric_date", "required", impact_description="业务概览流量无法按日期归集"),
        # [*] shop_id 降级为 optional: TikTok 流量导出格式里**没有店铺列**,
        # 店铺归属来自 catalog_files.shop_id(文件元数据), 而不是表头。
        # 之前把 shop_id 列为 required, 导致 analytics 契约永远 breaking_drift。
        SemanticContractDefinition("shop_id", "optional", impact_description="业务概览无法按店铺归属流量"),
        SemanticContractDefinition("visitor_count", "required", impact_description="业务概览UV无法计算"),
        SemanticContractDefinition("page_views", "required", impact_description="业务概览PV无法计算"),
        SemanticContractDefinition("conversion_rate", "optional"),
        SemanticContractDefinition("order_count", "optional"),
        SemanticContractDefinition("gmv", "optional"),
    ),
}


# [*] 批次 D: 域限定别名表已搬到 ``semantic_field_registry``(唯一口径)。
#
# 以前它们只被**契约判定**用, 从没进过「列名 → 语义键」的推断链路 ——
# 于是「页面浏览数」明明有别名(page_views), 推断时却认不出来, 命中率只有 3~6%。
# 现在注册表是唯一出处, 契约判定与推断共用同一份。
ORDER_SEMANTIC_ALIASES = _REGISTRY_ORDER_SEMANTIC_ALIASES
ANALYTICS_SEMANTIC_ALIASES = _REGISTRY_ANALYTICS_SEMANTIC_ALIASES
DOMAIN_SEMANTIC_ALIASES = _REGISTRY_DOMAIN_SEMANTIC_ALIASES


def _core_field_required_keys(core_fields: list[dict[str, Any]] | None) -> list[str]:
    """模板级核心字段清单里 ``required=true`` 的语义键(批次 E)。

    只取**有语义键**的条目 —— 翻译不出来的物理列名没有语义键,
    无法参与「按语义键判定缺失」, 只能靠逐字兜底。
    """
    from backend.services.core_fields_service import normalize_core_fields

    keys: list[str] = []
    for entry in normalize_core_fields(core_fields):
        semantic_key = entry.get("semantic_key")
        if not semantic_key or not entry.get("required"):
            continue
        if semantic_key not in keys:
            keys.append(semantic_key)
    return keys


class SemanticFieldContractService:
    def __init__(self, db):
        self.db = db

    async def evaluate(
        self,
        *,
        platform: str | None,
        data_domain: str | None,
        granularity: str | None,
        sub_domain: str | None,
        header_bindings: list[dict[str, Any]] | None,
        current_columns: list[str],
        template_columns: list[str] | None = None,
        consumer: str = "business_overview",
        core_fields: list[dict[str, Any]] | None = None,
        ignored_extra_fields: list[str] | None = None,
    ) -> SemanticContractResult:
        """判定语义契约状态(漂移阻断链的第 ② 层)。

        [*] 批次 E(E-5): ``core_fields`` = **模板级核心字段清单**。
        规格 §3.1「漂移阻断 = ``core_fields`` 中 ``required=true`` 的
        **∪** 域级契约 required」。

        为什么接进来**不会**让现有模板突然卡死
        ----------------------------------------
        清单的 ``required`` 由迁移回填, 回填口径是「域级契约 required
        ∩ 清单条目」⇒ **是域级契约 required 的子集** ⇒ 并入后
        ``missing_required_keys`` 不变。

        真正让它变严的是**用户在模板里勾选**(前端两级勾选)⇒
        那才是「用户勾一次, 阻断也跟着收紧一次」。

        注: 本方法在「该域没有契约」时提前返回 ``not_configured``
        ⇒ 清单的 required 在无契约域不参与阻断(与既有行为一致)。
        """
        definitions = await self._load_contracts(
            platform=platform,
            data_domain=data_domain,
            granularity=granularity,
            sub_domain=sub_domain,
            consumer=consumer,
        )
        if not definitions:
            return SemanticContractResult(
                status=SEMANTIC_CONTRACT_STATUS_NOT_CONFIGURED,
                should_block=False,
                has_contract=False,
            )

        current_set = {str(column) for column in current_columns}
        bindings = header_bindings or []
        raw_to_semantic = self._raw_to_semantic(bindings)
        inferred_current_keys = self._infer_semantic_keys(
            data_domain=data_domain,
            columns=current_columns,
        )
        inferred_template_keys = self._infer_semantic_keys(
            data_domain=data_domain,
            columns=template_columns or [],
        )
        resolved_keys = {
            semantic_key
            for raw_name, semantic_key in raw_to_semantic.items()
            if raw_name in current_set
        }
        resolved_keys.update(inferred_current_keys)
        resolved_keys.update(column for column in current_set if column in {item.semantic_key for item in definitions})

        template_declared_keys = set(raw_to_semantic.values())
        template_declared_keys.update(inferred_template_keys)
        template_declared_keys.update(
            column
            for column in set(template_columns or [])
            if column in {item.semantic_key for item in definitions}
        )
        # [*] 批次 F-3: 契约降为「域级下限护栏」(规格 §3.4)。
        #     域级契约的 required 分两类:
        #       * 身份/时间类 ⇒ 仍是硬要求(缺了整行就没有意义) ⇒ 阻断;
        #       * 指标类     ⇒ 降为下限(缺口可见、可引导, 但不拦批次)。
        #     模板级清单的 required 是**主来源**(用户勾的) ⇒ 照旧阻断。
        contract_required_keys = [
            item.semantic_key for item in definitions if item.importance == "required"
        ]
        domain_floor_keys = list(contract_required_keys)
        required_keys = [
            key
            for key in contract_required_keys
            if _semantic_kind(key) not in NON_BLOCKING_CONTRACT_KINDS
        ]
        # [*] 批次 E(E-5): 并入**模板级核心字段清单**里 required=true 的语义键。
        #     规格 §3.1: 漂移阻断 = 清单 required ∪ 域级契约 required。
        required_keys.extend(
            key
            for key in _core_field_required_keys(core_fields)
            if key not in required_keys
        )
        optional_keys = [
            item.semantic_key
            for item in definitions
            if item.importance == "optional" and item.semantic_key in template_declared_keys
        ]
        missing_required = [key for key in required_keys if key not in resolved_keys]
        missing_optional = [key for key in optional_keys if key not in resolved_keys]

        known_raw_columns = set(template_columns or [])
        known_raw_columns.update(raw_to_semantic.keys())
        # [*] 批次 F-4(API-6): 「已确认的新列」忽略清单 ——
        #     用户在模板里勾了「这列我确认过、忽略它」⇒ 不再算成新增噪音。
        #     (治理面板上它是一条**永久噪音**: 不阻断, 但每次都被报出来。)
        ignored_columns = {
            str(column).strip()
            for column in (ignored_extra_fields or [])
            if str(column).strip()
        }
        extra_raw_fields = [
            column
            for column in current_columns
            if str(column) not in known_raw_columns
            and str(column).strip() not in ignored_columns
        ]

        # [*] 模板里绑定了 optional 语义键、但当前文件没有的原始列名。
        # 这类列的缺失不阻断入库(例如「预估回款金额」), 属于非阻断漂移。
        optional_semantic_keys = {
            item.semantic_key for item in definitions if item.importance == "optional"
        }
        optional_removed_raw_fields = [
            raw_name
            for raw_name, semantic_key in raw_to_semantic.items()
            if semantic_key in optional_semantic_keys and raw_name not in current_set
        ]

        status = SEMANTIC_CONTRACT_STATUS_READY
        should_block = False
        if missing_required:
            status = SEMANTIC_CONTRACT_STATUS_BREAKING_DRIFT
            should_block = True
        elif missing_optional or extra_raw_fields:
            status = SEMANTIC_CONTRACT_STATUS_NON_BREAKING_DRIFT

        impact_by_key = {
            item.semantic_key: item.impact_description
            for item in definitions
            if item.impact_description
        }
        impact_descriptions = [
            impact_by_key[key]
            for key in missing_required
            if key in impact_by_key
        ]

        # [*] 批次 F-3: 域级下限缺口 —— 域级契约 required 里, **模板清单还没覆盖**的键。
        #     缺口**不阻断**, 但要暴露出来(前端治理面板引导用户去勾):
        #     用户勾了 ⇒ 进模板级 required ⇒ 那时才阻断。
        #
        #     只认**清单里用户勾过的**语义键 ——
        #     批次 D 的硬约束:「只有用户确认过的绑定才允许被提升成语义身份」。
        #     推断出来的键不算(那是猜测, 不是用户的选择)。
        from backend.services.core_fields_service import normalize_core_fields

        template_covered_keys = {
            key
            for key in (
                entry.get("semantic_key")
                for entry in normalize_core_fields(core_fields)
            )
            if key
        }
        below_domain_floor_keys = [
            key for key in domain_floor_keys if key not in template_covered_keys
        ]

        return SemanticContractResult(
            status=status,
            should_block=should_block,
            missing_required_keys=missing_required,
            missing_optional_keys=missing_optional,
            resolved_required_keys=[key for key in required_keys if key in resolved_keys],
            resolved_optional_keys=[key for key in optional_keys if key in resolved_keys],
            extra_raw_fields=extra_raw_fields,
            impact_descriptions=impact_descriptions,
            has_contract=True,
            optional_removed_raw_fields=optional_removed_raw_fields,
            below_domain_floor_keys=below_domain_floor_keys,
        )

    @classmethod
    def _infer_semantic_keys(
        cls,
        *,
        data_domain: str | None,
        columns: list[str],
    ) -> set[str]:
        """从原始表头推断语义键(按数据域的别名表)。

        之前只处理 ``orders``, 导致 analytics/流量域的 required 语义键
        (访客数/页面浏览量等) 只能依赖模板里人工填写的 header_bindings;
        而实际覆盖率极低(tiktok/analytics 71 个绑定只有 12 个有 semantic_key),
        契约状态因此恒为 breaking_drift —— 哪怕文件与模板 100% 一致。
        """
        domain = str(data_domain or "").strip().lower()
        aliases_by_key = DOMAIN_SEMANTIC_ALIASES.get(domain)
        if not aliases_by_key:
            return set()
        normalized_columns = {cls._normalize_alias(column) for column in columns}
        return {
            semantic_key
            for semantic_key, aliases in aliases_by_key.items()
            if any(cls._normalize_alias(alias) in normalized_columns for alias in aliases)
        }

    @staticmethod
    def _normalize_alias(value: Any) -> str:
        return str(value or "").strip().lower().replace("（", "(").replace("）", ")")

    async def _load_contracts(
        self,
        *,
        platform: str | None,
        data_domain: str | None,
        granularity: str | None,
        sub_domain: str | None,
        consumer: str,
    ) -> list[SemanticContractDefinition]:
        db_contracts = await self._load_contracts_from_db(
            platform=platform,
            data_domain=data_domain,
            granularity=granularity,
            sub_domain=sub_domain,
            consumer=consumer,
        )
        if db_contracts:
            return db_contracts
        return list(DEFAULT_CONTRACTS.get(str(data_domain or "").strip().lower(), ()))

    async def _load_contracts_from_db(
        self,
        *,
        platform: str | None,
        data_domain: str | None,
        granularity: str | None,
        sub_domain: str | None,
        consumer: str,
    ) -> list[SemanticContractDefinition]:
        if self.db is None:
            return []
        try:
            stmt = (
                select(SemanticFieldContract)
                .where(SemanticFieldContract.enabled.is_(True))
                .where(SemanticFieldContract.data_domain == data_domain)
                .where(SemanticFieldContract.consumer == consumer)
                .where(or_(SemanticFieldContract.platform == platform, SemanticFieldContract.platform.is_(None)))
                .where(or_(SemanticFieldContract.granularity == granularity, SemanticFieldContract.granularity.is_(None)))
                .where(or_(SemanticFieldContract.sub_domain == sub_domain, SemanticFieldContract.sub_domain.is_(None)))
            )
            result = await self.db.execute(stmt)
            rows = result.scalars().all()
        except SQLAlchemyError:
            return []

        return [
            SemanticContractDefinition(
                semantic_key=row.semantic_key,
                importance=row.importance,
                consumer=row.consumer,
                impact_description=row.impact_description,
            )
            for row in rows
        ]

    @staticmethod
    def _raw_to_semantic(header_bindings: list[dict[str, Any]]) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for binding in header_bindings:
            if not isinstance(binding, dict):
                continue
            semantic_key = binding.get("semantic_key") or binding.get("standard_field")
            raw_name = (
                binding.get("raw_name")
                or binding.get("source_header")
                or binding.get("display_name")
                or binding.get("original_column")
                or binding.get("name")
            )
            if semantic_key and raw_name:
                mapping[str(raw_name)] = str(semantic_key)
        return mapping
