from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.target import OperationWorkbenchApplyRequest
from backend.services.payroll_period_lock_service import PayrollPeriodLockService
from modules.core.db import (
    OperationMetricCatalog,
    PerformanceConfig,
    SalesTarget,
    TargetBreakdown,
)


class OperationMetricCalculator:
    """Calculates one operation metric without silently turning missing data into zero."""

    @staticmethod
    def calculate(metric: Any) -> tuple[float | None, dict[str, Any]]:
        direction = getattr(metric, "metric_direction", None)
        target = getattr(metric, "target_value", None)
        achieved = getattr(metric, "achieved_value", None)
        max_score = float(getattr(metric, "max_score", 0.0) or 0.0)
        manual_enabled = bool(getattr(metric, "manual_score_enabled", False))
        manual_score = getattr(metric, "manual_score_value", None)

        detail: dict[str, Any] = {
            "metric_code": getattr(metric, "metric_code", None),
            "metric_name": getattr(metric, "metric_name", None),
            "direction": direction,
            "target": target,
            "achieved": achieved,
            "max_score": max_score,
            "penalty": 0.0,
        }
        if direction == "manual_score" or manual_enabled:
            if manual_score is None:
                return None, {**detail, "status": "pending", "message": "等待人工评分"}
            score = max(0.0, min(float(manual_score), max_score))
            return score, {**detail, "status": "calculated", "score": score}

        if direction not in {"higher_better", "lower_better"}:
            return None, {**detail, "status": "pending", "message": "指标方向未配置"}
        if target is None or achieved is None:
            return None, {**detail, "status": "pending", "message": "等待录入实际值"}

        target_number = float(target)
        achieved_number = float(achieved)
        if direction == "higher_better":
            if target_number <= 0:
                return None, {
                    **detail,
                    "status": "pending",
                    "message": "正向指标目标必须大于零",
                }
            ratio = min(max(achieved_number / target_number, 0.0), 1.0)
        elif target_number == 0:
            ratio = 1.0 if achieved_number == 0 else 0.0
        elif achieved_number <= target_number:
            ratio = 1.0
        else:
            ratio = min(max(target_number / achieved_number, 0.0), 1.0)

        base_score = max_score * ratio
        penalty = 0.0
        if bool(getattr(metric, "penalty_enabled", False)):
            threshold = getattr(metric, "penalty_threshold", None)
            per_unit = float(getattr(metric, "penalty_per_unit", 0.0) or 0.0)
            penalty_max = float(getattr(metric, "penalty_max", 0.0) or 0.0)
            if threshold is not None and achieved_number > float(threshold):
                penalty = min(
                    (achieved_number - float(threshold)) * per_unit, penalty_max
                )
        score = max(0.0, base_score - penalty)
        return round(score, 4), {
            **detail,
            "status": "calculated",
            "rate": round(ratio * 100, 4),
            "penalty": round(penalty, 4),
            "score": round(score, 4),
        }


class OperationPerformanceWorkbenchConflictError(ValueError):
    """Raised when a user saves a stale workbench version."""


class OperationPerformanceWorkbenchService:
    """Shared scoring operations used by the workbench and performance settlement."""

    @staticmethod
    def aggregate_metrics(
        metrics: list[Any],
        *,
        expected_max_score: float,
    ) -> tuple[float | None, dict[str, Any]]:
        enabled = [
            metric for metric in metrics if bool(getattr(metric, "is_enabled", True))
        ]
        total_max_score = sum(
            float(getattr(metric, "max_score", 0.0) or 0.0) for metric in enabled
        )
        if round(total_max_score, 4) != round(float(expected_max_score), 4):
            raise ValueError("运营指标满分之和必须等于绩效配置的运营满分")

        items: list[dict[str, Any]] = []
        total_score = 0.0
        pending = False
        for metric in enabled:
            score, detail = OperationMetricCalculator.calculate(metric)
            items.append(detail)
            if score is None:
                pending = True
            else:
                total_score += score

        if pending:
            return None, {
                "status": "pending",
                "items": items,
                "max_score": float(expected_max_score),
                "score": None,
            }
        return round(max(total_score, 0.0), 4), {
            "status": "calculated",
            "items": items,
            "max_score": float(expected_max_score),
            "score": round(max(total_score, 0.0), 4),
        }

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def month_range(year_month: str) -> tuple[date, date]:
        start = datetime.strptime(year_month, "%Y-%m").date().replace(day=1)
        return start, start.replace(day=monthrange(start.year, start.month)[1])

    async def _catalog(
        self, catalog_version: int | None = None, *, active_only: bool = True
    ):
        query = select(OperationMetricCatalog)
        if catalog_version is not None:
            query = query.where(
                OperationMetricCatalog.catalog_version == catalog_version
            )
        else:
            latest = await self.db.execute(
                select(OperationMetricCatalog.catalog_version)
                .order_by(OperationMetricCatalog.catalog_version.desc())
                .limit(1)
            )
            catalog_version = latest.scalar_one_or_none()
            if catalog_version is None:
                return []
            query = query.where(
                OperationMetricCatalog.catalog_version == catalog_version
            )
        if active_only:
            query = query.where(OperationMetricCatalog.is_active.is_(True))
        return (
            (await self.db.execute(query.order_by(OperationMetricCatalog.id)))
            .scalars()
            .all()
        )

    async def _config(self, year_month: str, config_id: int | None = None):
        month_start, month_end = self.month_range(year_month)
        query = select(PerformanceConfig)
        if config_id is not None:
            query = query.where(PerformanceConfig.id == config_id)
        else:
            query = query.where(
                PerformanceConfig.is_active.is_(True),
                PerformanceConfig.effective_from <= month_end,
                (
                    PerformanceConfig.effective_to.is_(None)
                    | (PerformanceConfig.effective_to >= month_start)
                ),
            ).order_by(
                PerformanceConfig.effective_from.desc(), PerformanceConfig.id.desc()
            )
        return (await self.db.execute(query.limit(1))).scalar_one_or_none()

    async def _targets(self, year_month: str):
        month_start, month_end = self.month_range(year_month)
        return (
            (
                await self.db.execute(
                    select(SalesTarget)
                    .where(
                        SalesTarget.target_type == "operation",
                        SalesTarget.period_start == month_start,
                        SalesTarget.period_end == month_end,
                        SalesTarget.metric_catalog_version.is_not(None),
                        SalesTarget.scope_type.in_(("shop", None)),
                        SalesTarget.status != "cancelled",
                    )
                    .order_by(SalesTarget.metric_code, SalesTarget.id)
                )
            )
            .scalars()
            .all()
        )

    async def get_workbench(self, year_month: str) -> dict[str, Any]:
        month_start, month_end = self.month_range(year_month)
        config = await self._config(year_month)
        catalog = await self._catalog()
        targets = await self._targets(year_month)
        by_code = {str(row.metric_code): row for row in targets if row.metric_code}
        code_by_id = {
            row.id: str(row.metric_code) for row in targets if row.metric_code
        }
        target_ids = [row.id for row in targets]
        overrides = []
        if target_ids:
            overrides = (
                (
                    await self.db.execute(
                        select(TargetBreakdown)
                        .join(SalesTarget, SalesTarget.id == TargetBreakdown.target_id)
                        .where(
                            TargetBreakdown.target_id.in_(target_ids),
                            TargetBreakdown.breakdown_type == "shop",
                            SalesTarget.metric_catalog_version.is_not(None),
                            TargetBreakdown.operation_contract_version
                            == SalesTarget.metric_catalog_version,
                        )
                        .order_by(
                            TargetBreakdown.target_id,
                            TargetBreakdown.platform_code,
                            TargetBreakdown.shop_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
        rows = []
        for item in catalog:
            target = by_code.get(item.metric_code)
            rows.append(
                {
                    "metric_code": item.metric_code,
                    "metric_name": item.metric_name,
                    "metric_direction": item.metric_direction,
                    "catalog_version": item.catalog_version,
                    "is_enabled": (
                        bool(getattr(target, "is_enabled", True)) if target else False
                    ),
                    "target_id": getattr(target, "id", None),
                    "target_value": (
                        getattr(target, "target_value", None)
                        if target
                        else item.default_target_value
                    ),
                    "achieved_value": (
                        getattr(target, "achieved_value", None) if target else None
                    ),
                    "max_score": (
                        float(
                            getattr(target, "max_score", item.default_max_score) or 0.0
                        )
                        if target
                        else float(item.default_max_score or 0.0)
                    ),
                    "penalty_enabled": (
                        bool(
                            getattr(
                                target, "penalty_enabled", item.default_penalty_enabled
                            )
                        )
                        if target
                        else bool(item.default_penalty_enabled)
                    ),
                    "penalty_threshold": (
                        getattr(target, "penalty_threshold", None)
                        if target
                        else item.default_penalty_threshold
                    ),
                    "penalty_per_unit": (
                        getattr(target, "penalty_per_unit", None)
                        if target
                        else item.default_penalty_per_unit
                    ),
                    "penalty_max": (
                        getattr(target, "penalty_max", None)
                        if target
                        else item.default_penalty_max
                    ),
                    "manual_score_enabled": bool(
                        item.manual_score_enabled
                        or item.metric_direction == "manual_score"
                    ),
                    "manual_score_value": (
                        getattr(target, "manual_score_value", None) if target else None
                    ),
                }
            )
        return {
            "year_month": year_month,
            "period_start": month_start,
            "period_end": month_end,
            "catalog_version": catalog[0].catalog_version if catalog else None,
            "performance_config_id": getattr(config, "id", None),
            "performance_config_updated_at": getattr(config, "updated_at", None),
            "operation_max_score": float(
                getattr(config, "operation_max_score", 20) if config else 20
            ),
            "updated_at": max(
                (getattr(row, "updated_at", None) for row in targets), default=None
            ),
            "metrics": rows,
            "shop_overrides": [
                {
                    "target_id": row.target_id,
                    "metric_code": code_by_id.get(row.target_id),
                    "platform_code": row.platform_code,
                    "shop_id": row.shop_id,
                    "target_value": row.target_value,
                    "achieved_value": row.achieved_value,
                    "manual_score_value": row.manual_score_value,
                }
                for row in overrides
            ],
        }

    async def apply(
        self, request: OperationWorkbenchApplyRequest, username: str | None = None
    ) -> dict[str, Any]:
        month_start, month_end = self.month_range(request.year_month)
        await PayrollPeriodLockService(self.db).assert_month_mutable(
            year_month=request.year_month
        )
        catalog = await self._catalog(request.catalog_version)
        catalog_by_code = {item.metric_code: item for item in catalog}
        config = await self._config(request.year_month)
        if config is None:
            raise ValueError("考核周期内无可用绩效配置")
        if (
            request.performance_config_id is not None
            and request.performance_config_id != config.id
        ):
            raise OperationPerformanceWorkbenchConflictError(
                "绩效配置已变更，请刷新后重试"
            )
        expected_config_updated_at = request.expected_performance_config_updated_at
        current_config_updated_at = getattr(config, "updated_at", None)
        if (
            expected_config_updated_at is not None
            and current_config_updated_at is not None
            and abs(
                (current_config_updated_at - expected_config_updated_at).total_seconds()
            )
            > 0.001
        ):
            raise OperationPerformanceWorkbenchConflictError(
                "绩效配置已变更，请刷新后重试"
            )
        unknown_codes = [
            item.metric_code
            for item in request.metrics
            if item.metric_code not in catalog_by_code
        ]
        if unknown_codes:
            raise ValueError(f"运营指标不在目录中: {', '.join(unknown_codes)}")
        invalid_overrides = [
            item.metric_code
            for item in request.shop_overrides
            if item.metric_code
            not in {metric.metric_code for metric in request.metrics}
            or not item.platform_code.strip()
            or not item.shop_id.strip()
        ]
        if invalid_overrides:
            raise ValueError("店铺覆盖必须对应工作台指标且包含平台和店铺 ID")
        active_metrics = [item for item in request.metrics if item.is_enabled]
        score_sum = sum(float(item.max_score or 0) for item in active_metrics)
        if round(score_sum, 4) != round(float(config.operation_max_score), 4):
            raise ValueError("运营指标满分之和必须等于绩效配置的运营满分")

        existing = await self._targets(request.year_month)
        existing_by_code = {row.metric_code: row for row in existing if row.metric_code}
        if request.expected_updated_at is not None:
            current = max(
                (getattr(row, "updated_at", None) for row in existing), default=None
            )
            if (
                current is not None
                and abs((current - request.expected_updated_at).total_seconds()) > 0.001
            ):
                raise OperationPerformanceWorkbenchConflictError(
                    "运营绩效配置已被其他用户更新，请刷新后重试"
                )

        rows_by_code: dict[str, SalesTarget] = {}
        for item in request.metrics:
            catalog_item = catalog_by_code[item.metric_code]
            row = existing_by_code.get(item.metric_code)
            if row is None:
                row = SalesTarget(
                    target_name=catalog_item.metric_name,
                    target_type="operation",
                    scope_type="shop",
                    period_start=month_start,
                    period_end=month_end,
                    metric_code=item.metric_code,
                    created_by=username,
                )
                self.db.add(row)
            row.target_name = catalog_item.metric_name
            row.target_type = "operation"
            row.scope_type = "shop"
            row.period_start = month_start
            row.period_end = month_end
            row.metric_code = item.metric_code
            row.metric_name = catalog_item.metric_name
            row.metric_direction = catalog_item.metric_direction
            row.target_value = item.target_value
            row.achieved_value = item.achieved_value
            row.max_score = item.max_score
            row.penalty_enabled = item.penalty_enabled
            row.penalty_threshold = item.penalty_threshold
            row.penalty_per_unit = item.penalty_per_unit
            row.penalty_max = item.penalty_max
            row.manual_score_enabled = bool(
                catalog_item.manual_score_enabled
                or catalog_item.metric_direction == "manual_score"
            )
            row.manual_score_value = item.manual_score_value
            row.is_enabled = item.is_enabled
            row.metric_catalog_version = request.catalog_version
            row.performance_config_id = config.id
            row.performance_config_updated_at = getattr(config, "updated_at", None)
            row.status = "active"
            row.updated_at = datetime.now(timezone.utc)
            rows_by_code[item.metric_code] = row

        for row in existing:
            if row.metric_code not in rows_by_code:
                row.is_enabled = False
                row.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        target_ids = [row.id for row in rows_by_code.values()]
        if target_ids:
            current_contract_breakdown_ids = (
                select(TargetBreakdown.id)
                .join(SalesTarget, SalesTarget.id == TargetBreakdown.target_id)
                .where(
                    TargetBreakdown.target_id.in_(target_ids),
                    TargetBreakdown.breakdown_type == "shop",
                    SalesTarget.metric_catalog_version.is_not(None),
                    TargetBreakdown.operation_contract_version
                    == SalesTarget.metric_catalog_version,
                )
            )
            await self.db.execute(
                delete(TargetBreakdown).where(
                    TargetBreakdown.id.in_(current_contract_breakdown_ids)
                )
            )
        for override in request.shop_overrides:
            target = rows_by_code.get(override.metric_code)
            if target is None:
                raise ValueError(f"店铺覆盖指标不存在: {override.metric_code}")
            self.db.add(
                TargetBreakdown(
                    target_id=target.id,
                    breakdown_type="shop",
                    platform_code=override.platform_code.lower(),
                    shop_id=override.shop_id,
                    period_start=month_start,
                    period_end=month_end,
                    target_value=override.target_value,
                    achieved_value=override.achieved_value,
                    manual_score_value=override.manual_score_value,
                    operation_contract_version=target.metric_catalog_version,
                )
            )
        await self.db.commit()
        return await self.get_workbench(request.year_month)

    async def copy_prev_month(
        self, year_month: str, username: str | None = None
    ) -> dict[str, Any]:
        await PayrollPeriodLockService(self.db).assert_month_mutable(
            year_month=year_month
        )
        month_start, _ = self.month_range(year_month)
        previous_month = (
            f"{month_start.year - 1:04d}-12"
            if month_start.month == 1
            else f"{month_start.year:04d}-{month_start.month - 1:02d}"
        )
        current = await self._targets(year_month)
        if current:
            raise ValueError("目标月份已有运营配置，请清空后再复制")
        previous = await self._targets(previous_month)
        if not previous:
            raise ValueError("上月没有可复制的运营配置")
        active_catalog = {item.metric_code: item for item in await self._catalog()}
        if not active_catalog:
            raise ValueError("当前没有可用的运营指标目录")
        metrics = []
        skipped = []
        for row in previous:
            if row.metric_code not in active_catalog:
                skipped.append({"metric_code": row.metric_code, "reason": "指标已退役"})
                continue
            metrics.append(
                {
                    "metric_code": row.metric_code,
                    "is_enabled": bool(row.is_enabled),
                    "target_value": row.target_value,
                    "achieved_value": None,
                    "max_score": row.max_score,
                    "penalty_enabled": row.penalty_enabled,
                    "penalty_threshold": row.penalty_threshold,
                    "penalty_per_unit": row.penalty_per_unit,
                    "penalty_max": row.penalty_max,
                    "manual_score_value": None,
                }
            )
        previous_ids = [row.id for row in previous]
        overrides = []
        if previous_ids:
            rows = (
                (
                    await self.db.execute(
                        select(TargetBreakdown)
                        .join(SalesTarget, SalesTarget.id == TargetBreakdown.target_id)
                        .where(
                            TargetBreakdown.target_id.in_(previous_ids),
                            TargetBreakdown.breakdown_type == "shop",
                            SalesTarget.metric_catalog_version.is_not(None),
                            TargetBreakdown.operation_contract_version
                            == SalesTarget.metric_catalog_version,
                        )
                    )
                )
                .scalars()
                .all()
            )
            code_by_id = {row.id: row.metric_code for row in previous}
            overrides = [
                {
                    "metric_code": code_by_id[row.target_id],
                    "platform_code": row.platform_code,
                    "shop_id": row.shop_id,
                    "target_value": row.target_value,
                    "achieved_value": None,
                    "manual_score_value": None,
                }
                for row in rows
                if code_by_id[row.target_id] in active_catalog
            ]
        result = await self.apply(
            OperationWorkbenchApplyRequest(
                year_month=year_month,
                catalog_version=max(
                    active_catalog.values(), key=lambda item: item.catalog_version
                ).catalog_version,
                metrics=metrics,
                shop_overrides=overrides,
            ),
            username=username,
        )
        result["skipped"] = skipped
        return result
