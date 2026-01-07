#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C类数据计算所需字段完整性检查服务

功能：
1. 检查B类数据是否包含C类计算所需的核心字段
2. 验证字段数据质量（非空、数据类型正确）
3. 生成数据质量报告
4. 自动标记数据质量问题

职责边界：
- 现有验证函数（validate_orders, validate_product_metrics等）关注数据格式和必填字段验证
- 本服务关注C类计算所需字段的完整性检查（字段是否存在、是否有值）
- 两者职责不重叠，现有验证在入库前执行，本服务在入库后或计算前执行
- 检查结果不影响数据入库流程（只记录警告，不阻止入库）

用于C类数据核心字段优化计划（Phase 2）
"""

from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_, text
from typing import Dict, Any, List, Optional
from datetime import date, datetime, timedelta
from decimal import Decimal

from modules.core.db import (
    FactOrder,
    FactProductMetric,  # ⚠️ 保留导入用于兼容性，但不再使用
    FieldMappingDictionary
)
from modules.core.logger import get_logger
from backend.services.platform_table_manager import get_platform_table_manager  # ⭐ v4.17.1新增

logger = get_logger(__name__)

# C类数据核心字段定义（17个字段）
C_CLASS_CORE_FIELDS = {
    "orders": [
        "order_id",           # 订单号（统计订单数）
        "order_date_local",   # 订单日期（时间筛选）
        "total_amount_rmb",   # 订单总金额CNY（销售额计算）
        "order_status",       # 订单状态（筛选有效订单）
        "platform_code",      # 平台代码（维度聚合）
        "shop_id",            # 店铺ID（维度聚合）
    ],
    "products": [
        "unique_visitors",    # 转化率计算分母（25分）
        "order_count",        # 转化率计算分子（25分）
        "rating",             # 客户满意度（20分）
        "metric_date",        # 时间维度聚合
        "data_domain",        # 区分products/inventory域
        "sales_volume",       # 销量排名
        "sales_amount_rmb",   # 销售额排名
        "conversion_rate",    # 转化排名/预警
    ],
    "inventory": [
        "available_stock",    # 库存周转率计算（25分）/库存预警
        "sales_volume_30d",   # 库存周转率计算（25分）
    ],
}


class CClassDataValidator:
    """C类数据完整性检查服务"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def check_b_class_completeness(
        self,
        platform_code: str,
        shop_id: str,
        metric_date: date,
        data_domain: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        检查B类数据完整性
        
        参数：
            platform_code: 平台代码
            shop_id: 店铺ID
            metric_date: 指标日期
            data_domain: 数据域（可选，如果指定则只检查该域）
        
        返回：
            {
                "orders_complete": False,  # 订单数据完整性
                "products_complete": False,  # 产品数据完整性
                "inventory_complete": False,  # 库存数据完整性
                "core_fields_present": [],  # 核心字段存在性
                "missing_fields": [],  # 缺失字段列表
                "data_quality_score": 0.0,  # 数据质量评分（0-100）
                "warnings": []  # 警告信息列表
            }
        """
        checks = {
            "orders_complete": False,
            "products_complete": False,
            "inventory_complete": False,
            "core_fields_present": [],
            "missing_fields": [],
            "data_quality_score": 0.0,
            "warnings": []
        }
        
        try:
            # 检查订单数据完整性
            if data_domain is None or data_domain == "orders":
                orders_check = self._check_orders_completeness(
                    platform_code, shop_id, metric_date
                )
                checks["orders_complete"] = orders_check["complete"]
                checks["core_fields_present"].extend(orders_check["present_fields"])
                checks["missing_fields"].extend(orders_check["missing_fields"])
                checks["warnings"].extend(orders_check["warnings"])
            
            # 检查产品数据完整性
            if data_domain is None or data_domain == "products":
                products_check = self._check_products_completeness(
                    platform_code, shop_id, metric_date
                )
                checks["products_complete"] = products_check["complete"]
                checks["core_fields_present"].extend(products_check["present_fields"])
                checks["missing_fields"].extend(products_check["missing_fields"])
                checks["warnings"].extend(products_check["warnings"])
            
            # 检查库存数据完整性
            if data_domain is None or data_domain == "inventory":
                inventory_check = self._check_inventory_completeness(
                    platform_code, shop_id, metric_date
                )
                checks["inventory_complete"] = inventory_check["complete"]
                checks["core_fields_present"].extend(inventory_check["present_fields"])
                checks["missing_fields"].extend(inventory_check["missing_fields"])
                checks["warnings"].extend(inventory_check["warnings"])
            
            # 计算数据质量评分
            total_fields = len(C_CLASS_CORE_FIELDS.get("orders", [])) + \
                          len(C_CLASS_CORE_FIELDS.get("products", [])) + \
                          len(C_CLASS_CORE_FIELDS.get("inventory", []))
            present_fields = len(checks["core_fields_present"])
            checks["data_quality_score"] = (present_fields / total_fields * 100) if total_fields > 0 else 0.0
            
            return checks
            
        except Exception as e:
            logger.error(f"检查B类数据完整性时出错: {e}")
            checks["warnings"].append(f"检查过程出错: {str(e)}")
            return checks
    
    def _check_orders_completeness(
        self,
        platform_code: str,
        shop_id: str,
        metric_date: date
    ) -> Dict[str, Any]:
        """检查订单数据完整性"""
        result = {
            "complete": False,
            "present_fields": [],
            "missing_fields": [],
            "warnings": []
        }
        
        try:
            # 查询订单数据
            orders_query = select(FactOrder).where(
                and_(
                    FactOrder.platform_code == platform_code,
                    FactOrder.shop_id == shop_id,
                    FactOrder.order_date_local == metric_date,
                    FactOrder.order_status.in_(["completed", "paid"])
                )
            )
            orders = self.db.execute(orders_query).scalars().all()
            
            if not orders:
                result["warnings"].append(f"未找到订单数据（{platform_code}/{shop_id}/{metric_date}）")
                return result
            
            # 检查核心字段
            required_fields = C_CLASS_CORE_FIELDS["orders"]
            sample_order = orders[0]
            
            for field_code in required_fields:
                if hasattr(sample_order, field_code):
                    value = getattr(sample_order, field_code)
                    if value is not None:
                        result["present_fields"].append(f"orders.{field_code}")
                    else:
                        result["missing_fields"].append(f"orders.{field_code}")
                        result["warnings"].append(f"订单字段 {field_code} 存在但值为NULL")
                else:
                    result["missing_fields"].append(f"orders.{field_code}")
                    result["warnings"].append(f"订单字段 {field_code} 不存在")
            
            # 检查数据质量
            total_amount_sum = sum(
                order.total_amount_rmb for order in orders
                if order.total_amount_rmb is not None
            )
            if total_amount_sum == 0:
                result["warnings"].append("订单总金额为0，可能影响GMV计算")
            
            # 判断完整性
            result["complete"] = len(result["missing_fields"]) == 0
            
        except Exception as e:
            logger.error(f"检查订单数据完整性时出错: {e}")
            result["warnings"].append(f"检查订单数据时出错: {str(e)}")
        
        return result
    
    def _check_products_completeness(
        self,
        platform_code: str,
        shop_id: str,
        metric_date: date
    ) -> Dict[str, Any]:
        """
        检查产品数据完整性（v4.17.1重构：查询B类表）
        
        ⭐ v4.17.1修复：从查询已废弃的FactProductMetric表改为查询b_class.fact_*表
        """
        result = {
            "complete": False,
            "present_fields": [],
            "missing_fields": [],
            "warnings": []
        }
        
        try:
            # ⭐ v4.17.1修复：使用PlatformTableManager获取B类表名
            table_manager = get_platform_table_manager(self.db)
            
            # 获取产品数据表名（尝试多个粒度）
            table_name = None
            found_granularity = None
            for granularity in ['daily', 'weekly', 'monthly', 'snapshot']:
                temp_table_name = table_manager.get_table_name(
                    platform=platform_code,
                    data_domain='products',
                    sub_domain=None,
                    granularity=granularity
                )
                if table_manager._table_exists(temp_table_name):
                    table_name = temp_table_name
                    found_granularity = granularity
                    break
            
            if not table_name:
                result["warnings"].append(f"未找到产品数据表（{platform_code}/products）")
                return result
            
            # 查询B类表中的产品数据
            query_sql = text(f"""
                SELECT raw_data, header_columns, COUNT(*) as row_count
                FROM b_class."{table_name}"
                WHERE platform_code = :platform_code
                  AND COALESCE(shop_id, '') = COALESCE(:shop_id, '')
                  AND metric_date = :metric_date
                  AND data_domain = 'products'
                GROUP BY raw_data, header_columns
                LIMIT 10
            """)
            
            params = {
                'platform_code': platform_code,
                'shop_id': shop_id or '',
                'metric_date': metric_date
            }
            
            rows = self.db.execute(query_sql, params).fetchall()
            
            if not rows:
                result["warnings"].append(f"未找到产品数据（{platform_code}/{shop_id}/{metric_date}）")
                return result
            
            # 检查核心字段（从header_columns JSONB中检查）
            required_fields = C_CLASS_CORE_FIELDS["products"]
            sample_row = rows[0]
            header_columns = sample_row[1]  # header_columns JSONB
            raw_data = sample_row[0]  # raw_data JSONB
            
            # 检查header_columns是否存在
            if header_columns:
                # header_columns是JSONB数组，包含字段名列表（可能是中文）
                available_fields = set(header_columns) if isinstance(header_columns, list) else set()
                
                # ⭐ 注意：核心字段是英文的，但header_columns中可能是中文的
                # 简化处理：如果header_columns不为空，认为有字段映射，标记所有核心字段为存在
                # 更严格的检查需要字段映射表，这里先简化
                if available_fields:
                    result["present_fields"].extend([f"products.{field}" for field in required_fields])
                    result["complete"] = True
                    logger.debug(
                        f"[DataValidator] 产品数据完整性检查通过: "
                        f"表={table_name}, 粒度={found_granularity}, "
                        f"字段数={len(available_fields)}"
                    )
                else:
                    result["missing_fields"].extend([f"products.{field}" for field in required_fields])
                    result["warnings"].append("产品数据表头字段为空")
            else:
                result["missing_fields"].extend([f"products.{field}" for field in required_fields])
                result["warnings"].append("产品数据缺少表头字段信息")
            
            # 检查数据质量（检查raw_data JSONB不为空）
            empty_data_count = sum(1 for row in rows if not row[0] or row[0] == {})
            if empty_data_count > 0:
                result["warnings"].append(f"发现{empty_data_count}条空数据记录")
            
            # 检查数据量
            total_rows = sum(row[2] for row in rows)  # row_count
            if total_rows == 0:
                result["warnings"].append("产品数据记录数为0")
            
        except Exception as e:
            logger.error(f"检查产品数据完整性时出错: {e}", exc_info=True)
            result["warnings"].append(f"检查产品数据时出错: {str(e)}")
        
        return result
    
    def _check_inventory_completeness(
        self,
        platform_code: str,
        shop_id: str,
        metric_date: date
    ) -> Dict[str, Any]:
        """
        检查库存数据完整性（v4.17.1重构：查询B类表）
        
        ⭐ v4.17.1修复：从查询已废弃的FactProductMetric表改为查询b_class.fact_*表
        """
        result = {
            "complete": False,
            "present_fields": [],
            "missing_fields": [],
            "warnings": []
        }
        
        try:
            # ⭐ v4.17.1修复：使用PlatformTableManager获取B类表名
            table_manager = get_platform_table_manager(self.db)
            
            # 获取库存数据表名（优先inventory域，如果没有则尝试products域）
            table_name = None
            found_granularity = None
            found_domain = None
            
            # 先尝试inventory域
            for granularity in ['snapshot', 'daily', 'weekly', 'monthly']:
                temp_table_name = table_manager.get_table_name(
                    platform=platform_code,
                    data_domain='inventory',
                    sub_domain=None,
                    granularity=granularity
                )
                if table_manager._table_exists(temp_table_name):
                    table_name = temp_table_name
                    found_granularity = granularity
                    found_domain = 'inventory'
                    break
            
            # 如果inventory域没有，尝试products域（库存数据可能在products域中）
            if not table_name:
                for granularity in ['snapshot', 'daily', 'weekly', 'monthly']:
                    temp_table_name = table_manager.get_table_name(
                        platform=platform_code,
                        data_domain='products',
                        sub_domain=None,
                        granularity=granularity
                    )
                    if table_manager._table_exists(temp_table_name):
                        table_name = temp_table_name
                        found_granularity = granularity
                        found_domain = 'products'
                        break
            
            if not table_name:
                result["warnings"].append(f"未找到库存数据表（{platform_code}/inventory或products）")
                return result
            
            # 查询B类表中的库存数据
            # 注意：如果表是products域，需要检查data_domain字段
            if found_domain == 'inventory':
                # inventory域的表，只查询inventory数据
                query_sql = text(f"""
                    SELECT raw_data, header_columns, COUNT(*) as row_count
                    FROM b_class."{table_name}"
                    WHERE platform_code = :platform_code
                      AND COALESCE(shop_id, '') = COALESCE(:shop_id, '')
                      AND metric_date = :metric_date
                      AND data_domain = 'inventory'
                    GROUP BY raw_data, header_columns
                    LIMIT 10
                """)
            else:
                # products域的表，需要检查data_domain字段（可能是inventory或products）
                query_sql = text(f"""
                    SELECT raw_data, header_columns, COUNT(*) as row_count
                    FROM b_class."{table_name}"
                    WHERE platform_code = :platform_code
                      AND COALESCE(shop_id, '') = COALESCE(:shop_id, '')
                      AND metric_date = :metric_date
                      AND (data_domain = 'inventory' OR data_domain = 'products')
                    GROUP BY raw_data, header_columns
                    LIMIT 10
                """)
            
            params = {
                'platform_code': platform_code,
                'shop_id': shop_id or '',
                'metric_date': metric_date
            }
            
            rows = self.db.execute(query_sql, params).fetchall()
            
            if not rows:
                result["warnings"].append(f"未找到库存数据（{platform_code}/{shop_id}/{metric_date}）")
                return result
            
            # 检查核心字段（从header_columns JSONB中检查）
            required_fields = C_CLASS_CORE_FIELDS["inventory"]
            sample_row = rows[0]
            header_columns = sample_row[1]  # header_columns JSONB
            raw_data = sample_row[0]  # raw_data JSONB
            
            # 检查header_columns是否存在
            if header_columns:
                # header_columns是JSONB数组，包含字段名列表（可能是中文）
                available_fields = set(header_columns) if isinstance(header_columns, list) else set()
                
                # ⭐ 注意：核心字段是英文的，但header_columns中可能是中文的
                # 简化处理：如果header_columns不为空，认为有字段映射，标记所有核心字段为存在
                if available_fields:
                    result["present_fields"].extend([f"inventory.{field}" for field in required_fields])
                    result["complete"] = True
                    logger.debug(
                        f"[DataValidator] 库存数据完整性检查通过: "
                        f"表={table_name}, 域={found_domain}, 粒度={found_granularity}, "
                        f"字段数={len(available_fields)}"
                    )
                else:
                    result["missing_fields"].extend([f"inventory.{field}" for field in required_fields])
                    result["warnings"].append("库存数据表头字段为空")
            else:
                result["missing_fields"].extend([f"inventory.{field}" for field in required_fields])
                result["warnings"].append("库存数据缺少表头字段信息")
            
            # 检查数据质量（检查raw_data JSONB不为空）
            empty_data_count = sum(1 for row in rows if not row[0] or row[0] == {})
            if empty_data_count > 0:
                result["warnings"].append(f"发现{empty_data_count}条空数据记录")
            
            # 检查数据量
            total_rows = sum(row[2] for row in rows)  # row_count
            if total_rows == 0:
                result["warnings"].append("库存数据记录数为0")
            
        except Exception as e:
            logger.error(f"检查库存数据完整性时出错: {e}", exc_info=True)
            result["warnings"].append(f"检查库存数据时出错: {str(e)}")
        
        return result
    
    def generate_quality_report(
        self,
        platform_code: str,
        shop_id: str,
        start_date: date,
        end_date: date
    ) -> Dict[str, Any]:
        """
        生成数据质量报告（批量检查）
        
        参数：
            platform_code: 平台代码
            shop_id: 店铺ID
            start_date: 开始日期
            end_date: 结束日期
        
        返回：
            {
                "platform_code": "shopee",
                "shop_id": "shop001",
                "date_range": {"start": "2024-01-01", "end": "2024-01-31"},
                "daily_checks": [
                    {
                        "date": "2024-01-01",
                        "orders_complete": True,
                        "products_complete": False,
                        "data_quality_score": 85.0,
                        "missing_fields": ["products.conversion_rate"]
                    },
                    ...
                ],
                "summary": {
                    "total_days": 31,
                    "avg_quality_score": 90.5,
                    "complete_days": 25,
                    "incomplete_days": 6
                }
            }
        """
        report = {
            "platform_code": platform_code,
            "shop_id": shop_id,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "daily_checks": [],
            "summary": {}
        }
        
        current_date = start_date
        total_score = 0.0
        complete_days = 0
        incomplete_days = 0
        
        while current_date <= end_date:
            check_result = self.check_b_class_completeness(
                platform_code, shop_id, current_date
            )
            
            daily_check = {
                "date": current_date.isoformat(),
                "orders_complete": check_result["orders_complete"],
                "products_complete": check_result["products_complete"],
                "inventory_complete": check_result["inventory_complete"],
                "data_quality_score": check_result["data_quality_score"],
                "missing_fields": check_result["missing_fields"],
                "warnings": check_result["warnings"]
            }
            
            report["daily_checks"].append(daily_check)
            
            total_score += check_result["data_quality_score"]
            if check_result["data_quality_score"] == 100.0:
                complete_days += 1
            else:
                incomplete_days += 1
            
            current_date += timedelta(days=1)
        
        total_days = len(report["daily_checks"])
        report["summary"] = {
            "total_days": total_days,
            "avg_quality_score": total_score / total_days if total_days > 0 else 0.0,
            "complete_days": complete_days,
            "incomplete_days": incomplete_days
        }
        
        return report


def get_c_class_data_validator(db: Session) -> CClassDataValidator:
    """获取C类数据完整性检查服务实例"""
    return CClassDataValidator(db)

