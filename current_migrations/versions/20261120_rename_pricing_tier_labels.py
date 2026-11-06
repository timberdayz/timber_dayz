"""Rename the pricing-tier labels to age-based names (Stage 3).

The old labels named the *duration of being slow-moving* (``滞销30天``,
``滞销60天`` …) while the tier itself starts at a **restock-age threshold**
(``min_restock_days`` = 60 / 90 / 120).  Those two numbers never matched — the
tier that starts at 60 days was called "slow-moving for 30 days" — so the
label was actively misleading.  The new labels state the threshold directly.

Renames applied
---------------
===================  ==================
old                  new
===================  ==================
``滞销30天``           ``库龄≥60天``
``滞销60天``           ``库龄≥90天``
``滞销60天以上``       ``库龄≥120天``
===================  ==================

``日常`` (the tier starting at day 0) keeps its name.

Why the notification baselines are rewritten too
-------------------------------------------------
``ops.price_adjust_baselines.last_notified_context`` stores a snapshot of the
pricing inputs per SKU (1119 rows in production).  The minimum-price change
notification compares the previous snapshot with the current one, and it used
to compare the **tier label** to decide "did this SKU cross a tier?".  A pure
label rename would therefore make *every* SKU look like it had crossed a tier
⇒ a storm of false "tier change" notifications.

Two things prevent that:

1. The snapshot rewrite below renames the label inside those JSON snapshots
   too, so the old snapshot still matches the new label.
2. The notification now compares the tier's **identity**
   (``pricing_tier_min_restock_days``, added in Stage 3) instead of its
   display name, so *future* renames can never cause a storm either.

Idempotent: every statement is guarded by the label still being the old one.
"""

from alembic import op
import sqlalchemy as sa


revision = "current_schema_20261120_rename_pricing_tier_labels"
down_revision = "current_schema_20261119_add_sku_roi_input_columns"
branch_labels = None
depends_on = None


#: (old_label, new_label) —— 长的写前面，避免将来有人加前缀时短串先命中。
_TIER_RENAMES = (
    ("滞销60天以上", "库龄≥120天"),
    ("滞销30天", "库龄≥60天"),
    ("滞销60天", "库龄≥90天"),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str, schema: str) -> bool:
    return _inspector().has_table(table, schema=schema)


def _has_column(table: str, schema: str, name: str) -> bool:
    return _has_table(table, schema) and name in {
        column["name"] for column in _inspector().get_columns(table, schema=schema)
    }


def _exec_params(sql_text: str, params: dict) -> None:
    """带绑定参数执行一段 SQL。

    ⚠️ ``op.execute(sqltext, params)`` **不是**绑定参数用法：它的第二个位置参数是
    ``execution_options``（keyword-only），传字典会直接报
    ``execute() takes 2 positional arguments but 3 were given``。
    带参数一律走 ``op.get_bind().execute(text, params)``。
    """
    op.get_bind().execute(sa.text(sql_text), params)


def _rename_policy_labels(renames) -> None:
    """规则表里的档位名：直接改列值（显示名，不影响任何计算）。"""
    if not _has_table("sku_pricing_policies", "finance"):
        return
    for old_label, new_label in renames:
        _exec_params(
            "UPDATE finance.sku_pricing_policies SET tier_label = :new_label "
            "WHERE tier_label = :old_label",
            {"old_label": old_label, "new_label": new_label},
        )


def _rename_baseline_snapshots(renames) -> None:
    """通知基线快照里的档位名：JSONB 里的同名字段一起改。

    不改的话：老快照存着旧名字、当前算出新名字 ⇒ 每一个 SKU 看起来都"跨了档"
    ⇒ 最低售价变更通知误报成「库龄跨档」⇒ 通知风暴。
    """
    if not _has_table("price_adjust_baselines", "ops"):
        return
    if not _has_column("price_adjust_baselines", "ops", "last_notified_context"):
        return
    for old_label, new_label in renames:
        _exec_params(
            "UPDATE ops.price_adjust_baselines "
            "SET last_notified_context = jsonb_set("
            "  last_notified_context::jsonb, "
            "  '{pricing_tier_label}', "
            "  to_jsonb(CAST(:new_label AS text))"
            ") "
            "WHERE last_notified_context IS NOT NULL "
            "AND last_notified_context::jsonb ->> 'pricing_tier_label' = :old_label",
            {"old_label": old_label, "new_label": new_label},
        )


def upgrade() -> None:
    _rename_policy_labels(_TIER_RENAMES)
    _rename_baseline_snapshots(_TIER_RENAMES)


def downgrade() -> None:
    _rename_baseline_snapshots(
        tuple((new_label, old_label) for old_label, new_label in _TIER_RENAMES)
    )
    _rename_policy_labels(
        tuple((new_label, old_label) for old_label, new_label in _TIER_RENAMES)
    )
