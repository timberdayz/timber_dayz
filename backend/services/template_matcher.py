#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一模板匹配服务(SSOT)

v4.5.0新增:
- 提供统一的模板查找和应用逻辑
- 避免不同同步入口的重复逻辑
- 确保模板选择策略一致性

v4.18.2新增:
- 支持异步会话(AsyncSession)
- 双模式设计:同步/异步自动检测

调用方:
- FieldMappingEnhanced.vue(手动映射)
- data_sync_service.py(统一同步编排)
"""

from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_, case
from datetime import datetime

from modules.core.db import FieldMappingTemplate

# FieldMappingTemplateItem,  # v4.6.0移除:不再使用明细表,改用header_columns JSONB
from modules.core.logger import get_logger
from backend.services.currency_extractor import (
    get_currency_extractor,
)  # [*] v4.15.0新增
from backend.services.semantic_field_contract_service import (
    SemanticFieldContractService,
)
from backend.services.data_sync_status_semantics import (
    classify_drift,
)
from backend.services.template_alias_registry import get_header_alias_mapping
from backend.services.template_parse_rules_service import (
    DATE_ERROR_FORMAT_DRIFT_CODES,
    evaluate_date_value_shape,
)

logger = get_logger(__name__)


# ==================== 模板匹配条件构造 (SSOT) ====================
#
# 匹配规则被两处复用:
#   1. ``TemplateMatcher.find_best_template()`` —— 异步会话(同步/入库链路)
#   2. ``find_best_template_sync()``             —— 同步会话(采集落库登记)
#
# 两边必须用**同一套**条件, 否则会出现「采集时登记的模板」与
# 「入库时实际使用的模板」不一致 —— 那正是模板契约要消灭的问题。
# 因此条件构造集中在这里, 调用方只负责执行查询。

# 匹配层级名称 -> 命中后的日志说明
MATCH_LEVEL_ACCOUNT_SCOPED = "account_scoped"
MATCH_LEVEL_EXACT = "exact"
MATCH_LEVEL_RELAXED_SUB_DOMAIN = "relaxed_sub_domain"


def normalize_dimension_value(value: Optional[str]) -> Optional[str]:
    """维度归一化: 空字符串与 None 等价。"""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def match_dimension_condition(column, value: Optional[str]):
    """构造维度匹配条件。

    Treat empty string as None so that 用户保存的空值和实际None一致.
    """
    if value is None:
        return or_(column.is_(None), column == "")
    return column == value


def _account_generic_first_order():
    """同一版本号下, 「与店铺无关」的模板排在前面。

    为什么需要: 同一个版本号上可能同时存在「通用模板」与「店铺专属模板」。
    文件没有账号时, 应当优先用通用模板 —— 否则同一个文件在不同环境里
    可能被解释成不同模板(取决于数据库返回顺序)。
    """
    return case(
        (
            or_(
                FieldMappingTemplate.account.is_(None),
                FieldMappingTemplate.account == "",
            ),
            0,
        ),
        else_=1,
    )


def build_template_match_levels(
    platform: str,
    data_domain: str,
    granularity: Optional[str] = None,
    sub_domain: Optional[str] = None,
    account: Optional[str] = None,
) -> List[tuple]:
    """按优先级构造模板匹配条件组。

    返回 ``[(level_name, conditions), ...]``, 调用方按顺序逐级执行,
    命中即返回。

    * ``account_scoped``   账号/地区专属模板
    * ``exact``            精确匹配(platform + data_domain [+ sub_domain] + granularity)
    * ``relaxed_sub_domain``忽略 sub_domain(向后兼容; services 域不允许降级)

    降级语义(SSOT, 唯一一份定义)
    ----------------------------
    * **sub_domain**: 文件**没有** sub_domain 时**不约束** sub_domain
      (允许匹配任意 sub_domain 的模板); 文件**有** sub_domain 时必须相等。
      例外: ``services`` 域不允许再向下放宽(ai_assistant 与 agent 表头完全不同)。
    * **account**: 文件**有** account 时, 账号专属模板走第 0 级优先命中;
      其余级别只接受「与店铺无关」的模板(account 为空)或同账号模板,
      避免**别的店铺**的模板被误用。
      文件**没有** account 时不约束 account(与历史行为一致), 同版本号下通用模板优先。
    * **granularity**: 始终要求相等(忽略 granularity 的宽松匹配会选错模板, 已禁用)。
    """
    norm_granularity = normalize_dimension_value(granularity)
    norm_sub_domain = normalize_dimension_value(sub_domain)
    norm_account = normalize_dimension_value(account)
    normalized_domain = str(data_domain or "").lower()

    levels: List[tuple] = []

    # Level 0: 账号/地区专属模板
    if norm_account is not None:
        level0_conditions = [
            FieldMappingTemplate.platform == platform,
            FieldMappingTemplate.data_domain == data_domain,
            match_dimension_condition(
                FieldMappingTemplate.granularity, norm_granularity
            ),
            match_dimension_condition(FieldMappingTemplate.account, norm_account),
            FieldMappingTemplate.status == "published",
        ]
        if norm_sub_domain is not None:
            level0_conditions.append(
                match_dimension_condition(
                    FieldMappingTemplate.sub_domain, norm_sub_domain
                )
            )
        levels.append((MATCH_LEVEL_ACCOUNT_SCOPED, level0_conditions))

    # Level 1: 精确匹配
    level1_conditions = [
        FieldMappingTemplate.platform == platform,
        FieldMappingTemplate.data_domain == data_domain,
        match_dimension_condition(FieldMappingTemplate.granularity, norm_granularity),
        FieldMappingTemplate.status == "published",
    ]
    # [*] v4.16.0修复:只有当调用方提供了sub_domain时,才要求模板的sub_domain与之匹配
    # 当文件没有sub_domain时,不添加sub_domain条件,允许匹配任何sub_domain的模板
    if norm_sub_domain is not None:
        level1_conditions.append(
            match_dimension_condition(FieldMappingTemplate.sub_domain, norm_sub_domain)
        )
    # [*] 账号维度: 文件有账号时, 不允许命中「别的店铺」的专属模板。
    if norm_account is not None:
        level1_conditions.append(
            or_(
                FieldMappingTemplate.account.is_(None),
                FieldMappingTemplate.account == "",
                FieldMappingTemplate.account == norm_account,
            )
        )
    levels.append((MATCH_LEVEL_EXACT, level1_conditions))

    # Level 2: 忽略sub_domain(向后兼容)
    # [*] v4.16.0修复:services域不允许忽略sub_domain(ai_assistant和agent表头完全不同)
    level2_allowed = norm_granularity is not None or (
        sub_domain is not None and normalized_domain != "services"
    )
    services_blocked = normalized_domain == "services" and norm_sub_domain is not None
    if level2_allowed and not services_blocked:
        level2_conditions = [
            FieldMappingTemplate.platform == platform,
            FieldMappingTemplate.data_domain == data_domain,
            match_dimension_condition(
                FieldMappingTemplate.granularity, norm_granularity
            ),
            FieldMappingTemplate.status == "published",
        ]
        if norm_account is not None:
            level2_conditions.append(
                or_(
                    FieldMappingTemplate.account.is_(None),
                    FieldMappingTemplate.account == "",
                    FieldMappingTemplate.account == norm_account,
                )
            )
        levels.append((MATCH_LEVEL_RELAXED_SUB_DOMAIN, level2_conditions))

    return levels


# ==================== 文件 → 模板的唯一解析入口 (SSOT) ====================
#
# 背景
# ----
# 「一个文件该由哪一版模板解释」这件事, 历史上散落在三处, 口径各不相同:
#
#   1. ``TemplateMatcher.find_best_template``      —— 三级降级(账号专属 → 精确 → 忽略 sub_domain)
#   2. ``TemplateFamilyService._dimension_key``    —— 严格 5 维相等
#   3. ``TemplateFamilyService._legacy_shadow_compare`` —— 第四套(只按 version 取最新)
#
# 同一件事三把尺子 ⇒ 治理面板与入库判定对同一个文件给出相反结论
# (实测: resolver 报 ready, find_best_template 报「没有模板」)。
#
# 本模块把降级规则收进**唯一**入口 ``resolve_template_for_file``,
# 入库判定 / 治理看板 / 家族投影三处都调用它。
# 降级语义写在 :func:`build_template_match_levels` 的文档里(唯一一份定义)。


@dataclass(frozen=True)
class TemplateFileResolution:
    """一次「文件 → 模板」解析的结果。"""

    template: Optional[FieldMappingTemplate]
    level: Optional[str]
    platform: str
    data_domain: str
    granularity: Optional[str]
    sub_domain: Optional[str]
    account: Optional[str]

    @property
    def matched(self) -> bool:
        return self.template is not None


def _pick_by_sample_rows(
    candidates: List[FieldMappingTemplate],
    sample_rows: Optional[List[Dict[str, Any]]],
    *,
    file_date_from: Any = None,
    file_date_to: Any = None,
) -> FieldMappingTemplate:
    """在同级别的候选里挑一个「解析规则与样本行吻合」的模板。

    没有样本行时直接取第一个(版本号最高、通用模板优先)。

    [*] 批次 A 回归修复: 必须把**文件期间**一起传下去, 否则
    ``auto_by_companion_period`` 的规则永远判为「解不出样本」,
    候选里如果混着别的模板就会被挑错 ⇒ 用错解析规则 ⇒ 整份文件入库失败。
    """
    if not sample_rows:
        return candidates[0]
    # [*] 延迟导入: template_family_service 依赖本模块, 顶层互相 import 会成环
    from backend.services.template_family_service import _variant_matches_sample_rows

    for candidate in candidates:
        if _variant_matches_sample_rows(
            candidate.field_parse_rules or [],
            sample_rows,
            companion_date_from=file_date_from,
            companion_date_to=file_date_to,
        ):
            return candidate
    return candidates[0]


async def resolve_template_for_file(
    db: AsyncSession,
    *,
    platform: str,
    data_domain: str,
    granularity: Optional[str] = None,
    sub_domain: Optional[str] = None,
    account: Optional[str] = None,
    sample_rows: Optional[List[Dict[str, Any]]] = None,
    file_date_from: Any = None,
    file_date_to: Any = None,
) -> TemplateFileResolution:
    """唯一入口: 解析「解释这个文件的模板」。

    Args:
        platform: 平台代码
        data_domain: 数据域
        granularity: 粒度(可选)
        sub_domain: 子域(可选)
        account: 账号/地区(可选)
        sample_rows: 样本行(可选) —— 给出时优先选解析规则吻合的模板
        file_date_from / file_date_to: 文件期间(可选) —— ``auto_by_companion_period``
            的规则**必须**拿到期间才能判定样本是否吻合

    Returns:
        :class:`TemplateFileResolution`; ``template`` 为 None 表示没匹配到。
    """
    norm_granularity = normalize_dimension_value(granularity)
    norm_sub_domain = normalize_dimension_value(sub_domain)
    norm_account = normalize_dimension_value(account)

    levels = build_template_match_levels(
        platform=platform,
        data_domain=data_domain,
        granularity=granularity,
        sub_domain=sub_domain,
        account=account,
    )

    for level_name, conditions in levels:
        stmt = (
            select(FieldMappingTemplate)
            .where(*conditions)
            .order_by(
                desc(FieldMappingTemplate.version),
                _account_generic_first_order(),
            )
        )
        result = await db.execute(stmt)
        candidates = list(result.scalars().all())
        if not candidates:
            continue

        template = _pick_by_sample_rows(
            candidates,
            sample_rows,
            file_date_from=file_date_from,
            file_date_to=file_date_to,
        )
        logger.debug(
            f"[TemplateMatcher] 命中模板({level_name}): {template.template_name} "
            f"(v{template.version}, {platform}/{data_domain}/"
            f"{norm_sub_domain or 'None'}/{norm_granularity or 'None'}/"
            f"{norm_account or 'None'})"
        )
        return TemplateFileResolution(
            template=template,
            level=level_name,
            platform=platform,
            data_domain=data_domain,
            granularity=norm_granularity,
            sub_domain=norm_sub_domain,
            account=norm_account,
        )

    logger.info(
        f"[TemplateMatcher] 未找到严格匹配模板(platform={platform}, domain={data_domain}, "
        f"sub_domain={norm_sub_domain or 'None'}, granularity={norm_granularity or 'None'}, "
        f"account={norm_account or 'None'})"
    )
    return TemplateFileResolution(
        template=None,
        level=None,
        platform=platform,
        data_domain=data_domain,
        granularity=norm_granularity,
        sub_domain=norm_sub_domain,
        account=norm_account,
    )


def resolve_template_for_file_sync(
    session,
    *,
    platform: str,
    data_domain: str,
    granularity: Optional[str] = None,
    sub_domain: Optional[str] = None,
    account: Optional[str] = None,
    sample_rows: Optional[List[Dict[str, Any]]] = None,
    file_date_from: Any = None,
    file_date_to: Any = None,
) -> TemplateFileResolution:
    """同步会话版的唯一入口(采集落库登记链路)。

    与 :func:`resolve_template_for_file` 使用**同一套**条件与降级规则,
    保证「登记时记录的模板契约」与「入库时实际使用的模板」一致。
    """
    norm_granularity = normalize_dimension_value(granularity)
    norm_sub_domain = normalize_dimension_value(sub_domain)
    norm_account = normalize_dimension_value(account)

    levels = build_template_match_levels(
        platform=platform,
        data_domain=data_domain,
        granularity=granularity,
        sub_domain=sub_domain,
        account=account,
    )

    for level_name, conditions in levels:
        stmt = (
            select(FieldMappingTemplate)
            .where(*conditions)
            .order_by(
                desc(FieldMappingTemplate.version),
                _account_generic_first_order(),
            )
        )
        candidates = list(session.execute(stmt).scalars().all())
        if not candidates:
            continue
        template = _pick_by_sample_rows(
            candidates,
            sample_rows,
            file_date_from=file_date_from,
            file_date_to=file_date_to,
        )
        return TemplateFileResolution(
            template=template,
            level=level_name,
            platform=platform,
            data_domain=data_domain,
            granularity=norm_granularity,
            sub_domain=norm_sub_domain,
            account=norm_account,
        )

    return TemplateFileResolution(
        template=None,
        level=None,
        platform=platform,
        data_domain=data_domain,
        granularity=norm_granularity,
        sub_domain=norm_sub_domain,
        account=norm_account,
    )


def find_best_template_sync(
    session,
    platform: str,
    data_domain: str,
    granularity: Optional[str] = None,
    sub_domain: Optional[str] = None,
    account: Optional[str] = None,
):
    """同步会话版本的模板查找(采集落库登记用)。

    与 :meth:`TemplateMatcher.find_best_template` 使用同一套匹配条件,
    保证「登记时记录的模板契约」与「入库时实际使用的模板」一致。
    """
    try:
        resolution = resolve_template_for_file_sync(
            session,
            platform=platform,
            data_domain=data_domain,
            granularity=granularity,
            sub_domain=sub_domain,
            account=account,
        )
        return resolution.template
    except Exception as e:  # noqa: BLE001
        logger.error(f"[TemplateMatcher] 同步查找模板失败: {e}", exc_info=True)
        return None


class TemplateMatcher:
    """
    统一模板匹配服务

    核心原则:
    - 精确匹配:(platform, data_domain, granularity)
    - 状态筛选:status = 'published'(只用已发布模板)
    - 版本选择:MAX(version)(最新版本)
    - 忽略sub_domain:宽松匹配,提高覆盖率

    v4.18.2新增:
    - 支持异步会话(AsyncSession)
    v4.19.0更新:
    - 移除同步/异步双模式支持,统一为异步架构
    """

    def __init__(self, db: AsyncSession):
        """
        初始化模板匹配器

        Args:
            db: 异步数据库会话(AsyncSession)
        """
        self.db = db

    @staticmethod
    def _match_dimension(column, value: Optional[str]):
        """
        构造维度匹配条件

        Treat empty string as None so that 用户保存的空值和实际None一致.
        """
        return match_dimension_condition(column, value)

    def _normalize_dimension(self, value: Optional[str]) -> Optional[str]:
        return normalize_dimension_value(value)

    def _normalize_headers_for_compare(
        self,
        data_domain: str,
        columns: List[str],
    ) -> List[str]:
        currency_extractor = get_currency_extractor()
        normalized: List[str] = []
        for column in columns:
            field_name = str(column)
            currency_code = currency_extractor.extract_currency_code(field_name)
            if currency_code:
                normalized.append(currency_extractor.normalize_field_name(field_name))
            else:
                normalized.append(field_name)
        return normalized

    def _apply_header_aliases(
        self,
        platform: str,
        data_domain: str,
        granularity: str,
        columns: List[str],
        account: Optional[str] = None,
    ) -> List[str]:
        alias_mapping = get_header_alias_mapping(
            platform, data_domain, granularity, account=account
        )
        if not alias_mapping:
            return list(columns)
        return [alias_mapping.get(column, column) for column in columns]

    @staticmethod
    def _optional_raw_fields(core_fields: Any) -> List[str]:
        """模板核心字段清单里 ``required=false`` 的**原始列名**。

        这是「某列是否可缺」的**模板级声明**(SSOT):
        用户在工作台勾选「非必填」的列, 少掉它就不阻断入库。

        只有**带 raw_name** 的条目才有意义 —— 纯语义键条目(``raw_name=None``)
        描述的是「这个语义键参与去重/校验」, 而不是「某个具体物理列可缺」。

        ``semantic_key`` 形态的可选性由 L2 语义契约负责(``optional_keys``),
        两处互补, 不重复。
        """
        from backend.services.core_fields_service import normalize_core_fields

        optional: List[str] = []
        for entry in normalize_core_fields(core_fields):
            if entry.get("required"):
                continue
            raw_name = str(entry.get("raw_name") or "").strip()
            if raw_name and raw_name not in optional:
                optional.append(raw_name)
        return optional

    async def find_best_template(
        self,
        platform: str,
        data_domain: str,
        granularity: str = None,
        sub_domain: str = None,  # v4.5.1启用:支持子数据类型识别
        account: str = None,
    ) -> Optional[FieldMappingTemplate]:
        """
        查找最佳模板(v4.5.1增强版,v4.18.2异步支持)

        [*] 本方法只保留「取模板」的语义, 降级规则全部收敛到
        :func:`resolve_template_for_file`(唯一入口) —— 入库判定 / 治理看板 /
        家族投影三处必须用同一把尺子。

        匹配策略(三级智能降级, 定义见 ``build_template_match_levels``):
        Level 0: 账号/地区专属模板(platform + data_domain + granularity + account)
        Level 1: 精确匹配(platform + data_domain + sub_domain + granularity)
        Level 2: 忽略sub_domain(向后兼容)

        状态筛选:status = 'published'(只用已发布模板)
        版本选择:MAX(version)(最新版本)

        Args:
            platform: 平台代码(必填)
            data_domain: 数据域(必填)
            granularity: 粒度(可选)
            sub_domain: 子域(可选,如ai_assistant/agent)
            account: 账号/地区(可选)。给出时优先匹配该账号的专属模板,
                找不到再回落到通用模板 —— 这是「同一平台不同地区表头不一致」
                各自使用一套模板的前提。

        Returns:
            FieldMappingTemplate对象 或 None
        """
        try:
            resolution = await resolve_template_for_file(
                self.db,
                platform=platform,
                data_domain=data_domain,
                granularity=granularity,
                sub_domain=sub_domain,
                account=account,
            )
            if resolution.template is None:
                logger.info(
                    f"[TemplateMatcher] 未找到模板: {platform}/{data_domain}/"
                    f"{resolution.sub_domain or 'ANY'}/{resolution.granularity or 'ANY'}"
                )
                return None
            return resolution.template
        except Exception as e:
            logger.error(f"[TemplateMatcher] 查找模板失败: {e}", exc_info=True)
            return None

    async def find_published_template_by_format(
        self,
        *,
        platform: str,
        data_domain: str,
        format_signature: str,
        granularity: Optional[str] = None,
        sub_domain: Optional[str] = None,
        account: Optional[str] = None,
    ) -> Optional[FieldMappingTemplate]:
        """取「同一维度、同一格式签名」下的当前已发布模板。

        [*] 批次 H(H-1): 同维度多格式并存之后,
        「当前已发布模板」**不再是**「版本号最高的那个」——
        那可能是**另一种格式**(平台改过导出格式)。

        判定链路用它回答「我们自己升级过模板没有」,
        这个对照必须限定在**同格式内**:
        否则「另一种格式并存」会被误报成「我们升级过模板」。

        降级顺序与 :func:`resolve_template_for_file` 完全一致(同一把尺子)。
        """
        if not format_signature:
            return None

        # [*] 延迟导入: template_family_service 依赖本模块, 顶层互相 import 会成环
        from backend.services.template_family_service import resolve_format_signature

        levels = build_template_match_levels(
            platform=platform,
            data_domain=data_domain,
            granularity=granularity,
            sub_domain=sub_domain,
            account=account,
        )
        for _level_name, conditions in levels:
            stmt = (
                select(FieldMappingTemplate)
                .where(*conditions)
                .order_by(
                    desc(FieldMappingTemplate.version),
                    _account_generic_first_order(),
                )
            )
            result = await self.db.execute(stmt)
            for candidate in result.scalars().all():
                if resolve_format_signature(candidate) == format_signature:
                    return candidate
        return None

    async def get_template_config(self, template_id: int) -> Dict[str, Any]:
        """
        获取模板的完整配置(v4.6.0重构版,v4.18.2异步支持)

        v4.6.0变更:
        - mappings改为header_columns(原始表头字段列表)

        包含:
        - header_row: 表头行索引
        - sub_domain: 子数据类型
        - sheet_name: Excel工作表名称
        - encoding: 文件编码
        - field_count: 字段数量
        - header_columns: 原始表头字段列表(v4.6.0新增)
        """
        try:
            # [*] v4.18.2:支持异步会话
            result = await self.db.execute(
                select(FieldMappingTemplate).where(
                    FieldMappingTemplate.id == template_id
                )
            )
            template = result.scalar_one_or_none()

            if not template:
                logger.warning(f"[TemplateMatcher] 模板不存在: ID={template_id}")
                return {}

            # v4.6.0:从header_columns读取原始表头字段列表
            header_columns = template.header_columns or []

            return {
                "header_row": template.header_row or 0,
                "sub_domain": template.sub_domain,
                "sheet_name": template.sheet_name,
                "encoding": template.encoding or "utf-8",
                "field_count": template.field_count or len(header_columns),
                "header_columns": header_columns,  # v4.6.0:返回原始表头字段列表
                "header_bindings": template.header_bindings or [],
                "template_name": template.template_name,
                "version": template.version,
                "status": template.status,
            }

        except Exception as e:
            logger.error(f"[TemplateMatcher] 获取模板配置失败: {e}", exc_info=True)
            return {}

    async def get_template_mappings(self, template_id: int) -> Dict[str, Dict]:
        """
        获取模板的字段映射(v4.6.0重构版,v4.18.2异步支持)

        v4.6.0变更:
        - 不再查询FieldMappingTemplateItem表
        - 改为从template.header_columns读取原始表头字段列表
        - 返回格式:{original_field: {standard_field: None, confidence: 1.0, method: 'template', reason: '模板应用'}}

        Args:
            template_id: 模板ID

        Returns:
            {original_field: {standard_field, confidence, ...}}
        """
        try:
            # [*] v4.18.2:支持异步会话
            result = await self.db.execute(
                select(FieldMappingTemplate).where(
                    FieldMappingTemplate.id == template_id
                )
            )
            template = result.scalar_one_or_none()

            if not template:
                logger.warning(f"[TemplateMatcher] 模板不存在: ID={template_id}")
                return {}

            header_columns = template.header_columns or []

            # 构建映射字典(v4.6.0:不再有标准字段映射,只返回原始表头)
            mappings = {}
            for col in header_columns:
                mappings[col] = {
                    "standard_field": None,  # v4.6.0:不再存储标准字段映射
                    "confidence": 1.0,
                    "method": "template",
                    "reason": f"模板应用(原始表头)",
                }

            logger.info(f"[TemplateMatcher] 获取模板映射: {len(mappings)}个字段")
            return mappings

        except Exception as e:
            logger.error(f"[TemplateMatcher] 获取模板映射失败: {e}", exc_info=True)
            return {}

    async def apply_template_to_columns(
        self, template: FieldMappingTemplate, columns: List[str]
    ) -> Dict[str, Dict]:
        """
        应用模板到列(匹配列名,v4.18.2异步支持)

        支持:
        - 精确匹配
        - 模糊匹配(去除空格、特殊字符)

        Args:
            template: 模板对象
            columns: 列名列表

        Returns:
            {column: {standard_field, confidence, method, reason}}
        """
        import re

        try:
            # [*] v4.18.2:获取模板映射(异步)
            template_mappings = await self.get_template_mappings(template.id)

            # 应用到列
            result = {}
            for col in columns:
                matched = False

                # 1. 精确匹配
                if col in template_mappings:
                    result[col] = template_mappings[col]
                    result[col]["reason"] = f"模板: {template.template_name}"
                    matched = True
                else:
                    # 2. 模糊匹配(去除空格、特殊字符)
                    col_normalized = re.sub(r"[\s_\-()()]", "", col.lower())
                    for template_col, mapping in template_mappings.items():
                        template_col_normalized = re.sub(
                            r"[\s_\-()()]", "", template_col.lower()
                        )
                        if col_normalized == template_col_normalized:
                            result[col] = mapping.copy()
                            result[col][
                                "reason"
                            ] = f"模板: {template.template_name} (模糊匹配)"
                            matched = True
                            break

                if not matched:
                    # 未匹配的列不强制映射(由AI建议兜底)
                    pass

            logger.info(
                f"[TemplateMatcher] 应用模板: {template.template_name}, "
                f"匹配 {len(result)}/{len(columns)} 个字段"
            )

            return result

        except Exception as e:
            logger.error(f"[TemplateMatcher] 应用模板失败: {e}", exc_info=True)
            return {}

    async def get_template_coverage(self, platform: str = None) -> Dict[str, Any]:
        """
        获取模板覆盖度统计(v4.18.2异步支持)

        返回:
        - total_combinations: 总的域×粒度组合数
        - covered_combinations: 有模板覆盖的组合数
        - coverage_percentage: 覆盖率百分比
        - missing_combinations: 缺少模板的组合列表
        """
        try:
            from modules.core.db import CatalogFile

            # 查询所有唯一的域×粒度组合(从catalog_files)
            stmt = (
                select(CatalogFile.data_domain, CatalogFile.granularity)
                .where(CatalogFile.status == "pending")  # 只统计待处理的
                .distinct()
            )

            if platform:
                stmt = stmt.where(CatalogFile.platform_code == platform)

            # [*] v4.18.2:支持异步会话
            result = await self.db.execute(stmt)
            all_combinations = result.all()

            total = len(all_combinations)

            # 查询有模板的组合
            covered = []
            missing = []

            for domain, granularity in all_combinations:
                if granularity is None:
                    continue  # 跳过无粒度的文件

                # [*] v4.18.2:异步调用
                template = await self.find_best_template(
                    platform or "shopee", domain, granularity  # 如果未指定,默认shopee
                )

                if template:
                    covered.append((domain, granularity))
                else:
                    missing.append((domain, granularity))

            coverage_percentage = (len(covered) / total * 100) if total > 0 else 0

            return {
                "total_combinations": total,
                "covered_combinations": len(covered),
                "coverage_percentage": round(coverage_percentage, 1),
                "missing_combinations": [
                    {"domain": d, "granularity": g} for d, g in missing
                ],
            }

        except Exception as e:
            logger.error(f"[TemplateMatcher] 获取模板覆盖度失败: {e}", exc_info=True)
            return {
                "total_combinations": 0,
                "covered_combinations": 0,
                "coverage_percentage": 0,
                "missing_combinations": [],
            }

    async def detect_header_changes(
        self,
        template_id: int,
        current_columns: List[str],
        account: Optional[str] = None,
        *,
        sample_rows: Optional[List[Dict[str, Any]]] = None,
        companion_date_from: Any = None,
        companion_date_to: Any = None,
        field_parse_rules: Optional[List[Dict[str, Any]]] = None,
        core_fields: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        检测表头变化(v4.14.0安全版本,v4.18.2异步支持)

        [WARN] 安全原则:不进行相似度匹配,任何变化都需要用户手动确认

        比较当前表头与模板表头,检测:
        - 新增字段(current中有,template中没有)
        - 删除字段(template中有,current中没有)
        - 字段顺序变化(通过完全匹配检查)

        [*] 批次 B: 同时做**值形态**体检。
        表头一模一样也可能出事 —— 平台把日期从 ``01/10/2026`` 改成
        ``01-10-2026``, 列名一个没动, 但模板声明的格式已经解不出来了。
        这里用样本行试解析一遍声明的日期格式, 解不出来 ⇒ ``format_drift``。

        Args:
            template_id: 模板ID
            current_columns: 当前表头字段列表
            sample_rows: 文件样本行(用于值形态体检; 没有则跳过该维度)
            companion_date_from/to: 文件期间(用于 auto 模式消歧)
            field_parse_rules: 生效的日期解析规则; 缺省用模板自身的

        Returns:
            {
                'detected': bool,
                'added_fields': List[str],
                'removed_fields': List[str],
                'match_rate': float,  # 匹配率(0-100)
                'is_exact_match': bool,  # 是否完全匹配(字段名和顺序都一致)
                'template_columns': List[str],  # 模板字段列表(供前端对比)
                'current_columns': List[str]  # 当前字段列表(供前端对比)
            }
        """
        try:
            # [*] v4.18.2:支持异步会话
            result = await self.db.execute(
                select(FieldMappingTemplate).where(
                    FieldMappingTemplate.id == template_id
                )
            )
            template = result.scalar_one_or_none()

            if not template:
                logger.warning(f"[HeaderChange] 模板不存在: ID={template_id}")
                return {
                    "detected": True,  # 模板不存在视为变化
                    "added_fields": [],
                    "removed_fields": [],
                    "match_rate": 0.0,
                    "is_exact_match": False,
                    "template_columns": [],
                    "current_columns": current_columns,
                    "format_drift": False,
                    "value_shape": {
                        "checked_rules": 0,
                        "checked_values": 0,
                        "format_drift": False,
                        "error_codes": [],
                        "issues": [],
                    },
                }

            template_columns = template.header_columns or []

            # [*] v4.15.0新增:货币代码归一化
            # 在比较前,将字段名归一化(移除货币代码部分)
            normalized_current = self._normalize_headers_for_compare(
                template.data_domain,
                current_columns,
            )
            normalized_template = self._normalize_headers_for_compare(
                template.data_domain,
                template_columns,
            )

            semantic_current = self._apply_header_aliases(
                template.platform,
                template.data_domain,
                template.granularity or "",
                normalized_current,
                account=account,
            )
            semantic_template = self._apply_header_aliases(
                template.platform,
                template.data_domain,
                template.granularity or "",
                normalized_template,
                account=account,
            )

            # 使用归一化后的字段名进行比较
            current_set = set(normalized_current)
            template_set = set(normalized_template)
            semantic_current_set = set(semantic_current)
            semantic_template_set = set(semantic_template)

            # 1. 检测新增字段(current中有,template中没有)
            added_fields = list(current_set - template_set)

            # 2. 检测删除字段(template中有,current中没有)
            removed_fields = list(template_set - current_set)
            normalized_added_fields = list(semantic_current_set - semantic_template_set)
            normalized_removed_fields = list(
                semantic_template_set - semantic_current_set
            )
            # [*] L1 只产出**事实**(列差异 / 顺序 / 值形态), **不下结论**。
            #
            # 「什么算漂移、什么算阻断」由 L3 唯一判定入口给:
            # ``backend/services/data_sync_status_semantics.classify_drift``。
            #
            # 历史: 这里曾调用 ``_classify_header_changes`` 自行把列差异分成
            # blocking / non_blocking, 并且只对 ``shopee/orders/monthly``
            # 开了「新增列不阻断」的口子(2026-06-17 救火补丁)⇒
            # TikTok 订单多一列照样被卡住(2026-11-13 实测)。
            # ⇒ 判定权已整体上移到 L3, 本函数不再有平台特判。
            # [*] 批次 B: 值形态体检(列名没变, 但值的形态变了)。
            #
            # 用样本行试解析模板声明的日期格式 —— 解不出来就是 ``format_drift``。
            # 没有样本行时不判(不误伤)。
            effective_rules = (
                field_parse_rules
                if field_parse_rules is not None
                else (template.field_parse_rules or [])
            )
            value_shape_report = evaluate_date_value_shape(
                effective_rules,
                sample_rows,
                companion_date_from=companion_date_from,
                companion_date_to=companion_date_to,
            )
            value_shape = value_shape_report.to_dict()
            format_drift = bool(value_shape_report.format_drift)
            format_drift_columns = [
                issue["source_column"]
                for issue in value_shape.get("issues") or []
                if issue.get("error_code") in DATE_ERROR_FORMAT_DRIFT_CODES
            ]
            # [*] 批次 F-4(API-6): 「已确认的新列」忽略清单 ——
            #     用户勾过的列不再算成新增噪音, 也不再阻断
            #     (用户明说「这列我不要」⇒ 它不落库是用户的选择)。
            ignored_extra_fields = list(
                getattr(template, "ignored_extra_fields", None) or []
            )
            semantic_contract = await SemanticFieldContractService(self.db).evaluate(
                platform=template.platform,
                data_domain=template.data_domain,
                granularity=template.granularity,
                sub_domain=template.sub_domain,
                header_bindings=template.header_bindings or [],
                current_columns=current_columns,
                template_columns=template_columns,
                # [*] 批次 E(E-5): 模板级核心字段清单的 required 一并参与阻断判定。
                core_fields=core_fields,
                ignored_extra_fields=ignored_extra_fields,
            )
            semantic_summary = semantic_contract.to_dict()
            # [*] 判定权上移到 L3(``classify_drift``) —— 这里不再合并
            #     blocking / non_blocking, 避免同一事实出现第二份定义。

            # [*] v4.14.0安全版本:移除相似度匹配逻辑
            # 任何字段名变化都需要用户手动确认
            # [*] v4.15.0更新:但货币代码差异不视为变化(已通过归一化处理)

            # 3. 计算匹配率(基于归一化后的字段集合的交集)
            matched_fields = len(current_set & template_set)
            total_fields = len(current_set | template_set)
            match_rate = (
                (matched_fields / total_fields * 100) if total_fields > 0 else 0.0
            )

            # 4. 检查是否完全匹配(归一化后的字段名和顺序都一致)
            is_exact_match = (
                len(added_fields) == 0
                and len(removed_fields) == 0
                and normalized_current
                == normalized_template  # 顺序也要一致(基于归一化后的字段名)
            )
            is_semantic_match = (
                len(normalized_added_fields) == 0
                and len(normalized_removed_fields) == 0
                and semantic_current == semantic_template
            )

            # 5. 判断是否检测到变化
            # [WARN] 安全原则:任何变化(新增、删除、顺序变化)都视为变化
            detected = not is_exact_match

            # [*] L3: **唯一**的漂移判定入口。
            #
            # 业务口径(见 ``data_sync_status_semantics.classify_drift`` 文档):
            #   多一列 ⇒ 不阻断(原始数据完整保留, 映射按列名走);
            #   少了必填字段 / 值形态变了 ⇒ 阻断。
            #
            # 这里把 L1(事实) + L2(语义事实)交给 L3, 自己不下结论。
            drift_decision = classify_drift(
                added_fields=added_fields,
                removed_fields=removed_fields,
                format_drift_columns=format_drift_columns,
                is_exact_match=is_exact_match,
                is_semantic_match=is_semantic_match,
                has_semantic_contract=semantic_contract.has_contract,
                missing_required_keys=semantic_contract.missing_required_keys,
                missing_optional_keys=semantic_contract.missing_optional_keys,
                optional_removed_raw_fields=(
                    semantic_contract.optional_removed_raw_fields
                ),
                blocking_removed_raw_fields=(
                    semantic_contract.blocking_removed_raw_fields
                ),
                unmapped_removed_raw_fields=(
                    semantic_contract.unmapped_removed_raw_fields
                ),
                alias_rescued_removed_raw_fields=(
                    semantic_contract.alias_rescued_removed_raw_fields
                ),
                optional_raw_fields=self._optional_raw_fields(core_fields),
                confirmed_extra_fields=ignored_extra_fields,
            )
            change_classification = {
                "blocking_changes": list(drift_decision.blocking_changes),
                "non_blocking_changes": list(drift_decision.non_blocking_changes),
            }

            result_dict = {
                "detected": detected,
                "added_fields": added_fields,
                "removed_fields": removed_fields,
                "match_rate": round(match_rate, 1),
                "is_exact_match": is_exact_match,
                "is_semantic_match": is_semantic_match,
                "template_columns": template_columns,  # 返回原始模板字段列表(供前端对比,保留货币代码)
                "current_columns": current_columns,  # 返回原始当前字段列表(供前端对比,保留货币代码)
                "normalized_template_columns": normalized_template,  # [*] v4.15.0新增:归一化后的模板字段
                "normalized_current_columns": normalized_current,  # [*] v4.15.0新增:归一化后的当前字段
                "semantic_template_columns": semantic_template,
                "semantic_current_columns": semantic_current,
                "normalized_added_fields": normalized_added_fields,
                "normalized_removed_fields": normalized_removed_fields,
                "blocking_changes": change_classification["blocking_changes"],
                "non_blocking_changes": change_classification["non_blocking_changes"],
                # [*] L3 判定结论(下游不再自己拼结论, 直接取这里)
                "drift_decision": drift_decision.to_dict(),
                # [*] 用户确认过的新列(判定兜底路径要用)
                "confirmed_extra_fields": list(ignored_extra_fields),
                # [*] 批次 B: 值形态体检结果
                "format_drift": format_drift,
                "value_shape": value_shape,
                **semantic_summary,
            }

            if detected:
                logger.warning(
                    f"[HeaderChange] [WARN] 检测到表头变化: "
                    f"新增{len(added_fields)}个, 删除{len(removed_fields)}个, "
                    f"匹配率{match_rate:.1f}% - 需要用户手动确认"
                )

            return result_dict

        except Exception as e:
            logger.error(f"[HeaderChange] 检测表头变化失败: {e}", exc_info=True)
            return {
                "detected": True,  # 检测失败视为变化(安全策略)
                "added_fields": [],
                "removed_fields": [],
                "match_rate": 0.0,
                "is_exact_match": False,
                "template_columns": [],
                "current_columns": (
                    current_columns if "current_columns" in locals() else []
                ),
                # [*] 批次 B: 检测失败时**不**谎报格式漂移, 但形状保持一致。
                "format_drift": False,
                "value_shape": {
                    "checked_rules": 0,
                    "checked_values": 0,
                    "format_drift": False,
                    "error_codes": [],
                    "issues": [],
                },
            }


def get_template_matcher(db: AsyncSession) -> TemplateMatcher:
    """
    获取模板匹配器实例

    v4.18.2新增:支持异步会话(AsyncSession)
    v4.19.0更新:移除同步/异步双模式支持,统一为异步架构
    """
    return TemplateMatcher(db)
