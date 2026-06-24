from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import FieldMappingTemplate


_SHOPEE_ORDER_BINDINGS: dict[str, str] = {
    "销售数量": "sales_volume",
    "买家支付": "paid_amount",
    "买家支付(RMB)": "paid_amount",
    "买家支付（RMB）": "paid_amount",
    "利润": "profit",
    "利润(RMB)": "profit",
    "利润（RMB）": "profit",
    "预估回款金额": "estimated_settlement_amount",
    "预估回款金额(RMB)": "estimated_settlement_amount",
    "预估回款金额（RMB）": "estimated_settlement_amount",
    "结算时间": "settlement_time",
}


async def backfill_published_shopee_orders_template_bindings(
    session: AsyncSession,
) -> dict[str, int]:
    result = await session.execute(
        select(FieldMappingTemplate).where(
            FieldMappingTemplate.platform == "shopee",
            FieldMappingTemplate.data_domain == "orders",
            FieldMappingTemplate.granularity.in_(["daily", "monthly"]),
            FieldMappingTemplate.status == "published",
        )
    )
    templates = result.scalars().all()

    templates_updated = 0
    bindings_updated = 0
    for template in templates:
        changed = False
        bindings = [
            dict(binding)
            for binding in (template.header_bindings or [])
            if isinstance(binding, dict)
        ]
        by_raw_name = {
            str(binding.get("raw_name") or binding.get("display_name") or ""): binding
            for binding in bindings
        }

        for raw_name in template.header_columns or []:
            semantic_key = _SHOPEE_ORDER_BINDINGS.get(str(raw_name))
            if not semantic_key:
                continue
            binding = by_raw_name.get(str(raw_name))
            if binding is None:
                binding = _new_binding(str(raw_name), semantic_key, len(bindings))
                bindings.append(binding)
                by_raw_name[str(raw_name)] = binding
                changed = True
                bindings_updated += 1
                continue
            if binding.get("semantic_key") != semantic_key:
                binding["semantic_key"] = semantic_key
                changed = True
                bindings_updated += 1

        if changed:
            template.header_bindings = bindings
            templates_updated += 1

    if templates_updated:
        await session.commit()

    return {
        "templates_checked": len(templates),
        "templates_updated": templates_updated,
        "bindings_updated": bindings_updated,
    }


def _new_binding(raw_name: str, semantic_key: str, position: int) -> dict[str, Any]:
    return {
        "raw_name": raw_name,
        "display_name": raw_name,
        "semantic_key": semantic_key,
        "position": position,
        "required": False,
        "hash_participates": False,
    }
