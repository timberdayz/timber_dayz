"""
字段映射建议与模板应用（v4.6.0+）

[*] v4.6.0更新: 集成PatternMatcher支持Pattern-based Mapping
"""

from __future__ import annotations

from typing import Dict, List, Optional
import re
from sqlalchemy.orm import Session

# 完整的中英文映射字典（200+字段）
COMPREHENSIVE_ALIAS_DICTIONARY: Dict[str, str] = {
    # ========== 产品基础信息 ==========
    "商品编号": "product_id",
    "商品id": "product_id",
    "产品id": "product_id",
    "product id": "product_id",
    "item id": "product_id",
    "全球商品货号": "product_id",
    "spu": "product_id",
    
    "商品": "product_name",
    "商品名称": "product_name",
    "产品名称": "product_name",
    "product name": "product_name",
    "title": "product_name",
    
    "sku": "platform_sku",
    "商品sku": "platform_sku",
    "platform sku": "platform_sku",
    
    "商品状态": "item_status",
    "current item status": "item_status",
    "item status": "item_status",
    "状态": "item_status",
    
    "变体状态": "variation_status",
    "current variation status": "variation_status",
    
    "库存": "stock",
    "库存数量": "stock",
    "stock": "stock",
    "inventory": "stock",
    
    "价格": "price",
    "单价": "price",
    "price": "price",
    
    "币种": "currency",
    "货币": "currency",
    "currency": "currency",
    
    # ========== 流量指标 ==========
    "商品页面访问量": "page_views",
    "页面浏览量": "page_views",
    "浏览量": "page_views",
    "pv": "page_views",
    "page views": "page_views",
    "pageview": "page_views",
    
    "商品访客数": "unique_visitors",
    "商品访客数量": "unique_visitors",
    "访客数": "unique_visitors",
    "uv": "unique_visitors",
    "unique visitors": "unique_visitors",
    "去重访客数": "unique_visitors",
    
    "曝光量": "impressions",
    "曝光次数": "impressions",
    "展示次数": "impressions",
    "impressions": "impressions",
    
    "点击量": "clicks",
    "点击次数": "clicks",
    "clicks": "clicks",
    
    "点击率": "click_rate",
    "ctr": "click_rate",
    "click rate": "click_rate",
    
    # ========== 转化指标 ==========
    "加购次数": "cart_add_count",
    "加入购物车次数": "cart_add_count",
    "add to cart": "cart_add_count",
    
    "商品访客数(加入购物车)": "cart_add_visitors",
    "加购人数": "cart_add_visitors",
    "加购访客数": "cart_add_visitors",
    
    "订单数": "order_count",
    "订单量": "order_count",
    "order count": "order_count",
    "orders": "order_count",
    
    "成交件数": "sold_count",
    "销售件数": "sold_count",
    "销量": "sold_count",
    "units sold": "sold_count",
    "sold count": "sold_count",
    
    "转化率": "conversion_rate",
    "conversion rate": "conversion_rate",
    "conversion": "conversion_rate",
    
    "成交金额": "gmv",
    "销售额": "gmv",
    "gmv": "gmv",
    "gross merchandise value": "gmv",
    "商品交易总额": "gmv",
    
    # ========== 行为指标 ==========
    "商品跳出率": "bounce_rate",
    "跳出率": "bounce_rate",
    "bounce rate": "bounce_rate",
    
    "跳出商品页面的访客数": "bounce_visitors",
    "跳出访客数": "bounce_visitors",
    "bounce visitors": "bounce_visitors",
    
    "平均停留时长": "avg_session_duration",
    "停留时长": "avg_session_duration",
    "avg session duration": "avg_session_duration",
    
    # ========== 商品评价 ==========
    "评分": "rating",
    "商品评分": "rating",
    "rating": "rating",
    "star rating": "rating",
    
    "评价数": "review_count",
    "评论数": "review_count",
    "reviews": "review_count",
    "review count": "review_count",
    
    "好评率": "positive_rate",
    "positive rate": "positive_rate",
    
    # ========== 订单字段 ==========
    "订单号": "order_id",
    "order no": "order_id",
    "order id": "order_id",
    
    "订单时间": "order_ts",
    "下单时间": "order_ts",
    "order time": "order_ts",
    "order date": "order_ts",
    
    "订单状态": "order_status",
    "order status": "order_status",
    
    "买家id": "buyer_id",
    "buyer id": "buyer_id",
    
    "数量": "quantity",
    "购买数量": "quantity",
    "qty": "quantity",
    "quantity": "quantity",
    
    "运费": "shipping_fee",
    "shipping fee": "shipping_fee",
    
    "折扣": "discount_amount",
    "优惠金额": "discount_amount",
    "discount": "discount_amount",
    
    "总金额": "total_amount",
    "订单金额": "total_amount",
    "total amount": "total_amount",
    
    # ========== 时间字段 ==========
    "日期": "metric_date",
    "统计日期": "metric_date",
    "date": "metric_date",
    "metric date": "metric_date",
    
    # ========== 库存管理字段 ==========
    "实际库存": "quantity_on_hand",
    "可用库存": "quantity_available",
    "预留库存": "quantity_reserved",
    "在途库存": "quantity_incoming",
    "安全库存": "safety_stock",
    "补货点": "reorder_point",
    "平均成本": "avg_cost",
    "库存价值": "total_value",
    "仓库代码": "warehouse_code",
    "仓库": "warehouse_code",
    "warehouse": "warehouse_code",
    
    "库存变动类型": "transaction_type",
    "变动类型": "transaction_type",
    "transaction type": "transaction_type",
    "变动数量": "quantity_change",
    "变动前数量": "quantity_before",
    "变动后数量": "quantity_after",
    "单位成本": "unit_cost",
    "操作员": "operator_id",
    "操作员id": "operator_id",
    "operator": "operator_id",
    
    # ========== 财务管理字段 ==========
    "应收账款": "ar_amount_cny",
    "应收金额": "ar_amount_cny",
    "已收金额": "received_amount_cny",
    "未收金额": "outstanding_amount_cny",
    "开票日期": "invoice_date",
    "到期日期": "due_date",
    "应收状态": "ar_status",
    "是否逾期": "is_overdue",
    "逾期天数": "overdue_days",
    
    "收款日期": "receipt_date",
    "收款金额": "receipt_amount_cny",
    "收款方式": "payment_method",
    "银行账户": "bank_account",
    
    "费用类型": "expense_type",
    "费用日期": "expense_date",
    "费用金额": "amount_cny",
    "佣金": "commission",
    "平台佣金": "platform_commission",
    "支付手续费": "payment_fee",
    "运费": "shipping_fee",
    
    # ========== 成本利润字段 ==========
    "成本价": "cost_price",
    "成本单价": "cost_price",
    "成本总额": "cost_amount_cny",
    "毛利": "gross_profit_cny",
    "净利": "net_profit_cny",
    "利润率": "profit_margin",
    "毛利率": "gross_margin",
    "净利率": "net_margin",
    
    "汇率": "exchange_rate",
    "人民币金额": "gmv_cny",
    "人民币成本": "cost_amount_cny",
    "人民币毛利": "gross_profit_cny",
    "人民币净利": "net_profit_cny",
    
    # ========== 财务状态字段 ==========
    "是否已开票": "is_invoiced",
    "发票id": "invoice_id",
    "是否已收款": "is_payment_received",
    "收款凭证id": "payment_voucher_id",
    "库存是否已扣减": "inventory_deducted",
}

# 保持向后兼容
ALIAS_DICTIONARY = COMPREHENSIVE_ALIAS_DICTIONARY


def suggest_mappings(columns: List[str], domain: str, db: Optional[Session] = None) -> Dict[str, dict]:
    """
    智能字段映射（v4.6.0+ Pattern-based Mapping）
    
    策略优先级（v4.6.0新增）：
    0. [*] Pattern-based匹配（支持货币字段）<- 新增!
    1. 精确匹配（ALIAS_DICTIONARY）
    2. 模糊匹配（去除空格、大小写）
    3. 关键词匹配（包含关系）
    4. 语义理解（规则引擎）
    5. 数据域特定匹配（库存/财务）
    
    Args:
        columns: 原始列名列表
        domain: 数据域(orders/traffic/analytics等)
        db: 数据库会话(可选,用于PatternMatcher)
    
    Returns:
        映射建议字典: {原始列名: {standard, confidence, method, dimensions?, target_table?, target_columns?}}
    """
    suggestions = {}
    
    # [*] v4.6.0: 优先使用Pattern-based匹配(如果提供了db)
    if db:
        try:
            from backend.services.pattern_matcher import PatternMatcher
            matcher = PatternMatcher(db)
            
            for col in columns:
                # 尝试Pattern匹配
                pattern_result = matcher.match_field(col, data_domain=domain)
                if pattern_result and pattern_result.get('standard_field'):
                    suggestions[col] = {
                        "standard": pattern_result['standard_field'],
                        "confidence": pattern_result.get('confidence', 0.95),
                        "method": pattern_result.get('match_type', 'pattern_match'),
                        "reason": pattern_result.get('match_reason', 'Pattern-based匹配'),
                        "dimensions": pattern_result.get('dimensions', {}),
                        "target_table": pattern_result.get('target_table'),
                        "target_columns": pattern_result.get('target_columns')
                    }
                    continue  # Pattern匹配成功,跳过后续匹配
        except Exception as e:
            # PatternMatcher不可用时降级到传统匹配
            from modules.core.logger import get_logger
            logger = get_logger(__name__)
            logger.warning(f"PatternMatcher不可用,降级到传统匹配: {e}")
    
    # 传统匹配逻辑(对未通过Pattern匹配的字段)
    for col in columns:
        if col in suggestions:
            continue  # 已被Pattern匹配,跳过
            
        col_clean = (col or "").strip()
        col_lower = col_clean.lower()
        
        # 1. 精确匹配（置信度 1.0）
        if col_lower in COMPREHENSIVE_ALIAS_DICTIONARY:
            std = COMPREHENSIVE_ALIAS_DICTIONARY[col_lower]
            suggestions[col] = {
                "standard": std,
                "confidence": 1.0,
                "method": "exact_match"
            }
            continue
        
        # 2. 模糊匹配（去除空格、特殊字符）
        col_normalized = re.sub(r'[\s_\-()（）]', '', col_lower)
        for alias, std in COMPREHENSIVE_ALIAS_DICTIONARY.items():
            alias_normalized = re.sub(r'[\s_\-()（）]', '', alias.lower())
            if col_normalized == alias_normalized:
                suggestions[col] = {
                    "standard": std,
                    "confidence": 0.95,
                    "method": "fuzzy_match"
                }
                break
        
        if col in suggestions:
            continue
        
        # 3. 数据域特定匹配
        matched = False
        
        # 库存管理域特定匹配
        if domain == "inventory":
            if any(kw in col_lower for kw in ['实际库存', 'on hand', 'available stock']):
                suggestions[col] = {"standard": "quantity_on_hand", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['可用库存', 'available', 'usable']):
                suggestions[col] = {"standard": "quantity_available", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['预留库存', 'reserved', 'allocated']):
                suggestions[col] = {"standard": "quantity_reserved", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['在途库存', 'incoming', 'transit']):
                suggestions[col] = {"standard": "quantity_incoming", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['安全库存', 'safety', 'minimum']):
                suggestions[col] = {"standard": "safety_stock", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['补货点', 'reorder', 'trigger']):
                suggestions[col] = {"standard": "reorder_point", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['平均成本', 'avg cost', 'average cost']):
                suggestions[col] = {"standard": "avg_cost", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['库存价值', 'inventory value', 'total value']):
                suggestions[col] = {"standard": "total_value", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['仓库', 'warehouse', 'location']):
                suggestions[col] = {"standard": "warehouse_code", "confidence": 0.9, "method": "domain_specific"}
                matched = True
        
        # 财务管理域特定匹配
        elif domain == "finance":
            if any(kw in col_lower for kw in ['应收账款', 'accounts receivable', 'ar']):
                suggestions[col] = {"standard": "ar_amount_cny", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['已收金额', 'received', 'collected']):
                suggestions[col] = {"standard": "received_amount_cny", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['未收金额', 'outstanding', 'unpaid']):
                suggestions[col] = {"standard": "outstanding_amount_cny", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['开票日期', 'invoice date', 'billing date']):
                suggestions[col] = {"standard": "invoice_date", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['到期日期', 'due date', 'maturity']):
                suggestions[col] = {"standard": "due_date", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['应收状态', 'ar status', 'receivable status']):
                suggestions[col] = {"standard": "ar_status", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['是否逾期', 'overdue', 'past due']):
                suggestions[col] = {"standard": "is_overdue", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['逾期天数', 'overdue days', 'days past due']):
                suggestions[col] = {"standard": "overdue_days", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['收款日期', 'receipt date', 'payment date']):
                suggestions[col] = {"standard": "receipt_date", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['收款金额', 'receipt amount', 'payment amount']):
                suggestions[col] = {"standard": "receipt_amount_cny", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['收款方式', 'payment method', 'payment type']):
                suggestions[col] = {"standard": "payment_method", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['银行账户', 'bank account', 'account number']):
                suggestions[col] = {"standard": "bank_account", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['费用类型', 'expense type', 'cost type']):
                suggestions[col] = {"standard": "expense_type", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['费用日期', 'expense date', 'cost date']):
                suggestions[col] = {"standard": "expense_date", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['费用金额', 'expense amount', 'cost amount']):
                suggestions[col] = {"standard": "amount_cny", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['佣金', 'commission', 'fee']):
                suggestions[col] = {"standard": "commission", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['平台佣金', 'platform commission', 'marketplace fee']):
                suggestions[col] = {"standard": "platform_commission", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['支付手续费', 'payment fee', 'transaction fee']):
                suggestions[col] = {"standard": "payment_fee", "confidence": 0.9, "method": "domain_specific"}
                matched = True
            elif any(kw in col_lower for kw in ['运费', 'shipping fee', 'shipping cost']):
                suggestions[col] = {"standard": "shipping_fee", "confidence": 0.9, "method": "domain_specific"}
                matched = True
        
        if matched:
            continue
        
        # 4. 通用关键词匹配（按优先级）
        # 高优先级关键词（流量/转化指标）
        if any(kw in col_lower for kw in ['访问量', '浏览量', 'page view', 'pv']):
            suggestions[col] = {"standard": "page_views", "confidence": 0.85, "method": "keyword"}
            matched = True
        elif any(kw in col_lower for kw in ['访客数', 'visitor', 'uv']):
            if '加购' in col_lower or 'cart' in col_lower:
                suggestions[col] = {"standard": "cart_add_visitors", "confidence": 0.85, "method": "keyword"}
            elif '跳出' in col_lower or 'bounce' in col_lower:
                suggestions[col] = {"standard": "bounce_visitors", "confidence": 0.85, "method": "keyword"}
            else:
                suggestions[col] = {"standard": "unique_visitors", "confidence": 0.85, "method": "keyword"}
            matched = True
        elif any(kw in col_lower for kw in ['跳出率', 'bounce rate']):
            suggestions[col] = {"standard": "bounce_rate", "confidence": 0.85, "method": "keyword"}
            matched = True
        elif any(kw in col_lower for kw in ['转化率', 'conversion']):
            suggestions[col] = {"standard": "conversion_rate", "confidence": 0.85, "method": "keyword"}
            matched = True
        
        if matched:
            continue
        
        # 5. 低优先级关键词（基础字段）- 避免误匹配
        if col_lower in ['商品编号', '商品id', 'product id', 'item id']:
            suggestions[col] = {"standard": "product_id", "confidence": 0.9, "method": "keyword"}
        elif col_lower in ['商品', '商品名称', 'product name', 'title']:
            suggestions[col] = {"standard": "product_name", "confidence": 0.9, "method": "keyword"}
        elif 'status' in col_lower and 'item' in col_lower:
            suggestions[col] = {"standard": "item_status", "confidence": 0.8, "method": "keyword"}
        elif 'status' in col_lower and 'variation' in col_lower:
            suggestions[col] = {"standard": "variation_status", "confidence": 0.8, "method": "keyword"}
        else:
            # 无法识别
            suggestions[col] = {"standard": "", "confidence": 0.0, "method": "unknown"}
    
    return suggestions