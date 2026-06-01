from backend.schemas.field_mapping_template import TemplateVariantCreateContextResponse


def test_template_variant_create_context_response_schema_builds():
    schema = TemplateVariantCreateContextResponse.model_json_schema()

    assert "TemplateFamilyListItem" in schema.get("$defs", {})
    assert "TemplateVersionListItem" in schema.get("$defs", {})
    assert "TemplateVariantListItem" in schema.get("$defs", {})
