from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.target import OperationWorkbenchApplyRequest
from backend.services.payroll_period_lock_service import PayrollPeriodLockService
from backend.services.operation_performance_shop_scope_service import (
    OperationPerformanceShopScopeService,
)
from backend.services.operation_performance_scoring_service import (
    OperationPerformanceScoringService,
)
from modules.core.db import (
    OperationMetricCatalog,
    OperationPerformanceShopScope,
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

    async def _targets(self, year_month: str, *, auto_integer_only: bool = False):
        month_start, month_end = self.month_range(year_month)
        conditions = [
            SalesTarget.target_type == "operation",
            SalesTarget.period_start == month_start,
            SalesTarget.period_end == month_end,
            SalesTarget.metric_catalog_version.is_not(None),
            SalesTarget.scope_type.in_(("shop", None)),
            SalesTarget.status != "cancelled",
        ]
        if auto_integer_only:
            conditions.extend(
                [
                    SalesTarget.scoring_model_version == "auto_integer_v1",
                ]
            )
        return (
            (
                await self.db.execute(
                    select(SalesTarget)
                    .where(*conditions)
                    .order_by(SalesTarget.metric_code, SalesTarget.id)
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    def _shop_key(platform_code: str, shop_id: str) -> tuple[str, str]:
        return str(platform_code).strip().lower(), str(shop_id).strip()

    @staticmethod
    def _auto_integer_rule(target: SalesTarget) -> dict[str, Any]:
        if getattr(target, "scoring_model_version", None) != "auto_integer_v1":
            raise ValueError("运营指标不是 auto_integer_v1 受控规则")
        snapshot = getattr(target, "operation_rule_snapshot", None)
        if not isinstance(snapshot, dict):
            raise ValueError("运营指标缺少受控规则快照")
        input_kind = str(snapshot.get("input_kind") or "")
        if input_kind not in {"percentage", "count", "training_counts", "special_check"}:
            raise ValueError("运营指标规则快照的录入类型无效")
        return {
            **snapshot,
            "metric_code": target.metric_code,
            "metric_name": getattr(target, "metric_name", None),
            "metric_direction": target.metric_direction,
            "target_value": target.target_value,
            "max_score": target.max_score,
        }

    async def _active_shops(self):
        candidates, _ = await OperationPerformanceShopScopeService(
            self.db
        ).load_candidates()
        return candidates

    async def _unresolved_scope_shops(self):
        _, unresolved = await OperationPerformanceShopScopeService(
            self.db
        ).load_candidates()
        return unresolved

    async def _sales_target_shop_keys(self, year_month: str) -> set[tuple[str, str]]:
        month_start, month_end = self.month_range(year_month)
        rows = await self.db.execute(
            select(TargetBreakdown.platform_code, TargetBreakdown.shop_id)
            .join(SalesTarget, SalesTarget.id == TargetBreakdown.target_id)
            .where(
                SalesTarget.target_type == "shop",
                SalesTarget.period_start == month_start,
                SalesTarget.period_end == month_end,
                SalesTarget.status != "cancelled",
                TargetBreakdown.breakdown_type == "shop",
                TargetBreakdown.platform_code.is_not(None),
                TargetBreakdown.shop_id.is_not(None),
            )
        )
        return {
            self._shop_key(platform_code, shop_id)
            for platform_code, shop_id in rows.all()
        }

    async def _scope_rows(self, year_month: str):
        return (
            (
                await self.db.execute(
                    select(OperationPerformanceShopScope)
                    .where(OperationPerformanceShopScope.year_month == year_month)
                    .order_by(
                        OperationPerformanceShopScope.platform_code,
                        OperationPerformanceShopScope.shop_id,
                    )
                )
            )
            .scalars()
            .all()
        )

    async def get_scope(self, year_month: str) -> dict[str, Any]:
        active_shops = await self._active_shops()
        stored_rows = await self._scope_rows(year_month)
        if stored_rows and all(
            getattr(row, "snapshot_version", None) == 1 for row in stored_rows
        ):
            shops = [
                {
                    "platform_code": row.platform_code,
                    "shop_id": row.shop_id,
                    "standard_name": row.standard_name_snapshot or row.shop_id,
                    "aliases": row.alias_snapshots or [],
                    "is_included": bool(row.is_included),
                    "exclusion_reason": row.exclusion_reason,
                }
                for row in stored_rows
            ]
            return {
                "year_month": year_month,
                "is_confirmed": True,
                "shops": shops,
                "unresolved_shops": [],
                "included_count": sum(1 for item in shops if item["is_included"]),
            }
        stored_by_key = {
            self._shop_key(row.platform_code, row.shop_id): row for row in stored_rows
        }
        shops = []
        for shop in active_shops:
            key = self._shop_key(shop["platform_code"], shop["shop_id"])
            stored = stored_by_key.get(key)
            shops.append(
                {
                    "platform_code": key[0],
                    "shop_id": key[1],
                    "standard_name": shop["standard_name"],
                    "aliases": shop["aliases"],
                    "is_included": bool(getattr(stored, "is_included", True)),
                    "exclusion_reason": getattr(stored, "exclusion_reason", None),
                }
            )
        return {
            "year_month": year_month,
            "is_confirmed": False,
            "requires_reconfirmation": bool(stored_rows),
            "shops": shops,
            "unresolved_shops": await self._unresolved_scope_shops(),
            "included_count": sum(1 for item in shops if item["is_included"]),
        }

    async def apply_scope(self, request: Any, username: str | None = None):
        await PayrollPeriodLockService(self.db).assert_month_mutable(
            year_month=request.year_month
        )
        active_shops = await self._active_shops()
        unresolved_shops = await self._unresolved_scope_shops()
        if unresolved_shops:
            raise ValueError("存在待身份对齐的经营店铺，不能确认范围")
        active_by_key = {
            self._shop_key(shop["platform_code"], shop["shop_id"]): shop
            for shop in active_shops
        }
        requested_by_key = {
            self._shop_key(item.platform_code, item.shop_id): item
            for item in request.shops
        }
        unknown_keys = sorted(set(requested_by_key) - set(active_by_key))
        if unknown_keys:
            raise ValueError("店铺必须来自当前启用店铺主数据")

        requested_scope = {
            key: requested_by_key.get(key) for key in active_by_key
        }
        included_keys = {
            key
            for key, item in requested_scope.items()
            if item is None or item.is_included
        }
        target_keys = await self._sales_target_shop_keys(request.year_month)
        missing_target_keys = sorted(included_keys - target_keys)
        if missing_target_keys:
            rendered = ", ".join(f"{platform}/{shop}" for platform, shop in missing_target_keys)
            raise ValueError(f"参与运营绩效的店铺缺少当月销售目标: {rendered}")

        existing_by_key = {
            self._shop_key(row.platform_code, row.shop_id): row
            for row in await self._scope_rows(request.year_month)
        }
        if any(getattr(row, "snapshot_version", None) == 1 for row in existing_by_key.values()):
            raise ValueError("本月店铺范围已确认，请先撤销范围")
        if existing_by_key:
            await self.db.execute(
                delete(OperationPerformanceShopScope).where(
                    OperationPerformanceShopScope.year_month == request.year_month
                )
            )
        for key in active_by_key:
            request_item = requested_scope[key]
            is_included = True if request_item is None else request_item.is_included
            reason = (
                None
                if is_included
                else (str(request_item.exclusion_reason or "").strip() or None)
            )
            shop = active_by_key[key]
            self.db.add(
                OperationPerformanceShopScope(
                    year_month=request.year_month,
                    platform_code=key[0],
                    shop_id=key[1],
                    is_included=is_included,
                    exclusion_reason=reason,
                    source_shop_account_id=shop["source_shop_account_id"],
                    standard_name_snapshot=shop["standard_name"],
                    alias_snapshots=shop["aliases"],
                    snapshot_version=1,
                    confirmed_at=datetime.now(timezone.utc),
                    confirmed_by=username,
                    created_by=username,
                    updated_by=username,
                    updated_at=datetime.now(timezone.utc),
                )
            )
        await self.db.commit()
        return await self.get_scope(request.year_month)

    async def revoke_scope(self, year_month: str):
        await PayrollPeriodLockService(self.db).assert_month_mutable(year_month=year_month)
        target_ids = [target.id for target in await self._targets(year_month) if target.id]
        if target_ids:
            await self.db.execute(
                delete(TargetBreakdown).where(TargetBreakdown.target_id.in_(target_ids))
            )
        await self.db.execute(
            delete(OperationPerformanceShopScope).where(
                OperationPerformanceShopScope.year_month == year_month
            )
        )
        await self.db.commit()
        return await self.get_scope(year_month)

    @staticmethod
    def _is_manual_metric(metric: Any) -> bool:
        return bool(
            getattr(metric, "manual_score_enabled", False)
            or getattr(metric, "metric_direction", None) == "manual_score"
        )

    async def _entry_breakdowns(self, targets: list[SalesTarget]):
        target_ids = [target.id for target in targets if getattr(target, "id", None)]
        if not target_ids:
            return {}
        rows = (
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
                )
            )
            .scalars()
            .all()
        )
        return {
            (row.target_id, *self._shop_key(row.platform_code, row.shop_id)): row
            for row in rows
        }

    async def get_entries(self, year_month: str) -> dict[str, Any]:
        scope_rows = await self._scope_rows(year_month)
        included_rows = [row for row in scope_rows if row.is_included]
        if not scope_rows:
            return {
                "year_month": year_month,
                "scope_confirmed": False,
                "shops": [],
                "completion": {"completed": 0, "pending": 0},
            }
        if not all(getattr(row, "snapshot_version", None) == 1 for row in scope_rows):
            return {
                "year_month": year_month,
                "scope_confirmed": False,
                "shops": [],
                "completion": {"completed": 0, "pending": 0},
            }

        targets_with_rules = []
        configuration_errors = []
        for target in await self._targets(year_month, auto_integer_only=True):
            if not target.is_enabled:
                continue
            if getattr(target, "scoring_model_version", None) != "auto_integer_v1":
                continue
            try:
                targets_with_rules.append((target, self._auto_integer_rule(target)))
            except ValueError as exc:
                configuration_errors.append(
                    {
                        "metric_code": getattr(target, "metric_code", None),
                        "message": str(exc),
                    }
                )
                continue
        breakdowns = await self._entry_breakdowns(
            [target for target, _ in targets_with_rules]
        )
        shops = []
        completed = 0
        pending = 0
        for scope in included_rows:
            key = self._shop_key(scope.platform_code, scope.shop_id)
            metrics = []
            shop_complete = not configuration_errors
            for target, rule in targets_with_rules:
                breakdown = breakdowns.get((target.id, *key))
                input_kind = str(rule["input_kind"])
                payload = dict(
                    getattr(breakdown, "operation_input_payload", None) or {}
                )
                auto_score, scoring_detail = (
                    OperationPerformanceScoringService.calculate_metric_score(
                        metric=rule,
                        payload=payload or None,
                    )
                )
                metric_complete = auto_score is not None
                shop_complete = shop_complete and metric_complete
                metrics.append(
                    {
                        "metric_code": target.metric_code,
                        "metric_name": target.metric_name,
                        "metric_direction": target.metric_direction,
                        "target_value": target.target_value,
                        "max_score": float(target.max_score or 0.0),
                        "input_kind": input_kind,
                        "input_payload": payload,
                        "auto_score": auto_score,
                        "scoring_detail": scoring_detail,
                        "unit": rule.get("unit"),
                        "guidance": rule.get("guidance"),
                        "formula": self._operation_metric_formula(rule),
                        "status": "completed" if metric_complete else "pending",
                    }
                )
            completed += int(shop_complete)
            pending += int(not shop_complete)
            shops.append(
                {
                    "platform_code": key[0],
                    "shop_id": key[1],
                    "standard_name": getattr(scope, "standard_name_snapshot", None)
                    or key[1],
                    "aliases": getattr(scope, "alias_snapshots", None) or [],
                    "status": "completed" if shop_complete else "pending",
                    "configuration_errors": configuration_errors,
                    "metrics": metrics,
                }
            )
        return {
            "year_month": year_month,
            "scope_confirmed": True,
            "shops": shops,
            "completion": {"completed": completed, "pending": pending},
            "configuration_errors": configuration_errors,
        }

    @staticmethod
    def _operation_metric_formula(rule: dict[str, Any]) -> str:
        input_kind = str(rule.get("input_kind") or "numeric")
        max_score = int(float(rule.get("max_score") or 0))
        if input_kind == "training_counts":
            return f"得分 = 四舍五入({max_score} × 已完成人数 / 应完成人数)；应完成人数为 0 时按 100% 计。"
        if input_kind == "special_check":
            return f"通过得 {max_score} 分，部分完成得四舍五入({max_score} × 50%) 分，未通过得 0 分。"
        direction = str(rule.get("metric_direction") or "higher_better")
        target = rule.get("target_value")
        if direction == "lower_better":
            return f"实际值不高于目标 {target} 时得 {max_score} 分；超过目标时按目标值 / 实际值比例四舍五入。"
        return f"得分 = 四舍五入({max_score} × min(实际值 / 目标值 {target}, 100%))。"

    async def apply_entries(self, request: Any, username: str | None = None):
        await PayrollPeriodLockService(self.db).assert_month_mutable(
            year_month=request.year_month
        )
        scope_rows = await self._scope_rows(request.year_month)
        if not scope_rows:
            raise ValueError("请先确认本月运营绩效店铺范围")
        if not all(getattr(row, "snapshot_version", None) == 1 for row in scope_rows):
            raise ValueError("店铺范围尚未按当前规则确认，请先撤销并重新确认范围")
        included_keys = {
            self._shop_key(row.platform_code, row.shop_id)
            for row in scope_rows
            if row.is_included
        }
        for entry in request.entries:
            if self._shop_key(entry.platform_code, entry.shop_id) not in included_keys:
                raise ValueError("该店铺未参与本月运营绩效，不能录入")
        targets_by_code = {}
        rules_by_code = {}
        configuration_errors = []
        for target in await self._targets(
            request.year_month, auto_integer_only=True
        ):
            if not target.is_enabled:
                continue
            if getattr(target, "scoring_model_version", None) != "auto_integer_v1":
                continue
            try:
                rule = self._auto_integer_rule(target)
            except ValueError as exc:
                configuration_errors.append(str(exc))
                continue
            targets_by_code[target.metric_code] = target
            rules_by_code[target.metric_code] = rule
        if configuration_errors:
            raise ValueError(
                f"运营绩效规则配置错误，不能录入: {'; '.join(configuration_errors)}"
            )
        breakdowns = await self._entry_breakdowns(list(targets_by_code.values()))
        month_start, month_end = self.month_range(request.year_month)
        for entry in request.entries:
            key = self._shop_key(entry.platform_code, entry.shop_id)
            target = targets_by_code.get(entry.metric_code)
            if target is None:
                raise ValueError("店铺录入指标不存在或未启用")
            rule = rules_by_code[entry.metric_code]
            input_kind = str(rule["input_kind"])
            if input_kind == "training_counts":
                if (
                    entry.actual_value is not None
                    or entry.result is not None
                    or entry.note is not None
                ):
                    raise ValueError("录入字段与培训完成率指标类型不匹配")
                payload = {
                    "completed_count": entry.completed_count,
                    "required_count": entry.required_count,
                }
            elif input_kind == "special_check":
                if (
                    entry.actual_value is not None
                    or entry.completed_count is not None
                    or entry.required_count is not None
                ):
                    raise ValueError("录入字段与专项检查指标类型不匹配")
                payload = {"result": entry.result, "note": entry.note}
            elif input_kind in {"percentage", "count"}:
                if (
                    entry.completed_count is not None
                    or entry.required_count is not None
                    or entry.result is not None
                    or entry.note is not None
                ):
                    raise ValueError("录入字段与数值指标类型不匹配")
                payload = {"actual_value": entry.actual_value}
            else:
                raise ValueError("运营指标录入类型无效")
            OperationPerformanceScoringService.calculate_metric_score(
                metric=rule, payload=payload
            )

            breakdown = breakdowns.get((target.id, *key))
            if breakdown is None:
                breakdown = TargetBreakdown(
                    target_id=target.id,
                    breakdown_type="shop",
                    platform_code=key[0],
                    shop_id=key[1],
                    period_start=month_start,
                    period_end=month_end,
                    operation_contract_version=target.metric_catalog_version,
                )
                self.db.add(breakdown)
                breakdowns[(target.id, *key)] = breakdown
            breakdown.operation_input_payload = payload
            breakdown.achieved_value = None
            breakdown.manual_score_value = None
            breakdown.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        return await self.get_entries(request.year_month)

    async def get_workbench(self, year_month: str) -> dict[str, Any]:
        month_start, month_end = self.month_range(year_month)
        config = await self._config(year_month)
        catalog = await self._catalog()
        targets = await self._targets(year_month)
        by_code = {str(row.metric_code): row for row in targets if row.metric_code}
        rows = []
        for item in catalog:
            target = by_code.get(item.metric_code)
            rows.append(
                {
                    "metric_code": item.metric_code,
                    "metric_name": item.metric_name,
                    "metric_direction": item.metric_direction,
                    "catalog_version": item.catalog_version,
                    "sort_key": item.sort_key,
                    "input_kind": item.input_kind,
                    "unit": item.unit,
                    "guidance": item.guidance,
                    "is_enabled": (
                        bool(getattr(target, "is_enabled", True)) if target else False
                    ),
                    "target_id": getattr(target, "id", None),
                    "target_value": (
                        getattr(target, "target_value", None)
                        if target
                        else item.default_target_value
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
        active_metrics = [item for item in request.metrics if item.is_enabled]
        if not active_metrics:
            raise ValueError("至少启用一项运营指标")
        if float(config.operation_max_score) != 20:
            raise ValueError("自动整数计分要求运营满分为 20")
        allocations = OperationPerformanceScoringService.allocate_integer_budget(
            [
                {"metric_code": item.metric_code, "sort_key": catalog_by_code[item.metric_code].sort_key}
                for item in active_metrics
            ]
        )

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
            row.target_value = catalog_item.default_target_value
            row.achieved_value = None
            row.max_score = allocations.get(item.metric_code, 0)
            row.penalty_enabled = False
            row.penalty_threshold = None
            row.penalty_per_unit = None
            row.penalty_max = None
            row.manual_score_enabled = False
            row.manual_score_value = None
            row.is_enabled = item.is_enabled
            row.metric_catalog_version = request.catalog_version
            row.scoring_model_version = "auto_integer_v1"
            row.operation_rule_snapshot = {
                "metric_code": catalog_item.metric_code,
                "sort_key": catalog_item.sort_key,
                "input_kind": catalog_item.input_kind,
                "unit": catalog_item.unit,
                "guidance": catalog_item.guidance,
                "target_value": catalog_item.default_target_value,
                "scoring_rule_version": catalog_item.scoring_rule_version,
            }
            row.performance_config_id = config.id
            row.performance_config_updated_at = getattr(config, "updated_at", None)
            row.status = "active"
            row.updated_at = datetime.now(timezone.utc)
            rows_by_code[item.metric_code] = row

        for row in existing:
            if row.metric_code not in rows_by_code:
                row.is_enabled = False
                row.updated_at = datetime.now(timezone.utc)
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
        result = await self.apply(
            OperationWorkbenchApplyRequest(
                year_month=year_month,
                catalog_version=max(
                    active_catalog.values(), key=lambda item: item.catalog_version
                ).catalog_version,
                metrics=metrics,
            ),
            username=username,
        )
        result["skipped"] = skipped
        return result
