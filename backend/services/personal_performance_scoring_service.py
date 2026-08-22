from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any


class PersonalPerformanceScoringService:
    """Controlled V1 personal-target scoring with integer result scores."""

    TOTAL_SCORE = 20

    @classmethod
    def allocate_integer_budget(cls, metrics: list[dict[str, Any]]) -> dict[str, int]:
        if not metrics:
            raise ValueError("至少启用一项个人运营指标")
        ordered = sorted(
            metrics,
            key=lambda metric: (int(metric["sort_key"]), str(metric["metric_code"])),
        )
        base, remainder = divmod(cls.TOTAL_SCORE, len(ordered))
        return {
            str(metric["metric_code"]): base + int(index < remainder)
            for index, metric in enumerate(ordered)
        }

    @classmethod
    def calculate_metric_score(
        cls, *, metric: dict[str, Any], payload: dict[str, Any] | None
    ) -> tuple[int | None, dict[str, Any]]:
        input_kind = str(metric.get("input_kind") or "percentage")
        if input_kind == "training_counts":
            return cls._training_score(metric=metric, payload=payload)
        if input_kind == "special_task":
            return cls._special_task_score(metric=metric, payload=payload)
        if input_kind != "percentage":
            raise ValueError("个人指标录入类型无效")
        if not payload or payload.get("actual_value") is None:
            return None, {"status": "pending", "message": "等待录入实际值"}
        target_raw = metric.get("default_target_value", metric.get("target_value"))
        target = Decimal(str(target_raw))
        actual = Decimal(str(payload["actual_value"]))
        if target <= 0:
            raise ValueError("正向指标目标必须大于零")
        if actual < 0:
            raise ValueError("实际值不能小于零")
        score = cls._rounded_score(metric["max_score"], min(actual / target, Decimal("1")))
        return score, {
            "status": "calculated",
            "achievement_rate": float(min(actual / target, Decimal("1"))),
            "score": score,
        }

    @staticmethod
    def _rounded_score(max_score: Any, rate: Decimal) -> int:
        return int(
            (Decimal(str(max_score)) * rate).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP
            )
        )

    @classmethod
    def _training_score(
        cls, *, metric: dict[str, Any], payload: dict[str, Any] | None
    ) -> tuple[int | None, dict[str, Any]]:
        if not payload or payload.get("completed_count") is None or payload.get("required_count") is None:
            return None, {"status": "pending", "message": "等待录入培训人数"}
        completed = int(payload["completed_count"])
        required = int(payload["required_count"])
        if completed < 0 or required < 0 or completed > required:
            raise ValueError("已完成人数必须在零到应完成人数之间")
        rate = Decimal("1") if required == 0 else Decimal(completed) / Decimal(required)
        score = cls._rounded_score(metric["max_score"], rate)
        return score, {
            "status": "calculated",
            "achievement_rate": float(rate),
            "score": score,
            "message": "无需培训，按 100% 达成" if required == 0 else None,
        }

    @classmethod
    def _special_task_score(
        cls, *, metric: dict[str, Any], payload: dict[str, Any] | None
    ) -> tuple[int | None, dict[str, Any]]:
        if not payload or not payload.get("result"):
            return None, {"status": "pending", "message": "等待选择专项任务结果"}
        result = str(payload["result"])
        rates = {"passed": Decimal("1"), "partial": Decimal("0.5"), "failed": Decimal("0")}
        if result not in rates:
            raise ValueError("专项任务结果无效")
        if result in {"partial", "failed"} and not str(payload.get("note") or "").strip():
            raise ValueError("专项任务部分完成或未完成时必须填写说明")
        score = cls._rounded_score(metric["max_score"], rates[result])
        return score, {
            "status": "calculated",
            "achievement_rate": float(rates[result]),
            "score": score,
        }
