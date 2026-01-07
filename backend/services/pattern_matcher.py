#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
模式匹配引擎（v4.6.0核心）

功能：
1. Pattern-based Field Mapping（正则模式匹配）
2. 多维度提取（订单状态、货币、其他维度）
3. 配置驱动（零硬编码）
4. 智能降级（精确→模糊→AI建议）

使用示例：
    matcher = PatternMatcher(db)
    result = await matcher.match_field(
        original_field="销售额 (已付款订单) (BRL)",
        data_domain="orders"
    )
    # 返回：{
    #     "matched": True,
    #     "standard_field": "sales_amount",
    #     "dimensions": {"order_status": "paid", "currency": "BRL"},
    #     "target_columns": {...}
    # }
"""

import re
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from modules.core.db import FieldMappingDictionary
from modules.core.logger import get_logger
from .currency_normalizer import get_currency_normalizer

logger = get_logger(__name__)


class PatternMatcher:
    """
    模式匹配引擎
    
    设计原则：
    - 配置驱动：规则存储在数据库，零硬编码
    - 多维度支持：提取订单状态、货币等多个维度
    - 智能降级：精确匹配→模式匹配→模糊匹配
    """
    
    def __init__(self, db: Session):
        """
        初始化模式匹配引擎
        
        参数：
            db: 数据库会话
        """
        self.db = db
        self.normalizer = get_currency_normalizer()
        self._cache = {}  # 字典缓存
        
        logger.info("PatternMatcher initialized")
    
    def load_dictionary(self, data_domain: Optional[str] = None) -> List[FieldMappingDictionary]:
        """
        加载字段辞典（支持缓存）
        
        参数：
            data_domain: 数据域（如orders/products），None表示加载全部
        
        返回：
            字段辞典列表
        """
        cache_key = f"dict_{data_domain or 'all'}"
        
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        query = select(FieldMappingDictionary).where(
            FieldMappingDictionary.active == True,
            FieldMappingDictionary.status == 'active'
        )
        
        if data_domain:
            query = query.where(FieldMappingDictionary.data_domain == data_domain)
        
        query = query.order_by(FieldMappingDictionary.match_weight.desc())
        
        dictionary = self.db.execute(query).scalars().all()
        
        self._cache[cache_key] = dictionary
        logger.info(f"Loaded {len(dictionary)} dictionary entries for domain '{data_domain or 'all'}'")
        
        return dictionary
    
    def match_field(
        self,
        original_field: str,
        data_domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        匹配字段（智能降级策略）
        
        策略：
        1. 精确匹配（cn_name或synonyms）
        2. 模式匹配（field_pattern正则）
        3. 模糊匹配（相似度匹配）
        
        参数：
            original_field: 原始字段名（如"销售额 (已付款订单) (BRL)"）
            data_domain: 数据域（可选）
        
        返回：
            匹配结果字典：
            {
                "matched": bool,
                "standard_field": str,
                "confidence": float,
                "match_method": str,
                "dimensions": dict,  # 提取的维度
                "target_table": str,
                "target_columns": dict
            }
        """
        dictionary = self.load_dictionary(data_domain)
        
        # 策略1：精确匹配
        result = self._exact_match(original_field, dictionary)
        if result["matched"]:
            return result
        
        # 策略2：模式匹配（v4.6.0核心功能）
        result = self._pattern_match(original_field, dictionary)
        if result["matched"]:
            return result
        
        # 策略3：模糊匹配
        result = self._fuzzy_match(original_field, dictionary)
        if result["matched"]:
            return result
        
        # 未匹配
        logger.warning(f"No match found for field: '{original_field}'")
        return {
            "matched": False,
            "standard_field": None,
            "confidence": 0.0,
            "match_method": "none",
            "original_field": original_field
        }
    
    def _exact_match(
        self,
        original_field: str,
        dictionary: List[FieldMappingDictionary]
    ) -> Dict[str, Any]:
        """
        精确匹配策略
        
        匹配规则：
        1. cn_name完全匹配
        2. synonyms完全匹配
        3. en_name完全匹配
        """
        original_lower = original_field.lower().strip()
        
        for entry in dictionary:
            # 1. 中文名称匹配
            if entry.cn_name and entry.cn_name.lower().strip() == original_lower:
                logger.debug(f"Exact match (cn_name): '{original_field}' → '{entry.field_code}'")
                return {
                    "matched": True,
                    "standard_field": entry.field_code,
                    "confidence": 1.0,
                    "match_method": "exact_cn_name",
                    "dictionary_id": entry.id,
                    "dimensions": {},
                    "target_table": entry.target_table,
                    "target_columns": entry.target_columns or {}
                }
            
            # 2. 同义词匹配
            if entry.synonyms:
                synonyms_list = entry.synonyms if isinstance(entry.synonyms, list) else []
                if original_field in synonyms_list:
                    logger.debug(f"Exact match (synonym): '{original_field}' → '{entry.field_code}'")
                    return {
                        "matched": True,
                        "standard_field": entry.field_code,
                        "confidence": 1.0,
                        "match_method": "exact_synonym",
                        "dictionary_id": entry.id,
                        "dimensions": {},
                        "target_table": entry.target_table,
                        "target_columns": entry.target_columns or {}
                    }
            
            # 3. 英文名称匹配
            if entry.en_name and entry.en_name.lower().strip() == original_lower:
                logger.debug(f"Exact match (en_name): '{original_field}' → '{entry.field_code}'")
                return {
                    "matched": True,
                    "standard_field": entry.field_code,
                    "confidence": 1.0,
                    "match_method": "exact_en_name",
                    "dictionary_id": entry.id,
                    "dimensions": {},
                    "target_table": entry.target_table,
                    "target_columns": entry.target_columns or {}
                }
        
        return {"matched": False}
    
    def _pattern_match(
        self,
        original_field: str,
        dictionary: List[FieldMappingDictionary]
    ) -> Dict[str, Any]:
        """
        模式匹配策略（v4.6.0核心功能）⭐⭐⭐
        
        匹配规则：
        1. 使用field_pattern正则表达式匹配
        2. 提取命名组作为维度（如order_status, currency）
        3. 使用dimension_config映射维度值
        
        示例：
            原始字段："销售额 (已付款订单) (BRL)"
            正则："销售额\\s*\\((?P<order_status>.+?)\\)\\s*\\((?P<currency>[A-Z]{3})\\)"
            提取：{"order_status": "已付款订单", "currency": "BRL"}
            映射：{"order_status": "paid", "currency": "BRL"}
        """
        for entry in dictionary:
            # 只处理启用了pattern-based的字段
            if not entry.is_pattern_based or not entry.field_pattern:
                continue
            
            try:
                # 执行正则匹配
                match = re.match(entry.field_pattern, original_field, re.IGNORECASE)
                
                if match:
                    # 提取维度
                    dimensions = match.groupdict()
                    
                    # 映射维度值
                    mapped_dimensions = self._map_dimensions(dimensions, entry.dimension_config or {})
                    
                    logger.debug(f"Pattern match: '{original_field}' → '{entry.field_code}' with dimensions {mapped_dimensions}")
                    
                    return {
                        "matched": True,
                        "standard_field": entry.field_code,
                        "confidence": 0.95,  # 模式匹配置信度略低于精确匹配
                        "match_method": "pattern",
                        "dictionary_id": entry.id,
                        "dimensions": mapped_dimensions,
                        "target_table": entry.target_table,
                        "target_columns": entry.target_columns or {},
                        "pattern": entry.field_pattern
                    }
            
            except re.error as e:
                logger.error(f"Invalid regex pattern in dictionary entry {entry.id}: {entry.field_pattern} - {e}")
                continue
            except Exception as e:
                logger.error(f"Pattern match error for entry {entry.id}: {e}")
                continue
        
        return {"matched": False}
    
    def _map_dimensions(
        self,
        dimensions: Dict[str, str],
        dimension_config: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        映射维度值
        
        参数：
            dimensions: 提取的原始维度（如{"order_status": "已付款订单", "currency": "BRL"}）
            dimension_config: 维度配置（如{"order_status": {"已付款订单": "paid"}, "currency": {"type": "normalize"}}）
        
        返回：
            映射后的维度（如{"order_status": "paid", "currency": "BRL"}）
        """
        mapped = {}
        
        for dim_name, dim_value in dimensions.items():
            if dim_value is None:
                mapped[dim_name] = None
                continue
            
            # 获取该维度的配置
            dim_config = dimension_config.get(dim_name, {})
            
            if not dim_config:
                # 无配置，直接使用原值
                mapped[dim_name] = dim_value
                continue
            
            config_type = dim_config.get("type")
            
            if config_type == "normalize":
                # 货币标准化
                if dim_name == "currency":
                    mapped[dim_name] = self.normalizer.normalize(dim_value)
                else:
                    mapped[dim_name] = dim_value
            
            elif config_type == "enum" or isinstance(dim_config, dict):
                # 枚举映射
                mapping = dim_config.get("mapping", dim_config) if config_type == "enum" else dim_config
                mapped[dim_name] = mapping.get(dim_value, dim_value)
            
            elif config_type == "extract":
                # 直接提取
                mapped[dim_name] = dim_value
            
            else:
                # 默认使用原值
                mapped[dim_name] = dim_value
        
        return mapped
    
    def _fuzzy_match(
        self,
        original_field: str,
        dictionary: List[FieldMappingDictionary]
    ) -> Dict[str, Any]:
        """
        模糊匹配策略（最后降级）
        
        匹配规则：
        1. 计算字符串相似度
        2. 返回最相似的（相似度>0.7）
        
        注意：此方法为简化实现，生产环境建议使用更复杂的相似度算法
        """
        original_lower = original_field.lower().strip()
        best_match = None
        best_score = 0.0
        
        for entry in dictionary:
            if not entry.cn_name:
                continue
            
            # 简单相似度计算：Jaccard相似度
            score = self._jaccard_similarity(original_lower, entry.cn_name.lower().strip())
            
            if score > best_score and score > 0.7:  # 阈值0.7
                best_score = score
                best_match = entry
        
        if best_match:
            logger.debug(f"Fuzzy match: '{original_field}' → '{best_match.field_code}' (score={best_score:.2f})")
            return {
                "matched": True,
                "standard_field": best_match.field_code,
                "confidence": best_score,
                "match_method": "fuzzy",
                "dictionary_id": best_match.id,
                "dimensions": {},
                "target_table": best_match.target_table,
                "target_columns": best_match.target_columns or {}
            }
        
        return {"matched": False}
    
    def _jaccard_similarity(self, str1: str, str2: str) -> float:
        """
        计算Jaccard相似度
        
        公式：|A ∩ B| / |A ∪ B|
        """
        set1 = set(str1)
        set2 = set(str2)
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def batch_match_fields(
        self,
        field_list: List[str],
        data_domain: Optional[str] = None
    ) -> Dict[str, Dict[str, Any]]:
        """
        批量匹配字段（性能优化）
        
        参数：
            field_list: 字段列表
            data_domain: 数据域
        
        返回：
            {original_field: match_result} 字典
        """
        results = {}
        
        for field in field_list:
            results[field] = self.match_field(field, data_domain)
        
        logger.info(f"Batch matched {len(field_list)} fields, success rate: {sum(1 for r in results.values() if r['matched']) / len(field_list) * 100:.1f}%")
        
        return results
    
    def clear_cache(self):
        """清空缓存"""
        self._cache = {}
        logger.debug("Pattern matcher cache cleared")


# 全局单例（推荐用法）
_matcher_instance = None

def get_pattern_matcher(db: Session) -> PatternMatcher:
    """获取模式匹配引擎（工厂方法）"""
    return PatternMatcher(db)



