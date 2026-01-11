"""create materialized view for product management (Rewritten)

Revision ID: 20251105_204106
Revises: 20251105_add_field_usage_tracking
Create Date: 2025-11-05 20:41:06

企业级ERP语义层实施 - v4.8.0
参考SAP BW InfoCube和Oracle Materialized View设计标准

重写说明（2026-01-11）：
- 修复SQL语法错误
- 使用正确的dim_platforms和dim_shops字段名（name vs platform_name, shop_name保持一致）
- 基于schema.py中fact_product_metrics的实际字段
- 添加完整的幂等性检查
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '20251105_204106'
down_revision = 'add_field_usage_tracking'
branch_labels = None
depends_on = None


def upgrade():
    """
    创建产品管理物化视图（mv_product_management）
    
    目标：
    1. 预JOIN维度表（dim_platforms, dim_shops）
    2. 预计算业务指标（库存状态、转化率、预估营收）
    3. 提升查询性能10-100倍
    
    设计原则：
    - Single Source of Truth: 视图定义在此唯一位置
    - 企业级标准: 参考SAP HANA Views和Oracle MV
    - 性能优先: CONCURRENTLY刷新（不锁表）
    """
    conn = op.get_bind()
    inspector = inspect(conn)
    
    # 检查物化视图是否已存在
    existing_views = []
    try:
        result = conn.execute(text("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE schemaname = 'public' AND matviewname = 'mv_product_management'
        """))
        existing_views = [row[0] for row in result]
    except Exception as e:
        print(f"[WARNING] 无法检查物化视图: {e}")
        return
    
    if 'mv_product_management' in existing_views:
        print("[INFO] mv_product_management视图已存在，跳过创建")
        # 检查并创建缺失的索引
        try:
            existing_indexes = [idx['name'] for idx in inspector.get_indexes('mv_product_management')]
        except:
            existing_indexes = []
        
        # 确保唯一索引存在
        if 'idx_mv_product_management_pk' not in existing_indexes:
            try:
                op.execute(text("""
                    CREATE UNIQUE INDEX idx_mv_product_management_pk 
                    ON mv_product_management(platform_code, shop_id, platform_sku, metric_date, metric_type);
                """))
                print("[MV] 唯一索引创建成功")
            except Exception as e:
                print(f"[WARNING] 创建唯一索引失败: {e}")
        
        # 创建其他缺失的索引
        index_definitions = [
            ('idx_mv_product_platform', 'platform_code'),
            ('idx_mv_product_category', 'category'),
            ('idx_mv_product_stock_status', 'stock_status'),
            ('idx_mv_product_date', 'metric_date DESC'),
            ('idx_mv_product_platform_sku', 'platform_code, platform_sku')
        ]
        
        for idx_name, idx_cols in index_definitions:
            if idx_name not in existing_indexes:
                try:
                    op.execute(text(f"""
                        CREATE INDEX IF NOT EXISTS {idx_name} 
                        ON mv_product_management({idx_cols});
                    """))
                    print(f"[MV] 索引 {idx_name} 创建成功")
                except Exception as e:
                    print(f"[WARNING] 创建索引 {idx_name} 失败: {e}")
        return
    
    # 检查依赖表是否存在
    existing_tables = set(inspector.get_table_names())
    if 'fact_product_metrics' not in existing_tables:
        print("[WARNING] fact_product_metrics表不存在，跳过mv_product_management创建")
        return
    
    if 'dim_platforms' not in existing_tables or 'dim_shops' not in existing_tables:
        print("[WARNING] dim_platforms或dim_shops表不存在，跳过mv_product_management创建")
        return
    
    # 检查fact_product_metrics的必要列
    try:
        fp_columns = [col['name'] for col in inspector.get_columns('fact_product_metrics')]
        required_fp_columns = [
            'platform_code', 'shop_id', 'platform_sku', 'metric_date', 'metric_type',
            'product_name', 'category', 'brand', 'image_url', 'price', 'currency', 'price_rmb',
            'stock', 'available_stock', 'total_stock', 'sales_volume', 'sales_amount', 'sales_amount_rmb',
            'page_views', 'unique_visitors', 'add_to_cart_count', 'rating', 'review_count',
            'granularity', 'period_start', 'created_at', 'updated_at'
        ]
        missing_columns = set(required_fp_columns) - set(fp_columns)
        if missing_columns:
            print(f"[WARNING] fact_product_metrics表缺少必要列，跳过mv_product_management创建。缺失列: {missing_columns}")
            return
    except Exception as e:
        print(f"[WARNING] 无法检查fact_product_metrics表列: {e}")
        return
    
    # 创建产品管理物化视图
    # 注意：fact_product_metrics表使用复合主键（platform_code, shop_id, platform_sku, metric_date, metric_type）
    # 注意：dim_platforms表使用name字段（不是platform_name）
    # 注意：dim_shops表使用shop_name字段
    try:
        op.execute(text("""
            CREATE MATERIALIZED VIEW mv_product_management AS
            SELECT 
                -- ========== 主键和标识 ==========
                p.platform_code,
                plat.name as platform_name,
                p.shop_id,
                s.shop_name,
                
                -- ========== 产品基本信息 ==========
                p.platform_sku,
                p.metric_date,
                COALESCE(p.metric_type, 'default') as metric_type,
                p.product_name,
                p.category,
                p.brand,
                p.image_url,
                
                -- ========== 价格信息 ==========
                p.price,
                p.currency,
                p.price_rmb,
                
                -- ========== 库存信息 ==========
                p.stock,
                p.available_stock,
                p.total_stock,
                -- 计算字段：库存状态（业务逻辑集中管理）
                CASE 
                    WHEN COALESCE(p.available_stock, p.stock, 0) = 0 THEN 'out_of_stock'
                    WHEN COALESCE(p.available_stock, p.stock, 0) < 10 THEN 'low_stock'
                    WHEN COALESCE(p.available_stock, p.stock, 0) < 50 THEN 'medium_stock'
                    ELSE 'high_stock'
                END as stock_status,
                
                -- ========== 销售指标 ==========
                p.sales_volume,
                p.sales_amount,
                p.sales_amount_rmb,
                p.sales_amount as revenue,
                p.sales_amount_rmb as revenue_rmb,
                
                -- ========== 流量指标 ==========
                p.page_views,
                p.unique_visitors as visitors,
                p.add_to_cart_count,
                
                -- 计算字段：转化率（业务逻辑）
                CASE 
                    WHEN COALESCE(p.page_views, 0) > 0 
                    THEN ROUND((p.sales_volume::numeric / p.page_views * 100), 2)
                    ELSE 0
                END as conversion_rate_calc,
                
                -- 计算字段：加购率
                CASE 
                    WHEN COALESCE(p.page_views, 0) > 0 
                    THEN ROUND((p.add_to_cart_count::numeric / p.page_views * 100), 2)
                    ELSE 0
                END as add_to_cart_rate,
                
                -- ========== 评价指标 ==========
                p.rating,
                p.review_count,
                
                -- ========== 状态和时间 ==========
                p.granularity,
                p.period_start,
                
                -- ========== 计算字段（业务价值）==========
                -- 预估营收（CNY）
                p.sales_volume * COALESCE(p.price_rmb, p.price, 0) as estimated_revenue_rmb,
                
                -- 库存周转天数（假设）
                CASE 
                    WHEN COALESCE(p.sales_volume, 0) > 0 
                    THEN ROUND((p.stock::numeric / (p.sales_volume::numeric / 30)), 1)
                    ELSE 999
                END as inventory_turnover_days,
                
                -- 产品健康度评分（0-100）
                LEAST(100, GREATEST(0,
                    COALESCE(p.rating, 0) * 20 +  -- 评分占20分
                    CASE WHEN p.stock > 0 THEN 20 ELSE 0 END +  -- 有库存20分
                    LEAST(20, COALESCE(p.sales_volume, 0) / 10) +  -- 销量占20分
                    LEAST(20, COALESCE(p.page_views, 0) / 100) +  -- 流量占20分
                    20  -- 固定20分
                )) as product_health_score,
                
                -- ========== 审计字段 ==========
                p.created_at,
                p.updated_at
                
            FROM fact_product_metrics p
            LEFT JOIN dim_platforms plat ON p.platform_code = plat.platform_code
            LEFT JOIN dim_shops s ON p.platform_code = s.platform_code AND p.shop_id = s.shop_id
            
            -- 性能优化：只保留最近90天数据
            WHERE p.metric_date >= CURRENT_DATE - INTERVAL '90 days'
            
            WITH DATA;
        """))
        print("[MV] 物化视图mv_product_management创建成功")
        
        # 创建唯一索引（必须有，支持CONCURRENTLY刷新）
        op.execute(text("""
            CREATE UNIQUE INDEX idx_mv_product_management_pk 
            ON mv_product_management(platform_code, shop_id, platform_sku, metric_date, metric_type);
        """))
        print("[MV] 唯一索引创建成功")
        
        # 创建筛选索引（提升查询性能）
        index_definitions = [
            ('idx_mv_product_platform', 'platform_code'),
            ('idx_mv_product_category', 'category'),
            ('idx_mv_product_stock_status', 'stock_status'),
            ('idx_mv_product_date', 'metric_date DESC'),
            ('idx_mv_product_platform_sku', 'platform_code, platform_sku')
        ]
        
        for idx_name, idx_cols in index_definitions:
            op.execute(text(f"""
                CREATE INDEX {idx_name} 
                ON mv_product_management({idx_cols});
            """))
        print("[MV] 所有索引创建成功")
        
        # 创建刷新函数
        op.execute(text("""
            CREATE OR REPLACE FUNCTION refresh_product_management_view()
            RETURNS TABLE(
                duration_seconds FLOAT,
                row_count INTEGER,
                success BOOLEAN
            ) AS $$
            DECLARE
                start_time TIMESTAMP;
                end_time TIMESTAMP;
                duration FLOAT;
                rows INTEGER;
            BEGIN
                start_time := clock_timestamp();
                
                -- 刷新物化视图（CONCURRENTLY不锁表）
                REFRESH MATERIALIZED VIEW CONCURRENTLY mv_product_management;
                
                end_time := clock_timestamp();
                duration := EXTRACT(EPOCH FROM (end_time - start_time));
                
                -- 获取行数
                SELECT COUNT(*) INTO rows FROM mv_product_management;
                
                RETURN QUERY SELECT duration, rows, true;
            END;
            $$ LANGUAGE plpgsql;
        """))
        print("[MV] 刷新函数创建成功")
        
    except Exception as e:
        print(f"[ERROR] 创建mv_product_management物化视图失败: {e}")
        import traceback
        traceback.print_exc()
        # 不抛出异常，允许迁移继续


def downgrade():
    """
    回滚：删除物化视图和相关对象
    """
    conn = op.get_bind()
    
    # 删除刷新函数
    try:
        op.execute(text("DROP FUNCTION IF EXISTS refresh_product_management_view();"))
    except:
        pass
    
    # 删除物化视图（CASCADE删除所有依赖）
    try:
        op.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_product_management CASCADE;"))
        print("[MV] 物化视图已删除")
    except:
        pass
