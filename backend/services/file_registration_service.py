"""
文件注册服务 - File Registration Service

提供文件注册的原子性操作，确保采集文件正确入库
支持事务回滚和错误恢复
"""

import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import contextmanager

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from modules.core.db import CatalogFile, CollectionTask
from modules.core.logger import get_logger

logger = get_logger(__name__)


class FileRegistrationError(Exception):
    """文件注册错误"""
    pass


class FileRegistrationService:
    """
    文件注册服务
    
    功能：
    1. 原子性文件注册（数据库+文件系统）
    2. 失败时自动回滚
    3. 重复文件检测
    4. 文件哈希校验
    """
    
    def __init__(
        self,
        db: Session,
        data_dir: str = None,
        temp_dir: str = None
    ):
        """
        初始化文件注册服务
        
        Args:
            db: 数据库会话
            data_dir: 最终数据存储目录
            temp_dir: 临时下载目录
        """
        self.db = db
        self.data_dir = Path(data_dir or os.getenv('DATA_DIR', 'data'))
        self.temp_dir = Path(temp_dir or os.getenv('TEMP_DIR', 'temp'))
        
        # 确保目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    @contextmanager
    def _file_transaction(self, source_path: Path, target_path: Path):
        """
        文件事务上下文管理器
        
        成功时移动文件，失败时保持原状
        
        Args:
            source_path: 源文件路径
            target_path: 目标文件路径
        """
        # 如果目标文件已存在，先备份
        backup_path = None
        if target_path.exists():
            backup_path = target_path.with_suffix(target_path.suffix + '.bak')
            shutil.move(str(target_path), str(backup_path))
        
        try:
            # 确保目标目录存在
            target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # 移动文件
            shutil.move(str(source_path), str(target_path))
            
            yield target_path
            
            # 成功后删除备份
            if backup_path and backup_path.exists():
                backup_path.unlink()
        
        except Exception as e:
            # 失败时回滚
            logger.error(f"File transaction failed: {e}")
            
            # 如果目标文件被创建了，删除它
            if target_path.exists():
                try:
                    target_path.unlink()
                except Exception:
                    pass
            
            # 恢复备份
            if backup_path and backup_path.exists():
                shutil.move(str(backup_path), str(target_path))
            
            raise
    
    def _compute_file_hash(self, file_path: Path) -> str:
        """
        计算文件MD5哈希
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: MD5哈希值
        """
        import hashlib
        
        hash_md5 = hashlib.md5()
        
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        
        return hash_md5.hexdigest()
    
    def _build_target_path(
        self,
        platform: str,
        data_domain: str,
        account: str,
        date_str: str,
        filename: str
    ) -> Path:
        """
        构建目标文件路径
        
        路径格式: data/files/{platform}/{data_domain}/{account}/{YYYY-MM}/{filename}
        
        Args:
            platform: 平台代码
            data_domain: 数据域
            account: 账号ID
            date_str: 日期字符串 (YYYY-MM-DD)
            filename: 文件名
            
        Returns:
            Path: 目标路径
        """
        # 解析年月
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            year_month = date_obj.strftime("%Y-%m")
        except ValueError:
            year_month = datetime.now().strftime("%Y-%m")
        
        return (
            self.data_dir / 'files' /
            platform.lower() /
            data_domain.lower() /
            account /
            year_month /
            filename
        )
    
    def register_file(
        self,
        source_path: str,
        task_id: int,
        platform: str,
        data_domain: str,
        account: str,
        date_from: str,
        date_to: str = None,
        granularity: str = 'daily',
        sub_domain: str = None,
        shop_id: str = None,
        extra_metadata: Dict[str, Any] = None
    ) -> CatalogFile:
        """
        注册采集文件（原子性操作）
        
        Args:
            source_path: 源文件路径（临时下载目录中）
            task_id: 关联的任务ID
            platform: 平台代码
            data_domain: 数据域
            account: 账号ID
            date_from: 数据开始日期
            date_to: 数据结束日期（可选）
            granularity: 粒度
            sub_domain: 子域（可选）
            shop_id: 店铺ID（可选）
            extra_metadata: 额外元数据
            
        Returns:
            CatalogFile: 注册的文件记录
            
        Raises:
            FileRegistrationError: 注册失败
        """
        source_file = Path(source_path)
        
        # 验证源文件存在
        if not source_file.exists():
            raise FileRegistrationError(f"Source file not found: {source_path}")
        
        # 获取文件信息
        file_size = source_file.stat().st_size
        file_hash = self._compute_file_hash(source_file)
        filename = source_file.name
        
        # 检查是否重复（基于哈希）
        existing = self.db.query(CatalogFile).filter(
            CatalogFile.file_hash == file_hash
        ).first()
        
        if existing:
            logger.warning(f"Duplicate file detected: {filename} (hash: {file_hash})")
            # 删除临时文件
            source_file.unlink()
            return existing
        
        # 构建目标路径
        target_path = self._build_target_path(
            platform=platform,
            data_domain=data_domain,
            account=account,
            date_str=date_from,
            filename=filename
        )
        
        # 创建数据库记录
        catalog_file = CatalogFile(
            file_name=filename,
            file_path=str(target_path),
            file_size=file_size,
            file_hash=file_hash,
            platform_code=platform.lower(),
            data_domain=data_domain.lower(),
            sub_domain=sub_domain,
            account_id=account,
            shop_id=shop_id,
            granularity=granularity,
            date_from=datetime.strptime(date_from, "%Y-%m-%d").date() if date_from else None,
            date_to=datetime.strptime(date_to, "%Y-%m-%d").date() if date_to else None,
            status='pending',
            upload_time=datetime.utcnow(),
            metadata=extra_metadata or {}
        )
        
        try:
            # 开始事务
            with self._file_transaction(source_file, target_path):
                # 更新文件路径（确保使用最终路径）
                catalog_file.file_path = str(target_path)
                
                # 添加到数据库
                self.db.add(catalog_file)
                self.db.flush()  # 获取ID但不提交
                
                # 更新任务的文件计数
                if task_id:
                    task = self.db.query(CollectionTask).filter(
                        CollectionTask.id == task_id
                    ).first()
                    
                    if task:
                        task.files_collected = (task.files_collected or 0) + 1
                
                # 提交事务
                self.db.commit()
                
                logger.info(f"File registered: {filename} -> {target_path}")
                return catalog_file
        
        except IntegrityError as e:
            self.db.rollback()
            raise FileRegistrationError(f"Database integrity error: {e}")
        
        except Exception as e:
            self.db.rollback()
            raise FileRegistrationError(f"File registration failed: {e}")
    
    def register_files_batch(
        self,
        files: List[Dict[str, Any]],
        task_id: int
    ) -> List[CatalogFile]:
        """
        批量注册文件（原子性操作）
        
        所有文件要么全部成功，要么全部回滚
        
        Args:
            files: 文件信息列表
            task_id: 关联的任务ID
            
        Returns:
            List[CatalogFile]: 注册的文件记录列表
        """
        registered = []
        moved_files = []  # 记录已移动的文件，用于回滚
        
        try:
            for file_info in files:
                source_path = Path(file_info['source_path'])
                
                if not source_path.exists():
                    raise FileRegistrationError(f"Source file not found: {source_path}")
                
                # 获取文件信息
                file_size = source_path.stat().st_size
                file_hash = self._compute_file_hash(source_path)
                filename = source_path.name
                
                # 检查重复
                existing = self.db.query(CatalogFile).filter(
                    CatalogFile.file_hash == file_hash
                ).first()
                
                if existing:
                    logger.warning(f"Duplicate file skipped: {filename}")
                    source_path.unlink()
                    registered.append(existing)
                    continue
                
                # 构建目标路径
                target_path = self._build_target_path(
                    platform=file_info['platform'],
                    data_domain=file_info['data_domain'],
                    account=file_info['account'],
                    date_str=file_info.get('date_from', datetime.now().strftime('%Y-%m-%d')),
                    filename=filename
                )
                
                # 确保目录存在
                target_path.parent.mkdir(parents=True, exist_ok=True)
                
                # 移动文件
                shutil.move(str(source_path), str(target_path))
                moved_files.append({'source': source_path, 'target': target_path})
                
                # 创建记录
                catalog_file = CatalogFile(
                    file_name=filename,
                    file_path=str(target_path),
                    file_size=file_size,
                    file_hash=file_hash,
                    platform_code=file_info['platform'].lower(),
                    data_domain=file_info['data_domain'].lower(),
                    sub_domain=file_info.get('sub_domain'),
                    account_id=file_info['account'],
                    shop_id=file_info.get('shop_id'),
                    granularity=file_info.get('granularity', 'daily'),
                    date_from=datetime.strptime(file_info['date_from'], "%Y-%m-%d").date() if file_info.get('date_from') else None,
                    date_to=datetime.strptime(file_info['date_to'], "%Y-%m-%d").date() if file_info.get('date_to') else None,
                    status='pending',
                    upload_time=datetime.utcnow(),
                    metadata=file_info.get('metadata', {})
                )
                
                self.db.add(catalog_file)
                registered.append(catalog_file)
            
            # 更新任务文件计数
            if task_id and registered:
                task = self.db.query(CollectionTask).filter(
                    CollectionTask.id == task_id
                ).first()
                
                if task:
                    task.files_collected = (task.files_collected or 0) + len(registered)
            
            # 提交所有更改
            self.db.commit()
            
            logger.info(f"Batch registered {len(registered)} files for task {task_id}")
            return registered
        
        except Exception as e:
            # 回滚数据库
            self.db.rollback()
            
            # 回滚文件移动
            for move_info in moved_files:
                try:
                    shutil.move(str(move_info['target']), str(move_info['source']))
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback file move: {rollback_error}")
            
            raise FileRegistrationError(f"Batch registration failed: {e}")
    
    def mark_file_ingested(self, file_id: int) -> bool:
        """
        标记文件为已入库
        
        Args:
            file_id: 文件ID
            
        Returns:
            bool: 是否成功
        """
        try:
            catalog_file = self.db.query(CatalogFile).filter(
                CatalogFile.id == file_id
            ).first()
            
            if catalog_file:
                catalog_file.status = 'ingested'
                catalog_file.ingest_time = datetime.utcnow()
                self.db.commit()
                return True
            
            return False
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to mark file as ingested: {e}")
            return False
    
    def mark_file_failed(
        self,
        file_id: int,
        error_message: str
    ) -> bool:
        """
        标记文件为入库失败
        
        Args:
            file_id: 文件ID
            error_message: 错误信息
            
        Returns:
            bool: 是否成功
        """
        try:
            catalog_file = self.db.query(CatalogFile).filter(
                CatalogFile.id == file_id
            ).first()
            
            if catalog_file:
                catalog_file.status = 'failed'
                catalog_file.error_message = error_message
                self.db.commit()
                return True
            
            return False
        
        except Exception as e:
            self.db.rollback()
            logger.error(f"Failed to mark file as failed: {e}")
            return False


def get_file_registration_service(db: Session) -> FileRegistrationService:
    """
    获取文件注册服务实例
    
    Args:
        db: 数据库会话
        
    Returns:
        FileRegistrationService: 服务实例
    """
    return FileRegistrationService(db)

