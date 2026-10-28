"""跨 family 变体接管的**表头行感知**候选选择 (D7 服务层)

为什么需要这一层
----------------
判定门槛写在 :mod:`backend.services.template_variant_takeover` 里, 但门槛本身
解决不了「读哪一行表头」的问题。

实测 ``tiktok/products/monthly``(2026-10-29, 本地库)::

    family 27 (monthly) -> 变体 id=30 -> legacy 模板 id=350 (38 列, header_row=2)
    family 23 (daily)   -> 变体 id=44 -> legacy 模板 id=362 (176 列, header_row=3)

源文件是 176 列格式, **真实表头在 0-based 第 3 行**(第 2 行是「全部/全部/…」分组行)。
如果先按 monthly 模板的 ``header_row=2`` 读表头, 读出来的是 172 个
``全部.N`` 垃圾列 —— 拿去和任何变体比对, 匹配率必然是 0%,
跨 family 接管**永远不可能命中**。

所以接管必须是「**按候选变体自己的 header_row 读表头, 再评估**」,
而不是「先按当前模板的行读, 再回头找能解释它的变体」。

本模块的职责
------------
1. 列出**同 platform + 同 data_domain** 的其他 family 的 active 版本变体
   (边界收窄: 不同平台的导出格式不可类比)
2. **按每个变体自己声明的 header_row** 读一次表头(同一行只读一次, 带缓存)
3. 用 :func:`evaluate_variant_takeover` 逐个评估, 用
   :func:`select_best_takeover` 选出最优
4. 返回接管决定 + 报告 + 已读到的表头列(调用方直接复用, 避免重复读盘)

本模块只做**候选发现**; 真正的「这份文件归谁管」仍然由
:class:`backend.services.template_family_service.TemplateResolver` 决定,
这样治理视图与判定链路不会出现两个口径。
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from modules.core.logger import get_logger

from backend.services.template_variant_takeover import (
    build_takeover_report,
    evaluate_variant_takeover,
    select_best_takeover,
    template_explains_columns,
)

logger = get_logger(__name__)

#: 读取指定表头行列的回调 —— 由调用方注入(判定链路 / 入库链路 / 治理路由)
HeaderColumnsReader = Callable[[int], Awaitable[List[str]]]


class CrossFamilyTakeoverService:
    """跨 family 变体接管候选发现。"""

    def __init__(self, db: AsyncSession):
        self.db = db
        # 延迟导入: template_family_service 不依赖本模块, 但本模块依赖它
        from backend.services.template_family_service import get_template_resolver

        self.resolver = get_template_resolver(db)

    async def find_candidate(
        self,
        *,
        platform: Optional[str],
        data_domain: Optional[str],
        read_header: HeaderColumnsReader,
        exclude_granularity: Optional[str] = None,
        exclude_sub_domain: Optional[str] = None,
        exclude_account: Optional[str] = None,
        exclude_family_id: Optional[int] = None,
        own_granularity: Optional[str] = None,
        own_sub_domain: Optional[str] = None,
        own_account: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """找出能解释当前文件的变体(同 platform + 同 data_domain)。

        候选池含**自身 family** 的变体 —— 接管的前提是「自己家解释不了」,
        自身 family 的变体必须优先(见 ``select_best_takeover`` 的排序口径)。

        Args:
            platform / data_domain: 接管边界(必须同平台同数据域)
            read_header: 按 0-based 行号读取表头列的回调(内部会做行级缓存)
            exclude_granularity / exclude_sub_domain / exclude_account:
                需要整体排除的 family 维度
            own_granularity / own_sub_domain / own_account:
                文件自身所属的维度 —— 标记为「自家」, 排序时优先
            exclude_family_id: 直接排除的 family 行 ID

        Returns:
            命中时返回::

                {
                    "variant": {...},         # 命中的变体
                    "decision": {...},        # 门槛评估结果
                    "report": {...},          # 可展示/可落库的接管报告(仅跨 family 时)
                    "family": {...},          # 来源 family
                    "version": {...},         # 来源 active 版本
                    "header_row": int,        # 应当使用的表头行
                    "header_columns": [...],  # 该行的表头列(调用方可直接复用)
                    "is_own_family": bool,    # 是否命中的是「自家」变体
                }

            未命中返回 ``None``。
        """
        if not platform or not data_domain:
            return None

        try:
            candidates = await self.resolver.list_cross_family_variants(
                platform=platform,
                data_domain=data_domain,
                exclude_family_id=exclude_family_id,
                exclude_granularity=exclude_granularity,
                exclude_sub_domain=exclude_sub_domain,
                exclude_account=exclude_account,
                own_granularity=own_granularity,
                own_sub_domain=own_sub_domain,
                own_account=own_account,
            )
        except Exception as exc:  # noqa: BLE001
            # 变体表不可用(SQLite 测试库 / 未迁移的库)时**不能拖垮判定链路** ——
            # 跨 family 接管是增强项, 查不到就当没有接管, 判定照常走旧口径。
            logger.warning("[Takeover] 读取跨 family 变体失败: %s", exc)
            return None
        if not candidates:
            return None

        columns_cache: Dict[int, List[str]] = {}
        read_count = 0

        async def columns_at(row: int) -> List[str]:
            nonlocal read_count
            if row not in columns_cache:
                read_count += 1
                try:
                    raw = await read_header(row)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "[Takeover] 读取表头失败 (row=%s): %s", row, exc
                    )
                    raw = []
                columns_cache[row] = list(raw or [])
            return columns_cache[row]

        evaluated: List[Dict[str, Any]] = []
        for candidate in candidates:
            variant = candidate.get("variant") or {}
            if not (variant.get("required_headers") or []):
                # 没有 required_headers 的变体无法做覆盖率判定
                continue
            header_row = variant.get("header_row")
            if header_row is None:
                # 没有声明表头行 -> 无法做「表头行感知」的评估, 不接管
                continue
            try:
                header_row = int(header_row)
            except (TypeError, ValueError):
                continue

            columns = await columns_at(header_row)
            if not columns:
                continue

            decision = evaluate_variant_takeover(variant, columns)
            if decision is None:
                continue

            evaluated.append(
                {
                    **candidate,
                    "decision": decision,
                    "header_row": header_row,
                    "header_columns": columns,
                }
            )

        best = select_best_takeover(evaluated)
        if best is None:
            return None

        is_own_family = bool(best.get("is_own_family"))
        report = None
        if not is_own_family:
            report = build_takeover_report(
                best["decision"],
                source_family=best.get("family"),
                source_version=best.get("version"),
            )
            logger.info(
                "[Takeover] 跨 family 接管命中: variant=%s family=%s row=%s 匹配率=%s",
                best["decision"].get("variant_key"),
                (best.get("family") or {}).get("id"),
                best["header_row"],
                best["decision"].get("match_rate"),
            )
        else:
            logger.info(
                "[Takeover] 本 family 变体命中(无需跨 family 接管): variant=%s family=%s row=%s",
                best["decision"].get("variant_key"),
                (best.get("family") or {}).get("id"),
                best["header_row"],
            )
        return {
            "variant": best["variant"],
            "decision": best["decision"],
            "report": report,
            "family": best.get("family"),
            "version": best.get("version"),
            "header_row": best["header_row"],
            "header_columns": best["header_columns"],
            "is_own_family": is_own_family,
            "header_reads": read_count,
        }


def get_cross_family_takeover_service(db: AsyncSession) -> CrossFamilyTakeoverService:
    """获取跨 family 接管候选服务实例。"""
    return CrossFamilyTakeoverService(db)


async def resolve_baseline_for_file(
    db: AsyncSession,
    *,
    catalog_file: Any,
    published_template: Any,
    contract_template: Any,
    read_header: HeaderColumnsReader,
    use_template_header_row: bool = True,
) -> Dict[str, Any]:
    """决定「拿哪一版模板做这个文件的比较基准」—— 判定链路与治理路由共用。

    优先级
    ------
    1. **文件契约** —— 采集当时生效的那一版模板。
       但必须**对照文件真实表头校验**: 采集登记时按粒度选模板, 而导出格式
       不一定跟着粒度走(tiktok 商品导出实际只有一种表结构), 契约可能指向
       一个已经过时的模板。
    2. **跨 family 变体接管** —— 契约解释不了文件时, 由其他粒度的变体接手。
    3. **当前已发布模板** —— 兜底。

    返回::

        {
            "baseline_template": FieldMappingTemplate | None,
            "baseline_kind": "contract" | "cross_family_variant" | "current",
            "header_row": int,          # 应当按哪一行读表头
            "takeover": dict | None,    # 接管报告
            "takeover_candidate": dict | None,
            "contract_stale": bool,     # 契约存在但已过时, 需要修正
        }
    """
    from backend.services.data_sync_status_semantics import (
        TEMPLATE_BASELINE_CONTRACT,
        TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT,
        TEMPLATE_BASELINE_CURRENT,
    )
    from modules.core.db import FieldMappingTemplate

    def _row_of(candidate: Any) -> int:
        if (
            use_template_header_row
            and getattr(candidate, "header_row", None) is not None
        ):
            return int(candidate.header_row)
        return 0

    baseline_template = None
    baseline_kind = TEMPLATE_BASELINE_CURRENT
    takeover_report = None
    takeover_candidate = None
    contract_stale = False
    baseline_columns: List[str] = []

    header_row = _row_of(published_template) if published_template is not None else 0

    if contract_template is not None:
        contract_row = _row_of(contract_template)
        try:
            contract_columns = await read_header(contract_row)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[Takeover] 读取契约表头失败 (row=%s): %s", contract_row, exc)
            contract_columns = []
        if contract_columns and template_explains_columns(
            contract_template,
            contract_columns,
        ):
            baseline_template = contract_template
            baseline_kind = TEMPLATE_BASELINE_CONTRACT
            header_row = contract_row
            baseline_columns = list(contract_columns)

    if baseline_template is None:
        service = CrossFamilyTakeoverService(db)
        takeover_candidate = await service.find_candidate(
            platform=getattr(catalog_file, "platform_code", None),
            data_domain=getattr(catalog_file, "data_domain", None),
            read_header=read_header,
            own_granularity=getattr(catalog_file, "granularity", None),
            own_sub_domain=(getattr(catalog_file, "sub_domain", None) or None),
            own_account=(getattr(catalog_file, "account", None) or None),
        )
        if takeover_candidate is not None:
            legacy_template_id = (takeover_candidate.get("decision") or {}).get(
                "source_legacy_template_id"
            )
            takeover_template = None
            if legacy_template_id is not None:
                try:
                    takeover_template = await db.get(
                        FieldMappingTemplate,
                        int(legacy_template_id),
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("[Takeover] 读取被接管模板失败: %s", exc)
                    takeover_template = None
            if takeover_template is not None:
                header_row = int(takeover_candidate["header_row"])
                baseline_columns = list(takeover_candidate.get("header_columns") or [])
                if takeover_candidate.get("is_own_family"):
                    # 自家变体命中 -> **不是接管**, 只是把基准落到自家变体的模板上
                    baseline_template = takeover_template
                    baseline_kind = TEMPLATE_BASELINE_CURRENT
                else:
                    takeover_report = takeover_candidate.get("report")
                    baseline_template = takeover_template
                    baseline_kind = TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT
                    contract_stale = contract_template is not None
                header_row = int(takeover_candidate["header_row"])
                baseline_columns = list(takeover_candidate.get("header_columns") or [])

    if not baseline_columns:
        baseline_columns = list(await read_header(header_row) or [])

    return {
        "baseline_template": baseline_template,
        "baseline_kind": baseline_kind,
        "header_row": header_row,
        "header_columns": baseline_columns,
        "takeover": takeover_report,
        "takeover_candidate": takeover_candidate,
        "contract_stale": contract_stale,
    }
