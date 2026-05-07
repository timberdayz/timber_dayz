CREATE SCHEMA IF NOT EXISTS semantic;

-- Performance note:
-- This object is used in LATERAL identity resolution joins inside semantic analytics/order facts.
-- Keeping it as a dynamic VIEW forces Postgres to repeatedly execute REGEXP/UNION logic during
-- online dashboard reads. We materialize it (with indexes) and expose the same stable VIEW name.
--
-- IMPORTANT: Do NOT DROP ... CASCADE here.
-- The semantic/mart/api layer depends on this view - dropping with CASCADE will remove downstream
-- views and break online queries. Use CREATE IF NOT EXISTS + REFRESH instead.

DO $bootstrap$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_matviews
        WHERE schemaname = 'semantic'
          AND matviewname = 'shop_identity_resolution_candidates_mv'
    ) THEN
        EXECUTE $mv$
        CREATE MATERIALIZED VIEW semantic.shop_identity_resolution_candidates_mv AS
WITH active_shop_accounts AS (
    SELECT
        sa.id AS shop_account_pk,
        LOWER(COALESCE(sa.platform, '')) AS platform_code,
        NULLIF(TRIM(COALESCE(sa.shop_account_id, '')), '') AS resolved_shop_account_id,
        NULLIF(TRIM(COALESCE(sa.platform_shop_id, '')), '') AS candidate_platform_shop_id,
        NULLIF(TRIM(COALESCE(sa.store_name, '')), '') AS candidate_store_label,
        COALESCE(
            NULLIF(TRIM(COALESCE(sa.platform_shop_id, '')), ''),
            NULLIF(TRIM(COALESCE(sa.shop_account_id, '')), ''),
            sa.id::text
        ) AS resolved_shop_id
    FROM core.shop_accounts sa
),
identity_rows AS (
    SELECT
        platform_code,
        resolved_shop_id,
        resolved_shop_account_id,
        'platform_shop_id'::varchar AS resolution_method,
        1 AS resolution_priority,
        LOWER(candidate_platform_shop_id) AS identity_value_normalized,
        candidate_platform_shop_id AS identity_source_value
    FROM active_shop_accounts
    WHERE candidate_platform_shop_id IS NOT NULL

    UNION ALL

    SELECT
        platform_code,
        resolved_shop_id,
        resolved_shop_account_id,
        'shop_account_id'::varchar AS resolution_method,
        2 AS resolution_priority,
        LOWER(resolved_shop_account_id) AS identity_value_normalized,
        resolved_shop_account_id AS identity_source_value
    FROM active_shop_accounts
    WHERE resolved_shop_account_id IS NOT NULL

    UNION ALL

    SELECT
        asa.platform_code,
        asa.resolved_shop_id,
        asa.resolved_shop_account_id,
        'alias_match'::varchar AS resolution_method,
        3 AS resolution_priority,
        LOWER(TRIM(saa.alias_normalized)) AS identity_value_normalized,
        saa.alias_value AS identity_source_value
    FROM active_shop_accounts asa
    INNER JOIN core.shop_account_aliases saa
      ON saa.shop_account_id = asa.shop_account_pk
     AND saa.is_active = true
    WHERE NULLIF(TRIM(COALESCE(saa.alias_normalized, '')), '') IS NOT NULL

    UNION ALL

    SELECT
        platform_code,
        resolved_shop_id,
        resolved_shop_account_id,
        'store_name_match'::varchar AS resolution_method,
        4 AS resolution_priority,
        REGEXP_REPLACE(
            REGEXP_REPLACE(LOWER(TRIM(candidate_store_label)), '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*', '', 'i'),
            '[[:space:]_()/-]+',
            '',
            'g'
        ) AS identity_value_normalized,
        candidate_store_label AS identity_source_value
    FROM active_shop_accounts
    WHERE candidate_store_label IS NOT NULL
)
SELECT
    platform_code,
    identity_value_normalized,
    identity_source_value,
    resolved_shop_id,
    resolved_shop_account_id,
    resolution_method,
    resolution_priority
FROM identity_rows
WHERE NULLIF(TRIM(COALESCE(identity_value_normalized, '')), '') IS NOT NULL;
$mv$;
    ELSE
        REFRESH MATERIALIZED VIEW semantic.shop_identity_resolution_candidates_mv;
    END IF;
END
$bootstrap$;

CREATE INDEX IF NOT EXISTS ix_shop_identity_candidates_mv_platform_identity_priority
    ON semantic.shop_identity_resolution_candidates_mv (platform_code, identity_value_normalized, resolution_priority);

CREATE INDEX IF NOT EXISTS ix_shop_identity_candidates_mv_platform_identity
    ON semantic.shop_identity_resolution_candidates_mv (platform_code, identity_value_normalized);

CREATE OR REPLACE VIEW semantic.shop_identity_resolution_candidates AS
SELECT
    platform_code,
    identity_value_normalized,
    identity_source_value,
    resolved_shop_id,
    resolved_shop_account_id,
    resolution_method,
    resolution_priority
FROM semantic.shop_identity_resolution_candidates_mv;
