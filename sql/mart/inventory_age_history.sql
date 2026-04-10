CREATE SCHEMA IF NOT EXISTS mart;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'mart'
          AND c.relname = 'inventory_age_history'
          AND c.relkind = 'v'
    ) THEN
        EXECUTE 'DROP VIEW mart.inventory_age_history CASCADE';
    ELSIF EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'mart'
          AND c.relname = 'inventory_age_history'
          AND c.relkind = 'm'
    ) THEN
        EXECUTE 'DROP MATERIALIZED VIEW mart.inventory_age_history CASCADE';
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS mart.inventory_age_history (
    snapshot_date DATE NOT NULL,
    platform_code VARCHAR(64) NOT NULL,
    sku_key VARCHAR(255) NOT NULL,
    platform_sku VARCHAR(255),
    product_sku VARCHAR(255),
    sku_id VARCHAR(255),
    product_id VARCHAR(255),
    product_name TEXT,
    current_qty BIGINT NOT NULL,
    previous_qty BIGINT,
    qty_delta BIGINT,
    age_anchor_date DATE,
    age_days INTEGER,
    bucket VARCHAR(32),
    reset_reason VARCHAR(64) NOT NULL,
    on_hand_qty BIGINT,
    inventory_value NUMERIC(18, 2) NOT NULL DEFAULT 0,
    warehouse_count INTEGER NOT NULL DEFAULT 0,
    last_ingest_timestamp TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (platform_code, sku_key, snapshot_date)
);

CREATE INDEX IF NOT EXISTS ix_inventory_age_history_snapshot_date
    ON mart.inventory_age_history (snapshot_date);

CREATE INDEX IF NOT EXISTS ix_inventory_age_history_platform_age
    ON mart.inventory_age_history (platform_code, age_days DESC);
