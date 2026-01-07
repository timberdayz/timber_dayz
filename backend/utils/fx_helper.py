#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FX转换辅助函数（同步版本）

用于在同步函数中快速进行货币转换
从dim_exchange_rates表查询汇率
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from modules.core.db import DimExchangeRate
from modules.core.logger import get_logger

logger = get_logger(__name__)


def simple_convert_to_cny(
    amount: Optional[float],
    from_currency: str,
    rate_date: date,
    db: Session
) -> Decimal:
    """
    简化的CNY转换（同步版本）
    
    参数:
        amount: 原币金额
        from_currency: 原币种（如USD、SGD）
        rate_date: 汇率日期
        db: 数据库会话
    
    返回:
        CNY金额
    
    示例:
        cny_amount = simple_convert_to_cny(100.0, 'USD', date.today(), db)
    """
    if amount is None or amount == 0:
        return Decimal('0')
    
    # 标准化货币代码
    from_currency = from_currency.upper().strip()
    
    # 如果已经是CNY，直接返回
    if from_currency == 'CNY':
        return Decimal(str(amount))
    
    try:
        # 查询最近的汇率（<=rate_date的最新汇率）
        rate_record = db.execute(
            select(DimExchangeRate).where(
                and_(
                    DimExchangeRate.from_currency == from_currency,
                    DimExchangeRate.to_currency == 'CNY',
                    DimExchangeRate.rate_date <= rate_date
                )
            ).order_by(DimExchangeRate.rate_date.desc()).limit(1)
        ).scalar_one_or_none()
        
        if rate_record:
            # 使用查询到的汇率转换
            rate = Decimal(str(rate_record.rate))
            cny_amount = Decimal(str(amount)) * rate
            logger.debug(f"FX转换: {amount} {from_currency} = {cny_amount} CNY (rate: {rate})")
            return round(cny_amount, 2)
        else:
            # 找不到汇率，记录警告
            logger.warning(
                f"汇率未找到: {from_currency} -> CNY on {rate_date}, "
                f"返回原值 {amount}"
            )
            # 返回原值（作为降级策略）
            return Decimal(str(amount))
    
    except Exception as e:
        logger.error(f"FX转换失败: {e}, amount={amount}, currency={from_currency}")
        return Decimal(str(amount))


def get_exchange_rate(
    from_currency: str,
    to_currency: str,
    rate_date: date,
    db: Session
) -> Optional[Decimal]:
    """
    获取汇率
    
    参数:
        from_currency: 原币种
        to_currency: 目标币种
        rate_date: 汇率日期
        db: 数据库会话
    
    返回:
        汇率（Decimal）或None
    """
    try:
        rate_record = db.execute(
            select(DimExchangeRate).where(
                and_(
                    DimExchangeRate.from_currency == from_currency.upper(),
                    DimExchangeRate.to_currency == to_currency.upper(),
                    DimExchangeRate.rate_date <= rate_date
                )
            ).order_by(DimExchangeRate.rate_date.desc()).limit(1)
        ).scalar_one_or_none()
        
        if rate_record:
            return Decimal(str(rate_record.rate))
        else:
            return None
    
    except Exception as e:
        logger.error(f"获取汇率失败: {e}")
        return None

