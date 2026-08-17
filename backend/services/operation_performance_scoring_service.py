from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


class OperationPerformanceScoringService:
    TOTAL_SCORE = 20

    @classmethod
    def allocate_integer_budget(cls, metrics: list[dict[str, Any]]) -> dict[str, int]:
        if not metrics:
            raise ValueError("至少启用一项运营指标")

        ordered = sorted(
            metrics,
            key=lambda metric: (
                int(metric["sort_key"]),
                str(metric["metric_code"]),
            ),
        )
        base_score, remainder = divmod(cls.TOTAL_SCORE, len(ordered))
        return {
            str(metric["metric_code"]): base_score + int(index < remainder)
            for index, metric in enumerate(ordered)
        }

    @classmethod
    def calculate_metric_score(
        cls,
        *,
        metric: dict[str, Any],
        payload: dict[str, Any] | None,
    ) -> tuple[int | None, dict[str, Any]]:
        input_kind = str(metric.get("input_kind") or "numeric")
        if input_kind == "training_counts":
            return cls._calculate_training_score(metric=metric, payload=payload)
        if input_kind == "special_check":
            return cls._calculate_special_check_score(metric=metric, payload=payload)
        if not payload or payload.get("actual_value") is None:
            return None, {"status": "pending", "message": "等待录入实际值"}

        target = Decimal(str(metric["target_value"]))
        actual = Decimal(str(payload["actual_value"]))
        direction = str(metric["metric_direction"])
        if actual < 0:
            raise ValueError("实际值不能小于零")
        if direction == "higher_better":
            if target <= 0:
                raise ValueError("正向指标目标必须大于零")
            achievement_rate = min(actual / target, Decimal("1"))
        elif direction == "lower_better":
            achievement_rate = (
                Decimal("1")
                if actual <= target
                else (Decimal("0") if actual == 0 else target / actual)
            )
        else:
            raise ValueError("自动计分指标必须配置评分方向")

        score = int(
            (Decimal(str(metric["max_score"])) * achievement_rate).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        return score, {
            "status": "calculated",
            "achievement_rate": float(achievement_rate),
            "score": score,
        }

    @classmethod
    def _calculate_training_score(
        cls, *, metric: dict[str, Any], payload: dict[str, Any] | None
    ) -> tuple[int | None, dict[str, Any]]:
        if not payload or payload.get("completed_count") is None or payload.get("required_count") is None:
            return None, {"status": "pending", "message": "等待录入培训人数"}
        completed = int(payload["completed_count"])
        required = int(payload["required_count"])
        if completed < 0 or required < 0 or completed > required:
            raise ValueError("培训已完成人数必须在零到应完成人数之间")
        rate = Decimal("1") if required == 0 else Decimal(completed) / Decimal(required)
        score = int(
            (Decimal(str(metric["max_score"])) * rate).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        return score, {
            "status": "calculated",
            "achievement_rate": float(rate),
            "score": score,
            "message": "无需培训，按 100% 达成" if required == 0 else None,
        }

    @classmethod
    def _calculate_special_check_score(
        cls, *, metric: dict[str, Any], payload: dict[str, Any] | None
    ) -> tuple[int | None, dict[str, Any]]:
        if not payload or not payload.get("result"):
            return None, {"status": "pending", "message": "等待选择专项检查结论"}
        result = str(payload["result"])
        rates = {"passed": Decimal("1"), "partial": Decimal("0.5"), "failed": Decimal("0")}
        if result not in rates:
            raise ValueError("专项检查结论无效")
        note = str(payload.get("note") or "").strip()
        if result in {"partial", "failed"} and not note:
            raise ValueError("专项检查未通过或部分完成时必须填写说明")
        score = int(
            (Decimal(str(metric["max_score"])) * rates[result]).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )
        return score, {
            "status": "calculated",
            "achievement_rate": float(rates[result]),
            "score": score,
        }
