"""
成本价自动填充服务
从商品主数据自动填充成本价信息
"""

from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import text
import logging

logger = logging.getLogger(__name__)

class CostAutoFillService:
    """成本价自动填充服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_product_cost(self, platform_code: str, shop_id: str, 
                        platform_sku: str) -> Optional[Dict[str, Any]]:
        """获取商品成本信息"""
        try:
            # 查询商品主数据中的成本信息
            result = self.db.execute(text("""
                SELECT 
                    product_id,
                    platform_sku,
                    cost_price,
                    cost_currency,
                    suggested_price,
                    weight_kg,
                    length_cm,
                    product_status
                FROM dim_products 
                WHERE platform_code = :platform_code 
                AND shop_id = :shop_id 
                AND platform_sku = :platform_sku
                AND product_status = 'active'
            """), {
                "platform_code": platform_code,
                "shop_id": shop_id,
                "platform_sku": platform_sku
            })
            
            row = result.fetchone()
            if row:
                return {
                    "product_id": row[0],
                    "platform_sku": row[1],
                    "cost_price": float(row[2]) if row[2] else None,
                    "cost_currency": row[3],
                    "suggested_price": float(row[4]) if row[4] else None,
                    "weight_kg": float(row[5]) if row[5] else None,
                    "length_cm": float(row[6]) if row[6] else None,
                    "product_status": row[7]
                }
            return None
            
        except Exception as e:
            logger.error(f"获取商品成本信息失败: {e}")
            return None
    
    def get_inventory_cost(self, platform_code: str, shop_id: str, 
                          product_id: int) -> Optional[Dict[str, Any]]:
        """获取库存成本信息"""
        try:
            # 查询库存表中的成本信息
            result = self.db.execute(text("""
                SELECT 
                    avg_cost,
                    total_value,
                    quantity_on_hand
                FROM fact_inventory 
                WHERE platform_code = :platform_code 
                AND shop_id = :shop_id 
                AND product_id = :product_id
            """), {
                "platform_code": platform_code,
                "shop_id": shop_id,
                "product_id": product_id
            })
            
            row = result.fetchone()
            if row and row[0]:  # avg_cost不为空
                return {
                    "avg_cost": float(row[0]),
                    "total_value": float(row[1]) if row[1] else None,
                    "quantity_on_hand": int(row[2]) if row[2] else 0
                }
            return None
            
        except Exception as e:
            logger.error(f"获取库存成本信息失败: {e}")
            return None
    
    def auto_fill_cost_for_orders(self, orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为订单数据自动填充成本价"""
        enhanced_orders = []
        
        for order in orders:
            enhanced_order = order.copy()
            
            try:
                platform_code = order.get("platform_code")
                shop_id = order.get("shop_id")
                platform_sku = order.get("platform_sku") or order.get("sku")
                
                if not all([platform_code, shop_id, platform_sku]):
                    logger.warning(f"订单缺少必要字段: {order.get('order_id', 'unknown')}")
                    enhanced_orders.append(enhanced_order)
                    continue
                
                # 获取商品成本信息
                product_cost = self.get_product_cost(platform_code, shop_id, platform_sku)
                
                if product_cost:
                    # 填充成本价
                    if product_cost["cost_price"]:
                        enhanced_order["unit_cost"] = product_cost["cost_price"]
                        enhanced_order["cost_currency"] = product_cost["cost_currency"]
                        
                        # 计算行成本
                        quantity = order.get("quantity", 1)
                        if isinstance(quantity, (int, float)) and quantity > 0:
                            enhanced_order["line_cost"] = product_cost["cost_price"] * quantity
                        
                        # 计算人民币成本（如果有汇率）
                        exchange_rate = order.get("exchange_rate")
                        if exchange_rate and product_cost["cost_currency"] != "CNY":
                            enhanced_order["line_cost_cny"] = enhanced_order["line_cost"] * exchange_rate
                        elif product_cost["cost_currency"] == "CNY":
                            enhanced_order["line_cost_cny"] = enhanced_order["line_cost"]
                    
                    # 填充商品属性
                    if product_cost["weight_kg"]:
                        enhanced_order["weight_kg"] = product_cost["weight_kg"]
                    if product_cost["length_cm"]:
                        enhanced_order["length_cm"] = product_cost["length_cm"]
                    
                    # 填充建议售价
                    if product_cost["suggested_price"]:
                        enhanced_order["suggested_price"] = product_cost["suggested_price"]
                
                # 获取库存成本信息（作为备选）
                if not enhanced_order.get("unit_cost") and product_cost:
                    inventory_cost = self.get_inventory_cost(
                        platform_code, shop_id, product_cost["product_id"]
                    )
                    if inventory_cost and inventory_cost["avg_cost"]:
                        enhanced_order["unit_cost"] = inventory_cost["avg_cost"]
                        enhanced_order["cost_currency"] = "CNY"  # 库存成本通常是人民币
                        
                        # 计算行成本
                        quantity = order.get("quantity", 1)
                        if isinstance(quantity, (int, float)) and quantity > 0:
                            enhanced_order["line_cost"] = inventory_cost["avg_cost"] * quantity
                            enhanced_order["line_cost_cny"] = enhanced_order["line_cost"]
                
                # 计算利润
                if enhanced_order.get("line_cost") and order.get("line_amount"):
                    line_amount = order.get("line_amount", 0)
                    line_cost = enhanced_order.get("line_cost", 0)
                    enhanced_order["line_profit"] = line_amount - line_cost
                    
                    # 计算人民币利润
                    if enhanced_order.get("line_cost_cny") and order.get("line_amount_cny"):
                        line_amount_cny = order.get("line_amount_cny", 0)
                        line_cost_cny = enhanced_order.get("line_cost_cny", 0)
                        enhanced_order["line_profit_cny"] = line_amount_cny - line_cost_cny
                
                enhanced_orders.append(enhanced_order)
                
            except Exception as e:
                logger.error(f"处理订单成本填充失败: {e}")
                enhanced_orders.append(enhanced_order)
        
        return enhanced_orders
    
    def auto_fill_cost_for_inventory(self, inventory_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """为库存数据自动填充成本价"""
        enhanced_inventory = []
        
        for item in inventory_data:
            enhanced_item = item.copy()
            
            try:
                platform_code = item.get("platform_code")
                shop_id = item.get("shop_id")
                platform_sku = item.get("platform_sku") or item.get("sku")
                
                if not all([platform_code, shop_id, platform_sku]):
                    logger.warning(f"库存数据缺少必要字段: {item.get('product_id', 'unknown')}")
                    enhanced_inventory.append(enhanced_item)
                    continue
                
                # 获取商品成本信息
                product_cost = self.get_product_cost(platform_code, shop_id, platform_sku)
                
                if product_cost and product_cost["cost_price"]:
                    # 填充成本价
                    enhanced_item["avg_cost"] = product_cost["cost_price"]
                    
                    # 计算库存总价值
                    quantity = item.get("quantity_on_hand", 0)
                    if isinstance(quantity, (int, float)) and quantity > 0:
                        enhanced_item["total_value"] = product_cost["cost_price"] * quantity
                    
                    # 填充商品属性
                    if product_cost["weight_kg"]:
                        enhanced_item["weight_kg"] = product_cost["weight_kg"]
                    if product_cost["length_cm"]:
                        enhanced_item["length_cm"] = product_cost["length_cm"]
                
                enhanced_inventory.append(enhanced_item)
                
            except Exception as e:
                logger.error(f"处理库存成本填充失败: {e}")
                enhanced_inventory.append(enhanced_item)
        
        return enhanced_inventory
    
    def update_product_cost(self, platform_code: str, shop_id: str, 
                           platform_sku: str, cost_price: float, 
                           cost_currency: str = "CNY") -> bool:
        """更新商品成本价"""
        try:
            # 更新商品主数据中的成本价
            result = self.db.execute(text("""
                UPDATE dim_products 
                SET cost_price = :cost_price, 
                    cost_currency = :cost_currency,
                    updated_at = CURRENT_TIMESTAMP
                WHERE platform_code = :platform_code 
                AND shop_id = :shop_id 
                AND platform_sku = :platform_sku
            """), {
                "platform_code": platform_code,
                "shop_id": shop_id,
                "platform_sku": platform_sku,
                "cost_price": cost_price,
                "cost_currency": cost_currency
            })
            
            self.db.commit()
            return result.rowcount > 0
            
        except Exception as e:
            logger.error(f"更新商品成本价失败: {e}")
            self.db.rollback()
            return False
    
    def batch_update_costs(self, cost_updates: List[Dict[str, Any]]) -> Dict[str, int]:
        """批量更新成本价"""
        success_count = 0
        error_count = 0
        
        for update in cost_updates:
            try:
                platform_code = update.get("platform_code")
                shop_id = update.get("shop_id")
                platform_sku = update.get("platform_sku")
                cost_price = update.get("cost_price")
                cost_currency = update.get("cost_currency", "CNY")
                
                if self.update_product_cost(platform_code, shop_id, platform_sku, 
                                          cost_price, cost_currency):
                    success_count += 1
                else:
                    error_count += 1
                    
            except Exception as e:
                logger.error(f"批量更新成本价失败: {e}")
                error_count += 1
        
        return {
            "success_count": success_count,
            "error_count": error_count,
            "total": len(cost_updates)
        }

def get_cost_auto_fill_service(db: Session) -> CostAutoFillService:
    """获取成本价自动填充服务实例"""
    return CostAutoFillService(db)
