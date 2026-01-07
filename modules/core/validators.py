#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据验证器 - v4.3.5
统一的白名单校验和数据标准化
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass

# 白名单定义（Single Source of Truth）
VALID_PLATFORMS = {'shopee', 'tiktok', 'miaoshou', 'amazon'}
VALID_DATA_DOMAINS = {'orders', 'products', 'services', 'traffic', 'finance', 'analytics', 'inventory'}  # v4.10.0更新：traffic域已废弃（兼容性保留），统一使用analytics域
VALID_GRANULARITIES = {'daily', 'weekly', 'monthly', 'snapshot', 'hourly'}
VALID_SUB_DOMAINS = {'agent', 'ai_assistant', 'ai', ''}  # 空字符串表示无子域


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool
    normalized_value: Optional[str] = None
    error_message: Optional[str] = None


class DataValidator:
    """数据验证器（现代化ERP标准）"""
    
    @staticmethod
    def validate_platform(platform: str) -> ValidationResult:
        """
        验证并标准化平台名称
        
        Args:
            platform: 平台名称
            
        Returns:
            ValidationResult: 验证结果
        """
        if not platform:
            return ValidationResult(
                valid=False,
                error_message="平台名称不能为空"
            )
        
        normalized = platform.lower().strip()
        
        if normalized not in VALID_PLATFORMS:
            return ValidationResult(
                valid=False,
                error_message=f"无效的平台: {platform}。有效平台: {', '.join(sorted(VALID_PLATFORMS))}"
            )
        
        return ValidationResult(
            valid=True,
            normalized_value=normalized
        )
    
    @staticmethod
    def validate_data_domain(domain: str) -> ValidationResult:
        """
        验证并标准化数据域
        
        Args:
            domain: 数据域
            
        Returns:
            ValidationResult: 验证结果
        """
        if not domain:
            return ValidationResult(
                valid=False,
                error_message="数据域不能为空"
            )
        
        normalized = domain.lower().strip()
        
        if normalized not in VALID_DATA_DOMAINS:
            return ValidationResult(
                valid=False,
                error_message=f"无效的数据域: {domain}。有效数据域: {', '.join(sorted(VALID_DATA_DOMAINS))}"
            )
        
        return ValidationResult(
            valid=True,
            normalized_value=normalized
        )
    
    @staticmethod
    def validate_granularity(granularity: str) -> ValidationResult:
        """
        验证并标准化粒度
        
        Args:
            granularity: 时间粒度
            
        Returns:
            ValidationResult: 验证结果
        """
        if not granularity:
            return ValidationResult(
                valid=False,
                error_message="粒度不能为空"
            )
        
        normalized = granularity.lower().strip()
        
        if normalized not in VALID_GRANULARITIES:
            return ValidationResult(
                valid=False,
                error_message=f"无效的粒度: {granularity}。有效粒度: {', '.join(sorted(VALID_GRANULARITIES))}"
            )
        
        return ValidationResult(
            valid=True,
            normalized_value=normalized
        )
    
    @staticmethod
    def validate_sub_domain(sub_domain: str) -> ValidationResult:
        """
        验证并标准化子数据域
        
        Args:
            sub_domain: 子数据域
            
        Returns:
            ValidationResult: 验证结果
        """
        normalized = (sub_domain or '').lower().strip()
        
        if normalized not in VALID_SUB_DOMAINS:
            return ValidationResult(
                valid=False,
                error_message=f"无效的子数据域: {sub_domain}。有效子数据域: {', '.join(sorted(VALID_SUB_DOMAINS))}"
            )
        
        return ValidationResult(
            valid=True,
            normalized_value=normalized
        )
    
    @staticmethod
    def validate_file_metadata(
        platform: str,
        data_domain: str,
        granularity: str,
        sub_domain: str = ""
    ) -> Dict[str, Any]:
        """
        批量验证文件元数据
        
        Args:
            platform: 平台名称
            data_domain: 数据域
            granularity: 时间粒度
            sub_domain: 子数据域（可选）
            
        Returns:
            dict: {
                'valid': bool,
                'normalized': dict,
                'errors': list
            }
        """
        errors = []
        normalized = {}
        
        # 验证平台
        p_result = DataValidator.validate_platform(platform)
        if not p_result.valid:
            errors.append(p_result.error_message)
        else:
            normalized['platform'] = p_result.normalized_value
        
        # 验证数据域
        d_result = DataValidator.validate_data_domain(data_domain)
        if not d_result.valid:
            errors.append(d_result.error_message)
        else:
            normalized['data_domain'] = d_result.normalized_value
        
        # 验证粒度
        g_result = DataValidator.validate_granularity(granularity)
        if not g_result.valid:
            errors.append(g_result.error_message)
        else:
            normalized['granularity'] = g_result.normalized_value
        
        # 验证子域（可选）
        if sub_domain:
            s_result = DataValidator.validate_sub_domain(sub_domain)
            if not s_result.valid:
                errors.append(s_result.error_message)
            else:
                normalized['sub_domain'] = s_result.normalized_value
        else:
            normalized['sub_domain'] = ''
        
        return {
            'valid': len(errors) == 0,
            'normalized': normalized if len(errors) == 0 else {},
            'errors': errors
        }


# 便捷函数
def normalize_platform(platform: str) -> str:
    """标准化平台名称（小写）"""
    return platform.lower().strip() if platform else ''


def normalize_data_domain(domain: str) -> str:
    """标准化数据域（小写）"""
    return domain.lower().strip() if domain else ''


def normalize_granularity(granularity: str) -> str:
    """标准化粒度（小写）"""
    return granularity.lower().strip() if granularity else ''


def is_valid_platform(platform: str) -> bool:
    """检查是否为有效平台"""
    return normalize_platform(platform) in VALID_PLATFORMS


def is_valid_data_domain(domain: str) -> bool:
    """检查是否为有效数据域"""
    return normalize_data_domain(domain) in VALID_DATA_DOMAINS


def is_valid_granularity(granularity: str) -> bool:
    """检查是否为有效粒度"""
    return normalize_granularity(granularity) in VALID_GRANULARITIES

