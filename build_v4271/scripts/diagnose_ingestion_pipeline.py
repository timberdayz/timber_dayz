#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据入库管道诊断脚本

v4.11.4新增：
- 根据ingest_task_id查询staging→fact→MV行数链路
- 输出诊断报告（哪个环节数据丢失）
- 帮助用户快速定位"文件同步了但事实表为空"的问题

v4.11.5新增：
- 批量健康检查功能：检查Raw/Fact/MV三层数据完整性
- 数据隔离区统计
- 物化视图刷新状态检查
"""
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import SessionLocal
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)

def diagnose_pipeline(task_id: str = None, file_id: int = None):
    """
    诊断数据入库管道
    
    Args:
        task_id: 同步任务ID（可选）
        file_id: 文件ID（可选）
    
    如果都不提供，则诊断最近的任务
    """
    db = SessionLocal()
    try:
        print("=" * 60)
        print("数据入库管道诊断")
        print("=" * 60)
        
        # 1. 确定查询条件
        if task_id:
            print(f"\n[查询条件] 任务ID: {task_id}")
            task_filter = "ingest_task_id = :task_id"
            params = {"task_id": task_id}
        elif file_id:
            print(f"\n[查询条件] 文件ID: {file_id}")
            task_filter = "file_id = :file_id"
            params = {"file_id": file_id}
        else:
            print("\n[查询条件] 最近的任务")
            # 查询最近的task_id
            latest_task = db.execute(text("""
                SELECT DISTINCT ingest_task_id 
                FROM staging_orders 
                WHERE ingest_task_id IS NOT NULL
                ORDER BY created_at DESC 
                LIMIT 1
            """)).scalar()
            
            if not latest_task:
                latest_task = db.execute(text("""
                    SELECT DISTINCT ingest_task_id 
                    FROM staging_product_metrics 
                    WHERE ingest_task_id IS NOT NULL
                    ORDER BY created_at DESC 
                    LIMIT 1
                """)).scalar()
            
            if not latest_task:
                print("[ERROR] 没有找到任何同步任务")
                return
            
            task_id = latest_task
            task_filter = "ingest_task_id = :task_id"
            params = {"task_id": task_id}
            print(f"[使用任务ID] {task_id}")
        
        # 2. 查询staging层数据量
        print("\n[1/3] 查询Raw层（staging表）数据量...")
        
        staging_orders_count = db.execute(text(f"""
            SELECT COUNT(*) FROM staging_orders WHERE {task_filter}
        """), params).scalar() or 0
        
        staging_metrics_count = db.execute(text(f"""
            SELECT COUNT(*) FROM staging_product_metrics WHERE {task_filter}
        """), params).scalar() or 0
        
        staging_inventory_count = db.execute(text(f"""
            SELECT COUNT(*) FROM staging_inventory WHERE {task_filter}
        """), params).scalar() or 0
        
        total_staging = staging_orders_count + staging_metrics_count + staging_inventory_count
        
        print(f"  - staging_orders: {staging_orders_count}行")
        print(f"  - staging_product_metrics: {staging_metrics_count}行")
        print(f"  - staging_inventory: {staging_inventory_count}行")
        print(f"  - 总计: {total_staging}行")
        
        # 3. 查询fact层数据量（通过file_id关联）
        print("\n[2/3] 查询Fact层（事实表）数据量...")
        
        if file_id:
            # 如果有file_id，直接查询
            fact_orders_count = db.execute(text("""
                SELECT COUNT(*) FROM fact_orders 
                WHERE file_id = :file_id
            """), {"file_id": file_id}).scalar() or 0
            
            fact_items_count = db.execute(text("""
                SELECT COUNT(*) FROM fact_order_items foi
                JOIN fact_orders fo ON foi.order_id = fo.order_id
                WHERE fo.file_id = :file_id
            """), {"file_id": file_id}).scalar() or 0
            
            fact_metrics_count = db.execute(text("""
                SELECT COUNT(*) FROM fact_product_metrics 
                WHERE file_id = :file_id
            """), {"file_id": file_id}).scalar() or 0
            
            print(f"  - fact_orders: {fact_orders_count}行")
            print(f"  - fact_order_items: {fact_items_count}行")
            print(f"  - fact_product_metrics: {fact_metrics_count}行")
            print(f"  - 总计: {fact_orders_count + fact_items_count + fact_metrics_count}行")
        else:
            # 如果没有file_id，通过staging表的file_id查询
            file_ids = db.execute(text(f"""
                SELECT DISTINCT file_id 
                FROM staging_orders 
                WHERE {task_filter} AND file_id IS NOT NULL
                UNION
                SELECT DISTINCT file_id 
                FROM staging_product_metrics 
                WHERE {task_filter} AND file_id IS NOT NULL
                UNION
                SELECT DISTINCT file_id 
                FROM staging_inventory 
                WHERE {task_filter} AND file_id IS NOT NULL
            """), params).fetchall()
            
            file_id_list = [fid[0] for fid in file_ids if fid[0]]
            
            if file_id_list:
                fact_orders_count = db.execute(text("""
                    SELECT COUNT(*) FROM fact_orders 
                    WHERE file_id = ANY(:file_ids)
                """), {"file_ids": file_id_list}).scalar() or 0
                
                fact_metrics_count = db.execute(text("""
                    SELECT COUNT(*) FROM fact_product_metrics 
                    WHERE file_id = ANY(:file_ids)
                """), {"file_ids": file_id_list}).scalar() or 0
                
                print(f"  - fact_orders: {fact_orders_count}行（关联{len(file_id_list)}个文件）")
                print(f"  - fact_product_metrics: {fact_metrics_count}行（关联{len(file_id_list)}个文件）")
                print(f"  - 总计: {fact_orders_count + fact_metrics_count}行")
            else:
                print("  - 无法关联文件ID，跳过fact层查询")
                fact_orders_count = fact_metrics_count = 0
        
        # 4. 查询物化视图数据量（通过日期范围）
        print("\n[3/3] 查询Semantic层（物化视图）数据量...")
        
        # 获取staging数据的日期范围
        date_range = db.execute(text(f"""
            SELECT 
                MIN(created_at::date) as min_date,
                MAX(created_at::date) as max_date
            FROM (
                SELECT created_at FROM staging_orders WHERE {task_filter}
                UNION ALL
                SELECT created_at FROM staging_product_metrics WHERE {task_filter}
                UNION ALL
                SELECT created_at FROM staging_inventory WHERE {task_filter}
            ) t
        """), params).fetchone()
        
        if date_range and date_range[0]:
            min_date, max_date = date_range[0], date_range[1]
            print(f"  - 数据日期范围: {min_date} 至 {max_date}")
            
            # 查询物化视图行数（示例：mv_product_management）
            mv_product_count = db.execute(text("""
                SELECT COUNT(*) FROM mv_product_management
                WHERE metric_date BETWEEN :min_date AND :max_date
            """), {"min_date": min_date, "max_date": max_date}).scalar() or 0
            
            mv_sales_count = db.execute(text("""
                SELECT COUNT(*) FROM mv_sales_day_shop_sku
                WHERE metric_date BETWEEN :min_date AND :max_date
            """), {"min_date": min_date, "max_date": max_date}).scalar() or 0
            
            print(f"  - mv_product_management: {mv_product_count}行")
            print(f"  - mv_sales_day_shop_sku: {mv_sales_count}行")
        else:
            print("  - 无法确定日期范围，跳过MV查询")
        
        # 5. 诊断报告
        print("\n" + "=" * 60)
        print("诊断报告")
        print("=" * 60)
        
        if total_staging == 0:
            print("[问题] Raw层没有数据")
            print("  - 可能原因：文件解析失败、数据验证全部失败")
            print("  - 建议：检查data_quarantine表，查看隔离原因")
        elif total_staging > 0 and fact_orders_count + fact_metrics_count == 0:
            print("[问题] Raw层有数据，但Fact层没有数据")
            print("  - 可能原因：字段映射失败、数据清洗失败、upsert失败")
            print("  - 建议：检查后端日志，查看upsert错误信息")
        elif fact_orders_count + fact_metrics_count > 0:
            print("[OK] 数据已成功入库到Fact层")
            print("  - 如果物化视图没有数据，请手动刷新物化视图")
        
        print("\n[建议]")
        print("  1. 检查data_quarantine表，查看是否有隔离数据")
        print("  2. 检查后端日志，查看详细错误信息")
        print("  3. 运行物化视图刷新：python scripts/verify_materialized_view_refresh_completeness.py")
        
    except Exception as e:
        logger.error(f"[ERROR] 诊断失败: {e}", exc_info=True)
        print(f"\n[ERROR] 诊断失败: {e}")
    finally:
        db.close()

def check_b_class_sync_health():
    """
    ⭐ v4.11.5新增：批量健康检查功能
    检查Raw/Fact/MV三层数据完整性，数据隔离区统计，物化视图刷新状态
    """
    db = SessionLocal()
    try:
        print("=" * 60)
        print("B类数据同步健康检查")
        print("=" * 60)
        
        # 1. 检查Raw层（staging表）数据完整性
        print("\n[1/4] 检查Raw层（staging表）数据完整性...")
        
        staging_orders_total = db.execute(text("""
            SELECT COUNT(*) FROM staging_orders
        """)).scalar() or 0
        
        staging_metrics_total = db.execute(text("""
            SELECT COUNT(*) FROM staging_product_metrics
        """)).scalar() or 0
        
        staging_inventory_total = db.execute(text("""
            SELECT COUNT(*) FROM staging_inventory
        """)).scalar() or 0
        
        staging_with_task_id = db.execute(text("""
            SELECT COUNT(*) FROM staging_orders WHERE ingest_task_id IS NOT NULL
            UNION ALL
            SELECT COUNT(*) FROM staging_product_metrics WHERE ingest_task_id IS NOT NULL
            UNION ALL
            SELECT COUNT(*) FROM staging_inventory WHERE ingest_task_id IS NOT NULL
        """)).fetchall()
        staging_tracked = sum(row[0] for row in staging_with_task_id if row[0])
        
        print(f"  - staging_orders: {staging_orders_total}行")
        print(f"  - staging_product_metrics: {staging_metrics_total}行")
        print(f"  - staging_inventory: {staging_inventory_total}行")
        print(f"  - 总计: {staging_orders_total + staging_metrics_total + staging_inventory_total}行")
        print(f"  - 已追踪（有task_id）: {staging_tracked}行")
        
        if staging_tracked < (staging_orders_total + staging_metrics_total + staging_inventory_total) * 0.9:
            print("  [警告] 部分staging数据缺少task_id追踪")
        
        # 2. 检查Fact层数据完整性
        print("\n[2/4] 检查Fact层（事实表）数据完整性...")
        
        fact_orders_total = db.execute(text("""
            SELECT COUNT(*) FROM fact_orders
        """)).scalar() or 0
        
        fact_metrics_total = db.execute(text("""
            SELECT COUNT(*) FROM fact_product_metrics
        """)).scalar() or 0
        
        print(f"  - fact_orders: {fact_orders_total}行")
        print(f"  - fact_product_metrics: {fact_metrics_total}行")
        print(f"  - 总计: {fact_orders_total + fact_metrics_total}行")
        
        # 3. 检查数据隔离区统计
        print("\n[3/4] 检查数据隔离区统计...")
        
        quarantine_total = db.execute(text("""
            SELECT COUNT(*) FROM data_quarantine
        """)).scalar() or 0
        
        quarantine_by_type = db.execute(text("""
            SELECT error_type, COUNT(*) as count
            FROM data_quarantine
            GROUP BY error_type
            ORDER BY count DESC
            LIMIT 10
        """)).fetchall()
        
        print(f"  - 隔离数据总数: {quarantine_total}行")
        if quarantine_by_type:
            print("  - 按错误类型统计:")
            for error_type, count in quarantine_by_type:
                print(f"    - {error_type}: {count}行")
        
        # 4. 检查MV层（物化视图）刷新状态
        print("\n[4/4] 检查MV层（物化视图）刷新状态...")
        
        mv_refresh_log = db.execute(text("""
            SELECT view_name, refresh_completed_at, duration_seconds, row_count, status
            FROM mv_refresh_log
            ORDER BY refresh_completed_at DESC
            LIMIT 10
        """)).fetchall()
        
        if mv_refresh_log:
            print("  - 最近10次刷新记录:")
            for view_name, completed_at, duration, row_count, status in mv_refresh_log:
                status_icon = "[OK]" if status == "success" else "[FAIL]"
                print(f"    {status_icon} {view_name}: {row_count}行, {duration:.2f}秒, {completed_at}")
        else:
            print("  - 没有找到刷新记录")
        
        # 5. 健康检查总结
        print("\n" + "=" * 60)
        print("健康检查总结")
        print("=" * 60)
        
        issues = []
        if staging_tracked < (staging_orders_total + staging_metrics_total + staging_inventory_total) * 0.9:
            issues.append("部分staging数据缺少task_id追踪")
        
        if quarantine_total > 1000:
            issues.append(f"隔离数据过多（{quarantine_total}行），建议检查数据质量")
        
        if not mv_refresh_log:
            issues.append("物化视图没有刷新记录，建议手动刷新")
        
        if issues:
            print("[发现问题]")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print("[OK] 未发现明显问题")
        
        print("\n[建议]")
        print("  1. 定期检查数据隔离区，修复数据质量问题")
        print("  2. 确保物化视图定期刷新（每天凌晨2点自动刷新）")
        print("  3. 监控staging表数据量，避免数据积压")
        
    except Exception as e:
        logger.error(f"[ERROR] 健康检查失败: {e}", exc_info=True)
        print(f"\n[ERROR] 健康检查失败: {e}")
    finally:
        db.close()

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='数据入库管道诊断脚本')
    parser.add_argument('--task-id', type=str, help='同步任务ID')
    parser.add_argument('--file-id', type=int, help='文件ID')
    parser.add_argument('--health-check', action='store_true', help='执行批量健康检查')
    
    args = parser.parse_args()
    
    if args.health_check:
        check_b_class_sync_health()
    else:
        diagnose_pipeline(task_id=args.task_id, file_id=args.file_id)

