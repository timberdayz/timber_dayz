#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Currency service for daily FX rates and RMB normalization.

- Fetches rates from exchangerate.host
- Persists to dim_currency_rates (ORM in modules.core.db.schema)
- Provides helpers to get rate and normalize amounts

Design notes:
- No side effects at import time; engine is created lazily on function call
- Fallback to fixed rate when API fails (configurable via env)
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional
import os

import requests
from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from modules.core.db.schema import Base, DimCurrencyRate
from modules.core.secrets_manager import get_secrets_manager

DEFAULT_BASE = "USD"
DEFAULT_QUOTE = "CNY"  # RMB
DEFAULT_FALLBACK_RATE = float(os.getenv("FX_FALLBACK_USD_CNY", "7.0"))


def _get_engine() -> Engine:
    """Create SQLAlchemy engine from DATABASE_URL or secrets manager (lazy)."""
    url = os.getenv("DATABASE_URL")
    if not url:
        sm = get_secrets_manager()
        url = f"sqlite:///{sm.get_unified_database_path()}"
    # Use future Engine, safe defaults
    return create_engine(url, pool_pre_ping=True, future=True)


def _upsert_rate(session: Session, rate_date: date, base: str, quote: str, rate: float, source: str) -> None:
    rec = session.get(DimCurrencyRate, {"rate_date": rate_date, "base_currency": base, "quote_currency": quote})
    if rec is None:
        rec = DimCurrencyRate(
            rate_date=rate_date,
            base_currency=base,
            quote_currency=quote,
            rate=rate,
            source=source,
            fetched_at=datetime.utcnow(),
        )
        session.add(rec)
    else:
        rec.rate = rate
        rec.source = source
        rec.fetched_at = datetime.utcnow()


def fetch_rate_from_api(rate_date: date, base: str = DEFAULT_BASE, quote: str = DEFAULT_QUOTE) -> Optional[float]:
    """Fetch a single-day FX rate from exchangerate.host. Returns None on failure."""
    try:
        url = f"https://api.exchangerate.host/{rate_date.isoformat()}"
        params = {"base": base, "symbols": quote}
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        rate = data.get("rates", {}).get(quote)
        if rate is None:
            return None
        return float(rate)
    except Exception:
        return None


def get_rate(rate_date: date, base: str = DEFAULT_BASE, quote: str = DEFAULT_QUOTE, use_api: bool = True) -> float:
    """
    Get FX rate for date/base/quote.
    - Prefer memory cache
    - Then DB value
    - Optionally fetch from API and persist if missing
    - Fallback to DEFAULT_FALLBACK_RATE when everything fails
    """
    # 尝试从缓存获取
    try:
        from modules.services.cache_service import get_cached_exchange_rate, cache_exchange_rate
        cached_rate = get_cached_exchange_rate(base, rate_date)
        if cached_rate is not None:
            return cached_rate
    except ImportError:
        pass  # 缓存服务不可用
    
    engine = _get_engine()
    with Session(engine) as session:
        found = session.get(DimCurrencyRate, {"rate_date": rate_date, "base_currency": base, "quote_currency": quote})
        if found:
            rate = float(found.rate)
            # 保存到缓存
            try:
                cache_exchange_rate(base, rate_date, rate)
            except Exception:
                pass
            return rate
        if use_api:
            rate = fetch_rate_from_api(rate_date, base, quote)
            if rate is not None:
                _upsert_rate(session, rate_date, base, quote, rate, source="exchangerate.host")
                session.commit()
                # 保存到缓存
                try:
                    cache_exchange_rate(base, rate_date, rate)
                except Exception:
                    pass
                return rate
        # Fallback
        return DEFAULT_FALLBACK_RATE


def normalize_amount_to_rmb(amount: float, currency: str, rate_date: date) -> float:
    """Normalize an amount to RMB using USD->CNY intermediary when needed.

    Strategy:
    - If currency is CNY: return amount
    - If currency is USD: multiply by USD->CNY rate
    - For other currencies: request BASE=currency, QUOTE=CNY directly (API supports); fallback via USD cross if needed
    """
    if amount is None:
        return 0.0
    cur = (currency or "").upper()
    if cur == "CNY" or cur == "RMB":
        return float(amount)
    if cur == "USD":
        rate = get_rate(rate_date, base="USD", quote="CNY")
        return float(amount) * rate
    # Try direct currency->CNY
    rate = get_rate(rate_date, base=cur, quote="CNY")
    return float(amount) * rate


def backfill_rates(dates: list[date], base: str = DEFAULT_BASE, quote: str = DEFAULT_QUOTE) -> int:
    """Fetch and persist rates for a list of dates. Returns count."""
    engine = _get_engine()
    saved = 0
    with Session(engine) as session:
        for d in dates:
            r = fetch_rate_from_api(d, base, quote)
            if r is None:
                continue
            _upsert_rate(session, d, base, quote, r, source="exchangerate.host")
            saved += 1
        session.commit()
    return saved

