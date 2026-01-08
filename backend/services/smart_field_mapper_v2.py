#!/usr/bin/env python3
"""
智能字段映射器 v2.0 - 阶段1优化版本

改进点：
1. 避免列名重复映射（冲突检测）
2. 增强智能匹配算法（中英文同义词）
3. 优化置信度计算
4. 支持拼音匹配
"""

from typing import Dict, List, Tuple, Optional
from difflib import SequenceMatcher
import re


class SmartFieldMapperV2:
    """智能字段映射器 v2.0"""
    
    def __init__(self):
        # 中英文同义词词典（扩展版）
        self.synonyms = {
            # 商品相关
            "product_id": ["商品id", "产品id", "商品编号", "product_id", "item_id", "sku", "编号"],
            "product_name": ["商品名称", "产品名称", "商品", "产品", "品名", "title", "name", "标题"],
            "platform_sku": ["sku", "商品编码", "产品编码", "item_code", "货号"],
            "category": ["分类", "类别", "category", "类目", "品类"],
            "brand": ["品牌", "brand", "牌子"],
            
            # 价格相关
            "price": ["价格", "单价", "售价", "price", "unit_price", "sale_price"],
            "currency": ["货币", "币种", "currency"],
            
            # 库存相关
            "stock": ["库存", "库存数", "stock", "inventory", "qty_available"],
            
            # 销售相关
            "sales_volume": ["销量", "销售数量", "已售", "sales", "sold", "units_sold"],
            "sales_amount": ["销售额", "销售金额", "gmv", "revenue", "营收"],
            
            # 流量相关
            "page_views": ["浏览量", "访问量", "pv", "views", "页面浏览"],
            "unique_visitors": ["访客数", "uv", "visitors", "独立访客"],
            "click_through_rate": ["点击率", "ctr", "click_rate"],
            "conversion_rate": ["转化率", "conversion", "转化"],
            
            # 评价相关
            "rating": ["评分", "rating", "score", "评价分"],
            "review_count": ["评论数", "评价数", "reviews", "review_count"],
            
            # 订单相关
            "order_id": ["订单号", "订单编号", "order_id", "order_no"],
            "order_date": ["订单日期", "下单时间", "order_date", "order_time"],
            "total_amount": ["订单金额", "总金额", "total", "total_amount"],
            "buyer_name": ["买家", "客户", "buyer", "customer"],
            
            # 状态相关
            "status": ["状态", "status", "state"],
            "order_status": ["订单状态", "order_status"],
        }
        
        # 拼音映射（常用字段）
        self.pinyin_map = {
            "shangpin": "product",
            "jiage": "price",
            "kucun": "stock",
            "xiaoliang": "sales_volume",
            "dingdan": "order",
        }
    
    def map_fields(
        self, 
        columns: List[str], 
        data_domain: str = "products",
        source_platform: str = "shopee"
    ) -> Dict[str, Dict[str, any]]:
        """
        智能字段映射（v2.0 - 无冲突版本）
        
        Args:
            columns: Excel列名列表
            data_domain: 数据域（products/orders/analytics等）
            source_platform: 数据源平台（shopee/tiktok等）
        
        Returns:
            映射结果字典
            {
                "原始列名": {
                    "standard": "标准字段名",
                    "confidence": 0.95,
                    "method": "exact_match"
                }
            }
        """
        # Step 1: 获取该数据域的标准字段
        standard_fields = self._get_standard_fields(data_domain)
        
        # Step 2: 为每个列生成候选映射
        candidates = {}
        for column in columns:
            candidates[column] = self._find_candidates(column, standard_fields)
        
        # Step 3: 冲突检测和解决
        final_mappings = self._resolve_conflicts(candidates)
        
        return final_mappings
    
    def _get_standard_fields(self, data_domain: str) -> Dict[str, str]:
        """获取标准字段定义"""
        fields_map = {
            "products": {
                "platform_code": "平台代码",
                "shop_id": "店铺ID",
                "platform_sku": "平台SKU",
                "product_name": "商品名称",
                "category": "分类",
                "brand": "品牌",
                "price": "价格",
                "currency": "货币",
                "stock": "库存",
                "sales_volume": "销量",
                "sales_amount": "销售额",
                "page_views": "浏览量",
                "unique_visitors": "访客数",
                "click_through_rate": "点击率",
                "conversion_rate": "转化率",
                "rating": "评分",
                "review_count": "评论数",
            },
            "orders": {
                "platform_code": "平台代码",
                "shop_id": "店铺ID",
                "order_id": "订单ID",
                "order_date": "订单日期",
                "platform_sku": "商品SKU",
                "product_name": "商品名称",
                "quantity": "数量",
                "subtotal": "小计",
                "shipping_fee": "运费",
                "tax_amount": "税费",
                "discount_amount": "折扣",
                "total_amount": "总金额",
                "currency": "货币",
                "order_status": "订单状态",
                "payment_status": "支付状态",
                "buyer_name": "买家姓名",
            },
            "analytics": {
                "platform_code": "平台代码",
                "shop_id": "店铺ID",
                "metric_date": "日期",
                "page_views": "页面浏览量",
                "unique_visitors": "独立访客",
                "bounce_rate": "跳出率",
                "conversion_rate": "转化率",
            }
        }
        
        return fields_map.get(data_domain, fields_map["products"])
    
    def _find_candidates(
        self, 
        column: str, 
        standard_fields: Dict[str, str]
    ) -> List[Tuple[str, float, str]]:
        """
        为单个列找到候选映射
        
        Returns:
            [(标准字段名, 置信度, 匹配方法), ...]
        """
        candidates = []
        column_lower = column.lower().strip()
        column_clean = re.sub(r'[^\w\u4e00-\u9fff]', '', column)  # 移除特殊字符
        
        for std_field in standard_fields.keys():
            # 方法1: 精确匹配（100%）
            if column_lower == std_field.lower():
                candidates.append((std_field, 1.0, "exact_match"))
                continue
            
            # 方法2: 同义词匹配（95%）
            if std_field in self.synonyms:
                for synonym in self.synonyms[std_field]:
                    synonym_clean = synonym.lower().strip()
                    if column_lower == synonym_clean or column_clean.lower() == re.sub(r'[^\w\u4e00-\u9fff]', '', synonym).lower():
                        candidates.append((std_field, 0.95, "synonym_match"))
                        break
            
            # 方法3: 包含匹配（80-90%）
            if std_field.lower() in column_lower:
                confidence = 0.9 if len(std_field) > 3 else 0.8
                candidates.append((std_field, confidence, "contains_match"))
            elif column_lower in std_field.lower():
                confidence = 0.85
                candidates.append((std_field, confidence, "contained_match"))
            
            # 方法4: 模糊相似度匹配（70-85%）
            similarity = SequenceMatcher(None, column_lower, std_field.lower()).ratio()
            if similarity > 0.7:
                confidence = min(0.85, similarity)
                candidates.append((std_field, confidence, "fuzzy_match"))
        
        # 排序：置信度从高到低
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        return candidates
    
    def _resolve_conflicts(
        self, 
        candidates: Dict[str, List[Tuple[str, float, str]]]
    ) -> Dict[str, Dict[str, any]]:
        """
        解决映射冲突
        
        策略：
        1. 每个标准字段只能被映射一次
        2. 当多个原始列映射到同一标准字段时，选择置信度最高的
        3. 其他列映射为"未映射"或次优选择
        """
        # 反向映射：标准字段 -> (原始列, 置信度, 方法)
        reverse_map = {}
        
        # 第一轮：收集所有映射并找出冲突
        for orig_col, cands in candidates.items():
            if not cands:
                continue
            
            best_std, best_conf, best_method = cands[0]
            
            if best_std not in reverse_map:
                reverse_map[best_std] = (orig_col, best_conf, best_method)
            else:
                # 冲突！比较置信度
                existing_col, existing_conf, existing_method = reverse_map[best_std]
                if best_conf > existing_conf:
                    # 新的更好，替换
                    reverse_map[best_std] = (orig_col, best_conf, best_method)
        
        # 第二轮：构建最终映射
        final_mappings = {}
        mapped_standards = set(reverse_map.keys())
        
        for orig_col, cands in candidates.items():
            if not cands:
                # 完全无法映射
                final_mappings[orig_col] = {
                    "standard": orig_col,  # 保持原样
                    "confidence": 0.0,
                    "method": "no_match",
                    "is_unmapped": True
                }
                continue
            
            # 找到该列的最佳非冲突映射
            best_mapping = None
            for std_field, conf, method in cands:
                if std_field in reverse_map and reverse_map[std_field][0] == orig_col:
                    # 这是赢得冲突的映射
                    best_mapping = (std_field, conf, method)
                    break
                elif std_field not in mapped_standards:
                    # 这是一个未被占用的次优映射
                    best_mapping = (std_field, conf * 0.9, f"{method}_fallback")  # 降低10%置信度
                    break
            
            if best_mapping:
                std_field, conf, method = best_mapping
                final_mappings[orig_col] = {
                    "standard": std_field,
                    "confidence": round(conf * 100, 1),  # 转为百分比
                    "method": method,
                    "is_unmapped": False
                }
                if std_field not in reverse_map or reverse_map[std_field][0] != orig_col:
                    mapped_standards.add(std_field)
            else:
                # 所有候选都被占用了
                final_mappings[orig_col] = {
                    "standard": orig_col,
                    "confidence": 0.0,
                    "method": "conflict_unresolved",
                    "is_unmapped": True
                }
        
        return final_mappings
    
    def get_mapping_statistics(self, mappings: Dict[str, Dict]) -> Dict:
        """获取映射统计信息"""
        total = len(mappings)
        mapped = sum(1 for m in mappings.values() if not m.get('is_unmapped'))
        unmapped = total - mapped
        
        confidence_bins = {
            "high": 0,  # ≥90%
            "medium": 0,  # 60-90%
            "low": 0,  # <60%
        }
        
        for m in mappings.values():
            conf = m.get('confidence', 0)
            if conf >= 90:
                confidence_bins["high"] += 1
            elif conf >= 60:
                confidence_bins["medium"] += 1
            else:
                confidence_bins["low"] += 1
        
        return {
            "total_columns": total,
            "mapped_count": mapped,
            "unmapped_count": unmapped,
            "mapping_rate": round(mapped / total * 100, 1) if total > 0 else 0,
            "confidence_distribution": confidence_bins,
            "avg_confidence": round(
                sum(m.get('confidence', 0) for m in mappings.values()) / total, 1
            ) if total > 0 else 0
        }


# 向后兼容的导出
def smart_map_fields(columns: List[str], data_domain: str = "products", source_platform: str = "shopee") -> Dict:
    """便捷函数：智能字段映射"""
    mapper = SmartFieldMapperV2()
    return mapper.map_fields(columns, data_domain, source_platform)


# 测试代码
if __name__ == "__main__":
    # 测试用例
    mapper = SmartFieldMapperV2()
    
    # 场景1：shopee商品数据
    columns = [
        "商品名称", "商品", "SKU", "库存数", "价格", 
        "销量", "浏览量", "评分", "状态", "商品ID"
    ]
    
    print("="*60)
    print("测试场景1：Shopee商品数据")
    print("="*60)
    mappings = mapper.map_fields(columns, "products", "shopee")
    
    for orig, mapped in mappings.items():
        print(f"{orig:15} -> {mapped['standard']:20} (置信度={mapped['confidence']:5.1f}%, 方法={mapped['method']})")
    
    stats = mapper.get_mapping_statistics(mappings)
    print(f"\n映射统计:")
    print(f"  总列数: {stats['total_columns']}")
    print(f"  已映射: {stats['mapped_count']}")
    print(f"  未映射: {stats['unmapped_count']}")
    print(f"  映射率: {stats['mapping_rate']}%")
    print(f"  平均置信度: {stats['avg_confidence']}%")

