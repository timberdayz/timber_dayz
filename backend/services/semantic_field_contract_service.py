from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select, or_
from sqlalchemy.exc import SQLAlchemyError

from modules.core.db import SemanticFieldContract
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


# [*] analytics(流量)域的中文表头别名。
# 用途: 让语义契约能从**平台原始表头**推断出语义键, 而不是只依赖模板里
# 人工填写的 header_bindings。
# 背景: 已发布模板里 header_bindings 的 semantic_key 覆盖率极低
# (tiktok/analytics 71 个绑定只有 12 个有 semantic_key), 导致 required 语义键
# 根本解析不出来 -> 契约状态恒为 breaking_drift(哪怕文件与模板 100% 一致)。
ANALYTICS_SEMANTIC_ALIASES: dict[str, tuple[str, ...]] = {
    "metric_date": ("日期", "统计日期", "交易日期", "日期时间", "date"),
    "shop_id": ("店铺", "店铺id", "店铺名称", "shop_id", "shop id"),
    "visitor_count": ("商品访客数", "访客数", "访客量", "访问用户数", "uv"),
    "page_views": ("页面浏览次数", "页面浏览量", "页面浏览数", "商品浏览量", "浏览量", "pv"),
    "conversion_rate": ("转化率", "conversion_rate"),
    "order_count": ("订单数", "支付订单数", "成交订单数", "order_count"),
    "gmv": ("gmv", "成交金额", "成交额", "交易额"),
}


# 按数据域组织的语义键别名表
DOMAIN_SEMANTIC_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "orders": ORDER_SEMANTIC_ALIASES,
    "analytics": ANALYTICS_SEMANTIC_ALIASES,
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
