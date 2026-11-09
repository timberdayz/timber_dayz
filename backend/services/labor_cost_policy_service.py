from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.db import SystemConfig
from modules.core.logger import get_logger


class LaborCostPolicyService:
    """人工成本与利润基数的统一口径。

    口径名称
    --------
    以前这里有两个过渡名：``A_ONLY_V1``（只算 A 类成本）和
    ``A_PRE_COMMISSION_LABOR_V2``（A 类成本 + 提成前人力成本）。
    「V1 / V2」是上线期的临时叫法，业务上早就只有一个口径了，
    名字留着只会让人以为还有两个版本在跑。

    现在统一成中性名 ``SETTLEMENT_BASIS_V1``（结算基数 V1）：

    * **新写入**的利润基数一律用 ``SETTLEMENT_BASIS_V1``；
    * **历史已锁定**的快照保留原值（``A_ONLY_V1`` / ``A_PRE_COMMISSION_LABOR_V2``），
      不做批量改写 —— 审计要能看出「这一行是哪个时期按什么口径算出来的」；
    * 读的时候通过 :meth:`is_settlement_basis_version` 兼容新旧值。

    ``LABOR_COST_ALLOC_V1`` 是人力成本分摊表的 ``calculation_version``，
    与利润基数的 ``basis_version`` 是两套东西，不要混用。
    """

    CONFIG_KEY = "labor_cost_auto_effective_month"

    #: 当前唯一的利润基数口径
    CURRENT_BASIS_VERSION = "SETTLEMENT_BASIS_V1"

    #: 历史口径，仅用于读取兼容（历史快照保留原值以保审计可追溯）
    LEGACY_BASIS_VERSIONS = ("A_ONLY_V1", "A_PRE_COMMISSION_LABOR_V2")

    #: 所有可识别的口径版本
    KNOWN_BASIS_VERSIONS = (CURRENT_BASIS_VERSION,) + LEGACY_BASIS_VERSIONS

    # ------------------------------------------------------------------
    # 成本基数里到底算哪些成本 —— 这是**口径决策**，不是实现细节。
    # 放在这里是因为所有模块都从这里取，避免各自理解一套。
    # ------------------------------------------------------------------

    #: 计入成本基数的成本项
    #: （其他经营成本 + 提成前人力成本）
    INCLUDED_COST_FIELDS = (
        "other_a_class_cost_amount",
        "pre_commission_labor_cost_amount",
    )

    #: **不**计入成本基数的成本项
    #:
    #: * ``performance_salary``（绩效工资）
    #:   提成基数是「提成**前**利润」；绩效工资属于提成**之后**的支出。
    #:   把它计进基数，等于同一笔钱扣两次（先压低基数、再算提成），
    #:   而且分母越缩越小、金额波动被放大。
    #: * ``commission``（提成本身）
    #:   提成是「利润分给谁」的结果，不能反过来变成成本。
    EXCLUDED_COST_FIELDS = (
        "performance_salary",
        "commission",
    )

    #: 无归属人力成本（总部 / 仓库 / 客服等没有店铺归属的员工）
    #: **必须**落到各店头上 —— 否则这笔钱既不消失也不归属任何人，
    #: 等于让所有店的利润虚高、提成虚高。
    #: 分摊权重用「各店直接人力成本占比」，与结算口径同源、可复算。
    SHARED_LABOR_ALLOCATION_ENABLED = True

    @classmethod
    def describe_cost_basis_rules(cls) -> dict:
        """成本基数的口径说明（业务语言，供文档 / 接口引用）。"""
        return {
            "basis_version": cls.CURRENT_BASIS_VERSION,
            "formula": "利润基数 = 订单利润 − 其他经营成本 − 提成前人力成本",
            "included_cost_fields": list(cls.INCLUDED_COST_FIELDS),
            "excluded_cost_fields": list(cls.EXCLUDED_COST_FIELDS),
            "shared_labor_allocation_enabled": cls.SHARED_LABOR_ALLOCATION_ENABLED,
            "notes": [
                "绩效工资与提成本身不计入成本基数：提成基数是『提成前利润』。",
                "无归属人力成本按各店直接人力成本占比二次分摊进各店，"
                "避免这笔钱凭空消失导致利润与提成虚高。",
            ],
        }

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _validate_month(year_month: str) -> str:
        value = str(year_month or "").strip()
        try:
            datetime.strptime(value, "%Y-%m")
        except ValueError as exc:
            raise ValueError("effective month must use YYYY-MM") from exc
        return value

    async def get_effective_month(self) -> Optional[str]:
        """读取人工成本策略的生效月份；未配置或读不到时返回 None。

        ⚠️ **缺表必须降级而不是抛错**：看板概览等读路径会调用本方法，
        而 `system_config` 属于可选配置表——部分初始化的库里可能还没有它。
        读不到就按「未配置策略」处理（调用方退回手工成本口径），
        不能让整个看板接口 500。
        """
        try:
            record = (
                await self.db.execute(
                    select(SystemConfig).where(
                        SystemConfig.config_key == self.CONFIG_KEY
                    )
                )
            ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            get_logger(__name__).warning(
                "[LaborCostPolicy] failed to read %s, treating as unset: %s",
                self.CONFIG_KEY,
                exc,
            )
            await self.db.rollback()
            return None
        if record is None or not str(record.config_value or "").strip():
            return None
        return self._validate_month(record.config_value)

    async def get_profit_basis_version(self, year_month: str) -> str:
        """返回当月应当使用的利润基数口径。

        系统里**只有一个**口径了，不再按月份切换 V1/V2，
        所以这个方法保留下来只是为了不改调用方签名。
        """
        self._validate_month(year_month)
        return self.CURRENT_BASIS_VERSION

    @classmethod
    def is_settlement_basis_version(cls, basis_version: Optional[str]) -> bool:
        """判断一个 ``basis_version`` 是否属于「可识别的结算基数口径」。

        新旧口径都算 —— 历史快照保留原值以保审计可追溯，
        但业务逻辑不应该因为版本字符串不同而走不同的分支。
        """
        value = str(basis_version or "").strip()
        return value in cls.KNOWN_BASIS_VERSIONS

    @classmethod
    def normalize_basis_version(cls, basis_version: Optional[str]) -> str:
        """把任意（含历史）口径值规整成当前口径名，用于新写入的行。"""
        if cls.is_settlement_basis_version(basis_version):
            return cls.CURRENT_BASIS_VERSION
        return cls.CURRENT_BASIS_VERSION

    @classmethod
    def is_legacy_a_only_basis_version(cls, basis_version: Optional[str]) -> bool:
        """是否是历史「仅 A 类成本」口径。

        这条分支只为**复现历史快照**保留：新写入的行一律走当前口径。
        """
        return str(basis_version or "").strip() == "A_ONLY_V1"

    async def is_manual_labor_cost_allowed(self, year_month: str) -> bool:
        await self.get_profit_basis_version(year_month)
        return False

    async def set_effective_month(
        self,
        year_month: str,
        *,
        updated_by_user_id: Optional[int] = None,
    ) -> str:
        normalized_month = self._validate_month(year_month)
        record = (
            await self.db.execute(
                select(SystemConfig).where(SystemConfig.config_key == self.CONFIG_KEY)
            )
        ).scalar_one_or_none()
        if record is None:
            self.db.add(
                SystemConfig(
                    config_key=self.CONFIG_KEY,
                    config_value=normalized_month,
                    description="First month using projected labor cost",
                    updated_by=updated_by_user_id,
                )
            )
        else:
            record.config_value = normalized_month
            record.updated_at = datetime.now(timezone.utc)
            record.updated_by = updated_by_user_id
        await self.db.commit()
        return normalized_month
