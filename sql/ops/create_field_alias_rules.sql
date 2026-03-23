CREATE TABLE IF NOT EXISTS core.field_alias_rules (
    id BIGSERIAL PRIMARY KEY,
    platform_code VARCHAR(32) NOT NULL,
    data_domain VARCHAR(64) NOT NULL,
    sub_domain VARCHAR(64),
    source_field_name VARCHAR(256) NOT NULL,
    standard_field_name VARCHAR(128) NOT NULL,
    parser_type VARCHAR(64) NOT NULL DEFAULT 'text',
    priority INTEGER NOT NULL DEFAULT 100,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_field_alias_rules_scope
ON core.field_alias_rules (platform_code, data_domain, sub_domain, active);

CREATE INDEX IF NOT EXISTS ix_field_alias_rules_standard_field
ON core.field_alias_rules (standard_field_name, priority DESC);
