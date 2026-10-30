"""「源文件变动 → 工作台更新模板 → 正常同步」链路的**后端契约测试**。

为什么要有这个文件
------------------
第 1~4 批把模板保存口径和 hash 闸门收紧了，但验收标准是**业务语言**的：
「以后源文件有变动，我们去工作台把模板更新一下，就能正常同步」。

这条链路要通，需要同时满足：

1. **工作台认得出新源文件的列** —— 真实源文件的表头是 ``商品编号`` / ``ID`` /
   ``客服ID`` 这种平台自己的叫法，全局别名表认不出来，于是绑定停在 ``pending``；
2. **闸门能放行** —— 身份字段解析不到已确认语义键时，保存直接 400；
3. **hash 口径统一** —— 保存后的去重字段必须是**规范语义键**（``product_id``），
   而不是中文表头名（``商品编号``），否则同一笔业务在不同源文件下算出不同
   ``data_hash``，唯一约束撞不上，同一业务被插成多行。

本文件把这三条钉死，并且给「仍然过不了」的场景留下明确的失败原因，
避免以后再出现「按钮点不动、但不知道为什么」的黑箱。

⚠️ 护栏：``backend/tests/conftest.py`` 把 ``DATABASE_URL`` 重定向到一次性
PostgreSQL 容器；本文件不需要写库，但仍然在该隔离环境下运行。
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from backend.domains.data_platform.routers.field_mapping_templates import (
    _normalize_header_bindings,
)
from backend.services.deduplication_service import DeduplicationService
from backend.services.semantic_field_registry import (
    DOMAIN_COLUMN_SEMANTIC_OVERRIDES,
    infer_semantic_key_for_domain,
)
from backend.services.template_hash_policy import TemplateHashPolicyService
from backend.services.template_save_readiness_service import (
    TemplateSaveReadinessService,
    normalize_deduplication_fields_for_template,
)


def _bindings_by_raw(bindings: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {str(b.get("raw_name") or ""): b for b in bindings}


def _assess(
    *,
    data_domain: str,
    granularity: str | None,
    sub_domain: str | None,
    header_columns: List[str],
    header_bindings: List[Dict[str, Any]],
    deduplication_fields: List[str],
    field_parse_rules: List[Dict[str, Any]] | None = None,
):
    return TemplateSaveReadinessService().assess(
        data_domain=data_domain,
        granularity=granularity,
        sub_domain=sub_domain,
        header_columns=header_columns,
        header_bindings=header_bindings,
        deduplication_fields=deduplication_fields,
        field_parse_rules=list(field_parse_rules or []),
    )


class TestDomainScopedColumnRecognition:
    """域限定列名识别。"""

    def test_real_platform_headers_are_recognized(self):
        """真实源文件里的商品维度表头必须被认成身份键。"""
        bindings = _normalize_header_bindings(
            None,
            ["商品编号", "规格编号", "商品", "规格名称"],
            {},
            data_domain="products",
        )
        by_raw = _bindings_by_raw(bindings)

        assert by_raw["商品编号"]["semantic_key"] == "product_id"
        assert by_raw["规格编号"]["semantic_key"] == "sku_id"
        assert by_raw["商品"]["semantic_key"] == "product_name"
        # 规格名称是描述字段，不是身份键 —— 不能瞎认
        assert by_raw["规格名称"]["semantic_key"] is None

    def test_same_column_name_is_not_polluted_across_domains(self):
        """``ID`` 只在 products 域是商品 ID，换个域就不能认。"""
        assert (
            infer_semantic_key_for_domain("products", "ID") == "product_id"
        )
        assert infer_semantic_key_for_domain("orders", "ID") is None
        assert infer_semantic_key_for_domain("services", "ID") is None
        assert infer_semantic_key_for_domain("", "ID") is None

    def test_metric_like_columns_are_never_mapped_to_identity_keys(self):
        """状态类/名称类/货号类列名一律不映射，避免它们进 hash。"""
        for column in ("状态", "订单状态", "规格名称", "全球商品货号", "客服昵称"):
            for domain in ("products", "orders", "services"):
                assert (
                    infer_semantic_key_for_domain(domain, column) is None
                ), f"{domain}.{column} 不该被认成身份键"

    def test_domain_overrides_only_contain_canonical_semantic_keys(self):
        """表里的每个目标键都必须是真语义键，否则等于放行了一个假的身份键。"""
        from backend.services.semantic_field_registry import is_canonical_semantic_key

        for domain, mapping in DOMAIN_COLUMN_SEMANTIC_OVERRIDES.items():
            for column, semantic_key in mapping.items():
                assert is_canonical_semantic_key(semantic_key), (
                    f"{domain}.{column} -> {semantic_key} 不是规范语义键"
                )


class TestWorkbenchUpdateReachesSaveGate:
    """工作台更新模板 ⇒ 能过保存闸门。"""

    def test_products_template_update_passes_gate_and_normalizes_identity_keys(self):
        """Shopee 商品模板：源文件表头没变，重新进工作台更新后应当能保存，
        且去重字段被归一成语义键。

        源文件没有日期列 ⇒ 周期来自文件名 ⇒ 用户在工作台点一次「使用伴生周期」。
        """
        header_columns = ["商品编号", "商品", "规格编号", "规格名称", "销售额"]
        bindings = _normalize_header_bindings(
            None, header_columns, {}, data_domain="products"
        )
        # 模板里存的是历史写法（中文表头名）
        stored_fields = ["商品编号", "规格编号", "规格名称"]

        result = _assess(
            data_domain="products",
            granularity="monthly",
            sub_domain=None,
            header_columns=header_columns,
            header_bindings=bindings,
            deduplication_fields=["product_id", "sku_id"],
            field_parse_rules=[
                {
                    "target_field": "period_start_date",
                    "source_column": "__file_date_from__",
                    "value_kind": "single_date",
                    "strict": True,
                },
                {
                    "target_field": "period_end_date",
                    "source_column": "__file_date_to__",
                    "value_kind": "single_date",
                    "strict": True,
                },
            ],
        )
        assert result.can_save, result.blocking_errors

        normalized = normalize_deduplication_fields_for_template(
            ["商品编号", "规格编号"], bindings
        )
        assert normalized == ["product_id", "sku_id"]
        # 规格名称是描述字段，不该留在去重字段里
        assert "规格名称" not in normalized

    def test_orders_template_is_blocked_until_order_id_is_selected(self):
        """orders 域必须能定位到 order_id。

        历史模板的去重字段里没有订单号（只有状态和商品维度），
        此时闸门**必须**拦下 —— 否则同一订单的不同行会互相覆盖。
        """
        header_columns = ["订单编号", "订单状态", "产品ID", "平台SKU", "SKU ID"]
        bindings = _normalize_header_bindings(
            None, header_columns, {}, data_domain="orders"
        )
        by_raw = _bindings_by_raw(bindings)
        assert by_raw["订单编号"]["semantic_key"] == "order_id"

        blocked = _assess(
            data_domain="orders",
            granularity="monthly",
            sub_domain=None,
            header_columns=header_columns,
            header_bindings=bindings,
            deduplication_fields=["product_id", "platform_sku", "sku_id"],
        )
        assert not blocked.can_save
        missing = {g["key"] for g in blocked.hash_policy.missing_required_groups}
        assert "orders_identity" in missing

        fixed = _assess(
            data_domain="orders",
            granularity="monthly",
            sub_domain=None,
            header_columns=header_columns,
            header_bindings=bindings,
            deduplication_fields=["order_id", "product_id", "platform_sku", "sku_id"],
        )
        assert fixed.can_save, fixed.blocking_errors

    def test_shop_level_services_template_reports_missing_service_id(self):
        """店铺级服务报表（没有客服维度列）应当给出可执行的原因，
        而不是一句看不懂的报错。

        这是**业务口径问题**：源文件里根本没有 service_id，
        闸门要求它 ⇒ 只能由业务决定是否豁免（见方案文档 §3.5）。
        """
        header_columns = ["日期", "服务的访客", "已回答的问题", "好评比例"]
        bindings = _normalize_header_bindings(
            None, header_columns, {}, data_domain="services"
        )
        result = _assess(
            data_domain="services",
            granularity="monthly",
            sub_domain="ai_assistant",
            header_columns=header_columns,
            header_bindings=bindings,
            deduplication_fields=["metric_date"],
            field_parse_rules=[
                {
                    "target_field": "metric_date",
                    "source_column": "日期",
                    "value_kind": "single_date",
                    "strict": True,
                }
            ],
        )
        assert not result.can_save
        messages = " ".join(result.hash_policy.blocking_messages)
        assert "service_id" in messages

    def test_metric_field_in_deduplication_fields_is_rejected(self):
        """度量字段混进去重字段 ⇒ 必须被后端拦下（前端也会自动剔除，双保险）。"""
        header_columns = ["订单号", "订单状态", "产品ID"]
        bindings = _normalize_header_bindings(
            None, header_columns, {}, data_domain="orders"
        )
        result = _assess(
            data_domain="orders",
            granularity="monthly",
            sub_domain=None,
            header_columns=header_columns,
            header_bindings=bindings,
            deduplication_fields=["order_id", "订单状态"],
        )
        assert not result.can_save
        assert result.unresolved_deduplication_fields


class TestHashKeyIsIndependentOfSourceHeaderSpelling:
    """hash 口径统一 ⇒ 源文件表头写法不影响 ``data_hash``。"""

    def _hash(self, row: Dict[str, Any], fields: List[str], bindings) -> str:
        service = DeduplicationService.__new__(DeduplicationService)
        return service.calculate_data_hash(
            row,
            deduplication_fields=fields,
            header_bindings=bindings,
            scope_values={
                "platform_code": "shopee",
                "shop_id": "shop-1",
                "data_domain": "products",
                "granularity": "monthly",
                "sub_domain": None,
            },
        )

    def test_renamed_source_column_keeps_same_data_hash(self):
        """源文件把 ``商品编号`` 改名成 ``商品编号(新)``：

        改名列**不会**被自动认出（自动认列名靠的是别名表，改名就该由人确认），
        但只要用户在工作台把新列重新映射到 ``product_id``，
        模板的去重字段就仍然是 ``product_id`` ⇒ 同一笔业务 hash 不变。
        """
        old_bindings = _normalize_header_bindings(
            None, ["商品编号"], {}, data_domain="products"
        )
        # 用户在工作台显式重新映射（source=user）
        new_bindings = _normalize_header_bindings(
            [
                {
                    "raw_name": "商品编号(新)",
                    "semantic_key": "product_id",
                    "semantic_review_status": "confirmed_semantic",
                    "semantic_review_source": "user",
                }
            ],
            ["商品编号(新)"],
            {},
            data_domain="products",
        )
        assert _bindings_by_raw(new_bindings)["商品编号(新)"]["semantic_key"] == "product_id"

        old_hash = self._hash(
            {"商品编号": "P-1001"}, ["product_id"], old_bindings
        )
        new_hash = self._hash(
            {"商品编号(新)": "P-1001"}, ["product_id"], new_bindings
        )
        assert old_hash == new_hash

    def test_unnormalized_template_would_split_the_same_business(self):
        """对照：模板若仍存中文表头名，同一笔业务在两个源文件下 hash 不同
        ⇒ 唯一约束撞不上 ⇒ 同一业务被插成多行。"""
        old_bindings = _normalize_header_bindings(
            None, ["商品编号"], {}, data_domain="products"
        )
        new_bindings = _normalize_header_bindings(
            None, ["商品编号(新)"], {}, data_domain="products"
        )

        old_hash = self._hash({"商品编号": "P-1001"}, ["商品编号"], old_bindings)
        new_hash = self._hash({"商品编号(新)": "P-1001"}, ["商品编号(新)"], new_bindings)
        assert old_hash != new_hash


class TestInferredBindingDoesNotCreateFalseFamilyAgreement:
    """第 3 批修掉的「假一致」不能因为域限定推断而复发。"""

    def test_domain_inferred_binding_is_not_user_confirmed(self):
        """域限定列名推断出来的绑定，必须标记为 ``inferred`` 而不是 ``user``。"""
        bindings = _normalize_header_bindings(
            None, ["商品编号"], {}, data_domain="products"
        )
        binding = _bindings_by_raw(bindings)["商品编号"]
        assert binding["semantic_review_status"] == "confirmed_semantic"
        assert binding["semantic_review_source"] == "inferred"

    def test_family_comparison_ignores_inferred_bindings(self):
        """家族 hash 口径比较只认用户确认过的绑定。"""
        from backend.domains.data_platform.routers.field_mapping_templates import (
            _binding_lookup_by_source,
        )

        inferred = _normalize_header_bindings(
            None, ["商品编号"], {}, data_domain="products"
        )
        assert _binding_lookup_by_source(inferred) == {}

        user_confirmed = [
            {**inferred[0], "semantic_review_source": "user"},
        ]
        assert _binding_lookup_by_source(user_confirmed) == {
            "商品编号": "product_id",
        }


class TestHashPolicyRequirementGroups:
    """域级必需身份键的口径（闸门的业务依据）。"""

    @pytest.mark.parametrize(
        ("data_domain", "granularity", "expected_keys"),
        [
            ("products", "daily", {"products_identity", "products_metric_date"}),
            ("products", "monthly", {"products_identity", "products_period_date"}),
            ("orders", "monthly", {"orders_identity"}),
            ("services", "monthly", {"services_identity", "services_date"}),
        ],
    )
    def test_required_groups_are_stable(
        self, data_domain: str, granularity: str, expected_keys: set[str]
    ):
        service = TemplateHashPolicyService()
        result = service.validate(
            data_domain=data_domain,
            granularity=granularity,
            sub_domain=None,
            deduplication_fields=[],
            header_bindings=[],
            field_parse_rules=[],
        )
        assert {group["key"] for group in result.requirement_groups} == expected_keys
