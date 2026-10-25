CREATE SCHEMA IF NOT EXISTS mart;

-- Best practice note:
-- Avoid dynamic SQL for MV create/refresh inside SQL assets. To keep bootstrap idempotent,
-- expose a stable VIEW and let deploy-time bootstrap decide whether to materialize.
--
-- 2026-10-24 改造（滞销判据换血）：
--   1. **判据换成「距上次进货时长」**（days_since_restock = 今天 − 库存最后一次真实变动的时间）。
--      妙手「近 XX 天销量」是行级存储快照，增量模式下只覆盖 13.6% 的 SKU，
--      不能当判定依据；距上次进货时长是事件时刻，增量下始终准确。
--   2. **删掉 9999 哨兵与两个假指标**：estimated_turnover_days（9999 当「卖不动」、
--      0 当「没货」，两个都不是事实）、risk_level、clearance_priority_score。
--   3. **SQL 层只放原子事实，不做除法、不做分档**：
--      DOS 参考值（checklist_dos_*）与停滞档位（restock_tier）一律在 Python 的唯一实现里算，
--      见 backend/services/inventory/inventory_restock_service.py 与 inventory_dos_service.py。
--
-- ⚠️ 本视图**删了列**（estimated_turnover_days / risk_level / clearance_priority_score 等），
--    PostgreSQL 的 CREATE OR REPLACE VIEW 不允许删列 → 必须先 DROP 再建。
--    下游 api.* 视图依赖本视图，重建顺序必须是：先 DROP api.* → DROP 本视图 → 建本视图 → 建 api.*。
DROP VIEW IF EXISTS mart.inventory_backlog_base;
CREATE OR REPLACE VIEW mart.inventory_backlog_base AS
WITH latest AS (
    SELECT
        snapshot_date,
        platform_code,
        NULL::text AS shop_id,
        product_id,
        product_name,
        platform_sku,
        sku_id,
        product_sku,
        warehouse_name,
        warehouse_code,
        available_stock,
        on_hand_stock,
        inventory_value
    FROM mart.inventory_snapshot_latest
),
state AS (
    SELECT
        platform_code,
        sku_key,
        warehouse_name,
        stock_added_at,
        row_seen_at,
        row_written_at,
        checklist_sales_7d,
        checklist_sales_30d,
        checklist_sales_60d,
        checklist_sales_90d
    FROM mart.inventory_state
),
joined_backlog AS (
    SELECT
        l.snapshot_date,
        l.platform_code,
        l.shop_id,
        l.product_id,
        l.product_name,
        l.platform_sku,
        l.product_sku,
        l.warehouse_name,
        l.warehouse_code,
        l.available_stock,
        l.on_hand_stock,
        l.inventory_value,
        s.stock_added_at,
        s.row_seen_at,
        s.row_written_at,
        s.checklist_sales_7d,
        s.checklist_sales_30d,
        s.checklist_sales_60d,
        s.checklist_sales_90d,
        CASE
            WHEN s.stock_added_at IS NULL THEN NULL
            ELSE (CURRENT_DATE - s.stock_added_at::date)
        END AS days_since_restock
    FROM latest l
    LEFT JOIN state s
        ON s.platform_code = l.platform_code
       AND s.sku_key = COALESCE(
            NULLIF(l.platform_sku, ''),
            NULLIF(l.product_sku, ''),
            NULLIF(l.sku_id, ''),
            NULLIF(l.product_id, '')
       )
       AND COALESCE(s.warehouse_name, '') = COALESCE(l.warehouse_name, '')
    -- **只算还有库存的仓**：已卖空的 SKU 不压资金，不该算进积压。
    -- 口径与 api.sku_clearance_ranking_module 的 state CTE 完全一致
    -- （同一套过滤 + 同一套 SKU 级聚合），两张榜不会给出两个答案。
    WHERE l.available_stock > 0
)
SELECT
    snapshot_date,
    platform_code,
    shop_id,
    product_id,
    product_name,
    platform_sku,
    product_sku,
    warehouse_name,
    warehouse_code,
    available_stock,
    on_hand_stock,
    inventory_value,
    -- 三个时间戳各司其职
    stock_added_at,
    row_seen_at,
    row_written_at,
    -- 距上次进货天数（日期差，不是口径；分档在 Python 唯一实现里做）
    days_since_restock,
    -- 妙手滚动销量窗口（参考值；NULL = 该行取不到）
    checklist_sales_7d,
    checklist_sales_30d,
    checklist_sales_60d,
    checklist_sales_90d
FROM joined_backlog;
