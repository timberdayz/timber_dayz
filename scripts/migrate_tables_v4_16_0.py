#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v4.16.0表结构迁移脚本

功能：
1. 将fact_raw_data_traffic_*表的数据迁移到fact_raw_data_analytics_*表
2. 将fact_raw_data_services_*表的数据按sub_domain拆分到新表
   - ai_assistant子类型 -> fact_raw_data_services_ai_assistant_*
   - agent子类型 -> fact_raw_data_services_agent_*

使用方法：
    python scripts/migrate_tables_v4_16_0.py
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, select
from backend.models.database import get_db
from modules.core.db import (
    CatalogFile,
    FactRawDataTrafficDaily,
    FactRawDataTrafficWeekly,
    FactRawDataTrafficMonthly,
    FactRawDataAnalyticsDaily,
    FactRawDataAnalyticsWeekly,
    FactRawDataAnalyticsMonthly,
    FactRawDataServicesDaily,
    FactRawDataServicesWeekly,
    FactRawDataServicesMonthly,
    FactRawDataServicesAiAssistantDaily,
    FactRawDataServicesAiAssistantWeekly,
    FactRawDataServicesAiAssistantMonthly,
    FactRawDataServicesAgentWeekly,
    FactRawDataServicesAgentMonthly,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)


def safe_print(text: str):
    """安全打印（Windows兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


def migrate_traffic_to_analytics(db):
    """将traffic域数据迁移到analytics域"""
    safe_print("\n[Step 1] 迁移traffic域数据到analytics域...")
    
    # 迁移daily表
    safe_print("  迁移fact_raw_data_traffic_daily -> fact_raw_data_analytics_daily...")
    result = db.execute(
        text("""
            INSERT INTO fact_raw_data_analytics_daily 
            (platform_code, shop_id, data_domain, granularity, metric_date, file_id, 
             raw_data, header_columns, data_hash, ingest_timestamp, currency_code)
            SELECT platform_code, shop_id, 'analytics', granularity, metric_date, file_id,
                   raw_data, header_columns, data_hash, ingest_timestamp, currency_code
            FROM fact_raw_data_traffic_daily
            ON CONFLICT (data_domain, granularity, data_hash) DO NOTHING
        """)
    )
    daily_count = result.rowcount
    safe_print(f"    迁移了 {daily_count} 条记录")
    
    # 迁移weekly表
    safe_print("  迁移fact_raw_data_traffic_weekly -> fact_raw_data_analytics_weekly...")
    result = db.execute(
        text("""
            INSERT INTO fact_raw_data_analytics_weekly 
            (platform_code, shop_id, data_domain, granularity, metric_date, file_id, 
             raw_data, header_columns, data_hash, ingest_timestamp, currency_code)
            SELECT platform_code, shop_id, 'analytics', granularity, metric_date, file_id,
                   raw_data, header_columns, data_hash, ingest_timestamp, currency_code
            FROM fact_raw_data_traffic_weekly
            ON CONFLICT (data_domain, granularity, data_hash) DO NOTHING
        """)
    )
    weekly_count = result.rowcount
    safe_print(f"    迁移了 {weekly_count} 条记录")
    
    # 迁移monthly表
    safe_print("  迁移fact_raw_data_traffic_monthly -> fact_raw_data_analytics_monthly...")
    result = db.execute(
        text("""
            INSERT INTO fact_raw_data_analytics_monthly 
            (platform_code, shop_id, data_domain, granularity, metric_date, file_id, 
             raw_data, header_columns, data_hash, ingest_timestamp, currency_code)
            SELECT platform_code, shop_id, 'analytics', granularity, metric_date, file_id,
                   raw_data, header_columns, data_hash, ingest_timestamp, currency_code
            FROM fact_raw_data_traffic_monthly
            ON CONFLICT (data_domain, granularity, data_hash) DO NOTHING
        """)
    )
    monthly_count = result.rowcount
    safe_print(f"    迁移了 {monthly_count} 条记录")
    
    db.commit()
    safe_print(f"  [OK] traffic域数据迁移完成: daily={daily_count}, weekly={weekly_count}, monthly={monthly_count}")


def migrate_services_by_sub_domain(db):
    """将services域数据按sub_domain拆分"""
    safe_print("\n[Step 2] 迁移services域数据按sub_domain拆分...")
    
    # 查询所有services域的文件，获取sub_domain
    services_files = db.query(CatalogFile).filter(
        CatalogFile.data_domain == 'services'
    ).all()
    
    safe_print(f"  找到 {len(services_files)} 个services域文件")
    
    # 按sub_domain分组
    ai_assistant_file_ids = set()
    agent_file_ids = set()
    unknown_file_ids = set()
    
    for file_record in services_files:
        sub_domain = (file_record.sub_domain or '').lower()
        if sub_domain == 'ai_assistant':
            ai_assistant_file_ids.add(file_record.id)
        elif sub_domain == 'agent':
            agent_file_ids.add(file_record.id)
        else:
            unknown_file_ids.add(file_record.id)
    
    safe_print(f"  AI助手子类型文件: {len(ai_assistant_file_ids)} 个")
    safe_print(f"  人工服务子类型文件: {len(agent_file_ids)} 个")
    safe_print(f"  未知子类型文件: {len(unknown_file_ids)} 个")
    
    # 迁移AI助手子类型 - daily
    if ai_assistant_file_ids:
        safe_print("  迁移AI助手子类型 - daily...")
        file_ids_str = ','.join(map(str, ai_assistant_file_ids))
        result = db.execute(
            text(f"""
                INSERT INTO fact_raw_data_services_ai_assistant_daily 
                (platform_code, shop_id, data_domain, sub_domain, granularity, metric_date, file_id, 
                 raw_data, header_columns, data_hash, ingest_timestamp, currency_code)
                SELECT platform_code, shop_id, 'services', 'ai_assistant', granularity, metric_date, file_id,
                       raw_data, header_columns, data_hash, ingest_timestamp, currency_code
                FROM fact_raw_data_services_daily
                WHERE file_id IN ({file_ids_str})
                ON CONFLICT (data_domain, sub_domain, granularity, data_hash) DO NOTHING
            """)
        )
        safe_print(f"    迁移了 {result.rowcount} 条记录")
        
        # weekly
        safe_print("  迁移AI助手子类型 - weekly...")
        result = db.execute(
            text(f"""
                INSERT INTO fact_raw_data_services_ai_assistant_weekly 
                (platform_code, shop_id, data_domain, sub_domain, granularity, metric_date, file_id, 
                 raw_data, header_columns, data_hash, ingest_timestamp, currency_code)
                SELECT platform_code, shop_id, 'services', 'ai_assistant', granularity, metric_date, file_id,
                       raw_data, header_columns, data_hash, ingest_timestamp, currency_code
                FROM fact_raw_data_services_weekly
                WHERE file_id IN ({file_ids_str})
                ON CONFLICT (data_domain, sub_domain, granularity, data_hash) DO NOTHING
            """)
        )
        safe_print(f"    迁移了 {result.rowcount} 条记录")
        
        # monthly
        safe_print("  迁移AI助手子类型 - monthly...")
        result = db.execute(
            text(f"""
                INSERT INTO fact_raw_data_services_ai_assistant_monthly 
                (platform_code, shop_id, data_domain, sub_domain, granularity, metric_date, file_id, 
                 raw_data, header_columns, data_hash, ingest_timestamp, currency_code)
                SELECT platform_code, shop_id, 'services', 'ai_assistant', granularity, metric_date, file_id,
                       raw_data, header_columns, data_hash, ingest_timestamp, currency_code
                FROM fact_raw_data_services_monthly
                WHERE file_id IN ({file_ids_str})
                ON CONFLICT (data_domain, sub_domain, granularity, data_hash) DO NOTHING
            """)
        )
        safe_print(f"    迁移了 {result.rowcount} 条记录")
    
    # 迁移人工服务子类型 - weekly
    if agent_file_ids:
        safe_print("  迁移人工服务子类型 - weekly...")
        file_ids_str = ','.join(map(str, agent_file_ids))
        result = db.execute(
            text(f"""
                INSERT INTO fact_raw_data_services_agent_weekly 
                (platform_code, shop_id, data_domain, sub_domain, granularity, metric_date, file_id, 
                 raw_data, header_columns, data_hash, ingest_timestamp, currency_code)
                SELECT platform_code, shop_id, 'services', 'agent', granularity, metric_date, file_id,
                       raw_data, header_columns, data_hash, ingest_timestamp, currency_code
                FROM fact_raw_data_services_weekly
                WHERE file_id IN ({file_ids_str})
                ON CONFLICT (data_domain, sub_domain, granularity, data_hash) DO NOTHING
            """)
        )
        safe_print(f"    迁移了 {result.rowcount} 条记录")
        
        # monthly
        safe_print("  迁移人工服务子类型 - monthly...")
        result = db.execute(
            text(f"""
                INSERT INTO fact_raw_data_services_agent_monthly 
                (platform_code, shop_id, data_domain, sub_domain, granularity, metric_date, file_id, 
                 raw_data, header_columns, data_hash, ingest_timestamp, currency_code)
                SELECT platform_code, shop_id, 'services', 'agent', granularity, metric_date, file_id,
                       raw_data, header_columns, data_hash, ingest_timestamp, currency_code
                FROM fact_raw_data_services_monthly
                WHERE file_id IN ({file_ids_str})
                ON CONFLICT (data_domain, sub_domain, granularity, data_hash) DO NOTHING
            """)
        )
        safe_print(f"    迁移了 {result.rowcount} 条记录")
    
    if unknown_file_ids:
        safe_print(f"  [WARNING] 发现 {len(unknown_file_ids)} 个未知子类型的文件，需要手动处理")
        for file_id in list(unknown_file_ids)[:5]:  # 只显示前5个
            file_record = db.query(CatalogFile).filter(CatalogFile.id == file_id).first()
            if file_record:
                safe_print(f"    文件ID={file_id}, 文件名={file_record.file_name}, sub_domain={file_record.sub_domain}")
    
    db.commit()
    safe_print("  [OK] services域数据拆分完成")


def main():
    """主函数"""
    safe_print("=" * 60)
    safe_print("v4.16.0表结构迁移脚本")
    safe_print("=" * 60)
    
    db = next(get_db())
    
    try:
        # Step 1: 迁移traffic到analytics
        migrate_traffic_to_analytics(db)
        
        # Step 2: 迁移services按sub_domain拆分
        migrate_services_by_sub_domain(db)
        
        safe_print("\n" + "=" * 60)
        safe_print("[OK] 迁移完成！")
        safe_print("=" * 60)
        
    except Exception as e:
        db.rollback()
        safe_print(f"\n[ERROR] 迁移失败: {e}")
        logger.exception("迁移失败")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

