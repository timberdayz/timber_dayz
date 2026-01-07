#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
货币代码提取和字段名归一化服务（v4.16.0增强版）

功能：
1. 从字段名中提取货币代码（ISO 4217标准）
2. 字段名归一化（移除货币代码部分）
3. 验证货币代码是否有效
4. 支持多种货币代码格式：
   - (BRL) - 括号格式（末尾和中间）
   - _BRL - 下划线格式（末尾和中间）
   - -BRL - 连字符格式（末尾和中间）
   -  BRL - 空格格式（字段末尾和中间）
   - R$, S$ - 货币符号格式（新增）
   - 巴西雷亚尔, 新加坡元 - 中文货币名称格式（新增）
   - brl, BRL, Brl - 大小写混合（新增）

使用示例：
    extractor = CurrencyExtractor()
    # 格式1: 括号格式
    currency_code = extractor.extract_currency_code("销售额（已付款订单）(BRL)")  # 返回 "BRL"
    normalized = extractor.normalize_field_name("销售额（已付款订单）(BRL)")  # 返回 "销售额（已付款订单）"
    # 格式2: 下划线格式
    currency_code = extractor.extract_currency_code("销售额_已付款订单_BRL")  # 返回 "BRL"
    normalized = extractor.normalize_field_name("销售额_已付款订单_BRL")  # 返回 "销售额_已付款订单"
    # 格式3: 货币符号格式（新增）
    currency_code = extractor.extract_currency_code("销售R$")  # 返回 "BRL"
    currency_code = extractor.extract_currency_code("销售额（已付款订单）(R$)")  # 返回 "BRL"
    # 格式4: 中文名称格式（新增）
    currency_code = extractor.extract_currency_code("销售额（巴西雷亚尔）")  # 返回 "BRL"
"""

import re
from typing import Optional, Tuple, List
from backend.services.currency_normalizer import CurrencyNormalizer
from modules.core.logger import get_logger

logger = get_logger(__name__)


class CurrencyExtractor:
    """
    货币代码提取和字段名归一化服务（v4.16.0增强版）
    
    设计原则：
    - 支持多种货币代码格式（括号、下划线、连字符、空格、符号、中文名称）
    - 按常见程度顺序匹配（括号格式优先）
    - 验证货币代码是否在ISO 4217列表中
    - 支持字段名归一化（移除货币代码部分）
    - 支持字段中间位置的货币代码识别
    """
    
    def __init__(self):
        """初始化货币代码提取器"""
        self.normalizer = CurrencyNormalizer()
        # 获取所有有效的货币代码列表（用于验证）
        self.valid_codes = set(self.normalizer.CODE_TO_NAME.keys())
        
        # ⭐ v4.16.0增强：支持多种货币代码格式（按常见程度排序）
        # 1. ISO代码格式（3位字母，支持大小写混合）
        self.ISO_CODE_PATTERNS = [
            re.compile(r'\(([A-Z]{3})\)$', re.IGNORECASE),      # 格式1: (BRL) - 末尾括号，最常见
            re.compile(r'\(([A-Z]{3})\)', re.IGNORECASE),       # 格式1b: (BRL) - 中间括号
            re.compile(r'_([A-Z]{3})$', re.IGNORECASE),         # 格式2: _BRL - 末尾下划线
            re.compile(r'_([A-Z]{3})_', re.IGNORECASE),         # 格式2b: _BRL_ - 中间下划线
            re.compile(r'-([A-Z]{3})$', re.IGNORECASE),         # 格式3: -BRL - 末尾连字符
            re.compile(r'-([A-Z]{3})-', re.IGNORECASE),         # 格式3b: -BRL- - 中间连字符
            re.compile(r'\s+([A-Z]{3})$', re.IGNORECASE),      # 格式4:  BRL - 末尾空格
            re.compile(r'\s+([A-Z]{3})\s+', re.IGNORECASE),    # 格式4b:  BRL  - 中间空格
        ]
        
        # 2. 货币符号格式（需要转义特殊字符）
        # 构建货币符号的正则表达式（按长度降序，避免短符号误匹配长符号）
        symbol_patterns = []
        sorted_symbols = sorted(self.normalizer.SYMBOL_TO_CODE.keys(), key=len, reverse=True)
        for symbol in sorted_symbols:
            escaped_symbol = re.escape(symbol)
            symbol_patterns.append(
                re.compile(r'[（(]' + escaped_symbol + r'[）)]', re.IGNORECASE)  # 括号中的符号
            )
            symbol_patterns.append(
                re.compile(escaped_symbol + r'$', re.IGNORECASE)  # 末尾符号
            )
            symbol_patterns.append(
                re.compile(escaped_symbol, re.IGNORECASE)  # 任意位置的符号
            )
        self.SYMBOL_PATTERNS = symbol_patterns
        
        # 3. 中文货币名称格式
        name_patterns = []
        sorted_names = sorted(self.normalizer.NAME_TO_CODE.keys(), key=len, reverse=True)
        for name in sorted_names:
            escaped_name = re.escape(name)
            name_patterns.append(
                re.compile(r'[（(]' + escaped_name + r'[）)]')  # 括号中的名称
            )
            name_patterns.append(
                re.compile(escaped_name + r'$')  # 末尾名称
            )
            name_patterns.append(
                re.compile(escaped_name)  # 任意位置的名称
            )
        self.NAME_PATTERNS = name_patterns
        
        # 保留向后兼容（使用第一个ISO代码模式）
        self.CURRENCY_PATTERN = self.ISO_CODE_PATTERNS[0]
        self.CURRENCY_PATTERNS = self.ISO_CODE_PATTERNS  # 向后兼容
    
    def extract_currency_code(self, field_name: str) -> Optional[str]:
        """
        从字段名中提取货币代码（支持多种格式）
        
        ⭐ v4.16.0增强：支持更多格式
        - ISO代码格式：(BRL), _BRL, -BRL,  BRL（支持末尾和中间位置，大小写混合）
        - 货币符号格式：R$, S$, €, £, ¥等（支持括号和末尾）
        - 中文名称格式：巴西雷亚尔, 新加坡元等（支持括号和末尾）
        
        Args:
            field_name: 字段名（如 "销售额（已付款订单）(BRL)" 或 "销售R$" 或 "销售额（巴西雷亚尔）"）
        
        Returns:
            货币代码（如 "BRL"）或 None（如果未找到或无效）
        """
        if not field_name:
            return None
        
        # 1. 优先尝试ISO代码格式（最常见）
        # ⭐ v4.16.0修复：当有多个货币代码时，匹配第一个出现的（按位置排序）
        iso_matches = []
        for pattern in self.ISO_CODE_PATTERNS:
            for match in pattern.finditer(field_name):
                currency_str = match.group(1)
                currency_code = currency_str.upper()  # 转换为大写
                
                # 验证货币代码是否在ISO 4217列表中
                if currency_code in self.valid_codes:
                    iso_matches.append((match.start(), currency_code, pattern.pattern))
        
        # 如果有多个匹配，选择第一个（位置最靠前）
        if iso_matches:
            iso_matches.sort(key=lambda x: x[0])  # 按位置排序
            first_match = iso_matches[0]
            currency_code = first_match[1]
            logger.debug(
                f"[CurrencyExtractor] 通过ISO代码格式提取: {currency_code} "
                f"（字段名: {field_name}, 位置: {first_match[0]}, 模式: {first_match[2]}）"
            )
            return currency_code
        
        # 2. 尝试货币符号格式
        for pattern in self.SYMBOL_PATTERNS:
            match = pattern.search(field_name)
            if match:
                matched_symbol = match.group(0)
                # 查找匹配的符号（可能需要去除括号）
                symbol = matched_symbol.strip('()（）')
                
                if symbol in self.normalizer.SYMBOL_TO_CODE:
                    currency_code = self.normalizer.SYMBOL_TO_CODE[symbol]
                    logger.debug(
                        f"[CurrencyExtractor] 通过货币符号格式提取: {currency_code} "
                        f"（字段名: {field_name}, 符号: {symbol}）"
                    )
                    return currency_code
        
        # 3. 尝试中文货币名称格式
        for pattern in self.NAME_PATTERNS:
            match = pattern.search(field_name)
            if match:
                matched_name = match.group(0)
                # 查找匹配的名称（可能需要去除括号）
                name = matched_name.strip('()（）')
                
                if name in self.normalizer.NAME_TO_CODE:
                    currency_code = self.normalizer.NAME_TO_CODE[name]
                    logger.debug(
                        f"[CurrencyExtractor] 通过中文名称格式提取: {currency_code} "
                        f"（字段名: {field_name}, 名称: {name}）"
                    )
                    return currency_code
        
        # 4. 兜底策略：在整个字段名中查找货币符号或名称（用于处理"销售R$"这种格式）
        # 按长度降序查找，避免短符号误匹配
        for symbol in sorted(self.normalizer.SYMBOL_TO_CODE.keys(), key=len, reverse=True):
            if symbol in field_name:
                currency_code = self.normalizer.SYMBOL_TO_CODE[symbol]
                logger.debug(
                    f"[CurrencyExtractor] 通过兜底策略（符号）提取: {currency_code} "
                    f"（字段名: {field_name}, 符号: {symbol}）"
                )
                return currency_code
        
        for name in sorted(self.normalizer.NAME_TO_CODE.keys(), key=len, reverse=True):
            if name in field_name:
                currency_code = self.normalizer.NAME_TO_CODE[name]
                logger.debug(
                    f"[CurrencyExtractor] 通过兜底策略（名称）提取: {currency_code} "
                    f"（字段名: {field_name}, 名称: {name}）"
                )
                return currency_code
        
        return None
    
    def normalize_field_name(self, field_name: str) -> str:
        """
        归一化字段名（移除货币代码部分，支持多种格式）
        
        ⭐ v4.16.0增强：支持清理更多格式
        - 移除ISO代码部分（支持末尾和中间位置）
        - 移除货币符号（支持括号和末尾）
        - 移除中文货币名称（支持括号和末尾）
        - 清理尾随的分隔符和空格
        
        Args:
            field_name: 原始字段名（如 "销售额（已付款订单）(BRL)" 或 "销售R$" 或 "销售额（巴西雷亚尔）"）
        
        Returns:
            归一化后的字段名（如 "销售额（已付款订单）" 或 "销售"）
        """
        if not field_name:
            return field_name
        
        normalized = field_name
        
        # 1. 移除ISO代码格式（支持末尾和中间位置）
        # 策略：先处理括号格式（完整移除），再处理分隔符格式（保留分隔符）
        
        # 1.1 先处理括号格式（完整移除括号和内容）
        normalized = re.sub(r'\(([A-Z]{3})\)', '', normalized, flags=re.IGNORECASE)
        normalized = re.sub(r'（([A-Z]{3})）', '', normalized, flags=re.IGNORECASE)
        
        # 1.2 处理下划线格式（保留分隔符）
        # 匹配 _BRL_ 格式，移除 BRL 但保留下划线
        normalized = re.sub(r'_([A-Z]{3})_', '_', normalized, flags=re.IGNORECASE)
        # 匹配 _BRL$ 格式，移除 _BRL
        normalized = re.sub(r'_([A-Z]{3})$', '', normalized, flags=re.IGNORECASE)
        
        # 1.3 处理连字符格式（保留分隔符）
        # 匹配 -BRL- 格式，移除 BRL 但保留连字符
        normalized = re.sub(r'-([A-Z]{3})-', '-', normalized, flags=re.IGNORECASE)
        # 匹配 -BRL$ 格式，移除 -BRL
        normalized = re.sub(r'-([A-Z]{3})$', '', normalized, flags=re.IGNORECASE)
        
        # 1.4 处理空格格式（保留单个空格）
        # 匹配  BRL  格式，移除 BRL 但保留空格
        normalized = re.sub(r'\s+([A-Z]{3})\s+', ' ', normalized, flags=re.IGNORECASE)
        # 匹配  BRL$ 格式，移除空格和BRL
        normalized = re.sub(r'\s+([A-Z]{3})$', '', normalized, flags=re.IGNORECASE)
        
        # 2. 移除货币符号（按长度降序，避免短符号误匹配）
        for symbol in sorted(self.normalizer.SYMBOL_TO_CODE.keys(), key=len, reverse=True):
            escaped_symbol = re.escape(symbol)
            # 移除括号中的符号（完整移除括号和符号）
            normalized = re.sub(r'[（(]' + escaped_symbol + r'[）)]', '', normalized)
            # 移除末尾的符号
            normalized = re.sub(escaped_symbol + r'$', '', normalized)
            # 移除中间位置的符号（保留分隔符）
            normalized = re.sub(r'_' + escaped_symbol + r'_', '_', normalized)
            normalized = re.sub(r'-' + escaped_symbol + r'-', '-', normalized)
            normalized = re.sub(r'\s+' + escaped_symbol + r'\s+', ' ', normalized)
        
        # 3. 移除中文货币名称（按长度降序，避免短名称误匹配）
        for name in sorted(self.normalizer.NAME_TO_CODE.keys(), key=len, reverse=True):
            escaped_name = re.escape(name)
            # 移除括号中的名称（完整移除括号和名称）
            normalized = re.sub(r'[（(]' + escaped_name + r'[）)]', '', normalized)
            # 移除末尾的名称
            normalized = re.sub(escaped_name + r'$', '', normalized)
            # 移除中间位置的名称（保留分隔符）
            normalized = re.sub(r'_' + escaped_name + r'_', '_', normalized)
            normalized = re.sub(r'-' + escaped_name + r'-', '-', normalized)
            normalized = re.sub(r'\s+' + escaped_name + r'\s+', ' ', normalized)
        
        # 4. 清理尾随和开头的分隔符、空格、括号
        normalized = normalized.strip()
        # 清理尾随的分隔符（但保留中文括号）
        normalized = re.sub(r'[_\s\-\(\)、，,]+$', '', normalized)
        # 清理开头的分隔符（但保留中文括号）
        normalized = re.sub(r'^[_\s\-\(\)、，,]+', '', normalized)
        
        # 5. 清理多余的连续分隔符（但保留单个分隔符）
        normalized = re.sub(r'[_\s\-]{2,}', '', normalized)
        
        # 6. 修复中文括号不匹配的问题（如果左括号存在但右括号被移除）
        # 统计左括号和右括号数量
        left_brackets_chinese = normalized.count('（')
        right_brackets_chinese = normalized.count('）')
        left_brackets_english = normalized.count('(')
        right_brackets_english = normalized.count(')')
        
        # 修复中文括号
        if left_brackets_chinese > right_brackets_chinese:
            normalized += '）'
        # 修复英文括号
        if left_brackets_english > right_brackets_english:
            normalized += ')'
        
        return normalized
    
    def extract_and_normalize(self, field_name: str) -> Tuple[Optional[str], str]:
        """
        提取货币代码并归一化字段名（一步完成）
        
        ⭐ v4.16.0增强：支持更多货币代码格式
        
        Args:
            field_name: 原始字段名（如 "销售额（已付款订单）(BRL)" 或 "销售R$" 或 "销售额（巴西雷亚尔）"）
        
        Returns:
            (currency_code, normalized_field_name)
            - currency_code: 货币代码（如 "BRL"）或 None
            - normalized_field_name: 归一化后的字段名（如 "销售额（已付款订单）" 或 "销售"）
        """
        currency_code = self.extract_currency_code(field_name)
        normalized = self.normalize_field_name(field_name)
        return currency_code, normalized
    
    def extract_with_debug(self, field_name: str) -> Tuple[Optional[str], str, dict]:
        """
        提取货币代码并返回调试信息（用于问题排查）
        
        ⭐ v4.16.0新增：调试功能
        
        Args:
            field_name: 原始字段名
        
        Returns:
            (currency_code, normalized_field_name, debug_info)
            - currency_code: 货币代码或 None
            - normalized_field_name: 归一化后的字段名
            - debug_info: 调试信息字典
        """
        debug_info = {
            'original': field_name,
            'matched_pattern': None,
            'matched_string': None,
            'normalization_method': None,
            'extraction_method': None
        }
        
        # 尝试提取货币代码
        currency_code = None
        
        # 1. 尝试ISO代码格式
        for pattern in self.ISO_CODE_PATTERNS:
            match = pattern.search(field_name)
            if match:
                currency_str = match.group(1).upper()
                if currency_str in self.valid_codes:
                    currency_code = currency_str
                    debug_info['matched_pattern'] = pattern.pattern
                    debug_info['matched_string'] = match.group(0)
                    debug_info['extraction_method'] = 'ISO_CODE'
                    break
        
        # 2. 尝试货币符号格式
        if not currency_code:
            for pattern in self.SYMBOL_PATTERNS:
                match = pattern.search(field_name)
                if match:
                    matched_symbol = match.group(0).strip('()（）')
                    if matched_symbol in self.normalizer.SYMBOL_TO_CODE:
                        currency_code = self.normalizer.SYMBOL_TO_CODE[matched_symbol]
                        debug_info['matched_pattern'] = pattern.pattern
                        debug_info['matched_string'] = match.group(0)
                        debug_info['extraction_method'] = 'SYMBOL'
                        break
        
        # 3. 尝试中文名称格式
        if not currency_code:
            for pattern in self.NAME_PATTERNS:
                match = pattern.search(field_name)
                if match:
                    matched_name = match.group(0).strip('()（）')
                    if matched_name in self.normalizer.NAME_TO_CODE:
                        currency_code = self.normalizer.NAME_TO_CODE[matched_name]
                        debug_info['matched_pattern'] = pattern.pattern
                        debug_info['matched_string'] = match.group(0)
                        debug_info['extraction_method'] = 'CHINESE_NAME'
                        break
        
        # 归一化字段名
        normalized = self.normalize_field_name(field_name)
        debug_info['normalized'] = normalized
        
        return currency_code, normalized, debug_info
    
    def normalize_field_list(self, field_names: List[str]) -> List[str]:
        """
        批量归一化字段名列表
        
        Args:
            field_names: 字段名列表
        
        Returns:
            归一化后的字段名列表
        """
        return [self.normalize_field_name(field) for field in field_names]
    
    def extract_currency_from_row(
        self,
        row: dict,
        header_columns: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        从数据行中提取货币代码（如果一行有多个货币字段，提取第一个）
        
        Args:
            row: 数据行字典
            header_columns: 表头字段列表（可选，如果提供则只检查这些字段）
        
        Returns:
            货币代码（如 "BRL"）或 None
        """
        fields_to_check = header_columns if header_columns else list(row.keys())
        
        currency_codes = []
        for field_name in fields_to_check:
            currency_code = self.extract_currency_code(field_name)
            if currency_code:
                currency_codes.append((field_name, currency_code))
        
        if not currency_codes:
            return None
        
        # 如果一行数据有多个货币字段，提取第一个（方案A）
        if len(currency_codes) > 1:
            different_codes = set(code for _, code in currency_codes)
            if len(different_codes) > 1:
                logger.warning(
                    f"[CurrencyExtractor] 检测到多个不同的货币代码: {different_codes}，"
                    f"将使用第一个: {currency_codes[0][1]}（字段: {currency_codes[0][0]}）"
                )
        
        return currency_codes[0][1]


# 全局单例实例
_currency_extractor = None


def get_currency_extractor() -> CurrencyExtractor:
    """获取货币代码提取器单例实例"""
    global _currency_extractor
    if _currency_extractor is None:
        _currency_extractor = CurrencyExtractor()
    return _currency_extractor

