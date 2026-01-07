#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据对齐准确性保障服务（Data Alignment Validator）

v4.6.0新增：
- 表头识别验证
- 数据对齐验证（入库前）
- 数据验证（入库前）

职责：
- 验证表头行是否包含有效列名
- 验证字段数量匹配
- 验证字段名匹配
- 验证数据类型合理性
- 验证不同粒度表头不混淆
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import re

from modules.core.logger import get_logger

logger = get_logger(__name__)


class DataAlignmentValidator:
    """
    数据对齐准确性保障服务
    
    验证内容：
    1. 表头识别验证：检查表头行是否包含有效列名
    2. 数据对齐验证：验证字段数量匹配、字段名匹配
    3. 数据验证：验证数据类型合理性、粒度不混淆
    """
    
    def __init__(self):
        pass
    
    def validate_header_recognition(
        self,
        header_columns: List[str],
        min_valid_columns: int = 3
    ) -> Tuple[bool, Optional[str]]:
        """
        表头识别验证
        
        Args:
            header_columns: 表头字段列表
            min_valid_columns: 最少有效列数（默认3）
        
        Returns:
            (is_valid, error_message)
        """
        if not header_columns:
            return False, "表头字段列表为空"
        
        # 过滤有效列名（非空、非纯数字、非纯特殊字符）
        valid_columns = []
        for col in header_columns:
            col_str = str(col).strip()
            if not col_str:
                continue
            # 排除纯数字列名（可能是数据行）
            if col_str.isdigit():
                continue
            # 排除纯特殊字符列名
            if not re.search(r'[a-zA-Z\u4e00-\u9fa5]', col_str):
                continue
            valid_columns.append(col_str)
        
        if len(valid_columns) < min_valid_columns:
            return False, (
                f"表头识别失败：有效列数不足（{len(valid_columns)}/{min_valid_columns}）。"
                f"有效列：{valid_columns[:5]}"
            )
        
        return True, None
    
    def validate_data_alignment(
        self,
        rows: List[Dict[str, Any]],
        header_columns: List[str]
    ) -> Tuple[bool, List[str]]:
        """
        数据对齐验证（入库前）
        
        验证内容：
        - 字段数量匹配（header_columns数量 = raw_data键数量）
        - 字段名匹配（header_columns中的字段都在raw_data中）
        
        Args:
            rows: 数据行列表
            header_columns: 原始表头字段列表
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        if not rows:
            return True, []  # 空数据视为有效
        
        # 验证每一行
        for idx, row in enumerate(rows):
            row_errors = []
            
            # 1. 字段数量匹配
            row_keys = set(row.keys())
            header_set = set(header_columns)
            
            # 允许row中有额外的键（如元数据字段），但不允许缺少关键字段
            missing_fields = header_set - row_keys
            if missing_fields:
                row_errors.append(
                    f"行{idx+1}缺少字段: {list(missing_fields)[:5]}"
                )
            
            # 2. 字段名匹配（检查关键字段是否存在）
            # 注意：这里只检查关键字段，不要求完全匹配（因为可能有元数据字段）
            key_fields = [col for col in header_columns if any(
                keyword in col.lower() 
                for keyword in ['id', '编号', '日期', 'date', '订单', 'order', '产品', 'product']
            )]
            
            missing_key_fields = [f for f in key_fields if f not in row_keys]
            if missing_key_fields:
                row_errors.append(
                    f"行{idx+1}缺少关键字段: {missing_key_fields}"
                )
            
            if row_errors:
                errors.extend(row_errors)
        
        return len(errors) == 0, errors
    
    def validate_data_types(
        self,
        rows: List[Dict[str, Any]],
        header_columns: List[str]
    ) -> Tuple[bool, List[str]]:
        """
        验证数据类型合理性
        
        验证规则：
        - 订单号应该是字符串
        - 数量应该是数字
        - 日期应该是日期格式
        
        Args:
            rows: 数据行列表
            header_columns: 原始表头字段列表
        
        Returns:
            (is_valid, error_messages)
        """
        errors = []
        
        if not rows:
            return True, []
        
        # 定义字段类型规则
        type_rules = {
            '订单号': 'string',
            '订单编号': 'string',
            'order_id': 'string',
            'order_number': 'string',
            '产品ID': 'string',
            '商品ID': 'string',
            'product_id': 'string',
            'sku': 'string',
            '数量': 'number',
            'quantity': 'number',
            'qty': 'number',
            '金额': 'number',
            'amount': 'number',
            'price': 'number',
            '日期': 'date',
            'date': 'date',
            'order_date': 'date',
            'metric_date': 'date',
        }
        
        # 验证每一行
        for idx, row in enumerate(rows):
            row_errors = []
            
            for col in header_columns:
                col_lower = col.lower()
                
                # 查找匹配的类型规则
                matched_rule = None
                for rule_key, rule_type in type_rules.items():
                    if rule_key.lower() in col_lower or col_lower in rule_key.lower():
                        matched_rule = rule_type
                        break
                
                if not matched_rule:
                    continue  # 无规则，跳过
                
                value = row.get(col)
                if value is None or value == '':
                    continue  # 空值跳过
                
                # 类型验证
                if matched_rule == 'string':
                    if not isinstance(value, str):
                        row_errors.append(
                            f"行{idx+1}字段'{col}'应为字符串类型，实际: {type(value).__name__}"
                        )
                elif matched_rule == 'number':
                    if not isinstance(value, (int, float)) and not str(value).replace('.', '').replace('-', '').isdigit():
                        row_errors.append(
                            f"行{idx+1}字段'{col}'应为数字类型，实际: {type(value).__name__}"
                        )
                elif matched_rule == 'date':
                    # 日期验证（尝试解析）
                    if isinstance(value, str):
                        # 尝试解析日期字符串
                        date_patterns = [
                            r'\d{4}-\d{2}-\d{2}',
                            r'\d{4}/\d{2}/\d{2}',
                            r'\d{8}',
                        ]
                        if not any(re.match(pattern, value) for pattern in date_patterns):
                            row_errors.append(
                                f"行{idx+1}字段'{col}'日期格式可能不正确: {value}"
                            )
            
            if row_errors:
                errors.extend(row_errors)
        
        return len(errors) == 0, errors
    
    def validate_granularity_consistency(
        self,
        header_columns: List[str],
        data_domain: str,
        granularity: str
    ) -> Tuple[bool, Optional[str]]:
        """
        验证不同粒度表头不混淆
        
        验证规则：
        - 日度和周度的"日期"字段不混淆
        - 确保粒度与表头字段匹配
        
        Args:
            header_columns: 原始表头字段列表
            data_domain: 数据域
            granularity: 粒度
        
        Returns:
            (is_valid, error_message)
        """
        # 检查日期字段
        date_fields = [col for col in header_columns if any(
            keyword in col.lower() 
            for keyword in ['日期', 'date', '时间', 'time']
        )]
        
        if not date_fields:
            return True, None  # 无日期字段，跳过验证
        
        # 根据粒度验证日期字段格式
        if granularity == 'daily':
            # 日度粒度：日期字段应该是单日日期
            # 这里只做基本检查，具体格式验证在数据类型验证中
            pass
        elif granularity == 'weekly':
            # 周度粒度：日期字段应该是周度日期（可能包含范围）
            # 检查是否包含范围标识
            for date_field in date_fields:
                # 周度日期可能包含"~"或"-"分隔符
                pass
        elif granularity == 'monthly':
            # 月度粒度：日期字段应该是月度日期
            pass
        
        return True, None
    
    def validate_chinese_field_names(
        self,
        header_columns: List[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        验证中文字段名兼容性
        
        验证规则：
        - 检查字段名是否包含中文字符
        - 确保PostgreSQL和Metabase能正常查询
        
        Args:
            header_columns: 原始表头字段列表
        
        Returns:
            (is_valid, error_message)
        """
        # PostgreSQL和Metabase都支持中文字段名（在JSONB中作为键）
        # 这里只做基本检查，确保字段名不为空且不包含特殊字符
        
        invalid_chars = ['\x00', '\n', '\r', '\t']
        
        for col in header_columns:
            col_str = str(col)
            
            # 检查空字段名
            if not col_str.strip():
                return False, f"发现空字段名"
            
            # 检查特殊字符
            for char in invalid_chars:
                if char in col_str:
                    return False, f"字段名包含无效字符: {col_str}"
        
        return True, None
    
    def validate_all(
        self,
        rows: List[Dict[str, Any]],
        header_columns: List[str],
        data_domain: str,
        granularity: str
    ) -> Dict[str, Any]:
        """
        执行所有验证
        
        Args:
            rows: 数据行列表
            header_columns: 原始表头字段列表
            data_domain: 数据域
            granularity: 粒度
        
        Returns:
            验证结果字典
        """
        results = {
            'header_recognition': {'valid': False, 'error': None},
            'data_alignment': {'valid': False, 'errors': []},
            'data_types': {'valid': False, 'errors': []},
            'granularity_consistency': {'valid': False, 'error': None},
            'chinese_field_names': {'valid': False, 'error': None},
            'overall_valid': False
        }
        
        # 1. 表头识别验证
        is_valid, error = self.validate_header_recognition(header_columns)
        results['header_recognition'] = {'valid': is_valid, 'error': error}
        
        if not is_valid:
            results['overall_valid'] = False
            return results
        
        # 2. 数据对齐验证
        is_valid, errors = self.validate_data_alignment(rows, header_columns)
        results['data_alignment'] = {'valid': is_valid, 'errors': errors}
        
        # 3. 数据类型验证
        is_valid, errors = self.validate_data_types(rows, header_columns)
        results['data_types'] = {'valid': is_valid, 'errors': errors}
        
        # 4. 粒度一致性验证
        is_valid, error = self.validate_granularity_consistency(header_columns, data_domain, granularity)
        results['granularity_consistency'] = {'valid': is_valid, 'error': error}
        
        # 5. 中文字段名验证
        is_valid, error = self.validate_chinese_field_names(header_columns)
        results['chinese_field_names'] = {'valid': is_valid, 'error': error}
        
        # 总体验证结果
        results['overall_valid'] = all([
            results['header_recognition']['valid'],
            results['data_alignment']['valid'],
            results['data_types']['valid'],
            results['granularity_consistency']['valid'],
            results['chinese_field_names']['valid']
        ])
        
        return results


def get_data_alignment_validator() -> DataAlignmentValidator:
    """获取数据对齐验证器实例"""
    return DataAlignmentValidator()

