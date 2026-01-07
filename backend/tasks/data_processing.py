"""
数据处理异步任务
用于处理耗时的Excel文件解析和批量入库
"""

import sys
from pathlib import Path

root_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(root_dir))

from backend.celery_app import celery_app
from backend.models.database import SessionLocal
# ⚠️ v4.19.1：preview 函数已重构，使用 ExcelParser.read_excel 替代
from backend.services.excel_parser import ExcelParser
from backend.services.field_mapping.mapper import suggest_mappings
from backend.services.data_validator import validate_orders, validate_product_metrics
from backend.services.data_importer import (
    stage_orders,
    stage_product_metrics,
    upsert_orders,
    upsert_product_metrics
)
import logging

logger = logging.getLogger(__name__)


@celery_app.task(name="backend.tasks.data_processing.process_excel_file")
def process_excel_file(file_path: str, platform: str, data_domain: str, mappings: dict):
    """
    异步处理Excel文件
    
    Args:
        file_path: Excel文件路径
        platform: 平台代码
        data_domain: 数据域（orders/products）
        mappings: 字段映射字典
    
    Returns:
        处理结果
    """
    db = SessionLocal()
    
    try:
        logger.info(f"[TASK] Processing file: {file_path}")
        
        # 1. 读取Excel文件
        logger.info("  Step 1: Reading Excel...")
        # ⚠️ v4.19.1：使用 ExcelParser 替代旧的 preview_service
        df = ExcelParser.read_excel(file_path)
        rows = df.to_dict('records') if df is not None else []
        
        logger.info(f"  Found {len(rows)} rows")
        
        # 2. 应用字段映射
        logger.info("  Step 2: Applying field mappings...")
        mapped_rows = []
        for row in rows:
            mapped_row = {}
            for original_field, standard_field in mappings.items():
                if isinstance(standard_field, dict):
                    standard_field = standard_field.get("standard")
                if standard_field and original_field in row:
                    mapped_row[standard_field] = row[original_field]
            
            # 添加平台和店铺信息
            mapped_row["platform_code"] = platform
            mapped_rows.append(mapped_row)
        
        # 3. 数据验证
        logger.info("  Step 3: Validating data...")
        if data_domain == "orders":
            validation_result = validate_orders(mapped_rows)
        else:
            validation_result = validate_product_metrics(mapped_rows)
        
        # 只处理有效数据
        valid_rows = []
        error_rows = set()
        for error in validation_result.get("errors", []):
            error_rows.add(error.get("row", 0))
        
        for idx, row in enumerate(mapped_rows):
            if idx not in error_rows:
                valid_rows.append(row)
        
        logger.info(f"  Valid rows: {len(valid_rows)}, Error rows: {len(error_rows)}")
        
        # 4. 数据入库
        logger.info("  Step 4: Inserting to database...")
        staged = 0
        imported = 0
        
        if valid_rows:
            if data_domain == "orders":
                staged = stage_orders(db, valid_rows)
                imported = upsert_orders(db, valid_rows)
            else:
                staged = stage_product_metrics(db, valid_rows)
                imported = upsert_product_metrics(db, valid_rows)
        
        logger.info(f"[OK] Task completed: staged={staged}, imported={imported}")
        
        return {
            "status": "success",
            "file_path": file_path,
            "total_rows": len(rows),
            "valid_rows": len(valid_rows),
            "error_rows": len(error_rows),
            "staged": staged,
            "imported": imported,
            "validation": validation_result
        }
        
    except Exception as e:
        logger.error(f"[ERROR] Task failed: {e}")
        return {
            "status": "failed",
            "file_path": file_path,
            "error": str(e)
        }
    finally:
        db.close()


@celery_app.task(name="backend.tasks.data_processing.batch_process_files")
def batch_process_files(file_list: list, platform: str, data_domain: str):
    """
    批量处理多个Excel文件
    
    Args:
        file_list: 文件路径列表
        platform: 平台代码
        data_domain: 数据域
    
    Returns:
        批量处理结果
    """
    logger.info(f"[BATCH] Processing {len(file_list)} files...")
    
    results = []
    for file_path in file_list:
        # 每个文件作为独立任务
        task = process_excel_file.delay(file_path, platform, data_domain, {})
        results.append({
            "file_path": file_path,
            "task_id": task.id
        })
    
    return {
        "status": "queued",
        "total_files": len(file_list),
        "tasks": results
    }

