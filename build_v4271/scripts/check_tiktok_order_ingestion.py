# -*- coding: utf-8 -*-
"""
检查TikTok订单数据入库情况
用于诊断物化视图不显示数据的问题
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def check_tiktok_order_ingestion():
    """检查TikTok订单数据入库情况"""
    safe_print("=" * 70)
    safe_print("检查TikTok订单数据入库情况")
    safe_print("=" * 70)
    
    db = next(get_db())
    try:
        # 1. 检查fact_orders表中的TikTok订单数据
        safe_print("\n[1] 检查fact_orders表中的TikTok订单数据...")
        result = db.execute(text("""
            SELECT 
                COUNT(*) as total_count,
                COUNT(DISTINCT order_id) as unique_orders,
                COUNT(CASE WHEN shop_id IS NOT NULL AND shop_id != '' THEN 1 END) as has_shop_id,
                COUNT(CASE WHEN currency IS NOT NULL AND currency != '' THEN 1 END) as has_currency,
                COUNT(CASE WHEN subtotal > 0 THEN 1 END) as has_subtotal,
                COUNT(CASE WHEN shipping_fee > 0 THEN 1 END) as has_shipping_fee,
                COUNT(CASE WHEN tax_amount > 0 THEN 1 END) as has_tax_amount,
                COUNT(CASE WHEN total_amount > 0 THEN 1 END) as has_total_amount,
                COUNT(CASE WHEN order_date_local IS NOT NULL THEN 1 END) as has_order_date,
                COUNT(CASE WHEN order_time_utc IS NOT NULL THEN 1 END) as has_order_time
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
        """)).fetchone()
        
        if result:
            safe_print(f"  总订单数: {result[0]}")
            safe_print(f"  唯一订单数: {result[1]}")
            safe_print(f"  有shop_id的订单: {result[2]} ({result[2]/result[0]*100:.1f}%)")
            safe_print(f"  有currency的订单: {result[3]} ({result[3]/result[0]*100:.1f}%)")
            safe_print(f"  有subtotal的订单: {result[4]} ({result[4]/result[0]*100:.1f}%)")
            safe_print(f"  有shipping_fee的订单: {result[5]} ({result[5]/result[0]*100:.1f}%)")
            safe_print(f"  有tax_amount的订单: {result[6]} ({result[6]/result[0]*100:.1f}%)")
            safe_print(f"  有total_amount的订单: {result[7]} ({result[7]/result[0]*100:.1f}%)")
            safe_print(f"  有order_date_local的订单: {result[8]} ({result[8]/result[0]*100:.1f}%)")
            safe_print(f"  有order_time_utc的订单: {result[9]} ({result[9]/result[0]*100:.1f}%)")
        
        # 2. 查看示例订单数据
        safe_print("\n[2] 查看示例订单数据（前5条）...")
        samples = db.execute(text("""
            SELECT 
                order_id,
                shop_id,
                currency,
                subtotal,
                subtotal_rmb,
                shipping_fee,
                shipping_fee_rmb,
                tax_amount,
                tax_amount_rmb,
                total_amount,
                total_amount_rmb,
                order_date_local,
                order_time_utc,
                file_id,
                CASE WHEN attributes IS NOT NULL THEN 'has_attributes' ELSE NULL END as has_attributes
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
            ORDER BY order_time_utc DESC NULLS LAST, order_id DESC
            LIMIT 5
        """)).fetchall()
        
        for idx, sample in enumerate(samples, 1):
            safe_print(f"\n  订单 {idx}:")
            safe_print(f"    order_id: {sample[0]}")
            safe_print(f"    shop_id: {sample[1] or '(NULL)'}")
            safe_print(f"    currency: {sample[2] or '(NULL)'}")
            safe_print(f"    subtotal: {sample[3]}, subtotal_rmb: {sample[4]}")
            safe_print(f"    shipping_fee: {sample[5]}, shipping_fee_rmb: {sample[6]}")
            safe_print(f"    tax_amount: {sample[7]}, tax_amount_rmb: {sample[8]}")
            safe_print(f"    total_amount: {sample[9]}, total_amount_rmb: {sample[10]}")
            safe_print(f"    order_date_local: {sample[11] or '(NULL)'}")
            safe_print(f"    order_time_utc: {sample[12] or '(NULL)'}")
            safe_print(f"    file_id: {sample[13] or '(NULL)'}")
            safe_print(f"    attributes第一个键: {sample[14] or '(NULL)'}")
        
        # 3. 检查attributes中的字段
        safe_print("\n[3] 检查attributes中的字段...")
        attr_samples = db.execute(text("""
            SELECT 
                order_id,
                attributes
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
              AND attributes IS NOT NULL
            LIMIT 3
        """)).fetchall()
        
        for idx, (order_id, attrs) in enumerate(attr_samples, 1):
            safe_print(f"\n  订单 {idx} (order_id={order_id}):")
            if attrs:
                safe_print(f"    attributes字段数: {len(attrs)}")
                safe_print(f"    attributes前10个字段: {list(attrs.keys())[:10]}")
                # 检查是否有金额相关字段
                amount_fields = [k for k in attrs.keys() if any(word in k.lower() for word in ['金额', 'amount', '价格', 'price', '费用', 'fee'])]
                if amount_fields:
                    safe_print(f"    金额相关字段: {amount_fields}")
        
        # 4. 检查物化视图fact_orders的定义
        safe_print("\n[4] 检查物化视图fact_orders的定义...")
        mv_exists = db.execute(text("""
            SELECT EXISTS (
                SELECT 1 
                FROM pg_matviews 
                WHERE matviewname = 'fact_orders'
            )
        """)).scalar()
        
        if mv_exists:
            safe_print("  [OK] 物化视图fact_orders存在")
            # 获取视图定义
            mv_definition = db.execute(text("""
                SELECT definition 
                FROM pg_matviews 
                WHERE matviewname = 'fact_orders'
            """)).scalar()
            if mv_definition:
                safe_print(f"  视图定义（前500字符）:")
                safe_print(f"    {mv_definition[:500]}...")
            
            # 检查视图中的数据
            mv_count = db.execute(text("""
                SELECT COUNT(*) 
                FROM fact_orders 
                WHERE platform_code = 'tiktok'
            """)).scalar()
            safe_print(f"  物化视图中的TikTok订单数: {mv_count}")
        else:
            safe_print("  [WARNING] 物化视图fact_orders不存在")
            safe_print("  注意：如果前端显示的是fact_orders，可能是直接查询表而不是物化视图")
        
        # 5. 检查是否有其他订单相关的物化视图
        safe_print("\n[5] 检查其他订单相关的物化视图...")
        order_mvs = db.execute(text("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE matviewname LIKE '%order%' 
               OR matviewname LIKE '%sales%'
            ORDER BY matviewname
        """)).fetchall()
        
        for mv_name, in order_mvs:
            mv_count = db.execute(text(f"""
                SELECT COUNT(*) 
                FROM {mv_name}
                WHERE platform_code = 'tiktok'
            """)).scalar()
            safe_print(f"  {mv_name}: {mv_count}条TikTok数据")
        
        # 6. 检查catalog_files表中的TikTok订单文件
        safe_print("\n[6] 检查catalog_files表中的TikTok订单文件...")
        files = db.execute(text("""
            SELECT 
                file_id,
                file_name,
                platform_code,
                data_domain,
                status,
                rows_ingested,
                created_at
            FROM catalog_files 
            WHERE platform_code = 'tiktok' 
              AND data_domain = 'orders'
            ORDER BY created_at DESC
            LIMIT 5
        """)).fetchall()
        
        safe_print(f"  找到 {len(files)} 个TikTok订单文件:")
        for file_id, file_name, platform_code, data_domain, status, rows_ingested, created_at in files:
            safe_print(f"    file_id={file_id}, file_name={file_name}, status={status}, rows_ingested={rows_ingested}")
        
        safe_print("\n" + "=" * 70)
        safe_print("检查完成")
        safe_print("=" * 70)
        
        # 总结
        safe_print("\n诊断总结:")
        if result and result[0] > 0:
            safe_print("  [OK] fact_orders表中有TikTok订单数据")
            if result[2] == 0:
                safe_print("  [WARNING] 所有订单的shop_id都为空")
            if result[3] == 0:
                safe_print("  [WARNING] 所有订单的currency都为空")
            if result[4] == 0 and result[7] == 0:
                safe_print("  [WARNING] 所有订单的金额字段都为0")
            if result[8] == 0 and result[9] == 0:
                safe_print("  [WARNING] 所有订单都没有日期或时间信息")
        else:
            safe_print("  [ERROR] fact_orders表中没有TikTok订单数据")
            safe_print("  可能原因:")
            safe_print("    1. 数据没有成功入库")
            safe_print("    2. platform_code字段值不是'tiktok'")
            safe_print("    3. 入库过程中出现错误")
        
    except Exception as e:
        safe_print(f"检查失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_tiktok_order_ingestion()

