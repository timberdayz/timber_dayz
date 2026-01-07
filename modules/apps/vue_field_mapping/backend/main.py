#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Vue.js字段映射审核系统 - FastAPI后端

⚠️ 【已弃用 - v4.0.0混合架构】
==========================================

此模块内置后端仅作为兼容性保留，将在v5.0.0中移除。

请使用统一后端API：
- 主后端入口: backend/main.py
- 字段映射API: backend/routers/field_mapping.py  
- 统一启动: python run.py

迁移说明：
1. 所有API已迁移到 backend/routers/field_mapping.py
2. 前端请调用统一后端 http://localhost:8000/api/field-mapping
3. 不要在此文件添加新功能

弃用时间: 2025-10-21
移除计划: v5.0.0 (预计2026-01)
==========================================
"""

from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from modules.services.data_query_service import get_data_query_service
from modules.services.catalog_scanner import scan_and_register
from modules.services.ingestion_worker import run_once
from modules.services.cache_service import get_cache_service
from modules.services.mapping_engine import get_mapping_engine, MappingResult
from modules.services.data_validator import get_data_validator, ValidationResult
from modules.core.secrets_manager import get_secrets_manager

app = FastAPI(
    title="Vue字段映射审核系统 API",
    description="现代化的字段映射审核API，解决Streamlit死循环问题",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic模型
class ScanRequest(BaseModel):
    directories: List[str] = ["temp/outputs"]
    max_files: int = 5000

class ScanResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None

class FileGroupsResponse(BaseModel):
    platforms: List[str]
    domains: Dict[str, List[str]]
    files: Dict[str, Dict[str, List[str]]]

class FieldMappingFilePreviewRequest(BaseModel):
    """字段映射应用的文件预览请求（使用file_path）"""
    file_path: str
    platform: str
    data_domain: str
    header_row: Optional[int] = 0

class FilePreviewResponse(BaseModel):
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    columns: Optional[List[str]] = None
    error: Optional[str] = None

class FieldMappingRequest(BaseModel):
    columns: List[str]
    data_domain: str

class FieldMappingResponse(BaseModel):
    mappings: Dict[str, str]
    confidence: Dict[str, float]
    foreign_keys: Dict[str, Dict[str, Any]] = {}

class DataValidationRequest(BaseModel):
    file_path: str
    platform: str
    data_domain: str
    mappings: Dict[str, str]

class DataValidationResponse(BaseModel):
    is_valid: bool
    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    statistics: Dict[str, Any] = {}
    recommendations: List[str] = []

class IngestRequest(BaseModel):
    file_path: str
    platform: str
    data_domain: str
    mappings: Optional[Dict[str, str]] = None

class IngestResponse(BaseModel):
    success: bool
    message: str
    stats: Optional[Dict[str, Any]] = None

# 依赖注入
def get_query_service():
    return get_data_query_service()

def get_cache():
    return get_cache_service()

# API路由
@app.get("/")
async def root():
    """根路径 - 健康检查"""
    return {
        "message": "Vue字段映射审核系统 API", 
        "status": "running",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    try:
        service = get_query_service()
        catalog_status = service.get_catalog_status()
        return {
            "status": "healthy",
            "database": "connected",
            "catalog_files": catalog_status.get('total', 0),
            "timestamp": asyncio.get_event_loop().time()
        }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "unhealthy", "error": str(e)}
        )

@app.post("/api/scan", response_model=ScanResponse)
async def scan_files(request: ScanRequest, background_tasks: BackgroundTasks):
    """扫描文件目录"""
    try:
        # 将字符串路径转换为Path对象
        path_objects = [Path(d) for d in request.directories]
        
        # 异步执行扫描
        result = scan_and_register(path_objects)
        
        return ScanResponse(
            success=True,
            message=f"扫描完成：发现{result.seen}个文件，新注册{result.registered}个",
            data={
                "seen": result.seen,
                "registered": result.registered,
                "skipped": result.skipped
            }
        )
    except Exception as e:
        return ScanResponse(
            success=False,
            message=f"扫描失败: {str(e)}"
        )

@app.get("/api/file-groups", response_model=FileGroupsResponse)
async def get_file_groups(service=Depends(get_query_service)):
    """获取文件分组信息"""
    try:
        from sqlalchemy import text
        
        engine = service._get_engine()
        with engine.connect() as conn:
            # 查询所有平台
            platforms_result = conn.execute(text("""
                SELECT DISTINCT platform_code 
                FROM catalog_files 
                WHERE platform_code IS NOT NULL 
                AND platform_code != ''
                AND platform_code != 'unknown'
                ORDER BY platform_code
            """))
            platforms = [row[0] for row in platforms_result]
            
            # 查询所有数据域
            domains_result = conn.execute(text("""
                SELECT DISTINCT data_domain 
                FROM catalog_files 
                WHERE data_domain IS NOT NULL 
                AND data_domain != ''
                AND data_domain != 'unknown'
                ORDER BY data_domain
            """))
            domains_list = [row[0] for row in domains_result]
            
            # 构建域字典（简化版本）
            domains = {}
            for domain in domains_list:
                domains[domain] = ["daily", "weekly", "monthly"]  # 简化处理
            
            # 查询文件分组
            files = {}
            for platform in platforms:
                files[platform] = {}
                for domain in domains_list:
                    files_result = conn.execute(text("""
                        SELECT file_name 
                        FROM catalog_files 
                        WHERE platform_code = :platform 
                        AND data_domain = :domain
                        ORDER BY file_name
                        LIMIT 10
                    """), {"platform": platform, "domain": domain})
                    
                    files[platform][domain] = [row[0] for row in files_result]
        
        return FileGroupsResponse(
            platforms=platforms,
            domains=domains,
            files=files
        )
    except Exception as e:
        # 如果数据库查询失败，返回错误信息
        print(f"File groups API error: {e}")
        raise HTTPException(status_code=500, detail=f"获取文件分组失败: {str(e)}")

@app.post("/api/file-preview", response_model=FilePreviewResponse)
async def preview_file(request: FieldMappingFilePreviewRequest):
    """预览文件内容"""
    print(f"DEBUG: 收到预览请求: {request.file_path}, {request.platform}, {request.data_domain}")
    try:
        import pandas as pd
        from pathlib import Path
        from sqlalchemy import text
        
        # 从数据库获取实际文件路径
        service = get_query_service()
        engine = service._get_engine()
        
        with engine.connect() as conn:
            # 根据文件名、平台和数据域查找文件路径
            result = conn.execute(text("""
                SELECT file_path 
                FROM catalog_files 
                WHERE file_name = :file_name 
                AND platform_code = :platform 
                AND data_domain = :domain
                LIMIT 1
            """), {
                "file_name": request.file_path,  # 这里request.file_path实际是文件名
                "platform": request.platform,
                "domain": request.data_domain
            })
            
            row = result.fetchone()
            if not row:
                return FilePreviewResponse(
                    success=False,
                    error=f"文件未在数据库中找到: {request.file_path}"
                )
            
            actual_file_path = Path(row[0])
            
            if not actual_file_path.exists():
                return FilePreviewResponse(
                    success=False,
                    error=f"文件不存在: {actual_file_path}"
                )
            
            # 使用改进的Excel读取逻辑，支持表头行设置
            df = None
            header_row = request.header_row if request.header_row is not None else 0
            print(f"DEBUG: 开始读取文件 {actual_file_path}，表头行: {header_row}")
            try:
                df = pd.read_excel(actual_file_path, nrows=100, header=header_row, engine='calamine')
                print(f"DEBUG: calamine引擎成功")
            except Exception as e:
                print(f"DEBUG: calamine引擎失败: {e}")
                try:
                    df = pd.read_excel(actual_file_path, nrows=100, header=header_row, engine='openpyxl')
                    print(f"DEBUG: openpyxl引擎成功")
                except Exception as e:
                    print(f"DEBUG: openpyxl引擎失败: {e}")
                    try:
                        df = pd.read_excel(actual_file_path, nrows=100, header=header_row, engine='xlrd')
                        print(f"DEBUG: xlrd引擎成功")
                    except Exception as e:
                        print(f"DEBUG: xlrd引擎失败: {e}")
                        return FilePreviewResponse(
                            success=False,
                            error="无法读取Excel文件，请检查文件格式"
                        )
            
            if df is None:
                return FilePreviewResponse(
                    success=False,
                    error="文件为空或无法读取"
                )
            
            # 调试信息
            print(f"DEBUG: df.empty = {df.empty}, len(df.columns) = {len(df.columns)}")
            
            # 即使没有数据行，如果有列名也认为是有效的
            if df.empty and len(df.columns) == 0:
                print("DEBUG: 文件确实为空，没有列名")
                return FilePreviewResponse(
                    success=False,
                    error="文件为空或无法读取"
                )
            
            print("DEBUG: 文件有列名，继续处理")
            
            # 临时修复：强制处理空数据文件
            if df.empty and len(df.columns) > 0:
                print("DEBUG: 文件有列名但无数据行，创建空数据")
                # 创建一个空的数据行，但保留列名
                data = []
                columns = df.columns.tolist()
                return FilePreviewResponse(
                    success=True,
                    data=data,
                    columns=columns
                )
            
            # 转换为字典格式
            data = df.to_dict('records')
            columns = df.columns.tolist()
            
            return FilePreviewResponse(
                success=True,
                data=data,
                columns=columns
            )
            
    except Exception as e:
        return FilePreviewResponse(
            success=False,
            error=f"预览文件失败: {str(e)}"
        )

@app.post("/api/field-mapping", response_model=FieldMappingResponse)
async def get_field_mapping(request: FieldMappingRequest):
    """获取智能字段映射建议"""
    try:
        # 获取智能映射引擎
        mapping_engine = get_mapping_engine()
        
        # 定义目标字段（根据数据域）
        target_fields_map = {
            "products": [
                "product_id", "product_name", "product_sku", "product_price",
                "shop_id", "platform_code", "currency", "quantity", "status"
            ],
            "orders": [
                "order_id", "order_amount", "order_date", "shop_id",
                "customer_id", "currency", "status", "payment_method"
            ],
            "traffic": [
                "date", "shop_id", "visits", "page_views", "bounce_rate",
                "avg_session_duration", "platform_code"
            ],
            "service": [
                "date", "shop_id", "service_type", "service_count", "resolution_time",
                "platform_code", "status"
            ]
        }
        
        target_fields = target_fields_map.get(request.data_domain, target_fields_map["products"])
        
        # 生成智能映射
        mapping_results = mapping_engine.generate_mappings(
            source_columns=request.columns,
            target_fields=target_fields,
            data_domain=request.data_domain
        )
        
        # 转换为API响应格式
        mappings = {}
        confidence = {}
        foreign_keys = {}
        
        for result in mapping_results:
            mappings[result.source_column] = result.target_field
            confidence[result.source_column] = result.confidence
            
            # 如果是外键，记录外键信息
            if result.mapping_type == 'foreign_key' and result.foreign_key_info:
                foreign_keys[result.source_column] = result.foreign_key_info
        
        return FieldMappingResponse(
            mappings=mappings,
            confidence=confidence,
            foreign_keys=foreign_keys
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"字段映射生成失败: {str(e)}")

@app.post("/api/validate-data", response_model=DataValidationResponse)
async def validate_data(request: DataValidationRequest):
    """验证数据质量"""
    try:
        import pandas as pd
        
        # 获取数据库引擎和验证器
        service = get_query_service()
        engine = service._get_engine()
        validator = get_data_validator(engine)
        
        # 从数据库获取实际文件路径
        from sqlalchemy import text
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT file_path 
                FROM catalog_files 
                WHERE file_name = :file_name 
                AND platform_code = :platform 
                AND data_domain = :domain
                LIMIT 1
            """), {
                "file_name": request.file_path,
                "platform": request.platform,
                "domain": request.data_domain
            })
            
            row = result.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="文件未找到")
            
            actual_file_path = Path(row[0])
            if not actual_file_path.exists():
                raise HTTPException(status_code=404, detail="文件不存在")
        
        # 读取数据（使用多引擎策略）
        df = None
        engines = ['calamine', 'openpyxl', 'xlrd']
        
        for engine in engines:
            try:
                df = pd.read_excel(actual_file_path, nrows=1000, engine=engine)
                break
            except Exception as e:
                print(f"Engine {engine} failed: {e}")
                continue
        
        if df is None:
            raise HTTPException(status_code=400, detail="无法使用任何引擎读取Excel文件")
        
        # 准备映射配置
        mapping_configs = []
        for source_col, target_field in request.mappings.items():
            if source_col in df.columns:
                mapping_configs.append({
                    'source_column': source_col,
                    'target_field': target_field
                })
        
        # 执行数据验证
        validation_result = validator.validate_dataframe(
            df=df,
            mappings=mapping_configs,
            data_domain=request.data_domain
        )
        
        # 转换错误和警告为字典格式
        errors = []
        for error in validation_result.errors:
            errors.append({
                'row_index': error.row_index,
                'column_name': error.column_name,
                'error_type': error.error_type,
                'error_message': error.error_message,
                'current_value': str(error.current_value) if error.current_value is not None else None,
                'expected_value': str(error.expected_value) if error.expected_value is not None else None,
                'suggestion': error.suggestion
            })
        
        warnings = []
        for warning in validation_result.warnings:
            warnings.append({
                'row_index': warning.row_index,
                'column_name': warning.column_name,
                'error_type': warning.error_type,
                'error_message': warning.error_message,
                'current_value': str(warning.current_value) if warning.current_value is not None else None,
                'expected_value': str(warning.expected_value) if warning.expected_value is not None else None,
                'suggestion': warning.suggestion
            })
        
        # 生成建议
        summary = validator.get_validation_summary(validation_result)
        
        return DataValidationResponse(
            is_valid=validation_result.is_valid,
            errors=errors,
            warnings=warnings,
            statistics=validation_result.statistics,
            recommendations=summary.get('recommendations', [])
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据验证失败: {str(e)}")

@app.post("/api/ingest", response_model=IngestResponse)
async def ingest_file(request: IngestRequest, background_tasks: BackgroundTasks):
    """数据入库"""
    try:
        # 这里应该调用实际的入库逻辑
        # 为了演示，我们返回成功响应
        
        background_tasks.add_task(
            process_ingestion,
            request.file_path,
            request.platform,
            request.data_domain,
            request.mappings
        )
        
        return IngestResponse(
            success=True,
            message="数据入库任务已启动",
            stats={
                "file_path": request.file_path,
                "platform": request.platform,
                "data_domain": request.data_domain
            }
        )
    except Exception as e:
        return IngestResponse(
            success=False,
            message=f"入库失败: {str(e)}"
        )

async def process_ingestion(file_path: str, platform: str, data_domain: str, mappings: Dict[str, str]):
    """后台处理入库任务"""
    try:
        # 这里实现实际的入库逻辑
        print(f"Processing ingestion: {file_path}")
        # 模拟处理时间
        await asyncio.sleep(1)
        print(f"Ingestion completed: {file_path}")
    except Exception as e:
        print(f"Ingestion failed: {e}")

@app.get("/api/catalog/status")
async def get_catalog_status(service=Depends(get_query_service)):
    """获取Catalog状态"""
    try:
        status = service.get_catalog_status()
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/catalog/cleanup")
async def cleanup_invalid_files(service=Depends(get_query_service)):
    """清理无效文件记录"""
    try:
        from sqlalchemy import text
        
        engine = service._get_engine()
        with engine.connect() as conn:
            # 查询所有文件记录
            result = conn.execute(text("SELECT file_path FROM catalog_files"))
            
            invalid_files = []
            for row in result:
                file_path = row[0]
                # 确保file_path是字符串，然后转换为Path对象
                if isinstance(file_path, str):
                    path_obj = Path(file_path)
                else:
                    path_obj = file_path
                
                if not path_obj.exists():
                    invalid_files.append(file_path)
            
            if not invalid_files:
                return {"message": "所有文件记录都是有效的", "cleaned": 0}
            
            # 删除无效记录
            deleted_count = 0
            for file_path in invalid_files:
                try:
                    conn.execute(text("DELETE FROM catalog_files WHERE file_path = :file_path"), 
                               {"file_path": file_path})
                    deleted_count += 1
                except Exception as e:
                    print(f"删除记录失败 {file_path}: {e}")
            
            conn.commit()
            
            return {
                "message": f"成功清理 {deleted_count} 个无效文件记录",
                "cleaned": deleted_count,
                "total_invalid": len(invalid_files)
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/file-path")
async def get_file_path(file_name: str, platform: str, domain: str, service=Depends(get_query_service)):
    """获取文件完整路径"""
    try:
        from sqlalchemy import text
        engine = service._get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT file_path 
                FROM catalog_files 
                WHERE file_name = :file_name 
                AND platform_code = :platform 
                AND data_domain = :domain
                LIMIT 1
            """), {
                "file_name": file_name,
                "platform": platform,
                "domain": domain
            })
            
            row = result.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="文件未找到")
            
            return {
                "success": True,
                "file_path": row[0]
            }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)