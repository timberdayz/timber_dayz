"""
测试API - 用于诊断系统问题
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.database import get_db, get_async_db, DataFile
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger
from pathlib import Path

logger = get_logger(__name__)
router = APIRouter()

@router.get("/test-db")
async def test_database(db: AsyncSession = Depends(get_async_db)):
    """测试数据库连接"""
    try:
        # 查询文件数量
        from sqlalchemy import func
        count_result = await db.execute(select(func.count(DataFile.id)))
        file_count = count_result.scalar() or 0
        
        # 查询前5个文件
        result = await db.execute(select(DataFile).limit(5))
        files = result.scalars().all()
        file_list = []
        for f in files:
            file_list.append({
                "id": f.id,
                "file_name": f.file_name,
                "file_path": f.file_path,
                "platform": f.platform,
                "status": f.status
            })
        
        return {
            "success": True,
            "message": "数据库连接正常",
            "data": {
                "total_files": file_count,
                "sample_files": file_list
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "数据库连接失败"
        }

@router.get("/test-files")
async def test_file_system():
    """测试文件系统"""
    try:
        # 检查temp/outputs目录
        temp_outputs = Path("temp/outputs")
        if not temp_outputs.exists():
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message="temp/outputs目录不存在",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                status_code=404
            )
        
        # 统计文件
        excel_files = list(temp_outputs.rglob("*.xlsx")) + list(temp_outputs.rglob("*.xls"))
        json_files = list(temp_outputs.rglob("*.json"))
        
        return success_response(
            data={
                "temp_outputs_exists": temp_outputs.exists(),
                "excel_files_count": len(excel_files),
                "json_files_count": len(json_files),
                "sample_excel_files": [str(f) for f in excel_files[:5]],
                "sample_json_files": [str(f) for f in json_files[:5]]
            },
            message="文件系统正常"
        )
    except Exception as e:
        logger.error(f"文件系统检查失败: {e}")
        return error_response(
            code=ErrorCode.FILE_OPERATION_ERROR,
            message="文件系统检查失败",
            error_type=get_error_type(ErrorCode.FILE_OPERATION_ERROR),
            detail=str(e),
            status_code=500
        )

@router.post("/test-cleanup")
async def test_cleanup(db: AsyncSession = Depends(get_async_db)):
    """测试清理功能"""
    try:
        # 获取所有文件记录
        result = await db.execute(select(DataFile))
        db_files = result.scalars().all()
        
        orphaned_count = 0
        valid_count = 0
        
        for db_record in db_files:
            try:
                if db_record.file_path and db_record.file_path.strip():
                    file_path = Path(db_record.file_path)
                    if file_path.exists():
                        valid_count += 1
                    else:
                        orphaned_count += 1
                else:
                    orphaned_count += 1
            except Exception as e:
                print(f"检查文件时出错: {e}")
                orphaned_count += 1
        
        return success_response(
            data={
                "total_files": len(db_files),
                "valid_files": valid_count,
                "orphaned_files": orphaned_count
            },
            message="清理测试完成"
        )
    except Exception as e:
        logger.error(f"清理测试失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="清理测试失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )
