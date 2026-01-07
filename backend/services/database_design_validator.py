#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库设计规范验证工具

⭐ v4.12.0新增：验证数据库模型是否符合设计规范

功能：
1. 验证数据库模型是否符合主键设计规则
2. 验证字段是否符合必填规则
3. 验证索引设计是否符合规范
4. 验证物化视图是否符合规范
5. 生成验证报告

设计标准：
- 经营数据：自增ID主键 + SKU为核心的唯一索引
- 运营数据：自增ID主键 + shop_id为核心的唯一索引
- 主视图：包含数据域所有核心字段
- 辅助视图：依赖主视图或基础数据
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine
import re

from modules.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ValidationIssue:
    """验证问题"""
    severity: str  # 'error' | 'warning' | 'info'
    category: str  # 'primary_key' | 'nullable' | 'index' | 'foreign_key' | 'materialized_view'
    table_name: str
    field_name: Optional[str] = None
    issue: str = ""
    suggestion: Optional[str] = None


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


class DatabaseDesignValidator:
    """
    数据库设计规范验证器
    
    验证规则：
    1. 主键设计规则
    2. 字段必填规则
    3. 索引设计规则
    4. 外键约束规则
    5. 物化视图设计规则
    """
    
    # 经营数据表（以SKU为核心）
    OPERATIONAL_DATA_TABLES = {
        'fact_product_metrics',
        'fact_order_items',
        'fact_orders',  # 订单数据属于经营数据，但主键包含order_id
    }
    
    # 运营数据表（以shop_id为核心）
    BUSINESS_DATA_TABLES = {
        # 待创建：fact_traffic, fact_service, fact_analytics
    }
    
    # 主视图列表
    MAIN_VIEWS = {
        'mv_product_management': 'products',
        'mv_order_summary': 'orders',
        'mv_inventory_summary': 'inventory',
        'mv_traffic_summary': 'traffic',
        'mv_financial_overview': 'finance',
    }
    
    def __init__(self, db: Session):
        """初始化验证器"""
        self.db = db
        self.engine = db.bind
        self.inspector = inspect(self.engine)
    
    def validate_all(self) -> ValidationResult:
        """验证所有数据库模型"""
        issues = []
        
        # 1. 验证表结构
        table_issues = self.validate_tables()
        issues.extend(table_issues)
        
        # 2. 验证物化视图
        mv_issues = self.validate_materialized_views()
        issues.extend(mv_issues)
        
        # 3. 生成摘要
        summary = self._generate_summary(issues)
        
        return ValidationResult(
            is_valid=len([i for i in issues if i.severity == 'error']) == 0,
            issues=issues,
            summary=summary
        )
    
    def validate_tables(self) -> List[ValidationIssue]:
        """验证表结构"""
        issues = []
        tables = self.inspector.get_table_names()
        
        for table_name in tables:
            # 跳过系统表
            if table_name.startswith('pg_') or table_name.startswith('alembic'):
                continue
            
            # 验证主键
            pk_issues = self._validate_primary_key(table_name)
            issues.extend(pk_issues)
            
            # 验证字段必填规则
            nullable_issues = self._validate_nullable_fields(table_name)
            issues.extend(nullable_issues)
            
            # 验证索引
            index_issues = self._validate_indexes(table_name)
            issues.extend(index_issues)
            
            # 验证外键
            fk_issues = self._validate_foreign_keys(table_name)
            issues.extend(fk_issues)
        
        return issues
    
    def _validate_primary_key(self, table_name: str) -> List[ValidationIssue]:
        """验证主键设计"""
        issues = []
        
        try:
            pk_constraint = self.inspector.get_pk_constraint(table_name)
            pk_columns = pk_constraint.get('constrained_columns', [])
            
            if not pk_columns:
                issues.append(ValidationIssue(
                    severity='error',
                    category='primary_key',
                    table_name=table_name,
                    issue='表缺少主键',
                    suggestion='所有表必须有主键'
                ))
                return issues
            
            # 检查是否是经营数据表
            is_operational = table_name in self.OPERATIONAL_DATA_TABLES
            
            # 检查主键是否包含业务标识字段
            if is_operational:
                # 经营数据：主键应包含platform_code, shop_id, 业务标识（如platform_sku或order_id）
                has_platform_code = 'platform_code' in pk_columns
                has_shop_id = 'shop_id' in pk_columns
                has_business_id = any(col in pk_columns for col in ['platform_sku', 'order_id', 'product_id'])
                
                if not (has_platform_code and has_shop_id and has_business_id):
                    issues.append(ValidationIssue(
                        severity='warning',
                        category='primary_key',
                        table_name=table_name,
                        issue=f'经营数据表主键设计：当前主键={pk_columns}',
                        suggestion='经营数据表主键应包含platform_code, shop_id, 业务标识（如platform_sku或order_id）'
                    ))
            
            # 检查是否有自增ID（推荐但不强制）
            columns = self.inspector.get_columns(table_name)
            has_auto_increment_id = any(
                col.get('autoincrement', False) and col['name'] == 'id'
                for col in columns
            )
            
            if not has_auto_increment_id and is_operational:
                issues.append(ValidationIssue(
                    severity='info',
                    category='primary_key',
                    table_name=table_name,
                    issue='表没有自增ID字段',
                    suggestion='推荐使用自增ID作为主键，业务唯一性通过唯一索引保证'
                ))
        
        except Exception as e:
            logger.error(f"验证主键失败 {table_name}: {e}")
            issues.append(ValidationIssue(
                severity='error',
                category='primary_key',
                table_name=table_name,
                issue=f'验证主键时出错: {e}'
            ))
        
        return issues
    
    def _validate_nullable_fields(self, table_name: str) -> List[ValidationIssue]:
        """验证字段必填规则"""
        issues = []
        
        try:
            columns = self.inspector.get_columns(table_name)
            
            # 业务标识字段必须NOT NULL
            business_id_fields = ['platform_code', 'order_id', 'platform_sku', 'shop_id']
            
            for col in columns:
                col_name = col['name']
                is_nullable = col.get('nullable', True)
                
                # 主键字段必须NOT NULL
                pk_constraint = self.inspector.get_pk_constraint(table_name)
                pk_columns = pk_constraint.get('constrained_columns', [])
                
                if col_name in pk_columns and is_nullable:
                    issues.append(ValidationIssue(
                        severity='error',
                        category='nullable',
                        table_name=table_name,
                        field_name=col_name,
                        issue='主键字段不能为NULL',
                        suggestion='主键字段必须NOT NULL'
                    ))
                
                # 业务标识字段应该NOT NULL（除非明确允许NULL）
                if col_name in business_id_fields and is_nullable and col_name not in pk_columns:
                    issues.append(ValidationIssue(
                        severity='warning',
                        category='nullable',
                        table_name=table_name,
                        field_name=col_name,
                        issue=f'业务标识字段{col_name}允许NULL',
                        suggestion='业务标识字段通常应该NOT NULL，除非业务明确需要支持NULL'
                    ))
                
                # 金额字段应该NOT NULL（避免NULL计算问题）
                amount_fields = ['total_amount', 'subtotal', 'quantity', 'price', 'sales_amount']
                if any(field in col_name.lower() for field in amount_fields) and is_nullable:
                    issues.append(ValidationIssue(
                        severity='warning',
                        category='nullable',
                        table_name=table_name,
                        field_name=col_name,
                        issue=f'金额字段{col_name}允许NULL',
                        suggestion='金额字段应该NOT NULL，默认值为0.0，避免NULL计算问题'
                    ))
        
        except Exception as e:
            logger.error(f"验证字段必填规则失败 {table_name}: {e}")
        
        return issues
    
    def _validate_indexes(self, table_name: str) -> List[ValidationIssue]:
        """验证索引设计"""
        issues = []
        
        try:
            indexes = self.inspector.get_indexes(table_name)
            
            # 检查是否有业务唯一索引
            has_unique_index = any(idx.get('unique', False) for idx in indexes)
            
            # 经营数据表应该有包含SKU的唯一索引
            if table_name in self.OPERATIONAL_DATA_TABLES:
                has_sku_index = any(
                    'platform_sku' in idx.get('column_names', []) or 'sku' in ' '.join(idx.get('column_names', []))
                    for idx in indexes
                )
                
                if not has_sku_index:
                    issues.append(ValidationIssue(
                        severity='info',
                        category='index',
                        table_name=table_name,
                        issue='经营数据表缺少SKU相关索引',
                        suggestion='经营数据表应创建包含platform_sku的业务唯一索引'
                    ))
        
        except Exception as e:
            logger.error(f"验证索引失败 {table_name}: {e}")
        
        return issues
    
    def _validate_foreign_keys(self, table_name: str) -> List[ValidationIssue]:
        """验证外键约束"""
        issues = []
        
        try:
            foreign_keys = self.inspector.get_foreign_keys(table_name)
            
            for fk in foreign_keys:
                fk_name = fk.get('name', 'unnamed')
                fk_columns = fk.get('constrained_columns', [])
                referred_table = fk.get('referred_table', '')
                referred_columns = fk.get('referred_columns', [])
                
                # 检查外键命名规范
                if not fk_name.startswith('fk_'):
                    issues.append(ValidationIssue(
                        severity='info',
                        category='foreign_key',
                        table_name=table_name,
                        issue=f'外键命名不规范: {fk_name}',
                        suggestion='外键命名应遵循fk_表名_字段名格式'
                    ))
        
        except Exception as e:
            logger.error(f"验证外键失败 {table_name}: {e}")
        
        return issues
    
    def validate_materialized_views(self) -> List[ValidationIssue]:
        """验证物化视图设计"""
        issues = []
        
        try:
            # 查询所有物化视图
            result = self.db.execute(text("""
                SELECT matviewname 
                FROM pg_matviews 
                WHERE schemaname = 'public'
            """))
            materialized_views = [row[0] for row in result.fetchall()]
            
            # 检查主视图是否存在
            for view_name, data_domain in self.MAIN_VIEWS.items():
                if view_name not in materialized_views:
                    issues.append(ValidationIssue(
                        severity='warning',
                        category='materialized_view',
                        table_name=view_name,
                        issue=f'{data_domain}域主视图不存在',
                        suggestion=f'应创建{view_name}主视图，包含{data_domain}域的所有核心字段'
                    ))
                else:
                    # 验证主视图是否有唯一索引
                    indexes = self.inspector.get_indexes(view_name)
                    has_unique_index = any(idx.get('unique', False) for idx in indexes)
                    
                    if not has_unique_index:
                        issues.append(ValidationIssue(
                            severity='warning',
                            category='materialized_view',
                            table_name=view_name,
                            issue=f'主视图{view_name}缺少唯一索引',
                            suggestion='主视图应创建唯一索引以支持CONCURRENTLY刷新'
                        ))
        
        except Exception as e:
            logger.error(f"验证物化视图失败: {e}")
        
        return issues
    
    def _generate_summary(self, issues: List[ValidationIssue]) -> Dict[str, Any]:
        """生成验证摘要"""
        error_count = len([i for i in issues if i.severity == 'error'])
        warning_count = len([i for i in issues if i.severity == 'warning'])
        info_count = len([i for i in issues if i.severity == 'info'])
        
        category_counts = {}
        for issue in issues:
            category_counts[issue.category] = category_counts.get(issue.category, 0) + 1
        
        return {
            'total_issues': len(issues),
            'error_count': error_count,
            'warning_count': warning_count,
            'info_count': info_count,
            'category_counts': category_counts,
            'is_valid': error_count == 0
        }


def validate_database_design(db: Session) -> ValidationResult:
    """
    验证数据库设计是否符合规范
    
    Args:
        db: 数据库会话
        
    Returns:
        验证结果
    """
    validator = DatabaseDesignValidator(db)
    return validator.validate_all()


# ⭐ v4.12.0新增：导入数据入库流程验证器
from backend.services.data_ingestion_validator import validate_data_ingestion_process

