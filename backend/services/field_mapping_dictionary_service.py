#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段映射辞典服务 - v4.3.7
DB+缓存架构，提供中文友好的字段映射辞典查询
"""

from typing import List, Dict, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import select, or_
from modules.core.db import FieldMappingDictionary
from modules.core.logger import get_logger
import time

logger = get_logger(__name__)


# 跨域通用字段（当某域字段过少时进行补充）
COMMON_FIELDS_BY_DOMAIN: Dict[str, List[str]] = {
    "traffic": [
        "unique_visitors",
        "page_views",
        "click_through_rate",
        "add_to_cart_count",
        "conversion_rate",
        "order_count",
    ],
}


class FieldMappingDictionaryService:
    """字段映射辞典服务（DB+缓存）"""
    
    def __init__(self, db: Session):
        self.db = db
        self._cache = {}  # 内存缓存
        self._cache_time = 0  # 缓存时间戳
        self._cache_ttl = 300  # 缓存有效期5分钟
    
    def get_dictionary(
        self,
        data_domain: Optional[str] = None,
        active_only: bool = True,
        force_refresh: bool = False
    ) -> List[Dict]:
        """
        获取字段辞典（带缓存）
        
        Args:
            data_domain: 数据域过滤（orders/products/traffic/services）
            active_only: 仅返回活跃字段
            force_refresh: 强制刷新缓存
            
        Returns:
            字段辞典列表
        """
        cache_key = f"{data_domain or 'all'}_{active_only}"
        
        # 检查缓存
        current_time = time.time()
        if (not force_refresh and 
            cache_key in self._cache and 
            (current_time - self._cache_time) < self._cache_ttl):
            logger.debug(f"[Dictionary] 缓存命中: {cache_key}")
            return self._cache[cache_key]
        
        # 从数据库查询（使用原生SQL避免ORM schema不匹配问题）
        try:
            from sqlalchemy import text
            
            # 构建SQL查询（只查询必需字段，避免version/status导致的schema不匹配）
            sql = """
                SELECT 
                    id, field_code, cn_name, en_name, description,
                    data_domain, field_group, is_required, data_type,
                    value_range, synonyms, platform_synonyms, example_values,
                    display_order, match_weight, active, is_mv_display,
                    created_by, created_at, updated_by, updated_at, notes
                FROM field_mapping_dictionary
                WHERE 1=1
            """
            
            params = {}
            
            if data_domain:
                sql += " AND (data_domain = :data_domain OR data_domain = 'general')"
                params['data_domain'] = data_domain
            
            if active_only:
                sql += " AND active = true AND status = 'active'"
            
            sql += " ORDER BY is_required DESC NULLS LAST, display_order ASC, field_code ASC"
            
            result = self.db.execute(text(sql), params)
            rows = result.fetchall()
            
            # 转换为对象列表
            class DictEntry:
                def __init__(self, row):
                    self.id = row[0]
                    self.field_code = row[1]
                    self.cn_name = row[2]
                    self.en_name = row[3]
                    self.description = row[4]
                    self.data_domain = row[5]
                    self.field_group = row[6]
                    self.is_required = row[7]
                    self.data_type = row[8]
                    self.value_range = row[9]
                    self.synonyms = row[10]
                    self.platform_synonyms = row[11]
                    self.example_values = row[12]
                    self.display_order = row[13]
                    self.match_weight = row[14]
                    self.active = row[15]
                    self.is_mv_display = row[16] if len(row) > 16 else False  # v4.10.2新增
            
            entries = [DictEntry(row) for row in rows]

            # 如果指定数据域仍然为空，最后兜底返回全部活跃字段，避免前端下拉为空
            if data_domain and not entries:
                logger.warning(f"[Dictionary] {data_domain} 为空，使用全量兜底")
                # 使用原生SQL查询全部字段
                fallback_sql = """
                    SELECT 
                        id, field_code, cn_name, en_name, description,
                        data_domain, field_group, is_required, data_type,
                        value_range, synonyms, platform_synonyms, example_values,
                        display_order, match_weight, active, is_mv_display,
                        created_by, created_at, updated_by, updated_at, notes
                    FROM field_mapping_dictionary
                    WHERE active = true AND status = 'active'
                    ORDER BY is_required DESC NULLS LAST, display_order ASC, field_code ASC
                """
                fallback_result = self.db.execute(text(fallback_sql))
                fallback_rows = fallback_result.fetchall()
                entries = [DictEntry(row) for row in fallback_rows]
            
            # 如果字段过少，按域补充通用字段（按field_code跨域合并）
            need_codes: List[str] = COMMON_FIELDS_BY_DOMAIN.get(data_domain or "", [])
            if need_codes:
                existing_codes: Set[str] = {e.field_code for e in entries}
                missing_codes = [c for c in need_codes if c not in existing_codes]
                if missing_codes:
                    # 使用原生SQL查询补充字段
                    placeholders = ','.join([f"'{code}'" for code in missing_codes])
                    extra_sql = f"""
                        SELECT 
                            id, field_code, cn_name, en_name, description,
                            data_domain, field_group, is_required, data_type,
                            value_range, synonyms, platform_synonyms, example_values,
                            display_order, match_weight, active, is_mv_display,
                            created_by, created_at, updated_by, updated_at, notes
                        FROM field_mapping_dictionary
                        WHERE field_code IN ({placeholders})
                    """
                    extra_result = self.db.execute(text(extra_sql))
                    extra_rows = extra_result.fetchall()
                    extras = [DictEntry(row) for row in extra_rows]
                    entries.extend(extras)

            # 转换为字典格式（按field_code去重）
            seen: Set[str] = set()
            result: List[Dict] = []
            for entry in entries:
                if entry.field_code in seen:
                    continue
                seen.add(entry.field_code)
                result.append({
                    "field_code": entry.field_code,
                    "cn_name": entry.cn_name,
                    "en_name": entry.en_name,
                    "description": entry.description,
                    "data_domain": entry.data_domain,
                    "field_group": entry.field_group,
                    "is_required": entry.is_required,
                    "data_type": entry.data_type,
                    "value_range": entry.value_range,
                    "synonyms": entry.synonyms or [],
                    "platform_synonyms": entry.platform_synonyms or {},
                    "example_values": entry.example_values or [],
                    "display_order": entry.display_order,
                    "match_weight": entry.match_weight,
                    "is_mv_display": getattr(entry, 'is_mv_display', False) if hasattr(entry, 'is_mv_display') else False  # v4.10.2新增
                })
            
            # 更新缓存
            self._cache[cache_key] = result
            self._cache_time = current_time
            
            logger.info(f"[Dictionary] 加载{len(result)}条字段（{cache_key}）")
            return result
            
        except Exception as e:
            logger.error(f"[Dictionary] 加载失败: {e}")
            return []
    
    def get_field_by_code(self, field_code: str) -> Optional[Dict]:
        """根据字段代码获取单个字段信息"""
        try:
            stmt = select(FieldMappingDictionary).where(
                FieldMappingDictionary.field_code == field_code
            )
            entry = self.db.execute(stmt).scalar_one_or_none()
            
            if not entry:
                return None
            
            return {
                "field_code": entry.field_code,
                "cn_name": entry.cn_name,
                "en_name": entry.en_name,
                "description": entry.description,
                "data_domain": entry.data_domain,
                "field_group": entry.field_group,
                "is_required": entry.is_required,
                "data_type": entry.data_type,
                "value_range": entry.value_range,
                "synonyms": entry.synonyms or [],
                "platform_synonyms": entry.platform_synonyms or {},
                "example_values": entry.example_values or [],
                "display_order": entry.display_order,
                "match_weight": entry.match_weight,
                "is_mv_display": entry.is_mv_display if hasattr(entry, 'is_mv_display') else False  # v4.10.2新增
            }
        except Exception as e:
            logger.error(f"[Dictionary] 获取字段失败: {e}")
            return None
    
    def search_fields(
        self,
        query: str,
        data_domain: Optional[str] = None,
        search_in: List[str] = None
    ) -> List[Dict]:
        """
        搜索字段（支持中文/拼音/缩写）
        
        Args:
            query: 搜索关键词
            data_domain: 数据域过滤
            search_in: 搜索范围 ["cn_name", "synonyms", "field_code"]
            
        Returns:
            匹配的字段列表
        """
        if not query:
            return self.get_dictionary(data_domain=data_domain)
        
        if search_in is None:
            search_in = ["cn_name", "synonyms", "field_code"]
        
        # 获取全部字段
        all_fields = self.get_dictionary(data_domain=data_domain)
        
        # 搜索过滤
        query_lower = query.lower()
        matched_fields = []
        
        for field in all_fields:
            # 搜索中文名
            if "cn_name" in search_in and query_lower in field["cn_name"].lower():
                matched_fields.append(field)
                continue
            
            # 搜索字段代码
            if "field_code" in search_in and query_lower in field["field_code"].lower():
                matched_fields.append(field)
                continue
            
            # 搜索同义词
            if "synonyms" in search_in:
                synonyms = field.get("synonyms", [])
                if any(query_lower in syn.lower() for syn in synonyms):
                    matched_fields.append(field)
                    continue
        
        logger.info(f"[Dictionary] 搜索'{query}'：找到{len(matched_fields)}个字段")
        return matched_fields
    
    def get_required_fields(self, data_domain: str) -> List[Dict]:
        """获取必填字段列表"""
        all_fields = self.get_dictionary(data_domain=data_domain)
        return [f for f in all_fields if f["is_required"]]
    
    def get_fields_by_group(self, data_domain: str) -> Dict[str, List[Dict]]:
        """按分组获取字段"""
        all_fields = self.get_dictionary(data_domain=data_domain)
        
        grouped = {}
        for field in all_fields:
            group = field.get("field_group", "other")
            if group not in grouped:
                grouped[group] = []
            grouped[group].append(field)
        
        return grouped
    
    def clear_cache(self):
        """清空缓存"""
        self._cache = {}
        self._cache_time = 0
        logger.info("[Dictionary] 缓存已清空")


def get_dictionary_service(db: Session) -> FieldMappingDictionaryService:
    """获取辞典服务实例"""
    return FieldMappingDictionaryService(db)

