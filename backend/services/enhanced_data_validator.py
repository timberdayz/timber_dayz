"""
增强数据验证服务 - 支持库存、财务和订单关联验证
"""

from typing import Dict, List, Any
import datetime as dt
import re
from decimal import Decimal, InvalidOperation
from backend.services.data_validator import _parse_int, _parse_float, _parse_date, _parse_decimal


def validate_inventory(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    验证库存数据（DSS架构 - 最小化验证）
    
    ⭐ v4.6.0 DSS架构原则：
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
        
        # ⭐ DSS架构：不再验证必填字段（product_id、platform_sku等）
        # 原因：
        # 1. 数据保留原始中文表头，字段名可能不固定
        # 2. 去重通过data_hash实现，不依赖业务字段名
        # 3. PostgreSQL支持NULL值，允许空值入库
        # 4. platform_code和shop_id从file_record获取，不需要验证
        
        # ⭐ 只验证数据格式（如果字段存在且不为空）
        # 1. 数值字段格式验证（支持中英文字段名）
        numeric_int_fields = [
            # 英文字段名
            'quantity_on_hand', 'quantity_available', 'quantity_reserved',
            'quantity_incoming', 'safety_stock', 'reorder_point',
            # 中文字段名
            '实际库存', '可用库存', '预留库存', '在途库存',
            '安全库存', '补货点', '库存数量', '数量'
        ]
        
        numeric_decimal_fields = [
            # 英文字段名
            'avg_cost', 'total_value', 'cost', 'price',
            # 中文字段名
            '平均成本', '库存总价值', '成本', '价格', '单价'
        ]
        
        # 整数字段验证
        for field in numeric_int_fields:
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
                elif parsed_val > 10000000:
                    warnings.append({
                        "row": idx,
                        "col": field,
                        "type": "range",
                        "msg": f"{field}超过10000000，请确认"
                    })
        
        # 小数字段验证
        for field in numeric_decimal_fields:
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
                elif parsed_val > 100000000:
                    warnings.append({
                        "row": idx,
                        "col": field,
                        "type": "range",
                        "msg": f"{field}超过100000000，请确认"
                    })
        
        # 2. 日期字段格式验证（如果存在）
        date_fields = [
            'metric_date', 'date', '日期', '时间', '统计日期', '库存日期'
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
        
        # 3. 库存逻辑验证（如果相关字段都存在）
        # 尝试多种字段名（中英文）
        qty_on_hand = (
            _parse_int(r.get("quantity_on_hand")) or
            _parse_int(r.get("实际库存")) or
            _parse_int(r.get("库存数量")) or
            0
        )
        qty_available = (
            _parse_int(r.get("quantity_available")) or
            _parse_int(r.get("可用库存")) or
            0
        )
        qty_reserved = (
            _parse_int(r.get("quantity_reserved")) or
            _parse_int(r.get("预留库存")) or
            0
        )
        
        if qty_on_hand is not None and qty_available is not None and qty_reserved is not None:
            if qty_available > qty_on_hand:
                row_errors.append({
                    "col": "quantity_available",
                    "type": "logic",
                    "msg": "可用库存不能大于实际库存"
                })
            if qty_reserved > qty_on_hand:
                row_errors.append({
                    "col": "quantity_reserved",
                    "type": "logic",
                    "msg": "预留库存不能大于实际库存"
                })
            if qty_available + qty_reserved > qty_on_hand:
                warnings.append({
                    "row": idx,
                    "col": "quantity_available",
                    "type": "logic",
                    "msg": "可用库存+预留库存不应大于实际库存"
                })
        
        # 添加行错误
        for error in row_errors:
            error["row"] = idx
            errors.append(error)
        
        # 统计通过的行
        if not row_errors:
            ok += 1
    
    return {"errors": errors, "warnings": warnings, "ok_rows": ok, "total": len(rows)}


def validate_finance(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """验证财务数据"""
    errors, warnings = [], []
    ok = 0
    
    for idx, r in enumerate(rows):
        row_errors = []
        
        # 必填字段验证
        platform_code = r.get("platform_code")
        shop_id = r.get("shop_id")
        
        if not platform_code:
            row_errors.append({"col": "platform_code", "type": "required", "msg": "平台代码必填"})
        elif len(str(platform_code).strip()) < 2:
            row_errors.append({"col": "platform_code", "type": "format", "msg": "平台代码长度至少2位"})
            
        if not shop_id:
            row_errors.append({"col": "shop_id", "type": "required", "msg": "店铺ID必填"})
        elif len(str(shop_id).strip()) < 2:
            row_errors.append({"col": "shop_id", "type": "format", "msg": "店铺ID长度至少2位"})
        
        # 金额验证
        amount_fields = {
            'ar_amount_cny': (0, 10000000, "应收账款金额"),
            'received_amount_cny': (0, 10000000, "已收金额"),
            'outstanding_amount_cny': (0, 10000000, "未收金额"),
            'receipt_amount_cny': (0, 10000000, "收款金额"),
            'amount_cny': (0, 10000000, "费用金额"),
            'platform_commission': (0, 1000000, "平台佣金"),
            'payment_fee': (0, 1000000, "支付手续费"),
            'shipping_fee': (0, 1000000, "运费")
        }
        
        for field, (min_val, max_val, field_name) in amount_fields.items():
            value = r.get(field)
            if value is not None and str(value).strip():
                parsed_val = _parse_decimal(value)
                if parsed_val is not None:
                    if parsed_val < min_val:
                        row_errors.append({"col": field, "type": "range", "msg": f"{field_name}不能小于{min_val}"})
                    elif parsed_val > max_val:
                        warnings.append({"row": idx, "col": field, "type": "range", "msg": f"{field_name}超过{max_val}，请确认"})
                else:
                    row_errors.append({"col": field, "type": "data_type", "msg": f"{field_name}必须为数字"})
        
        # 日期验证
        date_fields = {
            'invoice_date': "开票日期",
            'due_date': "到期日期",
            'receipt_date': "收款日期",
            'expense_date': "费用日期"
        }
        
        for field, field_name in date_fields.items():
            value = r.get(field)
            if value and str(value).strip():
                parsed_date = _parse_date(value)
                if not parsed_date:
                    row_errors.append({"col": field, "type": "data_type", "msg": f"{field_name}格式不正确"})
                else:
                    # 日期合理性检查
                    date_dt = dt.datetime.fromisoformat(parsed_date)
                    if date_dt > dt.datetime.now():
                        warnings.append({"row": idx, "col": field, "type": "date", "msg": f"{field_name}为未来时间"})
                    elif date_dt < dt.datetime.now() - dt.timedelta(days=365*5):
                        warnings.append({"row": idx, "col": field, "type": "date", "msg": f"{field_name}超过5年"})
        
        # 状态验证
        status_fields = {
            'ar_status': ['pending', 'paid', 'overdue', 'cancelled'],
            'expense_type': ['commission', 'shipping', 'ad', 'other']
        }
        
        for field, valid_values in status_fields.items():
            value = r.get(field)
            if value and str(value).strip().lower() not in valid_values:
                warnings.append({"row": idx, "col": field, "type": "format", "msg": f"{field}状态可能不正确: {value}"})
        
        # 财务逻辑验证
        ar_amount = _parse_decimal(r.get("ar_amount_cny", 0))
        received_amount = _parse_decimal(r.get("received_amount_cny", 0))
        outstanding_amount = _parse_decimal(r.get("outstanding_amount_cny", 0))
        
        if ar_amount is not None and received_amount is not None and outstanding_amount is not None:
            if received_amount > ar_amount:
                row_errors.append({"col": "received_amount_cny", "type": "logic", "msg": "已收金额不能大于应收账款"})
            if abs(outstanding_amount - (ar_amount - received_amount)) > 0.01:
                warnings.append({"row": idx, "col": "outstanding_amount_cny", "type": "logic", "msg": "未收金额应等于应收账款减去已收金额"})
        
        # 逾期天数验证
        overdue_days = _parse_int(r.get("overdue_days"))
        if overdue_days is not None:
            if overdue_days < 0:
                row_errors.append({"col": "overdue_days", "type": "range", "msg": "逾期天数不能为负数"})
            elif overdue_days > 365:
                warnings.append({"row": idx, "col": "overdue_days", "type": "range", "msg": "逾期天数超过365天，请确认"})
        
        # 添加行错误
        for error in row_errors:
            error["row"] = idx
            errors.append(error)
        
        # 统计通过的行
        if not row_errors:
            ok += 1
    
    return {"errors": errors, "warnings": warnings, "ok_rows": ok, "total": len(rows)}


def validate_order_inventory_relation(orders: List[Dict[str, Any]], 
                                    inventory: List[Dict[str, Any]]) -> Dict[str, Any]:
    """验证订单与库存的关联关系"""
    errors, warnings = [], []
    
    # 构建库存查找字典
    inventory_lookup = {}
    for inv in inventory:
        key = f"{inv.get('platform_code')}_{inv.get('shop_id')}_{inv.get('platform_sku')}"
        inventory_lookup[key] = inv
    
    # 检查每个订单的库存可用性
    for idx, order in enumerate(orders):
        platform_code = order.get("platform_code")
        shop_id = order.get("shop_id")
        platform_sku = order.get("platform_sku")
        quantity = _parse_int(order.get("quantity", 0))
        
        if not all([platform_code, shop_id, platform_sku, quantity]):
            continue
        
        key = f"{platform_code}_{shop_id}_{platform_sku}"
        inv_data = inventory_lookup.get(key)
        
        if inv_data:
            available_qty = _parse_int(inv_data.get("quantity_available", 0))
            if available_qty is not None and quantity > available_qty:
                errors.append({
                    "row": idx,
                    "col": "quantity",
                    "type": "inventory_check",
                    "msg": f"订单数量({quantity})超过可用库存({available_qty})",
                    "order_id": order.get("order_id"),
                    "platform_sku": platform_sku
                })
        else:
            warnings.append({
                "row": idx,
                "col": "platform_sku",
                "type": "inventory_missing",
                "msg": f"未找到SKU {platform_sku} 的库存信息",
                "order_id": order.get("order_id"),
                "platform_sku": platform_sku
            })
    
    return {
        "errors": errors,
        "warnings": warnings,
        "total_orders": len(orders),
        "total_inventory": len(inventory)
    }


def validate_order_finance_relation(orders: List[Dict[str, Any]], 
                                   finance: List[Dict[str, Any]]) -> Dict[str, Any]:
    """验证订单与财务的关联关系"""
    errors, warnings = [], []
    
    # 构建财务查找字典
    finance_lookup = {}
    for fin in finance:
        order_id = fin.get("order_id")
        if order_id:
            finance_lookup[order_id] = fin
    
    # 检查每个订单的财务信息
    for idx, order in enumerate(orders):
        order_id = order.get("order_id")
        total_amount = _parse_decimal(order.get("total_amount", 0))
        
        if not order_id:
            continue
        
        fin_data = finance_lookup.get(order_id)
        
        if fin_data:
            ar_amount = _parse_decimal(fin_data.get("ar_amount_cny", 0))
            if ar_amount is not None and total_amount is not None:
                # 检查应收账款是否与订单金额匹配（考虑汇率）
                exchange_rate = _parse_decimal(order.get("exchange_rate", 1))
                expected_ar = total_amount * exchange_rate
                
                if abs(ar_amount - expected_ar) > 0.01:
                    warnings.append({
                        "row": idx,
                        "col": "ar_amount_cny",
                        "type": "amount_mismatch",
                        "msg": f"应收账款({ar_amount})与订单金额({expected_ar})不匹配",
                        "order_id": order_id
                    })
        else:
            warnings.append({
                "row": idx,
                "col": "order_id",
                "type": "finance_missing",
                "msg": f"未找到订单 {order_id} 的财务信息",
                "order_id": order_id
            })
    
    return {
        "errors": errors,
        "warnings": warnings,
        "total_orders": len(orders),
        "total_finance": len(finance)
    }
