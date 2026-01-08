"""
数据备份服务
提供数据备份和恢复功能

v4.20.0: 系统管理模块API实现
"""

import os
import subprocess
import hashlib
import tarfile
import gzip
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from modules.core.db import BackupRecord
from modules.core.logger import get_logger
from backend.utils.config import get_settings

logger = get_logger(__name__)


class BackupService:
    """数据备份服务类"""
    
    def __init__(self, db: AsyncSession):
        """初始化服务（仅支持异步）"""
        self.db = db
        self.settings = get_settings()
        
        # Docker环境路径配置
        self.backup_dir = Path("/app/backups")  # 容器内备份目录
        self.data_dirs = [
            "/app/data",
            "/app/downloads",
            "/app/logs",
            "/app/config"
        ]
        
        # 确保备份目录存在
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_database_url(self) -> str:
        """获取数据库连接URL（Docker网络内）"""
        # 从环境变量或settings获取数据库配置
        db_user = os.getenv("POSTGRES_USER", getattr(self.settings, "POSTGRES_USER", "erp_user"))
        db_password = os.getenv("POSTGRES_PASSWORD", getattr(self.settings, "POSTGRES_PASSWORD", ""))
        db_name = os.getenv("POSTGRES_DB", getattr(self.settings, "POSTGRES_DB", "xihong_erp"))
        
        # Docker网络内使用服务名连接
        return f"postgresql://{db_user}:{db_password}@postgres:5432/{db_name}"
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """计算文件SHA-256校验和"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    async def create_backup(
        self,
        backup_type: str = "full",
        description: Optional[str] = None,
        created_by: Optional[int] = None
    ) -> BackupRecord:
        """
        创建备份
        
        Docker环境实现：
        - 数据库备份：使用pg_dump连接postgres:5432
        - 文件备份：备份挂载的volume
        - 备份存储：保存到/app/backups
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        try:
            # 创建备份记录（pending状态）
            backup_record = BackupRecord(
                backup_type=backup_type,
                backup_path="",  # 稍后更新
                backup_size=0,  # 稍后更新
                status="pending",
                description=description,
                created_by=created_by
            )
            self.db.add(backup_record)
            await self.db.flush()  # 获取ID
            
            backup_files = []
            
            # 1. 数据库备份
            db_backup_path = self.backup_dir / f"backup_{timestamp}_database.sql.gz"
            try:
                db_url = self._get_database_url()
                # 使用pg_dump导出数据库
                cmd = [
                    "pg_dump",
                    db_url,
                    "--no-owner",
                    "--no-acl"
                ]
                
                # 执行pg_dump并压缩
                with open(db_backup_path, "wb") as f:
                    dump_process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )
                    gzip_process = subprocess.Popen(
                        ["gzip"],
                        stdin=dump_process.stdout,
                        stdout=f,
                        stderr=subprocess.PIPE
                    )
                    dump_process.stdout.close()
                    gzip_process.communicate()
                    dump_process.wait()
                    
                    if dump_process.returncode != 0:
                        raise Exception(f"pg_dump failed: {dump_process.stderr.read().decode()}")
                
                backup_files.append(db_backup_path)
                logger.info(f"数据库备份完成: {db_backup_path}")
            except Exception as e:
                logger.error(f"数据库备份失败: {e}", exc_info=True)
                raise
            
            # 2. 文件备份
            files_backup_path = self.backup_dir / f"backup_{timestamp}_files.tar.gz"
            try:
                with tarfile.open(files_backup_path, "w:gz") as tar:
                    for data_dir in self.data_dirs:
                        data_path = Path(data_dir)
                        if data_path.exists():
                            tar.add(data_path, arcname=data_path.name)
                            logger.info(f"已添加目录到备份: {data_dir}")
                
                backup_files.append(files_backup_path)
                logger.info(f"文件备份完成: {files_backup_path}")
            except Exception as e:
                logger.error(f"文件备份失败: {e}", exc_info=True)
                raise
            
            # 3. 计算总大小和校验和
            total_size = sum(f.stat().st_size for f in backup_files)
            checksum = self._calculate_checksum(files_backup_path)  # 使用文件备份的校验和作为主校验和
            
            # 4. 更新备份记录
            backup_record.backup_path = str(files_backup_path)  # 主备份文件路径
            backup_record.backup_size = total_size
            backup_record.checksum = checksum
            backup_record.status = "completed"
            backup_record.completed_at = datetime.utcnow()
            
            await self.db.commit()
            await self.db.refresh(backup_record)
            
            logger.info(f"备份创建成功: ID={backup_record.id}, 大小={total_size}字节")
            return backup_record
            
        except Exception as e:
            # 更新备份记录为失败状态
            if 'backup_record' in locals():
                backup_record.status = "failed"
                await self.db.commit()
            
            logger.error(f"创建备份失败: {e}", exc_info=True)
            raise
    
    async def get_backup(self, backup_id: int) -> Optional[BackupRecord]:
        """获取备份记录"""
        try:
            result = await self.db.execute(
                select(BackupRecord).where(BackupRecord.id == backup_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"获取备份记录失败: {e}", exc_info=True)
            return None
    
    async def list_backups(
        self,
        backup_type: Optional[str] = None,
        status: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20
    ) -> tuple[list[BackupRecord], int]:
        """获取备份列表（分页、筛选）"""
        try:
            conditions = []
            
            if backup_type:
                conditions.append(BackupRecord.backup_type == backup_type)
            
            if status:
                conditions.append(BackupRecord.status == status)
            
            if start_time:
                conditions.append(BackupRecord.created_at >= start_time)
            
            if end_time:
                conditions.append(BackupRecord.created_at <= end_time)
            
            # 查询总数
            from sqlalchemy import func, and_
            count_query = select(func.count(BackupRecord.id))
            if conditions:
                count_query = count_query.where(and_(*conditions))
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar() or 0
            
            # 查询数据
            query = select(BackupRecord).order_by(BackupRecord.created_at.desc())
            if conditions:
                query = query.where(and_(*conditions))
            
            # 分页
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            
            result = await self.db.execute(query)
            backups = result.scalars().all()
            
            return backups, total
            
        except Exception as e:
            logger.error(f"获取备份列表失败: {e}", exc_info=True)
            raise
    
    def verify_backup(self, backup_record: BackupRecord) -> tuple[bool, Optional[str]]:
        """
        验证备份文件完整性
        
        Returns:
            (is_valid, error_message)
        """
        backup_path = Path(backup_record.backup_path)
        
        if not backup_path.exists():
            return False, f"备份文件不存在: {backup_path}"
        
        # 验证文件大小
        actual_size = backup_path.stat().st_size
        if actual_size != backup_record.backup_size:
            return False, f"备份文件大小不匹配: 期望{backup_record.backup_size}字节，实际{actual_size}字节"
        
        # 验证校验和
        if backup_record.checksum:
            actual_checksum = self._calculate_checksum(backup_path)
            if actual_checksum != backup_record.checksum:
                return False, f"备份文件校验和不匹配: 期望{backup_record.checksum}，实际{actual_checksum}"
        
        return True, None


def get_backup_service(db: AsyncSession) -> BackupService:
    """获取备份服务实例"""
    return BackupService(db)
