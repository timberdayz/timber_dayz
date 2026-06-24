from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, or_
from sqlalchemy.exc import SQLAlchemyError

from modules.core.db import SemanticFieldContract


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
        }


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
        SemanticContractDefinition("shop_id", "required", impact_description="业务概览无法按店铺归属流量"),
        SemanticContractDefinition("visitor_count", "required", impact_description="业务概览UV无法计算"),
        SemanticContractDefinition("page_views", "required", impact_description="业务概览PV无法计算"),
        SemanticContractDefinition("conversion_rate", "optional"),
        SemanticContractDefinition("order_count", "optional"),
        SemanticContractDefinition("gmv", "optional"),
    ),
}


ORDER_SEMANTIC_ALIASES: dict[str, tuple[str, ...]] = {
    "order_id": ("订单编号", "订单号", "order_id", "order no", "order_no", "order id"),
    "shop_id": ("店铺", "店铺id", "shop_id", "shop id", "shop_name", "shop name"),
    "order_date": ("下单时间", "下单日期", "订单日期", "订单时间", "order_date", "order time", "order_time"),
    "sales_volume": ("销售数量", "出库数量", "销量", "sold_qty", "sales_volume", "quantity"),
    "paid_amount": (
        "买家支付",
        "买家支付(rmb)",
        "买家支付（rmb）",
        "实付金额",
        "buyer_paid",
        "paid_amount",
    ),
    "profit": ("利润", "利润(rmb)", "利润（rmb）", "profit", "profit_amount", "profit_rmb"),
    "estimated_settlement_amount": (
        "预估回款金额",
        "预估回款金额(rmb)",
        "预估回款金额（rmb）",
        "estimated_settlement",
        "estimated_settlement_amount",
    ),
    "settlement_time": ("结算时间", "settlement_time", "settlement date"),
    "cost_profit_rate": ("成本利润率", "cost_profit_rate"),
}


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
    ) -> SemanticContractResult:
        definitions = await self._load_contracts(
            platform=platform,
            data_domain=data_domain,
            granularity=granularity,
            sub_domain=sub_domain,
            consumer=consumer,
        )
        if not definitions:
            return SemanticContractResult(status="not_configured", should_block=False, has_contract=False)

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
        required_keys = [item.semantic_key for item in definitions if item.importance == "required"]
        optional_keys = [
            item.semantic_key
            for item in definitions
            if item.importance == "optional" and item.semantic_key in template_declared_keys
        ]
        missing_required = [key for key in required_keys if key not in resolved_keys]
        missing_optional = [key for key in optional_keys if key not in resolved_keys]

        known_raw_columns = set(template_columns or [])
        known_raw_columns.update(raw_to_semantic.keys())
        extra_raw_fields = [column for column in current_columns if str(column) not in known_raw_columns]

        status = "ready"
        should_block = False
        if missing_required:
            status = "breaking_drift"
            should_block = True
        elif missing_optional or extra_raw_fields:
            status = "non_breaking_drift"

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
        )

    @classmethod
    def _infer_semantic_keys(
        cls,
        *,
        data_domain: str | None,
        columns: list[str],
    ) -> set[str]:
        if str(data_domain or "").strip().lower() != "orders":
            return set()
        normalized_columns = {cls._normalize_alias(column) for column in columns}
        return {
            semantic_key
            for semantic_key, aliases in ORDER_SEMANTIC_ALIASES.items()
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
