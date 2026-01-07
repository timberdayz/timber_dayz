"""入库服务：raw→staging→unified（占位实现，含UPSERT接口）"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import insert
from datetime import datetime
from fastapi import HTTPException

from backend.models.database import (
    StagingOrders,
    StagingProductMetrics,
    StagingInventory,  # ⭐ v4.11.4新增：库存数据暂存表
    FactOrder,
    FactOrderItem,  # ⭐ v4.10.0新增：导入订单明细表
    FactProductMetric,
    DimProduct,
    DataQuarantine,
    CatalogFile,
)
from modules.core.db import BridgeProductKeys  # ⭐ v4.12.0新增：用于关联product_id
from modules.core.logger import get_logger  # ⭐ v4.6.1新增：导入logger

logger = get_logger(__name__)


# ========================= Attributes治理策略 =========================
_ATTR_MAX_KEYS = 200  # 单行最大属性键数
_ATTR_MAX_VALUE_LEN = 2000  # 单值最大长度
_ATTR_BLACKLIST_PREFIX = ("password", "token", "secret", "phone", "mobile", "email", "address")


def _sanitize_attributes(attrs: Dict[str, Any]) -> Dict[str, Any]:
    """
    清洗attributes，执行黑名单与限额策略。
    
    ⭐ v4.7.0修复：处理datetime/date对象和NaN值JSON序列化问题
    - datetime和date对象需要转换为ISO格式字符串才能序列化为JSON
    - NaN值需要转换为None（JSON标准不支持NaN）
    """
    if not attrs:
        return {}
    
    import math
    from datetime import datetime, date
    
    def sanitize_value(val):
        """递归清理值，确保JSON可序列化"""
        if val is None:
            return None
        elif isinstance(val, (datetime, date)):
            return val.isoformat()
        elif isinstance(val, str):
            return None if not val.strip() else val
        elif isinstance(val, (int, float)):
            # ⭐ v4.7.0修复：NaN值转换为None（JSON不支持NaN）
            if isinstance(val, float) and math.isnan(val):
                return None
            return val
        elif isinstance(val, dict):
            return {k: sanitize_value(v) for k, v in val.items()}
        elif isinstance(val, (list, tuple)):
            return [sanitize_value(item) for item in val]
        else:
            return val
    
    cleaned = {}
    for k, v in attrs.items():
        kl = str(k).lower()
        if any(kl.startswith(p) for p in _ATTR_BLACKLIST_PREFIX):
            continue
        
        # ⭐ v4.7.0修复：使用递归清理函数
        val = sanitize_value(v)
        
        # 长度限制
        if isinstance(val, str) and len(val) > _ATTR_MAX_VALUE_LEN:
            val = val[:_ATTR_MAX_VALUE_LEN]
        
        cleaned[k] = val
        if len(cleaned) >= _ATTR_MAX_KEYS:
            break
    return cleaned


def stage_orders(db: Session, rows: List[Dict[str, Any]], ingest_task_id: Optional[str] = None, file_id: Optional[int] = None) -> int:
    """
    暂存订单数据（v4.6.1修复 - 使用order_data JSON字段）
    
    v4.11.4增强：
    - 添加ingest_task_id和file_id参数，关联同步任务和文件记录
    
    修复说明：
    - StagingOrders表只有order_data字段（JSON），不是单独的字段
    - 所有订单数据都应该存储在order_data JSON中
    - ⭐ v4.6.1修复：date/datetime对象需要转换为字符串才能序列化为JSON
    - ⭐ v4.12.1修复：验证file_id是否存在，避免外键约束错误
    """
    import json
    from datetime import datetime, date
    from modules.core.db import CatalogFile
    from modules.core.logger import get_logger
    
    logger = get_logger(__name__)
    
    # ⭐ v4.12.1修复：验证file_id是否存在，避免外键约束错误
    # ⚠️ 注意：外键约束已修复为指向catalog_files表
    if file_id is not None:
        # 检查catalog_files表（正确的表）
        file_record = db.query(CatalogFile).filter(CatalogFile.id == file_id).first()
        if not file_record:
            logger.warning(f"[StageOrders] file_id={file_id} 不存在于catalog_files表中，将file_id设置为None")
            file_id = None  # 设置为None，避免外键约束错误
    
    def json_serial(obj):
        """JSON序列化辅助函数：处理date/datetime对象"""
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")
    
    objs = []
    for r in rows:
        # ⭐ v4.6.1修复：将所有数据存储在order_data JSON中
        # ⭐ v4.7.0企业级ERP空值处理：确保datetime字段正确处理
        order_data = {
            "platform_code": r.get("platform_code"),
            "shop_id": r.get("shop_id"),
            "order_id": r.get("order_id"),
            "product_id": r.get("product_id"),
            "platform_sku": r.get("platform_sku"),
            "sku": r.get("sku"),
            "status": r.get("status"),
            "qty": r.get("qty"),
            "unit_price": r.get("unit_price"),
            "currency": r.get("currency"),
            "order_ts": r.get("order_ts"),
            "shipped_ts": r.get("shipped_ts"),
            "returned_ts": r.get("returned_ts"),
            "gmv": r.get("gmv"),
            "total_amount": r.get("total_amount"),
            "order_date": r.get("order_date"),
            "order_date_local": r.get("order_date_local"),
            "order_time_utc": r.get("order_time_utc"),
            "payment_time": r.get("payment_time"),  # ⭐ v4.7.0新增：支付时间
            "ship_time": r.get("ship_time"),  # ⭐ v4.7.0新增：发货时间
            "account": r.get("account"),  # ⭐ v4.6.1新增：账号字段
            # 保留所有其他字段（用于后续处理）
            **{k: v for k, v in r.items() if k not in [
                "platform_code", "shop_id", "order_id", "product_id", "platform_sku", 
                "sku", "status", "qty", "unit_price", "currency", "order_ts", 
                "shipped_ts", "returned_ts", "gmv", "total_amount", "order_date",
                "order_date_local", "order_time_utc", "payment_time", "ship_time", "account"
            ]}
        }
        
        # ⭐ v4.7.0企业级ERP空值处理：确保datetime字段正确处理
        # ⭐ v4.7.0修复：递归序列化所有嵌套的datetime对象
        def serialize_for_json(obj):
            """递归序列化对象，确保所有datetime/date对象都被转换为字符串"""
            if obj is None:
                return None
            elif isinstance(obj, (datetime, date)):
                return obj.isoformat()
            elif isinstance(obj, str):
                # 空字符串转换为None
                return None if not obj.strip() else obj
            elif isinstance(obj, (list, tuple)):
                return [serialize_for_json(item) for item in obj]
            elif isinstance(obj, dict):
                return {k: serialize_for_json(v) for k, v in obj.items()}
            elif isinstance(obj, float):
                try:
                    import math
                    return None if math.isnan(obj) else obj
                except:
                    return obj
            else:
                return obj
        
        serialized_data = serialize_for_json(order_data)
        
        # ⭐ v4.7.0修复：确保order_id是字符串类型或None（不能是空字符串或数字）
        order_id_value = r.get("order_id")
        if order_id_value is None:
            order_id_value = None
        elif isinstance(order_id_value, str):
            # 空字符串转换为None
            order_id_value = None if not order_id_value.strip() else order_id_value
        elif isinstance(order_id_value, (int, float)):
            # 数字类型转换为字符串（order_id是VARCHAR类型）
            import math
            if isinstance(order_id_value, float) and math.isnan(order_id_value):
                order_id_value = None
            else:
                # 转换为字符串，避免科学计数法（如果需要）
                order_id_value = str(int(order_id_value)) if isinstance(order_id_value, float) and order_id_value.is_integer() else str(order_id_value)
        else:
            # 其他类型转换为字符串
            order_id_value = str(order_id_value) if order_id_value else None
        
        # ⭐ v4.7.0修复：确保platform_code和shop_id也是字符串或None
        platform_code_value = r.get("platform_code")
        if platform_code_value is None or (isinstance(platform_code_value, str) and not platform_code_value.strip()):
            platform_code_value = None
        else:
            platform_code_value = str(platform_code_value)
        
        shop_id_value = r.get("shop_id")
        if shop_id_value is None or (isinstance(shop_id_value, str) and not shop_id_value.strip()):
            shop_id_value = None
        else:
            shop_id_value = str(shop_id_value)
        
        # 创建StagingOrders对象（只传递必填字段）
        obj = StagingOrders(
            platform_code=platform_code_value,
            shop_id=shop_id_value,
            order_id=order_id_value,
            order_data=serialized_data,  # ⭐ v4.6.1修复：使用序列化后的数据
            ingest_task_id=ingest_task_id,  # ⭐ v4.11.4新增：关联同步任务
            file_id=file_id  # ⭐ v4.11.4新增：关联文件记录
        )
        objs.append(obj)
    
    # ⭐ v4.12.2增强：staging阶段错误处理，确保失败的数据被隔离
    successful_count = 0
    failed_rows = []
    
    try:
        db.add_all(objs)
        db.commit()
        successful_count = len(objs)
    except Exception as staging_error:
        # staging失败时，尝试逐条处理，隔离失败的行
        db.rollback()
        logger.error(f"[StageOrders] 批量staging失败，尝试逐条处理: {staging_error}", exc_info=True)
        
        # 获取文件信息用于隔离
        file_record = None
        if file_id:
            file_record = db.query(CatalogFile).filter(CatalogFile.id == file_id).first()
        
        # 逐条处理，隔离失败的行
        for idx, obj in enumerate(objs):
            try:
                db.add(obj)
                db.commit()
                successful_count += 1
            except Exception as row_error:
                db.rollback()
                logger.error(f"[StageOrders] 行{idx} staging失败: {row_error}", exc_info=True)
                failed_rows.append((idx, rows[idx], row_error))
                
                # 隔离失败的行
                try:
                    if file_record:
                        from modules.core.db import DataQuarantine
                        import json
                        
                        quarantine_record = DataQuarantine(
                            catalog_file_id=file_record.id,
                            source_file=file_record.file_name,
                            row_number=None,  # staging失败时无法确定具体行号
                            row_data=json.dumps(rows[idx], ensure_ascii=False, default=str),
                            error_type=type(row_error).__name__,
                            error_msg=f"Staging失败: {str(row_error)}",
                            platform_code=rows[idx].get("platform_code"),
                            shop_id=rows[idx].get("shop_id"),
                            data_domain="orders"
                        )
                        db.add(quarantine_record)
                        db.commit()
                        logger.info(f"[StageOrders] 已隔离staging失败的行{idx}")
                except Exception as quarantine_error:
                    logger.warning(f"[StageOrders] 隔离staging失败行时出错: {quarantine_error}", exc_info=True)
                    try:
                        db.rollback()
                    except Exception:
                        pass
        
        if failed_rows:
            logger.warning(f"[StageOrders] {len(failed_rows)}行数据staging失败并已隔离")
    
    return successful_count


def stage_product_metrics(db: Session, rows: List[Dict[str, Any]], ingest_task_id: Optional[str] = None, file_id: Optional[int] = None) -> int:
    """
    暂存产品指标数据
    
    v4.11.4增强：
    - 添加ingest_task_id和file_id参数，关联同步任务和文件记录
    - 实际写入staging_product_metrics表
    - ⭐ v4.12.1修复：验证file_id是否存在，避免外键约束错误
    """
    import json
    from datetime import datetime, date
    from modules.core.db import CatalogFile
    from modules.core.logger import get_logger
    
    logger = get_logger(__name__)
    
    # ⭐ v4.12.1修复：验证file_id是否存在，避免外键约束错误
    if file_id is not None:
        file_record = db.query(CatalogFile).filter(CatalogFile.id == file_id).first()
        if not file_record:
            logger.warning(f"[StageProductMetrics] file_id={file_id} 不存在于catalog_files表中，将file_id设置为None")
            file_id = None  # 设置为None，避免外键约束错误
    
    def serialize_for_json(obj):
        """递归序列化对象，确保所有datetime/date对象都被转换为字符串"""
        if obj is None:
            return None
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, str):
            return None if not obj.strip() else obj
        elif isinstance(obj, (list, tuple)):
            return [serialize_for_json(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: serialize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, float):
            try:
                import math
                return None if math.isnan(obj) else obj
            except:
                return obj
        else:
            return obj
    
    objs = []
    for r in rows:
        # 将所有数据存储在metric_data JSON中
        metric_data = serialize_for_json(r)
        
        # 提取关键字段用于索引
        platform_code_value = r.get("platform_code")
        if platform_code_value is None or (isinstance(platform_code_value, str) and not platform_code_value.strip()):
            platform_code_value = None
        else:
            platform_code_value = str(platform_code_value)
        
        shop_id_value = r.get("shop_id")
        if shop_id_value is None or (isinstance(shop_id_value, str) and not shop_id_value.strip()):
            shop_id_value = None
        else:
            shop_id_value = str(shop_id_value)
        
        platform_sku_value = r.get("platform_sku")
        if platform_sku_value is None or (isinstance(platform_sku_value, str) and not platform_sku_value.strip()):
            platform_sku_value = None
        else:
            platform_sku_value = str(platform_sku_value)
        
        obj = StagingProductMetrics(
            platform_code=platform_code_value,
            shop_id=shop_id_value,
            platform_sku=platform_sku_value,
            metric_data=metric_data,
            ingest_task_id=ingest_task_id,  # ⭐ v4.11.4新增：关联同步任务
            file_id=file_id  # ⭐ v4.11.4新增：关联文件记录
        )
        objs.append(obj)
    
    # ⭐ v4.12.2增强：staging阶段错误处理，确保失败的数据被隔离
    successful_count = 0
    failed_rows = []
    
    if objs:
        try:
            db.add_all(objs)
            db.commit()
            successful_count = len(objs)
        except Exception as staging_error:
            # staging失败时，尝试逐条处理，隔离失败的行
            db.rollback()
            logger.error(f"[StageProductMetrics] 批量staging失败，尝试逐条处理: {staging_error}", exc_info=True)
            
            # 获取文件信息用于隔离
            file_record = None
            if file_id:
                file_record = db.query(CatalogFile).filter(CatalogFile.id == file_id).first()
            
            # 逐条处理，隔离失败的行
            for idx, obj in enumerate(objs):
                try:
                    db.add(obj)
                    db.commit()
                    successful_count += 1
                except Exception as row_error:
                    db.rollback()
                    logger.error(f"[StageProductMetrics] 行{idx} staging失败: {row_error}", exc_info=True)
                    failed_rows.append((idx, rows[idx], row_error))
                    
                    # 隔离失败的行
                    try:
                        if file_record:
                            from modules.core.db import DataQuarantine
                            import json
                            
                            quarantine_record = DataQuarantine(
                                catalog_file_id=file_record.id,
                                source_file=file_record.file_name,
                                row_number=None,  # staging失败时无法确定具体行号
                                row_data=json.dumps(rows[idx], ensure_ascii=False, default=str),
                                error_type=type(row_error).__name__,
                                error_msg=f"Staging失败: {str(row_error)}",
                                platform_code=rows[idx].get("platform_code"),
                                shop_id=rows[idx].get("shop_id"),
                                data_domain="products"
                            )
                            db.add(quarantine_record)
                            db.commit()
                            logger.info(f"[StageProductMetrics] 已隔离staging失败的行{idx}")
                    except Exception as quarantine_error:
                        logger.warning(f"[StageProductMetrics] 隔离staging失败行时出错: {quarantine_error}", exc_info=True)
                        try:
                            db.rollback()
                        except Exception:
                            pass
            
            if failed_rows:
                logger.warning(f"[StageProductMetrics] {len(failed_rows)}行数据staging失败并已隔离")
    
    return successful_count


def stage_inventory(db: Session, rows: List[Dict[str, Any]], ingest_task_id: Optional[str] = None, file_id: Optional[int] = None) -> int:
    """
    暂存库存数据
    
    v4.11.4新增：
    - inventory域数据暂存表
    - 支持原始数据JSON存储
    - 关联同步任务和文件记录
    - ⭐ v4.12.1修复：验证file_id是否存在，避免外键约束错误
    """
    import json
    from datetime import datetime, date
    from modules.core.db import CatalogFile
    from modules.core.logger import get_logger
    
    logger = get_logger(__name__)
    
    # ⭐ v4.12.1修复：验证file_id是否存在，避免外键约束错误
    if file_id is not None:
        file_record = db.query(CatalogFile).filter(CatalogFile.id == file_id).first()
        if not file_record:
            logger.warning(f"[StageInventory] file_id={file_id} 不存在于catalog_files表中，将file_id设置为None")
            file_id = None  # 设置为None，避免外键约束错误
    
    def serialize_for_json(obj):
        """递归序列化对象，确保所有datetime/date对象都被转换为字符串"""
        if obj is None:
            return None
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, str):
            return None if not obj.strip() else obj
        elif isinstance(obj, (list, tuple)):
            return [serialize_for_json(item) for item in obj]
        elif isinstance(obj, dict):
            return {k: serialize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, float):
            try:
                import math
                return None if math.isnan(obj) else obj
            except:
                return obj
        else:
            return obj
    
    objs = []
    for r in rows:
        # 将所有数据存储在inventory_data JSON中
        inventory_data = serialize_for_json(r)
        
        # 提取关键字段用于索引
        platform_code_value = r.get("platform_code")
        if platform_code_value is None or (isinstance(platform_code_value, str) and not platform_code_value.strip()):
            platform_code_value = None
        else:
            platform_code_value = str(platform_code_value)
        
        shop_id_value = r.get("shop_id")
        if shop_id_value is None or (isinstance(shop_id_value, str) and not shop_id_value.strip()):
            shop_id_value = None
        else:
            shop_id_value = str(shop_id_value)
        
        platform_sku_value = r.get("platform_sku")
        if platform_sku_value is None or (isinstance(platform_sku_value, str) and not platform_sku_value.strip()):
            platform_sku_value = None
        else:
            platform_sku_value = str(platform_sku_value)
        
        warehouse_id_value = r.get("warehouse_id")
        if warehouse_id_value is None or (isinstance(warehouse_id_value, str) and not warehouse_id_value.strip()):
            warehouse_id_value = None
        else:
            warehouse_id_value = str(warehouse_id_value)
        
        obj = StagingInventory(
            platform_code=platform_code_value,
            shop_id=shop_id_value,
            platform_sku=platform_sku_value,
            warehouse_id=warehouse_id_value,
            inventory_data=inventory_data,
            ingest_task_id=ingest_task_id,
            file_id=file_id
        )
        objs.append(obj)
    
    if objs:
        db.add_all(objs)
        db.commit()
    return len(objs)


def _resolve_product_surrogate(db: Session, platform_code: str, product_id: str | None, platform_sku: str | None) -> str:
    """解析产品维度键（返回platform_sku）
    
    注意：DimProduct的主键是(platform_code, shop_id, platform_sku)，没有surrogate_id
    这里返回platform_sku作为关联键
    """
    # 直接返回platform_sku（简化版）
    return platform_sku or "unknown"


def upsert_orders(db: Session, rows: List[Dict[str, Any]], file_record: Optional[Any] = None) -> int:
    """
    批量UPSERT订单数据（v4.6.1修复 - 使用正确的字段）
    
    修复说明：
    - FactOrder表只包含订单级别的字段，不包含product_id, sku, status等
    - 使用upsert_orders_v2函数，它使用_FACT_ORDER_CORE_FIELDS筛选字段
    - 其他字段（如product_id, sku等）会自动进入attributes JSON字段
    
    ⭐ v4.6.1修复：传递file_record参数，用于获取platform_code
    """
    # ⭐ v4.6.1修复：使用v2版本，它使用正确的字段筛选逻辑
    return upsert_orders_v2(db, rows, file_record=file_record)


# ========================= 新版入库（关键列+attributes兜底） =========================

_FACT_ORDER_CORE_FIELDS = {
    "platform_code",
    "shop_id",
    "order_id",
    "order_time_utc",
    "order_date_local",
    "currency",
    "subtotal",
    "subtotal_rmb",
    "shipping_fee",
    "shipping_fee_rmb",
    "tax_amount",
    "tax_amount_rmb",
    "discount_amount",
    "discount_amount_rmb",
    "total_amount",
    "total_amount_rmb",
    "payment_method",
    "payment_status",
    "order_status",
    "shipping_status",
    "delivery_status",
    "is_cancelled",
    "is_refunded",
    "refund_amount",
    "refund_amount_rmb",
    "buyer_id",
    "buyer_name",
    "store_label_raw",
    "site",
    "account",
    "aligned_account_id",
    "file_id",
    "attributes",  # ⭐ v4.6.1修复：添加attributes字段到核心字段列表
}


def upsert_orders_v2(db: Session, rows: List[Dict[str, Any]], file_record: Optional[Any] = None) -> int:
    """新版UPSERT：核心字段直落列，其他列写入attributes。

    要求：rows中的字典使用事实表字段名；额外来源列将自动进入attributes。
    
    ⭐ v4.6.1增强：自动账号对齐
    - 如果account字段有值但aligned_account_id为空，自动调用账号对齐服务
    - 支持部分匹配（如"3C店"匹配"shopee新加坡3C店"）
    
    ⭐ v4.6.1修复：确保platform_code和order_id不为空
    - 如果rows中没有platform_code，从file_record中获取
    - 如果rows中没有order_id，使用attributes中的订单号或生成唯一ID
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from datetime import datetime  # ⭐ v4.6.1修复：导入datetime

    if not rows:
        return 0

    is_postgresql = 'postgresql' in str(db.bind.url)
    total = 0
    
    # ⭐ v4.6.1新增：初始化账号对齐服务（如果需要）
    alignment_service = None
    try:
        from modules.services.account_alignment import AccountAlignmentService
        alignment_service = AccountAlignmentService(db)
    except Exception as e:
        logger.warning(f"[UpsertOrders] 初始化账号对齐服务失败: {e}")

    for idx, r in enumerate(rows):
        # 拆分核心列与attributes
        core = {k: v for k, v in r.items() if k in _FACT_ORDER_CORE_FIELDS}
        extras = {k: v for k, v in r.items() if k not in _FACT_ORDER_CORE_FIELDS}
        
        # ⭐ v4.7.0修复：确保datetime字段在core中（不在attributes中）
        # ⚠️ 注意：FactOrder表中只有 order_time_utc 和 order_date_local 字段
        # ship_time 和 payment_time 不在表中，应该进入 attributes JSON
        # 只将 order_time_utc 和 order_date_local 移到 core 中
        datetime_fields_for_core = {
            "order_time_utc",  # ✅ FactOrder表中有此字段
            "order_date_local",  # ✅ FactOrder表中有此字段
            "metric_date"  # ✅ 可能用于某些场景
        }
        # ship_time 和 payment_time 不在 FactOrder 表中，应该留在 extras 中（进入 attributes）
        
        for field in datetime_fields_for_core:
            if field in extras and field not in core:
                core[field] = extras.pop(field)
        
        # ⭐ v4.7.0企业级ERP空值处理：确保datetime字段为None而不是空字符串
        # 对于可选时间字段（nullable=True），空值应该统一为None
        for field in ["order_time_utc", "order_date_local"]:  # ⚠️ 只处理FactOrder表中存在的字段
            if field in core:
                value = core[field]
                # 空字符串、空列表等统一转换为None
                if value == "" or (isinstance(value, str) and not value.strip()):
                    core[field] = None
                elif isinstance(value, float):
                    try:
                        import math
                        if math.isnan(value):
                            core[field] = None
                    except:
                        pass
        
        # ⭐ v4.7.0修复：确保所有数值字段都是正确的类型（float）
        # 防止字符串被插入到数值字段（会导致PostgreSQL类型错误）
        numeric_fields_in_core = {
            "subtotal", "subtotal_rmb", "shipping_fee", "shipping_fee_rmb",
            "tax_amount", "tax_amount_rmb", "discount_amount", "discount_amount_rmb",
            "total_amount", "total_amount_rmb", "refund_amount", "refund_amount_rmb"
        }
        for field in numeric_fields_in_core:
            if field in core:
                value = core[field]
                # 如果是None或空字符串，设置为0.0
                if value is None or value == "":
                    core[field] = 0.0
                # 如果是字符串，尝试转换为float
                elif isinstance(value, str):
                    value_str = value.strip()
                    if not value_str or value_str.lower() in ['none', 'null', 'n/a', 'na', '-']:
                        core[field] = 0.0
                    else:
                        try:
                            # 去除货币符号和千分位
                            cleaned = value_str.replace(',', '').replace('$', '').replace('¥', '').replace('€', '').replace('£', '').strip()
                            core[field] = float(cleaned)
                        except (ValueError, TypeError):
                            logger.warning(f"[UpsertOrders] 数值字段 {field} 无法转换为float: {value}，设置为0.0")
                            core[field] = 0.0
                # 如果是int，转换为float
                elif isinstance(value, int):
                    core[field] = float(value)
                # 如果是float，检查是否为NaN
                elif isinstance(value, float):
                    try:
                        import math
                        if math.isnan(value):
                            core[field] = 0.0
                    except:
                        pass
                # 其他类型，尝试转换
                else:
                    try:
                        core[field] = float(value)
                    except (ValueError, TypeError):
                        logger.warning(f"[UpsertOrders] 数值字段 {field} 类型错误: {type(value)}，设置为0.0")
                        core[field] = 0.0
        
        # ⭐ v4.7.0修复：处理attributes中的datetime对象（ship_time/payment_time会在这里）
        # 确保extras中的datetime字段（如ship_time、payment_time）正确处理
        core["attributes"] = _sanitize_attributes(extras) or None
        
        # ⭐ v4.6.1修复：确保platform_code不为空（主键字段）
        if not core.get("platform_code"):
            if file_record and file_record.platform_code:
                core["platform_code"] = file_record.platform_code
            else:
                # 尝试从attributes中提取平台信息
                if core.get("attributes") and isinstance(core["attributes"], dict):
                    platform = core["attributes"].get("平台") or core["attributes"].get("platform")
                    if platform:
                        # 映射常见平台名称到平台代码
                        platform_map = {
                            "shopee": "shopee",
                            "Shopee": "shopee",
                            "lazada": "lazada",
                            "Lazada": "lazada",
                            "tiktok": "tiktok",
                            "TikTok": "tiktok",
                            "amazon": "amazon",
                            "Amazon": "amazon",
                            "miaoshou": "miaoshou",
                            "妙手": "miaoshou",
                        }
                        core["platform_code"] = platform_map.get(platform.lower(), platform.lower())
                    else:
                        core["platform_code"] = "unknown"  # 默认值
                else:
                    core["platform_code"] = "unknown"  # 默认值
        
        # ⭐ v4.6.1修复：确保order_id不为空（主键字段）
        # ⭐ v4.10.0修复：确保order_id是字符串类型（避免科学计数法问题）
        if not core.get("order_id"):
            # 尝试从attributes中提取订单号
            if core.get("attributes") and isinstance(core["attributes"], dict):
                order_id = (
                    core["attributes"].get("订单号") or 
                    core["attributes"].get("订单编号") or 
                    core["attributes"].get("order_id") or
                    core["attributes"].get("order_number")
                )
                if order_id:
                    # ⭐ v4.10.0修复：确保order_id是字符串，不是科学计数法
                    if isinstance(order_id, float):
                        # 如果是浮点数（科学计数法），转换为整数再转字符串
                        core["order_id"] = str(int(order_id))
                    elif isinstance(order_id, (int, float)):
                        # 如果是数字，直接转字符串
                        core["order_id"] = str(int(order_id)) if isinstance(order_id, float) and order_id.is_integer() else str(order_id)
                    else:
                        # 已经是字符串，确保不是科学计数法格式
                        core["order_id"] = str(order_id).strip()
                else:
                    # 生成唯一ID（使用时间戳+索引）
                    core["order_id"] = f"ORDER_{int(datetime.now().timestamp() * 1000)}_{idx}"
            else:
                # 生成唯一ID
                core["order_id"] = f"ORDER_{int(datetime.now().timestamp() * 1000)}_{idx}"
        else:
            # ⭐ v4.10.0修复：确保order_id是字符串类型（避免科学计数法问题）
            order_id_value = core.get("order_id")
            if isinstance(order_id_value, float):
                # 如果是浮点数（科学计数法），转换为整数再转字符串
                core["order_id"] = str(int(order_id_value))
            elif isinstance(order_id_value, (int, float)):
                # 如果是数字，直接转字符串
                import math
                if isinstance(order_id_value, float) and math.isnan(order_id_value):
                    core["order_id"] = f"ORDER_{int(datetime.now().timestamp() * 1000)}_{idx}"
                else:
                    core["order_id"] = str(int(order_id_value)) if isinstance(order_id_value, float) and order_id_value.is_integer() else str(order_id_value)
            else:
                # 已经是字符串，确保不是科学计数法格式
                core["order_id"] = str(order_id_value).strip()
        
        # ⭐ v4.12.1修复：shop_id是主键，优先从file_record获取，避免数据丢失
        if not core.get("shop_id"):
            if file_record and file_record.shop_id:
                core["shop_id"] = file_record.shop_id
            else:
                # ⚠️ 注意：shop_id是主键的一部分，不能为空字符串
                # 如果file_record也没有shop_id，使用文件名或其他标识符作为shop_id
                if file_record and file_record.file_name:
                    # 尝试从文件名提取shop_id（如：shopee_orders_weekly_20250926_183956.xls）
                    import re
                    match = re.search(r'orders_(\w+)_', file_record.file_name)
                    if match:
                        core["shop_id"] = match.group(1)
                    else:
                        # 使用文件名的一部分作为shop_id
                        core["shop_id"] = file_record.file_name.replace('.xls', '').replace('.xlsx', '')[:64]
                else:
                    # 最后的兜底：使用时间戳作为shop_id
                    core["shop_id"] = f"unknown_{int(datetime.now().timestamp())}"
                logger.warning(f"[UpsertOrders] shop_id为空，使用兜底值: {core.get('shop_id')}")
        
        # ⭐ v4.6.1新增：处理已取消订单的信息空白问题
        # 已取消订单通常缺少采购、付款、发货等信息，这是正常的
        # 我们需要确保已取消订单能够正常入库，使用默认值填充缺失字段
        order_status = core.get("order_status")
        if not order_status and core.get("attributes") and isinstance(core["attributes"], dict):
            order_status = core["attributes"].get("订单状态")
        
        is_cancelled = False
        if order_status:
            cancelled_statuses = ["已取消", "cancelled", "canceled", "取消"]
            if str(order_status).strip() in cancelled_statuses:
                is_cancelled = True
                core["is_cancelled"] = True
                core["order_status"] = "cancelled"
                
                # ⭐ v4.6.1新增：已取消订单使用默认值填充缺失字段
                if not core.get("payment_status"):
                    core["payment_status"] = "cancelled"
                if not core.get("shipping_status"):
                    core["shipping_status"] = "cancelled"
                if not core.get("delivery_status"):
                    core["delivery_status"] = "cancelled"
                if core.get("total_amount") is None:
                    core["total_amount"] = 0.0
                if core.get("total_amount_rmb") is None:
                    core["total_amount_rmb"] = 0.0
                # 已取消订单的金额字段都设为0
                if core.get("subtotal") is None:
                    core["subtotal"] = 0.0
                if core.get("subtotal_rmb") is None:
                    core["subtotal_rmb"] = 0.0
                if core.get("shipping_fee") is None:
                    core["shipping_fee"] = 0.0
                if core.get("tax_amount") is None:
                    core["tax_amount"] = 0.0
                logger.debug(f"[UpsertOrders] 已取消订单处理: order_id={core.get('order_id')}, 使用默认值填充缺失字段")
        
        # ⭐ v4.12.1修复：确保file_id字段被设置（用于数据血缘追踪）
        if not core.get("file_id") and file_record:
            core["file_id"] = file_record.id
        
        # ⭐ v4.6.1新增：自动账号对齐
        # 如果account字段有值但aligned_account_id为空，尝试自动匹配
        if alignment_service and core.get("account") and not core.get("aligned_account_id"):
            platform_code = core.get("platform_code", "")
            account = core.get("account")
            site = core.get("site")
            store_label_raw = core.get("store_label_raw") or account  # 如果没有store_label_raw，使用account
            
            # 调用账号对齐服务
            aligned_account_id = alignment_service.align_order(
                account=account,
                site=site,
                store_label_raw=store_label_raw,
                platform_code=platform_code
            )
            
            if aligned_account_id:
                core["aligned_account_id"] = aligned_account_id
                logger.debug(f"[UpsertOrders] 自动对齐账号: '{account}' -> '{aligned_account_id}'")

        if is_postgresql:
            try:
                stmt = pg_insert(FactOrder).values(**core)
                # ⭐ v4.6.1修复：修复stmt.excluded访问方式
                # stmt.excluded是ReadOnlyColumnCollection，不能使用__getattribute__
                # 正确方式：直接使用列名作为键，通过stmt.excluded[column_name]访问
                update_dict = {
                    k: stmt.excluded[k] for k in core.keys() 
                    if k not in ("platform_code", "shop_id", "order_id")
                }
                update_dict["updated_at"] = datetime.now()
                stmt = stmt.on_conflict_do_update(
                    index_elements=["platform_code", "shop_id", "order_id"],
                    set_=update_dict,
                )
                db.execute(stmt)
                # ⭐ v4.10.0修复：每个订单入库成功后立即提交，避免事务失败影响其他订单
                db.commit()
            except Exception as order_error:
                # ⭐ v4.10.0修复：订单入库失败时回滚并记录错误，但不影响其他订单
                db.rollback()
                logger.error(f"[UpsertOrders] 订单入库失败: order_id={core.get('order_id')}, platform_code={core.get('platform_code')}, error={order_error}", exc_info=True)
                
                # ⭐ v4.12.1新增：自动隔离失败的订单（用于数据丢失追踪）
                try:
                    if file_record:
                        from modules.core.db import DataQuarantine
                        import json
                        
                        quarantine_record = DataQuarantine(
                            catalog_file_id=file_record.id,
                            source_file=file_record.file_name,
                            row_number=None,  # upsert失败时无法确定具体行号
                            row_data=json.dumps(r, ensure_ascii=False, default=str),
                            error_type=type(order_error).__name__,
                            error_msg=str(order_error),
                            platform_code=core.get("platform_code"),
                            shop_id=core.get("shop_id"),
                            data_domain="orders"
                        )
                        db.add(quarantine_record)
                        db.commit()
                        logger.info(f"[UpsertOrders] 已隔离失败订单: order_id={core.get('order_id')}")
                except Exception as quarantine_error:
                    # 隔离失败不影响主流程，只记录日志
                    logger.warning(f"[UpsertOrders] 隔离失败订单时出错: {quarantine_error}", exc_info=True)
                    try:
                        db.rollback()
                    except Exception:
                        pass
                
                # 跳过这个订单，继续处理下一个
                continue
        else:
            # 简易兼容：尝试插入，失败则更新
            try:
                db.add(FactOrder(**core))
                db.commit()
            except Exception:
                db.rollback()
                db.query(FactOrder).filter(
                    FactOrder.platform_code == core.get("platform_code"),
                    FactOrder.shop_id == core.get("shop_id"),
                    FactOrder.order_id == core.get("order_id"),
                ).update(core)
                db.commit()

        # ⭐ v4.10.0新增：如果数据包含订单明细字段，同时入库到fact_order_items表
        # ⚠️ 注意：只有在订单入库成功后才入库订单明细
        # 检查是否包含订单明细字段（platform_sku, quantity, line_amount等）
        # 字段可能存在于：
        #   1. r（字段映射后的标准字段，如platform_sku, quantity）
        #   2. extras（字段映射前的原始字段，但此时extras已被转换为attributes）
        #   3. core["attributes"]（未映射字段的JSON，包含原始列名）
        # 优先从r中提取（标准字段），如果找不到，再从attributes中提取（原始字段）
        
        # 从attributes中提取字段的辅助函数
        def get_from_attrs(key, default=None):
            """从attributes JSON中提取字段，支持多种可能的键名"""
            if not core.get("attributes") or not isinstance(core["attributes"], dict):
                return default
            attrs = core["attributes"]
            # 尝试多种可能的键名
            possible_keys = [
                key,  # 标准字段名
                key.lower(),  # 小写
                key.upper(),  # 大写
                key.replace("_", ""),  # 无下划线
            ]
            # 中文键名映射
            cn_key_map = {
                "platform_sku": ["平台SKU", "SKU ID", "商品SKU", "产品SKU", "规格货号"],
                "quantity": ["数量", "商品数量", "销售数量", "quantity", "qty"],
                "line_amount": ["金额", "商品金额", "行金额", "line_amount", "total_amount"],
                "line_amount_rmb": ["金额（元）", "商品金额（元）", "行金额（元）", "line_amount_rmb", "total_amount_rmb"],
                "unit_price": ["单价", "商品单价", "unit_price"],
                "unit_price_rmb": ["单价（元）", "商品单价（元）", "unit_price_rmb"],
                "product_title": ["商品名称", "产品名称", "product_name", "product_title"],
            }
            if key in cn_key_map:
                possible_keys.extend(cn_key_map[key])
            
            for k in possible_keys:
                if k in attrs:
                    value = attrs[k]
                    # 跳过空值和无效值
                    if value is not None and str(value).strip() and str(value).strip().lower() not in ['n/a', 'na', 'none', 'null', '']:
                        return value
            return default
        
        # 提取platform_sku（优先从r，其次从attributes）
        platform_sku = (
            r.get("platform_sku") or 
            r.get("product_sku") or 
            r.get("sku") or
            get_from_attrs("platform_sku") or
            get_from_attrs("product_sku") or
            get_from_attrs("sku") or
            None
        )
        
        # 提取quantity（优先从r，其次从attributes）
        quantity = (
            r.get("quantity") or 
            r.get("qty") or
            get_from_attrs("quantity") or
            get_from_attrs("qty") or
            1  # 默认值
        )
        
        # 提取line_amount（优先从r，其次从attributes）
        line_amount = (
            r.get("line_amount") or 
            r.get("line_amount_rmb") or
            r.get("total_amount") or
            r.get("total_amount_rmb") or
            get_from_attrs("line_amount") or
            get_from_attrs("total_amount") or
            0.0
        )
        
        # 提取line_amount_rmb（优先从r，其次从attributes）
        line_amount_rmb = (
            r.get("line_amount_rmb") or 
            r.get("total_amount_rmb") or
            get_from_attrs("line_amount_rmb") or
            get_from_attrs("total_amount_rmb") or
            line_amount  # 如果没有CNY金额，使用原币金额
        )
        
        # 提取unit_price（优先从r，其次从attributes）
        unit_price = (
            r.get("unit_price") or 
            r.get("unit_price_rmb") or
            get_from_attrs("unit_price") or
            (line_amount / quantity if quantity and quantity > 0 else 0.0)
        )
        
        # 提取unit_price_rmb（优先从r，其次从attributes）
        unit_price_rmb = (
            r.get("unit_price_rmb") or 
            get_from_attrs("unit_price_rmb") or
            unit_price  # 如果没有CNY单价，使用原币单价
        )
        
        # 提取product_title（优先从r，其次从attributes）
        product_title = (
            r.get("product_title") or 
            r.get("product_name") or
            get_from_attrs("product_title") or
            get_from_attrs("product_name") or
            None
        )
        
        # 如果包含platform_sku，入库订单明细
        if platform_sku and str(platform_sku).strip() and str(platform_sku).strip().lower() not in ['n/a', 'na', 'none', 'null', '']:
            try:
                # 确保数值字段类型正确
                quantity = int(quantity) if quantity else 1
                line_amount = float(line_amount) if line_amount else 0.0
                line_amount_rmb = float(line_amount_rmb) if line_amount_rmb else 0.0
                unit_price = float(unit_price) if unit_price else 0.0
                unit_price_rmb = float(unit_price_rmb) if unit_price_rmb else 0.0
                
                # ⭐ v4.12.0新增：通过BridgeProductKeys查找product_id
                product_id = None
                try:
                    bridge = db.query(BridgeProductKeys).filter(
                        BridgeProductKeys.platform_code == core.get("platform_code"),
                        BridgeProductKeys.shop_id == core.get("shop_id", ""),
                        BridgeProductKeys.platform_sku == str(platform_sku).strip()
                    ).first()
                    if bridge:
                        product_id = bridge.product_id
                except Exception as bridge_error:
                    # 查找失败不影响订单明细入库，记录警告即可
                    logger.debug(f"[UpsertOrders] 查找product_id失败: platform_code={core.get('platform_code')}, shop_id={core.get('shop_id')}, platform_sku={platform_sku}, error={bridge_error}")
                
                # 准备订单明细数据
                order_item_core = {
                    "platform_code": core.get("platform_code"),
                    "shop_id": core.get("shop_id", ""),
                    "order_id": core.get("order_id"),
                    "platform_sku": str(platform_sku).strip(),
                    "product_id": product_id,  # ⭐ v4.12.0新增：产品ID（冗余字段）
                    "product_title": str(product_title).strip() if product_title else None,
                    "quantity": quantity,
                    "currency": core.get("currency"),
                    "unit_price": unit_price,
                    "unit_price_rmb": unit_price_rmb,
                    "line_amount": line_amount,
                    "line_amount_rmb": line_amount_rmb,
                }
                
                # 订单明细的attributes（包含其他未映射字段）
                order_item_extras = {k: v for k, v in extras.items() if k not in ["platform_sku", "quantity", "line_amount", "line_amount_rmb", "unit_price", "unit_price_rmb", "product_title", "product_name"]}
                order_item_core["attributes"] = _sanitize_attributes(order_item_extras) or None
                
                # 入库订单明细
                if is_postgresql:
                    try:
                        item_stmt = pg_insert(FactOrderItem).values(**order_item_core)
                        item_update_dict = {
                            k: item_stmt.excluded[k] for k in order_item_core.keys() 
                            if k not in ("platform_code", "shop_id", "order_id", "platform_sku")
                        }
                        item_update_dict["updated_at"] = datetime.now()
                        item_stmt = item_stmt.on_conflict_do_update(
                            index_elements=["platform_code", "shop_id", "order_id", "platform_sku"],
                            set_=item_update_dict,
                        )
                        db.execute(item_stmt)
                        # ⭐ v4.10.0修复：订单明细入库成功后立即提交
                        db.commit()
                        logger.debug(f"[UpsertOrders] 已入库订单明细: order_id={core.get('order_id')}, platform_sku={platform_sku}, quantity={quantity}, line_amount={line_amount_rmb}")
                    except Exception as item_db_error:
                        # ⭐ v4.10.0修复：订单明细入库失败时回滚并记录错误
                        db.rollback()
                        logger.warning(f"[UpsertOrders] 入库订单明细失败: order_id={core.get('order_id')}, platform_sku={platform_sku}, error={item_db_error}", exc_info=True)
                        # 订单明细入库失败不影响订单级别数据入库，继续执行
                else:
                    # SQLite兼容
                    try:
                        db.add(FactOrderItem(**order_item_core))
                        db.commit()
                        logger.debug(f"[UpsertOrders] 已入库订单明细: order_id={core.get('order_id')}, platform_sku={platform_sku}, quantity={quantity}, line_amount={line_amount_rmb}")
                    except Exception:
                        db.rollback()
                        db.query(FactOrderItem).filter(
                            FactOrderItem.platform_code == order_item_core.get("platform_code"),
                            FactOrderItem.shop_id == order_item_core.get("shop_id"),
                            FactOrderItem.order_id == order_item_core.get("order_id"),
                            FactOrderItem.platform_sku == order_item_core.get("platform_sku"),
                        ).update(order_item_core)
                        db.commit()
                        logger.debug(f"[UpsertOrders] 已更新订单明细: order_id={core.get('order_id')}, platform_sku={platform_sku}")
            except Exception as item_error:
                logger.warning(f"[UpsertOrders] 处理订单明细失败: order_id={core.get('order_id')}, error={item_error}", exc_info=True)
                # 订单明细处理失败不影响订单级别数据入库，继续执行

        total += 1
    
    # ⭐ v4.10.0修复：PostgreSQL使用逐条提交，不需要批量提交
    # 每个订单入库成功后已经立即提交，这里不需要再次提交
    # if is_postgresql:
    #     db.commit()

    return total


def quarantine_failed_data(db: Session, file_id: int, validation_result: Dict[str, Any], header_row: int = 1) -> int:
    """
    将验证失败的数据写入隔离区
    
    v4.4.1关键修复：字段名匹配schema.py中的DataQuarantine定义
    - catalog_file_id (不是 file_id)
    - row_number (不是 row_idx)
    - row_data (不是 raw_value，JSON格式)
    - error_type (不是 issue_type)
    - error_msg (不是 message)
    
    ⭐ v4.6.1修复：row_number计算
    - validation_result中的row是数组索引（从0开始）
    - 需要转换为Excel实际行号：Excel行号 = header_row + row_index
    - 例如：header_row=2, row_index=0 → Excel行号=2（第一行数据）
    """
    import json
    
    quarantined_count = 0
    
    # 获取文件信息（用于填充必填字段）
    catalog_file = db.query(CatalogFile).filter(CatalogFile.id == file_id).first()
    source_file_name = catalog_file.file_name if catalog_file else f"file_id_{file_id}"
    platform_code = catalog_file.platform_code if catalog_file else None
    shop_id = catalog_file.shop_id if catalog_file else None
    data_domain = catalog_file.data_domain if catalog_file else None
    
    # 处理错误数据
    for error in validation_result.get("errors", []):
        # ⭐ v4.6.1修复：将数组索引转换为Excel实际行号
        row_index = error.get("row", 0)  # 数组索引（从0开始）
        # ⭐ v4.6.1修复：Excel行号 = header_row + row_index + 1
        # 因为pandas的header参数会跳过表头行，所以第一个数据行对应Excel行号 = header_row + 1
        excel_row_number = header_row + row_index + 1  # Excel实际行号
        
        # 如果header_row > 1，跳过表头行之前的数据（不应该被验证）
        if excel_row_number <= header_row:
            logger.warning(f"[Quarantine] 跳过表头行及其之前的数据: Excel行号={excel_row_number}, header_row={header_row}")
            continue
        
        # 构建row_data（JSON格式）
        row_data_dict = {
            "row": row_index,
            "excel_row": excel_row_number,  # ⭐ v4.6.1新增：Excel实际行号
            "col": error.get("col", ""),
            "raw_value": error.get("raw_value", ""),
            "suggested": error.get("suggested", "")
        }
        
        quarantine_record = DataQuarantine(
            catalog_file_id=file_id,  # ✅ 正确字段名
            source_file=source_file_name,  # ✅ 必填字段
            row_number=excel_row_number,  # ⭐ v4.6.1修复：使用Excel实际行号
            row_data=json.dumps(row_data_dict, ensure_ascii=False),  # ✅ 正确字段名，JSON格式
            error_type=error.get("type", "unknown"),  # ✅ 正确字段名
            error_msg=error.get("msg", ""),  # ✅ 正确字段名
            platform_code=platform_code,
            shop_id=shop_id,
            data_domain=data_domain,
            created_at=datetime.now()
        )
        db.add(quarantine_record)
        quarantined_count += 1
    
    # 处理警告数据（可选，通常不隔离警告）
    for warning in validation_result.get("warnings", []):
        # 只隔离严重警告
        if warning.get("type") in ["range", "date"]:
            # ⭐ v4.6.1修复：将数组索引转换为Excel实际行号
            row_index = warning.get("row", 0)
            # ⭐ v4.6.1修复：Excel行号 = header_row + row_index + 1
            excel_row_number = header_row + row_index + 1
            
            # 如果header_row > 1，跳过表头行之前的数据
            if excel_row_number <= header_row:
                continue
            
            row_data_dict = {
                "row": row_index,
                "excel_row": excel_row_number,  # ⭐ v4.6.1新增：Excel实际行号
                "col": warning.get("col", ""),
                "raw_value": warning.get("raw_value", ""),
                "suggested": warning.get("suggested", "")
            }
            
            quarantine_record = DataQuarantine(
                catalog_file_id=file_id,  # ✅ 正确字段名
                source_file=source_file_name,
                row_number=excel_row_number,  # ⭐ v4.6.1修复：使用Excel实际行号
                row_data=json.dumps(row_data_dict, ensure_ascii=False),  # ✅ 正确字段名
                error_type=f"warning_{warning.get('type', 'unknown')}",  # ✅ 正确字段名
                error_msg=warning.get("msg", ""),  # ✅ 正确字段名
                platform_code=platform_code,
                shop_id=shop_id,
                data_domain=data_domain,
                created_at=datetime.now()
            )
            db.add(quarantine_record)
            quarantined_count += 1
    
    return quarantined_count


def get_quarantine_summary(db: Session, file_id: int = None) -> Dict[str, Any]:
    """获取隔离区数据摘要（v4.4.1修复字段名）"""
    query = db.query(DataQuarantine)
    if file_id:
        query = query.filter(DataQuarantine.catalog_file_id == file_id)  # ✅ 修复字段名
    
    total_quarantined = query.count()
    
    # 按问题类型分组
    issue_types = {}
    for record in query.all():
        issue_type = record.error_type  # ✅ 修复字段名
        if issue_type not in issue_types:
            issue_types[issue_type] = 0
        issue_types[issue_type] += 1
    
    return {
        "total_quarantined": total_quarantined,
        "issue_types": issue_types,
        "files_affected": len(set(r.catalog_file_id for r in query.all() if r.catalog_file_id))  # ✅ 修复字段名
    }


def upsert_product_metrics(db: Session, rows: List[Dict[str, Any]], file_record: Optional[Any] = None, data_domain: Optional[str] = None) -> int:
    """
    批量UPSERT产品指标数据（优化版）
    性能：1万行从60秒优化到10秒
    
    ⭐ v4.7.0修复：metric_date字段NOT NULL约束处理
    - 如果metric_date为None，使用默认值（今天）或跳过该行
    
    ⭐ v4.6.3修复：双维护问题 - 接收file_record参数，确保platform_code正确
    - 如果rows中没有platform_code，从file_record获取
    - 避免数据被错误标记为"unknown"平台
    
    ⭐ v4.10.0新增：支持data_domain参数
    - 从file_record.data_domain读取，如果没有则使用默认值'products'
    - 支持inventory域数据入库
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from datetime import datetime, date
    
    if not rows:
        return 0
    
    # 检查数据库类型
    db_url = str(db.bind.url)
    is_postgresql = 'postgresql' in db_url
    
    count = 0
    skipped_count = 0
    
    if is_postgresql:
        # PostgreSQL: 使用高性能 ON CONFLICT 批量UPSERT（扁平化schema）
        from sqlalchemy.exc import IntegrityError
        
        try:
            for r in rows:
                # ⭐ v4.7.0修复：处理metric_date字段（NOT NULL约束）
                metric_date = r.get("metric_date")
                
                # 如果metric_date为None，尝试从其他字段获取或使用默认值
                if metric_date is None:
                    # 尝试从其他日期字段获取
                    metric_date = r.get("date") or r.get("metric_date_utc") or r.get("period_start")
                    
                    # 如果仍然为None，使用今天作为默认值（但记录警告）
                    if metric_date is None:
                        metric_date = date.today()
                        logger.warning(f"[upsert_product_metrics] metric_date为None，使用默认值（今天）: {date.today()}, 行数据: platform_code={r.get('platform_code')}, shop_id={r.get('shop_id')}, platform_sku={r.get('platform_sku')}")
                
                # 确保metric_date是date对象（如果是datetime，转换为date）
                if isinstance(metric_date, datetime):
                    metric_date = metric_date.date()
                elif isinstance(metric_date, str):
                    # 尝试解析字符串日期
                    try:
                        from datetime import datetime as dt_parser
                        parsed_date = dt_parser.strptime(metric_date, "%Y-%m-%d").date()
                        metric_date = parsed_date
                    except:
                        metric_date = date.today()
                        logger.warning(f"[upsert_product_metrics] metric_date字符串无法解析，使用默认值: {metric_date}, 原始值: {r.get('metric_date')}")
                
                # 构造UPSERT数据（适配扁平化schema的实际字段名）
                # ⭐ v4.6.3修复：双维护问题 - 确保platform_code正确（优先使用file_record）
                # ⭐ v4.10.0更新：inventory域允许platform_code和shop_id为空（仓库级数据）
                platform_code_value = r.get("platform_code")
                if not platform_code_value:
                    if file_record and file_record.platform_code:
                        platform_code_value = file_record.platform_code
                    else:
                        # v4.10.0更新：inventory域允许为空，其他域使用"unknown"兜底
                        domain_value_check = (
                            data_domain or 
                            (file_record.data_domain if file_record and hasattr(file_record, 'data_domain') and file_record.data_domain else None) or
                            r.get("data_domain") or 
                            "products"
                        )
                        if domain_value_check == "inventory":
                            platform_code_value = None  # inventory域允许为空
                        else:
                            platform_code_value = "unknown"  # 其他域兜底
                
                shop_id_value = r.get("shop_id")
                if not shop_id_value:
                    if file_record and file_record.shop_id:
                        shop_id_value = file_record.shop_id
                    else:
                        # v4.10.0更新：inventory域允许为空，其他域使用"unknown"兜底
                        domain_value_check = (
                            data_domain or 
                            (file_record.data_domain if file_record and hasattr(file_record, 'data_domain') and file_record.data_domain else None) or
                            r.get("data_domain") or 
                            "products"
                        )
                        if domain_value_check == "inventory":
                            shop_id_value = None  # inventory域允许为空
                        else:
                            shop_id_value = "unknown"  # 其他域兜底
                
                # ⭐ v4.6.3修复：兼容多种SKU字段名（product_sku, product_sku_1, platform_sku, sku, spec_sku）
                # ⭐ v4.10.0更新：支持SKU分层分级（商品SKU/产品SKU/规格货号）
                sku_value = (
                    r.get("platform_sku") or      # 产品SKU（具体规格级别，优先）
                    r.get("product_sku") or       # 商品SKU（品类级别）
                    r.get("product_sku_1") or    # 商品SKU（兼容字段）
                    r.get("spec_sku") or         # 规格货号（应映射到产品SKU）
                    r.get("sku") or              # 通用SKU字段
                    "unknown"
                )
                
                # ⭐ v4.10.0新增：获取data_domain（优先级：参数 > file_record > 行数据 > 默认值）
                domain_value = (
                    data_domain or 
                    (file_record.data_domain if file_record and hasattr(file_record, 'data_domain') and file_record.data_domain else None) or
                    r.get("data_domain") or 
                    "products"  # 默认值：向后兼容
                )
                
                # ⭐ 修复：确保created_at不为null（虽然schema有server_default，但显式设置更安全）
                current_time = datetime.utcnow()
                
                data = {
                    "platform_code": platform_code_value,
                    "shop_id": shop_id_value,
                    "platform_sku": sku_value,
                    "metric_date": metric_date,  # ⭐ v4.7.0修复：确保不为None
                    "granularity": r.get("granularity", "daily"),
                    "data_domain": domain_value,  # ⭐ v4.10.0新增：数据域标识
                    "sku_scope": r.get("sku_scope", "product"),  # 新增：sku_scope字段
                    "parent_platform_sku": r.get("parent_platform_sku"),  # 可选：父SKU
                    "source_catalog_id": r.get("source_catalog_id") or (file_record.id if file_record else None),  # ⭐ v4.13.2修复：优先使用行数据，否则使用file_record.id
                    "created_at": current_time,  # ⭐ 修复：显式设置created_at，避免null值
                    "updated_at": current_time,  # ⭐ 修复：显式设置updated_at
                    # 商品基础信息
                    "product_name": r.get("product_name"),
                    "category": r.get("category"),
                    "brand": r.get("brand"),
                    "specification": r.get("specification") or r.get("product_specification"),  # v4.6.3新增：规格
                    # 价格信息
                    # ⭐ v4.6.3修复：妙手ERP数据默认为CNY（人民币），不是USD
                    "currency": r.get("currency") or ("CNY" if platform_code_value == "miaoshou" else "USD"),  # 货币
                    "price": r.get("price"),  # 价格
                    "price_rmb": r.get("price_rmb"),  # 人民币价格
                    # 库存信息（v4.6.3扩展：细分库存）
                    "stock": int(float(r.get("stock", 0) or 0)),  # 旧字段，保留兼容
                    "total_stock": int(float(r.get("total_stock", 0) or 0)) if r.get("total_stock") is not None else None,  # v4.6.3新增
                    "available_stock": int(float(r.get("available_stock", 0) or 0)) if r.get("available_stock") is not None else None,  # v4.6.3新增
                    "reserved_stock": int(float(r.get("reserved_stock", 0) or 0)) if r.get("reserved_stock") is not None else None,  # v4.6.3新增
                    "in_transit_stock": int(float(r.get("in_transit_stock", 0) or 0)) if r.get("in_transit_stock") is not None else None,  # v4.6.3新增
                    # 仓库信息
                    "warehouse": r.get("warehouse"),  # v4.6.3新增：仓库位置
                    # 图片信息
                    "image_url": r.get("image_url"),  # v4.6.3已有
                    # 销售指标
                    "sales_volume": int(float(r.get("sales_volume", r.get("qty", 0)) or 0)),  # 销量（总销量）
                    "sales_amount": float(r.get("sales_amount", r.get("revenue", r.get("total_price", 0)) or 0)),  # 销售额（兼容total_price）
                    "sales_amount_rmb": float(r.get("sales_amount_rmb", r.get("revenue_rmb", 0)) or 0),  # 人民币销售额
                    # 近期销量数据（v4.6.3新增）
                    "sales_volume_7d": int(float(r.get("sales_volume_7d", 0) or 0)) if r.get("sales_volume_7d") is not None else None,
                    "sales_volume_30d": int(float(r.get("sales_volume_30d", 0) or 0)) if r.get("sales_volume_30d") is not None else None,
                    "sales_volume_60d": int(float(r.get("sales_volume_60d", 0) or 0)) if r.get("sales_volume_60d") is not None else None,
                    "sales_volume_90d": int(float(r.get("sales_volume_90d", 0) or 0)) if r.get("sales_volume_90d") is not None else None,
                    # 流量指标
                    "page_views": int(float(r.get("page_views", r.get("pv", 0)) or 0)),
                    "unique_visitors": int(float(r.get("unique_visitors", r.get("uv", 0)) or 0)),
                    "click_through_rate": float(r.get("click_through_rate", r.get("ctr", 0)) or 0),
                    "order_count": int(float(r.get("order_count", r.get("orders", 0)) or 0)),  # 订单数
                    # 转化指标
                    "conversion_rate": float(r.get("conversion_rate", r.get("conversion", 0)) or 0),
                    "add_to_cart_count": int(float(r.get("add_to_cart_count", r.get("add_to_cart", 0)) or 0)),  # 加购数
                    # 评价指标
                    "rating": float(r.get("rating", 0) or 0),
                    "review_count": int(float(r.get("review_count", r.get("reviews", 0)) or 0)),
                    # 时间和区间
                    "period_start": r.get("period_start"),  # 区间起始
                    "metric_date_utc": r.get("metric_date_utc"),  # UTC日期
                }
                
                # PostgreSQL ON CONFLICT DO UPDATE（基于复合唯一索引，包含sku_scope和data_domain）
                stmt = pg_insert(FactProductMetric).values(**data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['platform_code', 'shop_id', 'platform_sku', 'metric_date', 'granularity', 'sku_scope', 'data_domain'],  # ⭐ v4.10.0新增：添加data_domain
                    set_={
                        # ⭐ 修复：更新时也更新updated_at
                        "updated_at": datetime.utcnow(),
                        # 商品基础信息
                        "product_name": stmt.excluded.product_name,
                        "category": stmt.excluded.category,
                        "brand": stmt.excluded.brand,
                        "specification": stmt.excluded.specification,  # v4.6.3新增
                        "data_domain": stmt.excluded.data_domain,  # ⭐ v4.10.0新增：更新data_domain字段
                        "parent_platform_sku": stmt.excluded.parent_platform_sku,
                        "source_catalog_id": stmt.excluded.source_catalog_id,
                        # 价格信息
                        "currency": stmt.excluded.currency,
                        "price": stmt.excluded.price,
                        "price_rmb": stmt.excluded.price_rmb,
                        # 库存信息（v4.6.3扩展）
                        "stock": stmt.excluded.stock,
                        "total_stock": stmt.excluded.total_stock,  # v4.6.3新增
                        "available_stock": stmt.excluded.available_stock,  # v4.6.3新增
                        "reserved_stock": stmt.excluded.reserved_stock,  # v4.6.3新增
                        "in_transit_stock": stmt.excluded.in_transit_stock,  # v4.6.3新增
                        # 仓库信息
                        "warehouse": stmt.excluded.warehouse,  # v4.6.3新增
                        # 图片信息
                        "image_url": stmt.excluded.image_url,  # v4.6.3
                        # 销售指标
                        "sales_volume": stmt.excluded.sales_volume,
                        "sales_amount": stmt.excluded.sales_amount,
                        "sales_amount_rmb": stmt.excluded.sales_amount_rmb,
                        # 近期销量数据（v4.6.3新增）
                        "sales_volume_7d": stmt.excluded.sales_volume_7d,  # v4.6.3新增
                        "sales_volume_30d": stmt.excluded.sales_volume_30d,  # v4.6.3新增
                        "sales_volume_60d": stmt.excluded.sales_volume_60d,  # v4.6.3新增
                        "sales_volume_90d": stmt.excluded.sales_volume_90d,  # v4.6.3新增
                        # 流量指标
                        "page_views": stmt.excluded.page_views,
                        "unique_visitors": stmt.excluded.unique_visitors,
                        "click_through_rate": stmt.excluded.click_through_rate,
                        "order_count": stmt.excluded.order_count,
                        # 转化指标
                        "conversion_rate": stmt.excluded.conversion_rate,
                        "add_to_cart_count": stmt.excluded.add_to_cart_count,
                        # 评价指标
                        "rating": stmt.excluded.rating,
                        "review_count": stmt.excluded.review_count,
                        # 时间和区间
                        "period_start": stmt.excluded.period_start,
                        "metric_date_utc": stmt.excluded.metric_date_utc,
                    }
                )
                db.execute(stmt)
                count += 1
            
            # 批量提交
            db.commit()
            if skipped_count > 0:
                logger.warning(f"[upsert_product_metrics] 跳过了 {skipped_count} 行数据（metric_date无法解析）")
        except IntegrityError as e:
            db.rollback()
            logger.error(f"[upsert_product_metrics] 数据完整性错误: {e}", exc_info=True)
            raise HTTPException(status_code=400, detail=f"数据冲突: {str(e)}")
        except Exception as e:
            db.rollback()
            logger.error(f"[upsert_product_metrics] 数据入库失败: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"入库失败: {str(e)}")
        
    else:
        # SQLite: 使用扁平化schema（实际字段名）
        for r in rows:
            # ⭐ v4.7.0修复：处理metric_date字段（NOT NULL约束）
            metric_date = r.get("metric_date")
            
            # 如果metric_date为None，尝试从其他字段获取或使用默认值
            if metric_date is None:
                metric_date = r.get("date") or r.get("metric_date_utc") or r.get("period_start")
                if metric_date is None:
                    metric_date = date.today()
                    logger.warning(f"[upsert_product_metrics] metric_date为None，使用默认值（今天）: {date.today()}")
            
            # 确保metric_date是date对象
            if isinstance(metric_date, datetime):
                metric_date = metric_date.date()
            elif isinstance(metric_date, str):
                try:
                    from datetime import datetime as dt_parser
                    parsed_date = dt_parser.strptime(metric_date, "%Y-%m-%d").date()
                    metric_date = parsed_date
                except:
                    metric_date = date.today()
                    logger.warning(f"[upsert_product_metrics] metric_date字符串无法解析，使用默认值: {metric_date}")
            
            # ⭐ v4.6.3修复：双维护问题 - 确保platform_code正确（优先使用file_record）
            # ⭐ v4.10.0更新：inventory域允许platform_code和shop_id为空（仓库级数据）
            platform_code_value = r.get("platform_code")
            if not platform_code_value:
                if file_record and file_record.platform_code:
                    platform_code_value = file_record.platform_code
                else:
                    # v4.10.0更新：inventory域允许为空，其他域使用"unknown"兜底
                    domain_value_check = (
                        data_domain or 
                        (file_record.data_domain if file_record and hasattr(file_record, 'data_domain') and file_record.data_domain else None) or
                        r.get("data_domain") or 
                        "products"
                    )
                    if domain_value_check == "inventory":
                        platform_code_value = None  # inventory域允许为空
                    else:
                        platform_code_value = "unknown"  # 其他域兜底
            
            shop_id_value = r.get("shop_id")
            if not shop_id_value:
                if file_record and file_record.shop_id:
                    shop_id_value = file_record.shop_id
                else:
                    # v4.10.0更新：inventory域允许为空，其他域使用"unknown"兜底
                    domain_value_check = (
                        data_domain or 
                        (file_record.data_domain if file_record and hasattr(file_record, 'data_domain') and file_record.data_domain else None) or
                        r.get("data_domain") or 
                        "products"
                    )
                    if domain_value_check == "inventory":
                        shop_id_value = None  # inventory域允许为空
                    else:
                        shop_id_value = "unknown"  # 其他域兜底
            
            # ⭐ v4.6.3修复：兼容多种SKU字段名（product_sku, product_sku_1, platform_sku, sku, spec_sku）
            # ⭐ v4.10.0更新：支持SKU分层分级（商品SKU/产品SKU/规格货号）
            sku_value = (
                r.get("platform_sku") or      # 产品SKU（具体规格级别，优先）
                r.get("product_sku") or       # 商品SKU（品类级别）
                r.get("product_sku_1") or     # 商品SKU（兼容字段）
                r.get("spec_sku") or          # 规格货号（应映射到产品SKU）
                r.get("sku") or               # 通用SKU字段
                "unknown"
            )
            
            # ⭐ v4.10.0新增：获取data_domain（优先级：参数 > file_record > 行数据 > 默认值）
            domain_value = (
                data_domain or 
                (file_record.data_domain if file_record and hasattr(file_record, 'data_domain') and file_record.data_domain else None) or
                r.get("data_domain") or 
                "products"  # 默认值：向后兼容
            )
            
            obj = FactProductMetric(
                platform_code=platform_code_value,
                shop_id=shop_id_value,
                platform_sku=sku_value,
                metric_date=metric_date,  # ⭐ v4.7.0修复：确保不为None
                granularity=r.get("granularity", "daily"),
                data_domain=domain_value,  # ⭐ v4.10.0新增：数据域标识
                sku_scope=r.get("sku_scope", "product"),  # 新增：sku_scope字段
                parent_platform_sku=r.get("parent_platform_sku"),  # 可选：父SKU
                source_catalog_id=r.get("source_catalog_id") or (file_record.id if file_record else None),  # ⭐ v4.13.2修复：优先使用行数据，否则使用file_record.id
                # 商品基础信息
                product_name=r.get("product_name"),
                category=r.get("category"),
                brand=r.get("brand"),
                specification=r.get("specification") or r.get("product_specification"),  # v4.6.3新增
                # 价格信息
                # ⭐ v4.6.3修复：妙手ERP数据默认为CNY（人民币），不是USD
                currency=r.get("currency") or ("CNY" if platform_code_value == "miaoshou" else "USD"),
                price=r.get("price"),
                price_rmb=r.get("price_rmb"),
                # 库存信息（v4.6.3扩展）
                stock=int(float(r.get("stock", 0) or 0)),
                total_stock=int(float(r.get("total_stock", 0) or 0)) if r.get("total_stock") is not None else None,
                available_stock=int(float(r.get("available_stock", 0) or 0)) if r.get("available_stock") is not None else None,
                reserved_stock=int(float(r.get("reserved_stock", 0) or 0)) if r.get("reserved_stock") is not None else None,
                in_transit_stock=int(float(r.get("in_transit_stock", 0) or 0)) if r.get("in_transit_stock") is not None else None,
                # 仓库信息
                warehouse=r.get("warehouse"),  # v4.6.3新增
                # 图片信息
                image_url=r.get("image_url"),
                # 销售指标
                sales_volume=int(float(r.get("sales_volume", r.get("qty", 0)) or 0)),
                sales_amount=float(r.get("sales_amount", r.get("revenue", r.get("total_price", 0)) or 0)),  # 销售额（兼容total_price）
                sales_amount_rmb=float(r.get("sales_amount_rmb", r.get("revenue_rmb", 0)) or 0),
                # 近期销量数据（v4.6.3新增）
                sales_volume_7d=int(float(r.get("sales_volume_7d", 0) or 0)) if r.get("sales_volume_7d") is not None else None,
                sales_volume_30d=int(float(r.get("sales_volume_30d", 0) or 0)) if r.get("sales_volume_30d") is not None else None,
                sales_volume_60d=int(float(r.get("sales_volume_60d", 0) or 0)) if r.get("sales_volume_60d") is not None else None,
                sales_volume_90d=int(float(r.get("sales_volume_90d", 0) or 0)) if r.get("sales_volume_90d") is not None else None,
                # 流量指标
                page_views=int(float(r.get("page_views", r.get("pv", 0)) or 0)),
                unique_visitors=int(float(r.get("unique_visitors", r.get("uv", 0)) or 0)),
                click_through_rate=float(r.get("click_through_rate", r.get("ctr", 0)) or 0),
                order_count=int(float(r.get("order_count", r.get("orders", 0)) or 0)),
                # 转化指标
                conversion_rate=float(r.get("conversion_rate", r.get("conversion", 0)) or 0),
                add_to_cart_count=int(float(r.get("add_to_cart_count", r.get("add_to_cart", 0)) or 0)),
                # 评价指标
                rating=float(r.get("rating", 0) or 0),
                review_count=int(float(r.get("review_count", r.get("reviews", 0)) or 0)),
                # 时间和区间
                period_start=r.get("period_start"),
                metric_date_utc=r.get("metric_date_utc"),
            )
            try:
                db.add(obj)
                db.commit()
                count += 1
            except Exception:
                db.rollback()
                # UPDATE已存在记录（包含sku_scope字段）
                db.query(FactProductMetric).filter(
                    FactProductMetric.platform_code == obj.platform_code,
                    FactProductMetric.shop_id == obj.shop_id,
                    FactProductMetric.platform_sku == obj.platform_sku,
                    FactProductMetric.metric_date == obj.metric_date,
                    FactProductMetric.granularity == obj.granularity,
                    FactProductMetric.sku_scope == obj.sku_scope,  # 新增：sku_scope条件
                    FactProductMetric.data_domain == obj.data_domain,  # ⭐ v4.10.0新增：data_domain条件
                ).update({
                    # 商品基础信息
                    "product_name": obj.product_name,
                    "category": obj.category,
                    "brand": obj.brand,
                    "specification": obj.specification,  # v4.6.3新增
                    "data_domain": obj.data_domain,  # ⭐ v4.10.0新增：更新data_domain字段
                    "parent_platform_sku": obj.parent_platform_sku,
                    "source_catalog_id": obj.source_catalog_id,
                    # 价格信息
                    "currency": obj.currency,
                    "price": obj.price,
                    "price_rmb": obj.price_rmb,
                    # 库存信息（v4.6.3扩展）
                    "stock": obj.stock,
                    "total_stock": obj.total_stock,  # v4.6.3新增
                    "available_stock": obj.available_stock,  # v4.6.3新增
                    "reserved_stock": obj.reserved_stock,  # v4.6.3新增
                    "in_transit_stock": obj.in_transit_stock,  # v4.6.3新增
                    # 仓库信息
                    "warehouse": obj.warehouse,  # v4.6.3新增
                    # 图片信息
                    "image_url": obj.image_url,
                    # 销售指标
                    "sales_volume": obj.sales_volume,
                    "sales_amount": obj.sales_amount,
                    "sales_amount_rmb": obj.sales_amount_rmb,
                    # 近期销量数据（v4.6.3新增）
                    "sales_volume_7d": obj.sales_volume_7d,  # v4.6.3新增
                    "sales_volume_30d": obj.sales_volume_30d,  # v4.6.3新增
                    "sales_volume_60d": obj.sales_volume_60d,  # v4.6.3新增
                    "sales_volume_90d": obj.sales_volume_90d,  # v4.6.3新增
                    # 流量指标
                    "page_views": obj.page_views,
                    "unique_visitors": obj.unique_visitors,
                    "click_through_rate": obj.click_through_rate,
                    "order_count": obj.order_count,
                    # 转化指标
                    "conversion_rate": obj.conversion_rate,
                    "add_to_cart_count": obj.add_to_cart_count,
                    # 评价指标
                    "rating": obj.rating,
                    "review_count": obj.review_count,
                    # 时间和区间
                    "period_start": obj.period_start,
                    "metric_date_utc": obj.metric_date_utc,
                })
                db.commit()
                count += 1
    
    return count


# ✅ v4.4.1修复：删除重复定义，这是第二个定义（保留第一个）
# 第一个定义在行292，已修复字段名匹配问题


def get_quarantine_summary(db: Session, file_id: int = None) -> Dict[str, Any]:
    """获取隔离区数据摘要（v4.4.1修复字段名）"""
    query = db.query(DataQuarantine)
    if file_id:
        query = query.filter(DataQuarantine.catalog_file_id == file_id)  # ✅ 修复字段名
    
    total_quarantined = query.count()
    
    # 按问题类型分组
    issue_types = {}
    for record in query.all():
        issue_type = record.error_type  # ✅ 修复字段名
        if issue_type not in issue_types:
            issue_types[issue_type] = 0
        issue_types[issue_type] += 1
    
    return {
        "total_quarantined": total_quarantined,
        "issue_types": issue_types,
        "files_affected": len(set(r.catalog_file_id for r in query.all() if r.catalog_file_id))  # ✅ 修复字段名
    }


