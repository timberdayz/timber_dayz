CREATE TABLE IF NOT EXISTS core.semantic_field_rule_groups (
    id BIGSERIAL PRIMARY KEY,
    platform_code VARCHAR(32) NOT NULL,
    data_domain VARCHAR(64) NOT NULL,
    sub_domain VARCHAR(64),
    canonical_field_name VARCHAR(128) NOT NULL,
    rule_type VARCHAR(32) NOT NULL,
    coexistence_policy VARCHAR(64) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    decision_source VARCHAR(128) NOT NULL DEFAULT 'doc_sql_governance',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS core.semantic_field_rule_members (
    id BIGSERIAL PRIMARY KEY,
    rule_group_id BIGINT NOT NULL REFERENCES core.semantic_field_rule_groups(id) ON DELETE CASCADE,
    source_field_name VARCHAR(256) NOT NULL,
    priority INTEGER NOT NULL DEFAULT 100,
    source_platform_scope VARCHAR(32),
    source_domain_scope VARCHAR(64),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_semantic_field_rule_groups_scope
ON core.semantic_field_rule_groups (platform_code, data_domain, sub_domain, active);

CREATE INDEX IF NOT EXISTS ix_semantic_field_rule_groups_canonical
ON core.semantic_field_rule_groups (canonical_field_name, rule_type, active);

CREATE INDEX IF NOT EXISTS ix_semantic_field_rule_members_group
ON core.semantic_field_rule_members (rule_group_id, priority DESC, active);
