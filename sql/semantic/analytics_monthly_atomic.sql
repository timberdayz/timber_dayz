CREATE SCHEMA IF NOT EXISTS semantic;

DROP VIEW IF EXISTS semantic.fact_analytics_monthly_atomic CASCADE;

CREATE OR REPLACE VIEW semantic.fact_analytics_monthly_atomic AS
SELECT
    metric_date,
    platform_code,
    shop_id,
    raw_shop_id,
    store_label_raw,
    resolved_shop_account_id,
    resolution_method,
    identity_source_value,
    canonical_shop_id,
    identity_warning_code,
    visitor_count,
    product_visitor_count,
    page_views,
    impressions,
    order_count,
    sku_order_count,
    gmv,
    total_transaction_amount,
    data_hash,
    ingest_timestamp,
    identity_candidate_count,
    identity_candidates,
    -- [*] 2026-11-09 补登: shopee 独有的 5 个流量指标(与日/周链同源同口径)。
    new_visitor_count,
    returning_visitor_count,
    new_follower_count,
    avg_session_duration_seconds,
    avg_page_views_per_visitor,
    product_card_gmv,
    live_gmv,
    live_indirect_gmv,
    video_gmv,
    video_indirect_gmv,
    bound_account_live_attributed_gmv,
    bound_account_video_attributed_gmv,
    affiliate_video_attributed_gmv,
    creator_live_gmv,
    creator_live_attributed_gmv,
    creator_live_indirect_gmv,
    creator_video_gmv,
    creator_video_indirect_gmv
FROM semantic.fact_analytics_monthly_atomic_mv;
