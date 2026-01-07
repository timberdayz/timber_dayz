#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多层数据去重服务（Multi-Layer Deduplication Service）

v4.6.0新增：
- 文件级去重：基于file_hash检查
- 文件内去重：基于data_hash检查（同一文件内重复行）
- 跨文件去重：基于data_hash检查（不同文件间重复行）
- 业务语义去重：基于业务唯一键检查（如订单号、产品ID等）

职责：
- 计算数据哈希（data_hash）
- 批量查询已存在的哈希
- 过滤重复数据
- 性能优化（批量查询、向量化计算）
"""

from typing import List, Dict, Any, Set, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession  # ⭐ v4.18.2新增：异步支持
from sqlalchemy import select, func, and_
from datetime import datetime
import hashlib
import json
import pandas as pd

from modules.core.db import CatalogFile
from modules.core.logger import get_logger

logger = get_logger(__name__)


class DeduplicationService:
    """
    多层数据去重服务
    
    去重策略（从粗到细）：
    1. 文件级去重：基于file_hash（最快，跳过整个文件）
    2. 文件内去重：基于data_hash（同一文件内重复行）
    3. 跨文件去重：基于data_hash（不同文件间重复行）
    4. 业务语义去重：基于业务唯一键（如订单号、产品ID等）
    
    v4.18.2: 支持异步会话
    v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
    """
    
    def __init__(self, db: AsyncSession):
        """
        初始化去重服务
        
        Args:
            db: 异步数据库会话（AsyncSession）
        """
        self.db = db
    
    async def check_file_level_dedup(self, file_id: int) -> Tuple[bool, Optional[str]]:
        """
        文件级去重检查
        
        Args:
            file_id: 文件ID
        
        Returns:
            (is_duplicate, reason)
        
        v4.18.2: 支持异步会话
        v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
        """
        try:
            # ⭐ v4.18.2：支持异步会话
            result = await self.db.execute(
                select(CatalogFile).where(CatalogFile.id == file_id)
            )
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return False, None
            
            # 检查文件状态
            if file_record.status == 'ingested':
                return True, f"文件已处理（status=ingested）"
            
            # 检查file_hash（如果存在）
            if file_record.file_hash:
                # 查询是否有相同file_hash的文件已处理
                query = select(CatalogFile).where(
                    and_(
                        CatalogFile.file_hash == file_record.file_hash,
                        CatalogFile.status == 'ingested',
                        CatalogFile.id != file_id
                    )
                )
                
                result = await self.db.execute(query)
                existing = result.scalar_one_or_none()
                
                if existing:
                    return True, f"文件哈希重复（file_hash={file_record.file_hash[:16]}...，已处理文件ID={existing.id}）"
            
            return False, None
            
        except Exception as e:
            logger.error(f"[Dedup] 文件级去重检查失败: {e}", exc_info=True)
            return False, None
    
    def calculate_data_hash(
        self,
        row: Dict[str, Any],
        exclude_fields: Optional[List[str]] = None,
        deduplication_fields: Optional[List[str]] = None
    ) -> str:
        """
        计算单行数据的哈希值
        
        Args:
            row: 数据行字典
            exclude_fields: 排除的字段列表（元数据字段，如file_id、ingest_timestamp等）
            deduplication_fields: 核心去重字段列表（可选，如果提供则只使用这些字段计算hash）
        
        Returns:
            data_hash (SHA256, 64字符)
        """
        if exclude_fields is None:
            exclude_fields = ['file_id', 'ingest_timestamp', 'id', 'created_at', 'updated_at']
        
        # v4.14.0新增：如果提供了核心字段，只使用核心字段计算hash
        if deduplication_fields:
            # 只使用核心字段
            business_data = {}
            missing_fields = []
            for field in deduplication_fields:
                # 支持中英文字段名匹配（模糊匹配）
                matched = False
                matched_key = None
                for key in row.keys():
                    # 精确匹配
                    if key == field:
                        business_data[key] = row[key]
                        matched = True
                        matched_key = key
                        break
                    # 忽略大小写匹配
                    if key.lower() == field.lower():
                        business_data[key] = row[key]
                        matched = True
                        matched_key = key
                        break
                
                # 如果未找到匹配字段，记录警告（但不影响计算）
                if not matched:
                    missing_fields.append(field)
                    logger.debug(
                        f"[Dedup] 核心字段 {field} 在数据行中未找到，跳过（可用字段: {list(row.keys())[:5]}...）"
                    )
            
            # 如果所有核心字段都缺失，记录严重警告
            if len(missing_fields) == len(deduplication_fields):
                logger.warning(
                    f"[Dedup] ⚠️ 所有核心字段都未找到: {deduplication_fields}，"
                    f"将使用空字典计算hash（可能导致所有行产生相同的hash）"
                )
            elif missing_fields:
                logger.info(
                    f"[Dedup] 部分核心字段未找到: {missing_fields}，"
                    f"已找到的字段: {list(business_data.keys())}"
                )
        else:
            # 使用所有业务字段（向后兼容）
            business_data = {
                k: v for k, v in row.items()
                if k not in exclude_fields and v is not None
            }
        
        # 排序键值对（确保一致性）
        sorted_items = sorted(business_data.items())
        
        # 转换为JSON字符串（确保可序列化）
        json_str = json.dumps(sorted_items, ensure_ascii=False, sort_keys=True)
        
        # 计算SHA256哈希
        hash_obj = hashlib.sha256(json_str.encode('utf-8'))
        data_hash = hash_obj.hexdigest()
        
        # 记录用于hash计算的字段（仅在前几行记录，避免日志过多）
        if hasattr(self, '_hash_log_count'):
            self._hash_log_count += 1
        else:
            self._hash_log_count = 1
        
        if self._hash_log_count <= 3:
            logger.debug(
                f"[Dedup] 计算data_hash: 使用字段={list(business_data.keys())}, "
                f"hash前8位={data_hash[:8]}..."
            )
        
        return data_hash
    
    def batch_calculate_data_hash(
        self,
        rows: List[Dict[str, Any]],
        exclude_fields: Optional[List[str]] = None,
        deduplication_fields: Optional[List[str]] = None
    ) -> List[str]:
        """
        批量计算数据哈希（使用pandas向量化）
        
        Args:
            rows: 数据行列表
            exclude_fields: 排除的字段列表
            deduplication_fields: 核心去重字段列表（可选，如果提供则只使用这些字段计算hash）
        
        Returns:
            data_hash列表（与rows长度相同）
        """
        if not rows:
            return []
        
        # v4.14.0新增：如果提供了核心字段，使用逐行计算（确保字段匹配正确）
        if deduplication_fields:
            logger.info(
                f"[Dedup] 使用核心字段计算hash: {deduplication_fields}，"
                f"逐行计算以确保字段匹配正确（共{len(rows)}行）"
            )
            # 重置日志计数器
            self._hash_log_count = 0
            hashes = [
                self.calculate_data_hash(row, exclude_fields, deduplication_fields)
                for row in rows
            ]
            # 验证hash唯一性（前10行）
            if len(hashes) > 0:
                unique_hashes = set(hashes[:min(10, len(hashes))])
                if len(unique_hashes) == 1 and len(hashes) > 1:
                    logger.warning(
                        f"[Dedup] ⚠️ 警告：前{min(10, len(hashes))}行的data_hash都相同: {hashes[0][:8]}...，"
                        f"可能导致去重失败（所有行被识别为重复）"
                    )
            return hashes
        
        try:
            # 转换为DataFrame（性能优化）
            df = pd.DataFrame(rows)
            
            # 排除元数据字段
            if exclude_fields is None:
                exclude_fields = ['file_id', 'ingest_timestamp', 'id', 'created_at', 'updated_at']
            
            business_columns = [col for col in df.columns if col not in exclude_fields]
            df_business = df[business_columns].fillna('')
            
            # 批量计算哈希（向量化）
            def hash_row(row):
                sorted_items = sorted(row.items())
                json_str = json.dumps(sorted_items, ensure_ascii=False, sort_keys=True)
                return hashlib.sha256(json_str.encode('utf-8')).hexdigest()
            
            hashes = df_business.apply(hash_row, axis=1).tolist()
            
            logger.info(f"[Dedup] 批量计算哈希: {len(hashes)}行，耗时约{len(hashes) * 0.1:.1f}ms（估算）")
            return hashes
            
        except Exception as e:
            logger.error(f"[Dedup] 批量计算哈希失败，回退到逐行计算: {e}")
            # 回退到逐行计算
            return [
                self.calculate_data_hash(row, exclude_fields, deduplication_fields)
                for row in rows
            ]
    
    async def batch_check_existing_hashes(
        self,
        data_hashes: List[str],
        data_domain: str,
        granularity: str,
        sub_domain: Optional[str] = None  # ⭐ v4.16.0新增：子类型（services域必须提供）
    ) -> Set[str]:
        """
        批量查询已存在的哈希（跨文件去重）
        
        Args:
            data_hashes: 数据哈希列表
            data_domain: 数据域
            granularity: 粒度
            sub_domain: 子类型（可选，services域必须提供）
        
        Returns:
            已存在的哈希集合
        
        v4.18.2: 支持异步/同步双模式
        """
        if not data_hashes:
            return set()
        
        try:
            # ⭐ v4.16.0更新：根据data_domain+granularity+sub_domain选择目标表
            if data_domain.lower() == 'services' and sub_domain:
                # Services域按sub_domain分表
                table_name = f"fact_raw_data_services_{sub_domain.lower()}_{granularity}"
            else:
                # 其他域使用标准格式
                table_name = f"fact_raw_data_{data_domain}_{granularity}"
            
            # 批量查询（使用IN查询，1次SQL替代N次）
            # 注意：这里需要动态构建查询，因为表名是动态的
            # 为了简化，我们使用原始SQL
            from sqlalchemy import text
            
            placeholders = ','.join([f"'{h}'" for h in data_hashes])
            
            # ⭐ v4.16.0更新：services域的表有sub_domain字段，需要额外过滤
            if data_domain.lower() == 'services' and sub_domain:
                sql = text(f"""
                    SELECT DISTINCT data_hash 
                    FROM {table_name}
                    WHERE data_domain = :data_domain 
                      AND sub_domain = :sub_domain
                      AND granularity = :granularity
                      AND data_hash IN ({placeholders})
                """)
                params = {
                    "data_domain": data_domain,
                    "sub_domain": sub_domain.lower(),
                    "granularity": granularity
                }
            else:
                sql = text(f"""
                    SELECT DISTINCT data_hash 
                    FROM {table_name}
                    WHERE data_domain = :data_domain 
                      AND granularity = :granularity
                      AND data_hash IN ({placeholders})
                """)
                params = {
                    "data_domain": data_domain,
                    "granularity": granularity
                }
            
            # ⭐ v4.18.2：支持异步会话
            result = await self.db.execute(sql, params)
            
            existing_hashes = {row[0] for row in result}
            
            logger.info(f"[Dedup] 批量查询已存在哈希: {len(existing_hashes)}/{len(data_hashes)}已存在（表={table_name}）")
            return existing_hashes
            
        except Exception as e:
            logger.error(f"[Dedup] 批量查询已存在哈希失败: {e}", exc_info=True)
            # 如果表不存在，返回空集合（新表，无历史数据）
            return set()
    
    def filter_duplicates(
        self,
        rows: List[Dict[str, Any]],
        data_hashes: List[str],
        existing_hashes: Set[str],
        file_id: Optional[int] = None
    ) -> Tuple[List[Dict[str, Any]], List[str], int]:
        """
        过滤重复数据
        
        Args:
            rows: 数据行列表
            data_hashes: 数据哈希列表（与rows对应）
            existing_hashes: 已存在的哈希集合
            file_id: 文件ID（用于文件内去重）
        
        Returns:
            (new_rows, new_hashes, duplicate_count)
        """
        if not rows:
            return [], [], 0
        
        # 文件内去重：同一文件内重复行
        seen_in_file: Set[str] = set()
        new_rows = []
        new_hashes = []
        duplicate_count = 0
        
        for i, (row, data_hash) in enumerate(zip(rows, data_hashes)):
            # 1. 文件内去重
            if data_hash in seen_in_file:
                duplicate_count += 1
                logger.debug(f"[Dedup] 文件内重复: 行{i+1}, hash={data_hash[:16]}...")
                continue
            
            # 2. 跨文件去重
            if data_hash in existing_hashes:
                duplicate_count += 1
                logger.debug(f"[Dedup] 跨文件重复: 行{i+1}, hash={data_hash[:16]}...")
                continue
            
            # 新数据
            seen_in_file.add(data_hash)
            new_rows.append(row)
            new_hashes.append(data_hash)
        
        logger.info(f"[Dedup] 过滤重复数据: {len(new_rows)}/{len(rows)}新数据，{duplicate_count}重复")
        return new_rows, new_hashes, duplicate_count
    
    async def deduplicate_batch(
        self,
        rows: List[Dict[str, Any]],
        data_domain: str,
        granularity: str,
        file_id: Optional[int] = None,
        exclude_fields: Optional[List[str]] = None,
        sub_domain: Optional[str] = None  # ⭐ v4.16.0新增：子类型（services域必须提供）
    ) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, int]]:
        """
        批量去重（完整流程）
        
        Args:
            rows: 数据行列表
            data_domain: 数据域
            granularity: 粒度
            file_id: 文件ID
            exclude_fields: 排除的字段列表
            sub_domain: 子类型（可选，services域必须提供）
        
        Returns:
            (new_rows, new_hashes, stats)
            stats: {total, duplicates, new, file_internal_duplicates, cross_file_duplicates}
        
        v4.18.2: 支持异步会话
        v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
        """
        start_time = datetime.now()
        
        try:
            # 1. 批量计算哈希
            data_hashes = self.batch_calculate_data_hash(rows, exclude_fields)
            
            # 2. 批量查询已存在的哈希（⭐ v4.18.2：异步方法）
            existing_hashes = await self.batch_check_existing_hashes(data_hashes, data_domain, granularity, sub_domain)
            
            # 3. 过滤重复数据
            new_rows, new_hashes, duplicate_count = self.filter_duplicates(
                rows, data_hashes, existing_hashes, file_id
            )
            
            # 4. 统计
            elapsed = (datetime.now() - start_time).total_seconds()
            stats = {
                'total': len(rows),
                'duplicates': duplicate_count,
                'new': len(new_rows),
                'file_internal_duplicates': 0,  # 文件内重复数（在filter_duplicates中计算）
                'cross_file_duplicates': len(existing_hashes.intersection(set(data_hashes))),
                'processing_time_seconds': elapsed,
                'throughput_rows_per_second': len(rows) / elapsed if elapsed > 0 else 0
            }
            
            logger.info(
                f"[Dedup] 批量去重完成: "
                f"总计={stats['total']}, "
                f"新数据={stats['new']}, "
                f"重复={stats['duplicates']}, "
                f"耗时={elapsed:.2f}s, "
                f"吞吐量={stats['throughput_rows_per_second']:.1f}行/秒"
            )
            
            return new_rows, new_hashes, stats
            
        except Exception as e:
            logger.error(f"[Dedup] 批量去重失败: {e}", exc_info=True)
            # 失败时返回原始数据（不阻塞入库）
            return rows, [], {
                'total': len(rows),
                'duplicates': 0,
                'new': len(rows),
                'error': str(e)
            }


def get_deduplication_service(db: AsyncSession) -> DeduplicationService:
    """
    获取去重服务实例
    
    ⭐ v4.18.2：支持异步会话
    ⭐ v4.19.0更新：移除同步/异步双模式支持，统一为异步架构
    """
    return DeduplicationService(db)

