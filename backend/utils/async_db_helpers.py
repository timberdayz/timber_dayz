"""
异步数据库辅助函数 - 西虹ERP系统

职责:
- 提供常用异步数据库操作的简化接口
- 封装错误处理和日志记录
- 提供类型安全的查询辅助函数

版本: v4.18.2
创建: 2026-01-01
"""

from typing import TypeVar, Optional, List, Any, Type
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import DeclarativeBase
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=DeclarativeBase)


async def async_get_one(
    session: AsyncSession,
    model: Type[T],
    **filters
) -> Optional[T]:
    """
    异步获取单个记录
    
    Args:
        session: 异步数据库会话
        model: ORM模型类
        **filters: 过滤条件（字段名=值）
        
    Returns:
        匹配的记录，如果不存在则返回 None
        
    Example:
        user = await async_get_one(db, User, id=1)
        file = await async_get_one(db, CatalogFile, file_path="/path/to/file")
    """
    try:
        query = select(model)
        for key, value in filters.items():
            query = query.where(getattr(model, key) == value)
        
        result = await session.execute(query)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"[async] 查询 {model.__name__} 失败: {e}", exc_info=True)
        raise


async def async_get_all(
    session: AsyncSession,
    model: Type[T],
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    order_by: Optional[Any] = None,
    **filters
) -> List[T]:
    """
    异步获取多个记录
    
    Args:
        session: 异步数据库会话
        model: ORM模型类
        limit: 限制返回数量
        offset: 跳过记录数
        order_by: 排序字段
        **filters: 过滤条件（字段名=值）
        
    Returns:
        匹配的记录列表
        
    Example:
        files = await async_get_all(db, CatalogFile, status='pending', limit=100)
    """
    try:
        query = select(model)
        for key, value in filters.items():
            query = query.where(getattr(model, key) == value)
        
        if order_by is not None:
            query = query.order_by(order_by)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)
        
        result = await session.execute(query)
        return list(result.scalars().all())
    except Exception as e:
        logger.error(f"[async] 查询 {model.__name__} 列表失败: {e}", exc_info=True)
        raise


async def async_count(
    session: AsyncSession,
    model: Type[T],
    **filters
) -> int:
    """
    异步统计记录数量
    
    Args:
        session: 异步数据库会话
        model: ORM模型类
        **filters: 过滤条件（字段名=值）
        
    Returns:
        匹配的记录数量
        
    Example:
        count = await async_count(db, CatalogFile, status='pending')
    """
    try:
        query = select(func.count()).select_from(model)
        for key, value in filters.items():
            query = query.where(getattr(model, key) == value)
        
        result = await session.execute(query)
        return result.scalar() or 0
    except Exception as e:
        logger.error(f"[async] 统计 {model.__name__} 失败: {e}", exc_info=True)
        raise


async def async_commit_safe(session: AsyncSession) -> bool:
    """
    安全提交事务
    
    Args:
        session: 异步数据库会话
        
    Returns:
        True 如果提交成功，False 如果失败（已回滚）
        
    Note:
        失败时会自动回滚并记录错误
    """
    try:
        await session.commit()
        return True
    except Exception as e:
        logger.error(f"[async] 提交事务失败，正在回滚: {e}", exc_info=True)
        try:
            await session.rollback()
        except Exception as rollback_error:
            logger.error(f"[async] 回滚失败: {rollback_error}", exc_info=True)
        return False


async def async_refresh(session: AsyncSession, obj: T) -> T:
    """
    异步刷新对象
    
    Args:
        session: 异步数据库会话
        obj: 要刷新的ORM对象
        
    Returns:
        刷新后的对象
    """
    try:
        await session.refresh(obj)
        return obj
    except Exception as e:
        logger.error(f"[async] 刷新对象失败: {e}", exc_info=True)
        raise


__all__ = [
    "async_get_one",
    "async_get_all",
    "async_count",
    "async_commit_safe",
    "async_refresh",
]

