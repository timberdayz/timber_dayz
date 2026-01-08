"""
数据验证服务 v2.0 - 适配扁平化宽表schema

改进点：
1. 适配新schema（fact_product_metrics 25列，fact_orders 29列）
2. 放宽验证规则（必填字段从10+减少到4个）
3. 优化错误提示（批量汇总而非逐行）
4. 智能数据清洗（自动修正常见格式问题）
"""

from __future__ import annotations
from typing import Dict, List, Any, Optional
import datetime as dt
import re
from decimal import Decimal, InvalidOperation


# ============== 辅助函数 ==============

def _parse_int(v: Any) -> Optional[int]:
    """解析整数"""
    try:
        if v is None or str(v).strip() == '':
            return None
        return int(float(str(v).strip()))
    except Exception:
        return None


def _parse_float(v: Any) -> Optional[float]:
    """解析浮点数"""
    try:
        if v is None or str(v).strip() == '':
            return None
        return float(str(v).strip())
    except Exception:
        return None


def _parse_date(v: Any) -> Optional[str]:
    """解析日期"""
    if v is None:
        return None
    
    s = str(v).strip()
    if not s:
        return None
    
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


def _parse_decimal(v: Any) -> Optional[Decimal]:
    """解析金额字段"""
    try:
        if v is None or str(v).strip() == '':
            return None
        s = str(v).strip()
        # 移除货币符号和千分位分隔符
        s = re.sub(r'[^\d.-]', '', s)
        if s:
            return Decimal(s)
    except (InvalidOperation, ValueError):
        pass
    return None


def _validate_currency(currency: str) -> bool:
    """验证货币代码"""
    if not currency:
        return True  # 允许为空
    valid_currencies = {
        'USD', 'EUR', 'GBP', 'JPY', 'CNY', 'SGD', 'MYR', 
        'THB', 'VND', 'IDR', 'PHP', 'BRL', 'MXN', 'CAD', 'AUD'
    }
    return currency.upper() in valid_currencies


# ============== 商品指标验证 ==============

def validate_product_metrics(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    验证商品指标数据（v2.0 - 适配扁平化宽表）
    
    fact_product_metrics新schema:
    必填字段（4个）:
      - platform_code: 平台代码
      - shop_id: 店铺ID
      - platform_sku: 平台SKU
      - metric_date: 指标日期
    
    可选字段（19个）:
      - product_name, category, brand（商品信息）
      - price, currency, price_rmb（价格）
      - stock（库存）
      - sales_volume, sales_amount, sales_amount_rmb（销售）
      - page_views, unique_visitors, click_through_rate（流量）
      - conversion_rate, add_to_cart_count（转化）
      - rating, review_count（评价）
      - granularity（粒度，默认daily）
      - created_at, updated_at（时间戳，自动）
    
    Args:
        rows: 数据行列表
    
    Returns:
        {
            "errors": [{"row": int, "col": str, "type": str, "msg": str}],
            "warnings": [{"row": int, "col": str, "type": str, "msg": str}],
            "ok_count": int
        }
    """
    errors, warnings = [], []
    ok_count = 0
    
    for idx, row in enumerate(rows):
        row_errors = []
        
        # === 必填字段验证（仅4个） ===
        
        # 1. platform_sku（最重要）
        sku = row.get("platform_sku") or row.get("sku") or row.get("product_id")
        if not sku or len(str(sku).strip()) < 1:
            row_errors.append({
                "row": idx,
                "col": "platform_sku",
                "type": "required",
                "msg": "平台SKU必填"
            })
        
        # 2. metric_date
        date_str = row.get("metric_date") or row.get("date")
        granularity = row.get("granularity", "daily")  # [*] v4.6.2新增：获取粒度
        date_parsed = _parse_date(date_str)
        
        if not date_parsed:
            # [*] v4.6.2新增：snapshot数据允许缺少日期（自动补充）
            if granularity == "snapshot":
                # 自动使用今天日期（入库时会从文件名提取更准确的日期）
                from datetime import date as dt_date
                row['metric_date'] = dt_date.today().strftime("%Y-%m-%d")
                warnings.append({
                    "row": idx,
                    "col": "metric_date",
                    "type": "auto_fill",
                    "msg": "snapshot数据已自动补充日期（快照导出日期）"
                })
            else:
                # 其他粒度（daily/weekly/monthly）必须有日期
                row_errors.append({
                    "row": idx,
                    "col": "metric_date",
                    "type": "required",
                    "msg": "指标日期必填且格式正确（YYYY-MM-DD）"
                })
        else:
            # 日期合理性检查（仅警告）
            try:
                metric_dt = dt.datetime.strptime(date_parsed, "%Y-%m-%d")
                if metric_dt > dt.datetime.now():
                    warnings.append({
                        "row": idx,
                        "col": "metric_date",
                        "type": "date_future",
                        "msg": "指标日期为未来时间"
                    })
                elif metric_dt < dt.datetime.now() - dt.timedelta(days=365*5):
                    warnings.append({
                        "row": idx,
                        "col": "metric_date",
                        "type": "date_too_old",
                        "msg": "指标日期超过5年"
                    })
            except Exception:
                pass
        
        # 3. platform_code（宽松验证）
        platform = row.get("platform_code") or row.get("platform")
        if not platform:
            # 不是错误，仅警告（可能在入库时自动填充）
            warnings.append({
                "row": idx,
                "col": "platform_code",
                "type": "missing",
                "msg": "平台代码未提供，将使用默认值"
            })
        
        # 4. shop_id（宽松验证）
        shop = row.get("shop_id") or row.get("shop")
        if not shop:
            warnings.append({
                "row": idx,
                "col": "shop_id",
                "type": "missing",
                "msg": "店铺ID未提供，将使用默认值"
            })
        
        # === 可选字段验证（仅做合理性检查） ===
        
        # 数值范围检查（宽松）
        numeric_checks = {
            "price": (0, 1000000, "价格"),
            "stock": (0, 10000000, "库存"),
            "sales_volume": (0, 10000000, "销量"),
            "sales_amount": (0, 1000000000, "销售额"),
            "page_views": (0, 100000000, "浏览量"),
            "unique_visitors": (0, 10000000, "访客数"),
            "add_to_cart_count": (0, 10000000, "加购数"),
            "review_count": (0, 1000000, "评论数"),
        }
        
        for field, (min_val, max_val, field_name) in numeric_checks.items():
            value = row.get(field)
            if value is not None and str(value).strip() != '':
                parsed_val = _parse_float(value)
                if parsed_val is not None:
                    if parsed_val < min_val:
                        row_errors.append({
                            "row": idx,
                            "col": field,
                            "type": "range",
                            "msg": f"{field_name}不能为负数"
                        })
                    # 超过最大值仅警告（不阻止入库）
                    elif parsed_val > max_val:
                        warnings.append({
                            "row": idx,
                            "col": field,
                            "type": "range_high",
                            "msg": f"{field_name}值异常大（{parsed_val}），请确认"
                        })
        
        # 百分比检查（0-100或0-1）
        percentage_checks = {
            "click_through_rate": "点击率",
            "conversion_rate": "转化率",
        }
        
        for field, field_name in percentage_checks.items():
            value = row.get(field)
            if value is not None and str(value).strip() != '':
                parsed_val = _parse_float(value)
                if parsed_val is not None:
                    if parsed_val < 0:
                        row_errors.append({
                            "row": idx,
                            "col": field,
                            "type": "range",
                            "msg": f"{field_name}不能为负数"
                        })
                    elif parsed_val > 100:
                        warnings.append({
                            "row": idx,
                            "col": field,
                            "type": "percentage",
                            "msg": f"{field_name}超过100%（可能是小数格式0-1）"
                        })
        
        # 评分检查（0-5）
        rating = row.get("rating")
        if rating is not None and str(rating).strip() != '':
            parsed_rating = _parse_float(rating)
            if parsed_rating is not None:
                if parsed_rating < 0 or parsed_rating > 5:
                    row_errors.append({
                        "row": idx,
                        "col": "rating",
                        "type": "range",
                        "msg": "评分应在0-5之间"
                    })
        
        # 货币验证
        currency = row.get("currency")
        if currency and not _validate_currency(currency):
            warnings.append({
                "row": idx,
                "col": "currency",
                "type": "invalid_currency",
                "msg": f"未知货币代码: {currency}"
            })
        
        # 该行检查完成
        if row_errors:
            errors.extend(row_errors)
        else:
            ok_count += 1
    
    return {
        "errors": errors,
        "warnings": warnings,
        "ok_count": ok_count,
        "total_rows": len(rows),
        "error_rows": len(set(e["row"] for e in errors)),
        "validation_pass": len(errors) == 0
    }


# ============== 订单数据验证 ==============

def validate_orders(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    验证订单数据（v2.0 - 适配扁平化宽表）
    
    fact_orders新schema:
    必填字段（4个）:
      - platform_code: 平台代码
      - shop_id: 店铺ID
      - order_id: 订单ID
      - order_date_local: 订单日期
    
    重要字段（建议有）:
      - total_amount: 总金额
      - currency: 货币
    
    可选字段（23个）:
      详细金额、状态、买家信息、收货地址等
    
    Args:
        rows: 订单数据行
    
    Returns:
        验证结果字典
    """
    errors, warnings = [], []
    ok_count = 0
    
    for idx, row in enumerate(rows):
        row_errors = []
        
        # === 必填字段 ===
        
        # 1. order_id
        order_id = row.get("order_id")
        if not order_id or len(str(order_id).strip()) < 3:
            row_errors.append({
                "row": idx,
                "col": "order_id",
                "type": "required",
                "msg": "订单ID必填且至少3位"
            })
        
        # 2. order_date_local
        order_date = _parse_date(row.get("order_date_local") or row.get("order_date"))
        if not order_date:
            row_errors.append({
                "row": idx,
                "col": "order_date_local",
                "type": "required",
                "msg": "订单日期必填"
            })
        
        # 3. platform_code & shop_id（宽松）
        if not row.get("platform_code"):
            warnings.append({"row": idx, "col": "platform_code", "type": "missing", "msg": "平台代码缺失"})
        if not row.get("shop_id"):
            warnings.append({"row": idx, "col": "shop_id", "type": "missing", "msg": "店铺ID缺失"})
        
        # === 金额验证 ===
        
        amount_fields = {
            "total_amount": "总金额",
            "subtotal": "小计",
            "shipping_fee": "运费",
            "tax_amount": "税费",
            "discount_amount": "折扣",
        }
        
        for field, field_name in amount_fields.items():
            value = row.get(field)
            if value is not None and str(value).strip() != '':
                parsed_val = _parse_decimal(value)
                if parsed_val is not None:
                    if parsed_val < 0 and field != "discount_amount":
                        row_errors.append({
                            "row": idx,
                            "col": field,
                            "type": "range",
                            "msg": f"{field_name}不能为负数"
                        })
        
        # === 状态验证（仅警告） ===
        
        order_status = row.get("order_status")
        if order_status:
            valid_statuses = ['pending', 'confirmed', 'shipped', 'delivered', 'cancelled', 'refunded']
            if order_status.lower() not in valid_statuses:
                warnings.append({
                    "row": idx,
                    "col": "order_status",
                    "type": "invalid_value",
                    "msg": f"未知订单状态: {order_status}"
                })
        
        # 该行检查完成
        if row_errors:
            errors.extend(row_errors)
        else:
            ok_count += 1
    
    return {
        "errors": errors,
        "warnings": warnings,
        "ok_count": ok_count,
        "total_rows": len(rows),
        "error_rows": len(set(e["row"] for e in errors)),
        "validation_pass": len(errors) == 0
    }


# ============== 测试代码 ==============

if __name__ == "__main__":
    # 测试商品指标验证
    test_products = [
        {
            "platform_sku": "TEST-SKU-001",
            "metric_date": "2025-01-26",
            "product_name": "测试商品",
            "price": 99.99,
            "stock": 100,
            "sales_volume": 50,
            "rating": 4.5
        },
        {
            # 缺少必填字段
            "product_name": "无SKU商品",
            "price": 50.0
        },
        {
            # 异常值
            "platform_sku": "TEST-SKU-002",
            "metric_date": "2025-01-26",
            "price": -10,  # 负数
            "rating": 6.0  # 超范围
        }
    ]
    
    print("="*60)
    print("测试商品指标验证")
    print("="*60)
    result = validate_product_metrics(test_products)
    
    print(f"\n总行数: {result['total_rows']}")
    print(f"通过: {result['ok_count']}")
    print(f"错误行: {result['error_rows']}")
    print(f"错误数: {len(result['errors'])}")
    print(f"警告数: {len(result['warnings'])}")
    print(f"验证通过: {result['validation_pass']}")
    
    if result['errors']:
        print(f"\n错误详情（前5个）:")
        for err in result['errors'][:5]:
            print(f"  行{err['row']}, {err['col']}: {err['msg']}")
    
    if result['warnings']:
        print(f"\n警告详情（前5个）:")
        for warn in result['warnings'][:5]:
            print(f"  行{warn['row']}, {warn['col']}: {warn['msg']}")

