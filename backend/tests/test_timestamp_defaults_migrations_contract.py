"""契约测试：11 个「时间戳默认值修复迁移」守护合并成一个参数化文件。

为什么合并（批次 F-3，2026-11-13）：

原先有 **11 个形态完全同构**的守护文件（每个 24~44 行），彼此差别只有三处：
① 迁移文件的 glob；② 必须出现在迁移源码里的字面量清单；③ 尾部断言的变体。
11 份几乎一样的代码 = 11 处要同步维护的地方，而它们守的是**同一类规则**：
「某个迁移必须存在，且必须提到这些表名和 `SET DEFAULT now()`」。

合并后**逐条等价**：

- 用例数 **23 → 23**（11 × 「迁移存在」+ 11 × 「必须提到」+ 1 × 「control_plane 额外字面量」）；
- 每条断言的字面量、顺序、glob 全部按原文件搬运，**未增未减**；
- 断言顺序也保持原样：每条断言是「一组字符串，至少命中其中一个」，
  绝大多数组只有一个字符串（= 原文件里的 `assert X in source`），
  `public_system` 的「created_at 或 updated_at」是一组两个。

不在合并范围：``test_field_mapping_template_timestamp_defaults_migration_contract.py``
（220 行 / 5 用例）—— 形态完全不同（要连真库验证漂移修复），**原样保留**。

本文件同时是**覆盖守护**：``test_every_timestamp_default_migration_is_guarded``
保证「每个 timestamp-defaults 迁移都必须有守护」，防止以后新增迁移时漏配。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Tuple

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VERSIONS_DIR = PROJECT_ROOT / "migrations" / "versions"

#: 形态不同、由专门守护覆盖的迁移（要连真库验证漂移修复，不并入本表）。
DEDICATED_GUARD_RELATIVE = (
    "backend/tests/test_field_mapping_template_timestamp_defaults_migration_contract.py"
)
DEDICATED_GUARDED_MIGRATION = "20260409_field_mapping_template_timestamp_defaults.py"


@dataclass(frozen=True)
class TimestampDefaultsSpec:
    """一个「时间戳默认值修复迁移」守护的完整语义。

    ``groups`` 是一组**有序**的断言组，每组是「至少命中其中一个」的字符串集合：
    单元素组 = 原文件里的一条 ``assert X in source``；
    多元素组 = 原文件里的一条 ``assert A in source or B in source``。
    """

    key: str
    glob: str
    groups: Tuple[Tuple[str, ...], ...]
    extra_groups: Tuple[Tuple[str, ...], ...] = ()

    def find(self) -> Path:
        """找到（最新的）那个迁移文件。"""
        matches = sorted(VERSIONS_DIR.glob(self.glob))
        assert (
            matches
        ), "expected a {0} timestamp default repair migration in migrations/versions".format(
            self.key
        )
        return matches[-1]


SPECS: Tuple[TimestampDefaultsSpec, ...] = (
    TimestampDefaultsSpec(
        key="a_class_business",
        glob="*a_class*business*timestamp*default*.py",
        groups=(
            ("sales_campaigns",),
            ("sales_campaign_shops",),
            ("performance_config",),
            ("employee_shop_assignments",),
            ("shop_commission_config",),
            ("created_at",),
            ("updated_at",),
            ("SET DEFAULT now()",),
        ),
    ),
    TimestampDefaultsSpec(
        key="a_class_tail",
        glob="*a_class*tail*timestamp*default*.py",
        groups=(
            ("sales_targets_a",),
            ("sales_campaigns_a",),
            ("employee_targets",),
            ("attendance_records",),
            ("performance_config_a",),
            ("created_at",),
            ("updated_at",),
            ("SET DEFAULT now()",),
        ),
    ),
    TimestampDefaultsSpec(
        key="c_class",
        glob="*c_class*timestamp*default*.py",
        groups=(
            ("shop_health_scores",),
            ("performance_scores",),
            ("clearance_rankings",),
            ("created_at",),
            ("updated_at",),
            ("SET DEFAULT now()",),
        ),
    ),
    TimestampDefaultsSpec(
        key="control_plane",
        glob="*control*plane*timestamp*default*.py",
        groups=(
            ("employee_tasks",),
            ("employee_task_logs",),
            ("employee_task_participants",),
            ("sync_progress_tasks",),
            ("dim_rate_limit_config",),
            ("notification_templates",),
            ("alert_rules",),
            ("created_at",),
            ("updated_at",),
            ("SET DEFAULT now()",),
        ),
        extra_groups=(
            ('("core", "employee_tasks")',),
            ('("core", "employee_task_logs")',),
            ('("core", "employee_task_participants")',),
        ),
    ),
    TimestampDefaultsSpec(
        key="core_dimensions",
        glob="*core*dimension*timestamp*default*.py",
        groups=(
            ("dim_platforms",),
            ("dim_products",),
            ("dim_product_master",),
            ("created_at",),
            ("updated_at",),
            ("SET DEFAULT now()",),
        ),
    ),
    TimestampDefaultsSpec(
        key="core_metadata",
        glob="*core*metadata*timestamp*default*.py",
        groups=(
            ("field_mappings",),
            ("field_mapping_template_items",),
            ("dim_currencies",),
            ("dim_fiscal_calendar",),
            ("dim_vendors",),
            ("created_at",),
            ("SET DEFAULT now()",),
        ),
    ),
    TimestampDefaultsSpec(
        key="core_runtime",
        glob="*core*runtime*timestamp*default*.py",
        groups=(
            ("account_aliases",),
            ("collection_configs",),
            ("collection_sync_points",),
            ("component_versions",),
            ("platform_accounts",),
            ("created_at",),
            ("updated_at",),
            ("SET DEFAULT now()",),
        ),
    ),
    TimestampDefaultsSpec(
        key="dim_shops",
        glob="*dim_shops*timestamp*default*.py",
        groups=(
            ("core.dim_shops",),
            ("created_at",),
            ("updated_at",),
            ("SET DEFAULT now()",),
            ("WHERE created_at IS NULL",),
            ("WHERE updated_at IS NULL",),
        ),
    ),
    TimestampDefaultsSpec(
        key="finance",
        glob="*finance*timestamp*default*.py",
        groups=(
            ("fx_rates",),
            ("po_headers",),
            ("po_lines",),
            ("grn_headers",),
            ("grn_lines",),
            ("inventory_ledger",),
            ("invoice_headers",),
            ("invoice_lines",),
            ("three_way_match_log",),
            ("fact_expenses_month",),
            ("allocation_rules",),
            ("fact_expenses_allocated_day_shop_sku",),
            ("logistics_costs",),
            ("logistics_allocation_rules",),
            ("tax_vouchers",),
            ("gl_accounts",),
            ("journal_entries",),
            ("journal_entry_lines",),
            ("opening_balances",),
            ("return_orders",),
            ("created_at",),
            ("updated_at",),
            ("SET DEFAULT now()",),
        ),
    ),
    TimestampDefaultsSpec(
        key="public_system",
        glob="*public*system*timestamp*default*.py",
        groups=(
            ("system_logs",),
            ("security_config",),
            ("smtp_config",),
            ("system_config",),
            ("created_at", "updated_at"),
            ("SET DEFAULT now()",),
        ),
    ),
    TimestampDefaultsSpec(
        key="target_breakdown",
        glob="*target_breakdown*timestamp*default*.py",
        groups=(
            ("a_class.target_breakdown",),
            ("created_at",),
            ("updated_at",),
            ("SET DEFAULT now()",),
            ("WHERE created_at IS NULL",),
            ("WHERE updated_at IS NULL",),
        ),
    ),
)

SPEC_IDS = [spec.key for spec in SPECS]

EXTRA_SPECS = tuple(spec for spec in SPECS if spec.extra_groups)
EXTRA_SPEC_IDS = [spec.key for spec in EXTRA_SPECS]


def _assert_groups(
    spec: TimestampDefaultsSpec, source: str, groups: Sequence[Tuple[str, ...]]
) -> None:
    """逐组断言：每组至少要命中其中一个字符串。"""
    for group in groups:
        if len(group) == 1:
            assert group[0] in source, "{0} 迁移里必须提到 {1!r}".format(
                spec.key, group[0]
            )
            continue
        assert any(
            literal in source for literal in group
        ), "{0} 迁移里至少要提到其中之一: {1}".format(
            spec.key, " / ".join(repr(literal) for literal in group)
        )


@pytest.mark.parametrize("spec", SPECS, ids=SPEC_IDS)
def test_timestamp_defaults_migration_exists(spec: TimestampDefaultsSpec):
    """对应的修复迁移必须存在。"""
    spec.find()


@pytest.mark.parametrize("spec", SPECS, ids=SPEC_IDS)
def test_timestamp_defaults_migration_mentions_required_repairs(
    spec: TimestampDefaultsSpec,
):
    """迁移源码必须提到该批表名与 ``SET DEFAULT now()``。"""
    source = spec.find().read_text(encoding="utf-8")
    _assert_groups(spec, source, spec.groups)


@pytest.mark.parametrize("spec", EXTRA_SPECS, ids=EXTRA_SPEC_IDS)
def test_timestamp_defaults_migration_mentions_extra_literals(
    spec: TimestampDefaultsSpec,
):
    """少数迁移还有「必须出现指定字面量」的额外断言（如 schema/表名二元组）。"""
    source = spec.find().read_text(encoding="utf-8")
    _assert_groups(spec, source, spec.extra_groups)


def test_every_timestamp_default_migration_is_guarded():
    """**覆盖守护**：每个 timestamp-defaults 迁移都必须有守护。

    为什么要这条：合并后的参数化表是「唯一一处」规格表 —— 如果以后新增了一个
    timestamp-defaults 迁移却忘了加进 :data:`SPECS`，那条规则就**静默失去守护**
    （原文件时代每个迁移各有一个文件，少加一个很难发现；现在一张表就能一眼看出）。

    例外只有一个：``field_mapping_template`` 那份由**专门的守护文件**覆盖
    （它要连真库验证漂移修复，形态与本表不同）。
    """
    migrations = sorted(
        path.name for path in VERSIONS_DIR.glob("*timestamp*default*.py")
    )
    assert migrations, "migrations/versions 下不该一个 timestamp-defaults 迁移都没有"

    covered = set()
    for spec in SPECS:
        covered.update(path.name for path in VERSIONS_DIR.glob(spec.glob))

    dedicated_guard = PROJECT_ROOT / DEDICATED_GUARD_RELATIVE
    assert (
        dedicated_guard.exists()
    ), "{0} 不见了 —— field_mapping_template 的专门守护不能丢".format(
        DEDICATED_GUARD_RELATIVE
    )

    uncovered = [name for name in migrations if name not in covered]
    assert uncovered == [DEDICATED_GUARDED_MIGRATION], (
        "这些 timestamp-defaults 迁移没有任何守护覆盖: {0} —— "
        "要么把 spec 加进 SPECS，要么补一个专门守护文件".format(uncovered)
    )


def test_each_spec_matches_exactly_one_migration():
    """每个 spec 的 glob 只能命中一个迁移 —— 否则「取最新那个」的语义会漂。"""
    for spec in SPECS:
        matches = sorted(path.name for path in VERSIONS_DIR.glob(spec.glob))
        assert (
            len(matches) == 1
        ), "{0} 的 glob {1!r} 命中了 {2} 个迁移: {3} —— " "规格表与迁移文件必须一一对应".format(
            spec.key, spec.glob, len(matches), matches
        )
