from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.schemas.platform_shop_discovery import (
    PlatformShopDiscoveryCreateShopAccountRequest,
)
from backend.schemas.shop_discovery import (
    ShopDiscoveryEvidencePayload,
    ShopDiscoveryFieldSource,
    ShopDiscoveryMatchPayload,
    ShopDiscoveryPayload,
    ShopDiscoveryRunResponse,
)
from backend.services.shop_rename_service import (
    retain_previous_platform_shop_id_as_alias,
)
from modules.core.db import (
    PlatformShopDiscovery,
    ShopAccount,
    ShopAccountAlias,
    ShopAccountCapability,
)

# ---------------------------------------------------------------------------
# 探测状态机
# ---------------------------------------------------------------------------
#
# ``core.platform_shop_discoveries.status`` 是这套系统里**唯一**记录
# 「采集时看到的店铺编号到底指向谁」的地方。状态写错 ⇒ 运营以为一切正常,
# 实际数据已经带着错的编号落盘了。
#
# 状态语义:
#
# - ``detected_single_bound``      探测值 == 目标账号当前编号(确认通过)
# - ``stale_url``                  探测值 != 目标账号当前编号, 且目标账号**有**编号
#                                  (URL 还停在别的店 —— 切店尚未生效)
# - ``conflict_detected``          探测值被**另一个**账号占着
# - ``unmatched_platform_shop_id`` 探测值**对不上任何账号**, 且目标账号自己
#                                  还没有平台编号(无从判断绑定关系)
# - ``failed``                     **根本没探测成功** —— 采集时打开的是平台的
#                                  登录页 / 错误页 / 404 页, 页面上没有任何
#                                  店铺身份信息可读
#
# 最后这个状态是 H4 的正解: 以前「对不上任何账号」会被归进
# ``detected_single_bound`` —— **看起来像成功**, 实际是彻底没绑上。

PLATFORM_SHOP_DISCOVERY_STATUS_DETECTED_SINGLE_BOUND = "detected_single_bound"
PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL = "stale_url"
PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED = "conflict_detected"
PLATFORM_SHOP_DISCOVERY_STATUS_UNMATCHED = "unmatched_platform_shop_id"

#: 探测**失败**（没探测到任何东西）。
#:
#: ⚠️ **刻意不在** ``PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES`` 里 ——
#: 「没探测到」不是「探测到且对不上」, 不该进身份异常告警。
#: 2026-04 已有 3 条同口径的历史记录（当时命中的是登录页）。
PLATFORM_SHOP_DISCOVERY_STATUS_FAILED = "failed"

#: 需要人看一眼的状态 —— 这些不是「成功」, 是「采集期就发现身份对不上」。
#:
#: ⚠️ ``failed``（探测失败）**不在这里** —— 没探测到 ≠ 探测到且对不上。
PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES: frozenset[str] = frozenset(
    {
        PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL,
        PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED,
        PLATFORM_SHOP_DISCOVERY_STATUS_UNMATCHED,
    }
)


class PlatformShopDiscoveryService:
    @staticmethod
    def _default_capabilities_for(shop_type: str | None) -> dict[str, bool]:
        defaults = {
            "orders": True,
            "products": True,
            "services": True,
            "analytics": True,
            "finance": True,
            "inventory": True,
        }
        if shop_type == "global":
            defaults["services"] = False
        return defaults

    @staticmethod
    def _normalize_alias(value: str | None) -> str:
        return " ".join(str(value or "").strip().lower().split())

    async def _candidate_shop_account_ids(
        self,
        db: AsyncSession,
        *,
        platform: str,
        detected_store_name: str | None,
        detected_platform_shop_id: str | None,
        detected_region: str | None,
    ) -> list[str]:
        candidates: list[str] = []

        if detected_platform_shop_id:
            result = await db.execute(
                select(ShopAccount.shop_account_id).where(
                    func.lower(ShopAccount.platform) == platform.lower(),
                    ShopAccount.platform_shop_id == detected_platform_shop_id,
                    ShopAccount.enabled.is_(True),
                    ShopAccount.business_role == "operating_store",
                )
            )
            candidates.extend(result.scalars().all())

        if detected_store_name:
            normalized_alias = self._normalize_alias(detected_store_name)
            alias_result = await db.execute(
                select(ShopAccount.shop_account_id)
                .join(
                    ShopAccountAlias, ShopAccountAlias.shop_account_id == ShopAccount.id
                )
                .where(
                    func.lower(ShopAccountAlias.platform) == platform.lower(),
                    ShopAccountAlias.alias_normalized == normalized_alias,
                    ShopAccountAlias.is_active.is_(True),
                    ShopAccount.enabled.is_(True),
                    ShopAccount.business_role == "operating_store",
                )
            )
            candidates.extend(alias_result.scalars().all())

            shop_stmt = select(ShopAccount.shop_account_id).where(
                func.lower(ShopAccount.platform) == platform.lower(),
                ShopAccount.store_name == detected_store_name,
                ShopAccount.enabled.is_(True),
                ShopAccount.business_role == "operating_store",
            )
            if detected_region:
                shop_stmt = shop_stmt.where(ShopAccount.shop_region == detected_region)
            shop_result = await db.execute(shop_stmt)
            candidates.extend(shop_result.scalars().all())

        deduped: list[str] = []
        for candidate in candidates:
            if candidate not in deduped:
                deduped.append(candidate)
        return deduped

    async def _owner_of_platform_shop_id(
        self,
        db: AsyncSession,
        *,
        platform: str,
        platform_shop_id: str,
        exclude_shop_account_id: str | None = None,
    ) -> str | None:
        """查出占用这个平台店铺ID 的**其它**店铺账号ID；没人占用则返回 ``None``。

        归属校验只解决一个问题：**防止一个账号把别人的编号写到自己名下**。
        """
        detected = str(platform_shop_id or "").strip()
        if not detected:
            return None

        stmt = select(ShopAccount.shop_account_id).where(
            func.lower(ShopAccount.platform) == platform.lower(),
            ShopAccount.platform_shop_id == detected,
        )
        if exclude_shop_account_id:
            stmt = stmt.where(ShopAccount.shop_account_id != exclude_shop_account_id)
        result = await db.execute(stmt)
        owners = list(result.scalars().all())
        return owners[0] if owners else None

    async def _guard_platform_shop_id_binding(
        self,
        db: AsyncSession,
        *,
        platform: str,
        platform_shop_id: str,
        target_shop_account_id: str,
        allow_rebind: bool,
    ) -> tuple[str, str | None]:
        """改平台店铺ID 之前的**归属校验**（所有会改主数据的入口共用）。

        返回 ``(decision, owner_shop_account_id)``：

        - ``"bind"``     —— 允许改（这个编号没被别人占着）
        - ``"noop"``     —— 不需要改（编号已经就是这个账号的，或本次不允许换绑）
        - ``"conflict"`` —— **禁止改**：这个编号被**另一个**账号占着，
          ``owner`` 是占着它的账号ID

        ``allow_rebind`` 决定"已经有编号、但探测值不同"时能不能换绑：

        - **人工路径**（``record_manual_discovery`` / ``confirm_discovery``）传 True
          —— 平台真的换了编号时允许换绑（旧值留别名，历史数据不搬家）；
        - **采集运行时路径**传 False
          —— 运行时读到的编号来自**切店之前**的页面（是上一家店的编号），
            一律不许据此改主数据。
        """
        detected = str(platform_shop_id or "").strip()
        if not detected:
            return "noop", None

        owner = await self._owner_of_platform_shop_id(
            db,
            platform=platform,
            platform_shop_id=detected,
            exclude_shop_account_id=target_shop_account_id,
        )
        if owner is not None:
            return "conflict", owner

        if not allow_rebind:
            return "noop", None

        return "bind", None

    async def record_runtime_discovery(
        self,
        db: AsyncSession,
        *,
        platform: str,
        main_account_id: str,
        shop_account_id: str,
        detected_store_name: str | None,
        detected_platform_shop_id: str | None,
        detected_region: str | None,
        raw_payload: dict | None = None,
        probe_failed: bool = False,
    ) -> PlatformShopDiscovery | None:
        """记录一次**采集运行时**的店铺身份探测。

        ⚠️ **只记录证据，不改 ``core.shop_accounts``。**

        为什么不能改
        ------------
        运行时探测发生在「登录刚结束、切店组件还没跑」的位置
        （``modules/apps/collection_center/executor_v2.py`` 的三个调用点）。
        此刻 URL 上的 ``cnsc_shop_id`` 是**上一家店**的编号 ——
        持久 profile 会把上次会话停着的那个页面恢复出来。

        把这个值写进 ``platform_shop_id`` ⇒ 账号主数据**整体错位一位**
        ⇒ 采集下来的数据带着错的编号落盘
        ⇒ 语义层要么解析到别的账号，要么判成歧义落 ``unknown``。

        平台店铺ID 的变更只允许走人工路径：
        ``record_manual_discovery``（巡店）、``confirm_discovery``（人工确认）、
        账号管理页改号（``update_shop_account``，带唯一性校验）。

        状态语义
        --------
        - ``detected_single_bound``      ：探测值与目标账号当前编号一致（确认通过）
        - ``stale_url``                  ：探测值与目标账号当前编号**不一致**
          （URL 还停在别的店 —— 切店尚未生效）
        - ``conflict_detected``          ：探测值被**另一个**账号占着
        - ``unmatched_platform_shop_id`` ：探测值**对不上任何账号**，且目标账号
          自己还没有平台编号 ⇒ 无从判断绑定关系，**不算成功**
        - ``failed``                     ：**压根没探测成**（``probe_failed=True``，
          采集时打开的是平台的登录页 / 错误页 / 404 页）⇒ 页面上没有任何
          身份信息可读 ⇒ 不做绑定判定、**不写候选账号**、
          **不把 URL 上的编号当成探测值**
        """
        if probe_failed:
            # 错误页 / 404 页 / 登录页：URL 上的编号**不是探测结果**。
            #
            # 2026-11-07 实测事故：``https://seller.shopee.cn/404?cnsc_shop_id=1391124228``
            # 被当成一次正常探测 ⇒ 那个编号被另一个账号占着 ⇒ 记成
            # ``conflict_detected`` ⇒ 业务概览页弹出「采集期探测到 1 次店铺身份异常」。
            #
            # 那个编号是**上一家店**的（持久 profile 恢复出来的页面），
            # 拿它做绑定判定 = **制造假冲突**。
            # 现在判成「探测失败」：证据（URL）留在 ``raw_payload`` 里，
            # 不参与绑定判定，也不进身份异常告警（``failed`` 不在 issue 状态里）。
            discovery = PlatformShopDiscovery(
                platform=platform,
                main_account_id=main_account_id,
                detected_store_name=None,
                detected_platform_shop_id=None,
                detected_region=None,
                candidate_shop_account_ids=[],
                status=PLATFORM_SHOP_DISCOVERY_STATUS_FAILED,
                raw_payload={
                    **(raw_payload or {}),
                    "probe_failed": True,
                },
            )
            db.add(discovery)
            await db.commit()
            await db.refresh(discovery)
            return discovery

        if not detected_platform_shop_id:
            return None

        detected = str(detected_platform_shop_id).strip()
        shop_account = (
            await db.execute(
                select(ShopAccount).where(
                    ShopAccount.shop_account_id == shop_account_id
                )
            )
        ).scalar_one_or_none()
        current = str(
            (shop_account.platform_shop_id if shop_account else "") or ""
        ).strip()

        decision, owner = await self._guard_platform_shop_id_binding(
            db,
            platform=platform,
            platform_shop_id=detected,
            target_shop_account_id=shop_account_id,
            allow_rebind=False,
        )

        if decision == "conflict":
            status = PLATFORM_SHOP_DISCOVERY_STATUS_CONFLICT_DETECTED
        elif current and current != detected:
            status = PLATFORM_SHOP_DISCOVERY_STATUS_STALE_URL
        elif not current:
            # 目标账号自己还没有平台编号 ⇒ 探测值既不是本账号的,
            # 也没被别的账号占着(否则上面就是 conflict)。
            # 这种「什么都没对上」以前会被写成 detected_single_bound,
            # 看起来像成功 —— 实际是压根没绑上, 必须显式标出来。
            status = PLATFORM_SHOP_DISCOVERY_STATUS_UNMATCHED
        else:
            status = PLATFORM_SHOP_DISCOVERY_STATUS_DETECTED_SINGLE_BOUND

        discovery = PlatformShopDiscovery(
            platform=platform,
            main_account_id=main_account_id,
            detected_store_name=detected_store_name,
            detected_platform_shop_id=detected_platform_shop_id,
            detected_region=detected_region,
            candidate_shop_account_ids=([owner] if owner else [shop_account_id]),
            status=status,
            raw_payload=raw_payload or {},
        )
        db.add(discovery)
        await db.commit()
        await db.refresh(discovery)
        return discovery

    async def record_manual_discovery(
        self,
        db: AsyncSession,
        *,
        platform: str,
        main_account_id: str,
        detected_store_name: str | None,
        detected_platform_shop_id: str | None,
        detected_region: str | None,
        raw_payload: dict | None,
        confidence: float,
        source: dict[str, str | None],
        screenshot_path: str | None,
    ) -> ShopDiscoveryRunResponse:
        candidates = await self._candidate_shop_account_ids(
            db,
            platform=platform,
            detected_store_name=detected_store_name,
            detected_platform_shop_id=detected_platform_shop_id,
            detected_region=detected_region,
        )

        if len(candidates) == 1:
            status = "auto_bound"
        elif len(candidates) > 1:
            status = "pending_confirm"
        elif detected_store_name or detected_platform_shop_id:
            status = "no_match"
        else:
            status = "failed"

        persisted_status = {
            "auto_bound": "auto_bound",
            "pending_confirm": "pending_confirm",
            "no_match": "detected",
            "failed": "failed",
        }.get(status, "detected")

        discovery_record = PlatformShopDiscovery(
            platform=platform,
            main_account_id=main_account_id,
            detected_store_name=detected_store_name,
            detected_platform_shop_id=detected_platform_shop_id,
            detected_region=detected_region,
            candidate_shop_account_ids=candidates,
            status=persisted_status,
            raw_payload={
                **(raw_payload or {}),
                "source": source,
                "confidence": confidence,
                "screenshot_path": screenshot_path,
            },
        )
        db.add(discovery_record)

        if status == "auto_bound":
            shop_account = (
                await db.execute(
                    select(ShopAccount).where(
                        ShopAccount.shop_account_id == candidates[0]
                    )
                )
            ).scalar_one_or_none()
            if shop_account is not None and detected_platform_shop_id:
                # 归属校验：这个编号是不是被**另一个**账号占着？
                # 被别人占着就不能抢 —— 否则一个账号会把另一个账号的数据吸走。
                decision, owner = await self._guard_platform_shop_id_binding(
                    db,
                    platform=platform,
                    platform_shop_id=detected_platform_shop_id,
                    target_shop_account_id=candidates[0],
                    allow_rebind=True,
                )
                if decision == "conflict":
                    discovery_record.status = "conflict_detected"
                    discovery_record.candidate_shop_account_ids = sorted(
                        {candidates[0], owner or ""} - {""}
                    )
                    status = "pending_confirm"
                else:
                    previous_platform_shop_id = shop_account.platform_shop_id
                    shop_account.platform_shop_id = detected_platform_shop_id
                    shop_account.platform_shop_id_status = "auto_bound"
                    discovery_record.status = "auto_bound"
                    # 自动绑定也会换绑平台店铺ID ⇒ 旧值同样要留成别名。
                    await retain_previous_platform_shop_id_as_alias(
                        db, shop_account, previous_platform_shop_id
                    )

        await db.commit()
        await db.refresh(discovery_record)

        return ShopDiscoveryRunResponse(
            success=status != "failed",
            platform=platform,
            main_account_id=main_account_id,
            mode="current_only",
            discovery=ShopDiscoveryPayload(
                detected_store_name=detected_store_name,
                detected_platform_shop_id=detected_platform_shop_id,
                detected_region=detected_region,
                current_url=(raw_payload or {}).get("current_url"),
                source=ShopDiscoveryFieldSource(**source),
                confidence=confidence,
            ),
            match=ShopDiscoveryMatchPayload(
                status=status,
                shop_account_id=candidates[0] if len(candidates) == 1 else None,
                candidate_count=len(candidates),
            ),
            evidence=ShopDiscoveryEvidencePayload(screenshot_path=screenshot_path),
        )

    async def confirm_discovery(
        self,
        db: AsyncSession,
        discovery_id: int,
        shop_account_id: str,
    ) -> PlatformShopDiscovery:
        discovery = (
            await db.execute(
                select(PlatformShopDiscovery).where(
                    PlatformShopDiscovery.id == discovery_id
                )
            )
        ).scalar_one_or_none()
        if discovery is None:
            raise ValueError("platform shop discovery not found")

        shop_account = (
            await db.execute(
                select(ShopAccount).where(
                    ShopAccount.shop_account_id == shop_account_id
                )
            )
        ).scalar_one_or_none()
        if shop_account is None:
            raise ValueError("shop account not found")

        # 归属校验：人工确认也不能把**别人**的编号抢到自己名下。
        # 抢了的后果是另一个账号的数据被吸走（历史流量整体搬家）。
        decision, owner = await self._guard_platform_shop_id_binding(
            db,
            platform=discovery.platform,
            platform_shop_id=discovery.detected_platform_shop_id or "",
            target_shop_account_id=shop_account_id,
            allow_rebind=True,
        )
        if decision == "conflict":
            raise ValueError(
                "platform_shop_id '{0}' already belongs to shop account '{1}'".format(
                    discovery.detected_platform_shop_id, owner
                )
            )

        previous_platform_shop_id = shop_account.platform_shop_id
        shop_account.platform_shop_id = discovery.detected_platform_shop_id
        shop_account.platform_shop_id_status = "manual_confirmed"
        discovery.status = "manual_confirmed"
        # 人工确认也可能是换绑（平台把店ID换了）⇒ 旧值留成别名。
        await retain_previous_platform_shop_id_as_alias(
            db, shop_account, previous_platform_shop_id
        )

        await db.commit()
        await db.refresh(discovery)
        return discovery

    async def create_shop_account_from_discovery(
        self,
        db: AsyncSession,
        discovery_id: int,
        payload: PlatformShopDiscoveryCreateShopAccountRequest,
    ) -> PlatformShopDiscovery:
        discovery = (
            await db.execute(
                select(PlatformShopDiscovery).where(
                    PlatformShopDiscovery.id == discovery_id
                )
            )
        ).scalar_one_or_none()
        if discovery is None:
            raise ValueError("platform shop discovery not found")

        existing_shop = (
            await db.execute(
                select(ShopAccount).where(
                    ShopAccount.shop_account_id == payload.shop_account_id
                )
            )
        ).scalar_one_or_none()
        if existing_shop is not None:
            raise ValueError("shop account already exists")

        # 归属校验：新账号不能带着**别人已经在用**的平台店铺ID 建档
        # （否则两个账号认领同一个编号 ⇒ 语义层判歧义 ⇒ 流量落 unknown）。
        if discovery.detected_platform_shop_id:
            decision, owner = await self._guard_platform_shop_id_binding(
                db,
                platform=discovery.platform,
                platform_shop_id=discovery.detected_platform_shop_id,
                target_shop_account_id=payload.shop_account_id,
                allow_rebind=True,
            )
            if decision == "conflict":
                raise ValueError(
                    "platform_shop_id '{0}' already belongs to shop account '{1}'".format(
                        discovery.detected_platform_shop_id, owner
                    )
                )

        shop_account = ShopAccount(
            platform=discovery.platform,
            shop_account_id=payload.shop_account_id,
            main_account_id=discovery.main_account_id,
            store_name=payload.store_name,
            platform_shop_id=discovery.detected_platform_shop_id,
            platform_shop_id_status=(
                "manual_confirmed" if discovery.detected_platform_shop_id else "missing"
            ),
            shop_region=payload.shop_region or discovery.detected_region,
            shop_type=payload.shop_type,
            enabled=True,
            notes=payload.notes,
            created_by="system",
            updated_by="system",
        )
        db.add(shop_account)
        await db.flush()

        for domain, enabled in self._default_capabilities_for(
            payload.shop_type
        ).items():
            db.add(
                ShopAccountCapability(
                    shop_account_id=shop_account.id,
                    data_domain=domain,
                    enabled=enabled,
                )
            )

        discovery.candidate_shop_account_ids = [payload.shop_account_id]
        discovery.status = "created_shop_account"
        discovery.updated_at = datetime.now(timezone.utc)

        await db.commit()
        await db.refresh(discovery)
        return discovery

    # ------------------------------------------------------------------
    # 可见性: 让「采集期就发现身份对不上」这件事能被看见
    # ------------------------------------------------------------------

    async def list_platform_shop_discoveries(
        self,
        db: AsyncSession,
        *,
        statuses: Sequence[str] | None = None,
        only_issues: bool = False,
    ) -> list[PlatformShopDiscovery]:
        """按状态过滤列出探测记录。

        Args:
            statuses: 只保留这些状态(大小写不敏感); ``None`` 表示不过滤
            only_issues: 只保留「需要人看一眼」的状态
                (``PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES``)
        """
        stmt = select(PlatformShopDiscovery).order_by(
            PlatformShopDiscovery.created_at.desc()
        )

        effective = {str(s).strip() for s in (statuses or []) if str(s).strip()}
        if only_issues:
            effective |= set(PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES)
        if effective:
            stmt = stmt.where(PlatformShopDiscovery.status.in_(sorted(effective)))

        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def summarize_platform_shop_discovery_issues(
        self,
        db: AsyncSession,
        *,
        platform: str | None = None,
    ) -> dict[str, object]:
        """汇总「采集期身份对不上」的探测记录。

        返回:

        - ``total``        探测记录总数
        - ``issue_count``  问题态记录数(``stale_url`` / ``conflict_detected`` /
          ``unmatched_platform_shop_id``)
        - ``by_status``    各状态计数
        - ``issues``       问题态明细(轻量字段, 供告警面板直接展示)

        这是「让问题下次自己冒出来」的落点: 采集期探测到的身份冲突,
        比等数据落错之后再从看板上倒查**早一个数量级**。
        """
        count_stmt = select(
            PlatformShopDiscovery.status,
            func.count(),
        ).group_by(PlatformShopDiscovery.status)
        issue_stmt = select(
            PlatformShopDiscovery.id,
            PlatformShopDiscovery.platform,
            PlatformShopDiscovery.main_account_id,
            PlatformShopDiscovery.detected_store_name,
            PlatformShopDiscovery.detected_platform_shop_id,
            PlatformShopDiscovery.candidate_shop_account_ids,
            PlatformShopDiscovery.status,
            PlatformShopDiscovery.created_at,
        ).where(
            PlatformShopDiscovery.status.in_(
                sorted(PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES)
            )
        )

        if platform:
            normalized_platform = str(platform).strip().lower()
            if normalized_platform:
                count_stmt = count_stmt.where(
                    func.lower(PlatformShopDiscovery.platform) == normalized_platform
                )
                issue_stmt = issue_stmt.where(
                    func.lower(PlatformShopDiscovery.platform) == normalized_platform
                )

        by_status = {
            str(status): int(count)
            for status, count in (await db.execute(count_stmt)).all()
        }
        total = sum(by_status.values())
        issue_count = sum(
            count
            for status, count in by_status.items()
            if status in PLATFORM_SHOP_DISCOVERY_ISSUE_STATUSES
        )

        issue_rows = (
            await db.execute(
                issue_stmt.order_by(PlatformShopDiscovery.created_at.desc())
            )
        ).all()
        issues = [
            {
                "id": row.id,
                "platform": row.platform,
                "main_account_id": row.main_account_id,
                "detected_store_name": row.detected_store_name,
                "detected_platform_shop_id": row.detected_platform_shop_id,
                "candidate_shop_account_ids": row.candidate_shop_account_ids or [],
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in issue_rows
        ]

        return {
            "total": total,
            "issue_count": issue_count,
            "by_status": by_status,
            "issues": issues,
        }


_platform_shop_discovery_service: PlatformShopDiscoveryService | None = None


def get_platform_shop_discovery_service() -> PlatformShopDiscoveryService:
    global _platform_shop_discovery_service
    if _platform_shop_discovery_service is None:
        _platform_shop_discovery_service = PlatformShopDiscoveryService()
    return _platform_shop_discovery_service
