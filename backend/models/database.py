"""
数据库配置和连接管理 - 西虹ERP系统

职责:
- 数据库引擎配置（PostgreSQL/SQLite）
- Session管理和连接池（同步+异步）
- FastAPI依赖注入（get_db/get_async_db函数）

架构规范（v4.18.2）:
- [OK] 所有模型定义在 modules/core/db/schema.py（单一数据源）
- [OK] 本文件只负责引擎配置和Session管理
- [OK] 不重复定义任何模型
- [OK] 符合 Single Source of Truth 原则
- [OK] 符合 .cursorrules 架构规范
- [OK] 支持同步/异步双模式（过渡期）

依赖方向:
  Frontend -> backend/routers -> backend/models/database -> modules/core/db

版本: v4.18.2
更新: 2026-01-01 - 添加异步SQLAlchemy支持
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import Generator, AsyncGenerator
from urllib.parse import urlparse, urlunparse
import asyncio
import logging

# ==================== 从core导入统一Schema（Single Source of Truth） ====================

from modules.core.db import (
    Base,
    # 维度表
    DimPlatform,
    DimShop,
    DimProduct,
    DimProductMaster,
    BridgeProductKeys,
    DimCurrencyRate,
    # 事实表
    # [WARN] v4.6.0 DSS架构重构：以下表已废弃，但仍在使用中（31个文件引用）
    # 新数据应写入fact_raw_data_*表（按data_domain+granularity分表）
    # 计划在Phase 6.1中删除（需要先完成数据迁移）
    FactOrder,  # 已废弃，使用fact_raw_data_orders_*替代
    FactOrderItem,  # 已废弃，使用fact_raw_data_orders_*替代
    FactProductMetric,  # 已废弃，使用fact_raw_data_products_*替代
    # 管理表
    CatalogFile,
    DataQuarantine,
    Account,
    CollectionTask,
    DataFile,
    DataRecord,
    FieldMapping,
    MappingSession,
    # 暂存表
    StagingOrders,
    StagingProductMetrics,
    StagingInventory,  # v4.11.4新增：库存数据暂存表
    # 物化视图管理
    MaterializedViewRefreshLog,  # v4.11.4新增：物化视图刷新日志表
)

from backend.utils.config import get_settings

logger = logging.getLogger(__name__)

# ==================== 数据库URL转换函数 ====================

def get_async_database_url(database_url: str) -> str:
    """
    将同步数据库URL转换为异步URL
    
    支持的数据库类型：
    - PostgreSQL: postgresql:// -> postgresql+asyncpg://
    - SQLite: sqlite:// -> sqlite+aiosqlite://
    
    Args:
        database_url: 同步数据库URL
        
    Returns:
        异步数据库URL
        
    Raises:
        ValueError: 不支持的数据库类型
    """
    parsed = urlparse(database_url)
    scheme = parsed.scheme.split('+')[0]  # 移除现有驱动（如 +psycopg2）
    
    # 根据数据库类型选择异步驱动
    if scheme == "postgresql":
        new_scheme = "postgresql+asyncpg"
    elif scheme == "sqlite":
        new_scheme = "sqlite+aiosqlite"
    else:
        raise ValueError(f"不支持的数据库类型: {scheme}")
    
    new_parsed = parsed._replace(scheme=new_scheme)
    return urlunparse(new_parsed)

# ==================== 数据库引擎配置 ====================

settings = get_settings()
DATABASE_URL = settings.DATABASE_URL

# SQLite 与 PostgreSQL 的连接参数区分
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    pool_config = {}
else:
    # PostgreSQL连接池配置（第二阶段优化）
    # v4.12.0: 配置search_path以支持多schema访问
    connect_args = {
        "options": "-c statement_timeout=30000 -c idle_in_transaction_session_timeout=300000 -c search_path=public,b_class,a_class,c_class,core,finance"
    }
    pool_config = {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_timeout": settings.DB_POOL_TIMEOUT,
        "pool_recycle": settings.DB_POOL_RECYCLE,
        "pool_pre_ping": True,  # 连接前测试可用性
    }

# 创建数据库引擎
engine = create_engine(
    DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    connect_args=connect_args,
    **pool_config
)

# 创建Session工厂
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

logger.info(f"[sync] 数据库连接已配置: {DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else 'SQLite'}")

# ==================== 异步数据库引擎配置（v4.18.2新增） ====================

ASYNC_DATABASE_URL = get_async_database_url(DATABASE_URL)

# SQLite 不支持连接池，使用简化配置
if ASYNC_DATABASE_URL.startswith("sqlite"):
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        echo=settings.DATABASE_ECHO,
        # SQLite 不需要连接池配置
    )
else:
    # PostgreSQL 支持连接池，使用完整配置
    # [*] v4.19.0更新：使用环境感知的配置（与同步引擎保持一致）
    async_engine = create_async_engine(
        ASYNC_DATABASE_URL,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=True,  # 连接有效性检测
        echo=settings.DATABASE_ECHO,
    )

# [*] v4.18.2修复：asyncpg 需要通过事件监听器设置 search_path
# asyncpg 不支持通过 connect_args 传递 options
from sqlalchemy import event, text

@event.listens_for(async_engine.sync_engine, "connect")
def set_search_path_on_connect(dbapi_connection, connection_record):
    """每次连接建立时设置 search_path"""
    cursor = dbapi_connection.cursor()
    cursor.execute("SET search_path TO public, b_class, a_class, c_class, core, finance")
    cursor.close()

logger.info("[async] 已配置 asyncpg search_path 事件监听器")

# 创建异步Session工厂
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False
)

logger.info(f"[async] 异步数据库连接已配置: {ASYNC_DATABASE_URL.split('@')[-1] if '@' in ASYNC_DATABASE_URL else 'SQLite'}")

# ==================== FastAPI依赖注入 ====================

def get_db() -> Generator[Session, None, None]:
    """
    FastAPI数据库Session依赖注入（同步版本）
    
    Usage:
        @router.get("/items")
        async def get_items(db: Session = Depends(get_db)):
            items = db.query(CatalogFile).all()
            return items
    
    Yields:
        Session: SQLAlchemy数据库会话
        
    Note:
        v4.18.2: 此函数保留用于过渡期，新代码请使用 get_async_db()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI数据库Session依赖注入（异步版本，v4.18.2新增）
    
    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_async_db)):
            result = await db.execute(select(CatalogFile))
            items = result.scalars().all()
            return items
    
    Yields:
        AsyncSession: SQLAlchemy异步数据库会话
        
    Note:
        事务策略说明：
        - 成功时自动 commit（请求结束后）
        - 异常时自动 rollback
        - 如果路由函数内已手动 commit，此处再次 commit 是无害的（空操作）
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()  # 自动提交（如果有未提交的更改）
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def init_db():
    """
    初始化数据库（创建所有表）
    
    注意：
    - 生产环境：禁止使用此函数，必须使用 Alembic 迁移（alembic upgrade head）
    - 开发环境：可以使用此函数快速创建表（但不推荐）
    - 此函数仅作为辅助，不保证表结构完整性和迁移历史
    
    推荐方式：使用 Alembic 迁移
    """
    import os
    
    # 生产环境禁止使用
    environment = os.getenv("ENVIRONMENT", "").lower()
    if environment == "production":
        logger.warning(
            "[WARN] 生产环境禁止使用 init_db()，请使用 Alembic 迁移: alembic upgrade head"
        )
        return
    
    # 开发环境：仅作为快速原型，记录警告
    logger.warning(
        "[WARN] 使用 init_db() 创建表，这不是推荐方式。"
        "请使用 Alembic 迁移: alembic upgrade head"
    )
    
    missing_tables = []
    created_tables = []
    
    try:
        # 执行前检查
        from sqlalchemy import inspect
        inspector = inspect(engine)
        existing_before = set(inspector.get_table_names())
        
        # 创建表
        Base.metadata.create_all(bind=engine)
        
        # 执行后验证
        existing_after = set(inspector.get_table_names())
        expected_tables = set(Base.metadata.tables.keys())
        
        created_tables = existing_after - existing_before
        missing_tables = expected_tables - existing_after
        
        if missing_tables:
            logger.error(
                f"[ERROR] 以下表创建失败: {', '.join(sorted(missing_tables))}"
            )
            # 开发环境也抛出错误，让开发者知道问题
            raise RuntimeError(f"Missing tables: {', '.join(sorted(missing_tables))}")
        
        logger.info(
            f"[OK] 数据库表初始化完成（开发模式）: 创建 {len(created_tables)} 张表, "
            f"总计 {len(existing_after)} 张表"
        )
            
    except Exception as e:
        error_str = str(e)
        # 区分真正的错误和可以忽略的重复错误
        if "already exists" in error_str.lower() or "duplicate" in error_str.lower():
            # 索引/约束重复是可以接受的
            logger.warning(f"数据库对象可能已存在，跳过创建: {e}")
        else:
            # 其他错误必须抛出
            logger.error(f"[ERROR] init_db() 失败: {e}")
            raise


def verify_schema_completeness():
    """
    验证数据库表结构完整性（生产环境必须）
    
    检查：
    1. schema.py 中定义的所有表是否都存在
    2.  Alembic 迁移状态是否与代码一致
    
    Returns:
        dict: {
            "all_tables_exist": bool,
            "missing_tables": List[str],
            "migration_status": str,
            "current_revision": str,
            "head_revision": str,
            "expected_table_count": int,
            "actual_table_count": int
        }
    """
    from sqlalchemy import inspect
    
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    
    # 获取 schema.py 中定义的所有表
    expected_tables = set(Base.metadata.tables.keys())
    
    missing_tables = expected_tables - existing_tables
    
    # 检查 Alembic 版本
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.runtime.migration import MigrationContext
        
        alembic_cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(alembic_cfg)
        context = MigrationContext.configure(engine.connect())
        current_rev = context.get_current_revision()
        head_rev = script.get_current_head()
        
        migration_status = "up_to_date" if current_rev == head_rev else "outdated"
        if current_rev is None:
            migration_status = "not_initialized"
    except Exception as e:
        migration_status = f"error: {str(e)}"
        current_rev = None
        head_rev = None
    
    return {
        "all_tables_exist": len(missing_tables) == 0,
        "missing_tables": sorted(list(missing_tables)),
        "migration_status": migration_status,
        "current_revision": current_rev,
        "head_revision": head_rev,
        "expected_table_count": len(expected_tables),
        "actual_table_count": len(existing_tables)
    }


def warm_up_pool(pool_size: int = 10):
    """
    预热数据库连接池（同步版本，v4.1.0新增）
    
    通过预先创建和测试连接，避免首次请求时的冷启动延迟。
    
    Args:
        pool_size: 预热连接数量，默认10个
    
    Returns:
        None
    
    Raises:
        Exception: 连接池预热失败时抛出异常
    """
    from sqlalchemy import text
    
    connections = []
    try:
        logger.info(f"[sync] 开始预热连接池（目标: {pool_size}个连接）")
        
        # 创建连接并执行测试查询
        for i in range(pool_size):
            conn = engine.connect()
            conn.execute(text("SELECT 1"))
            connections.append(conn)
        
        # 关闭所有连接（返回连接池）
        for conn in connections:
            conn.close()
        
        logger.info(f"[sync] 连接池预热完成: {pool_size}个连接已测试")
        
    except Exception as e:
        logger.error(f"[sync] 连接池预热失败: {e}")
        # 清理已创建的连接
        for conn in connections:
            try:
                conn.close()
            except:
                pass
        raise


async def warm_up_async_pool(pool_size: int = 10):
    """
    预热异步数据库连接池（v4.18.2新增）
    
    通过并发创建和测试连接，避免首次请求时的冷启动延迟。
    
    Args:
        pool_size: 预热连接数量，默认10个
    
    Returns:
        None
    
    Raises:
        Exception: 连接池预热失败时抛出异常
        
    Note:
        必须并发创建多个连接，才能真正预热连接池。
        单个 session 循环执行只会复用同一连接。
    """
    from sqlalchemy import text
    
    async def test_single_connection(i: int):
        """测试单个连接"""
        session = AsyncSessionLocal()
        try:
            result = await session.execute(text("SELECT 1"))
            # [*] 修复：fetchone() 不需要 await（它返回 Row，不是协程）
            result.fetchone()
        except Exception as e:
            logger.warning(f"[async] 连接 {i} 测试失败: {e}")
            raise
        finally:
            try:
                await session.close()
            except Exception:
                pass  # 忽略关闭时的错误
    
    try:
        logger.info(f"[async] 开始预热异步连接池（目标: {pool_size}个连接）")
        
        # 并发创建多个连接，真正预热连接池
        tasks = [test_single_connection(i) for i in range(pool_size)]
        await asyncio.gather(*tasks)
        
        logger.info(f"[async] 异步连接池预热完成: {pool_size}个连接已创建")
    except Exception as e:
        logger.error(f"[async] 异步连接池预热失败: {e}")
        raise


# ==================== 导出接口 ====================

# 导出给backend/routers使用
# 注意：所有模型都来自 modules/core/db/schema.py，此处只是重新导出
__all__ = [
    # 数据库配置（同步）
    "Base",
    "engine",
    "SessionLocal",
    "get_db",
    "init_db",
    "warm_up_pool",  # v4.1.0新增
    # 数据库配置（异步，v4.18.2新增）
    "async_engine",
    "AsyncSessionLocal",
    "get_async_db",
    "warm_up_async_pool",
    "get_async_database_url",
    # 维度表
    "DimPlatform",
    "DimShop",
    "DimProduct",
    "DimProductMaster",
    "BridgeProductKeys",
    "DimCurrencyRate",
    # 事实表
    # [WARN] v4.6.0 DSS架构重构：以下表已废弃，但仍在使用中
    "FactOrder",  # 已废弃，使用fact_raw_data_orders_*替代
    "FactOrderItem",  # 已废弃，使用fact_raw_data_orders_*替代
    "FactProductMetric",  # 已废弃，使用fact_raw_data_products_*替代
    # 管理表
    "CatalogFile",
    "DataQuarantine",
    "Account",
    "CollectionTask",
    "DataFile",
    "DataRecord",
    "FieldMapping",
    "MappingSession",
    # 暂存表
    "StagingOrders",
    "StagingProductMetrics",
]

# ==================== 向后兼容别名 ====================

# 为了兼容可能使用旧名称的代码
FactSalesOrders = FactOrder  # 别名
FactProductMetrics = FactProductMetric  # 别名
