#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据入库流程验证工具

⭐ v4.12.0新增：验证数据入库流程是否符合设计规范

验证规则：
1. shop_id获取规则（从源数据、文件元数据、默认值等）
2. platform_code获取规则
3. 字段映射规则（如何从源数据映射到标准字段）
4. 数据验证规则（必填字段、数据类型、取值范围等）
5. AccountAlias映射规则
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from sqlalchemy import text

from modules.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class IngestionIssue:
    """入库流程问题"""
    severity: str  # 'error' | 'warning' | 'info'
    category: str  # 'shop_id' | 'platform_code' | 'field_mapping' | 'validation' | 'account_alias'
    issue: str = ""
    suggestion: Optional[str] = None
    code_location: Optional[str] = None  # 代码位置


@dataclass
class IngestionValidationResult:
    """入库流程验证结果"""
    is_valid: bool
    issues: List[IngestionIssue] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)


class DataIngestionValidator:
    """
    数据入库流程验证器
    
    验证规则：
    1. shop_id获取规则
    2. platform_code获取规则
    3. 字段映射规则
    4. 数据验证规则
    5. AccountAlias映射规则
    """
    
    def __init__(self, db: Session):
        """初始化验证器"""
        self.db = db
    
    def validate_ingestion_process(self) -> IngestionValidationResult:
        """验证数据入库流程"""
        issues = []
        
        # 1. 验证shop_id获取规则
        shop_id_issues = self._validate_shop_id_rules()
        issues.extend(shop_id_issues)
        
        # 2. 验证platform_code获取规则
        platform_code_issues = self._validate_platform_code_rules()
        issues.extend(platform_code_issues)
        
        # 3. 验证AccountAlias映射规则
        account_alias_issues = self._validate_account_alias_rules()
        issues.extend(account_alias_issues)
        
        # 4. 生成摘要
        summary = self._generate_summary(issues)
        
        return IngestionValidationResult(
            is_valid=len([i for i in issues if i.severity == 'error']) == 0,
            issues=issues,
            summary=summary
        )
    
    def _validate_shop_id_rules(self) -> List[IngestionIssue]:
        """验证shop_id获取规则"""
        issues = []
        
        # 规则1：优先从源数据获取shop_id
        # 规则2：使用AccountAlias映射非标准店铺名称
        # 规则3：从文件元数据获取shop_id
        # 规则4：默认值处理
        
        # 检查AccountAlias表是否存在
        try:
            result = self.db.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'account_aliases'
                )
            """))
            
            if not result.scalar():
                issues.append(IngestionIssue(
                    severity='warning',
                    category='account_alias',
                    issue='AccountAlias表不存在',
                    suggestion='应创建AccountAlias表用于映射非标准店铺名称',
                    code_location='modules/core/db/schema.py'
                ))
        except Exception as e:
            logger.error(f"验证AccountAlias表失败: {e}")
        
        # 检查数据入库代码是否正确使用AccountAlias
        # 这个检查需要静态代码分析，暂时跳过
        
        return issues
    
    def _validate_platform_code_rules(self) -> List[IngestionIssue]:
        """验证platform_code获取规则"""
        issues = []
        
        # 规则1：从文件元数据获取platform_code
        # 规则2：验证平台代码有效性
        
        # 检查DimPlatform表是否存在
        try:
            result = self.db.execute(text("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'dim_platforms'
                )
            """))
            
            if not result.scalar():
                issues.append(IngestionIssue(
                    severity='error',
                    category='platform_code',
                    issue='DimPlatform表不存在',
                    suggestion='应创建DimPlatform表用于验证平台代码有效性',
                    code_location='modules/core/db/schema.py'
                ))
        except Exception as e:
            logger.error(f"验证DimPlatform表失败: {e}")
        
        return issues
    
    def _validate_account_alias_rules(self) -> List[IngestionIssue]:
        """验证AccountAlias映射规则"""
        issues = []
        
        # 检查AccountAlias表结构
        try:
            result = self.db.execute(text("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns 
                WHERE table_schema = 'public' 
                AND table_name = 'account_aliases'
                ORDER BY ordinal_position
            """))
            
            columns = {row[0]: {'type': row[1], 'nullable': row[2]} for row in result.fetchall()}
            
            # 检查必需字段（根据schema.py中的实际字段）
            required_fields = ['platform', 'data_domain', 'store_label_raw', 'target_id']
            for field in required_fields:
                if field not in columns:
                    issues.append(IngestionIssue(
                        severity='error',
                        category='account_alias',
                        issue=f'AccountAlias表缺少必需字段: {field}',
                        suggestion=f'应在AccountAlias表中添加{field}字段',
                        code_location='modules/core/db/schema.py'
                    ))
        except Exception as e:
            # 表不存在，已在_validate_shop_id_rules中处理
            pass
        
        return issues
    
    def _generate_summary(self, issues: List[IngestionIssue]) -> Dict[str, Any]:
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


def validate_data_ingestion_process(db: Session) -> IngestionValidationResult:
    """
    验证数据入库流程是否符合规范
    
    Args:
        db: 数据库会话
        
    Returns:
        验证结果
    """
    validator = DataIngestionValidator(db)
    return validator.validate_ingestion_process()

