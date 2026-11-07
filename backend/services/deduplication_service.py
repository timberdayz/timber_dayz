#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多层数据去重服务(Multi-Layer Deduplication Service)

v4.6.0新增:
- 文件级去重:基于file_hash检查
- 文件内去重:基于data_hash检查(同一文件内重复行)
- 跨文件去重:基于data_hash检查(不同文件间重复行)
- 业务语义去重:基于业务唯一键检查(如订单号、产品ID等)

职责:
- 计算数据哈希(data_hash)
- 批量查询已存在的哈希
- 过滤重复数据
- 性能优化(批量查询、向量化计算)
"""

from typing import List, Dict, Any, Set, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession  # [*] v4.18.2新增:异步支持
from sqlalchemy import select, func, and_
from datetime import date, datetime
import hashlib
import json
import pandas as pd

from modules.core.db import CatalogFile
from modules.core.logger import get_logger
from backend.services.semantic_field_registry import (
    get_semantic_requirements,
    is_canonical_semantic_key,
    normalize_semantic_key,
    resolve_semantic_value,
)
logger = get_logger(__name__)


class DeduplicationService:
    """
    多层数据去重服务
    
    去重策略(从粗到细):
    1. 文件级去重:基于file_hash(最快,跳过整个文件)
    2. 文件内去重:基于data_hash(同一文件内重复行)
    3. 跨文件去重:基于data_hash(不同文件间重复行)
    4. 业务语义去重:基于业务唯一键(如订单号、产品ID等)
    
    v4.18.2: 支持异步会话
    v4.19.0更新:移除同步/异步双模式支持,统一为异步架构
    """

    # 去重作用域的维度键（固定维度，不随店铺变化）
    _SCOPE_DIMENSION_KEYS = ("platform_code", "data_domain", "granularity", "sub_domain")

    # 去重作用域的身份键（稳定身份优先，只取第一个可用的）
    _SCOPE_IDENTITY_KEYS = ("shop_account_id", "platform_shop_id", "shop_id")

    def __init__(self, db: AsyncSession):
        """
        初始化去重服务
        
        Args:
            db: 异步数据库会话(AsyncSession)
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
        v4.19.0更新:移除同步/异步双模式支持,统一为异步架构
        """
        try:
            # [*] v4.18.2:支持异步会话
            result = await self.db.execute(
                select(CatalogFile).where(CatalogFile.id == file_id)
            )
            file_record = result.scalar_one_or_none()
            
            if not file_record:
                return False, None
            
            # 检查文件状态
            if file_record.status == 'ingested':
                return True, f"文件已处理(status=ingested)"
            
            # 检查file_hash(如果存在)
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
                    return True, f"文件哈希重复(file_hash={file_record.file_hash[:16]}...,已处理文件ID={existing.id})"
            
            return False, None
            
        except Exception as e:
            logger.error(f"[Dedup] 文件级去重检查失败: {e}", exc_info=True)
            return False, None
    
    def calculate_data_hash(
        self,
        row: Dict[str, Any],
        exclude_fields: Optional[List[str]] = None,
        deduplication_fields: Optional[List[str]] = None,
        header_bindings: Optional[List[Dict[str, Any]]] = None,
        scope_values: Optional[Dict[str, Any]] = None,
        identity_values: Optional[Dict[str, Any]] = None,
        core_fields: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        计算单行数据的哈希值

        Args:
            row: 数据行字典
            exclude_fields: 排除的字段列表(元数据字段,如file_id、ingest_timestamp等)
            deduplication_fields: 核心去重字段列表(可选,如果提供则只使用这些字段计算hash)
            core_fields: [*] 批次 E: 版本级核心字段清单。
                提供时**优先于** ``deduplication_fields``, 取值口径变成
                「标准含义优先, 逐字兜底」(见
                :func:`backend.services.core_fields_service.resolve_core_field_value`)。
                这是规格 §6.1 要求的「显式开关」的新口径, 可一键回退。

        Returns:
            data_hash (SHA256, 64字符)
        """
        if exclude_fields is None:
            exclude_fields = ['file_id', 'ingest_timestamp', 'id', 'created_at', 'updated_at']
        scope_hash_data = self._build_scope_hash_data(scope_values)

        if core_fields:
            business_data, missing_fields, missing_required_fields = self._build_core_field_hash_data(
                row,
                core_fields=core_fields,
                deduplication_fields=deduplication_fields,
                header_bindings=header_bindings,
                identity_values=identity_values,
                scope_hash_data=scope_hash_data,
            )
            self._log_core_field_hash_notes(
                missing_fields=missing_fields,
                missing_required_fields=missing_required_fields,
                expected_count=len(core_fields),
                business_data=business_data,
            )
        # v4.14.0新增:如果提供了核心字段,只使用核心字段计算hash
        elif deduplication_fields:
            business_data = dict(scope_hash_data)
            missing_fields = []
            # 只使用核心字段
            missing_fields = []
            missing_required_fields = []
            for field in deduplication_fields:
                field_text = str(field or "").strip()
                semantic_key = normalize_semantic_key(field_text) if is_canonical_semantic_key(field_text) else None
                identity_key = semantic_key or field_text
                if identity_values and identity_key:
                    override_value = identity_values.get(identity_key)
                    if override_value is None and field_text != identity_key:
                        override_value = identity_values.get(field_text)
                    if override_value is not None and str(override_value).strip() != "":
                        business_data[identity_key] = self._normalize_hash_value(override_value)
                        continue
                # [*] 批次 E: 取值逻辑收敛到 _resolve_hash_field_value(新旧两条分支同源)
                value, business_key = self._resolve_hash_field_value(
                    row,
                    field,
                    header_bindings=header_bindings,
                )
                if business_key is not None:
                    business_data[business_key] = self._normalize_hash_value(value)
                    continue

                # 如果未找到匹配字段,记录警告(但不影响计算)
                missing_fields.append(field)
                if semantic_key and get_semantic_requirements(semantic_key).get("required"):
                    missing_required_fields.append(field)
                logger.debug(
                    f"[Dedup] 核心字段 {field} 在数据行中未找到,跳过(可用字段: {list(row.keys())[:5]}...)"
                )
            
            # 如果所有核心字段都缺失,记录严重警告
            if len(missing_fields) == len(deduplication_fields):
                logger.warning(
                    f"[Dedup] [WARN] 所有核心字段都未找到: {deduplication_fields},"
                    f"将使用空字典计算hash(可能导致所有行产生相同的hash)"
                )
            elif missing_required_fields:
                logger.info(
                    f"[Dedup] 部分核心字段未找到: {missing_required_fields},"
                    f"已找到的字段: {list(business_data.keys())}"
                )
            elif missing_fields:
                logger.debug(
                    f"[Dedup] 可选核心字段未找到: {missing_fields},"
                    f"已找到的字段: {list(business_data.keys())}"
                )
        else:
            # 使用所有业务字段(向后兼容)
            business_data = {
                k: v for k, v in row.items()
                if k not in exclude_fields and v is not None
            }
            business_data.update(scope_hash_data)
        
        # 排序键值对(确保一致性)
        sorted_items = sorted(business_data.items())
        
        # 转换为JSON字符串(确保可序列化)
        json_str = json.dumps(sorted_items, ensure_ascii=False, sort_keys=True)
        
        # 计算SHA256哈希
        hash_obj = hashlib.sha256(json_str.encode('utf-8'))
        data_hash = hash_obj.hexdigest()
        
        # 记录用于hash计算的字段(仅在前几行记录,避免日志过多)
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

    @staticmethod
    def _resolve_hash_field_value(
        row: Dict[str, Any],
        field: str,
        *,
        header_bindings: Optional[List[Dict[str, Any]]],
    ) -> Tuple[Any, Optional[str]]:
        """**hash 取值的 SSOT** —— 规范键走语义解析, 否则逐字匹配。

        新旧两条分支都必须走这里, 否则「同一份数据两套 hash」。

        Returns:
            ``(value, business_key)``。

            * ``business_key`` 是**写进 hash 载荷的键**(参与 hash)——
              取不到时为 ``None``;
            * 命中但值为 ``None`` 时, ``business_key`` **仍非 None**
              (旧口径把它算「命中」, 这里必须一致)。
        """
        field_text = str(field or "").strip()
        semantic_key = (
            normalize_semantic_key(field_text)
            if is_canonical_semantic_key(field_text)
            else None
        )
        if semantic_key:
            semantic_value, _matched = resolve_semantic_value(
                row,
                semantic_key,
                header_bindings=header_bindings,
            )
            if semantic_value is not None:
                return semantic_value, semantic_key

        # 支持中英文字段名匹配(模糊匹配)
        # 单次遍历: 精确匹配与「忽略大小写」按 row 的列顺序判断, 先命中先算。
        # (不能改成「先扫精确、再扫大小写」—— 命中列不同 ⇒ 载荷键不同 ⇒ hash 不同)
        for key in row.keys():
            if key == field:
                return row[key], key
            if str(key).lower() == str(field).lower():
                return row[key], key
        return None, None

    def _build_core_field_hash_data(
        self,
        row: Dict[str, Any],
        *,
        core_fields: List[Dict[str, Any]],
        deduplication_fields: Optional[List[str]],
        header_bindings: Optional[List[Dict[str, Any]]],
        identity_values: Optional[Dict[str, Any]],
        scope_hash_data: Dict[str, Any],
    ) -> Tuple[Dict[str, Any], List[str], List[str]]:
        """按版本级核心字段清单算 hash 载荷(批次 E 新口径)。

        字段集合 vs 取值方式
        --------------------
        * **字段集合** = 调用方传进来的 ``deduplication_fields``
          (旧口径算好的**完整**链: 模板字段 + ``platform_code``/``shop_id``/
          ``sub_domain`` + orders 域扩展 + auto-date 身份字段)。
          **绝不**在这里自己重建集合 —— 少一个系统身份字段,
          hash 就与旧口径不同 ⇒ 已入库的行全部变成「没见过的数据」。
        * **取值方式** = 清单驱动: 清单里的字段走「逐字优先, 语义兜底」;
          集合里**不在清单中**的系统字段走旧口径通用取值。

        与旧口径的**逐字等价性**
        ------------------------
        1. 载荷**键名**: 清单字段用 ``raw_name`` 优先(= 旧口径键名);
           系统字段用旧口径通用取值(键名不变)。
        2. 载荷**取值**: 清单字段先按旧口径逐字取 ⇒ 同值同键;
           只有旧口径**取不到**(平台改了列名)时, 才按标准含义兜底
           ⇒ 旧口径会丢字段的场景, 新口径把字段救回来。
        """
        from backend.services.core_fields_service import (
            normalize_core_fields,
            resolve_core_field_value,
        )

        business_data: Dict[str, Any] = dict(scope_hash_data)
        missing_fields: List[str] = []
        missing_required_fields: List[str] = []

        entry_by_key: Dict[str, Dict[str, Any]] = {}
        for entry in normalize_core_fields(core_fields):
            if not entry.get("in_hash"):
                continue
            hash_key = entry.get("raw_name") or entry.get("semantic_key") or ""
            if not hash_key or hash_key in entry_by_key:
                continue
            entry_by_key[hash_key] = entry

        # 字段集合: 用旧口径算好的完整链; 没传就退回清单自身的身份。
        fields = list(deduplication_fields or entry_by_key.keys())

        for field in fields:
            field_text = str(field or "").strip()
            entry = entry_by_key.get(field_text)
            semantic_key = (
                normalize_semantic_key(field_text)
                if is_canonical_semantic_key(field_text)
                else None
            )
            identity_key = semantic_key or field_text

            if identity_values and identity_key:
                override_value = identity_values.get(identity_key)
                if override_value is None and field_text != identity_key:
                    override_value = identity_values.get(field_text)
                if override_value is not None and str(override_value).strip() != "":
                    business_data[identity_key] = self._normalize_hash_value(override_value)
                    continue

            if entry is not None:
                # 清单字段 ⇒ 逐字优先, 语义兜底
                value, business_key, degraded = resolve_core_field_value(
                    row,
                    entry,
                    header_bindings=header_bindings,
                )
                if business_key is not None:
                    business_data[business_key] = self._normalize_hash_value(value)
                    if degraded:
                        logger.debug(
                            "[Dedup] 核心字段 %s 逐字未命中, 已按标准含义兜底取值(列=%s)",
                            identity_key,
                            business_key,
                        )
                    continue
            else:
                # 系统身份字段 ⇒ 旧口径通用取值
                value, business_key = self._resolve_hash_field_value(
                    row,
                    field,
                    header_bindings=header_bindings,
                )
                if business_key is not None:
                    business_data[business_key] = self._normalize_hash_value(value)
                    continue

            missing_fields.append(field)
            if entry is not None:
                if entry.get("required"):
                    missing_required_fields.append(identity_key)
            elif semantic_key and get_semantic_requirements(semantic_key).get("required"):
                missing_required_fields.append(field)
            logger.debug(
                "[Dedup] 核心字段 %s 在数据行中未找到,跳过(可用字段: %s)",
                identity_key,
                list(row.keys())[:5],
            )

        return business_data, missing_fields, missing_required_fields

    @staticmethod
    def _log_core_field_hash_notes(
        *,
        missing_fields: List[str],
        missing_required_fields: List[str],
        expected_count: int,
        business_data: Dict[str, Any],
    ) -> None:
        """核心字段缺失的日志(与旧口径同结构, 便于对照排查)。"""
        if len(missing_fields) == expected_count and expected_count:
            logger.warning(
                f"[Dedup] [WARN] 所有核心字段都未找到: {missing_fields},"
                f"将使用空字典计算hash(可能导致所有行产生相同的hash)"
            )
        elif missing_required_fields:
            logger.info(
                f"[Dedup] 部分核心字段未找到: {missing_required_fields},"
                f"已找到的字段: {list(business_data.keys())}"
            )
        elif missing_fields:
            logger.debug(
                f"[Dedup] 可选核心字段未找到: {missing_fields},"
                f"已找到的字段: {list(business_data.keys())}"
            )

    @staticmethod
    def _build_scope_hash_data(scope_values: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """构造去重作用域（data_hash 的"店铺/数据域"部分）。

        口径（Task 10）：
        - 维度键固定：``platform_code`` / ``data_domain`` / ``granularity`` / ``sub_domain``；
        - 身份键只取**第一个可用的稳定身份**：
          ``shop_account_id``（永不变化）> ``platform_shop_id`` > ``shop_id``。

        为什么身份键只取一个：
        - ``shop_id`` 随改名变化，**不能单独决定去重**（同一份数据改名后会重复入库）；
        - ``shop_account_id`` 与 ``platform_shop_id`` 在同一个店铺上是一一对应的，
          同时放进作用域不会增加区分度，却会让"后补一个字段"变成一次口径变更
          （回填 platform_shop_id 会让已经算好的 hash 全部作废）；
        - 只取一个身份键 -> 身份一旦确定，口径就**不再变化**（幂等）。

        口径变更的影响：作用域里的键/值变了 => 已入库行的 ``data_hash`` 与新算出的
        hash 不同 => 同一份数据再采一次会被当成新数据插入。
        因此**回填必须先行**，并且回填后需要按"需重建清单"重建受影响文件的事实行
        （见 ``backend/services/catalog_files_identity_backfill.py`` 的报告）。
        """
        if not scope_values:
            return {}

        scope_hash_data: Dict[str, Any] = {}
        for key in DeduplicationService._SCOPE_DIMENSION_KEYS:
            value = scope_values.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            scope_hash_data[f"scope:{key}"] = text

        for key in DeduplicationService._SCOPE_IDENTITY_KEYS:
            value = scope_values.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if not text:
                continue
            scope_hash_data[f"scope:{key}"] = text
            break

        return scope_hash_data

    @staticmethod
    def _normalize_hash_value(value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    @staticmethod
    def _identity_values_for_row(
        identity_values: Optional[List[Dict[str, Any]] | Dict[str, Any]],
        index: int,
    ) -> Optional[Dict[str, Any]]:
        if not identity_values:
            return None
        if isinstance(identity_values, list):
            if index >= len(identity_values):
                return None
            row_values = identity_values[index]
            return row_values if isinstance(row_values, dict) else None
        return identity_values if isinstance(identity_values, dict) else None
     
    def batch_calculate_data_hash(
        self,
        rows: List[Dict[str, Any]],
        exclude_fields: Optional[List[str]] = None,
        deduplication_fields: Optional[List[str]] = None,
        header_bindings: Optional[List[Dict[str, Any]]] = None,
        scope_values: Optional[Dict[str, Any]] = None,
        identity_values: Optional[List[Dict[str, Any]] | Dict[str, Any]] = None,
        core_fields: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """
        批量计算数据哈希(使用pandas向量化)

        Args:
            rows: 数据行列表
            exclude_fields: 排除的字段列表
            deduplication_fields: 核心去重字段列表(可选,如果提供则只使用这些字段计算hash)
            core_fields: [*] 批次 E: 版本级核心字段清单(优先于 deduplication_fields)

        Returns:
            data_hash列表(与rows长度相同)
        """
        if not rows:
            return []

        # v4.14.0新增:如果提供了核心字段,使用逐行计算(确保字段匹配正确)
        if core_fields or deduplication_fields:
            if core_fields:
                logger.info(
                    f"[Dedup] 使用核心字段清单计算hash: {len(core_fields)} 项,"
                    f"逐行计算以确保字段匹配正确(共{len(rows)}行)"
                )
            else:
                logger.info(
                    f"[Dedup] 使用核心字段计算hash: {deduplication_fields},"
                    f"逐行计算以确保字段匹配正确(共{len(rows)}行)"
                )
            # 重置日志计数器
            self._hash_log_count = 0
            hashes = [
                self.calculate_data_hash(
                    row,
                    exclude_fields,
                    deduplication_fields,
                    header_bindings,
                    scope_values,
                    self._identity_values_for_row(identity_values, index),
                    core_fields,
                )
                for index, row in enumerate(rows)
            ]
            # 验证hash唯一性(前10行)
            if len(hashes) > 0:
                unique_hashes = set(hashes[:min(10, len(hashes))])
                if len(unique_hashes) == 1 and len(hashes) > 1:
                    logger.warning(
                        f"[Dedup] [WARN] 警告:前{min(10, len(hashes))}行的data_hash都相同: {hashes[0][:8]}...,"
                        f"可能导致去重失败(所有行被识别为重复)"
                    )
            return hashes
        
        try:
            # 转换为DataFrame(性能优化)
            df = pd.DataFrame(rows)
            
            # 排除元数据字段
            if exclude_fields is None:
                exclude_fields = ['file_id', 'ingest_timestamp', 'id', 'created_at', 'updated_at']
            
            business_columns = [col for col in df.columns if col not in exclude_fields]
            df_business = df[business_columns].fillna('')
            
            # 批量计算哈希(向量化)
            def hash_row(row):
                sorted_items = sorted(row.items())
                json_str = json.dumps(sorted_items, ensure_ascii=False, sort_keys=True)
                return hashlib.sha256(json_str.encode('utf-8')).hexdigest()
            
            hashes = df_business.apply(hash_row, axis=1).tolist()
            
            logger.info(f"[Dedup] 批量计算哈希: {len(hashes)}行,耗时约{len(hashes) * 0.1:.1f}ms(估算)")
            return hashes
            
        except Exception as e:
            logger.error(f"[Dedup] 批量计算哈希失败,回退到逐行计算: {e}")
            # 回退到逐行计算
            return [
                self.calculate_data_hash(row, exclude_fields, deduplication_fields, header_bindings, scope_values)
                for row in rows
            ]
    
    async def batch_check_existing_hashes(
        self,
        data_hashes: List[str],
        data_domain: str,
        granularity: str,
        sub_domain: Optional[str] = None  # [*] v4.16.0新增:子类型(services域必须提供)
    ) -> Set[str]:
        """
        批量查询已存在的哈希(跨文件去重)
        
        Args:
            data_hashes: 数据哈希列表
            data_domain: 数据域
            granularity: 粒度
            sub_domain: 子类型(可选,services域必须提供)
        
        Returns:
            已存在的哈希集合
        
        v4.18.2: 支持异步/同步双模式
        """
        if not data_hashes:
            return set()
        
        try:
            # [*] v4.16.0更新:根据data_domain+granularity+sub_domain选择目标表
            if data_domain.lower() == 'services' and sub_domain:
                # Services域按sub_domain分表
                table_name = f"fact_raw_data_services_{sub_domain.lower()}_{granularity}"
            else:
                # 其他域使用标准格式
                table_name = f"fact_raw_data_{data_domain}_{granularity}"
            
            # 批量查询(使用IN查询,1次SQL替代N次)
            # 注意:这里需要动态构建查询,因为表名是动态的
            # 为了简化,我们使用原始SQL
            from sqlalchemy import text
            
            placeholders = ','.join([f"'{h}'" for h in data_hashes])
            
            # [*] v4.16.0更新:services域的表有sub_domain字段,需要额外过滤
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
            
            # [*] v4.18.2:支持异步会话
            result = await self.db.execute(sql, params)
            
            existing_hashes = {row[0] for row in result}
            
            logger.info(f"[Dedup] 批量查询已存在哈希: {len(existing_hashes)}/{len(data_hashes)}已存在(表={table_name})")
            return existing_hashes
            
        except Exception as e:
            logger.error(f"[Dedup] 批量查询已存在哈希失败: {e}", exc_info=True)
            # 如果表不存在,返回空集合(新表,无历史数据)
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
            data_hashes: 数据哈希列表(与rows对应)
            existing_hashes: 已存在的哈希集合
            file_id: 文件ID(用于文件内去重)
        
        Returns:
            (new_rows, new_hashes, duplicate_count)
        """
        if not rows:
            return [], [], 0
        
        # 文件内去重:同一文件内重复行
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
        
        logger.info(f"[Dedup] 过滤重复数据: {len(new_rows)}/{len(rows)}新数据,{duplicate_count}重复")
        return new_rows, new_hashes, duplicate_count
    
    async def deduplicate_batch(
        self,
        rows: List[Dict[str, Any]],
        data_domain: str,
        granularity: str,
        file_id: Optional[int] = None,
        exclude_fields: Optional[List[str]] = None,
        sub_domain: Optional[str] = None  # [*] v4.16.0新增:子类型(services域必须提供)
    ) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, int]]:
        """
        批量去重(完整流程)
        
        Args:
            rows: 数据行列表
            data_domain: 数据域
            granularity: 粒度
            file_id: 文件ID
            exclude_fields: 排除的字段列表
            sub_domain: 子类型(可选,services域必须提供)
        
        Returns:
            (new_rows, new_hashes, stats)
            stats: {total, duplicates, new, file_internal_duplicates, cross_file_duplicates}
        
        v4.18.2: 支持异步会话
        v4.19.0更新:移除同步/异步双模式支持,统一为异步架构
        """
        start_time = datetime.now()
        
        try:
            # 1. 批量计算哈希
            data_hashes = self.batch_calculate_data_hash(rows, exclude_fields)
            
            # 2. 批量查询已存在的哈希([*] v4.18.2:异步方法)
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
                'file_internal_duplicates': 0,  # 文件内重复数(在filter_duplicates中计算)
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
            # 失败时返回原始数据(不阻塞入库)
            return rows, [], {
                'total': len(rows),
                'duplicates': 0,
                'new': len(rows),
                'error': str(e)
            }


def get_deduplication_service(db: AsyncSession) -> DeduplicationService:
    """
    获取去重服务实例
    
    [*] v4.18.2:支持异步会话
    [*] v4.19.0更新:移除同步/异步双模式支持,统一为异步架构
    """
    return DeduplicationService(db)
