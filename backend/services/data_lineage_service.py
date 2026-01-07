#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据血缘追踪服务（Data Lineage Service）

v4.12.0新增：
- 数据血缘追踪（数据来源、处理过程、目标表）
- 数据影响分析（下游影响、上游依赖）
- 复用现有字段和表，不创建新表

职责：
- 追踪数据流转（使用ingest_task_id和file_id）
- 存储血缘信息（使用catalog_files.file_metadata）
- 提供数据影响分析
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_
import json

from modules.core.db import CatalogFile, StagingOrders, StagingProductMetrics, StagingInventory
from modules.core.db import FactOrder, FactOrderItem, FactProductMetric
from modules.core.logger import get_logger

logger = get_logger(__name__)


class DataLineageService:
    """
    数据血缘追踪服务
    
    职责：
    - 追踪数据流转（使用ingest_task_id和file_id）
    - 存储血缘信息（使用catalog_files.file_metadata）
    - 提供数据影响分析
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def record_lineage(
        self,
        file_id: int,
        task_id: str,
        source_info: Dict[str, Any],
        processing_steps: List[Dict[str, Any]],
        target_tables: List[str]
    ) -> None:
        """
        记录数据血缘信息
        
        Args:
            file_id: 文件ID
            task_id: 同步任务ID
            source_info: 数据源信息
            processing_steps: 处理步骤列表
            target_tables: 目标表列表
        """
        try:
            # 获取文件记录
            catalog_file = self.db.query(CatalogFile).filter(
                CatalogFile.id == file_id
            ).first()
            
            if not catalog_file:
                logger.warning(f"[DataLineage] File {file_id} not found")
                return
            
            # 获取或创建lineage元数据
            metadata = catalog_file.file_metadata if isinstance(catalog_file.file_metadata, dict) else {}
            lineage_info = metadata.get("lineage", {})
            
            # 记录血缘信息
            lineage_info[task_id] = {
                "source": source_info,
                "processing_steps": processing_steps,
                "target_tables": target_tables,
                "recorded_at": self._get_current_timestamp(),
            }
            
            # 更新元数据
            metadata["lineage"] = lineage_info
            catalog_file.file_metadata = metadata
            
            self.db.commit()
            
            logger.info(f"[DataLineage] Recorded lineage for file {file_id}, task {task_id}")
            
        except Exception as e:
            logger.error(f"[DataLineage] Failed to record lineage: {e}", exc_info=True)
            self.db.rollback()
    
    def get_file_lineage(
        self,
        file_id: int
    ) -> Dict[str, Any]:
        """
        获取文件的数据血缘
        
        Args:
            file_id: 文件ID
            
        Returns:
            数据血缘信息字典
        """
        try:
            catalog_file = self.db.query(CatalogFile).filter(
                CatalogFile.id == file_id
            ).first()
            
            if not catalog_file:
                return {}
            
            metadata = catalog_file.file_metadata if isinstance(catalog_file.file_metadata, dict) else {}
            lineage_info = metadata.get("lineage", {})
            
            return lineage_info
            
        except Exception as e:
            logger.error(f"[DataLineage] Failed to get file lineage: {e}", exc_info=True)
            return {}
    
    def get_task_lineage(
        self,
        task_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取任务的数据血缘
        
        Args:
            task_id: 同步任务ID
            
        Returns:
            数据血缘信息字典，如果不存在则返回None
        """
        try:
            # 通过ingest_task_id查找staging表
            staging_orders = self.db.query(StagingOrders).filter(
                StagingOrders.ingest_task_id == task_id
            ).first()
            
            if staging_orders and staging_orders.file_id:
                return self.get_file_lineage(staging_orders.file_id)
            
            staging_products = self.db.query(StagingProductMetrics).filter(
                StagingProductMetrics.ingest_task_id == task_id
            ).first()
            
            if staging_products and staging_products.file_id:
                return self.get_file_lineage(staging_products.file_id)
            
            staging_inventory = self.db.query(StagingInventory).filter(
                StagingInventory.ingest_task_id == task_id
            ).first()
            
            if staging_inventory and staging_inventory.file_id:
                return self.get_file_lineage(staging_inventory.file_id)
            
            return None
            
        except Exception as e:
            logger.error(f"[DataLineage] Failed to get task lineage: {e}", exc_info=True)
            return None
    
    def trace_data_flow(
        self,
        file_id: int
    ) -> Dict[str, Any]:
        """
        追踪数据流转路径
        
        Args:
            file_id: 文件ID
            
        Returns:
            数据流转路径信息
        """
        try:
            catalog_file = self.db.query(CatalogFile).filter(
                CatalogFile.id == file_id
            ).first()
            
            if not catalog_file:
                return {}
            
            flow_info = {
                "source": {
                    "file_id": file_id,
                    "file_name": catalog_file.file_name,
                    "file_path": catalog_file.file_path,
                    "platform": catalog_file.platform_code,
                    "data_domain": catalog_file.data_domain,
                    "granularity": catalog_file.granularity,
                },
                "staging": [],
                "fact": [],
                "materialized_views": [],
            }
            
            # 查找staging表数据
            staging_orders = self.db.query(StagingOrders).filter(
                StagingOrders.file_id == file_id
            ).all()
            if staging_orders:
                flow_info["staging"].append({
                    "table": "staging_orders",
                    "row_count": len(staging_orders),
                    "task_ids": list(set([s.ingest_task_id for s in staging_orders if s.ingest_task_id])),
                })
            
            staging_products = self.db.query(StagingProductMetrics).filter(
                StagingProductMetrics.file_id == file_id
            ).all()
            if staging_products:
                flow_info["staging"].append({
                    "table": "staging_product_metrics",
                    "row_count": len(staging_products),
                    "task_ids": list(set([s.ingest_task_id for s in staging_products if s.ingest_task_id])),
                })
            
            staging_inventory = self.db.query(StagingInventory).filter(
                StagingInventory.file_id == file_id
            ).all()
            if staging_inventory:
                flow_info["staging"].append({
                    "table": "staging_inventory",
                    "row_count": len(staging_inventory),
                    "task_ids": list(set([s.ingest_task_id for s in staging_inventory if s.ingest_task_id])),
                })
            
            # 查找fact表数据（通过file_id）
            fact_orders = self.db.query(FactOrder).filter(
                FactOrder.file_id == file_id
            ).all()
            if fact_orders:
                flow_info["fact"].append({
                    "table": "fact_orders",
                    "row_count": len(fact_orders),
                })
            
            # 查找fact_product_metrics（通过catalog_file_id）
            fact_products = self.db.query(FactProductMetric).filter(
                FactProductMetric.catalog_file_id == file_id
            ).all()
            if fact_products:
                flow_info["fact"].append({
                    "table": "fact_product_metrics",
                    "row_count": len(fact_products),
                })
            
            return flow_info
            
        except Exception as e:
            logger.error(f"[DataLineage] Failed to trace data flow: {e}", exc_info=True)
            return {}
    
    def analyze_impact(
        self,
        file_id: int
    ) -> Dict[str, Any]:
        """
        分析数据影响（下游影响）
        
        Args:
            file_id: 文件ID
            
        Returns:
            影响分析结果
        """
        try:
            impact_info = {
                "file_id": file_id,
                "affected_tables": [],
                "affected_rows": 0,
                "downstream_views": [],
            }
            
            # 追踪数据流转
            flow_info = self.trace_data_flow(file_id)
            
            # 统计受影响的行数
            for staging_info in flow_info.get("staging", []):
                impact_info["affected_rows"] += staging_info.get("row_count", 0)
                impact_info["affected_tables"].append(staging_info["table"])
            
            for fact_info in flow_info.get("fact", []):
                impact_info["affected_rows"] += fact_info.get("row_count", 0)
                impact_info["affected_tables"].append(fact_info["table"])
            
            # 查找下游物化视图（简化处理，实际应该查询物化视图定义）
            # 这里假设所有fact表都有对应的物化视图
            for fact_info in flow_info.get("fact", []):
                table_name = fact_info["table"]
                if table_name == "fact_orders":
                    impact_info["downstream_views"].append("mv_sales_dashboard")
                    impact_info["downstream_views"].append("mv_order_analytics")
                elif table_name == "fact_product_metrics":
                    impact_info["downstream_views"].append("mv_product_performance")
                    impact_info["downstream_views"].append("mv_inventory_analytics")
            
            return impact_info
            
        except Exception as e:
            logger.error(f"[DataLineage] Failed to analyze impact: {e}", exc_info=True)
            return {}
    
    def find_upstream_dependencies(
        self,
        table_name: str,
        record_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        查找上游依赖（数据来源）
        
        Args:
            table_name: 表名
            record_id: 记录ID（可选）
            
        Returns:
            上游依赖列表
        """
        try:
            dependencies = []
            
            # 根据表名查找上游数据
            if table_name == "fact_orders":
                query = self.db.query(FactOrder)
                if record_id:
                    query = query.filter(FactOrder.order_id == record_id)
                
                orders = query.all()
                for order in orders:
                    if order.file_id:
                        catalog_file = self.db.query(CatalogFile).filter(
                            CatalogFile.id == order.file_id
                        ).first()
                        if catalog_file:
                            dependencies.append({
                                "source_type": "file",
                                "file_id": catalog_file.id,
                                "file_name": catalog_file.file_name,
                                "platform": catalog_file.platform_code,
                                "data_domain": catalog_file.data_domain,
                            })
            
            elif table_name == "fact_product_metrics":
                query = self.db.query(FactProductMetric)
                if record_id:
                    query = query.filter(FactProductMetric.platform_sku == record_id)
                
                metrics = query.all()
                for metric in metrics:
                    if metric.catalog_file_id:
                        catalog_file = self.db.query(CatalogFile).filter(
                            CatalogFile.id == metric.catalog_file_id
                        ).first()
                        if catalog_file:
                            dependencies.append({
                                "source_type": "file",
                                "file_id": catalog_file.id,
                                "file_name": catalog_file.file_name,
                                "platform": catalog_file.platform_code,
                                "data_domain": catalog_file.data_domain,
                            })
            
            return dependencies
            
        except Exception as e:
            logger.error(f"[DataLineage] Failed to find upstream dependencies: {e}", exc_info=True)
            return []
    
    def _get_current_timestamp(self) -> str:
        """获取当前时间戳（ISO格式）"""
        from datetime import datetime
        return datetime.utcnow().isoformat()

