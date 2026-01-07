"""
系统性能测试和监控API路由

⚠️ v4.18.0: 修改prefix为/system/performance，避免与绩效管理API冲突
- 本路由: /system/performance - 系统性能监控（CPU/内存/API响应时间）
- 绩效管理: /performance - 员工绩效管理（销售目标/绩效评分）
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.models.database import get_db
from backend.services.performance_monitor import performance_monitor
from backend.routers.auth import get_current_user
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import DimUser  # v4.12.0 SSOT迁移
from modules.core.logger import get_logger
from typing import Dict, Any, List
import json
import time

logger = get_logger(__name__)
router = APIRouter(prefix="/system/performance", tags=["系统性能监控"])

async def require_admin(current_user: DimUser = Depends(get_current_user)):
    """要求管理员权限"""
    if not any(role.name == "admin" for role in current_user.roles):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions"
        )
    return current_user

@router.post("/monitor/start")
async def start_monitoring(
    interval: float = 1.0,
    current_user: DimUser = Depends(require_admin)
):
    """开始性能监控"""
    try:
        performance_monitor.start_monitoring(interval)
        return success_response(
            data={
                "interval": interval,
                "timestamp": time.time()
            },
            message="性能监控已启动"
        )
    except Exception as e:
        logger.error(f"启动监控失败: {e}")
        return error_response(
            code=ErrorCode.SYSTEM_ERROR,
            message="启动监控失败",
            error_type=get_error_type(ErrorCode.SYSTEM_ERROR),
            detail=str(e),
            status_code=500
        )

@router.post("/monitor/stop")
async def stop_monitoring(current_user: DimUser = Depends(require_admin)):
    """停止性能监控"""
    try:
        performance_monitor.stop_monitoring()
        return success_response(
            data={"timestamp": time.time()},
            message="性能监控已停止"
        )
    except Exception as e:
        logger.error(f"停止监控失败: {e}")
        return error_response(
            code=ErrorCode.SYSTEM_ERROR,
            message="停止监控失败",
            error_type=get_error_type(ErrorCode.SYSTEM_ERROR),
            detail=str(e),
            status_code=500
        )

@router.get("/monitor/status")
async def get_monitoring_status(current_user: DimUser = Depends(require_admin)):
    """获取监控状态"""
    return success_response(data={
        "is_monitoring": performance_monitor.is_monitoring,
        "start_time": performance_monitor.start_time.isoformat() if performance_monitor.start_time else None,
        "metrics_count": len(performance_monitor.metrics_history),
        "timestamp": time.time()
    })

@router.get("/metrics/current")
async def get_current_metrics(current_user: DimUser = Depends(require_admin)):
    """获取当前性能指标"""
    try:
        metrics = performance_monitor.get_current_metrics()
        return success_response(data={
            "timestamp": metrics.timestamp.isoformat(),
            "cpu_percent": metrics.cpu_percent,
            "memory_percent": metrics.memory_percent,
            "memory_used_mb": metrics.memory_used_mb,
            "memory_available_mb": metrics.memory_available_mb,
            "disk_usage_percent": metrics.disk_usage_percent,
            "network_sent_mb": metrics.network_sent_mb,
            "network_recv_mb": metrics.network_recv_mb,
            "active_connections": metrics.active_connections,
            "load_average": metrics.load_average
        })
    except Exception as e:
        logger.error(f"获取性能指标失败: {e}")
        return error_response(
            code=ErrorCode.SYSTEM_ERROR,
            message="获取性能指标失败",
            error_type=get_error_type(ErrorCode.SYSTEM_ERROR),
            detail=str(e),
            status_code=500
        )

@router.get("/metrics/summary")
async def get_metrics_summary(
    duration_minutes: int = 5,
    current_user: DimUser = Depends(require_admin)
):
    """获取性能指标摘要"""
    try:
        summary = performance_monitor.get_metrics_summary(duration_minutes)
        return success_response(data=summary)
    except Exception as e:
        logger.error(f"获取性能摘要失败: {e}")
        return error_response(
            code=ErrorCode.SYSTEM_ERROR,
            message="获取性能摘要失败",
            error_type=get_error_type(ErrorCode.SYSTEM_ERROR),
            detail=str(e),
            status_code=500
        )

@router.get("/metrics/history")
async def get_metrics_history(
    limit: int = 100,
    current_user: DimUser = Depends(require_admin)
):
    """获取历史性能指标"""
    try:
        history = performance_monitor.get_metrics_history(limit)
        return success_response(data={
            "count": len(history),
            "metrics": history
        })
    except Exception as e:
        logger.error(f"获取历史指标失败: {e}")
        return error_response(
            code=ErrorCode.SYSTEM_ERROR,
            message="获取历史指标失败",
            error_type=get_error_type(ErrorCode.SYSTEM_ERROR),
            detail=str(e),
            status_code=500
        )

@router.post("/metrics/export")
async def export_metrics(
    filepath: str = "temp/outputs/performance_metrics.json",
    current_user: DimUser = Depends(require_admin)
):
    """导出性能指标"""
    try:
        success = performance_monitor.export_metrics(filepath)
        if success:
            return success_response(
                data={
                    "filepath": filepath,
                    "timestamp": time.time()
                },
                message="性能指标导出成功"
            )
        else:
            return error_response(
                code=ErrorCode.FILE_OPERATION_ERROR,
                message="导出失败",
                error_type=get_error_type(ErrorCode.FILE_OPERATION_ERROR),
                status_code=500
            )
    except Exception as e:
        logger.error(f"导出性能指标失败: {e}")
        return error_response(
            code=ErrorCode.FILE_OPERATION_ERROR,
            message="导出性能指标失败",
            error_type=get_error_type(ErrorCode.FILE_OPERATION_ERROR),
            detail=str(e),
            status_code=500
        )

@router.post("/test/batch-import")
async def test_batch_import(
    data: Dict[str, Any],
    current_user: DimUser = Depends(require_admin)
):
    """测试批量导入性能"""
    try:
        batch_data = data.get("data", [])
        batch_id = data.get("batch_id", 1)
        
        # 模拟批量导入处理
        successful_count = 0
        failed_count = 0
        
        for record in batch_data:
            try:
                # 模拟数据处理
                if "id" in record or "order_id" in record or "sku" in record:
                    successful_count += 1
                else:
                    failed_count += 1
            except Exception:
                failed_count += 1
        
        return success_response(data={
            "batch_id": batch_id,
            "total_records": len(batch_data),
            "successful_count": successful_count,
            "failed_count": failed_count,
            "success_rate": (successful_count / len(batch_data) * 100) if batch_data else 0,
            "processing_time": time.time()
        })
    except Exception as e:
        logger.error(f"批量导入测试失败: {e}")
        return error_response(
            code=ErrorCode.SYSTEM_ERROR,
            message="批量导入测试失败",
            error_type=get_error_type(ErrorCode.SYSTEM_ERROR),
            detail=str(e),
            status_code=500
        )

@router.post("/test/single-import")
async def test_single_import(
    record: Dict[str, Any],
    current_user: DimUser = Depends(require_admin)
):
    """测试单个记录导入性能"""
    try:
        # 模拟单个记录处理
        success = "id" in record or "order_id" in record or "sku" in record
        
        return success_response(data={
            "success": success,
            "record_id": record.get("id", record.get("order_id", record.get("sku", "unknown"))),
            "processing_time": time.time()
        })
    except Exception as e:
        logger.error(f"单个导入测试失败: {e}")
        return error_response(
            code=ErrorCode.SYSTEM_ERROR,
            message="单个导入测试失败",
            error_type=get_error_type(ErrorCode.SYSTEM_ERROR),
            detail=str(e),
            status_code=500
        )

@router.get("/test/health")
async def test_health_check():
    """健康检查测试端点"""
    return success_response(
        data={
            "status": "healthy",
            "timestamp": time.time()
        },
        message="系统运行正常"
    )

@router.get("/test/load")
async def test_load_endpoint(
    iterations: int = 100,
    current_user: DimUser = Depends(require_admin)
):
    """负载测试端点"""
    try:
        start_time = time.time()
        results = []
        
        for i in range(iterations):
            # 模拟一些计算
            result = sum(range(1000))
            results.append(result)
        
        processing_time = time.time() - start_time
        
        return success_response(data={
            "iterations": iterations,
            "processing_time": processing_time,
            "iterations_per_second": iterations / processing_time if processing_time > 0 else 0,
            "average_time_per_iteration": processing_time / iterations if iterations > 0 else 0,
            "timestamp": time.time()
        })
    except Exception as e:
        logger.error(f"负载测试失败: {e}")
        return error_response(
            code=ErrorCode.SYSTEM_ERROR,
            message="负载测试失败",
            error_type=get_error_type(ErrorCode.SYSTEM_ERROR),
            detail=str(e),
            status_code=500
        )

@router.get("/system/info")
async def get_system_info(current_user: DimUser = Depends(require_admin)):
    """获取系统信息"""
    try:
        import platform
        import sys
        import psutil
        
        return success_response(data={
            "platform": platform.platform(),
            "python_version": sys.version,
            "cpu_count": psutil.cpu_count(),
            "memory_total_gb": psutil.virtual_memory().total / (1024**3),
            "disk_total_gb": psutil.disk_usage('/').total / (1024**3),
            "timestamp": time.time()
        })
    except Exception as e:
        logger.error(f"获取系统信息失败: {e}")
        return error_response(
            code=ErrorCode.SYSTEM_ERROR,
            message="获取系统信息失败",
            error_type=get_error_type(ErrorCode.SYSTEM_ERROR),
            detail=str(e),
            status_code=500
        )
