#!/usr/bin/env python3
"""
===================================================
西虹ERP系统 - 数据库表初始化脚本
===================================================
功能：
1. 基于SQLAlchemy模型创建所有表
2. 插入示例数据（4个平台账号）
3. 创建必要的索引和约束
4. 支持幂等性（可重复运行）

使用方式：
python docker/postgres/init-tables.py
===================================================
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

# 导入数据库模型
from backend.models.database import (
    Base,
    Account,
    DataFile,
    FieldMapping,
    DataRecord,
    CollectionTask,
    DimPlatform,
    DimShop,
    DimProduct,
    RawIngestion,
    DataQuarantine,
    StagingOrders,
    StagingProductMetrics,
    FactSalesOrders,
    FactProductMetrics,
    MappingSession
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_database_url():
    """获取数据库连接URL"""
    # 从环境变量获取
    database_url = os.getenv(
        'DATABASE_URL',
        'postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp'
    )
    logger.info(f"数据库连接: {database_url.split('@')[-1]}")
    return database_url


def create_all_tables(engine):
    """创建所有表"""
    logger.info("=" * 60)
    logger.info("开始创建数据库表...")
    logger.info("=" * 60)
    
    try:
        # 创建所有表
        Base.metadata.create_all(bind=engine)
        logger.info("✅ 所有表创建成功")
        
        # 输出创建的表列表
        from sqlalchemy import inspect
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        logger.info(f"📊 共创建 {len(tables)} 个表:")
        for table in sorted(tables):
            logger.info(f"   - {table}")
            
        return True
    except Exception as e:
        logger.error(f"❌ 创建表失败: {e}")
        return False


def insert_sample_data(engine):
    """插入示例数据"""
    logger.info("\n" + "=" * 60)
    logger.info("插入示例数据...")
    logger.info("=" * 60)
    
    from sqlalchemy.orm import sessionmaker
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        # 1. 插入平台维度数据（使用原生SQL，更健壮）
        platforms_data = [
            ("SHOPEE", "Shopee"),
            ("TIKTOK", "TikTok Shop"),
            ("AMAZON", "Amazon"),
            ("MIAOSHOU", "妙手ERP"),
        ]
        
        for code, name in platforms_data:
            try:
                # 使用INSERT ... ON CONFLICT DO NOTHING（PostgreSQL）
                from sqlalchemy import text
                sql = text("""
                    INSERT INTO dim_platform (platform_code, name) 
                    VALUES (:code, :name)
                    ON CONFLICT (platform_code) DO NOTHING
                """)
                session.execute(sql, {"code": code, "name": name})
                logger.info(f"   ✅ 添加平台: {name}")
            except Exception as e:
                logger.info(f"   ℹ️  平台已存在或跳过: {name}")
        
        session.commit()
        
        # 2. 插入示例账号数据
        logger.info("\n插入账号数据...")
        
        accounts_count = session.query(Account).count()
        if accounts_count == 0:
            accounts = [
                Account(
                    platform="SHOPEE",
                    username="shopee_main",
                    password="encrypted_password_1",
                    login_url="https://shopee.com/login",
                    status="online",
                    health_score=95.0,
                    notes="主要Shopee账号"
                ),
                Account(
                    platform="TIKTOK",
                    username="tiktok_shop_1",
                    password="encrypted_password_2",
                    login_url="https://seller.tiktok.com/login",
                    status="online",
                    health_score=88.0,
                    notes="TikTok小店账号"
                ),
                Account(
                    platform="AMAZON",
                    username="amazon_seller",
                    password="encrypted_password_3",
                    login_url="https://sellercentral.amazon.com/login",
                    status="offline",
                    health_score=92.0,
                    notes="Amazon美国站账号"
                ),
                Account(
                    platform="MIAOSHOU",
                    username="miaoshou_erp",
                    password="encrypted_password_4",
                    login_url="https://miaoshou.com/login",
                    status="online",
                    health_score=98.0,
                    notes="妙手ERP主账号"
                ),
            ]
            
            session.add_all(accounts)
            session.commit()
            logger.info(f"   ✅ 添加 {len(accounts)} 个账号")
        else:
            logger.info(f"   ℹ️  账号已存在 ({accounts_count} 条)，跳过")
        
        # 3. 插入示例数据记录
        logger.info("\n插入数据记录...")
        
        records_count = session.query(DataRecord).count()
        if records_count == 0:
            records = [
                DataRecord(
                    platform="SHOPEE",
                    data_type="商品数据",
                    record_count=2500,
                    quality_score=95.0,
                    status="active"
                ),
                DataRecord(
                    platform="TIKTOK",
                    data_type="订单数据",
                    record_count=1800,
                    quality_score=88.0,
                    status="active"
                ),
                DataRecord(
                    platform="AMAZON",
                    data_type="财务数据",
                    record_count=1200,
                    quality_score=92.0,
                    status="active"
                ),
                DataRecord(
                    platform="MIAOSHOU",
                    data_type="流量数据",
                    record_count=950,
                    quality_score=98.0,
                    status="active"
                ),
            ]
            
            session.add_all(records)
            session.commit()
            logger.info(f"   ✅ 添加 {len(records)} 条数据记录")
        else:
            logger.info(f"   ℹ️  数据记录已存在 ({records_count} 条)，跳过")
        
        logger.info("✅ 示例数据插入完成")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 插入示例数据失败: {e}")
        session.rollback()
        return False
    finally:
        session.close()


def create_indexes(engine):
    """创建额外的索引（优化查询性能）"""
    logger.info("\n" + "=" * 60)
    logger.info("创建性能优化索引...")
    logger.info("=" * 60)
    
    try:
        with engine.connect() as conn:
            # 为常用查询创建复合索引
            indexes = [
                # 数据文件索引
                "CREATE INDEX IF NOT EXISTS idx_data_files_platform_type ON data_files(platform, data_type)",
                "CREATE INDEX IF NOT EXISTS idx_data_files_processed ON data_files(processed)",
                
                # 字段映射索引
                "CREATE INDEX IF NOT EXISTS idx_field_mappings_file_platform ON field_mappings(file_id, platform)",
                
                # 账号索引
                "CREATE INDEX IF NOT EXISTS idx_accounts_platform_status ON accounts(platform, status)",
                
                # 采集任务索引
                "CREATE INDEX IF NOT EXISTS idx_collection_tasks_platform_status ON collection_tasks(platform, status)",
                
                # 时间戳索引（用于数据清理）
                "CREATE INDEX IF NOT EXISTS idx_data_files_created ON data_files(created_at)",
                "CREATE INDEX IF NOT EXISTS idx_collection_tasks_created ON collection_tasks(created_at)",
            ]
            
            for sql in indexes:
                try:
                    conn.execute(text(sql))
                    index_name = sql.split("idx_")[1].split()[0]
                    logger.info(f"   ✅ 创建索引: idx_{index_name}")
                except Exception as e:
                    logger.warning(f"   ⚠️  索引可能已存在: {e}")
            
            conn.commit()
            
        logger.info("✅ 索引创建完成")
        return True
        
    except Exception as e:
        logger.error(f"❌ 创建索引失败: {e}")
        return False


def main():
    """主函数"""
    logger.info("\n" + "=" * 60)
    logger.info("西虹ERP系统 - 数据库表初始化")
    logger.info("=" * 60)
    logger.info(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 获取数据库连接
    database_url = get_database_url()
    
    try:
        # 创建引擎
        engine = create_engine(database_url, echo=False)
        
        # 测试连接
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            logger.info(f"✅ 数据库连接成功")
            logger.info(f"📌 PostgreSQL版本: {version.split(',')[0]}")
        
        # 执行初始化
        success = True
        success = success and create_all_tables(engine)
        success = success and insert_sample_data(engine)
        success = success and create_indexes(engine)
        
        if success:
            logger.info("\n" + "=" * 60)
            logger.info("🎉 数据库初始化全部完成！")
            logger.info("=" * 60)
            logger.info("下一步:")
            logger.info("1. 启动后端服务: uvicorn backend.main:app --reload")
            logger.info("2. 启动前端服务: cd frontend && npm run dev")
            logger.info("3. 访问系统: http://localhost:5174")
            logger.info("=" * 60)
            return 0
        else:
            logger.error("\n❌ 数据库初始化过程中出现错误")
            return 1
            
    except Exception as e:
        logger.error(f"\n❌ 数据库初始化失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

