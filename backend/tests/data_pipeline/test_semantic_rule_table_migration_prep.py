from pathlib import Path


def test_semantic_rule_table_v2_draft_sql_exists():
    sql_path = Path("sql/ops/create_semantic_field_rules_v2_draft.sql")
    assert sql_path.exists()


def test_semantic_rule_table_v2_draft_sql_defines_rule_groups_and_members():
    sql_text = Path("sql/ops/create_semantic_field_rules_v2_draft.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS core.semantic_field_rule_groups" in sql_text
    assert "CREATE TABLE IF NOT EXISTS core.semantic_field_rule_members" in sql_text
    assert "rule_type" in sql_text
    assert "coexistence_policy" in sql_text
    assert "canonical_field_name" in sql_text
    assert "rule_group_id" in sql_text
    assert "source_field_name" in sql_text


def test_semantic_rule_table_v2_draft_can_represent_split_merge_and_priority():
    doc_text = Path("docs/architecture/FIELD_ALIAS_RULES_MIGRATION_PREP.md").read_text(
        encoding="utf-8"
    )

    assert "`merge`" in doc_text
    assert "`split`" in doc_text
    assert "`priority`" in doc_text
    assert "split_if_same_file" in doc_text
    assert "merge_cross_platform_only" in doc_text
    assert "priority_fallback" in doc_text
