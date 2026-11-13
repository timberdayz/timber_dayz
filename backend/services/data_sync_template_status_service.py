from __future__ import annotations

from datetime import timezone
from typing import Any, Dict, Optional

from sqlalchemy.exc import OperationalError

from modules.core.db import CatalogFile, FieldMappingTemplate
from backend.services.template_contract_service import (
    contract_template_id,
    describe_contract_baseline,
    is_contract_baseline_valid,
    parse_contract_captured_at,
    read_template_contract,
)
from backend.services.template_family_service import get_template_resolver
from backend.services.template_matcher import get_template_matcher
from backend.services.data_sync_status_semantics import (
    GOVERNANCE_STATUS_BREAKING_DRIFT,
    GOVERNANCE_STATUS_FORMAT_DRIFT,
    GOVERNANCE_STATUS_MISSING_FAMILY,
    GOVERNANCE_STATUS_MISSING_VARIANT,
    GOVERNANCE_STATUS_NON_BREAKING_DRIFT,
    GOVERNANCE_STATUS_READY,
    TEMPLATE_BASELINE_CONTRACT,
    TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT,
    TEMPLATE_BASELINE_CURRENT,
    TEMPLATE_BASELINE_NONE,
    TEMPLATE_STATUS_ALIAS_ONLY,
    TEMPLATE_STATUS_FORMAT_DRIFT,
    TEMPLATE_STATUS_MISSING,
    TEMPLATE_STATUS_MISSING_VARIANT,
    TEMPLATE_STATUS_READY,
    TEMPLATE_STATUS_UPDATE_REQUIRED,
    classify_drift,
    governance_status_for,
)


# 漂移来源(SSOT)
# source_change : 文件结构与「自己的模板契约」不符 —— 源文件侧发生了变化
# template_upgrade: 文件与自己的契约一致, 只是当前已发布模板被我们升级过 —— 不是源文件问题
# unknown       : 没有可用契约(历史文件), 无法判定漂移来源
DRIFT_ORIGIN_SOURCE_CHANGE = "source_change"
DRIFT_ORIGIN_TEMPLATE_UPGRADE = "template_upgrade"
DRIFT_ORIGIN_UNKNOWN = "unknown"


# ── 契约状态(第 3 批 3.3) ───────────────────────────────────────────
#
# 「契约失效」以前与「从来没有契约」混为一谈:
# 契约指向的模板行被删 / 被原地改写 ⇒ 基准直接落到「当前已发布模板」,
# 历史文件被**静默**地用新模板解释, 没有留痕。
#
# 现在契约状态是**一等状态**, 三种取值互不重叠:
CONTRACT_STATUS_VALID = "valid"
CONTRACT_STATUS_INVALID = "invalid"
CONTRACT_STATUS_MISSING = "missing"


class DataSyncTemplateStatusService:
    def __init__(self, db):
        self.db = db
        self.template_matcher = get_template_matcher(db)
        self.template_resolver = get_template_resolver(db)

    async def _load_legacy_template(
        self, template_id: Any
    ) -> Optional[FieldMappingTemplate]:
        """按模板行 ID 取模板行(用于跨 family 接管时取被接管变体的模板)。"""
        if template_id is None:
            return None
        try:
            return await self.db.get(FieldMappingTemplate, int(template_id))
        except (TypeError, ValueError):
            return None

    async def _resolve_contract_candidate(
        self,
        contract: Optional[Dict[str, Any]],
    ) -> Optional[FieldMappingTemplate]:
        """取契约指向的模板行(用 ``db.get``, 命中会话 identity map, 不额外查询)。"""
        template_id = contract_template_id(contract)
        if template_id is None:
            return None
        try:
            return await self.db.get(FieldMappingTemplate, template_id)
        except Exception:  # noqa: BLE001 - 取不到就按「契约失效」处理
            return None

    async def _evaluate_contract_status(
        self,
        contract: Optional[Dict[str, Any]],
    ) -> tuple[str, Optional[str]]:
        """判定契约状态(第 3 批 3.3)。

        Returns:
            ``(contract_status, invalid_reason)``

        * ``valid``   契约指向的模板行还在, 且表头指纹仍然一致
        * ``invalid`` 模板行已被删除, 或被原地改写(``columns_hash`` 不匹配)
        * ``missing`` 文件上根本没有契约
        """
        if not isinstance(contract, dict) or not contract:
            return CONTRACT_STATUS_MISSING, None
        candidate = await self._resolve_contract_candidate(contract)
        if candidate is None:
            return (
                CONTRACT_STATUS_INVALID,
                "契约指向的模板行已不存在(模板被删除或未迁移), 已回退到当前已发布模板",
            )
        if not is_contract_baseline_valid(contract, candidate):
            return (
                CONTRACT_STATUS_INVALID,
                "契约记录的表头指纹与模板当前表头不一致(模板被原地改写), 已回退到当前已发布模板",
            )
        return CONTRACT_STATUS_VALID, None

    @staticmethod
    def _build_contract_signals(
        *,
        contract_status: str,
        contract_invalid_reason: Optional[str],
        contract_stale: bool,
        baseline_kind: str,
        comparison_template: Any,
    ) -> Dict[str, Any]:
        """契约相关信号(第 3 批 3.3)。

        契约失效时**必须**显式带上「已回退到当前模板」的标记 ——
        不允许静默回退(上层据此落库与提示)。
        """
        contract_fallback: Optional[Dict[str, Any]] = None
        if contract_status == CONTRACT_STATUS_INVALID:
            contract_fallback = {
                "applied": True,
                "reason": contract_invalid_reason,
                "fallback_template_id": getattr(comparison_template, "id", None),
                "fallback_template_name": getattr(
                    comparison_template, "template_name", None
                ),
                "fallback_kind": baseline_kind,
            }
        return {
            "contract_status": contract_status,
            "contract_invalid": contract_status == CONTRACT_STATUS_INVALID,
            "contract_stale": contract_stale,
            "contract_fallback": contract_fallback,
        }

    async def _resolve_same_format_published(
        self,
        *,
        catalog_file: CatalogFile,
        reference: Optional[FieldMappingTemplate],
        fallback: Optional[FieldMappingTemplate],
        normalized_sub_domain: Optional[str],
        normalized_account: Optional[str],
    ) -> Optional[FieldMappingTemplate]:
        """把「当前已发布模板」收敛到**与基准同格式**的那一版。

        [*] 批次 H(H-1): 同维度多格式并存后, 「当前已发布模板」不再等于
        「版本号最高的那个」—— 那可能是另一种格式。

        两种情形要分清
        --------------
        * **基准那一版仍然 published**(两种格式并存)⇒ 同格式的已发布模板
          就是它自己 ⇒ 「我们升级过模板」这个信号应当**不成立**
          (不是升级, 是并存);
        * **基准那一版已被归档**(新版把它顶掉了)⇒ 同格式**没有**已发布版本
          ⇒ 这一格式确实被取代了 ⇒ 仍用「当前已发布模板」做对照,
          「我们升级过模板」的信号照常成立。

        ⇒ 找不到同格式的已发布模板时, 退回 **fallback(当前已发布模板)**,
        而不是退回基准模板本身。
        """
        if fallback is None or reference is None:
            return fallback

        from backend.services.template_family_service import resolve_format_signature

        reference_signature = resolve_format_signature(reference)
        fallback_signature = resolve_format_signature(fallback)
        if not reference_signature or reference_signature == fallback_signature:
            return fallback

        same_format = await self.template_matcher.find_published_template_by_format(
            platform=catalog_file.platform_code,
            data_domain=catalog_file.data_domain,
            granularity=catalog_file.granularity,
            sub_domain=normalized_sub_domain,
            account=normalized_account,
            format_signature=reference_signature,
        )
        return same_format or fallback

    async def evaluate_catalog_file(
        self,
        catalog_file: CatalogFile,
        *,
        template=None,
        current_columns: Optional[list[str]] = None,
        sample_rows: Optional[list[dict[str, Any]]] = None,
        header_row: Optional[int] = None,
        takeover: Optional[Dict[str, Any]] = None,
        baseline_template_override: Optional[FieldMappingTemplate] = None,
        baseline_kind_override: Optional[str] = None,
        published_template: Optional[FieldMappingTemplate] = None,
    ) -> Dict[str, Any]:
        resolver_result = None
        normalized_sub_domain = (
            catalog_file.sub_domain if catalog_file.sub_domain else None
        )
        # [*] 账号/地区维度: 不同地区的导出表头可能不同, 优先匹配账号专属模板
        normalized_account = getattr(catalog_file, "account", None) or None
        try:
            resolver_result = await self.template_resolver.resolve(
                platform=catalog_file.platform_code,
                data_domain=catalog_file.data_domain,
                granularity=catalog_file.granularity,
                sub_domain=normalized_sub_domain,
                # [*] 必须传 account —— 少了它, resolver 会用「无账号」的家族,
                #     与入库判定(走模板匹配)对同一个文件给出相反结论。
                account=normalized_account,
                header_row=header_row,
                header_columns=current_columns or [],
                sample_rows=sample_rows or [],
                # [*] 批次 A 回归修复: 文件期间必须一起传下去,
                #     否则 auto_by_companion_period 的变体永远判成「解不出样本」。
                file_date_from=getattr(catalog_file, "date_from", None),
                file_date_to=getattr(catalog_file, "date_to", None),
            )
        except OperationalError:
            resolver_result = None

        template = template or await self.template_matcher.find_best_template(
            platform=catalog_file.platform_code,
            data_domain=catalog_file.data_domain,
            granularity=catalog_file.granularity,
            sub_domain=normalized_sub_domain,
            account=normalized_account,
        )

        # [*] 模板契约(SSOT): 文件自带的契约决定「拿哪一版模板做基准」。
        #
        # 没有契约的历史文件只能拿「当前最新已发布模板」当基准 ——
        # 于是我们每升级一次模板, 历史上按旧模板采集的文件全被判成结构漂移,
        # 而且无法区分「源文件变了」与「我们自己升级了模板」。
        #
        # 有契约时: 基准 = 契约指向的那一版模板(采集当时生效的版本)。
        contract = read_template_contract(catalog_file)
        baseline_template = None
        baseline_kind = TEMPLATE_BASELINE_CURRENT
        current_template = template
        # [*] 契约状态(第 3 批 3.3): valid / invalid / missing 三者互不重叠
        contract_status, contract_invalid_reason = (
            await self._evaluate_contract_status(contract)
            if contract
            else (CONTRACT_STATUS_MISSING, None)
        )

        # [D7] 跨 family 接管: 由**其他粒度**的变体解释本文件。
        #
        # 场景: tiktok 商品导出实际只有一种表结构(176 列), 但模板按粒度分别登记,
        # monthly 的模板停留在旧版 38 列 -> monthly 的文件在 family 27 里
        # 匹配不到任何变体 -> 被判结构漂移 -> 永不自动入库。
        # 跨 family 接管让它由 family 23 的 176 列变体解释, 匹配率 100%。
        #
        # 来源优先级: 调用方显式传入的接管决定(表头行感知发现) > resolver 兜底命中。
        takeover_report = takeover or (
            resolver_result.get("takeover") if resolver_result else None
        )

        if baseline_kind_override is not None:
            # [*] 调用方(有文件访问能力的那一层)已经拍板了比较基准 ——
            # 它读得到真实表头, 也知道表头行, 所以以它的判定为准。
            #
            # ``baseline_kind_override`` 为 "current" 时基准模板是 None,
            # 表示「既没有可用契约, 也没有接管」—— 这一点必须由调用方说了算,
            # 因为契约是否**仍然解释得了文件**, 只有读到表头才知道。
            baseline_template = baseline_template_override
            baseline_kind = baseline_kind_override

            # [*] 契约基准: 额外拿「当前已发布模板」做对照。
            #
            # 它有两个用途, 缺一不可:
            #   1. 识别「我们自己升级过模板」(template_outdated) —— D7 的核心语义;
            #      少了它, ``drift_origin`` 永远算成 ``source_change``,
            #      治理面板就分不清「源文件变了」与「我们升级了模板」。
            #   2. 契约失效时的**补救路径**(见文件末尾的契约晋升)。
            if baseline_kind == TEMPLATE_BASELINE_CONTRACT:
                if published_template is None:
                    published_template = await self.template_matcher.find_best_template(
                        platform=catalog_file.platform_code,
                        data_domain=catalog_file.data_domain,
                        granularity=catalog_file.granularity,
                        sub_domain=normalized_sub_domain,
                        account=normalized_account,
                    )
                # [*] 批次 H(H-1): 「当前模板」必须限定在**同格式**内。
                #
                #     同维度多格式并存之后, 维度里最新的已发布模板可能是
                #     **另一种格式**(平台改过导出格式)。
                #     拿它跟契约比, 会把「另一种格式并存」误报成
                #     「我们升级过模板」—— 治理面板上就会出现
                #     「文件按 v3 采集, 当前已发布模板为 v12」这种看不懂的话。
                published_template = await self._resolve_same_format_published(
                    catalog_file=catalog_file,
                    reference=baseline_template,
                    fallback=published_template,
                    normalized_sub_domain=normalized_sub_domain,
                    normalized_account=normalized_account,
                )
                if published_template is not None:
                    current_template = published_template
        elif contract:
            candidate = await self._resolve_contract_candidate(contract)
            if candidate is not None and contract_status == CONTRACT_STATUS_VALID:
                baseline_template = candidate
                baseline_kind = TEMPLATE_BASELINE_CONTRACT
                # 当前已发布模板: 用来识别「我们自己升级过模板」这种情况
                published_template = await self.template_matcher.find_best_template(
                    platform=catalog_file.platform_code,
                    data_domain=catalog_file.data_domain,
                    granularity=catalog_file.granularity,
                    sub_domain=normalized_sub_domain,
                    account=normalized_account,
                )
                # [*] 批次 H(H-1): 同格式(与上面那条分支同一把尺子)。
                published_template = await self._resolve_same_format_published(
                    catalog_file=catalog_file,
                    reference=candidate,
                    fallback=published_template,
                    normalized_sub_domain=normalized_sub_domain,
                    normalized_account=normalized_account,
                )
                current_template = published_template or candidate
            # [*] 契约失效(invalid)⇒ **不再无声回退**:
            #     基准落到「当前已发布模板」, 但返回结构里会带上
            #     contract_status=invalid + contract_fallback 标记(见文件末尾)。

        if baseline_template is None and takeover_report:
            takeover_template = await self._load_legacy_template(
                takeover_report.get("source_legacy_template_id")
            )
            if takeover_template is not None:
                baseline_template = takeover_template
                baseline_kind = TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT

        baseline_info = describe_contract_baseline(contract, current_template)

        # [D7] 比较基准: 契约 > 跨 family 接管 > 当前已发布模板
        comparison_template = baseline_template or template

        # [*] 契约是否已过时: 契约存在, 但实际解释这个文件的基准不是它 ——
        #     说明采集登记时按粒度选错了模板(导出格式不跟着粒度走), 需要修正。
        contract_stale = bool(
            contract and baseline_kind and baseline_kind != TEMPLATE_BASELINE_CONTRACT
        )

        # [*] 契约信号(第 3 批 3.3): 契约失效必须**显式**留痕, 不允许无声回退
        contract_signals = self._build_contract_signals(
            contract_status=contract_status,
            contract_invalid_reason=contract_invalid_reason,
            contract_stale=contract_stale,
            baseline_kind=baseline_kind,
            comparison_template=comparison_template,
        )

        if not comparison_template:
            governance_status = (
                resolver_result.get(
                    "governance_status", GOVERNANCE_STATUS_MISSING_FAMILY
                )
                if resolver_result
                else GOVERNANCE_STATUS_MISSING_FAMILY
            )
            active_version = (
                resolver_result.get("active_version") if resolver_result else None
            )
            return {
                "template_status": (
                    TEMPLATE_STATUS_MISSING_VARIANT
                    if governance_status == GOVERNANCE_STATUS_MISSING_VARIANT
                    else TEMPLATE_STATUS_MISSING
                ),
                "governance_status": governance_status,
                "has_template": governance_status == "missing_variant",
                "template_name": (
                    active_version.get("template_name") if active_version else None
                ),
                "template_header_row": None,
                "template_update_required": False,
                "update_reason": None,
                "error_code": (
                    "MISSING_VARIANT"
                    if governance_status == "missing_variant"
                    else "NO_TEMPLATE"
                ),
                "should_auto_sync": False,
                "exact_match": False,
                "semantic_match": False,
                "drift_origin": None,
                "template_baseline": (
                    baseline_kind
                    if baseline_template is not None
                    else TEMPLATE_BASELINE_NONE
                ),
                "takeover": takeover_report,
                "template_outdated": False,
                "baseline_template_id": baseline_info.get("baseline_template_id"),
                "baseline_template_version": baseline_info.get(
                    "baseline_template_version"
                ),
                "shadow_compare": (
                    resolver_result.get("shadow_compare") if resolver_result else None
                ),
                **contract_signals,
            }

        if current_columns is None:
            return {
                "template_status": TEMPLATE_STATUS_READY,
                "governance_status": GOVERNANCE_STATUS_READY,
                "has_template": True,
                "template_name": comparison_template.template_name,
                "template_header_row": getattr(comparison_template, "header_row", None),
                "template_update_required": False,
                "update_reason": None,
                "error_code": None,
                "should_auto_sync": True,
                "exact_match": True,
                "semantic_match": True,
                "drift_origin": None,
                "template_baseline": (
                    baseline_kind
                    if baseline_template is not None
                    else TEMPLATE_BASELINE_CURRENT
                ),
                "takeover": takeover_report,
                "template_outdated": bool(baseline_info.get("template_outdated")),
                "baseline_template_id": baseline_info.get("baseline_template_id"),
                "baseline_template_version": baseline_info.get(
                    "baseline_template_version"
                ),
                "shadow_compare": (
                    resolver_result.get("shadow_compare") if resolver_result else None
                ),
                **contract_signals,
            }

        # [*] 批次 B: 值形态体检用的解析规则。
        #
        # 用**生效**的那一份(变体优先) —— 入库时真正被消费的是变体的规则,
        # 拿 legacy 模板的规则去体检, 体检的就不是真正会失败的那份配置。
        effective_parse_rules = list(
            (resolver_result or {}).get("field_parse_rules") or []
        ) or list(getattr(comparison_template, "field_parse_rules", None) or [])

        header_changes = await self.template_matcher.detect_header_changes(
            comparison_template.id,
            current_columns,
            account=normalized_account,
            sample_rows=sample_rows,
            companion_date_from=getattr(catalog_file, "date_from", None),
            companion_date_to=getattr(catalog_file, "date_to", None),
            field_parse_rules=effective_parse_rules,
        )

        blocking_changes = header_changes.get("blocking_changes")
        if not isinstance(blocking_changes, list):
            blocking_changes = []
        non_blocking_changes = header_changes.get("non_blocking_changes")
        if not isinstance(non_blocking_changes, list):
            non_blocking_changes = []

        # [*] 批次 B: 值形态漂移优先于「精确匹配」。
        #
        # 表头一个字段都没变, 但日期值从 ``01/10/2026`` 变成了 ``01-10/2026`` ——
        # 这时候 ``is_exact_match`` 是 True, 但这份文件入库**必然**整份失败。
        # 所以先判 format_drift, 不要被「精确匹配」盖过去。
        format_drift = bool(header_changes.get("format_drift", False))

        # [*] 判定结论一律来自 L3 唯一入口(``classify_drift``)——
        #     本服务只做「选基准 → 跑 L1/L2 → 取结论」, **不再自己拼状态**。
        #
        # 历史: 这里曾有一份自己的分支树(ready / alias_only / update_required),
        # 与 ``template_matcher._classify_header_changes``、语义契约层各算一套
        # ⇒ 同一事实三份定义 ⇒ Shopee 订单月报只能靠平台特判打补丁,
        #    TikTok 订单多一列照样被卡住(2026-11-13 实测)。
        decision = header_changes.get("drift_decision")
        if not isinstance(decision, dict) or not decision.get("template_status"):
            # 兜底: 异常路径没有结论 ⇒ 用已有事实重算一次, 不猜。
            decision = classify_drift(
                added_fields=header_changes.get("added_fields") or [],
                removed_fields=header_changes.get("removed_fields") or [],
                is_exact_match=bool(header_changes.get("is_exact_match", False)),
                is_semantic_match=bool(header_changes.get("is_semantic_match", False)),
                has_semantic_contract=bool(
                    header_changes.get("has_semantic_contract", False)
                ),
                missing_required_keys=(
                    header_changes.get("missing_required_keys") or []
                ),
                missing_optional_keys=(
                    header_changes.get("missing_optional_keys") or []
                ),
                confirmed_extra_fields=(
                    header_changes.get("confirmed_extra_fields") or []
                ),
            ).to_dict()

        status = str(decision.get("template_status") or TEMPLATE_STATUS_READY)
        governance_status = str(
            decision.get("governance_status") or governance_status_for(status)
        )
        should_auto_sync = not bool(decision.get("is_blocking", False))
        update_required = bool(decision.get("is_blocking", False))
        blocking_changes = list(decision.get("blocking_changes") or [])
        non_blocking_changes = list(decision.get("non_blocking_changes") or [])
        format_drift = status == TEMPLATE_STATUS_FORMAT_DRIFT

        # [*] 漂移来源: 回答「为什么对不上」
        if update_required:
            drift_origin = (
                DRIFT_ORIGIN_SOURCE_CHANGE
                if (baseline_template is not None or contract)
                else DRIFT_ORIGIN_UNKNOWN
            )
        else:
            drift_origin = (
                DRIFT_ORIGIN_TEMPLATE_UPGRADE
                if baseline_info.get("template_outdated")
                else None
            )

        # [*] 契约失效: 契约基准已经解释不了这个文件, 而当前已发布模板可以。
        #
        # 契约保证的是「采集**当时**那一版模板在解释这个文件」, 而不是
        # 「那一版模板至今仍能解释它」。当源文件结构**先于**模板发生变化时,
        # 契约指向的模板从此**不可能**再解释这个文件 ⇒ 判定永远停在结构漂移,
        # 用户唯一能做的补救(把新字段补进模板并发布新版本)**完全不产生效果**。
        #
        # 实测(tiktok/analytics/monthly, 2026-10-29): 文件 29 列(含「商品卡 GMV」),
        # 契约指向 v6(28 列) ⇒ 永久漂移; 用户发布 v8(29 列, 与文件 exact match)
        # 后**仍然**永久漂移 —— 因为契约没变, 用户做对了却看不到任何效果。
        #
        # 所以: 契约基准判出结构漂移 = 证明契约已不是该文件的正确解释;
        # 此时唯一还能修复的路径就是「当前已发布模板」(用户能改的那一版)。
        #   * 当前已发布模板能解释 -> 漂移其实是被模板升级解决的, 放行,
        #     并给出 ``contract_promotion`` 信号 —— 由落库链路把契约改写掉,
        #     否则契约会继续把文件钉在旧模板上, 下一轮重检又被打回。
        #   * 当前已发布模板也解释不了 -> 是源文件结构真变了, 保持「待更新」,
        #     等人工更新模板 —— 与修复前结论一致, 绝不误放行。
        #
        # [*] 「事后追平」判据(D7 的既有设计不能被破坏)
        #
        # 光看「当前已发布模板能解释文件」是不够的 —— 那会把「我们顺手升级了模板」
        # 也当成追平, 于是历史文件被悄悄改用新版(D7 明确禁止)。
        # 两者在数据上完全同构(旧契约的列 + 新模板多一列), 唯一能区分的是**时序**:
        #
        #   * 当前已发布模板的诞生时刻 **晚于** 契约的采集时刻
        #     => 这一版模板是在文件登记**之后**才存在的, 不可能是「登记时那一版」,
        #        它只能是**为这个文件而追平**的 => 放行
        #   * 当前已发布模板的诞生时刻 **早于或等于** 契约的采集时刻
        #     => 它就是文件登记时那一版, 文件相对它漂移就是**源文件结构变了**
        #        => 阻断, 等人工更新模板(D7 原语义不变)
        #
        # 拿不到时间戳(老契约没有 captured_at / 模板没有 created_at)时**保守阻断**。
        if (
            status == TEMPLATE_STATUS_UPDATE_REQUIRED
            and baseline_kind == TEMPLATE_BASELINE_CONTRACT
            and published_template is not None
            and baseline_template is not None
            and getattr(published_template, "id", None)
            != getattr(baseline_template, "id", None)
        ):
            contract_captured_at = parse_contract_captured_at(contract)
            published_created_at = getattr(published_template, "created_at", None)
            if published_created_at is not None and published_created_at.tzinfo is None:
                # SQLite / naive datetime 统一按 UTC 处理 —— 只比较相对先后
                published_created_at = published_created_at.replace(tzinfo=timezone.utc)
            is_after_the_fact = (
                contract_captured_at is not None
                and published_created_at is not None
                and published_created_at > contract_captured_at
            )
            if is_after_the_fact:
                promoted = await self.evaluate_catalog_file(
                    catalog_file,
                    template=published_template,
                    current_columns=current_columns,
                    sample_rows=sample_rows,
                    header_row=header_row,
                    takeover=takeover_report,
                    baseline_template_override=published_template,
                    baseline_kind_override=TEMPLATE_BASELINE_CURRENT,
                    published_template=published_template,
                )
                if promoted.get("template_status") in {
                    TEMPLATE_STATUS_READY,
                    TEMPLATE_STATUS_ALIAS_ONLY,
                }:
                    promoted["contract_promotion"] = {
                        "from_template_id": getattr(baseline_template, "id", None),
                        "from_template_version": getattr(
                            baseline_template, "version", None
                        ),
                        "from_template_name": getattr(
                            baseline_template, "template_name", None
                        ),
                        "to_template_id": getattr(published_template, "id", None),
                        "to_template_version": getattr(
                            published_template, "version", None
                        ),
                        "to_template_name": getattr(
                            published_template, "template_name", None
                        ),
                        "reason": "契约基准已解释不了该文件, 当前已发布模板可以",
                    }
                    return promoted

        return {
            "template_status": status,
            "governance_status": governance_status,
            "has_template": True,
            "template_id": getattr(comparison_template, "id", None),
            "template_version": getattr(comparison_template, "version", None),
            "template_name": comparison_template.template_name,
            "template_header_row": getattr(comparison_template, "header_row", None),
            "template_update_required": update_required,
            "update_reason": (
                "format_drift"
                if status == TEMPLATE_STATUS_FORMAT_DRIFT
                else (None if status in {"ready", "alias_only"} else "header_changed")
            ),
            "error_code": (
                "FORMAT_DRIFT"
                if status == TEMPLATE_STATUS_FORMAT_DRIFT
                else (None if status in {"ready", "alias_only"} else "HEADER_CHANGED")
            ),
            "should_auto_sync": should_auto_sync,
            "exact_match": header_changes.get("is_exact_match", False),
            "semantic_match": header_changes.get("is_semantic_match", False),
            # [*] 批次 B: 值形态漂移信号
            "format_drift": format_drift,
            "value_shape": header_changes.get("value_shape") or {},
            "semantic_contract_status": header_changes.get("semantic_contract_status"),
            "missing_required_keys": header_changes.get("missing_required_keys", []),
            "missing_optional_keys": header_changes.get("missing_optional_keys", []),
            "resolved_required_keys": header_changes.get("resolved_required_keys", []),
            "resolved_optional_keys": header_changes.get("resolved_optional_keys", []),
            "extra_raw_fields": header_changes.get("extra_raw_fields", []),
            "impact_descriptions": header_changes.get("impact_descriptions", []),
            "header_changes": header_changes,
            # [*] 契约相关信号
            "drift_origin": drift_origin,
            "template_baseline": (
                baseline_kind
                if baseline_template is not None
                else TEMPLATE_BASELINE_CURRENT
            ),
            "takeover": takeover_report,
            "template_outdated": bool(baseline_info.get("template_outdated")),
            "baseline_template_id": baseline_info.get("baseline_template_id"),
            "baseline_template_version": baseline_info.get("baseline_template_version"),
            "baseline_valid": bool(baseline_info.get("baseline_valid")),
            "shadow_compare": (
                resolver_result.get("shadow_compare") if resolver_result else None
            ),
            **contract_signals,
        }
