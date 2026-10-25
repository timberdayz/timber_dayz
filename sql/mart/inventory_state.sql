CREATE SCHEMA IF NOT EXISTS mart;

-- 状态层：每个 SKU×仓 一行，由 inventory_state_refresh_service 的「双闸判定」维护。
--
-- 双闸（2026-10-24 定案）：
--   闸 1（妙手侧）：「更新时间」维度 + 区间筛选，只决定这次导出哪些行；
--   闸 2（我方侧）：与上一批比对库存数量，决定这一行算不算「真的变了」。
--
-- 为什么不用妙手的「更新时间」直接当变动时间：
-- 实测 file 2764 有 535 行（43.7%）的更新时间被一次 bulk UPDATE 批量覆盖成
-- 2026-05-08 10:36:36~39，而那些行的库存和销量完全没变。
-- → stock_changed_at 只认「库存数量真的变了」。
--
-- Use Alembic for schema evolution; keep bootstrap SQL idempotent.
CREATE TABLE IF NOT EXISTS mart.inventory_state (
    platform_code VARCHAR(64) NOT NULL,
    sku_key VARCHAR(255) NOT NULL,
    warehouse_name VARCHAR(255) NOT NULL,
    platform_sku VARCHAR(255),
    product_sku VARCHAR(255),
    sku_id VARCHAR(255),
    product_id VARCHAR(255),
    product_name TEXT,
    -- 当前库存
    available_stock NUMERIC(18, 2) NOT NULL DEFAULT 0,
    on_hand_stock NUMERIC(18, 2) NOT NULL DEFAULT 0,
    reserved_stock NUMERIC(18, 2) NOT NULL DEFAULT 0,
    inventory_value NUMERIC(18, 2) NOT NULL DEFAULT 0,
    unit_cost NUMERIC(18, 2) NOT NULL DEFAULT 0,
    -- 妙手仓库清单自带的滚动销量窗口（参考值；NULL = 该行取不到）
    checklist_sales_7d NUMERIC(18, 2),
    checklist_sales_30d NUMERIC(18, 2),
    checklist_sales_60d NUMERIC(18, 2),
    checklist_sales_90d NUMERIC(18, 2),
    -- 三个时间戳，各司其职
    stock_added_at TIMESTAMPTZ,     -- **上次进货（库存增加）时间** —— 距上次进货天数的分子
    row_seen_at TIMESTAMPTZ,        -- 本行最近一次被采集看到的时间
    row_written_at TIMESTAMPTZ,     -- 妙手给的时间戳（仅留档，不参与判定）
    -- 妙手「创建时间」= 首次铺货时间。**补货不会重置它**，
    -- 它只用来做「首次观测」的初值（首次铺货 ≈ 首次进货）。
    created_at TIMESTAMPTZ,
    last_metric_date DATE,
    source_file_id INTEGER,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (platform_code, sku_key, warehouse_name)
);

CREATE INDEX IF NOT EXISTS ix_inventory_state_stock_added_at
    ON mart.inventory_state (stock_added_at DESC);

CREATE INDEX IF NOT EXISTS ix_inventory_state_sales_90d
    ON mart.inventory_state (checklist_sales_90d);
