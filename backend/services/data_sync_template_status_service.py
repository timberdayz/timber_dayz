from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.exc import OperationalError

from modules.core.db import CatalogFile, FieldMappingTemplate
from backend.services.template_contract_service import (
    describe_contract_baseline,
    is_contract_baseline_valid,
    read_template_contract,
    resolve_contract_template,
)
from backend.services.template_family_service import get_template_resolver
from backend.services.template_matcher import get_template_matcher
from backend.services.data_sync_status_semantics import (
    GOVERNANCE_STATUS_BREAKING_DRIFT,
    GOVERNANCE_STATUS_MISSING_FAMILY,
    GOVERNANCE_STATUS_MISSING_VARIANT,
    GOVERNANCE_STATUS_NON_BREAKING_DRIFT,
    GOVERNANCE_STATUS_READY,
    TEMPLATE_BASELINE_CONTRACT,
    TEMPLATE_BASELINE_CROSS_FAMILY_VARIANT,
    TEMPLATE_BASELINE_CURRENT,
    TEMPLATE_BASELINE_NONE,
    TEMPLATE_STATUS_ALIAS_ONLY,
    TEMPLATE_STATUS_MISSING,
    TEMPLATE_STATUS_MISSING_VARIANT,
    TEMPLATE_STATUS_READY,
    TEMPLATE_STATUS_UPDATE_REQUIRED,
)


# 漂移来源(SSOT)
# source_change : 文件结构与「自己的模板契约」不符 —— 源文件侧发生了变化
# template_upgrade: 文件与自己的契约一致, 只是当前已发布模板被我们升级过 —— 不是源文件问题
# unknown       : 没有可用契约(历史文件), 无法判定漂移来源
DRIFT_ORIGIN_SOURCE_CHANGE = "source_change"
DRIFT_ORIGIN_TEMPLATE_UPGRADE = "template_upgrade"
DRIFT_ORIGIN_UNKNOWN = "unknown"


class DataSyncTemplateStatusService:
    def __init__(self, db):
        self.db = db
        self.template_matcher = get_template_matcher(db)
        self.template_resolver = get_template_resolver(db)

    async def _load_legacy_template(self, template_id: Any) -> Optional[FieldMappingTemplate]:
        """按模板行 ID 取模板行(用于跨 family 接管时取被接管变体的模板)。"""
        if template_id is None:
            return None
        try:
            return await self.db.get(FieldMappingTemplate, int(template_id))
        except (TypeError, ValueError):
            return None

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
    ) -> Dict[str, Any]:
        resolver_result = None
        try:
            resolver_result = await self.template_resolver.resolve(
                platform=catalog_file.platform_code,
                data_domain=catalog_file.data_domain,
                granularity=catalog_file.granularity,
                sub_domain=catalog_file.sub_domain if catalog_file.sub_domain else None,
                header_row=header_row,
                header_columns=current_columns or [],
                sample_rows=sample_rows or [],
            )
        except OperationalError:
            resolver_result = None

        normalized_sub_domain = catalog_file.sub_domain if catalog_file.sub_domain else None
        # [*] 账号/地区维度: 不同地区的导出表头可能不同, 优先匹配账号专属模板
        normalized_account = (
            getattr(catalog_file, "account", None) or None
        )
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
        elif contract:
            candidate = await resolve_contract_template(self.db, contract)
            if candidate is not None and is_contract_baseline_valid(contract, candidate):
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
                current_template = published_template or candidate

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

        if not comparison_template:
            governance_status = (
                resolver_result.get(
                    "governance_status", GOVERNANCE_STATUS_MISSING_FAMILY
                )
                if resolver_result
                else GOVERNANCE_STATUS_MISSING_FAMILY
            )
            active_version = resolver_result.get("active_version") if resolver_result else None
            return {
                "template_status": (
                    TEMPLATE_STATUS_MISSING_VARIANT
                    if governance_status == GOVERNANCE_STATUS_MISSING_VARIANT
                    else TEMPLATE_STATUS_MISSING
                ),
                "governance_status": governance_status,
                "has_template": governance_status == "missing_variant",
                "template_name": active_version.get("template_name") if active_version else None,
                "template_header_row": None,
                "template_update_required": False,
                "update_reason": None,
                "error_code": "MISSING_VARIANT" if governance_status == "missing_variant" else "NO_TEMPLATE",
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
                "baseline_template_version": baseline_info.get("baseline_template_version"),
                "shadow_compare": resolver_result.get("shadow_compare") if resolver_result else None,
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
                "baseline_template_version": baseline_info.get("baseline_template_version"),
                "shadow_compare": resolver_result.get("shadow_compare") if resolver_result else None,
            }

        header_changes = await self.template_matcher.detect_header_changes(
            comparison_template.id,
            current_columns,
            account=normalized_account,
        )

        blocking_changes = header_changes.get("blocking_changes")
        if not isinstance(blocking_changes, list):
            blocking_changes = []
        non_blocking_changes = header_changes.get("non_blocking_changes")
        if not isinstance(non_blocking_changes, list):
            non_blocking_changes = []

        if header_changes.get("is_exact_match", False):
            status = TEMPLATE_STATUS_READY
            governance_status = GOVERNANCE_STATUS_READY
            should_auto_sync = True
            update_required = False
        elif header_changes.get("is_semantic_match", False) or (
            header_changes.get("detected", False)
            and not blocking_changes
            and bool(non_blocking_changes)
        ):
            status = TEMPLATE_STATUS_ALIAS_ONLY
            governance_status = GOVERNANCE_STATUS_NON_BREAKING_DRIFT
            should_auto_sync = True
            update_required = False
        else:
            status = TEMPLATE_STATUS_UPDATE_REQUIRED
            governance_status = GOVERNANCE_STATUS_BREAKING_DRIFT
            should_auto_sync = False
            update_required = True

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

        # [*] 契约是否已过时: 契约存在, 但实际解释这个文件的基准不是它 ——
        # 说明采集登记时按粒度选错了模板(导出格式不跟着粒度走), 需要修正。
        contract_stale = bool(
            contract
            and baseline_kind
            and baseline_kind != TEMPLATE_BASELINE_CONTRACT
        )

        return {
            "template_status": status,
            "governance_status": governance_status,
            "has_template": True,
            "template_name": comparison_template.template_name,
            "template_header_row": getattr(comparison_template, "header_row", None),
            "template_update_required": update_required,
            "update_reason": None if status in {"ready", "alias_only"} else "header_changed",
            "error_code": None if status in {"ready", "alias_only"} else "HEADER_CHANGED",
            "should_auto_sync": should_auto_sync,
            "exact_match": header_changes.get("is_exact_match", False),
            "semantic_match": header_changes.get("is_semantic_match", False),
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
            "contract_stale": contract_stale,
            "template_outdated": bool(baseline_info.get("template_outdated")),
            "baseline_template_id": baseline_info.get("baseline_template_id"),
            "baseline_template_version": baseline_info.get("baseline_template_version"),
            "baseline_valid": bool(baseline_info.get("baseline_valid")),
            "shadow_compare": resolver_result.get("shadow_compare") if resolver_result else None,
        }
