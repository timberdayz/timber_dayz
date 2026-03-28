from __future__ import annotations

from backend.utils.schema_cleanup_low_risk_proofs import collect_low_risk_candidate_proofs


def build_wave1_preplan() -> dict[str, list[dict[str, str]]]:
    proofs = collect_low_risk_candidate_proofs()

    approved_targets: list[dict[str, str]] = []
    blocked_targets: list[dict[str, str]] = []

    for table_name in ("target_breakdown", "performance_config", "sales_campaigns", "sales_campaign_shops"):
        proof = proofs[table_name]
        if proof["ready_for_wave1"]:
            approved_targets.append(
                {
                    "table_name": table_name,
                    "source_schema": "public",
                    "target_schema": str(proof["expected_target_schema"]),
                    "operation": "archive_rename",
                    "why": "runtime proof confirms target schema is authoritative",
                }
            )
        else:
            blocked_targets.append(
                {
                    "table_name": table_name,
                    "expected_target_schema": str(proof["expected_target_schema"]),
                    "blocker_reason": str(proof["blocker_reason"]),
                    "required_next_step": "complete ORM/runtime schema alignment before cleanup",
                }
            )

    return {
        "approved_targets": approved_targets,
        "blocked_targets": blocked_targets,
    }
