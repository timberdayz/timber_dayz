"""
业务自动化服务
包含：订单入库自动流程、库存管理、财务管理
"""

from typing import Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timedelta
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class OrderAutomation:
    """订单业务自动化"""
    
    @staticmethod
    def on_order_created(db: Session, order_id: int) -> Dict[str, Any]:
        """
        订单创建后自动触发流程
        1. 扣减库存
        2. 创建应收账款
        3. 计算利润
        4. 触发物化视图刷新
        """
        try:
            logger.info(f"[AUTO] Processing order creation: order_id={order_id}")
            
            # 查询订单信息
            order = db.execute(text("""
                SELECT
                    id,
                    platform_code,
                    shop_id,
                    order_id as platform_order_id,
                    product_surrogate_id,
                    qty,
                    gmv_cny,
                    inventory_deducted,
                    is_invoiced
                FROM fact_sales_orders
                WHERE id = :order_id
            """), {"order_id": order_id}).fetchone()
            
            if not order:
                return {"success": False, "error": "Order not found"}
            
            results = {}
            
            # 1. 扣减库存（如果还未扣减）
            if not order.inventory_deducted:
                result = OrderAutomation._deduct_inventory(db, order)
                results["inventory"] = result
            
            # 2. 创建应收账款（如果还未创建）
            if not order.is_invoiced:
                result = OrderAutomation._create_accounts_receivable(db, order)
                results["accounts_receivable"] = result
            
            # 3. 计算利润
            result = OrderAutomation._calculate_profit(db, order)
            results["profit"] = result
            
            return {"success": True, "results": results}
            
        except Exception as e:
            logger.error(f"[ERROR] Order automation failed: {e}")
            db.rollback()
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _deduct_inventory(db: Session, order) -> Dict[str, Any]:
        """扣减库存"""
        try:
            # 查询库存
            inventory = db.execute(text("""
                SELECT
                    inventory_id,
                    quantity_available,
                    quantity_reserved,
                    avg_cost
                FROM fact_inventory
                WHERE platform_code = :platform
                AND shop_id = :shop_id
                AND product_id = :product_id
                LIMIT 1
            """), {
                "platform": order.platform_code,
                "shop_id": order.shop_id,
                "product_id": order.product_surrogate_id
            }).fetchone()
            
            if not inventory:
                logger.warning(f"[WARN] No inventory found for product {order.product_surrogate_id}")
                return {"success": False, "error": "No inventory record"}
            
            # 检查库存是否充足
            if inventory.quantity_available < order.qty:
                logger.warning(f"[WARN] Insufficient inventory: available={inventory.quantity_available}, required={order.qty}")
                # 仍然允许扣减（负库存）
            
            # 扣减库存
            db.execute(text("""
                UPDATE fact_inventory
                SET
                    quantity_available = quantity_available - :qty,
                    quantity_reserved = quantity_reserved + :qty,
                    last_updated = NOW()
                WHERE inventory_id = :inventory_id
            """), {
                "qty": order.qty,
                "inventory_id": inventory.inventory_id
            })
            
            # 记录库存流水
            db.execute(text("""
                INSERT INTO fact_inventory_transactions (
                    inventory_id,
                    product_id,
                    transaction_type,
                    reference_type,
                    reference_id,
                    quantity_change,
                    quantity_before,
                    quantity_after,
                    unit_cost,
                    transaction_time
                ) VALUES (
                    :inventory_id,
                    :product_id,
                    'sale',
                    'order',
                    :order_id,
                    :qty_change,
                    :qty_before,
                    :qty_after,
                    :unit_cost,
                    NOW()
                )
            """), {
                "inventory_id": inventory.inventory_id,
                "product_id": order.product_surrogate_id,
                "order_id": str(order.platform_order_id),
                "qty_change": -order.qty,
                "qty_before": inventory.quantity_available,
                "qty_after": inventory.quantity_available - order.qty,
                "unit_cost": inventory.avg_cost
            })
            
            # 更新订单状态
            db.execute(text("""
                UPDATE fact_sales_orders
                SET inventory_deducted = TRUE,
                    updated_at = NOW()
                WHERE id = :order_id
            """), {"order_id": order.id})
            
            db.commit()
            
            logger.info(f"[OK] Inventory deducted: {order.qty} units")
            return {
                "success": True,
                "quantity_deducted": order.qty,
                "remaining_available": inventory.quantity_available - order.qty
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to deduct inventory: {e}")
            db.rollback()
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _create_accounts_receivable(db: Session, order) -> Dict[str, Any]:
        """创建应收账款"""
        try:
            # 计算应收金额和到期日
            ar_amount = order.gmv_cny or 0
            invoice_date = datetime.now().date()
            due_date = invoice_date + timedelta(days=30)  # 默认30天账期
            
            # 创建应收账款记录
            db.execute(text("""
                INSERT INTO fact_accounts_receivable (
                    order_id,
                    platform_code,
                    shop_id,
                    ar_amount_cny,
                    received_amount_cny,
                    outstanding_amount_cny,
                    invoice_date,
                    due_date,
                    payment_terms,
                    ar_status
                ) VALUES (
                    :order_id,
                    :platform,
                    :shop_id,
                    :ar_amount,
                    0,
                    :ar_amount,
                    :invoice_date,
                    :due_date,
                    'Net 30',
                    'pending'
                )
            """), {
                "order_id": order.id,
                "platform": order.platform_code,
                "shop_id": order.shop_id,
                "ar_amount": ar_amount,
                "invoice_date": invoice_date,
                "due_date": due_date
            })
            
            # 更新订单开票状态
            db.execute(text("""
                UPDATE fact_sales_orders
                SET is_invoiced = TRUE,
                    updated_at = NOW()
                WHERE id = :order_id
            """), {"order_id": order.id})
            
            db.commit()
            
            logger.info(f"[OK] Accounts receivable created: CNY {ar_amount}")
            return {
                "success": True,
                "ar_amount": float(ar_amount),
                "due_date": due_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to create AR: {e}")
            db.rollback()
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def _calculate_profit(db: Session, order) -> Dict[str, Any]:
        """计算订单利润"""
        try:
            # 查询商品成本（从库存表）
            inventory = db.execute(text("""
                SELECT avg_cost
                FROM fact_inventory
                WHERE platform_code = :platform
                AND shop_id = :shop_id
                AND product_id = :product_id
                LIMIT 1
            """), {
                "platform": order.platform_code,
                "shop_id": order.shop_id,
                "product_id": order.product_surrogate_id
            }).fetchone()
            
            if not inventory or not inventory.avg_cost:
                logger.warning(f"[WARN] No cost found for product {order.product_surrogate_id}")
                return {"success": False, "error": "No cost data"}
            
            # 计算成本和利润
            cost_amount_cny = Decimal(str(inventory.avg_cost)) * Decimal(str(order.qty))
            gross_profit_cny = Decimal(str(order.gmv_cny or 0)) - cost_amount_cny
            
            # 查询订单相关费用
            fees = db.execute(text("""
                SELECT SUM(amount_cny) as total_fees
                FROM fact_expenses
                WHERE order_id = :order_id
            """), {"order_id": order.id}).fetchone()
            
            total_fees = Decimal(str(fees.total_fees or 0))
            net_profit_cny = gross_profit_cny - total_fees
            
            # 更新订单利润字段
            db.execute(text("""
                UPDATE fact_sales_orders
                SET
                    cost_amount_cny = :cost,
                    gross_profit_cny = :gross_profit,
                    net_profit_cny = :net_profit,
                    updated_at = NOW()
                WHERE id = :order_id
            """), {
                "cost": float(cost_amount_cny),
                "gross_profit": float(gross_profit_cny),
                "net_profit": float(net_profit_cny),
                "order_id": order.id
            })
            
            db.commit()
            
            logger.info(f"[OK] Profit calculated: gross={gross_profit_cny}, net={net_profit_cny}")
            return {
                "success": True,
                "cost_amount_cny": float(cost_amount_cny),
                "gross_profit_cny": float(gross_profit_cny),
                "net_profit_cny": float(net_profit_cny)
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to calculate profit: {e}")
            db.rollback()
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def on_order_cancelled(db: Session, order_id: int) -> Dict[str, Any]:
        """
        订单取消后自动恢复库存
        """
        try:
            logger.info(f"[AUTO] Processing order cancellation: order_id={order_id}")
            
            # 查询订单信息
            order = db.execute(text("""
                SELECT
                    id,
                    platform_code,
                    shop_id,
                    product_surrogate_id,
                    qty,
                    inventory_deducted
                FROM fact_sales_orders
                WHERE id = :order_id
            """), {"order_id": order_id}).fetchone()
            
            if not order:
                return {"success": False, "error": "Order not found"}
            
            # 如果库存已扣减，恢复库存
            if order.inventory_deducted:
                db.execute(text("""
                    UPDATE fact_inventory
                    SET
                        quantity_available = quantity_available + :qty,
                        quantity_reserved = quantity_reserved - :qty,
                        last_updated = NOW()
                    WHERE platform_code = :platform
                    AND shop_id = :shop_id
                    AND product_id = :product_id
                """), {
                    "qty": order.qty,
                    "platform": order.platform_code,
                    "shop_id": order.shop_id,
                    "product_id": order.product_surrogate_id
                })
                
                # 记录库存流水
                db.execute(text("""
                    INSERT INTO fact_inventory_transactions (
                        product_id,
                        transaction_type,
                        reference_type,
                        reference_id,
                        quantity_change,
                        transaction_time
                    ) VALUES (
                        :product_id,
                        'cancel_return',
                        'order',
                        :order_id,
                        :qty,
                        NOW()
                    )
                """), {
                    "product_id": order.product_surrogate_id,
                    "order_id": str(order.id),
                    "qty": order.qty
                })
                
                # 更新订单状态
                db.execute(text("""
                    UPDATE fact_sales_orders
                    SET inventory_deducted = FALSE,
                        status = 'cancelled',
                        updated_at = NOW()
                    WHERE id = :order_id
                """), {"order_id": order_id})
                
                db.commit()
                
                logger.info(f"[OK] Inventory restored: {order.qty} units")
                return {"success": True, "quantity_restored": order.qty}
            else:
                # 只更新状态
                db.execute(text("""
                    UPDATE fact_sales_orders
                    SET status = 'cancelled',
                        updated_at = NOW()
                    WHERE id = :order_id
                """), {"order_id": order_id})
                db.commit()
                
                return {"success": True, "quantity_restored": 0}
                
        except Exception as e:
            logger.error(f"[ERROR] Failed to cancel order: {e}")
            db.rollback()
            return {"success": False, "error": str(e)}


class InventoryAutomation:
    """库存管理自动化"""
    
    @staticmethod
    def check_low_stock_alert(db: Session) -> List[Dict[str, Any]]:
        """检查低库存商品"""
        try:
            result = db.execute(text("""
                SELECT
                    i.platform_code,
                    i.shop_id,
                    p.platform_sku,
                    p.title,
                    i.quantity_available,
                    i.safety_stock,
                    (i.safety_stock - i.quantity_available) as shortage
                FROM fact_inventory i
                JOIN dim_product p ON i.product_id = p.product_surrogate_id
                WHERE i.quantity_available < i.safety_stock
                ORDER BY shortage DESC
            """))
            
            low_stock_products = []
            for row in result:
                low_stock_products.append({
                    "platform": row[0],
                    "shop": row[1],
                    "sku": row[2],
                    "title": row[3],
                    "available": row[4],
                    "safety_stock": row[5],
                    "shortage": row[6]
                })
            
            return low_stock_products
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to check low stock: {e}")
            return []
    
    @staticmethod
    def adjust_inventory(
        db: Session,
        product_id: int,
        platform_code: str,
        shop_id: str,
        quantity_change: int,
        operator_id: str,
        notes: str = None
    ) -> Dict[str, Any]:
        """
        库存调整（盘点、补货等）
        """
        try:
            # 查询当前库存
            inventory = db.execute(text("""
                SELECT inventory_id, quantity_on_hand
                FROM fact_inventory
                WHERE platform_code = :platform
                AND shop_id = :shop_id
                AND product_id = :product_id
                LIMIT 1
            """), {
                "platform": platform_code,
                "shop_id": shop_id,
                "product_id": product_id
            }).fetchone()
            
            if not inventory:
                return {"success": False, "error": "Inventory not found"}
            
            # 更新库存
            db.execute(text("""
                UPDATE fact_inventory
                SET
                    quantity_on_hand = quantity_on_hand + :change,
                    quantity_available = quantity_available + :change,
                    last_updated = NOW()
                WHERE inventory_id = :inventory_id
            """), {
                "change": quantity_change,
                "inventory_id": inventory.inventory_id
            })
            
            # 记录流水
            db.execute(text("""
                INSERT INTO fact_inventory_transactions (
                    inventory_id,
                    product_id,
                    transaction_type,
                    quantity_change,
                    quantity_before,
                    quantity_after,
                    operator_id,
                    notes,
                    transaction_time
                ) VALUES (
                    :inventory_id,
                    :product_id,
                    'adjust',
                    :change,
                    :before,
                    :after,
                    :operator,
                    :notes,
                    NOW()
                )
            """), {
                "inventory_id": inventory.inventory_id,
                "product_id": product_id,
                "change": quantity_change,
                "before": inventory.quantity_on_hand,
                "after": inventory.quantity_on_hand + quantity_change,
                "operator": operator_id,
                "notes": notes
            })
            
            db.commit()
            
            return {
                "success": True,
                "quantity_before": inventory.quantity_on_hand,
                "quantity_after": inventory.quantity_on_hand + quantity_change
            }
            
        except Exception as e:
            logger.error(f"[ERROR] Failed to adjust inventory: {e}")
            db.rollback()
            return {"success": False, "error": str(e)}


# v4.17.0: 财务域表已删除，FinanceAutomation类已废弃
# class FinanceAutomation:
#     """财务管理自动化"""
#     
#     @staticmethod
#     def record_payment(
#         db: Session,
#         ar_id: int,
#         receipt_amount: Decimal,
#         payment_method: str,
#         receipt_date: datetime.date
#     ) -> Dict[str, Any]:
#         """
#         记录收款并自动核销应收账款
#         """
#         try:
#             # 查询应收账款
#             ar = db.execute(text("""
#                 SELECT
#                     ar_id,
#                     outstanding_amount_cny,
#                     ar_status
#                 FROM fact_accounts_receivable
#                 WHERE ar_id = :ar_id
#             """), {"ar_id": ar_id}).fetchone()
#             
#             if not ar:
#                 return {"success": False, "error": "AR not found"}
#             
#             # 记录收款
#             db.execute(text("""
#                 INSERT INTO fact_payment_receipts (
#                     ar_id,
#                     receipt_date,
#                     receipt_amount_cny,
#                     payment_method
#                 ) VALUES (
#                     :ar_id,
#                     :receipt_date,
#                     :amount,
#                     :method
#                 )
#             """), {
#                 "ar_id": ar_id,
#                 "receipt_date": receipt_date,
#                 "amount": float(receipt_amount),
#                 "method": payment_method
#             })
#             
#             # 更新应收账款
#             new_received = db.execute(text("""
#                 SELECT SUM(receipt_amount_cny)
#                 FROM fact_payment_receipts
#                 WHERE ar_id = :ar_id
#             """), {"ar_id": ar_id}).scalar() or 0
#             
#             new_outstanding = ar.outstanding_amount_cny - Decimal(str(new_received))
#             new_status = 'paid' if new_outstanding <= 0 else 'partial'
#             
#             db.execute(text("""
#                 UPDATE fact_accounts_receivable
#                 SET
#                     received_amount_cny = :received,
#                     outstanding_amount_cny = :outstanding,
#                     ar_status = :status,
#                     last_payment_date = :payment_date,
#                     updated_at = NOW()
#                 WHERE ar_id = :ar_id
#             """), {
#                 "received": float(new_received),
#                 "outstanding": max(0, float(new_outstanding)),
#                 "status": new_status,
#                 "payment_date": receipt_date,
#                 "ar_id": ar_id
#             })
#             
#             # 如果全额收款，更新订单状态
#             if new_status == 'paid':
#                 db.execute(text("""
#                     UPDATE fact_sales_orders
#                     SET is_payment_received = TRUE,
#                         updated_at = NOW()
#                     WHERE id = (
#                         SELECT order_id FROM fact_accounts_receivable WHERE ar_id = :ar_id
#                     )
#                 """), {"ar_id": ar_id})
#             
#             db.commit()
#             
#             return {
#                 "success": True,
#                 "received_amount": float(receipt_amount),
#                 "new_outstanding": max(0, float(new_outstanding)),
#                 "status": new_status
#             }
#             
#         except Exception as e:
#             logger.error(f"[ERROR] Failed to record payment: {e}")
#             db.rollback()
#             return {"success": False, "error": str(e)}

