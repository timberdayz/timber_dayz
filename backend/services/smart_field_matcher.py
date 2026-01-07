#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能字段匹配引擎 - v4.3.7
四层匹配策略：同义词 → 关键词相似 → 值模式检测 → 平台特定规则
"""

from typing import List, Dict, Optional, Tuple, Any
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from modules.core.logger import get_logger

logger = get_logger(__name__)


class SmartFieldMatcher:
    """智能字段匹配引擎"""
    
    def __init__(self, dictionary_fields: List[Dict], platform: str = None):
        """
        初始化匹配引擎
        
        Args:
            dictionary_fields: 辞典字段列表
            platform: 平台代码（用于平台特定规则）
        """
        self.dictionary = dictionary_fields
        self.platform = platform
        self._build_lookup_index()
    
    def _build_lookup_index(self):
        """构建查找索引（加速匹配）"""
        self.synonym_index = {}  # 同义词 → field_code
        self.keyword_index = {}  # 关键词 → field_code（带权重）
        
        for field in self.dictionary:
            field_code = field['field_code']
            
            # 索引同义词
            synonyms = field.get('synonyms', [])
            for syn in synonyms:
                syn_lower = syn.lower()
                if syn_lower not in self.synonym_index:
                    self.synonym_index[syn_lower] = []
                self.synonym_index[syn_lower].append(field_code)
            
            # 索引平台特定同义词
            if self.platform:
                platform_syns = field.get('platform_synonyms', {}).get(self.platform, [])
                for syn in platform_syns:
                    syn_lower = syn.lower()
                    if syn_lower not in self.synonym_index:
                        self.synonym_index[syn_lower] = []
                    # 平台特定同义词权重更高（插入到列表前面）
                    self.synonym_index[syn_lower].insert(0, field_code)
            
            # 索引关键词（从中文名和同义词提取）
            cn_name = field.get('cn_name', '')
            all_text = [cn_name] + synonyms
            for text in all_text:
                # 提取中文关键词（2-4字）
                keywords = self._extract_keywords(text)
                for kw in keywords:
                    if kw not in self.keyword_index:
                        self.keyword_index[kw] = {}
                    if field_code not in self.keyword_index[kw]:
                        self.keyword_index[kw][field_code] = 0
                    self.keyword_index[kw][field_code] += 1
        
        logger.info(f"[Matcher] 索引构建完成: {len(self.synonym_index)}个同义词, {len(self.keyword_index)}个关键词")
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取中文关键词"""
        if not text:
            return []
        
        # 简化版：提取2-4个连续汉字
        keywords = []
        
        # 匹配2-4个汉字
        for length in [4, 3, 2]:
            pattern = f'[\\u4e00-\\u9fff]{{{length}}}'
            matches = re.findall(pattern, text)
            keywords.extend(matches)
        
        # 去重
        return list(set(keywords))
    
    def match(
        self,
        original_column: str,
        sample_values: List[Any] = None
    ) -> Tuple[str, float, str, str]:
        """
        匹配单个字段
        
        Args:
            original_column: 原始列名
            sample_values: 样例值（可选，用于值模式检测）
        
        Returns:
            (standard_field, confidence, method, reason)
        """
        # 清洗列名
        cleaned_column = self._clean_column_name(original_column)
        
        # 策略1：精确同义词匹配（置信度0.95）
        result = self._match_by_synonym(cleaned_column)
        if result:
            return result
        
        # 策略2：关键词相似度（置信度0.70-0.85）
        result = self._match_by_keywords(cleaned_column)
        if result:
            return result
        
        # 策略3：值模式检测（置信度0.80-0.90）
        if sample_values:
            result = self._match_by_value_pattern(cleaned_column, sample_values)
            if result:
                return result
        
        # 未匹配
        return ("未映射", 0.0, "no_match", "未找到匹配的标准字段")
    
    def _clean_column_name(self, column: str) -> str:
        """清洗列名（去括号/单位/空格）"""
        # 去除括号内容
        column = re.sub(r'\([^)]*\)', '', column)
        column = re.sub(r'\[[^\]]*\]', '', column)
        
        # 去除空格和特殊字符
        column = column.strip()
        
        return column
    
    def _match_by_synonym(self, column: str) -> Optional[Tuple[str, float, str, str]]:
        """策略1：同义词精确匹配"""
        column_lower = column.lower()
        
        if column_lower in self.synonym_index:
            matched_fields = self.synonym_index[column_lower]
            if matched_fields:
                field_code = matched_fields[0]  # 取第一个（平台特定优先）
                
                # 检查是否为平台特定匹配
                confidence = 0.98 if len(matched_fields) == 1 else 0.95
                
                return (
                    field_code,
                    confidence,
                    "synonym_exact_match",
                    f"精确匹配同义词: {column}"
                )
        
        return None
    
    def _match_by_keywords(self, column: str) -> Optional[Tuple[str, float, str, str]]:
        """策略2：关键词相似度匹配（v4.6.1增强 - 优先精确匹配）"""
        keywords = self._extract_keywords(column)
        
        if not keywords:
            return None
        
        # 统计每个字段的关键词命中数
        field_scores = {}
        matched_keywords = {}
        field_similarity = {}  # ⭐ v4.6.1新增：字段名相似度
        
        for kw in keywords:
            if kw in self.keyword_index:
                for field_code, count in self.keyword_index[kw].items():
                    if field_code not in field_scores:
                        field_scores[field_code] = 0
                        matched_keywords[field_code] = []
                        # ⭐ 计算字段名相似度
                        field_dict = next((f for f in self.dictionary if f.get('field_code') == field_code), None)
                        if field_dict:
                            cn_name = field_dict.get('cn_name', '')
                            # 计算相似度（字段名包含原始列名的程度）
                            similarity = self._calculate_name_similarity(column, cn_name)
                            field_similarity[field_code] = similarity
                    field_scores[field_code] += count
                    matched_keywords[field_code].append(kw)
        
        if not field_scores:
            return None
        
        # ⭐ v4.6.1增强：综合考虑得分和相似度
        # 优先选择：1) 得分高 + 2) 相似度高
        def combined_score(field_code):
            score = field_scores[field_code]
            similarity = field_similarity.get(field_code, 0.0)
            # 相似度权重更高（0.7），得分权重较低（0.3）
            return score * 0.3 + similarity * 0.7
        
        # 找到综合得分最高的字段
        best_field = max(field_scores.items(), key=lambda x: combined_score(x[0]))
        field_code = best_field[0]
        score = best_field[1]
        similarity = field_similarity.get(field_code, 0.0)
        
        # 计算置信度（基于匹配关键词数量和相似度）
        keywords_matched = len(matched_keywords[field_code])
        total_keywords = len(keywords)
        
        # ⭐ v4.6.1增强：相似度高时提升置信度
        if similarity >= 0.8:  # 高度相似
            base_confidence = 0.90
        elif similarity >= 0.6:  # 中等相似
            base_confidence = 0.80
        elif keywords_matched >= total_keywords:
            base_confidence = 0.85
        elif keywords_matched >= total_keywords * 0.6:
            base_confidence = 0.75
        else:
            base_confidence = 0.65
        
        # 置信度阈值：>=0.65才返回
        if base_confidence < 0.65:
            return None
        
        return (
            field_code,
            base_confidence,
            "keyword_similarity",
            f"关键词匹配: {', '.join(matched_keywords[field_code])} (相似度: {similarity:.2f})"
        )
    
    def _calculate_name_similarity(self, original: str, target: str) -> float:
        """
        计算字段名相似度（v4.6.1新增）
        
        Args:
            original: 原始字段名
            target: 目标字段名（CN Name）
            
        Returns:
            相似度分数 (0.0 - 1.0)
        """
        if not original or not target:
            return 0.0
        
        original_lower = original.lower()
        target_lower = target.lower()
        
        # 方法1：完全包含（最高分）
        if original_lower in target_lower or target_lower in original_lower:
            return 0.95
        
        # 方法2：字符重叠度
        original_chars = set(original_lower)
        target_chars = set(target_lower)
        
        if not original_chars or not target_chars:
            return 0.0
        
        intersection = original_chars & target_chars
        union = original_chars | target_chars
        
        jaccard = len(intersection) / len(union) if union else 0.0
        
        return jaccard
    
    def _match_by_value_pattern(
        self,
        column: str,
        sample_values: List[Any]
    ) -> Optional[Tuple[str, float, str, str]]:
        """策略3：值模式检测"""
        # 过滤None值
        valid_values = [v for v in sample_values if v is not None and str(v).strip()]
        
        if len(valid_values) < 3:
            return None  # 样本太少
        
        # 检测日期模式
        date_pattern = self._detect_date_pattern(valid_values)
        if date_pattern:
            return date_pattern
        
        # 检测金额+币种模式
        currency_pattern = self._detect_currency_pattern(valid_values, column)
        if currency_pattern:
            return currency_pattern
        
        # 检测整数数量模式
        quantity_pattern = self._detect_quantity_pattern(valid_values, column)
        if quantity_pattern:
            return quantity_pattern
        
        # 检测比率模式
        ratio_pattern = self._detect_ratio_pattern(valid_values, column)
        if ratio_pattern:
            return ratio_pattern
        
        return None
    
    def _detect_date_pattern(self, values: List[Any]) -> Optional[Tuple[str, float, str, str]]:
        """检测日期模式"""
        date_count = 0
        date_formats = []
        
        for val in values[:20]:  # 检测前20个
            val_str = str(val).strip()
            
            # 常见日期格式
            date_patterns = [
                r'\d{4}-\d{2}-\d{2}',  # 2024-09-25
                r'\d{2}/\d{2}/\d{4}',  # 25/09/2024
                r'\d{4}/\d{2}/\d{2}',  # 2024/09/25
                r'\d{2}-\d{2}-\d{4}',  # 25-09-2024
            ]
            
            for pattern in date_patterns:
                if re.match(pattern, val_str):
                    date_count += 1
                    date_formats.append(pattern)
                    break
        
        # 如果≥70%的值是日期格式
        if date_count / len(values[:20]) >= 0.7:
            # 查找日期类型的标准字段
            date_fields = [f for f in self.dictionary if f.get('data_type') in ['date', 'datetime']]
            
            if date_fields:
                # 优先选择metric_date或order_date
                for field in date_fields:
                    if 'date' in field['field_code']:
                        return (
                            field['field_code'],
                            0.85,
                            "value_pattern_date",
                            f"值模式检测: 日期格式（{date_count}/{len(values[:20])}样本）"
                        )
        
        return None
    
    def _detect_currency_pattern(
        self,
        values: List[Any],
        column: str
    ) -> Optional[Tuple[str, float, str, str]]:
        """检测金额+币种模式"""
        currency_count = 0
        detected_currency = None
        
        for val in values[:20]:
            val_str = str(val).strip()
            
            # 检测币种符号或代码
            currency_patterns = {
                r'[R$R\$]\s*[\d,]+\.?\d*': 'BRL',
                r'USD?\s*[\d,]+\.?\d*': 'USD',
                r'CNY?\s*[\d,]+\.?\d*': 'CNY',
                r'SGD?\s*[\d,]+\.?\d*': 'SGD',
            }
            
            for pattern, currency in currency_patterns.items():
                if re.search(pattern, val_str):
                    currency_count += 1
                    detected_currency = currency
                    break
            
            # 检测纯数字金额（带小数点）
            if re.match(r'^\d+\.\d{2}$', val_str):
                currency_count += 1
        
        # 如果≥50%的值是金额格式，且列名包含"金额"/"价格"等关键词
        if currency_count / len(values[:20]) >= 0.5:
            amount_keywords = ['金额', '价格', '费', '优惠', 'amount', 'price', 'fee', 'discount']
            
            if any(kw in column.lower() for kw in amount_keywords):
                # 查找金额类型的标准字段
                amount_fields = [f for f in self.dictionary if f.get('data_type') == 'currency']
                
                if amount_fields:
                    # 根据关键词匹配具体金额字段
                    if '运费' in column or 'shipping' in column.lower():
                        target = 'shipping_fee'
                    elif '优惠' in column or 'discount' in column.lower():
                        if '平台' in column:
                            target = 'platform_discount'
                        else:
                            target = 'seller_discount'
                    else:
                        target = 'total_amount'  # 默认为总金额
                    
                    # 验证target在辞典中
                    if any(f['field_code'] == target for f in amount_fields):
                        return (
                            target,
                            0.82,
                            "value_pattern_currency",
                            f"值模式检测: 金额格式（{currency_count}/{len(values[:20])}样本）"
                        )
        
        return None
    
    def _detect_quantity_pattern(
        self,
        values: List[Any],
        column: str
    ) -> Optional[Tuple[str, float, str, str]]:
        """检测整数数量模式"""
        integer_count = 0
        
        for val in values[:20]:
            val_str = str(val).strip()
            
            # 检测纯整数（可能有逗号分隔符）
            if re.match(r'^\d{1,3}(,\d{3})*$', val_str) or re.match(r'^\d+$', val_str):
                integer_count += 1
        
        # 如果≥80%的值是整数
        if integer_count / len(values[:20]) >= 0.8:
            quantity_keywords = ['数量', '库存', '访客', '浏览', 'quantity', 'stock', 'visitors', 'views']
            
            if any(kw in column.lower() for kw in quantity_keywords):
                # 根据关键词匹配具体数量字段
                if '库存' in column or 'stock' in column.lower():
                    target = 'stock'
                elif '访客' in column or 'visitor' in column.lower() or 'uv' in column.lower():
                    target = 'visitors'
                elif '浏览' in column or 'view' in column.lower() or 'pv' in column.lower():
                    target = 'page_views'
                elif '数量' in column or 'quantity' in column.lower() or 'qty' in column.lower():
                    target = 'quantity'
                else:
                    return None
                
                # 验证target在辞典中
                if any(f['field_code'] == target for f in self.dictionary):
                    return (
                        target,
                        0.80,
                        "value_pattern_quantity",
                        f"值模式检测: 整数数量（{integer_count}/{len(values[:20])}样本）"
                    )
        
        return None
    
    def _detect_ratio_pattern(
        self,
        values: List[Any],
        column: str
    ) -> Optional[Tuple[str, float, str, str]]:
        """检测比率模式"""
        ratio_count = 0
        
        for val in values[:20]:
            val_str = str(val).strip()
            
            # 检测百分比（如：5%，0.05）
            if re.match(r'^\d+(\.\d+)?%$', val_str):
                ratio_count += 1
            elif re.match(r'^0\.\d+$', val_str):
                try:
                    num = float(val_str)
                    if 0 <= num <= 1:
                        ratio_count += 1
                except ValueError:
                    pass
        
        # 如果≥60%的值是比率格式
        if ratio_count / len(values[:20]) >= 0.6:
            ratio_keywords = ['率', '比例', 'rate', 'ratio', 'cvr']
            
            if any(kw in column.lower() for kw in ratio_keywords):
                # 查找比率类型的标准字段
                ratio_fields = [f for f in self.dictionary if f.get('data_type') == 'ratio']
                
                if ratio_fields:
                    # 默认匹配第一个比率字段（通常是conversion_rate）
                    target = ratio_fields[0]['field_code']
                    
                    return (
                        target,
                        0.78,
                        "value_pattern_ratio",
                        f"值模式检测: 比率格式（{ratio_count}/{len(values[:20])}样本）"
                    )
        
        return None
    
    def batch_match(
        self,
        columns: List[str],
        sample_data: List[Dict] = None
    ) -> Dict[str, Dict]:
        """
        批量匹配字段
        
        Args:
            columns: 原始列名列表
            sample_data: 样例数据（可选）
        
        Returns:
            {
                "原始列名": {
                    "standard_field": "标准字段代码",
                    "confidence": 0.95,
                    "method": "synonym_exact_match",
                    "reason": "精确匹配同义词: 订单号"
                },
                ...
            }
        """
        results = {}
        
        for col in columns:
            # 提取样例值
            sample_values = None
            if sample_data:
                sample_values = [row.get(col) for row in sample_data if row.get(col) is not None]
            
            # 匹配
            standard_field, confidence, method, reason = self.match(col, sample_values)
            
            results[col] = {
                "standard_field": standard_field,
                "confidence": confidence,
                "method": method,
                "reason": reason
            }
        
        # 统计
        high_conf = sum(1 for r in results.values() if r['confidence'] >= 0.90)
        medium_conf = sum(1 for r in results.values() if 0.70 <= r['confidence'] < 0.90)
        low_conf = sum(1 for r in results.values() if r['confidence'] < 0.70)
        
        logger.info(f"[Matcher] 批量匹配完成: {len(columns)}列 → 高{high_conf}/中{medium_conf}/低{low_conf}")
        
        return results


def get_smart_matcher(dictionary_fields: List[Dict], platform: str = None) -> SmartFieldMatcher:
    """获取智能匹配器实例"""
    return SmartFieldMatcher(dictionary_fields, platform)

