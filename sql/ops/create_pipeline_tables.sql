CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.pipeline_run_log (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(128) NOT NULL UNIQUE,
    pipeline_name VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    trigger_source VARCHAR(64),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    context JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ops.pipeline_step_log (
    id BIGSERIAL PRIMARY KEY,
    run_id VARCHAR(128) NOT NULL,
    step_name VARCHAR(128) NOT NULL,
    target_name VARCHAR(256),
    status VARCHAR(32) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    affected_rows BIGINT,
    error_message TEXT,
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ops.data_freshness_log (
    id BIGSERIAL PRIMARY KEY,
    target_name VARCHAR(256) NOT NULL UNIQUE,
    target_type VARCHAR(64) NOT NULL,
    last_started_at TIMESTAMPTZ,
    last_succeeded_at TIMESTAMPTZ,
    status VARCHAR(32) NOT NULL DEFAULT 'unknown',
    affected_rows BIGINT,
    data_min_date DATE,
    data_max_date DATE,
    notes JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS ops.data_lineage_registry (
    id BIGSERIAL PRIMARY KEY,
    target_name VARCHAR(256) NOT NULL,
    target_type VARCHAR(64) NOT NULL,
    source_name VARCHAR(256) NOT NULL,
    source_type VARCHAR(64) NOT NULL,
    dependency_level INTEGER NOT NULL DEFAULT 1,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (target_name, source_name)
);

CREATE INDEX IF NOT EXISTS ix_pipeline_run_log_status
ON ops.pipeline_run_log (status, started_at DESC);

CREATE INDEX IF NOT EXISTS ix_pipeline_step_log_run_id
ON ops.pipeline_step_log (run_id, started_at DESC);

CREATE INDEX IF NOT EXISTS ix_pipeline_step_log_target_name
ON ops.pipeline_step_log (target_name, status);

CREATE INDEX IF NOT EXISTS ix_data_freshness_log_status
ON ops.data_freshness_log (status, last_succeeded_at DESC);

CREATE INDEX IF NOT EXISTS ix_data_lineage_registry_target_name
ON ops.data_lineage_registry (target_name, active);
