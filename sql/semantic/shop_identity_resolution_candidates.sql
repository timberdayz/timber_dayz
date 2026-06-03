CREATE SCHEMA IF NOT EXISTS semantic;

-- Best practice note:
-- Avoid DO/EXECUTE dynamic SQL inside SQL assets. If performance requires materialization,
-- implement it in the Python bootstrap runner, not inside the SQL file.
CREATE OR REPLACE VIEW semantic.shop_identity_resolution_candidates AS
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
     AND saa.is_active = TRUE
    WHERE NULLIF(TRIM(COALESCE(saa.alias_normalized, '')), '') IS NOT NULL

    UNION ALL

    SELECT
        platform_code,
        resolved_shop_id,
        resolved_shop_account_id,
        'store_name_match'::varchar AS resolution_method,
        4 AS resolution_priority,
        REGEXP_REPLACE(
            REGEXP_REPLACE(
                LOWER(TRIM(candidate_store_label)),
                '^(shopee|tiktok\s*shop|tiktok|tk|miaoshou|amazon|lazada)\s*',
                '',
                'i'
            ),
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

CREATE INDEX IF NOT EXISTS ix_shop_accounts_platform_shop_id_lookup
ON core.shop_accounts (
    LOWER(COALESCE(platform, '')),
    LOWER(COALESCE(platform_shop_id, ''))
);

CREATE INDEX IF NOT EXISTS ix_shop_accounts_platform_account_id_lookup
ON core.shop_accounts (
    LOWER(COALESCE(platform, '')),
    LOWER(COALESCE(shop_account_id, ''))
);

CREATE INDEX IF NOT EXISTS ix_shop_account_aliases_platform_alias_lookup
ON core.shop_account_aliases (
    platform,
    LOWER(TRIM(alias_normalized)),
    is_active
);
