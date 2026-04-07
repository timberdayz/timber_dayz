"""
字段映射API路由 - 数据入库与模板子模块

包含数据预览、映射生成、入库、验证、模板管理等端点。
端点: preview, generate-mapping, ingest, validate, save-template, apply-template,
      templates, template-cache/stats, template-cache/cleanup, template-cache/similar
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any
from datetime import datetime
from pathlib import Path
import re

from backend.models.database import get_async_db, FieldMapping, CatalogFile
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from backend.services.field_mapping.mapper import suggest_mappings
from backend.services.data_validator import validate_orders, validate_product_metrics, validate_services
from backend.services.data_importer import (
    stage_orders,
    stage_product_metrics,
    stage_inventory,
    upsert_orders,
    upsert_product_metrics,
    quarantine_failed_data,
    get_quarantine_summary,
)
from backend.services.data_standardizer import standardize_rows
from backend.services.currency_extractor import get_currency_extractor
from modules.core.logger import get_logger
from backend.routers._field_mapping_helpers import _safe_resolve_path

logger = get_logger(__name__)

router = APIRouter()


def check_if_all_zero_data(rows: List[Dict], domain: str, mappings: Dict = None) -> bool:
    """
    检查数据是否全为0(v4.6.1增强 - 检查所有数值字段)
    
    用于区分:
    - 数据源本身为0(正常情况,如采集期间无业务)
    - 系统错误导致0条(异常情况)
    """
    if not rows:
        return False
    
    numeric_fields = set()
    
    if mappings:
        numeric_keywords = ['amount', 'price', 'qty', 'quantity', 'count', 'rate', 'ratio', 
                           'sales', 'revenue', 'cost', 'profit', 'stock', 'inventory',
                           'views', 'visitors', 'conversion', 'refund', 'gmv']
        
        for orig_col, mapping_info in mappings.items():
            if isinstance(mapping_info, dict):
                std_field = mapping_info.get('standard_field')
            else:
                std_field = mapping_info
            
            if std_field and std_field != '未映射':
                std_field_lower = std_field.lower()
                if any(keyword in std_field_lower for keyword in numeric_keywords):
                    numeric_fields.add(std_field)
    
    numeric_fields_by_domain = {
        "orders": ["total_amount", "qty", "gmv", "unit_price", "sales_amount", "refund_amount"],
        "products": ["page_views", "unique_visitors", "sales_amount", "stock"],
        "traffic": ["page_views", "unique_visitors", "conversion_rate", "visitor_count", "chat_inquiry_count"],
        "services": ["amount"]
    }
    
    predefined_fields = numeric_fields_by_domain.get(domain, [])
    numeric_fields.update(predefined_fields)
    
    if rows:
        first_row = rows[0]
        for key, value in first_row.items():
            if value is not None:
                try:
                    float_val = float(value)
                    if not any(kw in key.lower() for kw in ['id', 'date', 'time', '编号', '日期', '时间']):
                        numeric_fields.add(key)
                except (ValueError, TypeError):
                    pass
    
    if not numeric_fields:
        return False
    
    non_zero_found = False
    for row in rows:
        for field in numeric_fields:
            value = row.get(field)
            if value is not None:
                try:
                    float_val = float(value)
                    if abs(float_val) > 1e-10:
                        non_zero_found = True
                        break
                except (ValueError, TypeError):
                    pass
        if non_zero_found:
            break
    
    return not non_zero_found


@router.post("/preview")
async def preview_file(file_data: dict, db: AsyncSession = Depends(get_async_db)):
    """
    预览文件数据(v4.3.1优化版:从catalog_files查询路径,毫秒级响应)
    """
    file_id = int(file_data.get("file_id", 0))
    header_row = int(file_data.get("header_row", 0))
    
    logger.info(f"[Preview] 开始预览: id={file_id}")
    
    try:
        catalog_result = await db.execute(
            select(CatalogFile).where(CatalogFile.id == file_id)
        )
        catalog_record = catalog_result.scalar_one_or_none()
        
        if not catalog_record:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件未注册",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"文件未注册: id={file_id}",
                recovery_suggestion="请先扫描采集文件,确保文件已注册到系统中",
                status_code=404
            )
        
        file_path = catalog_record.file_path
        logger.info(f"[Preview] 文件路径: {file_path}")
        
        safe_path = _safe_resolve_path(file_path)
        if not Path(safe_path).exists():
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"文件不存在: {file_path}",
                recovery_suggestion="请检查文件路径是否正确,或重新扫描采集文件",
                status_code=404
            )
        
        from backend.services.excel_parser import ExcelParser
        
        if header_row < 0:
            header_param = None
        else:
            header_param = header_row
        
        file_size_mb = Path(safe_path).stat().st_size / (1024 * 1024)
        preview_rows = 50 if file_size_mb > 10 else 100
        
        logger.info(f"[Preview] 文件大小: {file_size_mb:.2f}MB, 预览行数: {preview_rows}")
        
        df = ExcelParser.read_excel(
            safe_path,
            header=header_param,
            nrows=preview_rows
        )
        normalization_report = {}
        try:
            df, normalization_report = ExcelParser.normalize_table(
                df,
                data_domain=catalog_record.data_domain or "products",
                file_size_mb=file_size_mb
            )
            if file_size_mb > 10:
                logger.info(f"[Preview] 大文件规范化完成(只处理关键列): {file_size_mb:.2f}MB")
        except Exception as norm_error:
            logger.warning(f"[Preview] 规范化失败(使用原始数据): {norm_error}", exc_info=True)
            normalization_report = {"filled_columns": [], "filled_rows": 0, "strategy": "none", "error": str(norm_error)}
        
        df.columns = [str(col).strip() for col in df.columns]
        df = df.dropna(how='all')
        df = df.fillna('')
        
        columns = df.columns.tolist()
        preview_rows_limit = 100
        data = df.head(preview_rows_limit).to_dict('records')
        
        data = {
            "file_path": file_path,
            "file_name": catalog_record.file_name,
            "file_size": Path(file_path).stat().st_size,
            "columns": columns,
            "data": data,
            "total_rows": len(df),
            "preview_rows": len(data),
            "preview_limit": preview_rows_limit,
            
            "source_platform": catalog_record.source_platform,
            "data_domain": catalog_record.data_domain,
            "sub_domain": catalog_record.sub_domain,
            "granularity": catalog_record.granularity,
            "quality_score": catalog_record.quality_score,
            "storage_layer": catalog_record.storage_layer or 'raw',
            "date_from": str(catalog_record.date_from) if catalog_record.date_from else None,
            "date_to": str(catalog_record.date_to) if catalog_record.date_to else None,
            "normalization_report": normalization_report,
            
            "platform": catalog_record.platform_code,
        }
        
        logger.info(f"[Preview] 成功: {len(columns)}列, {len(data)}行, 质量={catalog_record.quality_score}")
        return success_response(data=data, message="文件预览成功")
        
    except Exception as e:
        logger.error(f"[Preview] 失败: {e}", exc_info=True)
        
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="文件预览失败",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(e)[:500],
            recovery_suggestion="建议:1) 检查文件格式是否正确;2) 尝试在Excel中重新导出为标准.xlsx;3) 联系技术支持",
            status_code=500
        )

@router.post("/generate-mapping")
async def generate_field_mapping(mapping_data: dict):
    """生成字段映射(智能映射算法)"""
    try:
        columns = mapping_data.get("columns", [])
        domain = mapping_data.get("domain", "products")
        platform = mapping_data.get("platform", "shopee")
        granularity = mapping_data.get("granularity", "daily")
        
        standard_fields = {
            "products": {
                "product_id": "商品ID",
                "product_name": "商品名称", 
                "price": "价格",
                "stock": "库存",
                "sales": "销量",
                "rating": "评分",
                "category": "分类",
                "brand": "品牌",
                "sku": "SKU",
                "description": "描述",
                "image_url": "图片链接",
                "status": "状态"
            },
            "orders": {
                "order_id": "订单ID",
                "order_date": "订单日期",
                "customer_id": "客户ID",
                "total_amount": "订单金额",
                "status": "订单状态",
                "payment_method": "支付方式",
                "shipping_address": "收货地址"
            },
            "analytics": {
                "date": "日期",
                "page_views": "页面浏览量",
                "visitors": "访客数",
                "bounce_rate": "跳出率",
                "conversion_rate": "转化率"
            },
            "finance": {
                "date": "日期",
                "revenue": "收入",
                "cost": "成本",
                "profit": "利润",
                "currency": "货币"
            },
            "services": {
                "date": "日期",
                "service_type": "服务类型",
                "response_time": "响应时间",
                "satisfaction": "满意度",
                "agent_id": "客服ID"
            }
        }
        
        mappings = []
        domain_fields = standard_fields.get(domain, standard_fields["products"])
        
        for column in columns:
            column_lower = column.lower()
            best_match = None
            best_confidence = 0.0
            match_method = "none"
            
            for std_field, std_name in domain_fields.items():
                if column_lower == std_field.lower() or column_lower == std_name.lower():
                    best_match = std_field
                    best_confidence = 1.0
                    match_method = "exact_match"
                    break
            
            if not best_match:
                for std_field, std_name in domain_fields.items():
                    keywords = {
                        "product_id": ["product", "id", "商品", "id"],
                        "product_name": ["product", "name", "商品", "名称", "title"],
                        "price": ["price", "价格", "cost", "费用"],
                        "stock": ["stock", "库存", "quantity", "数量"],
                        "sales": ["sales", "销量", "sold", "售出"],
                        "rating": ["rating", "评分", "score", "评价"],
                        "category": ["category", "分类", "type", "类型"],
                        "brand": ["brand", "品牌", "manufacturer"],
                        "sku": ["sku", "code", "编码"],
                        "description": ["description", "描述", "desc", "detail"],
                        "image_url": ["image", "图片", "photo", "url"],
                        "status": ["status", "状态", "state"]
                    }
                    
                    if std_field in keywords:
                        for keyword in keywords[std_field]:
                            if keyword in column_lower:
                                confidence = 0.8
                                if confidence > best_confidence:
                                    best_match = std_field
                                    best_confidence = confidence
                                    match_method = "fuzzy_match"
                                break
            
            if not best_match:
                for std_field, std_name in domain_fields.items():
                    if std_field in column_lower or std_name in column:
                        confidence = 0.6
                        if confidence > best_confidence:
                            best_match = std_field
                            best_confidence = confidence
                            match_method = "keyword"
            
            mappings.append({
                "original": column,
                "standard": best_match or "未映射",
                "confidence": best_confidence,
                "method": match_method
            })
        
        data = {
            "mappings": mappings,
            "source": "ai_generated",
            "domain": domain,
            "platform": platform,
            "granularity": granularity
        }
        
        return success_response(data=data, message="字段映射生成成功")
    except Exception as e:
        logger.error(f"生成字段映射失败: {str(e)}", exc_info=True)
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="生成字段映射失败",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(e),
            status_code=500
        )

@router.post("/ingest")
async def ingest_file(
    ingest_data: dict, 
    db: AsyncSession = Depends(get_async_db),
    extract_images: bool = True
):
    """
    数据入库(集成隔离机制 + v3.0图片提取)
    """
    try:
        file_id = int(ingest_data.get("file_id", 0))
        platform = ingest_data.get("platform", "")
        domain = ingest_data.get("domain") or ingest_data.get("data_domain", "")
        mappings = ingest_data.get("mappings", {})
        header_columns = ingest_data.get("header_columns", [])
        rows = ingest_data.get("rows", [])
        header_row = ingest_data.get("header_row", 0)
        if header_row is None:
            header_row = 0
        
        task_id = ingest_data.get("task_id")
        if not task_id:
            task_id = f"single_file_{file_id}" if file_id else None

        file_record_result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
        file_record = file_record_result.scalar_one_or_none()
        if not file_record:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件记录不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail="文件记录不存在",
                recovery_suggestion="请先扫描采集文件,确保文件已注册到系统中",
                status_code=404
            )
        
        if not domain and file_record.data_domain:
            domain = file_record.data_domain
            logger.info(f"[Ingest] 从文件记录获取data_domain(二次确认): {domain}")
        
        logger.info(f"[Ingest] 数据域: {domain}, header_row: {header_row} (0-based, Excel第{header_row+1}行)")
        
        if file_record.status == "ingested":
            error_msg = file_record.error_message or ""
            if "[全0数据标识]" in error_msg:
                data = {
                    "message": "该文件已识别为全0数据文件,无需重复入库。所有数值字段均为0,这是正常情况(如采集期间无业务)。",
                    "staged": 0,
                    "imported": 0,
                    "amount_imported": 0,
                    "quarantined": 0,
                    "skipped": True,
                    "skip_reason": "all_zero_data_already_processed"
                }
                return success_response(data=data)

        logger.info(f"[Ingest] 开始重新读取完整文件: {file_record.file_path}")
        
        from backend.services.excel_parser import ExcelParser
        
        safe_path = _safe_resolve_path(file_record.file_path)
        if not Path(safe_path).exists():
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="文件不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"文件不存在: {file_record.file_path}",
                recovery_suggestion="请检查文件路径是否正确,或重新扫描采集文件",
                status_code=404
            )
        
        if header_row < 0:
            header_param = None
        else:
            header_param = header_row
        
        logger.info(f"[Ingest] 实际使用的表头行: header_param={header_param} (0-based, Excel第{header_param+1 if header_param is not None else '无表头'}行)")
        
        try:
            df = ExcelParser.read_excel(
                safe_path,
                header=header_param,
                nrows=None
            )
            
            file_size_mb = Path(safe_path).stat().st_size / (1024 * 1024)
            normalization_report = {}
            try:
                df, normalization_report = ExcelParser.normalize_table(
                    df,
                    data_domain=domain or "products",
                    file_size_mb=file_size_mb
                )
                if file_size_mb > 10:
                    logger.info(f"[Ingest] 大文件规范化完成(只处理关键列): {file_size_mb:.2f}MB")
            except Exception as norm_error:
                logger.warning(f"[Ingest] 规范化失败(使用原始数据): {norm_error}", exc_info=True)
                normalization_report = {"filled_columns": [], "filled_rows": 0, "strategy": "none", "error": str(norm_error)}
            
            df.columns = [str(col).strip() for col in df.columns]
            df = df.dropna(how='all')
            df = df.fillna('')
            
            all_rows = df.to_dict('records')
            logger.info(f"[Ingest] 读取完整文件成功: {len(all_rows)}行数据")
            
        except Exception as read_error:
            logger.error(f"[Ingest] 读取文件失败: {read_error}", exc_info=True)
            return error_response(
                code=ErrorCode.FILE_OPERATION_ERROR,
                message="读取文件失败",
                error_type=get_error_type(ErrorCode.FILE_OPERATION_ERROR),
                detail=str(read_error),
                recovery_suggestion="请检查文件格式是否正确,或尝试重新导出文件",
                status_code=500
            )
        
        file_original_columns = list(df.columns)
        original_header_columns = file_original_columns
        
        if not header_columns:
            header_columns = file_original_columns
            logger.info(f"[Ingest] 未提供header_columns,从DataFrame获取: {len(header_columns)}个字段")
        else:
            logger.info(f"[Ingest] 使用传入的header_columns: {len(header_columns)}个字段(但实际使用文件原始列名)")
        
        enhanced_rows = all_rows
        
        processed_mappings = {}
        if mappings:
            for orig_col, mapping_info in mappings.items():
                if isinstance(mapping_info, dict):
                    processed_mappings[orig_col] = mapping_info
                elif isinstance(mapping_info, str):
                    processed_mappings[orig_col] = {"standard_field": mapping_info, "confidence": 0.95}
            logger.info(f"[Ingest] 检测到mappings参数({len(processed_mappings)}个),DSS架构将忽略,直接使用原始数据")
        
        logger.info(f"[Ingest] [DSS] 准备入库原始数据到B类数据表,{len(enhanced_rows)}行,{len(header_columns)}个字段")
        
        logger.info(f"[Ingest] [DSS] 跳过数据标准化,保留原始数据格式")
        logger.info(f"[Ingest] [DSS] 跳过特殊处理,保留原始数据完整性")
        
        logger.info(f"[Ingest] [DSS] 跳过数据验证,所有{len(enhanced_rows)}行数据将直接进入去重和入库流程")
        validation_result = {
            "errors": [],
            "warnings": [],
            "ok_rows": len(enhanced_rows),
            "total": len(enhanced_rows)
        }
        quarantined_count = 0

        valid_rows = enhanced_rows
        error_rows = []

        staged = 0
        imported = 0
        amount_imported = 0
        
        if valid_rows:
            try:
                from backend.services.raw_data_importer import RawDataImporter
                from backend.services.deduplication_service import DeduplicationService
                
                granularity = file_record.granularity if file_record.granularity else "daily"
                if not granularity:
                    granularity = "snapshot" if domain == "inventory" else "daily"
                
                logger.info(f"[Ingest] DSS架构:准备入库到B类数据表,domain={domain}, granularity={granularity}")
                
                raw_data_importer = RawDataImporter(db)
                deduplication_service = DeduplicationService(db)
                
                data_hashes = deduplication_service.batch_calculate_data_hash(valid_rows)
                
                currency_extractor = get_currency_extractor()
                normalized_rows = []
                currency_codes = []
                
                for row in valid_rows:
                    normalized_row = {}
                    for field_name, value in row.items():
                        normalized_field_name = currency_extractor.normalize_field_name(field_name)
                        normalized_row[normalized_field_name] = value
                    normalized_rows.append(normalized_row)
                    
                    currency_code = currency_extractor.extract_currency_from_row(
                        row,
                        header_columns=None
                    )
                    currency_codes.append(currency_code)
                
                sub_domain_value = None
                if file_record and hasattr(file_record, 'sub_domain'):
                    sub_domain_value = file_record.sub_domain
                
                normalized_header_columns = currency_extractor.normalize_field_list(original_header_columns)
                
                imported = raw_data_importer.batch_insert_raw_data(
                    rows=normalized_rows,
                    data_hashes=data_hashes,
                    data_domain=domain,
                    granularity=granularity,
                    platform_code=file_record.platform_code or platform,
                    shop_id=file_record.shop_id,
                    file_id=file_record.id,
                    header_columns=normalized_header_columns,
                    currency_codes=currency_codes,
                    sub_domain=sub_domain_value,
                    original_header_columns=original_header_columns
                )
                
                table_suffix = f"{domain}_{granularity}"
                if sub_domain_value:
                    table_suffix = f"{domain}_{sub_domain_value}_{granularity}"
                logger.info(f"[Ingest] DSS架构:成功入库 {imported} 条记录到 fact_raw_data_{table_suffix}")
                
                staged = imported
                
            except Exception as dss_error:
                logger.error(f"[Ingest] DSS架构入库失败,降级到旧逻辑: {dss_error}", exc_info=True)
            
            if domain == "orders":
                staged = stage_orders(db, valid_rows, ingest_task_id=task_id, file_id=file_id)
                imported = upsert_orders(db, valid_rows, file_record=file_record)
            elif domain == "inventory":
                staged = stage_inventory(db, valid_rows, ingest_task_id=task_id, file_id=file_id)
                for row in valid_rows:
                    row['data_domain'] = 'inventory'
                    if not row.get('granularity'):
                        row['granularity'] = 'snapshot'
                imported = upsert_product_metrics(db, valid_rows, file_record=file_record, data_domain='inventory')
            else:
                staged = stage_product_metrics(db, valid_rows, ingest_task_id=task_id, file_id=file_id)
                imported = upsert_product_metrics(db, valid_rows, file_record=file_record)

        if validation_result.get("errors"):
            file_record.status = "partial_success"
        else:
            file_record.status = "ingested"
        try:
            setattr(file_record, "last_processed_at", datetime.now())
        except Exception:
            file_record.last_processed = datetime.now()
        await db.commit()
        
        image_extraction_started = False
        if extract_images and imported > 0:
            try:
                from backend.tasks.image_extraction import extract_product_images_task
                
                extract_product_images_task.delay(
                    file_id=file_id,
                    file_path=file_record.file_path,
                    platform_code=platform,
                    shop_id=file_record.shop_id or "unknown"
                )
            except (ImportError, Exception) as e:
                error_type = type(e).__name__
                if "OperationalError" in error_type or "ConnectionError" in error_type:
                    logger.warning(
                        f"[字段映射] Redis/Celery连接失败({error_type}),跳过图片提取任务"
                    )
                else:
                    logger.warning(
                        f"[字段映射] 图片提取任务调用失败({error_type}),跳过"
                    )
                
                image_extraction_started = True
                logger.info(f"[Ingest] 图片提取任务已提交: file_id={file_id}")
                
            except ImportError:
                logger.warning("[Ingest] Celery未配置,图片提取任务跳过(同步模式下可手动调用)")
            except Exception as img_error:
                logger.warning(f"[Ingest] 图片提取任务提交失败(继续): {img_error}")

        if imported == 0:
            all_zero = check_if_all_zero_data(valid_rows, domain, processed_mappings)
            
            reasons = []
            if quarantined_count > 0:
                reasons.append(f"{quarantined_count}条因数据质量问题被隔离")
            if len(valid_rows) == 0 and len(error_rows) > 0:
                reasons.append(f"所有{len(error_rows)}条记录验证失败")
            
            if all_zero:
                reasons.append("数据源本身所有数值列均为0(非系统错误)")
                
                existing_msg = file_record.error_message or ""
                file_record.error_message = existing_msg + f"\n[全0数据标识] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 所有数值字段为0,已识别"
                await db.commit()
                
                message = f"入库成功,但导入0条有效记录。原因:{'; '.join(reasons) if reasons else '数据源无有效记录'}。\n提示:数据源所有数值字段均为0,这是正常情况(如采集期间无业务),无需查看隔离区。"
            else:
                message = f"入库成功,但导入0条有效记录。原因:{'; '.join(reasons) if reasons else '数据源无有效记录'}"
        else:
            message = f"入库完成,成功导入{imported}条记录"
        
        mapped_rows = all_rows
        
        data = {
            "message": message,
            "staged": staged, 
            "imported": imported,
            "amount_imported": amount_imported,
            "quarantined": quarantined_count,
            "image_extraction": "processing" if image_extraction_started else "skipped",
            "validation": {
                "total_rows": len(mapped_rows),
                "preview_rows": len(rows) if rows else 0,
                "valid_rows": len(valid_rows),
                "error_rows": len(error_rows),
                "warnings": len(validation_result.get("warnings", []))
            },
            "analysis": {
                "all_zero_data": check_if_all_zero_data(valid_rows, domain, processed_mappings) if imported == 0 else False,
                "quarantine_summary": get_quarantine_summary(db, file_record.id) if quarantined_count > 0 else None
            }
        }
        
        return success_response(data=data, message=message)
    except Exception as e:
        await db.rollback()
        logger.error(f"[Ingest] 入库失败: {e}", exc_info=True)
        error_detail = str(e)
        if hasattr(e, '__cause__') and e.__cause__:
            error_detail = f"{error_detail}\n原因: {str(e.__cause__)}"
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="数据入库失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=error_detail,
            status_code=500
        )


@router.post("/validate")
async def validate_data(payload: dict):
    """数据验证接口(支持库存、财务和订单关联验证)"""
    try:
        from backend.services.enhanced_data_validator import (
            validate_inventory, 
            validate_finance,
            validate_order_inventory_relation,
            validate_order_finance_relation
        )
        
        domain = payload.get("domain", "orders")
        rows = payload.get("rows", [])
        
        if domain == "orders":
            result = validate_orders(rows)
        elif domain == "inventory":
            result = validate_inventory(rows)
        elif domain == "finance":
            result = validate_finance(rows)
        elif domain == "services":
            result = validate_services(rows)
        else:
            result = validate_product_metrics(rows)
        
        if domain == "orders":
            inventory_data = payload.get("inventory_data", [])
            finance_data = payload.get("finance_data", [])
            
            if inventory_data:
                inventory_relation = validate_order_inventory_relation(rows, inventory_data)
                result["inventory_relation"] = inventory_relation
            
            if finance_data:
                finance_relation = validate_order_finance_relation(rows, finance_data)
                result["finance_relation"] = finance_relation
        
        return success_response(data=result)
    except Exception as e:
        logger.error(f"数据验证失败: {e}")
        return error_response(
            code=ErrorCode.DATA_VALIDATION_FAILED,
            message="数据验证失败",
            error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
            detail=str(e),
            status_code=500
        )


@router.post("/save-template")
async def save_template_deprecated(payload: dict, db: AsyncSession = Depends(get_async_db)):
    """
    [DEPRECATED v4.5.1] 此API已废弃
    
    请使用新API: POST /field-mapping/dictionary/templates/save
    """
    return error_response(
        code=ErrorCode.API_DEPRECATED,
        message="API已废弃",
        error_type=get_error_type(ErrorCode.API_DEPRECATED),
        detail={
            "deprecated_since": "v4.5.1",
            "removed_in": "v4.6.0",
            "alternative": "POST /field-mapping/dictionary/templates/save",
            "migration_guide": "前端已自动使用新API,后端请勿调用此endpoint",
            "reason": "旧API使用已废弃的field_mappings表,新API使用field_mapping_templates表(符合SSOT原则)"
        },
        recovery_suggestion="请使用新API: POST /field-mapping/dictionary/templates/save",
        status_code=410
    )


@router.post("/apply-template")
async def apply_template_deprecated(payload: dict, db: AsyncSession = Depends(get_async_db)):
    """
    [DEPRECATED v4.5.1] 此API已废弃
    
    请使用新API: POST /field-mapping/dictionary/templates/apply
    """
    return error_response(
        code=ErrorCode.API_DEPRECATED,
        message="API已废弃",
        error_type=get_error_type(ErrorCode.API_DEPRECATED),
        detail={
            "deprecated_since": "v4.5.1",
            "removed_in": "v4.6.0",
            "alternative": "POST /field-mapping/dictionary/templates/apply",
            "migration_guide": "前端已自动使用新API(api.applyTemplateById),后端请勿调用此endpoint",
            "reason": "旧API使用已废弃的field_mappings表,新API使用field_mapping_templates表(符合SSOT原则)",
            "template_features_lost": [
                "header_row自动配置(新API支持)",
                "sub_domain精确匹配(新API支持)",
                "智能降级策略(新API支持)"
            ]
        },
        recovery_suggestion="请使用新API: POST /field-mapping/dictionary/templates/apply",
        status_code=410
    )
    
    # 以下代码不会执行,仅保留作为历史参考
    if False:
        from backend.services.field_mapping.normalizer import normalize_template_key
        from backend.services.field_mapping.entry import get_key_fields

        file_id = payload.get("file_id")
        file_granularity = None
        if file_id:
            file_record_result = await db.execute(select(CatalogFile).where(CatalogFile.id == file_id))
            file_record = file_record_result.scalar_one_or_none()
            if file_record and file_record.granularity:
                file_granularity = file_record.granularity
                logger.info(f"[ApplyTemplate] 从文件元数据读取粒度: {file_granularity}")
        
        key = normalize_template_key(payload)
        source_platform = key["source_platform"]
        domain = key["domain"]
        sub_domain = key["sub_domain"]
        granularity = file_granularity or key["granularity"]
        columns = payload.get("columns", [])
        
        logger.info(f"[ApplyTemplate] {source_platform}/{domain}/{sub_domain}/{granularity} (文件粒度: {file_granularity}, 用户选择: {key['granularity']})")
        
        template = None
        
        if not template:
            if file_granularity and file_granularity != key["granularity"]:
                logger.warning(f"[ApplyTemplate] 粒度不匹配:文件粒度={file_granularity},用户选择={key['granularity']},未找到匹配模板")
            
            logger.info(f"[ApplyTemplate] 未找到模板,使用统一映射入口")
            from backend.services.field_mapping.entry import get_mappings
            suggestions = get_mappings(columns, domain, source_platform)
            key_fields = set(get_key_fields(domain))
            need_review = []
            for col, m in suggestions.items():
                if m.get("standard") in key_fields and (m.get("confidence", 0) < 0.8):
                    need_review.append({"column": col, "standard": m.get("standard"), "confidence": m.get("confidence", 0)})

            return {
                "success": True,
                "mappings": suggestions,
                "source": "ai_suggested",
                "message": f"未找到{source_platform}/{domain}/{granularity}的模板,使用智能映射",
                "need_review": need_review,
                "granularity_warning": file_granularity and file_granularity != key["granularity"]
            }
        
        template_mappings_result = await db.execute(
            select(FieldMapping).where(
                FieldMapping.platform == template.platform,
                FieldMapping.domain == template.domain,
                FieldMapping.sub_domain == template.sub_domain,
                FieldMapping.granularity == template.granularity,
                FieldMapping.version == template.version
            )
        )
        template_mappings = template_mappings_result.scalars().all()
        
        template_dict = {t.original_field: {"standard": t.standard_field, "confidence": t.confidence} for t in template_mappings}
        
        mapping_dict = {}
        for col in columns:
            matched = False
            
            if col in template_dict:
                mapping_dict[col] = template_dict[col]
                matched = True
            else:
                col_normalized = re.sub(r'[\s_\-()()]', '', col.lower())
                for template_col, mapping in template_dict.items():
                    template_col_normalized = re.sub(r'[\s_\-()()]', '', template_col.lower())
                    if col_normalized == template_col_normalized:
                        mapping_dict[col] = mapping
                        matched = True
                        break
            
            if not matched:
                from backend.services.field_mapping.entry import get_mappings
                suggestions = get_mappings([col], domain, source_platform)
                if suggestions and col in suggestions:
                    mapping_dict[col] = suggestions[col]

        return {
            "success": True, 
            "mappings": mapping_dict,
            "source": "template",
            "template_info": {
                "id": template.id,
                "source_platform": template.platform,
                "domain": template.domain,
                "sub_domain": template.sub_domain,
                "granularity": template.granularity,
                "version": template.version,
                "created_at": template.created_at.isoformat() if template.created_at else None
            }
        }


@router.get("/templates")
async def list_templates(platform: str, domain: str, granularity: str | None = None, sheet_name: str | None = None, db: AsyncSession = Depends(get_async_db)):
    """列出模板版本与字段(按平台/域/粒度/Sheet)"""
    try:
        stmt = select(FieldMapping).where(
            FieldMapping.platform == platform,
            FieldMapping.domain == domain,
        )
        if granularity:
            stmt = stmt.where(FieldMapping.granularity == granularity)
        if sheet_name:
            stmt = stmt.where(FieldMapping.sheet_name == sheet_name)
        stmt = stmt.order_by(FieldMapping.version.desc(), FieldMapping.original_field.asc())
        result = await db.execute(stmt)
        rows = result.scalars().all()
        versions = {}
        for r in rows:
            versions.setdefault(r.version, []).append({
                "original": r.original_field,
                "standard": r.standard_field,
                "confidence": r.confidence,
                "sheet_name": r.sheet_name,
                "header_row": None,
            })
        return success_response(data={"versions": versions})
    except Exception as e:
        logger.error(f"获取模板列表失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取模板列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/template-cache/stats")
async def get_template_cache_stats():
    """获取模板缓存统计信息"""
    try:
        from backend.services.template_cache import get_template_cache
        
        cache = get_template_cache()
        stats = cache.get_cache_stats()
        
        return success_response(data={"stats": stats}, message="获取缓存统计成功")
    except Exception as e:
        logger.error(f"获取缓存统计失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取缓存统计失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )

@router.post("/template-cache/cleanup")
async def cleanup_template_cache(days: int = 30):
    """清理过期模板缓存"""
    try:
        from backend.services.template_cache import get_template_cache
        
        cache = get_template_cache()
        deleted_count = cache.cleanup_expired_templates(days)
        
        data = {
            "deleted_count": deleted_count
        }
        
        return success_response(
            data=data,
            message=f"清理完成,删除了 {deleted_count} 个过期模板"
        )
    except Exception as e:
        logger.error(f"清理缓存失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="清理缓存失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )

@router.get("/template-cache/similar")
async def find_similar_templates(platform: str, domain: str, columns: str):
    """查找相似模板"""
    try:
        from backend.services.template_cache import get_template_cache
        
        cache = get_template_cache()
        columns_list = columns.split(',') if columns else []
        similar_templates = cache.find_similar_templates(platform, domain, columns_list)
        
        return success_response(
            data={"similar_templates": similar_templates},
            message="查找相似模板成功"
        )
    except Exception as e:
        logger.error(f"查找相似模板失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查找相似模板失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )
