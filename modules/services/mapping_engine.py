#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能字段映射引擎

提供多层次的字段映射策略：
1. 精确匹配
2. 模糊匹配（字符串相似度）
3. 语义匹配（同义词库）
4. 历史学习
5. 数据内容分析
6. 外键识别
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from difflib import SequenceMatcher
import json
from pathlib import Path

@dataclass
class MappingResult:
    """映射结果"""
    source_column: str
    target_field: str
    confidence: float
    mapping_type: str  # 'exact', 'fuzzy', 'semantic', 'learned', 'foreign_key'
    transformation_rule: Optional[str] = None
    foreign_key_info: Optional[Dict[str, Any]] = None

@dataclass
class ForeignKeyMapping:
    """外键映射"""
    source_column: str
    target_table: str
    target_field: str
    confidence: float
    validation_query: Optional[str] = None

class SmartMappingEngine:
    """智能字段映射引擎"""
    
    def __init__(self):
        """初始化映射引擎"""
        self.synonym_dict = self._load_synonym_dict()
        self.mapping_history = self._load_mapping_history()
        self.foreign_key_patterns = self._load_foreign_key_patterns()
    
    def _load_synonym_dict(self) -> Dict[str, List[str]]:
        """加载同义词库"""
        return {
            # 商品相关
            "product_name": ["商品名称", "产品名称", "item_name", "product_title", "商品标题", "产品标题"],
            "product_sku": ["商品SKU", "产品SKU", "sku", "product_code", "商品编码", "产品编码"],
            "product_price": ["商品价格", "产品价格", "price", "cost", "amount", "价格", "金额"],
            "product_category": ["商品分类", "产品分类", "category", "分类", "类目"],
            
            # 订单相关
            "order_id": ["订单号", "订单ID", "order_number", "order_no", "订单编号"],
            "order_amount": ["订单金额", "总金额", "total_amount", "gmv", "订单总额"],
            "order_date": ["订单日期", "下单时间", "order_date", "date", "日期", "时间"],
            "customer_id": ["客户ID", "用户ID", "customer", "user", "客户", "用户"],
            
            # 店铺相关
            "shop_id": ["店铺ID", "商店ID", "shop", "store", "店铺", "商店"],
            "shop_name": ["店铺名称", "商店名称", "shop_name", "store_name", "店铺名"],
            
            # 平台相关
            "platform_code": ["平台", "platform", "site", "渠道", "平台代码"],
            
            # 通用字段
            "currency": ["货币", "币种", "currency", "curr", "货币代码"],
            "quantity": ["数量", "quantity", "qty", "数量"],
            "status": ["状态", "status", "状态码"],
            "description": ["描述", "说明", "description", "desc", "备注"],
        }
    
    def _load_foreign_key_patterns(self) -> Dict[str, Dict[str, Any]]:
        """加载外键模式"""
        return {
            "shop_id": {
                "patterns": ["shop", "store", "店铺", "商店"],
                "target_table": "dim_shops",
                "target_field": "shop_id"
            },
            "product_id": {
                "patterns": ["product", "item", "商品", "产品"],
                "target_table": "dim_products", 
                "target_field": "product_id"
            },
            "order_id": {
                "patterns": ["order", "订单"],
                "target_table": "fact_orders",
                "target_field": "order_id"
            },
            "customer_id": {
                "patterns": ["customer", "user", "客户", "用户"],
                "target_table": "dim_customers",
                "target_field": "customer_id"
            }
        }
    
    def _load_mapping_history(self) -> Dict[str, List[MappingResult]]:
        """加载映射历史（简化版，实际应从数据库加载）"""
        return {}
    
    def generate_mappings(self, source_columns: List[str], target_fields: List[str], 
                         data_domain: str = "products") -> List[MappingResult]:
        """
        生成字段映射建议
        
        Args:
            source_columns: 源文件列名列表
            target_fields: 目标数据库字段列表
            data_domain: 数据域（products, orders, traffic等）
            
        Returns:
            映射结果列表
        """
        mappings = []
        
        for source_col in source_columns:
            best_mapping = self._find_best_mapping(source_col, target_fields, data_domain)
            if best_mapping:
                mappings.append(best_mapping)
        
        # 按置信度排序
        mappings.sort(key=lambda x: x.confidence, reverse=True)
        
        return mappings
    
    def _find_best_mapping(self, source_col: str, target_fields: List[str], 
                          data_domain: str) -> Optional[MappingResult]:
        """为单个源列找到最佳映射"""
        
        # 1. 精确匹配
        exact_match = self._exact_match(source_col, target_fields)
        if exact_match:
            return exact_match
        
        # 2. 模糊匹配
        fuzzy_match = self._fuzzy_match(source_col, target_fields)
        if fuzzy_match and fuzzy_match.confidence > 0.8:
            return fuzzy_match
        
        # 3. 语义匹配
        semantic_match = self._semantic_match(source_col, target_fields)
        if semantic_match and semantic_match.confidence > 0.7:
            return semantic_match
        
        # 4. 历史学习
        learned_match = self._learned_match(source_col, data_domain)
        if learned_match and learned_match.confidence > 0.6:
            return learned_match
        
        # 5. 外键识别
        foreign_key_match = self._identify_foreign_key(source_col, target_fields)
        if foreign_key_match:
            return foreign_key_match
        
        return fuzzy_match  # 返回模糊匹配结果（即使置信度较低）
    
    def _exact_match(self, source_col: str, target_fields: List[str]) -> Optional[MappingResult]:
        """精确匹配"""
        source_normalized = self._normalize_column_name(source_col)
        
        for target_field in target_fields:
            target_normalized = self._normalize_column_name(target_field)
            if source_normalized == target_normalized:
                return MappingResult(
                    source_column=source_col,
                    target_field=target_field,
                    confidence=1.0,
                    mapping_type='exact'
                )
        
        return None
    
    def _fuzzy_match(self, source_col: str, target_fields: List[str]) -> Optional[MappingResult]:
        """模糊匹配"""
        source_normalized = self._normalize_column_name(source_col)
        best_match = None
        best_score = 0.0
        
        for target_field in target_fields:
            target_normalized = self._normalize_column_name(target_field)
            
            # 计算字符串相似度
            similarity = SequenceMatcher(None, source_normalized, target_normalized).ratio()
            
            # 计算子字符串匹配
            substring_score = 0.0
            if source_normalized in target_normalized:
                substring_score = len(source_normalized) / len(target_normalized)
            elif target_normalized in source_normalized:
                substring_score = len(target_normalized) / len(source_normalized)
            
            # 综合评分
            combined_score = max(similarity, substring_score)
            
            if combined_score > best_score:
                best_score = combined_score
                best_match = MappingResult(
                    source_column=source_col,
                    target_field=target_field,
                    confidence=combined_score,
                    mapping_type='fuzzy'
                )
        
        return best_match if best_score > 0.3 else None
    
    def _semantic_match(self, source_col: str, target_fields: List[str]) -> Optional[MappingResult]:
        """语义匹配"""
        source_normalized = self._normalize_column_name(source_col)
        best_match = None
        best_score = 0.0
        
        for target_field in target_fields:
            # 检查同义词匹配
            synonyms = self.synonym_dict.get(target_field, [])
            
            for synonym in synonyms:
                synonym_normalized = self._normalize_column_name(synonym)
                
                # 检查是否包含同义词
                if synonym_normalized in source_normalized or source_normalized in synonym_normalized:
                    score = 0.8  # 同义词匹配给较高分数
                    if score > best_score:
                        best_score = score
                        best_match = MappingResult(
                            source_column=source_col,
                            target_field=target_field,
                            confidence=score,
                            mapping_type='semantic'
                        )
        
        return best_match
    
    def _learned_match(self, source_col: str, data_domain: str) -> Optional[MappingResult]:
        """历史学习匹配"""
        # 简化版历史学习，实际应从数据库查询
        history_key = f"{data_domain}_{source_col}"
        
        if history_key in self.mapping_history:
            # 返回最常用的映射
            most_used = max(self.mapping_history[history_key], 
                          key=lambda x: x.confidence)
            return most_used
        
        return None
    
    def _identify_foreign_key(self, source_col: str, target_fields: List[str]) -> Optional[MappingResult]:
        """识别外键关系"""
        source_normalized = self._normalize_column_name(source_col)
        
        for fk_name, fk_info in self.foreign_key_patterns.items():
            patterns = fk_info["patterns"]
            
            for pattern in patterns:
                pattern_normalized = self._normalize_column_name(pattern)
                
                # 检查列名是否包含外键模式
                if (pattern_normalized in source_normalized or 
                    source_normalized in pattern_normalized):
                    
                    # 检查目标字段中是否有对应的外键字段
                    if fk_name in target_fields:
                        return MappingResult(
                            source_column=source_col,
                            target_field=fk_name,
                            confidence=0.9,
                            mapping_type='foreign_key',
                            foreign_key_info={
                                'target_table': fk_info['target_table'],
                                'target_field': fk_info['target_field'],
                                'validation_query': f"SELECT COUNT(*) FROM {fk_info['target_table']} WHERE {fk_info['target_field']} = ?"
                            }
                        )
        
        return None
    
    def _normalize_column_name(self, column_name: str) -> str:
        """标准化列名"""
        if not column_name:
            return ""
        
        # 转换为小写
        normalized = column_name.lower()
        
        # 移除特殊字符
        normalized = re.sub(r'[^\w\u4e00-\u9fff]', '', normalized)
        
        # 移除常见前缀/后缀
        prefixes = ['col_', 'field_', 'column_', '列_', '字段_']
        suffixes = ['_col', '_field', '_column', '_列', '_字段']
        
        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break
        
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]
                break
        
        return normalized
    
    def analyze_data_content(self, column_name: str, sample_data: List[Any]) -> Dict[str, Any]:
        """
        分析数据内容，推断字段类型和可能的映射
        
        Args:
            column_name: 列名
            sample_data: 样本数据
            
        Returns:
            分析结果字典
        """
        if not sample_data:
            return {'type': 'unknown', 'confidence': 0.0}
        
        # 数据类型分析
        data_type = self._infer_data_type(sample_data)
        
        # 内容模式分析
        patterns = self._analyze_patterns(sample_data)
        
        # 推断可能的映射
        possible_mappings = self._suggest_mappings_by_content(column_name, data_type, patterns)
        
        return {
            'type': data_type,
            'patterns': patterns,
            'possible_mappings': possible_mappings,
            'confidence': 0.7 if data_type != 'unknown' else 0.3
        }
    
    def _infer_data_type(self, sample_data: List[Any]) -> str:
        """推断数据类型"""
        if not sample_data:
            return 'unknown'
        
        # 检查数字类型
        numeric_count = 0
        for value in sample_data:
            try:
                float(str(value).replace(',', '').replace('$', ''))
                numeric_count += 1
            except (ValueError, TypeError):
                pass
        
        if numeric_count / len(sample_data) > 0.8:
            return 'numeric'
        
        # 检查日期类型
        date_count = 0
        for value in sample_data:
            if self._is_date_like(str(value)):
                date_count += 1
        
        if date_count / len(sample_data) > 0.8:
            return 'date'
        
        # 检查ID类型（数字字符串）
        id_count = 0
        for value in sample_data:
            if str(value).isdigit() and len(str(value)) > 3:
                id_count += 1
        
        if id_count / len(sample_data) > 0.8:
            return 'id'
        
        return 'text'
    
    def _is_date_like(self, value: str) -> bool:
        """检查是否像日期"""
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',
            r'\d{2}/\d{2}/\d{4}',
            r'\d{4}/\d{2}/\d{2}',
            r'\d{2}-\d{2}-\d{4}'
        ]
        
        for pattern in date_patterns:
            if re.match(pattern, value):
                return True
        
        return False
    
    def _analyze_patterns(self, sample_data: List[Any]) -> Dict[str, Any]:
        """分析数据模式"""
        if not sample_data:
            return {}
        
        patterns = {
            'unique_values': len(set(sample_data)),
            'total_values': len(sample_data),
            'null_count': sum(1 for x in sample_data if x is None or str(x).strip() == ''),
            'avg_length': sum(len(str(x)) for x in sample_data if x is not None) / len(sample_data)
        }
        
        return patterns
    
    def _suggest_mappings_by_content(self, column_name: str, data_type: str, 
                                   patterns: Dict[str, Any]) -> List[str]:
        """基于内容建议映射"""
        suggestions = []
        
        if data_type == 'id':
            if 'shop' in column_name.lower() or '店铺' in column_name:
                suggestions.append('shop_id')
            elif 'product' in column_name.lower() or '商品' in column_name:
                suggestions.append('product_id')
            elif 'order' in column_name.lower() or '订单' in column_name:
                suggestions.append('order_id')
            elif 'customer' in column_name.lower() or '客户' in column_name:
                suggestions.append('customer_id')
        
        elif data_type == 'numeric':
            if 'price' in column_name.lower() or '价格' in column_name:
                suggestions.append('product_price')
            elif 'amount' in column_name.lower() or '金额' in column_name:
                suggestions.append('order_amount')
            elif 'quantity' in column_name.lower() or '数量' in column_name:
                suggestions.append('quantity')
        
        elif data_type == 'date':
            if 'date' in column_name.lower() or '日期' in column_name:
                suggestions.append('order_date')
            elif 'time' in column_name.lower() or '时间' in column_name:
                suggestions.append('created_at')
        
        elif data_type == 'text':
            if 'name' in column_name.lower() or '名称' in column_name:
                suggestions.extend(['product_name', 'shop_name', 'customer_name'])
            elif 'description' in column_name.lower() or '描述' in column_name:
                suggestions.append('description')
            elif 'status' in column_name.lower() or '状态' in column_name:
                suggestions.append('status')
        
        return suggestions
    
    def save_mapping_history(self, mapping: MappingResult, user_id: str = None):
        """保存映射历史"""
        # 简化版，实际应保存到数据库
        key = f"{mapping.source_column}_{mapping.target_field}"
        if key not in self.mapping_history:
            self.mapping_history[key] = []
        
        self.mapping_history[key].append(mapping)
    
    def get_mapping_statistics(self) -> Dict[str, Any]:
        """获取映射统计信息"""
        total_mappings = len(self.mapping_history)
        mapping_types = {}
        
        for mappings in self.mapping_history.values():
            for mapping in mappings:
                mapping_type = mapping.mapping_type
                mapping_types[mapping_type] = mapping_types.get(mapping_type, 0) + 1
        
        return {
            'total_mappings': total_mappings,
            'mapping_types': mapping_types,
            'average_confidence': sum(
                mapping.confidence 
                for mappings in self.mapping_history.values() 
                for mapping in mappings
            ) / max(total_mappings, 1)
        }


# 全局实例
_mapping_engine = None

def get_mapping_engine() -> SmartMappingEngine:
    """获取映射引擎实例"""
    global _mapping_engine
    if _mapping_engine is None:
        _mapping_engine = SmartMappingEngine()
    return _mapping_engine
