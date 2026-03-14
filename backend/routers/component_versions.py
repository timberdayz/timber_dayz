"""
组件版本管理API路由 (Phase 9.4)

提供组件版本的CRUD、A/B测试、提升/回滚等功能
"""

from typing import List, Optional, Any
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import not_, or_, select
from pydantic import BaseModel, Field
import uuid
import sys

from backend.models.database import get_db, get_async_db, SessionLocal
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode
from backend.services.component_version_service import ComponentVersionService
from modules.core.db import ComponentVersion, ComponentTestHistory
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/component-versions", tags=["组件版本管理"])


def save_test_history_sync(
    db: Session,
    component_name: str,
    platform: str,
    account_id: str,
    test_result: Any,
    version_id: Optional[int] = None,
    component_version: Optional[str] = None,
) -> None:
    """同步保存测试历史（供子进程回调线程使用，避免跨事件循环使用 AsyncSession）。"""
    import uuid
    try:
        success_rate = (test_result.steps_passed / test_result.steps_total) if test_result.steps_total > 0 else 0.0
        step_results_json = [
            {"step_id": s.step_id, "action": s.action, "status": s.status.value, "duration_ms": s.duration_ms, "error": s.error}
            for s in test_result.step_results
        ]
        history = ComponentTestHistory(
            test_id=str(uuid.uuid4()),
            component_name=component_name,
            component_version=component_version,
            version_id=version_id,
            platform=platform,
            account_id=account_id,
            headless=False,
            status=test_result.status.value,
            duration_ms=test_result.duration_ms,
            steps_total=test_result.steps_total,
            steps_passed=test_result.steps_passed,
            steps_failed=test_result.steps_failed,
            success_rate=success_rate,
            step_results=step_results_json,
            error_message=test_result.error,
            tested_by="version_manager",
        )
        db.add(history)
        db.commit()
        logger.info(f"Test history saved (sync): {history.test_id}")
    except Exception as e:
        logger.warning(f"Failed to save test history (sync): {e}")
        db.rollback()


async def save_test_history(
    db: AsyncSession,
    component_name: str,
    platform: str,
    account_id: str,
    test_result: Any,
    version_id: Optional[int] = None,
    component_version: Optional[str] = None
) -> None:
    """保存测试历史记录到数据库"""
    import uuid
    from typing import Any
    try:
        # 计算成功率
        success_rate = (test_result.steps_passed / test_result.steps_total) if test_result.steps_total > 0 else 0.0
        
        # 格式化步骤结果为JSON
        step_results_json = [
            {
                'step_id': s.step_id,
                'action': s.action,
                'status': s.status.value,
                'duration_ms': s.duration_ms,
                'error': s.error
            }
            for s in test_result.step_results
        ]
        
        # 创建历史记录
        history = ComponentTestHistory(
            test_id=str(uuid.uuid4()),
            component_name=component_name,
            component_version=component_version,
            version_id=version_id,
            platform=platform,
            account_id=account_id,
            headless=False,  # 前端测试默认有头模式
            status=test_result.status.value,
            duration_ms=test_result.duration_ms,
            steps_total=test_result.steps_total,
            steps_passed=test_result.steps_passed,
            steps_failed=test_result.steps_failed,
            success_rate=success_rate,
            step_results=step_results_json,
            error_message=test_result.error,
            tested_by="version_manager"  # 来自版本管理页
        )
        
        db.add(history)
        await db.commit()
        logger.info(f"Test history saved: {history.test_id}")
        
    except Exception as e:
        logger.warning(f"Failed to save test history: {e}")
        await db.rollback()


# ==================== Pydantic Models ====================

class ComponentVersionResponse(BaseModel):
    """组件版本响应模型"""
    id: int
    component_name: str
    version: str
    file_path: str
    is_stable: bool
    is_active: bool
    is_testing: bool
    usage_count: int
    success_count: int
    failure_count: int
    success_rate: float
    test_ratio: float
    test_start_at: Optional[str] = None
    test_end_at: Optional[str] = None
    description: Optional[str] = None
    created_by: Optional[str] = None
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class VersionListResponse(BaseModel):
    """版本列表响应"""
    data: List[ComponentVersionResponse]
    total: int
    page: int
    page_size: int


class VersionRegisterRequest(BaseModel):
    """注册版本请求"""
    component_name: str = Field(..., description="组件名称(如shopee/login)")
    version: str = Field(..., description="版本号(如1.0.0)")
    file_path: str = Field(..., description="文件路径")
    description: Optional[str] = Field(None, description="版本说明")
    is_stable: bool = Field(False, description="是否标记为稳定版本")
    created_by: Optional[str] = Field(None, description="创建人")


class ABTestRequest(BaseModel):
    """启动A/B测试请求"""
    test_ratio: float = Field(..., ge=0.05, le=0.5, description="测试流量比例(0.05-0.5)")
    duration_days: int = Field(..., ge=1, le=30, description="测试持续天数(1-30)")


class VersionUpdateRequest(BaseModel):
    """更新版本请求"""
    is_active: Optional[bool] = Field(None, description="是否启用")
    description: Optional[str] = Field(None, description="版本说明")


class BatchRegisterRequest(BaseModel):
    """批量注册请求"""
    platform: Optional[str] = Field(None, description="指定平台(可选)")


class BatchRegisterResult(BaseModel):
    """批量注册结果"""
    component_name: str
    file_path: str
    version: str
    status: str  # registered, updated, skipped, error
    error: Optional[str] = None


class BatchRegisterResponse(BaseModel):
    """批量注册响应"""
    success: bool
    registered_count: int
    skipped_count: int
    error_count: int
    details: List[BatchRegisterResult]


# ==================== API Endpoints ====================

@router.get("", response_model=VersionListResponse)
async def list_versions(
    platform: Optional[str] = Query(None, description="平台筛选"),
    component_type: Optional[str] = Query(None, description="组件类型筛选"),
    status: Optional[str] = Query(None, description="状态筛选: stable/testing/inactive"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
    request: Request = None  # [*] Phase 3: 用于获取缓存服务
):
    """
    查询组件版本列表
    
    支持按平台、组件类型、状态筛选,分页查询
    [*] Phase 3: 添加缓存支持(5分钟TTL)
    """
    # [*] Phase 3: 尝试从缓存获取
    if request and hasattr(request.app.state, 'cache_service'):
        cache_service = request.app.state.cache_service
        cached_data = await cache_service.get(
            "component_versions",
            platform=platform,
            component_type=component_type,
            status=status,
            page=page,
            page_size=page_size
        )
        if cached_data is not None:
            logger.debug(f"[Cache] 组件版本列表缓存命中: platform={platform}, page={page}")
            return VersionListResponse(**cached_data)
    
    try:
        from sqlalchemy import func
        service = ComponentVersionService(db)
        
        # 构建查询条件
        conditions = []
        
        # 平台筛选
        if platform:
            conditions.append(ComponentVersion.component_name.like(f"{platform}/%"))
        
        # 组件类型筛选
        if component_type:
            conditions.append(ComponentVersion.component_name.like(f"%/{component_type}%"))
        
        # 状态筛选
        if status == "stable":
            conditions.append(ComponentVersion.is_stable == True)
        elif status == "testing":
            conditions.append(ComponentVersion.is_testing == True)
        elif status == "inactive":
            conditions.append(ComponentVersion.is_active == False)
        
        # v4.8.0: 排除非组件文件(config 文件、工具文件等)
        conditions.extend([
            not_(ComponentVersion.file_path.like('%_config.py')),
            not_(ComponentVersion.file_path.like('%overlay_guard.py')),
            not_(ComponentVersion.component_name.like('%_config')),
            not_(ComponentVersion.component_name.like('%overlay_guard'))
        ])
        
        # 总数
        count_stmt = select(func.count(ComponentVersion.id)).where(*conditions)
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # 分页
        offset = (page - 1) * page_size
        stmt = select(ComponentVersion).where(*conditions).order_by(
            ComponentVersion.success_rate.desc(),
            ComponentVersion.created_at.desc()
        ).offset(offset).limit(page_size)
        result = await db.execute(stmt)
        versions = result.scalars().all()
        
        # 格式化响应
        data = [
            ComponentVersionResponse(
                id=v.id,
                component_name=v.component_name,
                version=v.version,
                file_path=v.file_path,
                is_stable=v.is_stable,
                is_active=v.is_active,
                is_testing=v.is_testing,
                usage_count=v.usage_count,
                success_count=v.success_count,
                failure_count=v.failure_count,
                success_rate=v.success_rate,
                test_ratio=v.test_ratio,
                test_start_at=v.test_start_at.isoformat() if v.test_start_at else None,
                test_end_at=v.test_end_at.isoformat() if v.test_end_at else None,
                description=v.description,
                created_by=v.created_by,
                created_at=v.created_at.isoformat(),
                updated_at=v.updated_at.isoformat()
            )
            for v in versions
        ]
        
        result = VersionListResponse(
            data=data,
            total=total,
            page=page,
            page_size=page_size
        )
        
        # [*] Phase 3: 写入缓存
        if request and hasattr(request.app.state, 'cache_service'):
            cache_service = request.app.state.cache_service
            await cache_service.set(
                "component_versions",
                result.dict(),
                ttl=300,  # 5分钟TTL
                platform=platform,
                component_type=component_type,
                status=status,
                page=page,
                page_size=page_size
            )
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to list versions: {e}")
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            str(e),
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.get("/{version_id}", response_model=ComponentVersionResponse)
async def get_version(
    version_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """获取版本详情"""
    try:
        result = await db.execute(select(ComponentVersion).where(ComponentVersion.id == version_id))
        version = result.scalar_one_or_none()
        
        if not version:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                "Version not found",
                status_code=404,
                recovery_suggestion="请检查版本ID",
            )

        return ComponentVersionResponse(
            id=version.id,
            component_name=version.component_name,
            version=version.version,
            file_path=version.file_path,
            is_stable=version.is_stable,
            is_active=version.is_active,
            is_testing=version.is_testing,
            usage_count=version.usage_count,
            success_count=version.success_count,
            failure_count=version.failure_count,
            success_rate=version.success_rate,
            test_ratio=version.test_ratio,
            test_start_at=version.test_start_at.isoformat() if version.test_start_at else None,
            test_end_at=version.test_end_at.isoformat() if version.test_end_at else None,
            description=version.description,
            created_by=version.created_by,
            created_at=version.created_at.isoformat(),
            updated_at=version.updated_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Failed to get version {version_id}: {e}")
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            str(e),
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.post("", response_model=ComponentVersionResponse)
async def register_version(
    request: VersionRegisterRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """注册新版本"""
    try:
        service = ComponentVersionService(db)
        
        version = service.register_version(
            component_name=request.component_name,
            version=request.version,
            file_path=request.file_path,
            description=request.description,
            is_stable=request.is_stable,
            created_by=request.created_by
        )
        
        return ComponentVersionResponse(
            id=version.id,
            component_name=version.component_name,
            version=version.version,
            file_path=version.file_path,
            is_stable=version.is_stable,
            is_active=version.is_active,
            is_testing=version.is_testing,
            usage_count=version.usage_count,
            success_count=version.success_count,
            failure_count=version.failure_count,
            success_rate=version.success_rate,
            test_ratio=version.test_ratio,
            test_start_at=version.test_start_at.isoformat() if version.test_start_at else None,
            test_end_at=version.test_end_at.isoformat() if version.test_end_at else None,
            description=version.description,
            created_by=version.created_by,
            created_at=version.created_at.isoformat(),
            updated_at=version.updated_at.isoformat()
        )
        
    except Exception as e:
        logger.error(f"Failed to register version: {e}")
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            str(e),
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.post("/{version_id}/ab-test")
async def start_ab_test(
    version_id: int,
    request: ABTestRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """启动A/B测试"""
    try:
        service = ComponentVersionService(db)
        
        # 获取版本
        result = await db.execute(select(ComponentVersion).where(ComponentVersion.id == version_id))
        version = result.scalar_one_or_none()
        if not version:
            return error_response(ErrorCode.DATA_NOT_FOUND, "Version not found", status_code=404, recovery_suggestion="请检查版本ID")
        
        # 启动A/B测试
        updated_version = service.start_ab_test(
            component_name=version.component_name,
            test_version=version.version,
            test_ratio=request.test_ratio,
            duration_days=request.duration_days
        )
        
        logger.info(
            f"A/B test started: {version.component_name} v{version.version}, "
            f"ratio={request.test_ratio:.2%}, duration={request.duration_days}days"
        )
        
        return {
            "success": True,
            "message": "A/B测试已启动",
            "test_ratio": request.test_ratio,
            "duration_days": request.duration_days,
            "test_start_at": updated_version.test_start_at.isoformat(),
            "test_end_at": updated_version.test_end_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to start A/B test for version {version_id}: {e}")
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, str(e), status_code=500, detail=str(e), recovery_suggestion="请稍后重试")


@router.post("/{version_id}/stop-ab-test")
async def stop_ab_test(
    version_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """停止A/B测试"""
    try:
        # 获取版本
        result = await db.execute(select(ComponentVersion).where(ComponentVersion.id == version_id))
        version = result.scalar_one_or_none()
        if not version:
            return error_response(ErrorCode.DATA_NOT_FOUND, "Version not found", status_code=404, recovery_suggestion="请检查版本ID")
        
        if not version.is_testing:
            return error_response(ErrorCode.DATA_VALIDATION_FAILED, "Version is not in A/B testing", status_code=400, recovery_suggestion="请先加入A/B测试")
        
        # 停止测试
        version.is_testing = False
        version.test_ratio = 0
        await db.commit()
        
        logger.info(f"A/B test stopped: {version.component_name} v{version.version}")
        
        return {
            "success": True,
            "message": "A/B测试已停止"
        }
        
    except Exception as e:
        logger.error(f"Failed to stop A/B test for version {version_id}: {e}")
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, str(e), status_code=500, detail=str(e), recovery_suggestion="请稍后重试")


@router.post("/{version_id}/promote")
async def promote_to_stable(
    version_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """提升为稳定版本"""
    try:
        service = ComponentVersionService(db)
        
        # 获取版本
        result = await db.execute(select(ComponentVersion).where(ComponentVersion.id == version_id))
        version = result.scalar_one_or_none()
        if not version:
            return error_response(ErrorCode.DATA_NOT_FOUND, "Version not found", status_code=404, recovery_suggestion="请检查版本ID")
        
        # 提升为稳定版本
        updated_version = service.promote_to_stable(
            component_name=version.component_name,
            version=version.version
        )
        
        logger.info(f"Version promoted to stable: {version.component_name} v{version.version}")
        
        return {
            "success": True,
            "message": "已提升为稳定版本"
        }
        
    except Exception as e:
        logger.error(f"Failed to promote version {version_id}: {e}")
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, str(e), status_code=500, detail=str(e), recovery_suggestion="请稍后重试")


@router.patch("/{version_id}")
async def update_version(
    version_id: int,
    request: VersionUpdateRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """更新版本"""
    try:
        # 获取版本
        result = await db.execute(select(ComponentVersion).where(ComponentVersion.id == version_id))
        version = result.scalar_one_or_none()
        if not version:
            return error_response(ErrorCode.DATA_NOT_FOUND, "Version not found", status_code=404, recovery_suggestion="请检查版本ID")
        
        # 更新字段
        if request.is_active is not None:
            version.is_active = request.is_active
        if request.description is not None:
            version.description = request.description
        
        await db.commit()
        
        logger.info(f"Version updated: {version.component_name} v{version.version}")
        
        return {
            "success": True,
            "message": "版本已更新"
        }
        
    except Exception as e:
        logger.error(f"Failed to update version {version_id}: {e}")
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, str(e), status_code=500, detail=str(e), recovery_suggestion="请稍后重试")


@router.delete("/{version_id}")
async def delete_version(
    version_id: int,
    request: Request = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    删除组件版本。可删除条件: !is_testing && !is_active (非测试中且已禁用)。
    稳定版在禁用后也可删除。
    """
    from pathlib import Path

    try:
        result = await db.execute(select(ComponentVersion).where(ComponentVersion.id == version_id))
        version = result.scalar_one_or_none()

        if not version:
            return error_response(ErrorCode.DATA_NOT_FOUND, "版本不存在", status_code=404, recovery_suggestion="请检查版本ID")

        if version.is_testing:
            return error_response(ErrorCode.DATA_VALIDATION_FAILED, "无法删除正在测试的版本,请先停止A/B测试", status_code=400, recovery_suggestion="请先停止A/B测试")
        if version.is_active:
            return error_response(ErrorCode.DATA_VALIDATION_FAILED, "无法删除启用中的版本,请先禁用", status_code=400, recovery_suggestion="请先禁用版本")

        # 记录删除信息
        component_name = version.component_name
        version_str = version.version
        file_path = version.file_path

        # 删除前检查：是否还有其他版本引用同一 file_path
        other_result = await db.execute(
            select(ComponentVersion).where(
                ComponentVersion.file_path == file_path,
                ComponentVersion.id != version_id
            )
        )
        other_versions = other_result.scalars().all()
        should_delete_file = len(other_versions) == 0 and file_path and file_path.endswith(".py")

        # 删除记录
        await db.delete(version)
        await db.commit()

        # 若无其他版本引用，删除磁盘上的 .py 文件
        file_deleted = False
        if should_delete_file:
            try:
                project_root = Path(__file__).parent.parent.parent
                full_path = project_root / file_path
                if full_path.exists() and full_path.is_file():
                    full_path.unlink()
                    file_deleted = True
                    logger.info(f"Deleted file: {full_path}")
            except Exception as e:
                logger.warning(f"Failed to delete file {file_path}: {e}")

        logger.info(f"Deleted version: {component_name} v{version_str} (file: {file_path}, file_deleted={file_deleted})")

        # 失效组件版本列表缓存，避免列表显示已删除的版本
        if request and hasattr(request.app.state, "cache_service"):
            try:
                cache_service = request.app.state.cache_service
                await cache_service.invalidate("component_versions")
                logger.debug("[Cache] component_versions invalidated after delete")
            except Exception as ce:
                logger.warning(f"[Cache] Failed to invalidate component_versions: {ce}")

        return {
            "success": True,
            "message": f"已删除版本 {component_name} v{version_str}",
            "deleted_version": {
                "id": version_id,
                "component_name": component_name,
                "version": version_str,
                "file_path": file_path
            }
        }
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete version {version_id}: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"删除版本失败: {str(e)}", status_code=500, detail=str(e), recovery_suggestion="请稍后重试")


@router.get("/{component_name}/statistics")
async def get_component_statistics(
    component_name: str,
    db: AsyncSession = Depends(get_async_db)
):
    """获取组件所有版本的统计信息"""
    try:
        service = ComponentVersionService(db)
        stats = service.get_version_statistics(component_name)
        
        return {
            "success": True,
            "component_name": component_name,
            "versions": stats
        }
        
    except Exception as e:
        logger.error(f"Failed to get statistics for {component_name}: {e}")
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, str(e), status_code=500, detail=str(e), recovery_suggestion="请稍后重试")


@router.post("/batch-register-python", response_model=BatchRegisterResponse)
async def batch_register_python_components(
    request: BatchRegisterRequest = None,
    db: AsyncSession = Depends(get_async_db)
):
    """
    批量注册 Python 组件(v4.8.0 新增)
    
    扫描 modules/platforms/ 下所有 Python 组件,注册到 ComponentVersion 表。
    已存在的组件会跳过(基于 component_name + file_path)。
    
    Args:
        platform: 可选,指定平台(shopee, tiktok, miaoshou)
    
    Returns:
        BatchRegisterResponse: 注册统计和详细信息
    """
    import importlib.util
    from pathlib import Path
    from datetime import datetime
    from backend.services.component_name_utils import (
        parse_filename_to_component_and_version,
        is_standard_component_name,
    )

    SUPPORTED_PLATFORMS = ["shopee", "tiktok", "miaoshou"]
    project_root = Path(__file__).parent.parent.parent
    platforms_dir = project_root / "modules" / "platforms"
    
    results: List[BatchRegisterResult] = []
    registered_count = 0
    skipped_count = 0
    error_count = 0
    
    try:
        # 确定要扫描的平台
        if request and request.platform:
            target_platforms = [request.platform]
        else:
            target_platforms = SUPPORTED_PLATFORMS
        
        for platform in target_platforms:
            platform_dir = platforms_dir / platform / "components"
            
            if not platform_dir.exists():
                logger.warning(f"Platform components directory not found: {platform_dir}")
                continue
            
            for py_file in platform_dir.glob("*.py"):
                # 跳过 __init__.py
                if py_file.name.startswith("__"):
                    continue
                
                comp_name, default_version = parse_filename_to_component_and_version(
                    py_file.name, platform
                )
                if not comp_name:
                    continue
                component_name = comp_name
                relative_path = str(py_file.relative_to(project_root)).replace("\\", "/")
                if not is_standard_component_name(component_name):
                    logger.warning(f"Non-standard component_name (will register): {component_name}")
                
                try:
                    # 先提取组件类型(用于后续更新描述)
                    component_type = "unknown"
                    try:
                        spec = importlib.util.spec_from_file_location("component", py_file)
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        
                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if isinstance(attr, type) and hasattr(attr, "component_type"):
                                component_type = getattr(attr, "component_type", "unknown")
                                break
                    except Exception:
                        # 从文件名推断
                        if "login" in py_file.stem:
                            component_type = "login"
                        elif "navigation" in py_file.stem:
                            component_type = "navigation"
                        elif "export" in py_file.stem:
                            component_type = "export"
                        elif "date_picker" in py_file.stem:
                            component_type = "date_picker"
                        elif "shop_selector" in py_file.stem or "shop_switch" in py_file.stem:
                            component_type = "shop_selector"
                        elif "overlay_guard" in py_file.stem:
                            component_type = "overlay_guard"
                        elif "metrics_selector" in py_file.stem:
                            component_type = "metrics_selector"
                        elif "analytics" in py_file.stem:
                            component_type = "analytics"
                        else:
                            component_type = "other"
                    
                    # 检查是否已存在(基于 component_name + version,这是唯一约束)
                    existing_result = await db.execute(select(ComponentVersion).where(
                        ComponentVersion.component_name == component_name,
                        ComponentVersion.version == default_version
                    ))
                    existing = existing_result.scalar_one_or_none()
                    
                    if existing:
                        # 如果 file_path 相同,跳过
                        if existing.file_path == relative_path:
                            results.append(BatchRegisterResult(
                                component_name=component_name,
                                file_path=relative_path,
                                version=existing.version,
                                status="skipped",
                                error=None
                            ))
                            skipped_count += 1
                            continue
                        else:
                            # file_path 不同,更新 file_path(从YAML迁移到Python的情况)
                            existing.file_path = relative_path
                            existing.updated_at = datetime.utcnow()
                            # 如果描述还是旧的,更新描述
                            if "YAML" in existing.description or "DEPRECATED" in existing.description:
                                existing.description = f"Python component: {component_type}"
                            
                            results.append(BatchRegisterResult(
                                component_name=component_name,
                                file_path=relative_path,
                                version=existing.version,
                                status="updated",
                                error=None
                            ))
                            registered_count += 1  # 计入更新
                            logger.info(f"Updated Python component file_path: {component_name} -> {relative_path}")
                            continue
                    
                    # 注册新版本，默认非稳定（与录制保存一致）
                    new_version = ComponentVersion(
                        component_name=component_name,
                        version=default_version,
                        file_path=relative_path,
                        description=f"Python component: {component_type}",
                        is_stable=False,
                        is_active=True,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.add(new_version)  # AsyncSession.add is sync
                    
                    results.append(BatchRegisterResult(
                        component_name=component_name,
                        file_path=relative_path,
                        version=default_version,
                        status="registered",
                        error=None
                    ))
                    registered_count += 1
                    logger.info(f"Registered Python component: {component_name}")
                    
                except Exception as e:
                    results.append(BatchRegisterResult(
                        component_name=component_name,
                        file_path=relative_path,
                        version="",
                        status="error",
                        error=str(e)
                    ))
                    error_count += 1
                    logger.error(f"Failed to register {component_name}: {e}")
        
        await db.commit()
        
        logger.info(
            f"Batch registration completed: {registered_count} registered, "
            f"{skipped_count} skipped, {error_count} errors"
        )
        
        return BatchRegisterResponse(
            success=error_count == 0,
            registered_count=registered_count,
            skipped_count=skipped_count,
            error_count=error_count,
            details=results
        )
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Batch registration failed: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, str(e), status_code=500, detail=str(e), recovery_suggestion="请稍后重试")


class ComponentTestRequest(BaseModel):
    """测试组件请求"""
    account_id: str = Field(..., description="测试账号ID")


class TestHistoryResponse(BaseModel):
    """测试历史响应模型"""
    test_id: str
    component_name: str
    component_version: Optional[str] = None
    platform: str
    account_id: str
    status: str
    duration_ms: int
    steps_total: int
    steps_passed: int
    steps_failed: int
    success_rate: float
    tested_at: str
    tested_by: Optional[str] = None
    
    class Config:
        from_attributes = True


class TestHistoryListResponse(BaseModel):
    """测试历史列表响应"""
    total: int
    items: List[TestHistoryResponse]


@router.post("/{version_id}/test")
async def test_component_version(
    version_id: int,
    request: ComponentTestRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    测试组件版本 - v4.7.4: HTTP 轮询进度
    
    从版本管理页调用,测试已注册的组件版本
    进度通过 GET /component-versions/{version_id}/test/{test_id}/status 接口查询
    
    重构说明:移除 WebSocket,统一使用 HTTP 轮询
    """
    import yaml
    import asyncio
    from pathlib import Path
    from datetime import datetime
    from backend.services.component_test_service import ComponentTestService
    from tools.test_component import TestStatus, ComponentTester, ComponentTestResult
    
    # #region agent log
    import json
    from pathlib import Path as LogPath
    from modules.core.path_manager import get_project_root
    log_file = get_project_root() / ".cursor" / "debug.log"
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps({"location":"component_versions.py:522","message":"test_component_version called","data":{"version_id":version_id,"account_id":request.account_id},"timestamp":__import__('datetime').datetime.now().isoformat(),"sessionId":"debug-session","hypothesisId":"H1"})+"\n")
    # #endregion
    
    try:
        # 1. 获取版本信息
        result = await db.execute(select(ComponentVersion).where(
            ComponentVersion.id == version_id
        ))
        version = result.scalar_one_or_none()
        
        if not version:
            return error_response(ErrorCode.DATA_NOT_FOUND, "版本不存在", status_code=404, recovery_suggestion="请检查版本ID")
        
        if not version.is_active:
            return error_response(ErrorCode.DATA_VALIDATION_FAILED, "该版本已禁用,无法测试", status_code=400, recovery_suggestion="请先启用版本")
        
        # 2. 验证账号
        from modules.core.db import PlatformAccount
        account_result = await db.execute(select(PlatformAccount).where(
            PlatformAccount.account_id == request.account_id
        ))
        account = account_result.scalar_one_or_none()
        
        if not account:
            return error_response(ErrorCode.DATA_NOT_FOUND, "账号不存在", status_code=404, recovery_suggestion="请检查账号ID")
        
        # #region agent log
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps({"location":"component_versions.py:548","message":"Account found","data":{"account_id":account.account_id,"platform":account.platform},"timestamp":__import__('datetime').datetime.now().isoformat(),"sessionId":"debug-session","hypothesisId":"H3"})+"\n")
        # #endregion
        
        logger.info(
            f"Testing component version: {version.component_name} v{version.version} "
            f"with account: {request.account_id}"
        )
        
        # 3. 读取组件文件(支持 YAML 和 Python 组件)
        project_root = Path(__file__).parent.parent.parent
        component_path = project_root / version.file_path
        
        if not component_path.exists():
            return error_response(ErrorCode.FILE_NOT_FOUND, f"组件文件不存在: {version.file_path}", status_code=404, recovery_suggestion="请检查组件路径或重新上传")
        
        # v4.8.0: 判断是 Python 组件还是 YAML 组件
        is_python_component = version.file_path.endswith('.py')
        
        if is_python_component:
            # Python 组件:从文件路径提取平台和组件名
            # 例如: modules/platforms/shopee/components/login.py
            path_parts = version.file_path.replace('\\', '/').split('/')
            if 'platforms' in path_parts:
                platform_idx = path_parts.index('platforms') + 1
                if platform_idx < len(path_parts):
                    platform = path_parts[platform_idx]
                else:
                    platform = version.component_name.split('/')[0]
            component_config = {}  # Python 组件不需要 YAML 配置
        else:
            # YAML 组件
            with open(component_path, 'r', encoding='utf-8') as f:
                component_config = yaml.safe_load(f)
            platform = component_config.get('platform', version.component_name.split('/')[0])
        # 使用逻辑组件名（如 login、orders_export），供 component_loader 按类名约定查找；不用 file_path.stem（如 login_v1_0_0）否则找不到类
        component_name = (
            version.component_name.split("/")[-1]
            if "/" in version.component_name
            else component_path.stem
        )
        
        # 4. 使用统一服务准备账号信息 [*]
        account_info = ComponentTestService.prepare_account_info(account)
        
        # #region agent log
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps({"location":"component_versions.py:573","message":"Account info prepared","data":{"has_username":bool(account_info.get('username')),"has_password":bool(account_info.get('password')),"platform":account_info.get('platform')},"timestamp":__import__('datetime').datetime.now().isoformat(),"sessionId":"debug-session","hypothesisId":"H3"})+"\n")
        # #endregion
        
        # 5. 生成测试ID(用于 HTTP 轮询状态查询)
        test_id = f"test_{uuid.uuid4().hex[:12]}"
        logger.info(f"Starting test with ID: {test_id}")
        
        # #region agent log
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps({"location":"component_versions.py:600","message":"Starting background test","data":{"test_id":test_id,"platform":platform,"component_name":component_name},"timestamp":__import__('datetime').datetime.now().isoformat(),"sessionId":"debug-session","hypothesisId":"H2"})+"\n")
        # #endregion
        
        # 6. 使用独立进程运行测试(subprocess 方案)
        # [*] v4.7.4: 移除 WebSocket,使用 HTTP 轮询获取进度
        # 进度和结果保存在 temp/ 目录下,通过状态查询接口获取
        
        # 创建进度/结果目录
        import tempfile
        import os
        test_dir = project_root / 'temp' / 'component_tests' / test_id
        test_dir.mkdir(parents=True, exist_ok=True)
        
        config_path = test_dir / 'config.json'
        result_path = test_dir / 'result.json'
        progress_path = test_dir / 'progress.json'
        
        # 写入配置文件
        import json as json_lib
        test_config = {
            'platform': platform,
            'account_id': request.account_id,
            'component_name': component_name,
            'component_path': str(component_path),
            'headless': False,
            'screenshot_on_error': True,
            'account_info': account_info,
            'version_id': version_id,  # 用于更新统计
            'test_dir': str(test_dir),  # 验证码回传：子进程轮询 verification_response.json 的目录
        }
        with open(config_path, 'w', encoding='utf-8') as f:
            json_lib.dump(test_config, f, ensure_ascii=False)
        
        # 写入初始进度
        initial_progress = {
            'status': 'running',
            'progress': 0,
            'current_step': 'Starting test...',
            'step_index': 0,
            'step_total': 0,
            'message': 'Starting test...'
        }
        with open(progress_path, 'w', encoding='utf-8') as f:
            json_lib.dump(initial_progress, f, ensure_ascii=False)
        
        def run_test_in_subprocess():
            """在独立进程中运行测试"""
            import subprocess
            import time
            
            try:
                # 启动 subprocess
                script_path = project_root / 'tools' / 'run_component_test.py'
                logger.info(f"Starting subprocess test: {script_path}")
                
                proc = subprocess.Popen(
                    [sys.executable, str(script_path), str(config_path), str(result_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    errors='replace'
                )
                
                # 等待子进程完成(子进程会写入进度文件)
                stdout, stderr = proc.communicate()
                
                if proc.returncode != 0:
                    logger.error(f"Subprocess exited with code {proc.returncode}")
                    logger.error(f"STDERR: {stderr[:1000] if stderr else 'none'}")
                    
                    # 写入失败状态
                    with open(progress_path, 'w', encoding='utf-8') as f:
                        json_lib.dump({
                            'status': 'failed',
                            'progress': 100,
                            'current_step': 'Test failed',
                            'error': stderr[:500] if stderr else 'Unknown error'
                        }, f, ensure_ascii=False)
                else:
                    # v4.8.0: 根据实际测试结果设置进度状态
                    # 读取结果文件确定实际测试状态
                    final_status = 'completed'  # 默认为完成
                    final_step = 'Test completed'
                    final_error = None
                    
                    if os.path.exists(result_path):
                        try:
                            with open(result_path, 'r', encoding='utf-8') as f:
                                temp_result = json_lib.load(f)
                            
                            # 检查实际测试状态
                            test_status = temp_result.get('status', 'failed')
                            test_error = temp_result.get('error')
                            
                            if test_status != 'passed':
                                final_status = 'failed'
                                final_step = 'Test failed'
                                final_error = test_error or f'Test status: {test_status}'
                        except Exception as read_err:
                            logger.warning(f"Failed to read result for status: {read_err}")
                    
                    with open(progress_path, 'w', encoding='utf-8') as f:
                        progress_data = {
                            'status': final_status,
                            'progress': 100,
                            'current_step': final_step
                        }
                        if final_error:
                            progress_data['error'] = final_error
                        if temp_result.get('phase') is not None:
                            progress_data['phase'] = temp_result['phase']
                        if temp_result.get('phase_component_name') is not None:
                            progress_data['phase_component_name'] = temp_result['phase_component_name']
                        if temp_result.get('phase_component_version') is not None:
                            progress_data['phase_component_version'] = temp_result['phase_component_version']
                        json_lib.dump(progress_data, f, ensure_ascii=False)

                    # 更新版本统计与测试历史（使用同步 Session，避免线程内新建事件循环导致 asyncpg 跨 loop 报错）
                    if os.path.exists(result_path):
                        with open(result_path, 'r', encoding='utf-8') as f:
                            result_dict = json_lib.load(f)
                        
                        stats_update_error = None
                        try:
                            from backend.models.database import SessionLocal
                            from sqlalchemy import select
                            from tools.test_component import TestStatus, ComponentTestResult, StepResult

                            db = SessionLocal()
                            try:
                                res = db.execute(select(ComponentVersion).where(ComponentVersion.id == version_id))
                                test_version = res.scalar_one_or_none()
                                if test_version:
                                    test_version.usage_count += 1
                                    if result_dict.get('status') == 'passed':
                                        test_version.success_count += 1
                                    else:
                                        test_version.failure_count += 1
                                    if test_version.usage_count > 0:
                                        test_version.success_rate = test_version.success_count / test_version.usage_count
                                    db.commit()
                                    logger.info(f"Updated version stats: usage={test_version.usage_count}")

                                test_result_obj = ComponentTestResult(
                                    component_name=result_dict.get('component_name', component_name),
                                    platform=result_dict.get('platform', platform),
                                    status=TestStatus(result_dict.get('status', 'failed')),
                                    start_time=result_dict.get('start_time'),
                                    end_time=result_dict.get('end_time'),
                                    duration_ms=result_dict.get('duration_ms', 0),
                                    steps_total=result_dict.get('steps_total', 0),
                                    steps_passed=result_dict.get('steps_passed', 0),
                                    steps_failed=result_dict.get('steps_failed', 0),
                                    error=result_dict.get('error'),
                                )
                                for sr_dict in result_dict.get('step_results', []):
                                    test_result_obj.step_results.append(StepResult(
                                        step_id=sr_dict.get('step_id', ''),
                                        action=sr_dict.get('action', ''),
                                        status=TestStatus(sr_dict.get('status', 'failed')),
                                        duration_ms=sr_dict.get('duration_ms', 0),
                                        error=sr_dict.get('error'),
                                        screenshot=sr_dict.get('screenshot'),
                                    ))
                                save_test_history_sync(
                                    db=db,
                                    component_name=version.component_name,
                                    platform=platform,
                                    account_id=request.account_id,
                                    test_result=test_result_obj,
                                    version_id=version_id,
                                    component_version=version.version,
                                )
                            finally:
                                db.close()
                        except Exception as e:
                            logger.error(f"Failed to update version stats: {e}", exc_info=True)
                            stats_update_error = str(e)
                            if progress_path and os.path.exists(progress_path):
                                try:
                                    with open(progress_path, 'r', encoding='utf-8') as f:
                                        progress_data = json_lib.load(f)
                                    progress_data['stats_update_error'] = stats_update_error
                                    with open(progress_path, 'w', encoding='utf-8') as f:
                                        json_lib.dump(progress_data, f, ensure_ascii=False)
                                except Exception:
                                    pass
                    
                    logger.info(f"Test {test_id} completed")
                
            except Exception as e:
                logger.error(f"Subprocess test failed: {e}", exc_info=True)
                # 写入错误状态
                with open(progress_path, 'w', encoding='utf-8') as f:
                    json_lib.dump({
                        'status': 'failed',
                        'progress': 100,
                        'current_step': 'Test failed',
                        'error': str(e)
                    }, f, ensure_ascii=False)
        
        # 9. 在独立线程中启动 subprocess 测试
        from concurrent.futures import ThreadPoolExecutor
        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(run_test_in_subprocess)
        
        # 10. 立即返回test_id给前端(用于 HTTP 轮询)
        logger.info(f"Test {test_id} started in background task")
        
        # #region agent log
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps({"location":"component_versions.py:730","message":"Returning test_id to frontend","data":{"test_id":test_id},"timestamp":__import__('datetime').datetime.now().isoformat(),"sessionId":"debug-session","hypothesisId":"H4"})+"\n")
        # #endregion
        
        return {
            "success": True,
            "test_id": test_id,
            "message": "测试已在后台启动,请轮询状态接口获取进度",
            "version_info": {
                "component_name": version.component_name,
                "version": version.version
            }
        }
    
    except ValueError as ve:
        # #region agent log
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps({"location":"component_versions.py:660","message":"ValueError caught","data":{"error":str(ve)},"timestamp":__import__('datetime').datetime.now().isoformat(),"sessionId":"debug-session","hypothesisId":"H3"})+"\n")
        # #endregion
        # 密码解密失败等业务异常
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, str(ve), status_code=500, detail=str(ve), recovery_suggestion="请稍后重试")
    except RuntimeError as re:
        # #region agent log
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps({"location":"component_versions.py:668","message":"RuntimeError caught","data":{"error":str(re)},"timestamp":__import__('datetime').datetime.now().isoformat(),"sessionId":"debug-session","hypothesisId":"H2"})+"\n")
        # #endregion
        # 测试进程失败等运行时异常
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, str(re), status_code=500, detail=str(re), recovery_suggestion="请稍后重试")
    except Exception as e:
        # #region agent log
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps({"location":"component_versions.py:676","message":"General exception caught","data":{"error":str(e),"type":type(e).__name__},"timestamp":__import__('datetime').datetime.now().isoformat(),"sessionId":"debug-session","hypothesisId":"H1"})+"\n")
        # #endregion
        logger.error(f"Failed to test component version: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"测试组件失败: {str(e)}", status_code=500, detail=str(e), recovery_suggestion="请稍后重试")


@router.get("/{version_id}/test/{test_id}/status")
async def get_test_status(
    version_id: int,
    test_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取测试进度状态(v4.7.4 新增)
    
    用于前端轮询,替代 WebSocket 实时推送
    
    Returns:
        {
            "status": "running|completed|failed",
            "progress": 0-100,
            "current_step": "当前步骤描述",
            "test_result": {...}  # 测试完成时返回完整结果
        }
    """
    import json
    from pathlib import Path
    
    project_root = Path(__file__).parent.parent.parent
    test_dir = project_root / 'temp' / 'component_tests' / test_id
    
    progress_path = test_dir / 'progress.json'
    result_path = test_dir / 'result.json'
    
    # 检查测试目录是否存在
    if not test_dir.exists():
        return error_response(ErrorCode.DATA_NOT_FOUND, f"测试 {test_id} 不存在", status_code=404, recovery_suggestion="请检查测试ID")
    
    # 读取进度文件
    progress_data = {
        'status': 'unknown',
        'progress': 0,
        'current_step': '未知状态'
    }
    
    if progress_path.exists():
        try:
            with open(progress_path, 'r', encoding='utf-8') as f:
                progress_data = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read progress file: {e}")
    
    # 如果测试完成,读取结果文件
    test_result = None
    if progress_data.get('status') in ['completed', 'failed'] and result_path.exists():
        try:
            with open(result_path, 'r', encoding='utf-8') as f:
                test_result = json.load(f)
            
            # [*] v4.7.4: 如果缺少 success_rate,计算它(兼容旧数据)
            if 'success_rate' not in test_result or test_result.get('success_rate') is None:
                steps_total = test_result.get('steps_total', 0)
                steps_passed = test_result.get('steps_passed', 0)
                if steps_total > 0:
                    test_result['success_rate'] = (steps_passed / steps_total) * 100  # 百分比
                else:
                    test_result['success_rate'] = 0.0
        except Exception as e:
            logger.warning(f"Failed to read result file: {e}")
    
    resp = {
        "status": progress_data.get('status', 'running'),
        "progress": progress_data.get('progress', 0),
        "current_step": progress_data.get('current_step') or progress_data.get('message', ''),
        "step_index": progress_data.get('step_index', 0),
        "step_total": progress_data.get('step_total', 0),
        "test_result": test_result,
        "error": progress_data.get('error'),
        "stats_update_error": progress_data.get('stats_update_error'),
        "phase": progress_data.get('phase'),
        "phase_component_name": progress_data.get('phase_component_name'),
        "phase_component_version": progress_data.get('phase_component_version'),
    }
    if progress_data.get('status') == 'verification_required':
        resp["verification_type"] = progress_data.get('verification_type', 'graphical_captcha')
        resp["verification_screenshot"] = progress_data.get('verification_screenshot', '')
        resp["verification_screenshot_url"] = f"/component-versions/{version_id}/test/{test_id}/verification-screenshot"
    if progress_data.get('verification_timeout'):
        resp["verification_timeout"] = True
    return resp


@router.get("/{version_id}/test/{test_id}/verification-screenshot")
async def get_test_verification_screenshot(
    version_id: int,
    test_id: str,
):
    """返回测试验证码截图（当测试处于 verification_required 时供前端展示）。"""
    from pathlib import Path
    from fastapi.responses import FileResponse

    project_root = Path(__file__).parent.parent.parent
    test_dir = project_root / "temp" / "component_tests" / test_id
    if not test_dir.exists():
        return error_response(ErrorCode.DATA_NOT_FOUND, f"测试 {test_id} 不存在", status_code=404, recovery_suggestion="请检查测试ID")
    progress_path = test_dir / "progress.json"
    if not progress_path.exists():
        return error_response(ErrorCode.FILE_NOT_FOUND, "进度文件不存在", status_code=404, recovery_suggestion="请重新发起测试")
    import json
    try:
        with open(progress_path, "r", encoding="utf-8") as f:
            progress_data = json.load(f)
    except Exception as ex:
        logger.error(f"读取进度失败: {ex}")
        return error_response(ErrorCode.FILE_READ_ERROR, "读取进度失败", status_code=500, detail=str(ex), recovery_suggestion="请重新发起测试")
    if progress_data.get("status") != "verification_required":
        return error_response(ErrorCode.PARAMETER_INVALID, "当前测试不需要验证码截图", status_code=400, recovery_suggestion="请确认测试状态")
    filename = progress_data.get("verification_screenshot") or "verification_screenshot.png"
    file_path = test_dir / filename
    if not file_path.exists():
        return error_response(ErrorCode.FILE_NOT_FOUND, "验证码截图文件不存在", status_code=404, recovery_suggestion="请上传验证码截图")
    return FileResponse(path=str(file_path), media_type="image/png", filename=filename)


class TestResumeRequest(BaseModel):
    """测试验证码回传请求体"""
    captcha_code: Optional[str] = Field(None, description="图形验证码")
    otp: Optional[str] = Field(None, description="短信/OTP 验证码")


@router.post("/{version_id}/test/{test_id}/resume")
async def post_test_resume(
    version_id: int,
    test_id: str,
    body: TestResumeRequest,
):
    """提交验证码并恢复测试（仅当测试 status 为 verification_required 时有效）。"""
    from pathlib import Path
    import json

    project_root = Path(__file__).parent.parent.parent
    test_dir = project_root / "temp" / "component_tests" / test_id
    if not test_dir.exists():
        return error_response(ErrorCode.DATA_NOT_FOUND, f"测试 {test_id} 不存在", status_code=404, recovery_suggestion="请检查测试ID")
    progress_path = test_dir / "progress.json"
    if not progress_path.exists():
        return error_response(ErrorCode.FILE_NOT_FOUND, "进度文件不存在", status_code=400, recovery_suggestion="请重新发起测试")
    try:
        with open(progress_path, "r", encoding="utf-8") as f:
            progress_data = json.load(f)
    except Exception as ex:
        logger.error(f"读取进度失败: {ex}")
        return error_response(ErrorCode.FILE_READ_ERROR, "读取进度失败", status_code=500, detail=str(ex), recovery_suggestion="请重新发起测试")
    if progress_data.get("status") != "verification_required":
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            "验证已超时或测试已结束，请重新发起测试",
            status_code=400,
            recovery_suggestion="请重新发起测试",
        )
    value = body.captcha_code or body.otp
    if not value or not value.strip():
        return error_response(ErrorCode.PARAMETER_INVALID, "请提供 captcha_code 或 otp", status_code=400, recovery_suggestion="请填写验证码或OTP")
    response_data = {}
    if body.captcha_code:
        response_data["captcha_code"] = body.captcha_code.strip()
    if body.otp:
        response_data["otp"] = body.otp.strip()
    response_path = test_dir / "verification_response.json"
    try:
        with open(response_path, "w", encoding="utf-8") as f:
            json.dump(response_data, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Write verification_response.json failed: {e}")
        return error_response(ErrorCode.FILE_WRITE_ERROR, "写入回传文件失败", status_code=500, detail=str(e), recovery_suggestion="请稍后重试")
    return {"success": True, "message": "验证码已提交，测试将继续执行"}


@router.get("/test-history", response_model=TestHistoryListResponse)
async def get_test_history(
    component_name: Optional[str] = Query(None, description="组件名称(可选筛选)"),
    limit: int = Query(5, ge=1, le=50, description="返回数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取组件测试历史记录
    
    参数:
    - component_name: 组件名称(可选),如 "shopee/login"
    - limit: 返回数量(默认5条)
    
    返回最近的测试历史记录
    """
    try:
        from sqlalchemy import func
        
        # 构建查询
        stmt = select(ComponentTestHistory)
        
        # 如果指定了组件名称,筛选
        if component_name:
            stmt = stmt.where(ComponentTestHistory.component_name == component_name)
        
        # 按测试时间降序排序
        stmt = stmt.order_by(ComponentTestHistory.tested_at.desc())
        
        # 限制数量
        stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        history_records = result.scalars().all()
        
        # 获取总数
        count_stmt = select(func.count(ComponentTestHistory.id))
        if component_name:
            count_stmt = count_stmt.where(ComponentTestHistory.component_name == component_name)
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # 格式化响应
        items = []
        for record in history_records:
            items.append(TestHistoryResponse(
                test_id=record.test_id,
                component_name=record.component_name,
                component_version=record.component_version,
                platform=record.platform,
                account_id=record.account_id,
                status=record.status,
                duration_ms=record.duration_ms,
                steps_total=record.steps_total,
                steps_passed=record.steps_passed,
                steps_failed=record.steps_failed,
                success_rate=record.success_rate,
                tested_at=record.tested_at.isoformat(),
                tested_by=record.tested_by
            ))
        
        return TestHistoryListResponse(total=total, items=items)
    
    except Exception as e:
        logger.error(f"Failed to get test history: {e}", exc_info=True)
        return error_response(ErrorCode.INTERNAL_SERVER_ERROR, f"获取测试历史失败: {str(e)}", status_code=500, detail=str(e), recovery_suggestion="请稍后重试")
