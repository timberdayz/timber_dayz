from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncio
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import (
    BridgeSpuSku,
    DimErpSku,
    DimSpu,
    FeishuProjectionConfig,
    FeishuProjectionLog,
    FeishuProjectionTask,
    LogisticsBill,
    LogisticsBillLine,
    LogisticsBillLineAllocation,
    SkuProfitEstimate,
    SkuOperatingProfile,
)

from .feishu_projection_client import (
    FEISHU_BATCH_CREATE_LIMIT,
    FEISHU_BATCH_WRITE_INTERVAL_SECONDS,
    FeishuProjectionClient,
)

# 单轮投递最多处理多少条价格调整记录。
# 飞书批量新增单次 500 条 → 这个上限对应 4 批。一次性全量铺开会让单次事务
# 过长，且失败时整批回滚代价大。
PRICE_ADJUST_DELIVERY_LIMIT = 2000


def _to_float(value: Any) -> float | None:
    """把 payload 里的数值转成 float（飞书 number 字段只吃 float）。"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def projection_payload_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class FeishuProjectionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def enqueue(self, entity_type: str, business_key: str, payload: dict[str, Any]) -> FeishuProjectionTask:
        payload_hash = projection_payload_hash(payload)
        existing = (
            await self.db.execute(
                select(FeishuProjectionTask).where(
                    FeishuProjectionTask.entity_type == entity_type,
                    FeishuProjectionTask.business_key == business_key,
                    FeishuProjectionTask.payload_hash == payload_hash,
                    FeishuProjectionTask.status.in_(("pending", "running", "completed")),
                )
            )
        ).scalars().first()
        if existing is not None:
            return existing
        task = FeishuProjectionTask(
            entity_type=entity_type,
            business_key=business_key,
            payload_hash=payload_hash,
            payload_json=payload,
        )
        self.db.add(task)
        await self.db.flush()
        return task

    async def enqueue_full_refresh(self, reason: str) -> int:
        count = 0
        refresh_nonce = datetime.now(timezone.utc).isoformat()
        spus = (await self.db.execute(select(DimSpu).where(DimSpu.active.is_(True)))).scalars().all()
        skus = (await self.db.execute(select(DimErpSku).where(DimErpSku.status == "active"))).scalars().all()
        profiles = (await self.db.execute(select(SkuOperatingProfile).where(SkuOperatingProfile.status == "active", SkuOperatingProfile.effective_to.is_(None)))).scalars().all()
        for spu in spus:
            await self.enqueue("spu", spu.spu, {"reason": reason, "spu": spu.spu, "refresh_nonce": refresh_nonce})
            count += 1
        for sku in skus:
            await self.enqueue("sku", str(sku.sku_id), {"reason": reason, "sku_id": sku.sku_id, "refresh_nonce": refresh_nonce})
            count += 1
        for profile in profiles:
            await self.enqueue("platform_sku_profit", str(profile.profile_id), {"reason": reason, "profile_id": profile.profile_id, "refresh_nonce": refresh_nonce})
            count += 1
        return count

    async def get_config(self) -> FeishuProjectionConfig | None:
        return (
            await self.db.execute(
                select(FeishuProjectionConfig).where(FeishuProjectionConfig.provider_code == "feishu")
            )
        ).scalar_one_or_none()

    async def set_initialized(
        self,
        spu_table_id: str,
        sku_table_id: str,
        platform_sku_profit_table_id: str,
        price_adjust_table_id: str | None = None,
        price_adjust_base_token: str | None = None,
    ) -> FeishuProjectionConfig:
        config = await self.get_config()
        if config is None:
            config = FeishuProjectionConfig(provider_code="feishu")
            self.db.add(config)
        config.spu_table_id = spu_table_id
        config.sku_table_id = sku_table_id
        config.platform_sku_profit_table_id = platform_sku_profit_table_id
        if price_adjust_table_id:
            config.price_adjust_table_id = price_adjust_table_id
        if price_adjust_base_token:
            config.price_adjust_base_token = price_adjust_base_token
        config.status = "ready"
        config.last_error = None
        config.initialized_at = datetime.now(timezone.utc)
        await self.db.flush()
        return config

    async def initialize_tables(
        self,
        client: FeishuProjectionClient,
        spu_table_id: str | None = None,
        sku_table_id: str | None = None,
        platform_sku_profit_table_id: str | None = None,
        price_adjust_table_id: str | None = None,
        price_adjust_base_token: str | None = None,
    ) -> FeishuProjectionConfig:
        existing = await self.get_config()
        spu_table_id = spu_table_id or (existing.spu_table_id if existing else None)
        sku_table_id = sku_table_id or (existing.sku_table_id if existing else None)
        platform_sku_profit_table_id = platform_sku_profit_table_id or (
            existing.platform_sku_profit_table_id if existing else None
        )
        price_adjust_table_id = price_adjust_table_id or (
            existing.price_adjust_table_id if existing else None
        )
        price_adjust_base_token = price_adjust_base_token or (
            existing.price_adjust_base_token if existing else None
        )
        if not spu_table_id:
            spu_table_id = await client.create_table("ERP-SPU经营", _spu_table_fields())
        if not sku_table_id:
            sku_table_id = await client.create_table("ERP-SKU经营明细", _sku_table_fields())
        if not platform_sku_profit_table_id:
            platform_sku_profit_table_id = await client.create_table("ERP-平台SKU利润", _platform_sku_profit_table_fields())
        return await self.set_initialized(
            spu_table_id,
            sku_table_id,
            platform_sku_profit_table_id,
            price_adjust_table_id,
            price_adjust_base_token,
        )

    async def status(self) -> dict[str, Any]:
        config = await self.get_config()
        counts = (
            await self.db.execute(
                select(FeishuProjectionTask.status, func.count())
                .group_by(FeishuProjectionTask.status)
            )
        ).all()
        return {
            "configured": bool(config and config.status == "ready"),
            "spu_table_id": config.spu_table_id if config else None,
            "sku_table_id": config.sku_table_id if config else None,
            "platform_sku_profit_table_id": config.platform_sku_profit_table_id if config else None,
            "price_adjust_table_id": config.price_adjust_table_id if config else None,
            "price_adjust_base_token": config.price_adjust_base_token if config else None,
            "status": config.status if config else "pending",
            "last_error": config.last_error if config else None,
            "tasks": {status: count for status, count in counts},
        }

    async def retry_failed(self) -> int:
        result = await self.db.execute(
            update(FeishuProjectionTask)
            .where(FeishuProjectionTask.status == "failed")
            .values(status="pending", next_retry_at=None, last_error=None)
        )
        return int(result.rowcount or 0)

    async def _sku_payload(self, sku_id: int) -> dict[str, Any]:
        sku = await self.db.get(DimErpSku, sku_id)
        if sku is None:
            raise ValueError("SKU not found for projection")
        binding = (
            await self.db.execute(
                select(BridgeSpuSku).where(
                    BridgeSpuSku.sku_id == sku_id,
                    BridgeSpuSku.binding_status == "active",
                    BridgeSpuSku.effective_to.is_(None),
                )
            )
        ).scalars().first()
        spu = await self.db.get(DimSpu, binding.spu) if binding else None
        allocated_line = (
            await self.db.execute(
                select(LogisticsBillLineAllocation, LogisticsBillLine)
                .join(LogisticsBillLine, LogisticsBillLine.line_id == LogisticsBillLineAllocation.bill_line_id)
                .join(LogisticsBill, LogisticsBill.bill_id == LogisticsBillLine.bill_id)
                .where(LogisticsBillLineAllocation.sku_id == sku_id, LogisticsBill.status == "confirmed")
                .order_by(LogisticsBill.confirmed_at.desc())
            )
        ).first()
        bill_line = (
            await self.db.execute(
                select(LogisticsBillLine)
                .join(LogisticsBill, LogisticsBill.bill_id == LogisticsBillLine.bill_id)
                .where(LogisticsBillLine.sku_id == sku_id, LogisticsBill.status == "confirmed")
                .order_by(LogisticsBill.confirmed_at.desc())
            )
        ).scalars().first()
        estimate = (
            await self.db.execute(
                select(SkuProfitEstimate)
                .where(SkuProfitEstimate.sku_id == sku_id, SkuProfitEstimate.scenario == "base")
                .order_by(SkuProfitEstimate.estimate_as_of.desc())
            )
        ).scalars().first()
        volume = None
        if all(value is not None for value in (sku.package_length_cm, sku.package_width_cm, sku.package_height_cm)):
            volume = sku.package_length_cm * sku.package_width_cm * sku.package_height_cm / 1_000_000
        if allocated_line is not None:
            allocation, allocation_source = allocated_line
            quantity = float(allocation.allocated_quantity or 0)
            ratio = float(allocation.allocation_ratio or 0)
            actual_logistics_cost = float(allocation.allocated_amount or 0) / quantity if quantity else None
            headhaul_cost = float(allocation_source.headhaul_cost or 0) * ratio / quantity if quantity else None
            handling_cost = float(allocation_source.handling_cost or 0) * ratio / quantity if quantity else None
            last_mile_cost = float(allocation_source.last_mile_cost or 0) * ratio / quantity if quantity else None
        else:
            actual_logistics_cost = float(bill_line.line_total_amount or 0) / float(bill_line.shipped_qty) if bill_line and bill_line.shipped_qty else None
            headhaul_cost = float(bill_line.unit_headhaul_cost) if bill_line and bill_line.unit_headhaul_cost is not None else None
            handling_cost = float(bill_line.unit_handling_cost) if bill_line and bill_line.unit_handling_cost is not None else None
            last_mile_cost = float(bill_line.unit_last_mile_cost) if bill_line and bill_line.unit_last_mile_cost is not None else None
        return {
            "ERP SKU": sku.sku_key,
            "SPU": binding.spu if binding else "",
            "商品名称": sku.sku_name or "",
            "规格": sku.specification or "",
            "重量 kg": sku.weight_kg,
            "长 cm": sku.package_length_cm,
            "宽 cm": sku.package_width_cm,
            "高 cm": sku.package_height_cm,
            "体积 m³": volume,
            "箱规": sku.units_per_carton,
            "默认采购成本 RMB": sku.default_purchase_cost,
            "预计物流成本 RMB": sku.expected_logistics_cost,
            "预计仓储成本 RMB": sku.expected_storage_cost,
            "实际物流成本 RMB": actual_logistics_cost,
            "头程单位成本 RMB": headhaul_cost,
            "操作费单位成本 RMB": handling_cost,
            "尾程单位成本 RMB": last_mile_cost,
            "基准预计利润 RMB": float(estimate.estimated_contribution_profit) if estimate and estimate.estimated_contribution_profit is not None else None,
            "基准预计利润率": float(estimate.estimated_margin_rate) if estimate and estimate.estimated_margin_rate is not None else None,
            "采购成本来源": sku.purchase_cost_source or "",
            "物流成本来源": estimate.logistics_cost_source if estimate else "",
            "物流货损率": spu.logistics_damage_rate if spu else None,
            "退货损失率": spu.return_loss_rate if spu else None,
            "数据完整度": estimate.cost_completeness if estimate else "incomplete",
            "更新时间": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }

    async def _spu_payload(self, spu: str) -> dict[str, Any]:
        row = await self.db.get(DimSpu, spu)
        if row is None:
            raise ValueError("SPU not found for projection")
        metrics = (
            await self.db.execute(
                text(
                    """
                    SELECT sku_count, total_qty, inventory_value_rmb, estimated_profit,
                           estimated_margin_rate, snapshot_date, calculated_at
                    FROM mart.spu_operating_current
                    WHERE spu = :spu
                    """
                ),
                {"spu": spu},
            )
        ).mappings().first()
        sku_count = int(metrics["sku_count"] or 0) if metrics else int((await self.db.execute(select(func.count()).select_from(BridgeSpuSku).where(BridgeSpuSku.spu == spu, BridgeSpuSku.binding_status == "active", BridgeSpuSku.effective_to.is_(None)))).scalar() or 0)
        return {
            "SPU": row.spu,
            "商品名称": row.spu_name,
            "一级品类": row.category_l1 or "",
            "二级品类": row.category_l2 or "",
            "经营状态": row.biz_status,
            "负责人": str(row.owner_user_id or ""),
            "SKU数": sku_count,
            "库存数量": float(metrics["total_qty"] or 0) if metrics else 0,
            "库存金额 RMB": float(metrics["inventory_value_rmb"] or 0) if metrics else 0,
            "基准预计利润 RMB": float(metrics["estimated_profit"] or 0) if metrics else 0,
            "基准预计利润率": float(metrics["estimated_margin_rate"]) if metrics and metrics["estimated_margin_rate"] is not None else None,
            "数据完整度": "complete" if metrics else "pending_refresh",
            "计算时间": (metrics["calculated_at"] or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S") if metrics else datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }

    async def _platform_sku_profit_payload(self, profile_id: int) -> dict[str, Any]:
        profile = await self.db.get(SkuOperatingProfile, profile_id)
        if profile is None:
            raise ValueError("SKU operating profile not found for projection")
        sku = await self.db.get(DimErpSku, profile.sku_id)
        estimate = (
            await self.db.execute(
                select(SkuProfitEstimate)
                .where(
                    SkuProfitEstimate.operating_profile_id == profile_id,
                    SkuProfitEstimate.calculation_basis == "estimated",
                )
                .order_by(SkuProfitEstimate.estimate_as_of.desc())
            )
        ).scalars().first()
        binding = (
            await self.db.execute(
                select(BridgeSpuSku).where(
                    BridgeSpuSku.sku_id == profile.sku_id,
                    BridgeSpuSku.binding_status == "active",
                    BridgeSpuSku.effective_to.is_(None),
                )
            )
        ).scalars().first()
        spu = await self.db.get(DimSpu, binding.spu) if binding else None
        from .product_finance_service import ProductFinanceService

        actual_logistics_cost = await ProductFinanceService(self.db).find_confirmed_logistics_cost(
            profile.sku_id, profile.warehouse_code, profile.transport_type
        )
        return {
            "经营范围键": f"{profile.platform_code}+{profile.warehouse_code}+{profile.sku_id}",
            "幂等键说明": "platform_code + warehouse_code + sku_id",
            "平台": profile.platform_code,
            "收货仓库": profile.warehouse_name or profile.warehouse_code,
            "ERP SKU": sku.sku_key if sku else str(profile.sku_id),
            "SPU": binding.spu if binding else "",
            "商品名称": sku.sku_name if sku else "",
            "参考售价": float(sku.reference_selling_price) if sku and sku.reference_selling_price is not None else None,
            "竞品价格": float(profile.competitor_price) if profile.competitor_price is not None else None,
            "预计售价": float(profile.expected_selling_price) if profile.expected_selling_price is not None else None,
            "优惠券": float(profile.seller_coupon_amount) if profile.seller_coupon_amount is not None else None,
            "采购成本": float(estimate.purchase_cost) if estimate and estimate.purchase_cost is not None else None,
            "预计物流成本": float(estimate.expected_logistics_cost) if estimate and estimate.expected_logistics_cost is not None else float(profile.expected_logistics_cost) if profile.expected_logistics_cost is not None else None,
            "预计仓储成本": float(estimate.expected_storage_cost) if estimate and estimate.expected_storage_cost is not None else float(profile.expected_storage_cost) if profile.expected_storage_cost is not None else None,
            "实际物流成本": float(actual_logistics_cost) if actual_logistics_cost is not None else float(estimate.logistics_cost) if estimate and estimate.logistics_cost_source == "confirmed_logistics_bill" and estimate.logistics_cost is not None else None,
            "实际仓储成本": None,
            "平台费率": float(profile.platform_fee_rate) if profile.platform_fee_rate is not None else None,
            "预计广告费率": float(profile.expected_ad_rate) if profile.expected_ad_rate is not None else None,
            "预计广告费用": float(estimate.expected_ad_cost) if estimate and estimate.expected_ad_cost is not None else None,
            "预计贡献利润": float(estimate.estimated_contribution_profit) if estimate and estimate.estimated_contribution_profit is not None else None,
            "预计利润率": float(estimate.estimated_margin_rate) if estimate and estimate.estimated_margin_rate is not None else None,
            "实际成本重估利润": float(estimate.actual_recost_profit) if estimate and estimate.actual_recost_profit is not None else None,
            "实际成本重估利润率": float(estimate.actual_recost_margin_rate) if estimate and estimate.actual_recost_margin_rate is not None else None,
            "成本偏差": float(estimate.total_cost_variance) if estimate and estimate.total_cost_variance is not None else None,
            "计算口径": estimate.calculation_basis if estimate else "",
            "货损率": spu.logistics_damage_rate if spu else None,
            "退货损失率": spu.return_loss_rate if spu else None,
            "成本来源": estimate.logistics_cost_source if estimate else "",
            "数据完整度": estimate.cost_completeness if estimate else "incomplete",
            "置信度": estimate.confidence_level if estimate else "low",
            "版本": estimate.assumption_version if estimate else "",
            "估算时间": estimate.estimate_as_of if estimate else None,
            "更新时间": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }

    def _price_adjust_payload(self, task: FeishuProjectionTask) -> dict[str, Any]:
        """把 outbox payload 组装成飞书「调价记录表」的行字段。

        ⚠️ **「变动时间」不来自 payload**，而是取 outbox 任务的 `created_at`：
        payload 的哈希是去重依据，若把每次都变的时间戳塞进 payload，
        同一次变化重跑时哈希就不同，去重会失效。
        """
        payload = dict(task.payload_json or {})
        changed_at = task.created_at or datetime.now(timezone.utc)

        fields: dict[str, Any] = {
            "ERP SKU": payload.get("sku_key"),
            "SPU": payload.get("spu") or "",
            "商品名称": payload.get("sku_name") or "",
            "规格": payload.get("specification") or "",
            "上次最低售价": _to_float(payload.get("old_min_selling_price")),
            "新最低售价": _to_float(payload.get("new_min_selling_price")),
            "变动幅度": payload.get("change_rate"),
            "库龄天数": payload.get("age_days"),
            "命中档位": payload.get("pricing_tier_label") or "",
            "库存数量": payload.get("current_qty"),
            "库存金额": _to_float(payload.get("inventory_value")),
            "变动时间": changed_at.isoformat(),
        }
        # 单选字段在飞书 API 里是字符串数组
        if payload.get("direction"):
            fields["变动方向"] = [payload["direction"]]
        if payload.get("reason"):
            fields["变动原因"] = [payload["reason"]]
        # 「平台」「当前售价」第一版不写：
        #   平台——第一版按 SKU 粒度推送，平台粒度等售价数据源打通后再细化
        #   当前售价——目前没有可靠数据源（平台 SKU 档案靠人工维护，覆盖率未知），
        #            填一个可能错的数比留空更危险
        return {key: value for key, value in fields.items() if value is not None}

    async def _advance_price_adjust_baseline(self, task: FeishuProjectionTask) -> None:
        """价格调整记录**投递成功后**推进基线。

        顺序不能反：ERP 侧只新增、不更新，没有"重写旧行"这个补救动作。
        先推基线再投递，一旦飞书写失败（限流 1254291、网络抖动、token 过期），
        基线已被推进，那次变化就永远不会再被检出——最该通知的变化被静默吞掉。

        实现本身复用 `PriceAdjustNotifyService.advance_baseline_for_sku`，
        **不另写一份**——基线读写只有那一处实现。
        """
        payload = dict(task.payload_json or {})
        sku_id = payload.get("sku_id")
        context = payload.get("context")
        if sku_id is None or not context:
            return
        from .price_adjust_notify_service import PriceAdjustNotifyService

        await PriceAdjustNotifyService(self.db).advance_baseline_for_sku(
            int(sku_id),
            payload.get("new_min_selling_price"),
            context,
        )

    async def _process_price_adjust_tasks(
        self, config: FeishuProjectionConfig, client: FeishuProjectionClient
    ) -> int:
        """批量新增价格调整记录。

        与其它三种实体分开处理：它们是**按业务键 upsert**（覆盖更新），
        价格调整是**只增不改**（每次变化新增一行，行归档由飞书机器人负责）。
        """
        if not config.price_adjust_table_id:
            return 0

        tasks = (
            await self.db.execute(
                select(FeishuProjectionTask)
                .where(
                    FeishuProjectionTask.entity_type == "price_adjust",
                    (FeishuProjectionTask.status == "pending")
                    | (
                        (FeishuProjectionTask.status == "failed")
                        & (FeishuProjectionTask.next_retry_at <= datetime.now(timezone.utc))
                    ),
                )
                .order_by(FeishuProjectionTask.created_at)
                .limit(PRICE_ADJUST_DELIVERY_LIMIT)
            )
        ).scalars().all()
        if not tasks:
            return 0

        completed = 0
        # 调价记录表可能不在默认 base 里（它通常与三张状态镜像表分属不同多维表格）
        target_base = config.price_adjust_base_token or client.base_token
        # 按飞书单次上限分块，**每块独立成败**。
        # ⚠️ 不能"整批一次调用、失败就把所有任务标 failed"：
        # 第 3 块失败时，第 1、2 块其实已经写进飞书了，
        # 但它们被一起标成 failed → 重试时再写一遍 → 飞书里出现重复行。
        # 调价记录表是**只增不改**的，重复行不会被覆盖，只会一直堆着。
        for offset in range(0, len(tasks), FEISHU_BATCH_CREATE_LIMIT):
            chunk_tasks = tasks[offset:offset + FEISHU_BATCH_CREATE_LIMIT]
            chunk_payloads = [self._price_adjust_payload(task) for task in chunk_tasks]
            try:
                await client.batch_create_records(
                    config.price_adjust_table_id, chunk_payloads, target_base
                )
            except Exception as exc:  # noqa: BLE001
                for task in chunk_tasks:
                    await self.record_attempt(task, "failed", str(exc)[:1000])
                continue

            for task in chunk_tasks:
                try:
                    await self.record_attempt(task, "completed")
                    await self._advance_price_adjust_baseline(task)
                    completed += 1
                except Exception as exc:  # noqa: BLE001
                    await self.record_attempt(task, "failed", str(exc)[:1000])

            # 同一张表不支持并发写（1254291）→ 块与块之间必须留间隔
            if offset + FEISHU_BATCH_CREATE_LIMIT < len(tasks):
                await asyncio.sleep(FEISHU_BATCH_WRITE_INTERVAL_SECONDS)
        return completed



    async def process_pending(self, limit: int = 50, client: FeishuProjectionClient | None = None) -> int:
        config = await self.get_config()
        if config is None:
            return 0
        projection_client = client or FeishuProjectionClient()

        # 调价记录表**独立**投递：只要求它自己的表 id 配好。
        # ⚠️ 不能把镜像表的检查放在它前面——三张状态镜像表和调价记录表分属不同
        # 多维表格、配置上也互不依赖；镜像表 id 没配齐就整体 return 0 的话，
        # 调价记录也会被一起卡住（一行都写不出去，且不报错）。
        completed = await self._process_price_adjust_tasks(config, projection_client)

        # 其余三种实体是「按业务键 upsert」，要求镜像表 id 齐全且配置已就绪
        if config.status != "ready" or not config.spu_table_id or not config.sku_table_id:
            return completed

        tasks = (
            await self.db.execute(
                select(FeishuProjectionTask)
                .where(
                    FeishuProjectionTask.entity_type != "price_adjust",
                    (FeishuProjectionTask.status == "pending")
                    | (
                        (FeishuProjectionTask.status == "failed")
                        & (FeishuProjectionTask.next_retry_at <= datetime.now(timezone.utc))
                    )
                )
                .order_by(FeishuProjectionTask.created_at)
                .limit(limit)
            )
        ).scalars().all()
        for task in tasks:
            try:
                if task.entity_type == "sku":
                    payload = await self._sku_payload(int(task.business_key))
                    await projection_client.upsert_record(config.sku_table_id, "ERP SKU", payload["ERP SKU"], payload)
                elif task.entity_type == "spu":
                    payload = await self._spu_payload(task.business_key)
                    await projection_client.upsert_record(config.spu_table_id, "SPU", payload["SPU"], payload)
                elif task.entity_type == "platform_sku_profit":
                    if not config.platform_sku_profit_table_id:
                        raise RuntimeError("platform_sku_profit_table_id is not configured")
                    payload = await self._platform_sku_profit_payload(int(task.business_key))
                    await projection_client.upsert_record(config.platform_sku_profit_table_id, "经营范围键", payload["经营范围键"], payload)
                else:
                    await self.record_attempt(task, "completed")
                    continue
                await self.record_attempt(task, "completed")
                completed += 1
            except Exception as exc:
                await self.record_attempt(task, "failed", str(exc)[:1000])
        return completed

    async def record_attempt(
        self,
        task: FeishuProjectionTask,
        status: str,
        error_message: str | None = None,
    ) -> None:
        task.status = status
        task.attempt_count += 1
        task.last_error = error_message
        if status == "failed":
            task.next_retry_at = datetime.now(timezone.utc) + timedelta(
                seconds=min(3600, 30 * (2 ** min(task.attempt_count - 1, 6)))
            )
        else:
            task.next_retry_at = None
        if status == "completed":
            task.completed_at = datetime.now(timezone.utc)
        self.db.add(
            FeishuProjectionLog(
                task_id=task.id,
                status=status,
                payload_hash=task.payload_hash,
                error_message=error_message,
            )
        )


async def trigger_pending_projection_delivery() -> None:
    """Best-effort async dispatch; durable outbox keeps failed work retryable."""
    from backend.models.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            await FeishuProjectionService(db).process_pending()
            await db.commit()
        except Exception:
            await db.rollback()


def _number(name: str, precision: int = 2, percentage: bool = False) -> dict[str, Any]:
    return {"name": name, "type": "number", "style": {"type": "plain", "precision": precision, "percentage": percentage}}


def _spu_table_fields() -> list[dict[str, Any]]:
    return [
        {"name": "SPU", "type": "text"}, {"name": "商品名称", "type": "text"},
        {"name": "一级品类", "type": "text"}, {"name": "二级品类", "type": "text"},
        {"name": "经营状态", "type": "text"}, {"name": "负责人", "type": "text"},
        _number("SKU数", 0), _number("库存数量", 0), _number("库存金额 RMB"),
        _number("基准预计利润 RMB"), _number("基准预计利润率", 4, True),
        {"name": "数据完整度", "type": "text"}, {"name": "计算时间", "type": "datetime", "style": {"format": "yyyy-MM-dd HH:mm"}},
    ]


def _sku_table_fields() -> list[dict[str, Any]]:
    return [
        {"name": "ERP SKU", "type": "text"}, {"name": "SPU", "type": "text"},
        {"name": "商品名称", "type": "text"}, {"name": "规格", "type": "text"},
        _number("重量 kg", 3), _number("长 cm"), _number("宽 cm"), _number("高 cm"), _number("体积 m³", 4), _number("箱规", 0),
        _number("默认采购成本 RMB"), _number("预计物流成本 RMB", 4), _number("预计仓储成本 RMB", 4), _number("实际物流成本 RMB", 4),
        _number("头程单位成本 RMB", 4), _number("操作费单位成本 RMB", 4), _number("尾程单位成本 RMB", 4),
        _number("基准预计利润 RMB"), _number("基准预计利润率", 4, True),
        _number("物流货损率", 4, True), _number("退货损失率", 4, True),
        {"name": "采购成本来源", "type": "text"}, {"name": "物流成本来源", "type": "text"}, {"name": "数据完整度", "type": "text"},
        {"name": "更新时间", "type": "datetime", "style": {"format": "yyyy-MM-dd HH:mm"}},
    ]


def _platform_sku_profit_table_fields() -> list[dict[str, Any]]:
    return [
        {"name": "经营范围键", "type": "text"}, {"name": "平台", "type": "text"}, {"name": "收货仓库", "type": "text"}, {"name": "ERP SKU", "type": "text"}, {"name": "SPU", "type": "text"}, {"name": "商品名称", "type": "text"},
        _number("参考售价"), _number("竞品价格"), _number("预计售价"), _number("优惠券"), _number("采购成本"), _number("预计物流成本", 4), _number("预计仓储成本", 4), _number("实际物流成本", 4), _number("实际仓储成本", 4), _number("平台费率", 4, True), _number("预计广告费率", 4, True), _number("预计广告费用"), _number("预计贡献利润"), _number("预计利润率", 4, True), _number("实际成本重估利润"), _number("实际成本重估利润率", 4, True), _number("成本偏差"), {"name": "计算口径", "type": "text"},
        _number("货损率", 4, True), _number("退货损失率", 4, True), {"name": "成本来源", "type": "text"}, {"name": "数据完整度", "type": "text"}, {"name": "置信度", "type": "text"}, {"name": "版本", "type": "text"}, {"name": "估算时间", "type": "datetime", "style": {"format": "yyyy-MM-dd HH:mm"}}, {"name": "更新时间", "type": "datetime", "style": {"format": "yyyy-MM-dd HH:mm"}},
    ]
