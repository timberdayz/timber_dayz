#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从dim_products同步图片URL到fact_product_metrics
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import text
from backend.models.database import engine

def sync_image_urls():
    """同步图片URL"""
    
    print("\n" + "="*80)
    print("从dim_products同步图片URL到fact_product_metrics")
    print("="*80)
    
    with engine.connect() as conn:
        # 检查dim_products中有图片的产品数量
        result = conn.execute(text("""
            SELECT COUNT(*) 
            FROM dim_products 
            WHERE image_url IS NOT NULL AND image_url != ''
        """))
        dim_count = result.scalar()
        print(f"\n[检查] dim_products表中有图片的产品: {dim_count}个")
        
        if dim_count == 0:
            print("\n[跳过] dim_products表中没有图片数据，无需同步")
            print("       建议：重新导入miaoshou产品数据，映射'商品图片'字段")
            return
        
        # 执行同步
        print("\n[同步] 正在同步图片URL...")
        result = conn.execute(text("""
            UPDATE fact_product_metrics fm
            SET image_url = dp.image_url
            FROM dim_products dp
            WHERE fm.platform_code = dp.platform_code
            AND fm.shop_id = dp.shop_id
            AND fm.platform_sku = dp.platform_sku
            AND dp.image_url IS NOT NULL
            AND dp.image_url != ''
        """))
        conn.commit()
        
        updated_count = result.rowcount
        print(f"[OK] 同步完成，更新了 {updated_count} 条记录")
        
        # 验证
        result = conn.execute(text("""
            SELECT COUNT(*) 
            FROM fact_product_metrics 
            WHERE image_url IS NOT NULL AND image_url != ''
        """))
        metrics_count = result.scalar()
        print(f"\n[验证] fact_product_metrics表中有图片的产品: {metrics_count}个")
        
        # 显示示例
        if metrics_count > 0:
            result = conn.execute(text("""
                SELECT platform_sku, product_name, image_url
                FROM fact_product_metrics
                WHERE image_url IS NOT NULL
                LIMIT 3
            """))
            
            print("\n[示例] 有图片的产品:")
            for row in result:
                print(f"  {row[0]}: {row[1]}")
                print(f"    {row[2][:100]}...")
        
        print("\n" + "="*80)
        print("同步完成！刷新产品管理页面查看效果")
        print("="*80)

if __name__ == "__main__":
    sync_image_urls()

