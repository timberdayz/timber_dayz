"""数据校验服务"""

from __future__ import annotations

from typing import Dict, List, Any
import datetime as dt
import re
from decimal import Decimal, InvalidOperation


def _parse_int(v: Any) -> int | None:
    try:
        return int(float(str(v).strip()))
    except Exception:
        return None


def _parse_float(v: Any) -> float | None:
    try:
        return float(str(v).strip())
    except Exception:
        return None


def _validate_core_ownership_fields(row: Dict[str, Any], domain: str) -> List[Dict[str, Any]]:
    """
    验证核心归属字段（DSS架构 - 最小化验证）
    
    [*] v4.6.0 DSS架构原则：
    - 表头字段完全参考源文件的实际表头行
    - PostgreSQL只做数据存储（JSONB格式，保留原始中文表头）
    - 目标：把正确不重复的数据入库到PostgreSQL即可
    - 去重通过data_hash实现，不依赖业务字段名
    
    验证原则：
    - 不进行任何必填字段验证
    - platform_code和shop_id从file_record获取，不需要验证
    - 只验证数据格式（如果字段存在且不为空）
    - 允许空值（PostgreSQL支持NULL）
    
    Args:
        row: 数据行
        domain: 数据域（orders/products/services/traffic/inventory）
    
    Returns:
        错误列表（空列表表示通过验证）
    """
    errors = []
    
    # [*] DSS架构：不进行任何必填字段验证
    # 原因：
    # 1. 数据保留原始中文表头，字段名可能不固定
    # 2. 去重通过data_hash实现，不依赖业务字段名
    # 3. PostgreSQL支持NULL值，允许空值入库
    # 4. platform_code和shop_id从file_record获取，不需要验证
    
    # [*] 只验证数据格式（如果字段存在且不为空）
    # 1. shop_id格式验证（如果存在）
    shop_id = row.get("shop_id")
    if shop_id and str(shop_id).strip() and len(str(shop_id).strip()) < 2:
        errors.append({
            "col": "shop_id",
            "type": "format",
            "msg": "店铺ID长度至少2位"
        })
    
    # 2. 账号格式验证（如果存在）
    account = row.get("account") or row.get("account_id")
    if account and str(account).strip() and len(str(account).strip()) < 2:
        errors.append({
            "col": "account",
            "type": "format",
            "msg": "账号长度至少2位"
        })
    
    # [*] 不再验证日期字段（即使格式错误也不隔离）
    # 原因：日期字段不是主键，格式错误不影响数据入库
    # 日期格式验证可以在数据标准化阶段处理，但不应该导致数据隔离
    
    return errors


def _parse_date(v: Any) -> str | None:
    """
    解析日期字符串（v4.6.1增强 - 支持更多格式）
    
    支持的格式：
    - YYYY-MM-DD
    - YYYY/MM/DD
    - YYYY-MM-DD HH:MM:SS
    - YYYY/MM/DD HH:MM:SS
    - YYYY-MM-DD HH:MM
    - YYYY/MM/DD HH:MM
    - YYYY-MM-DD-HH:MM（Shopee格式）
    - YYYY-MM-DD 0（截断的时间格式，修复为完整格式）
    """
    if v is None:
        return None
    
    s = str(v).strip()
    if not s or s.lower() in ['none', 'null', '暂无数据', '']:
        return None
    
    # [*] v4.6.1修复：处理截断的时间格式（如"2025-09-25 0"）
    # 如果格式是"YYYY-MM-DD 0"或"YYYY-MM-DD 0:0"等，补全为"YYYY-MM-DD 00:00:00"
    if re.match(r'^\d{4}-\d{2}-\d{2}\s+0(?::0)*$', s):
        s = s.split()[0] + ' 00:00:00'
    elif re.match(r'^\d{4}-\d{2}-\d{2}\s+0$', s):
        s = s.split()[0] + ' 00:00:00'
    
    # 支持的日期格式列表（按优先级排序）
    formats = [
        "%Y-%m-%d %H:%M:%S",      # 2025-09-25 10:23:08
        "%Y-%m-%d %H:%M",          # 2025-09-25 10:23
        "%Y-%m-%d",                # 2025-09-25
        "%Y/%m/%d %H:%M:%S",       # 2025/09/25 10:23:08
        "%Y/%m/%d %H:%M",          # 2025/09/25 10:23
        "%Y/%m/%d",                # 2025/09/25
        "%Y-%m-%d-%H:%M",          # 2025-09-25-10:23 (Shopee格式)
    ]
    
    for fmt in formats:
        try:
            parsed = dt.datetime.strptime(s, fmt)
            return parsed.isoformat()
        except Exception:
            continue
    
    # 如果所有格式都失败，尝试使用dateutil（如果可用）
    try:
        from dateutil import parser as date_parser
        parsed = date_parser.parse(s)
        return parsed.isoformat()
    except Exception:
        pass
    
    return None


def _parse_decimal(v: Any) -> Decimal | None:
    """解析金额字段，支持多种格式"""
    try:
        s = str(v).strip()
        # 移除货币符号和千分位分隔符
        s = re.sub(r'[^\d.-]', '', s)
        if s:
            return Decimal(s)
    except (InvalidOperation, ValueError):
        pass
    return None


def _validate_email(email: str) -> bool:
    """验证邮箱格式"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def _validate_phone(phone: str) -> bool:
    """验证手机号格式"""
    pattern = r'^\+?[\d\s\-\(\)]{7,20}$'
    return bool(re.match(pattern, phone))


def _validate_currency(currency: str) -> bool:
    """验证货币代码"""
    valid_currencies = {'USD', 'EUR', 'GBP', 'JPY', 'CNY', 'SGD', 'MYR', 'THB', 'VND', 'IDR', 'PHP', 'BRL', 'MXN', 'CAD', 'AUD'}
    return currency.upper() in valid_currencies


def validate_orders(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    验证订单数据（v4.6.1优化 - 极简验证，只保留警告）
    
    核心原则：
    - [*] v4.6.1优化：orders域不进行任何必填验证，所有数据都允许入库
    - [*] v4.6.1优化：主键字段（platform_code、order_id）会在入库时自动处理
    - [*] v4.6.1优化：所有验证只记录警告，不隔离数据
    - 隔离区只针对真正无法入库的数据（主键字段为空且无法自动生成）
    """
    errors, warnings = [], []
    ok = 0
    
    for idx, r in enumerate(rows):
        # [*] v4.6.1优化：orders域不进行任何必填验证
        # 主键字段会在upsert_orders_v2中自动处理（从file_record提取或生成）
        
        # [*] v4.6.1新增：已取消订单的特殊处理
        # 已取消订单通常缺少采购、付款、发货等信息，这是正常的，不应该报错
        order_status = r.get("order_status") or r.get("订单状态")
        is_cancelled = False
        if order_status:
            cancelled_statuses = ["已取消", "cancelled", "canceled", "取消"]
            if str(order_status).strip() in cancelled_statuses:
                is_cancelled = True
        
        # order_id验证（只警告，不隔离）
        order_id = r.get("order_id")
        if not order_id:
            # [*] v4.6.1新增：已取消订单如果没有order_id，尝试从attributes中提取
            if is_cancelled and r.get("attributes") and isinstance(r.get("attributes"), dict):
                order_id = (
                    r["attributes"].get("订单号") or 
                    r["attributes"].get("订单编号") or
                    r["attributes"].get("order_id")
                )
                if order_id:
                    r["order_id"] = str(order_id)
            
            if not r.get("order_id"):
                warnings.append({
                    "row": idx, 
                    "col": "order_id", 
                    "type": "missing_business_field", 
                    "msg": "订单号缺失（将在入库时自动生成）"
                })
        elif len(str(order_id).strip()) < 3:
            warnings.append({
                "row": idx, 
                "col": "order_id", 
                "type": "format", 
                "msg": "订单号长度至少3位（建议格式）"
            })
        
        # product_id验证（只警告，不隔离）
        # [*] v4.6.1新增：已取消订单可能没有product_id，这是正常的
        product_id = r.get("product_id") or r.get("platform_sku")
        if not product_id:
            # [*] v4.6.1新增：已取消订单如果没有product_id，尝试从attributes中提取
            if is_cancelled and r.get("attributes") and isinstance(r.get("attributes"), dict):
                product_id = (
                    r["attributes"].get("产品ID") or 
                    r["attributes"].get("SKU ID") or
                    r["attributes"].get("platform_sku")
                )
                if product_id:
                    r["product_id"] = str(product_id)
            
            if not r.get("product_id") and not r.get("platform_sku"):
                if is_cancelled:
                    # 已取消订单没有product_id是正常的，只记录警告
                    warnings.append({
                        "row": idx, 
                        "col": "product_id/platform_sku", 
                        "type": "missing_business_field", 
                        "msg": "已取消订单缺少产品ID（这是正常情况）"
                    })
                else:
                    warnings.append({
                        "row": idx, 
                        "col": "product_id/platform_sku", 
                        "type": "missing_business_field", 
                        "msg": "产品ID或SKU缺失（将作为店铺级订单汇总数据入库）"
                    })
        elif len(str(product_id).strip()) < 2:
            warnings.append({
                "row": idx, 
                "col": "product_id/platform_sku", 
                "type": "format", 
                "msg": "产品ID或SKU长度至少2位（建议格式）"
            })
        
        # [*] v4.6.1优化：数值字段验证改为只警告，不隔离
        # 只要有核心归属字段（shop_id、date），就不隔离
        
        # 数量验证（只警告）
        qty = _parse_int(r.get("qty"))
        if qty is None and r.get("qty"):
            warnings.append({"row": idx, "col": "qty", "type": "data_type", "msg": "数量格式可能不正确"})
        elif qty is not None and qty < 0:
            warnings.append({"row": idx, "col": "qty", "type": "range", "msg": "数量为负数，请确认"})
        elif qty is not None and qty > 10000:
            warnings.append({"row": idx, "col": "qty", "type": "range", "msg": "数量超过10000，请确认"})
        
        # 金额验证（只警告）
        total_amount = _parse_decimal(r.get("total_amount"))
        if total_amount is not None:
            if total_amount < 0:
                warnings.append({"row": idx, "col": "total_amount", "type": "range", "msg": "订单金额为负数，请确认"})
            elif total_amount > 1000000:
                warnings.append({"row": idx, "col": "total_amount", "type": "range", "msg": "订单金额超过100万，请确认"})
        
        # 货币验证（只警告）
        currency = r.get("currency")
        if currency and not _validate_currency(currency):
            warnings.append({"row": idx, "col": "currency", "type": "format", "msg": f"不支持的货币代码: {currency}"})
        
        # 日期合理性检查（只警告，不隔离）
        order_date = _parse_date(r.get("order_ts")) or _parse_date(r.get("order_date"))
        if order_date:
            try:
                order_dt = dt.datetime.fromisoformat(order_date)
                if order_dt > dt.datetime.now():
                    warnings.append({"row": idx, "col": "order_ts", "type": "date", "msg": "订单日期为未来时间"})
                elif order_dt < dt.datetime.now() - dt.timedelta(days=365*2):
                    warnings.append({"row": idx, "col": "order_ts", "type": "date", "msg": "订单日期超过2年"})
            except Exception:
                pass
        
        # 买家信息验证（只警告）
        buyer_id = r.get("buyer_id")
        if buyer_id and len(str(buyer_id).strip()) < 2:
            warnings.append({"row": idx, "col": "buyer_id", "type": "format", "msg": "买家ID长度至少2位"})
        
        # 状态验证（只警告）
        order_status = r.get("order_status")
        valid_statuses = {'pending', 'paid', 'shipped', 'delivered', 'cancelled', 'returned'}
        if order_status and order_status.lower() not in valid_statuses:
            warnings.append({"row": idx, "col": "order_status", "type": "format", "msg": f"订单状态可能不正确: {order_status}"})
        
        # [*] v4.6.1优化：不添加任何错误，所有数据都允许入库
        # 主键字段会在upsert_orders_v2中自动处理
        
        # 统计通过的行（所有行都通过）
        ok += 1

    return {"errors": errors, "warnings": warnings, "ok_rows": ok, "total": len(rows)}


def validate_services(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    验证服务/运营数据（DSS架构 - 最小化验证）
    
    [*] v4.6.0 DSS架构原则：
    - 表头字段完全参考源文件的实际表头行
    - PostgreSQL只做数据存储（JSONB格式，保留原始中文表头）
    - 目标：把正确不重复的数据入库到PostgreSQL即可
    - 去重通过data_hash实现，不依赖业务字段名
    
    验证原则：
    - 只验证数据格式（日期、数字等）
    - 不强制标准字段名
    - 允许空值（PostgreSQL支持NULL）
    - 数据去重通过data_hash实现
    """
    errors, warnings = [], []
    ok = 0
    
    for idx, r in enumerate(rows):
        row_errors = []
        
        # [*] DSS架构：不进行任何必填字段验证
        # 只验证数据格式（如果字段存在且不为空）
        
        # 1. 日期格式验证（如果存在）
        date_fields = [
            'metric_date', 'date', 'service_date', '日期', '时间', '统计日期'
        ]
        
        for field in date_fields:
            value = r.get(field)
            if value is not None and str(value).strip():
                parsed_date = _parse_date(value)
                if not parsed_date:
                    row_errors.append({
                        "col": field,
                        "type": "data_type",
                        "msg": f"{field}格式不正确（应为日期格式）"
                    })
                else:
                    # 日期合理性检查（只警告，不隔离）
                    try:
                        metric_dt = dt.datetime.fromisoformat(parsed_date)
                        if metric_dt > dt.datetime.now():
                            warnings.append({
                                "row": idx,
                                "col": field,
                                "type": "date",
                                "msg": "指标日期为未来时间"
                            })
                        elif metric_dt < dt.datetime.now() - dt.timedelta(days=365*3):
                            warnings.append({
                                "row": idx,
                                "col": field,
                                "type": "date",
                                "msg": "指标日期超过3年"
                            })
                    except Exception:
                        pass
        
        # 2. 数值字段格式验证（如果存在，支持中英文字段名）
        numeric_fields = [
            'amount', 'quantity', 'count',
            # 中文字段名
            '金额', '数量', '次数'
        ]
        
        for field in numeric_fields:
            value = r.get(field)
            if value is not None and str(value).strip():
                parsed_val = _parse_decimal(value)
                if parsed_val is None:
                    row_errors.append({
                        "col": field,
                        "type": "data_type",
                        "msg": f"{field}必须为数字"
                    })
                elif parsed_val < 0:
                    row_errors.append({
                        "col": field,
                        "type": "range",
                        "msg": f"{field}不能为负数"
                    })
        
        # 添加行错误
        for error in row_errors:
            error["row"] = idx
            errors.append(error)
        
        # 统计通过的行
        if not row_errors:
            ok += 1
    
    return {"errors": errors, "warnings": warnings, "ok_rows": ok, "total": len(rows)}


def validate_traffic(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    验证流量数据（DSS架构 - 最小化验证）
    
    [*] v4.6.0 DSS架构原则：
    - 表头字段完全参考源文件的实际表头行
    - PostgreSQL只做数据存储（JSONB格式，保留原始中文表头）
    - 目标：把正确不重复的数据入库到PostgreSQL即可
    - 去重通过data_hash实现，不依赖业务字段名
    
    验证原则：
    - 只验证数据格式（日期、数字等）
    - 不强制标准字段名
    - 允许空值（PostgreSQL支持NULL）
    - 数据去重通过data_hash实现
    """
    errors, warnings = [], []
    ok = 0
    
    for idx, r in enumerate(rows):
        row_errors = []
        
        # [*] DSS架构：不进行任何必填字段验证
        # 只验证数据格式（如果字段存在且不为空）
        
        # 1. 日期格式验证（如果存在）
        date_fields = [
            'metric_date', 'date', '日期', '时间', '统计日期'
        ]
        
        for field in date_fields:
            value = r.get(field)
            if value is not None and str(value).strip():
                parsed_date = _parse_date(value)
                if not parsed_date:
                    row_errors.append({
                        "col": field,
                        "type": "data_type",
                        "msg": f"{field}格式不正确（应为日期格式）"
                    })
                else:
                    # 日期合理性检查（只警告，不隔离）
                    try:
                        metric_dt = dt.datetime.fromisoformat(parsed_date)
                        if metric_dt > dt.datetime.now():
                            warnings.append({
                                "row": idx,
                                "col": field,
                                "type": "date",
                                "msg": "指标日期为未来时间"
                            })
                        elif metric_dt < dt.datetime.now() - dt.timedelta(days=365*3):
                            warnings.append({
                                "row": idx,
                                "col": field,
                                "type": "date",
                                "msg": "指标日期超过3年"
                            })
                    except Exception:
                        pass
        
        # 2. 数值字段格式验证（如果存在，支持中英文字段名）
        numeric_fields = [
            'page_views', 'unique_visitors', 'order_count', 'click_count',
            # 中文字段名
            '浏览量', '访客数', '订单数', '点击量'
        ]
        
        for field in numeric_fields:
            value = r.get(field)
            if value is not None and str(value).strip():
                parsed_val = _parse_int(value)
                if parsed_val is None:
                    row_errors.append({
                        "col": field,
                        "type": "data_type",
                        "msg": f"{field}必须为整数"
                    })
                elif parsed_val < 0:
                    row_errors.append({
                        "col": field,
                        "type": "range",
                        "msg": f"{field}不能为负数"
                    })
        
        # 添加行错误
        for error in row_errors:
            error["row"] = idx
            errors.append(error)
        
        # 统计通过的行
        if not row_errors:
            ok += 1
    
    return {"errors": errors, "warnings": warnings, "ok_rows": ok, "total": len(rows)}


def validate_analytics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    验证分析数据（DSS架构 - 最小化验证）
    
    [*] v4.6.0 DSS架构原则：
    - 表头字段完全参考源文件的实际表头行
    - PostgreSQL只做数据存储（JSONB格式，保留原始中文表头）
    - 目标：把正确不重复的数据入库到PostgreSQL即可
    - 去重通过data_hash实现，不依赖业务字段名
    
    验证原则：
    - 只验证数据格式（日期、数字等）
    - 不强制标准字段名
    - 允许空值（PostgreSQL支持NULL）
    - 数据去重通过data_hash实现
    """
    errors, warnings = [], []
    ok = 0
    
    for idx, r in enumerate(rows):
        row_errors = []
        
        # [*] DSS架构：不进行任何必填字段验证
        # 只验证数据格式（如果字段存在且不为空）
        
        # 1. 日期格式验证（如果存在）
        date_fields = [
            'metric_date', 'date', '日期', '时间', '统计日期'
        ]
        
        for field in date_fields:
            value = r.get(field)
            if value is not None and str(value).strip():
                parsed_date = _parse_date(value)
                if not parsed_date:
                    row_errors.append({
                        "col": field,
                        "type": "data_type",
                        "msg": f"{field}格式不正确（应为日期格式）"
                    })
                else:
                    # 日期合理性检查（只警告，不隔离）
                    try:
                        metric_dt = dt.datetime.fromisoformat(parsed_date)
                        if metric_dt > dt.datetime.now():
                            warnings.append({
                                "row": idx,
                                "col": field,
                                "type": "date",
                                "msg": "指标日期为未来时间"
                            })
                        elif metric_dt < dt.datetime.now() - dt.timedelta(days=365*3):
                            warnings.append({
                                "row": idx,
                                "col": field,
                                "type": "date",
                                "msg": "指标日期超过3年"
                            })
                    except Exception:
                        pass
        
        # 2. 数值字段格式验证（如果存在，支持中英文字段名）
        numeric_fields = [
            'conversion_rate', 'click_rate', 'bounce_rate',
            # 中文字段名
            '转化率', '点击率', '跳出率'
        ]
        
        for field in numeric_fields:
            value = r.get(field)
            if value is not None and str(value).strip():
                parsed_val = _parse_float(value)
                if parsed_val is None:
                    row_errors.append({
                        "col": field,
                        "type": "data_type",
                        "msg": f"{field}必须为数字"
                    })
                elif parsed_val < 0 or parsed_val > 100:
                    # 比率字段应该在0-100之间
                    row_errors.append({
                        "col": field,
                        "type": "range",
                        "msg": f"{field}应该在0-100之间"
                    })
        
        # 添加行错误
        for error in row_errors:
            error["row"] = idx
            errors.append(error)
        
        # 统计通过的行
        if not row_errors:
            ok += 1
    
    return {"errors": errors, "warnings": warnings, "ok_rows": ok, "total": len(rows)}


def validate_product_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    验证产品指标数据（DSS架构 - 最小化验证）
    
    [*] v4.6.0 DSS架构原则：
    - 表头字段完全参考源文件的实际表头行
    - PostgreSQL只做数据存储（JSONB格式，保留原始中文表头）
    - 目标：把正确不重复的数据入库到PostgreSQL即可
    - 去重通过data_hash实现，不依赖业务字段名
    
    验证原则：
    - 只验证数据格式（日期、数字等）
    - 不强制标准字段名（不再要求product_id、platform_sku等）
    - 允许空值（PostgreSQL支持NULL）
    - 数据去重通过data_hash实现
    """
    errors, warnings = [], []
    ok = 0
    
    for idx, r in enumerate(rows):
        row_errors = []
        
        # [*] DSS架构：不进行任何必填字段验证
        # 只验证数据格式（如果字段存在且不为空）
        
        # 1. 日期格式验证（如果存在）
        date_fields = [
            'metric_date', 'date', '日期', '时间', '统计日期'
        ]
        
        for field in date_fields:
            value = r.get(field)
            if value is not None and str(value).strip():
                parsed_date = _parse_date(value)
                if not parsed_date:
                    row_errors.append({
                        "col": field,
                        "type": "data_type",
                        "msg": f"{field}格式不正确（应为日期格式）"
                    })
                else:
                    # 日期合理性检查（只警告，不隔离）
                    try:
                        metric_dt = dt.datetime.fromisoformat(parsed_date)
                        if metric_dt > dt.datetime.now():
                            warnings.append({
                                "row": idx,
                                "col": field,
                                "type": "date",
                                "msg": "指标日期为未来时间"
                            })
                        elif metric_dt < dt.datetime.now() - dt.timedelta(days=365*3):
                            warnings.append({
                                "row": idx,
                                "col": field,
                                "type": "date",
                                "msg": "指标日期超过3年"
                            })
                    except Exception:
                        pass
        
        # 2. 数值字段格式验证（如果存在，支持中英文字段名）
        numeric_fields = [
            'sales_amount', 'sales_volume', 'page_views', 'unique_visitors',
            'click_rate', 'conversion_rate', 'rating',
            # 中文字段名
            '销售额', '销量', '浏览量', '访客数', '点击率', '转化率', '评分'
        ]
        
        for field in numeric_fields:
            value = r.get(field)
            if value is not None and str(value).strip():
                # 尝试解析为数字
                parsed_val = _parse_float(value)
                if parsed_val is None:
                    row_errors.append({
                        "col": field,
                        "type": "data_type",
                        "msg": f"{field}必须为数字"
                    })
                elif parsed_val < 0 and field not in ['click_rate', 'conversion_rate']:
                    # 点击率和转化率可能为0，但不应该为负数
                    row_errors.append({
                        "col": field,
                        "type": "range",
                        "msg": f"{field}不能为负数"
                    })
        
        # 添加行错误
        for error in row_errors:
            error["row"] = idx
            errors.append(error)
        
        # 统计通过的行
        if not row_errors:
            ok += 1
    
    return {"errors": errors, "warnings": warnings, "ok_rows": ok, "total": len(rows)}


