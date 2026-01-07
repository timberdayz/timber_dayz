#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据验证引擎

提供多层次的数据验证功能：
1. 数据类型验证
2. 必填字段验证
3. 外键存在性验证
4. 业务规则验证
5. 数据一致性验证
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, date
import pandas as pd
from sqlalchemy import create_engine, text

@dataclass
class ValidationError:
    """验证错误"""
    row_index: int
    column_name: str
    error_type: str
    error_message: str
    current_value: Any
    expected_value: Optional[Any] = None
    suggestion: Optional[str] = None

@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]
    statistics: Dict[str, Any]

class DataValidator:
    """数据验证器"""
    
    def __init__(self, database_engine=None):
        """初始化验证器"""
        self.database_engine = database_engine
        self.validation_rules = self._load_default_rules()
    
    def _load_default_rules(self) -> Dict[str, Dict[str, Any]]:
        """加载默认验证规则"""
        return {
            # 数据类型规则
            'data_types': {
                'product_id': {'type': 'string', 'pattern': r'^[A-Za-z0-9_-]+$'},
                'shop_id': {'type': 'string', 'pattern': r'^[A-Za-z0-9_-]+$'},
                'order_id': {'type': 'string', 'pattern': r'^[A-Za-z0-9_-]+$'},
                'customer_id': {'type': 'string', 'pattern': r'^[A-Za-z0-9_-]+$'},
                'product_price': {'type': 'numeric', 'min': 0, 'max': 1000000},
                'order_amount': {'type': 'numeric', 'min': 0, 'max': 10000000},
                'quantity': {'type': 'integer', 'min': 0, 'max': 10000},
                'order_date': {'type': 'date'},
                'created_at': {'type': 'datetime'},
                'status': {'type': 'enum', 'values': ['pending', 'completed', 'cancelled', 'failed']},
                'currency': {'type': 'enum', 'values': ['USD', 'CNY', 'SGD', 'MYR', 'THB', 'PHP', 'VND']}
            },
            
            # 必填字段规则
            'required_fields': {
                'products': ['product_id', 'product_name', 'shop_id'],
                'orders': ['order_id', 'order_amount', 'order_date', 'shop_id'],
                'traffic': ['date', 'shop_id', 'visits'],
                'service': ['date', 'shop_id', 'service_type']
            },
            
            # 外键规则
            'foreign_keys': {
                'shop_id': {'table': 'dim_shops', 'column': 'shop_id'},
                'product_id': {'table': 'dim_products', 'column': 'product_id'},
                'order_id': {'table': 'fact_orders', 'column': 'order_id'},
                'customer_id': {'table': 'dim_customers', 'column': 'customer_id'}
            },
            
            # 业务规则
            'business_rules': {
                'order_amount_positive': {
                    'condition': 'order_amount > 0',
                    'message': '订单金额必须大于0'
                },
                'quantity_positive': {
                    'condition': 'quantity > 0',
                    'message': '数量必须大于0'
                },
                'order_date_not_future': {
                    'condition': 'order_date <= current_date',
                    'message': '订单日期不能是未来日期'
                }
            }
        }
    
    def validate_dataframe(self, df: pd.DataFrame, mappings: List[Dict[str, Any]], 
                          data_domain: str = 'products') -> ValidationResult:
        """
        验证DataFrame数据
        
        Args:
            df: 要验证的数据框
            mappings: 字段映射配置
            data_domain: 数据域
            
        Returns:
            验证结果
        """
        errors = []
        warnings = []
        
        # 1. 数据类型验证
        type_errors = self._validate_data_types(df, mappings)
        errors.extend(type_errors)
        
        # 2. 必填字段验证
        required_errors = self._validate_required_fields(df, mappings, data_domain)
        errors.extend(required_errors)
        
        # 3. 外键验证
        fk_errors = self._validate_foreign_keys(df, mappings)
        errors.extend(fk_errors)
        
        # 4. 业务规则验证
        business_errors = self._validate_business_rules(df, mappings)
        errors.extend(business_errors)
        
        # 5. 数据一致性验证
        consistency_warnings = self._validate_consistency(df, mappings)
        warnings.extend(consistency_warnings)
        
        # 生成统计信息
        statistics = self._generate_statistics(df, errors, warnings)
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            statistics=statistics
        )
    
    def _validate_data_types(self, df: pd.DataFrame, mappings: List[Dict[str, Any]]) -> List[ValidationError]:
        """验证数据类型"""
        errors = []
        
        for mapping in mappings:
            source_col = mapping.get('source_column')
            target_field = mapping.get('target_field')
            
            if source_col not in df.columns:
                continue
            
            # 获取验证规则
            rules = self.validation_rules['data_types'].get(target_field)
            if not rules:
                continue
            
            column_data = df[source_col]
            
            for idx, value in column_data.items():
                error = self._validate_single_value(value, rules, target_field)
                if error:
                    errors.append(ValidationError(
                        row_index=idx,
                        column_name=source_col,
                        error_type='data_type',
                        error_message=error,
                        current_value=value,
                        expected_value=rules.get('type')
                    ))
        
        return errors
    
    def _validate_single_value(self, value: Any, rules: Dict[str, Any], field_name: str) -> Optional[str]:
        """验证单个值"""
        if value is None or pd.isna(value):
            return None
        
        value_str = str(value).strip()
        if not value_str:
            return None
        
        # 类型验证
        expected_type = rules.get('type')
        if expected_type == 'numeric':
            try:
                float(value_str.replace(',', '').replace('$', ''))
            except ValueError:
                return f"值 '{value}' 不是有效的数字"
        
        elif expected_type == 'integer':
            try:
                int(float(value_str))
            except ValueError:
                return f"值 '{value}' 不是有效的整数"
        
        elif expected_type == 'date':
            if not self._is_valid_date(value_str):
                return f"值 '{value}' 不是有效的日期格式"
        
        elif expected_type == 'datetime':
            if not self._is_valid_datetime(value_str):
                return f"值 '{value}' 不是有效的日期时间格式"
        
        # 模式验证
        pattern = rules.get('pattern')
        if pattern and not re.match(pattern, value_str):
            return f"值 '{value}' 不符合预期格式"
        
        # 枚举值验证
        enum_values = rules.get('values')
        if enum_values and value_str not in enum_values:
            return f"值 '{value}' 不在允许的值列表中: {enum_values}"
        
        # 范围验证
        if expected_type in ['numeric', 'integer']:
            try:
                num_value = float(value_str.replace(',', '').replace('$', ''))
                min_val = rules.get('min')
                max_val = rules.get('max')
                
                if min_val is not None and num_value < min_val:
                    return f"值 '{value}' 小于最小值 {min_val}"
                
                if max_val is not None and num_value > max_val:
                    return f"值 '{value}' 大于最大值 {max_val}"
            except ValueError:
                pass
        
        return None
    
    def _validate_required_fields(self, df: pd.DataFrame, mappings: List[Dict[str, Any]], 
                                 data_domain: str) -> List[ValidationError]:
        """验证必填字段"""
        errors = []
        
        # 获取必填字段列表
        required_fields = self.validation_rules['required_fields'].get(data_domain, [])
        
        # 根据映射找到对应的源列
        mapping_dict = {m['target_field']: m['source_column'] for m in mappings}
        
        for required_field in required_fields:
            source_col = mapping_dict.get(required_field)
            if not source_col or source_col not in df.columns:
                continue
            
            column_data = df[source_col]
            null_indices = column_data.isnull() | (column_data.astype(str).str.strip() == '')
            
            for idx in null_indices[null_indices].index:
                errors.append(ValidationError(
                    row_index=idx,
                    column_name=source_col,
                    error_type='required_field',
                    error_message=f"必填字段 '{required_field}' 不能为空",
                    current_value=column_data.iloc[idx]
                ))
        
        return errors
    
    def _validate_foreign_keys(self, df: pd.DataFrame, mappings: List[Dict[str, Any]]) -> List[ValidationError]:
        """验证外键"""
        errors = []
        
        if not self.database_engine:
            return errors  # 没有数据库连接时跳过外键验证
        
        fk_rules = self.validation_rules['foreign_keys']
        
        for mapping in mappings:
            source_col = mapping.get('source_column')
            target_field = mapping.get('target_field')
            
            if source_col not in df.columns:
                continue
            
            # 检查是否是外键字段
            fk_info = fk_rules.get(target_field)
            if not fk_info:
                continue
            
            # 获取唯一值
            unique_values = df[source_col].dropna().unique()
            if len(unique_values) == 0:
                continue
            
            # 查询数据库验证外键存在性
            invalid_values = self._check_foreign_key_existence(
                unique_values, fk_info['table'], fk_info['column']
            )
            
            # 为每个无效值创建错误
            for invalid_value in invalid_values:
                invalid_indices = df[df[source_col] == invalid_value].index
                for idx in invalid_indices:
                    errors.append(ValidationError(
                        row_index=idx,
                        column_name=source_col,
                        error_type='foreign_key',
                        error_message=f"外键值 '{invalid_value}' 在表 {fk_info['table']} 中不存在",
                        current_value=invalid_value,
                        suggestion=f"请检查 {fk_info['table']} 表中是否存在该记录"
                    ))
        
        return errors
    
    def _check_foreign_key_existence(self, values: List[Any], table: str, column: str) -> List[Any]:
        """检查外键值在数据库中的存在性"""
        if not self.database_engine:
            return []
        
        try:
            with self.database_engine.connect() as conn:
                # 构建查询语句
                placeholders = ','.join(['?' for _ in values])
                query = f"SELECT {column} FROM {table} WHERE {column} IN ({placeholders})"
                
                result = conn.execute(text(query), list(values))
                existing_values = [row[0] for row in result]
                
                # 返回不存在的值
                return [v for v in values if v not in existing_values]
        
        except Exception as e:
            print(f"外键验证查询失败: {e}")
            return []  # 查询失败时返回空列表，避免阻塞验证
    
    def _validate_business_rules(self, df: pd.DataFrame, mappings: List[Dict[str, Any]]) -> List[ValidationError]:
        """验证业务规则"""
        errors = []
        
        business_rules = self.validation_rules['business_rules']
        
        for rule_name, rule_config in business_rules.items():
            condition = rule_config['condition']
            message = rule_config['message']
            
            # 简化的条件解析（实际应该使用更复杂的表达式解析器）
            if condition == 'order_amount > 0':
                # 查找订单金额字段
                amount_col = None
                for mapping in mappings:
                    if mapping.get('target_field') == 'order_amount':
                        amount_col = mapping.get('source_column')
                        break
                
                if amount_col and amount_col in df.columns:
                    invalid_indices = df[df[amount_col] <= 0].index
                    for idx in invalid_indices:
                        errors.append(ValidationError(
                            row_index=idx,
                            column_name=amount_col,
                            error_type='business_rule',
                            error_message=message,
                            current_value=df.loc[idx, amount_col]
                        ))
            
            elif condition == 'order_date <= current_date':
                # 查找订单日期字段
                date_col = None
                for mapping in mappings:
                    if mapping.get('target_field') == 'order_date':
                        date_col = mapping.get('source_column')
                        break
                
                if date_col and date_col in df.columns:
                    current_date = datetime.now().date()
                    for idx, date_value in df[date_col].items():
                        if pd.notna(date_value):
                            try:
                                if isinstance(date_value, str):
                                    parsed_date = datetime.strptime(date_value, '%Y-%m-%d').date()
                                else:
                                    parsed_date = date_value.date() if hasattr(date_value, 'date') else date_value
                                
                                if parsed_date > current_date:
                                    errors.append(ValidationError(
                                        row_index=idx,
                                        column_name=date_col,
                                        error_type='business_rule',
                                        error_message=message,
                                        current_value=date_value
                                    ))
                            except (ValueError, AttributeError):
                                pass
        
        return errors
    
    def _validate_consistency(self, df: pd.DataFrame, mappings: List[Dict[str, Any]]) -> List[ValidationError]:
        """验证数据一致性"""
        warnings = []
        
        # 检查重复记录
        duplicate_cols = []
        for mapping in mappings:
            source_col = mapping.get('source_column')
            target_field = mapping.get('target_field')
            
            if target_field in ['order_id', 'product_id'] and source_col in df.columns:
                duplicate_cols.append(source_col)
        
        if duplicate_cols:
            duplicates = df[df.duplicated(subset=duplicate_cols, keep=False)]
            for idx in duplicates.index:
                warnings.append(ValidationError(
                    row_index=idx,
                    column_name=','.join(duplicate_cols),
                    error_type='consistency',
                    error_message="发现重复记录",
                    current_value=duplicates.loc[idx, duplicate_cols].to_dict()
                ))
        
        return warnings
    
    def _generate_statistics(self, df: pd.DataFrame, errors: List[ValidationError], 
                           warnings: List[ValidationError]) -> Dict[str, Any]:
        """生成验证统计信息"""
        total_rows = len(df)
        error_count = len(errors)
        warning_count = len(warnings)
        
        # 按错误类型分组
        error_types = {}
        for error in errors:
            error_type = error.error_type
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        # 按列分组错误
        column_errors = {}
        for error in errors:
            col = error.column_name
            column_errors[col] = column_errors.get(col, 0) + 1
        
        return {
            'total_rows': total_rows,
            'error_count': error_count,
            'warning_count': warning_count,
            'error_rate': error_count / total_rows if total_rows > 0 else 0,
            'warning_rate': warning_count / total_rows if total_rows > 0 else 0,
            'error_types': error_types,
            'column_errors': column_errors,
            'validation_passed': error_count == 0
        }
    
    def _is_valid_date(self, value: str) -> bool:
        """检查是否为有效日期"""
        date_formats = [
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%d/%m/%Y',
            '%m/%d/%Y',
            '%d-%m-%Y'
        ]
        
        for fmt in date_formats:
            try:
                datetime.strptime(value, fmt)
                return True
            except ValueError:
                continue
        
        return False
    
    def _is_valid_datetime(self, value: str) -> bool:
        """检查是否为有效日期时间"""
        datetime_formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y/%m/%d %H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%SZ'
        ]
        
        for fmt in datetime_formats:
            try:
                datetime.strptime(value, fmt)
                return True
            except ValueError:
                continue
        
        return False
    
    def add_custom_rule(self, field_name: str, rule_type: str, rule_config: Dict[str, Any]):
        """添加自定义验证规则"""
        if rule_type not in self.validation_rules:
            self.validation_rules[rule_type] = {}
        
        self.validation_rules[rule_type][field_name] = rule_config
    
    def get_validation_summary(self, result: ValidationResult) -> Dict[str, Any]:
        """获取验证摘要"""
        return {
            'is_valid': result.is_valid,
            'total_errors': len(result.errors),
            'total_warnings': len(result.warnings),
            'statistics': result.statistics,
            'error_summary': {
                error_type: len([e for e in result.errors if e.error_type == error_type])
                for error_type in set(e.error_type for e in result.errors)
            },
            'recommendations': self._generate_recommendations(result)
        }
    
    def _generate_recommendations(self, result: ValidationResult) -> List[str]:
        """生成修复建议"""
        recommendations = []
        
        if not result.errors:
            recommendations.append("数据验证通过，可以安全入库")
            return recommendations
        
        # 分析错误类型给出建议
        error_types = set(e.error_type for e in result.errors)
        
        if 'data_type' in error_types:
            recommendations.append("发现数据类型错误，请检查数据格式或字段映射")
        
        if 'required_field' in error_types:
            recommendations.append("发现必填字段为空，请补充缺失数据")
        
        if 'foreign_key' in error_types:
            recommendations.append("发现外键引用错误，请检查关联表数据或调整映射")
        
        if 'business_rule' in error_types:
            recommendations.append("发现业务规则违规，请检查数据逻辑")
        
        if 'consistency' in result.statistics.get('error_types', {}):
            recommendations.append("发现重复数据，建议去重后重新验证")
        
        return recommendations


# 全局实例
_validator = None

def get_data_validator(database_engine=None) -> DataValidator:
    """获取数据验证器实例"""
    global _validator
    if _validator is None:
        _validator = DataValidator(database_engine)
    return _validator
