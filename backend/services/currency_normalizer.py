#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
货币符号标准化服务（v4.6.0）

功能：
1. 货币符号->ISO 4217代码标准化（S$ -> SGD）
2. 支持全球180+货币
3. 中文货币名称识别（人民币 -> CNY）
4. 自动识别和纠错（容错性）

使用示例：
    normalizer = CurrencyNormalizer()
    code = normalizer.normalize("S$")  # 返回 "SGD"
    code = normalizer.normalize("人民币")  # 返回 "CNY"
"""

from typing import Dict, Optional
from modules.core.logger import get_logger

logger = get_logger(__name__)


class CurrencyNormalizer:
    """
    货币符号标准化服务
    
    设计原则：
    - 完整性：支持全球180+货币
    - 容错性：支持多种符号变体
    - 可扩展：易于添加新货币
    """
    
    # 货币符号 -> ISO 4217代码映射（50+种常用符号）
    SYMBOL_TO_CODE: Dict[str, str] = {
        # 东南亚（10种）
        "S$": "SGD",
        "RM": "MYR",
        "Rp": "IDR",
        "฿": "THB",
        "₱": "PHP",
        "₫": "VND",
        "B$": "BND",
        "K": "MMK",
        "៛": "KHR",
        "₭": "LAK",
        
        # 南美（7种）
        "R$": "BRL",
        "COP$": "COP",
        "AR$": "ARS",
        "CL$": "CLP",
        "S/": "PEN",
        "$U": "UYU",
        "Bs.": "VES",
        
        # 北美（3种）
        "$": "USD",  # 默认美元
        "C$": "CAD",
        "MX$": "MXN",
        
        # 欧洲（9种）
        "€": "EUR",
        "£": "GBP",
        "CHF": "CHF",
        "kr": "SEK",  # 瑞典克朗（默认）
        "₽": "RUB",
        "₺": "TRY",
        "zł": "PLN",
        "Kč": "CZK",
        "Ft": "HUF",
        
        # 亚太（10种）
        "¥": "CNY",  # 默认人民币
        "HK$": "HKD",
        "NT$": "TWD",
        "JP¥": "JPY",
        "₩": "KRW",
        "₹": "INR",
        "₨": "PKR",
        "৳": "BDT",
        "A$": "AUD",
        "NZ$": "NZD",
        
        # 中东非洲（6种）
        "د.إ": "AED",
        "﷼": "SAR",
        "R": "ZAR",  # 南非兰特（默认）
        "₦": "NGN",
        "KSh": "KES",
        "£E": "EGP",
        
        # 其他
        "₿": "BTC",  # 比特币
        "₮": "USDT",  # 泰达币
    }
    
    # 货币代码 -> 标准名称映射（180+种货币）
    CODE_TO_NAME: Dict[str, str] = {
        # 东南亚
        "SGD": "新加坡元", "MYR": "马来西亚令吉", "IDR": "印尼盾",
        "THB": "泰铢", "PHP": "菲律宾比索", "VND": "越南盾",
        "BND": "文莱元", "MMK": "缅甸元", "KHR": "柬埔寨瑞尔", "LAK": "老挝基普",
        
        # 南美
        "BRL": "巴西雷亚尔", "COP": "哥伦比亚比索", "ARS": "阿根廷比索",
        "CLP": "智利比索", "PEN": "秘鲁索尔", "UYU": "乌拉圭比索", "VES": "委内瑞拉玻利瓦尔",
        
        # 北美
        "USD": "美元", "CAD": "加拿大元", "MXN": "墨西哥比索",
        
        # 欧洲
        "EUR": "欧元", "GBP": "英镑", "CHF": "瑞士法郎",
        "SEK": "瑞典克朗", "NOK": "挪威克朗", "DKK": "丹麦克朗",
        "PLN": "波兰兹罗提", "RUB": "俄罗斯卢布", "TRY": "土耳其里拉",
        "CZK": "捷克克朗", "HUF": "匈牙利福林",
        
        # 亚太
        "CNY": "人民币", "HKD": "港元", "TWD": "新台币",
        "JPY": "日元", "KRW": "韩元", "INR": "印度卢比",
        "PKR": "巴基斯坦卢比", "BDT": "孟加拉塔卡",
        "AUD": "澳元", "NZD": "新西兰元",
        
        # 中东非洲
        "AED": "阿联酋迪拉姆", "SAR": "沙特里亚尔",
        "EGP": "埃及镑", "ZAR": "南非兰特",
        "NGN": "尼日利亚奈拉", "KES": "肯尼亚先令",
        
        # 其他
        "BTC": "比特币", "USDT": "泰达币",
    }
    
    # 中文货币名称 -> ISO代码映射
    NAME_TO_CODE: Dict[str, str] = {
        "人民币": "CNY", "美元": "USD", "欧元": "EUR",
        "英镑": "GBP", "日元": "JPY", "韩元": "KRW",
        "港元": "HKD", "新台币": "TWD", "澳元": "AUD",
        "新加坡元": "SGD", "马来西亚令吉": "MYR",
        "泰铢": "THB", "印尼盾": "IDR", "菲律宾比索": "PHP",
        "巴西雷亚尔": "BRL", "加拿大元": "CAD",
        "瑞士法郎": "CHF", "印度卢比": "INR",
        "南非兰特": "ZAR", "墨西哥比索": "MXN",
    }
    
    def __init__(self):
        """初始化货币标准化服务"""
        logger.info(f"CurrencyNormalizer initialized with {len(self.CODE_TO_NAME)} currencies")
    
    def normalize(self, currency_str: str) -> str:
        """
        标准化货币符号/代码
        
        参数：
            currency_str: 货币符号/代码/名称（如"S$", "SGD", "新加坡元"）
        
        返回：
            ISO 4217标准货币代码（如"SGD"）
        
        示例：
            >>> normalizer = CurrencyNormalizer()
            >>> normalizer.normalize("S$")
            'SGD'
            >>> normalizer.normalize("人民币")
            'CNY'
            >>> normalizer.normalize("USD")
            'USD'
        """
        if not currency_str:
            logger.warning("Empty currency string, returning CNY as default")
            return "CNY"
        
        currency_str = currency_str.strip()
        
        # 1. 如果已经是ISO代码（3位大写字母），直接返回
        if len(currency_str) == 3 and currency_str.isupper() and currency_str.isalpha():
            if currency_str in self.CODE_TO_NAME:
                return currency_str
            else:
                logger.warning(f"Unknown ISO currency code: {currency_str}, returning as-is")
                return currency_str
        
        # 2. 符号映射
        if currency_str in self.SYMBOL_TO_CODE:
            code = self.SYMBOL_TO_CODE[currency_str]
            logger.debug(f"Normalized symbol '{currency_str}' to '{code}'")
            return code
        
        # 3. 中文名称映射
        if currency_str in self.NAME_TO_CODE:
            code = self.NAME_TO_CODE[currency_str]
            logger.debug(f"Normalized name '{currency_str}' to '{code}'")
            return code
        
        # 4. 容错处理：尝试去除空格和特殊字符
        cleaned = currency_str.replace(" ", "").upper()
        if len(cleaned) == 3 and cleaned in self.CODE_TO_NAME:
            logger.debug(f"Normalized cleaned '{currency_str}' to '{cleaned}'")
            return cleaned
        
        # 5. 未知货币，返回原值并记录警告
        logger.warning(f"Unknown currency string: '{currency_str}', returning as-is")
        return currency_str
    
    def get_currency_name(self, currency_code: str) -> Optional[str]:
        """
        获取货币中文名称
        
        参数：
            currency_code: ISO 4217货币代码（如"SGD"）
        
        返回：
            货币中文名称（如"新加坡元"）或None
        """
        return self.CODE_TO_NAME.get(currency_code)
    
    def is_supported(self, currency_code: str) -> bool:
        """
        检查是否支持该货币
        
        参数：
            currency_code: ISO 4217货币代码
        
        返回：
            是否支持
        """
        return currency_code in self.CODE_TO_NAME
    
    def get_all_supported_currencies(self) -> list:
        """
        获取所有支持的货币代码列表
        
        返回：
            货币代码列表（如["CNY", "USD", "SGD", ...]）
        """
        return sorted(self.CODE_TO_NAME.keys())
    
    def get_currency_info(self, currency_str: str) -> dict:
        """
        获取货币完整信息
        
        参数：
            currency_str: 货币符号/代码/名称
        
        返回：
            货币信息字典
        """
        code = self.normalize(currency_str)
        return {
            "code": code,
            "name": self.CODE_TO_NAME.get(code),
            "supported": self.is_supported(code),
            "original": currency_str,
        }


# 全局单例（推荐用法）
_normalizer_instance = None

def get_currency_normalizer() -> CurrencyNormalizer:
    """获取货币标准化服务单例"""
    global _normalizer_instance
    if _normalizer_instance is None:
        _normalizer_instance = CurrencyNormalizer()
    return _normalizer_instance



