#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
元数据文件管理器 - 方案B+数据治理组件

功能：
1. 创建.meta.json伴生文件
2. 读取和更新元数据文件
3. 记录数据处理历史（数据血缘）
4. 支持多阶段数据流转（raw→staging→curated）

元数据文件格式：
{
    "file_info": {...},           # 文件基础信息
    "business_metadata": {...},   # 业务元数据
    "collection_info": {...},     # 采集信息
    "data_quality": {...},        # 数据质量
    "processing_history": [...]   # 处理历史（数据血缘）
}
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List
from modules.core.logger import get_logger

logger = get_logger(__name__)


class MetadataManager:
    """元数据文件管理器"""
    
    @staticmethod
    def create_meta_file(
        file_path: Path,
        business_metadata: Dict,
        collection_info: Dict,
        data_quality: Optional[Dict] = None
    ) -> Path:
        """
        创建.meta.json伴生文件
        
        Args:
            file_path: 数据文件路径
            business_metadata: 业务元数据（platform, domain, granularity等）
            collection_info: 采集信息（method, account, shop_id等）
            data_quality: 数据质量评分（可选）
            
        Returns:
            元数据文件路径
            
        Examples:
            >>> MetadataManager.create_meta_file(
            ...     Path('data/raw/2025/shopee_products_monthly_xxx.xlsx'),
            ...     business_metadata={'source_platform': 'shopee', 'data_domain': 'products'},
            ...     collection_info={'method': 'playwright'},
            ...     data_quality={'quality_score': 95.5}
            ... )
            PosixPath('data/raw/2025/shopee_products_monthly_xxx.meta.json')
        """
        meta_path = file_path.with_suffix('.meta.json')
        
        # 构建完整元数据结构
        metadata = {
            "file_info": {
                "file_name": file_path.name,
                "file_size": file_path.stat().st_size if file_path.exists() else 0,
                "file_ext": file_path.suffix,
                "created_at": datetime.now().isoformat()
            },
            "business_metadata": business_metadata,
            "collection_info": collection_info,
            "data_quality": data_quality or {},
            "processing_history": [
                {
                    "timestamp": datetime.now().isoformat(),
                    "stage": "raw",
                    "status": "received",
                    "processor": collection_info.get('method', 'unknown')
                }
            ],
            "lineage": {
                "upstream_sources": [],
                "downstream_tables": [],
                "related_files": []
            }
        }
        
        # 写入文件
        try:
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"元数据文件已创建: {meta_path}")
            return meta_path
            
        except Exception as e:
            logger.error(f"创建元数据文件失败 {meta_path}: {e}")
            raise
    
    @staticmethod
    def read_meta_file(meta_path: Path) -> Dict:
        """
        读取元数据文件
        
        Args:
            meta_path: 元数据文件路径
            
        Returns:
            元数据字典
            
        Raises:
            FileNotFoundError: 元数据文件不存在
            json.JSONDecodeError: JSON格式错误
        """
        if not meta_path.exists():
            raise FileNotFoundError(f"元数据文件不存在: {meta_path}")
        
        try:
            with open(meta_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
            return metadata
        except json.JSONDecodeError as e:
            logger.error(f"元数据文件JSON格式错误 {meta_path}: {e}")
            raise
    
    @staticmethod
    def update_processing_stage(
        meta_path: Path,
        stage: str,
        status: str,
        **kwargs
    ) -> None:
        """
        更新处理阶段（追加到processing_history）
        
        Args:
            meta_path: 元数据文件路径
            stage: 处理阶段（raw/staging/curated/quarantine）
            status: 状态（received/validated/ingested/failed）
            **kwargs: 额外信息（如rows_imported, table等）
            
        Examples:
            >>> MetadataManager.update_processing_stage(
            ...     Path('data/raw/2025/xxx.meta.json'),
            ...     stage='curated',
            ...     status='ingested',
            ...     rows_imported=1523,
            ...     table='fact_product_metrics'
            ... )
        """
        try:
            metadata = MetadataManager.read_meta_file(meta_path)
            
            # 添加新的处理记录
            history_entry = {
                "timestamp": datetime.now().isoformat(),
                "stage": stage,
                "status": status,
                **kwargs
            }
            
            metadata['processing_history'].append(history_entry)
            
            # 写回文件
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"元数据已更新: {meta_path} → {stage}/{status}")
            
        except Exception as e:
            logger.error(f"更新元数据失败 {meta_path}: {e}")
            raise
    
    @staticmethod
    def update_lineage(
        meta_path: Path,
        upstream_sources: Optional[List[str]] = None,
        downstream_tables: Optional[List[str]] = None,
        related_files: Optional[List[str]] = None
    ) -> None:
        """
        更新数据血缘信息
        
        Args:
            meta_path: 元数据文件路径
            upstream_sources: 上游数据源列表
            downstream_tables: 下游表列表
            related_files: 相关文件列表
        """
        try:
            metadata = MetadataManager.read_meta_file(meta_path)
            
            if upstream_sources is not None:
                metadata['lineage']['upstream_sources'] = upstream_sources
            
            if downstream_tables is not None:
                metadata['lineage']['downstream_tables'] = downstream_tables
            
            if related_files is not None:
                metadata['lineage']['related_files'] = related_files
            
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"数据血缘已更新: {meta_path}")
            
        except Exception as e:
            logger.error(f"更新数据血缘失败 {meta_path}: {e}")
            raise
    
    @staticmethod
    def get_processing_stage(meta_path: Path) -> str:
        """
        获取当前处理阶段
        
        Args:
            meta_path: 元数据文件路径
            
        Returns:
            当前阶段（raw/staging/curated/quarantine）
        """
        try:
            metadata = MetadataManager.read_meta_file(meta_path)
            history = metadata.get('processing_history', [])
            
            if not history:
                return 'raw'
            
            # 返回最后一个阶段
            return history[-1].get('stage', 'raw')
            
        except Exception as e:
            logger.warning(f"获取处理阶段失败 {meta_path}: {e}")
            return 'raw'
    
    @staticmethod
    def get_quality_score(meta_path: Path) -> Optional[float]:
        """
        获取数据质量分数
        
        Args:
            meta_path: 元数据文件路径
            
        Returns:
            质量分数（0-100），如果不存在返回None
        """
        try:
            metadata = MetadataManager.read_meta_file(meta_path)
            return metadata.get('data_quality', {}).get('quality_score')
        except Exception:
            return None
    
    @staticmethod
    def batch_create_meta_files(
        file_paths: List[Path],
        business_metadata_fn,
        collection_info_fn,
        data_quality_fn=None
    ) -> List[Path]:
        """
        批量创建元数据文件
        
        Args:
            file_paths: 文件路径列表
            business_metadata_fn: 业务元数据生成函数
            collection_info_fn: 采集信息生成函数
            data_quality_fn: 数据质量评估函数（可选）
            
        Returns:
            元数据文件路径列表
        """
        meta_paths = []
        
        for file_path in file_paths:
            try:
                business_meta = business_metadata_fn(file_path)
                collection_info = collection_info_fn(file_path)
                data_quality = data_quality_fn(file_path) if data_quality_fn else None
                
                meta_path = MetadataManager.create_meta_file(
                    file_path,
                    business_meta,
                    collection_info,
                    data_quality
                )
                meta_paths.append(meta_path)
                
            except Exception as e:
                logger.error(f"批量创建元数据失败 {file_path}: {e}")
        
        return meta_paths


# 便捷函数
def create_meta_file(file_path: Path, **kwargs) -> Path:
    """便捷函数：创建元数据文件"""
    return MetadataManager.create_meta_file(file_path, **kwargs)


def read_meta_file(meta_path: Path) -> Dict:
    """便捷函数：读取元数据文件"""
    return MetadataManager.read_meta_file(meta_path)


def update_processing_stage(meta_path: Path, stage: str, status: str, **kwargs) -> None:
    """便捷函数：更新处理阶段"""
    return MetadataManager.update_processing_stage(meta_path, stage, status, **kwargs)

