from backend.services.deduplication_fields_config import get_deduplication_fields


def test_services_template_dedup_fields_are_strengthened_with_shop_identity():
    fields = get_deduplication_fields(
        data_domain="services",
        template_fields=["日期"],
        sub_domain="ai_assistant",
    )

    assert "日期" in fields
    assert "platform_code" in fields
    assert "shop_id" in fields
    assert "sub_domain" in fields
