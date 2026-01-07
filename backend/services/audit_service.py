"""
审计日志服务

v4.12.0 SSOT迁移：从modules.core.db导入FactAuditLog
"""

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.database import get_db
from modules.core.db import FactAuditLog  # v4.12.0 SSOT迁移
from typing import Optional, Dict, Any, Union
from datetime import datetime

class AuditService:
    """审计服务类"""
    
    async def log_action(
        self,
        user_id: int,
        action: str,
        resource: str,
        ip_address: str,
        user_agent: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        db: AsyncSession = None
    ):
        """记录操作日志（异步模式）"""
        if db is None:
            from backend.models.database import AsyncSessionLocal
            db = AsyncSessionLocal()
        
        try:
            # 获取用户名
            from modules.core.db import DimUser  # v4.12.0 SSOT迁移
            result = await db.execute(
                select(DimUser).where(DimUser.user_id == user_id)
            )
            user = result.scalar_one_or_none()
            username = user.username if user else "unknown"
            
            # 创建审计日志记录
            audit_log = FactAuditLog(
                user_id=user_id,
                username=username,
                action_type=action,  # v4.12.0修复：使用action_type字段
                resource_type=resource,  # v4.12.0修复：使用resource_type字段
                resource_id=resource_id,
                action_description=f"{action} {resource} {resource_id or ''}",
                ip_address=ip_address,
                user_agent=user_agent,
                is_success=True,
                created_at=datetime.utcnow()
            )
            
            db.add(audit_log)
            await db.commit()
            
        except Exception as e:
            # 审计日志记录失败不应该影响主业务
            print(f"Audit log failed: {e}")
            await db.rollback()
    
    def get_user_actions(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        db: Session = None
    ) -> list:
        """获取用户操作日志"""
        if db is None:
            db = next(get_db())
        
        offset = (page - 1) * page_size
        logs = db.query(FactAuditLog).filter(
            FactAuditLog.user_id == user_id
        ).order_by(FactAuditLog.created_at.desc()).offset(offset).limit(page_size).all()
        
        return logs
    
    def get_resource_actions(
        self,
        resource: str,
        resource_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        db: Session = None
    ) -> list:
        """获取资源操作日志"""
        if db is None:
            db = next(get_db())
        
        offset = (page - 1) * page_size
        query = db.query(FactAuditLog).filter(FactAuditLog.resource_type == resource)  # v4.12.0修复：使用resource_type字段
        
        if resource_id:
            query = query.filter(FactAuditLog.resource_id == resource_id)
        
        logs = query.order_by(FactAuditLog.created_at.desc()).offset(offset).limit(page_size).all()
        return logs
    
    def get_recent_actions(
        self,
        hours: int = 24,
        page: int = 1,
        page_size: int = 20,
        db: Session = None
    ) -> list:
        """获取最近的操作日志"""
        if db is None:
            db = next(get_db())
        
        from datetime import datetime, timedelta
        since = datetime.utcnow() - timedelta(hours=hours)
        
        offset = (page - 1) * page_size
        logs = db.query(FactAuditLog).filter(
            FactAuditLog.created_at >= since
        ).order_by(FactAuditLog.created_at.desc()).offset(offset).limit(page_size).all()
        
        return logs
    
    # v4.12.0新增：数据同步操作日志
    async def log_sync_operation(
        self,
        user_id: Optional[int],
        file_id: int,
        task_id: Optional[str],
        operation: str,
        details: Dict[str, Any],
        db: AsyncSession = None
    ) -> None:
        """
        记录数据同步操作日志（复用FactAuditLog表，异步模式）
        
        Args:
            user_id: 用户ID（可选，系统操作时为None）
            file_id: 文件ID
            task_id: 同步任务ID（可选）
            operation: 操作类型（sync_start/sync_success/sync_failed等）
            details: 操作详情
            db: 数据库会话（可选）
        """
        if db is None:
            from backend.models.database import AsyncSessionLocal
            db = AsyncSessionLocal()
        
        try:
            from modules.core.db import DimUser
            
            # 获取用户名
            username = "system"
            if user_id:
                result = await db.execute(
                    select(DimUser).where(DimUser.user_id == user_id)
                )
                user = result.scalar_one_or_none()
                username = user.username if user else "unknown"
            
            # 构建操作详情
            operation_details = {
                **details,
                "task_id": task_id,
                "file_id": file_id,
            }
            
            # 创建审计日志记录
            audit_log = FactAuditLog(
                user_id=user_id or 0,  # 系统操作时使用0
                username=username,
                action_type=f"data_sync_{operation}",
                resource_type="data_sync",
                resource_id=str(file_id),
                action_description=f"数据同步操作: {operation}",
                changes_json=None,  # 同步操作不使用changes_json
                ip_address="system",
                user_agent="data_sync_service",
                is_success=operation not in ("sync_failed", "sync_error"),
                error_message=details.get("error") if operation in ("sync_failed", "sync_error") else None,
                created_at=datetime.utcnow()
            )
            
            db.add(audit_log)
            await db.commit()
            
        except Exception as e:
            # 审计日志记录失败不应该影响主业务
            print(f"Audit log failed: {e}")
            await db.rollback()
    
    # v4.12.0新增：数据变更历史（使用changes_json字段）
    async def log_data_change(
        self,
        user_id: Optional[int],
        resource_type: str,
        resource_id: str,
        action: str,
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
        db: AsyncSession = None
    ) -> None:
        """
        记录数据变更历史（使用changes_json字段，异步模式）
        
        Args:
            user_id: 用户ID（可选）
            resource_type: 资源类型（order/product/inventory等）
            resource_id: 资源ID
            action: 操作类型（create/update/delete）
            before: 变更前的数据（可选）
            after: 变更后的数据（可选）
            db: 数据库会话（可选）
        """
        if db is None:
            from backend.models.database import AsyncSessionLocal
            db = AsyncSessionLocal()
        
        try:
            import json
            from modules.core.db import DimUser
            
            # 获取用户名
            username = "system"
            if user_id:
                result = await db.execute(
                    select(DimUser).where(DimUser.user_id == user_id)
                )
                user = result.scalar_one_or_none()
                username = user.username if user else "unknown"
            
            # 构建变更详情（JSON格式）
            changes_data = {
                "before": before,
                "after": after,
                "action": action,
            }
            changes_json = json.dumps(changes_data, ensure_ascii=False, default=str)
            
            # 创建审计日志记录
            audit_log = FactAuditLog(
                user_id=user_id or 0,
                username=username,
                action_type=action,
                resource_type=resource_type,
                resource_id=resource_id,
                action_description=f"{action} {resource_type} {resource_id}",
                changes_json=changes_json,
                ip_address="system",
                user_agent="data_sync_service",
                is_success=True,
                created_at=datetime.utcnow()
            )
            
            db.add(audit_log)
            await db.commit()
            
        except Exception as e:
            # 审计日志记录失败不应该影响主业务
            print(f"Audit log failed: {e}")
            await db.rollback()
    
    # v4.12.0新增：获取数据同步审计追溯
    def get_sync_audit_trail(
        self,
        file_id: Optional[int] = None,
        task_id: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        db: Session = None
    ) -> list:
        """
        获取数据同步审计追溯
        
        Args:
            file_id: 文件ID（可选）
            task_id: 任务ID（可选）
            page: 页码
            page_size: 每页数量
            db: 数据库会话（可选）
            
        Returns:
            审计日志列表
        """
        if db is None:
            db = next(get_db())
        
        offset = (page - 1) * page_size
        query = db.query(FactAuditLog).filter(
            FactAuditLog.resource_type == "data_sync"
        )
        
        if file_id:
            query = query.filter(FactAuditLog.resource_id == str(file_id))
        
        if task_id:
            # 通过changes_json或action_description查找task_id
            # 注意：这里简化处理，实际应该从task_details中查询
            query = query.filter(
                FactAuditLog.action_description.like(f"%{task_id}%")
            )
        
        logs = query.order_by(FactAuditLog.created_at.desc()).offset(offset).limit(page_size).all()
        return logs

# 全局审计服务实例
audit_service = AuditService()
