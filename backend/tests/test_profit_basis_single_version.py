"""利润基数**单一口径**守护（批次 4）。

背景（ADR-2026-11-21）：口径归一之后，系统里**只应存在一个**利润基数口径版本
``SETTLEMENT_BASIS_V1``。历史口径版本（``A_ONLY_V1`` /
``A_PRE_COMMISSION_LABOR_V2``）由迁移 ``20261243`` 删除。

本守护守三件事：

1. **判定唯一**：「什么是历史口径」只有一个判定处
   （``LaborCostPolicyService.is_legacy_basis_version``），
   且它必须认出**全部**历史版本 —— 不是只有 ``A_ONLY_V1``。
2. **读取时跳过**：所有读利润基数的地方都必须跳过历史口径行，
   否则同一个月的看板会同时出现两套口径的数字。
3. **迁移必须删干净**：删除 legacy 行的迁移存在，且覆盖全部历史版本。

⚠️ 这里刻意**不改** ``is_legacy_a_only_basis_version`` 的语义：
它判的是**成本构成**（只有 ``A_ONLY_V1`` 是「仅 A 类成本」，
``A_PRE_COMMISSION_LABOR_V2`` 的成本构成与现行口径一致），
按「重建快照用哪种成本构成」用它才是对的。
"""

import re
from pathlib import Path

import pytest

from backend.services.labor_cost_policy_service import LaborCostPolicyService

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 迁移文件：删除 legacy 利润基数行
MIGRATION = (
    REPO_ROOT / "current_migrations/versions/20261243_drop_legacy_profit_basis.py"
)

#: 读利润基数的服务 / 脚本（必须跳过历史口径行）
READERS = [
    REPO_ROOT / "backend/services/hr_income_calculation_service.py",
    REPO_ROOT / "backend/services/monthly_profit_settlement_service.py",
    REPO_ROOT / "scripts/check_monthly_profit_dashboard_readiness.py",
]


class TestLegacy判定:
    """「什么是历史口径」必须只有一处判定，且要认全。"""

    def test_legacy_versions_are_declared_once(self):
        assert LaborCostPolicyService.LEGACY_BASIS_VERSIONS == (
            "A_ONLY_V1",
            "A_PRE_COMMISSION_LABOR_V2",
        )
        assert LaborCostPolicyService.CURRENT_BASIS_VERSION == "SETTLEMENT_BASIS_V1"
        assert LaborCostPolicyService.KNOWN_BASIS_VERSIONS == (
            "SETTLEMENT_BASIS_V1",
            "A_ONLY_V1",
            "A_PRE_COMMISSION_LABOR_V2",
        )

    @pytest.mark.parametrize("version", ["A_ONLY_V1", "A_PRE_COMMISSION_LABOR_V2"])
    def test_is_legacy_basis_version_covers_every_legacy(self, version):
        assert LaborCostPolicyService.is_legacy_basis_version(version) is True

    @pytest.mark.parametrize(
        "version",
        ["SETTLEMENT_BASIS_V1", "", None, "SOMETHING_NEW"],
    )
    def test_is_legacy_basis_version_rejects_non_legacy(self, version):
        assert LaborCostPolicyService.is_legacy_basis_version(version) is False

    def test_is_current_basis_version(self):
        assert LaborCostPolicyService.is_current_basis_version("SETTLEMENT_BASIS_V1")
        assert not LaborCostPolicyService.is_current_basis_version("A_ONLY_V1")
        assert not LaborCostPolicyService.is_current_basis_version("")

    def test_a_only_predicate_keeps_its_narrow_meaning(self):
        """``is_legacy_a_only_basis_version`` 判的是**成本构成**，不能被扩大。

        ``A_PRE_COMMISSION_LABOR_V2`` 的成本构成与现行口径一致 ——
        若把它也判成「仅 A 类成本」，重建快照时成本会算少。
        """
        assert LaborCostPolicyService.is_legacy_a_only_basis_version("A_ONLY_V1")
        assert not LaborCostPolicyService.is_legacy_a_only_basis_version(
            "A_PRE_COMMISSION_LABOR_V2"
        )


class Test读取时跳过历史口径:
    """读利润基数的地方必须跳过历史口径行。"""

    @pytest.mark.parametrize("path", READERS, ids=lambda p: p.name)
    def test_reader_skips_legacy_rows(self, path):
        assert path.exists(), f"文件不存在：{path}"
        text = path.read_text(encoding="utf-8")
        assert "is_legacy_basis_version" in text, (
            f"{path.name} 没有跳过历史口径行 —— "
            "同一个月的看板会同时出现两套口径的数字。"
        )
        # 读利润基数的地方不许再用「只认 A_ONLY」的旧判定
        assert not re.search(
            r"is_legacy_a_only_basis_version\(\s*\n?\s*getattr\(\s*row",
            text,
        ), f"{path.name} 仍按「仅 A 类成本」判定 legacy，会漏掉 A_PRE_COMMISSION_LABOR_V2"


class Test迁移删除历史口径:
    """删除 legacy 行的迁移必须存在且覆盖全部历史版本。"""

    def test_migration_file_exists(self):
        assert MIGRATION.exists(), f"缺少迁移：{MIGRATION}"

    def test_migration_deletes_all_legacy_versions(self):
        text = MIGRATION.read_text(encoding="utf-8")
        for version in LaborCostPolicyService.LEGACY_BASIS_VERSIONS:
            assert version in text, f"迁移没有覆盖历史口径版本 {version}"
        assert "DELETE FROM" in text

    def test_migration_is_on_the_current_chain(self):
        text = MIGRATION.read_text(encoding="utf-8")
        assert (
            'down_revision = "current_schema_20261242_drop_monthly_profit_snapshots"'
            in text
        )

    def test_migration_declares_no_silent_downgrade(self):
        """downgrade 不许悄悄恢复旧行（恢复出来的数字是假的）。"""
        text = MIGRATION.read_text(encoding="utf-8")
        downgrade = text.split("def downgrade", 1)[-1]
        assert "INSERT" not in downgrade.upper()
