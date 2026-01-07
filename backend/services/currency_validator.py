#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
货币字段验证服务

功能：
1. 验证字段是否符合货币策略
2. 检测多币种数据混入
3. 自动标记货币策略违规数据

货币策略：
- orders域：CNY本位币（必须为CNY）
- products域：无货币（禁止货币字段）
- inventory域：CNY本位币（必须为CNY）

用于C类数据核心字段优化计划（Phase 3）
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass
import re

from modules.core.logger import get_logger

logger = get_logger(__name__)

# 货币策略定义
CURRENCY_POLICIES = {
    "orders": {
        "currency": "CNY",
        "source_priority": ["miaoshou"],
        "validation": "必须为CNY，禁止多币种",
        "allowed_currencies": ["CNY", "RMB", "人民币"]
    },
    "products": {
        "currency": "无货币",
        "source_priority": ["shopee", "tiktok"],
        "validation": "只采集数量指标，禁止货币字段",
        "allowed_currencies": []  # 空列表表示禁止任何货币字段
    },
    "inventory": {
        "currency": "CNY",
        "source_priority": ["miaoshou"],
        "validation": "必须为CNY，统一从妙手ERP导出",
        "allowed_currencies": ["CNY", "RMB", "人民币"]
    },
    "general": {
        "currency": "CNY",
        "source_priority": [],
        "validation": "默认CNY",
        "allowed_currencies": ["CNY", "RMB", "人民币"]
    }
}

# 货币字段识别模式（用于检测货币字段）
CURRENCY_FIELD_PATTERNS = [
    r".*amount.*",
    r".*price.*",
    r".*cost.*",
    r".*revenue.*",
    r".*sales.*money.*",
    r".*total.*money.*",
    r".*value.*",
    r".*金额.*",
    r".*价格.*",
    r".*成本.*",
    r".*收入.*",
    r".*销售额.*",
]

# 货币符号识别模式（用于检测货币值）
CURRENCY_SYMBOL_PATTERNS = {
    "CNY": [r"¥", r"CNY", r"RMB", r"人民币", r"元"],
    "SGD": [r"S\$", r"SGD", r"新加坡元"],
    "MYR": [r"RM", r"MYR", r"马来西亚林吉特"],
    "THB": [r"฿", r"THB", r"泰铢"],
    "USD": [r"\$", r"USD", r"美元"],
    "EUR": [r"€", r"EUR", r"欧元"],
    "BRL": [r"R\$", r"BRL", r"巴西雷亚尔"],
}


@dataclass
class ValidationResult:
    """验证结果"""
    valid: bool
    error: Optional[str] = None
    warning: Optional[str] = None
    detected_currency: Optional[str] = None
    field_code: Optional[str] = None


class CurrencyValidator:
    """货币字段验证器"""
    
    def __init__(self):
        self.policies = CURRENCY_POLICIES
        self.currency_patterns = CURRENCY_FIELD_PATTERNS
        self.currency_symbols = CURRENCY_SYMBOL_PATTERNS
    
    def validate_currency_policy(
        self,
        field_code: str,
        data_domain: str,
        value: Any = None,
        field_name: Optional[str] = None
    ) -> ValidationResult:
        """
        验证字段是否符合货币策略
        
        参数：
            field_code: 字段代码（如total_amount_rmb）
            data_domain: 数据域（orders/products/inventory）
            value: 字段值（可选，用于检测货币符号）
            field_name: 字段名称（可选，用于检测货币字段）
        
        返回：
            ValidationResult对象
        """
        # 获取数据域的货币策略
        policy = self.policies.get(data_domain, self.policies["general"])
        
        # 检查是否为货币字段
        is_currency_field = self._is_currency_field(field_code, field_name)
        
        # 如果数据域禁止货币字段
        if policy["currency"] == "无货币":
            if is_currency_field:
                return ValidationResult(
                    valid=False,
                    error=f"运营数据域禁止货币字段：{field_code}",
                    field_code=field_code
                )
            else:
                return ValidationResult(valid=True)
        
        # 如果数据域要求CNY本位币
        if policy["currency"] == "CNY":
            if is_currency_field:
                # 检查字段名是否符合CNY命名规范
                if not self._is_cny_field(field_code):
                    return ValidationResult(
                        valid=False,
                        error=f"金额字段必须包含_rmb或_cny后缀：{field_code}",
                        field_code=field_code
                    )
                
                # 如果提供了值，检查货币符号
                if value is not None:
                    detected_currency = self._detect_currency_symbol(value)
                    if detected_currency and detected_currency not in policy["allowed_currencies"]:
                        return ValidationResult(
                            valid=False,
                            error=f"检测到非CNY货币：{detected_currency}，字段：{field_code}",
                            detected_currency=detected_currency,
                            field_code=field_code
                        )
                
                return ValidationResult(valid=True)
        
        return ValidationResult(valid=True)
    
    def _is_currency_field(self, field_code: str, field_name: Optional[str] = None) -> bool:
        """检查是否为货币字段"""
        # 检查字段代码
        field_code_lower = field_code.lower()
        for pattern in self.currency_patterns:
            if re.search(pattern, field_code_lower, re.IGNORECASE):
                return True
        
        # 检查字段名（如果提供）
        if field_name:
            field_name_lower = field_name.lower()
            for pattern in self.currency_patterns:
                if re.search(pattern, field_name_lower, re.IGNORECASE):
                    return True
        
        return False
    
    def _is_cny_field(self, field_code: str) -> bool:
        """检查是否为CNY字段（包含_rmb或_cny后缀）"""
        field_code_lower = field_code.lower()
        return "_rmb" in field_code_lower or "_cny" in field_code_lower or field_code_lower.endswith("_rmb") or field_code_lower.endswith("_cny")
    
    def _detect_currency_symbol(self, value: Any) -> Optional[str]:
        """检测值中的货币符号"""
        if value is None:
            return None
        
        value_str = str(value)
        
        # 检查各种货币符号
        for currency, patterns in self.currency_symbols.items():
            for pattern in patterns:
                if re.search(pattern, value_str, re.IGNORECASE):
                    return currency
        
        return None
    
    def validate_batch_fields(
        self,
        fields: Dict[str, Any],
        data_domain: str
    ) -> Dict[str, ValidationResult]:
        """
        批量验证字段货币策略
        
        参数：
            fields: 字段字典 {field_code: value}
            data_domain: 数据域
        
        返回：
            {field_code: ValidationResult}
        """
        results = {}
        
        for field_code, value in fields.items():
            result = self.validate_currency_policy(
                field_code=field_code,
                data_domain=data_domain,
                value=value
            )
            results[field_code] = result
        
        return results
    
    def detect_multi_currency(
        self,
        fields: Dict[str, Any],
        data_domain: str
    ) -> List[Dict[str, Any]]:
        """
        检测多币种数据混入
        
        参数：
            fields: 字段字典
            data_domain: 数据域
        
        返回：
            [
                {
                    "field_code": "total_amount_sgd",
                    "detected_currency": "SGD",
                    "error": "检测到非CNY货币：SGD"
                },
                ...
            ]
        """
        violations = []
        
        policy = self.policies.get(data_domain, self.policies["general"])
        
        # 如果数据域禁止货币字段，检查是否有货币字段
        if policy["currency"] == "无货币":
            for field_code, value in fields.items():
                if self._is_currency_field(field_code):
                    violations.append({
                        "field_code": field_code,
                        "detected_currency": "unknown",
                        "error": f"运营数据域禁止货币字段：{field_code}"
                    })
        
        # 如果数据域要求CNY，检查是否有非CNY货币
        elif policy["currency"] == "CNY":
            for field_code, value in fields.items():
                if self._is_currency_field(field_code):
                    detected_currency = self._detect_currency_symbol(value)
                    if detected_currency and detected_currency not in policy["allowed_currencies"]:
                        violations.append({
                            "field_code": field_code,
                            "detected_currency": detected_currency,
                            "error": f"检测到非CNY货币：{detected_currency}，字段：{field_code}"
                        })
        
        return violations


def get_currency_validator() -> CurrencyValidator:
    """获取货币验证器实例"""
    return CurrencyValidator()

