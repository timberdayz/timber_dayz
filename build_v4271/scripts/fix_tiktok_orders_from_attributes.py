# -*- coding: utf-8 -*-
"""
修复TikTok订单数据：从attributes JSON中提取字段并更新到fact_orders标准字段
"""

import sys
from pathlib import Path
from datetime import datetime, date
from typing import Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text
from modules.core.logger import get_logger

logger = get_logger(__name__)

def safe_print(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def safe_float(value) -> float:
    """安全转换为float"""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value):  # NaN check
            return 0.0
        return float(value)
    if isinstance(value, str):
        value = value.strip()
        if not value or value.lower() in ['none', 'null', 'n/a', 'na', '-', '']:
            return 0.0
        try:
            # 去除货币符号和千分位
            cleaned = value.replace(',', '').replace('$', '').replace('¥', '').replace('€', '').replace('£', '').replace('R$', '').replace('S$', '').strip()
            return float(cleaned)
        except (ValueError, TypeError):
            return 0.0
    return 0.0

def safe_str(value) -> Optional[str]:
    """安全转换为字符串"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (value != value):  # NaN check
            return None
        return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)
    return str(value).strip() if str(value).strip() else None

def safe_date(value) -> Optional[date]:
    """安全转换为date"""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            # 尝试解析日期字符串
            for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S']:
                try:
                    dt = datetime.strptime(value.strip(), fmt)
                    return dt.date()
                except ValueError:
                    continue
        except:
            pass
    return None

def extract_fields_from_attributes(attrs: dict) -> dict:
    """从attributes中提取字段并映射到标准字段"""
    if not attrs or not isinstance(attrs, dict):
        return {}
    
    updates = {}
    
    # 1. shop_id映射（多个可能的字段名）
    shop_id_candidates = [
        'shop_id', 'shop', '店铺', '店铺ID', '店铺编号',
        'store_id', 'store', 'store_label', 'store_label_raw'
    ]
    for candidate in shop_id_candidates:
        if candidate in attrs and attrs[candidate]:
            updates['shop_id'] = safe_str(attrs[candidate])
            break
    
    # 2. currency映射
    currency_candidates = [
        'currency', '币种', '货币', 'currency_code',
        '币种代码', '货币代码'
    ]
    for candidate in currency_candidates:
        if candidate in attrs and attrs[candidate]:
            currency = safe_str(attrs[candidate])
            # 标准化货币代码（大写，去除空格）
            if currency:
                currency = currency.upper().strip()
                # 处理常见货币符号
                currency_map = {
                    'RMB': 'CNY', '人民币': 'CNY', 'CNY': 'CNY',
                    'USD': 'USD', '美元': 'USD', 'US$': 'USD',
                    'SGD': 'SGD', '新加坡元': 'SGD', 'S$': 'SGD',
                    'MYR': 'MYR', '马来西亚林吉特': 'MYR', 'RM': 'MYR',
                    'BRL': 'BRL', '巴西雷亚尔': 'BRL', 'R$': 'BRL',
                }
                currency = currency_map.get(currency, currency)
                if len(currency) == 3:  # 只接受3位货币代码
                    updates['currency'] = currency
            break
    
    # 3. 金额字段映射
    # subtotal（小计/商品金额）
    subtotal_candidates = [
        'subtotal', '小计', '商品金额', '商品总价',
        'paid_amount_mai_jia', '买家实付金额',  # TikTok特定字段
        'amount_yi_jie_suan', '已结算金额',
    ]
    for candidate in subtotal_candidates:
        if candidate in attrs and attrs[candidate] is not None:
            value = safe_float(attrs[candidate])
            if value > 0:
                updates['subtotal'] = value
                break
    
    # shipping_fee（运费）
    shipping_fee_candidates = [
        'shipping_fee', '运费', '物流费', '配送费',
        'actual_shipping_fee', '实际运费',  # TikTok特定字段
        'shipping_fee_shang_jia', '商家运费',
    ]
    for candidate in shipping_fee_candidates:
        if candidate in attrs and attrs[candidate] is not None:
            value = safe_float(attrs[candidate])
            if value > 0:
                updates['shipping_fee'] = value
                break
    
    # tax_amount（税费）
    tax_candidates = [
        'tax_amount', '税费', '税金', '税',
        'GST', 'VAT', '增值税',
    ]
    for candidate in tax_candidates:
        if candidate in attrs and attrs[candidate] is not None:
            value = safe_float(attrs[candidate])
            if value > 0:
                updates['tax_amount'] = value
                break
    
    # total_amount（总金额）
    total_amount_candidates = [
        'total_amount', '总金额', '订单金额', '实收金额',
        'paid_amount_mai_jia', '买家实付金额',  # TikTok特定字段
        'amount_yi_jie_suan', '已结算金额',
    ]
    for candidate in total_amount_candidates:
        if candidate in attrs and attrs[candidate] is not None:
            value = safe_float(attrs[candidate])
            if value > 0:
                updates['total_amount'] = value
                break
    
    # 如果total_amount为空，尝试从subtotal + shipping_fee + tax_amount计算
    if 'total_amount' not in updates and ('subtotal' in updates or 'shipping_fee' in updates or 'tax_amount' in updates):
        total = updates.get('subtotal', 0.0) + updates.get('shipping_fee', 0.0) + updates.get('tax_amount', 0.0)
        if total > 0:
            updates['total_amount'] = total
    
    # 4. order_date_local映射（从order_time_utc提取日期）
    # 如果order_time_utc存在，提取日期部分
    if 'order_time_utc' not in updates:  # 如果标准字段中没有
        date_candidates = [
            'order_date_local', 'order_date', '订单日期', '下单日期',
            'order_time_utc', '下单时间', 'order_time',
        ]
        for candidate in date_candidates:
            if candidate in attrs and attrs[candidate]:
                date_value = safe_date(attrs[candidate])
                if date_value:
                    updates['order_date_local'] = date_value
                    break
    
    return updates

def fix_tiktok_orders():
    """修复TikTok订单数据"""
    safe_print("=" * 70)
    safe_print("修复TikTok订单数据：从attributes提取字段并更新标准字段")
    safe_print("=" * 70)
    
    db = next(get_db())
    try:
        # 1. 查询所有需要修复的TikTok订单
        safe_print("\n[1] 查询需要修复的TikTok订单...")
        orders = db.execute(text("""
            SELECT 
                platform_code,
                shop_id,
                order_id,
                attributes,
                order_time_utc,
                order_date_local,
                currency,
                subtotal,
                shipping_fee,
                tax_amount,
                total_amount
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
              AND attributes IS NOT NULL
            ORDER BY order_time_utc DESC NULLS LAST
        """)).fetchall()
        
        safe_print(f"  找到 {len(orders)} 条TikTok订单需要检查")
        
        # 2. 统计需要更新的字段
        stats = {
            'total': len(orders),
            'shop_id_updated': 0,
            'currency_updated': 0,
            'subtotal_updated': 0,
            'shipping_fee_updated': 0,
            'tax_amount_updated': 0,
            'total_amount_updated': 0,
            'order_date_local_updated': 0,
            'skipped': 0,
        }
        
        # 3. 批量更新订单
        safe_print("\n[2] 开始批量更新订单...")
        batch_size = 100
        updated_count = 0
        
        for idx, order in enumerate(orders):
            platform_code, shop_id, order_id, attrs, order_time_utc, order_date_local, currency, subtotal, shipping_fee, tax_amount, total_amount = order
            
            # 检查是否需要更新
            needs_update = False
            if not shop_id or shop_id == '':
                needs_update = True
            if not currency:
                needs_update = True
            if not subtotal or subtotal == 0:
                needs_update = True
            if not total_amount or total_amount == 0:
                needs_update = True
            if not order_date_local and order_time_utc:
                needs_update = True
            
            if not needs_update:
                stats['skipped'] += 1
                continue
            
            # 从attributes中提取字段
            updates = extract_fields_from_attributes(attrs)
            
            if not updates:
                stats['skipped'] += 1
                continue
            
            # 构建UPDATE语句
            update_fields = []
            update_values = {}
            
            # shop_id
            if 'shop_id' in updates and (not shop_id or shop_id == ''):
                update_fields.append('shop_id = :shop_id')
                update_values['shop_id'] = updates['shop_id']
                stats['shop_id_updated'] += 1
            
            # currency
            if 'currency' in updates and not currency:
                update_fields.append('currency = :currency')
                update_values['currency'] = updates['currency']
                stats['currency_updated'] += 1
            
            # subtotal
            if 'subtotal' in updates and (not subtotal or subtotal == 0):
                update_fields.append('subtotal = :subtotal')
                update_values['subtotal'] = updates['subtotal']
                stats['subtotal_updated'] += 1
            
            # shipping_fee
            if 'shipping_fee' in updates and (not shipping_fee or shipping_fee == 0):
                update_fields.append('shipping_fee = :shipping_fee')
                update_values['shipping_fee'] = updates['shipping_fee']
                stats['shipping_fee_updated'] += 1
            
            # tax_amount
            if 'tax_amount' in updates and (not tax_amount or tax_amount == 0):
                update_fields.append('tax_amount = :tax_amount')
                update_values['tax_amount'] = updates['tax_amount']
                stats['tax_amount_updated'] += 1
            
            # total_amount
            if 'total_amount' in updates and (not total_amount or total_amount == 0):
                update_fields.append('total_amount = :total_amount')
                update_values['total_amount'] = updates['total_amount']
                stats['total_amount_updated'] += 1
            
            # order_date_local
            if 'order_date_local' in updates and not order_date_local:
                update_fields.append('order_date_local = :order_date_local')
                update_values['order_date_local'] = updates['order_date_local']
                stats['order_date_local_updated'] += 1
            
            if update_fields:
                # 添加updated_at
                update_fields.append('updated_at = CURRENT_TIMESTAMP')
                
                # 执行UPDATE
                update_sql = f"""
                    UPDATE fact_orders 
                    SET {', '.join(update_fields)}
                    WHERE platform_code = :platform_code 
                      AND shop_id = :old_shop_id
                      AND order_id = :order_id
                """
                update_values['platform_code'] = platform_code
                update_values['old_shop_id'] = shop_id or ''
                update_values['order_id'] = order_id
                
                try:
                    db.execute(text(update_sql), update_values)
                    updated_count += 1
                    
                    # 每100条提交一次
                    if updated_count % batch_size == 0:
                        db.commit()
                        safe_print(f"  已更新 {updated_count} 条订单...")
                except Exception as e:
                    db.rollback()
                    logger.error(f"更新订单失败: order_id={order_id}, error={e}")
                    continue
        
        # 提交剩余的更新
        db.commit()
        
        # 4. 显示统计结果
        safe_print("\n[3] 更新统计:")
        safe_print(f"  总订单数: {stats['total']}")
        safe_print(f"  已更新订单数: {updated_count}")
        safe_print(f"  跳过订单数: {stats['skipped']}")
        safe_print(f"  shop_id更新: {stats['shop_id_updated']}")
        safe_print(f"  currency更新: {stats['currency_updated']}")
        safe_print(f"  subtotal更新: {stats['subtotal_updated']}")
        safe_print(f"  shipping_fee更新: {stats['shipping_fee_updated']}")
        safe_print(f"  tax_amount更新: {stats['tax_amount_updated']}")
        safe_print(f"  total_amount更新: {stats['total_amount_updated']}")
        safe_print(f"  order_date_local更新: {stats['order_date_local_updated']}")
        
        # 5. 验证更新结果
        safe_print("\n[4] 验证更新结果...")
        result = db.execute(text("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN shop_id IS NOT NULL AND shop_id != '' THEN 1 END) as has_shop_id,
                COUNT(CASE WHEN currency IS NOT NULL AND currency != '' THEN 1 END) as has_currency,
                COUNT(CASE WHEN subtotal > 0 THEN 1 END) as has_subtotal,
                COUNT(CASE WHEN total_amount > 0 THEN 1 END) as has_total_amount,
                COUNT(CASE WHEN order_date_local IS NOT NULL THEN 1 END) as has_order_date
            FROM fact_orders 
            WHERE platform_code = 'tiktok'
        """)).fetchone()
        
        if result:
            total, has_shop_id, has_currency, has_subtotal, has_total_amount, has_order_date = result
            safe_print(f"  总订单数: {total}")
            safe_print(f"  有shop_id: {has_shop_id} ({has_shop_id/total*100:.1f}%)")
            safe_print(f"  有currency: {has_currency} ({has_currency/total*100:.1f}%)")
            safe_print(f"  有subtotal: {has_subtotal} ({has_subtotal/total*100:.1f}%)")
            safe_print(f"  有total_amount: {has_total_amount} ({has_total_amount/total*100:.1f}%)")
            safe_print(f"  有order_date_local: {has_order_date} ({has_order_date/total*100:.1f}%)")
        
        safe_print("\n" + "=" * 70)
        safe_print("修复完成！")
        safe_print("=" * 70)
        
    except Exception as e:
        db.rollback()
        safe_print(f"修复失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    fix_tiktok_orders()

