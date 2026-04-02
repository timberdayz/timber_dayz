"""
组件版本管理API路由 (Phase 9.4)

提供组件版本的CRUD、A/B测试、提升/回滚等功能
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import not_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.models.database import get_async_db
from backend.schemas.component_version import (
    ABTestRequest,
    BatchRegisterRequest,
    BatchRegisterResponse,
    BatchRegisterResult,
    ComponentTestRequest,
    ComponentVersionResponse,
    TestHistoryListResponse,
    TestHistoryResponse,
    TestResumeRequest,
    VersionListResponse,
    VersionRegisterRequest,
    VersionUpdateRequest,
)
from backend.services.component_name_utils import parse_component_name
from backend.services.collection_component_topology import (
    build_component_name_from_filename,
    is_canonical_component_filename,
)
from backend.services.active_collection_components import (
    is_active_component_name,
    is_archive_only_file,
    list_active_component_names,
)
from backend.services.component_version_service import ComponentVersionService
from backend.services.verification_service import VerificationService
from backend.services.verification_state_store import VerificationStateStore
from backend.services.verification_protocol import (
    extract_resume_submission,
    verification_input_mode,
)
from backend.services.collection_contracts import (
    build_date_range_from_time_selection,
    derive_granularity_from_time_selection,
    normalize_time_selection,
)
from backend.utils.api_response import error_response
from backend.utils.error_codes import ErrorCode
from modules.core.db import ComponentTestHistory, ComponentVersion
from modules.core.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/component-versions", tags=["组件版本管理"])


# canonical 组件文件清单：仅这些文件允许作为默认逻辑组件入口进入批量注册主路径
CANONICAL_COMPONENT_FILES = {
    "shopee": {
        "login.py",
        "navigation.py",
        "date_picker.py",
        "orders_export.py",
        "products_export.py",
        "analytics_export.py",
        "finance_export.py",
        "services_export.py",
    },
    "tiktok": {
        "login.py",
        "navigation.py",
        "date_picker.py",
        "shop_switch.py",
        "export.py",
    },
    "miaoshou": {
        "login.py",
        "navigation.py",
        "date_picker.py",
        "export.py",
        "orders_shopee_export.py",
        "orders_tiktok_export.py",
    },
}


def _is_canonical_component_file(platform: str, filename: str) -> bool:
    """Return True when the file is a canonical logical component entry."""
    try:
        return is_canonical_component_filename(filename)
    except Exception:
        return False


CANONICAL_COMPONENT_NAMES = {
    platform: {f"{platform}/{name[:-3]}" for name in filenames if name.endswith(".py")}
    for platform, filenames in CANONICAL_COMPONENT_FILES.items()
}


def _derive_python_test_component_name(
    *,
    version_component_name: str,
    logical_component: str,
    component_path: Path,
) -> str:
    """Preserve domain-specific python component names for version-page tests."""
    normalized_logical = str(logical_component or "").strip()
    if normalized_logical != "export":
        return normalized_logical

    version_tail = (
        version_component_name.split("/")[-1]
        if "/" in str(version_component_name or "")
        else str(version_component_name or "")
    )
    if str(version_tail or "").endswith("_export"):
        return version_tail

    stem = component_path.stem
    if stem.endswith("_export"):
        return stem

    return normalized_logical


def _get_test_verification_store_path(test_dir) -> Path:
    return test_dir / "verification_state.json"


def _get_canonical_component_names(platform: Optional[str] = None) -> list[str]:
    """Return canonical component_name values for a platform or all platforms."""
    project_root = Path(__file__).parent.parent.parent
    platforms_dir = project_root / "modules" / "platforms"
    target_platforms = [platform] if platform else ["shopee", "tiktok", "miaoshou"]

    merged: set[str] = set()
    for platform_name in target_platforms:
        platform_dir = platforms_dir / platform_name / "components"
        if not platform_dir.exists():
            continue
        for py_file in platform_dir.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
            if not is_canonical_component_filename(py_file.name):
                continue
            merged.add(build_component_name_from_filename(platform_name, py_file.name))
    return sorted(merged)


def _filter_component_names_by_type(
    component_names: list[str],
    component_type: Optional[str],
) -> list[str]:
    """Filter canonical component names by logical component type."""
    if not component_type:
        return component_names

    expected = component_type.strip().lower()
    filtered: list[str] = []
    for name in component_names:
        _, logical_type, _, _ = parse_component_name(name)
        if str(logical_type or "").lower() == expected:
            filtered.append(name)
    return filtered


def _build_component_test_runtime_config(
    request: ComponentTestRequest, component_name: str
) -> tuple[str, dict[str, Any]]:
    """Build runtime config for component tests from the request and component identity."""
    _, logical_type, data_domain, sub_domain = parse_component_name(component_name)
    logical_type = str(logical_type or "").lower()

    if logical_type != "export":
        return logical_type, {}

    runtime_config: dict[str, Any] = {}
    if request.shop_account_id and not request.account_id:
        runtime_config["shop_account_id"] = request.shop_account_id
    if data_domain:
        runtime_config["data_domain"] = data_domain

    effective_sub_domain = (request.sub_domain or sub_domain or "").strip()
    if effective_sub_domain:
        runtime_config["sub_domain"] = effective_sub_domain
        if str(data_domain or "").lower() == "services":
            runtime_config["services_subtype"] = effective_sub_domain

    time_selection = normalize_time_selection(
        time_selection=request.time_selection.model_dump(exclude_none=True)
        if request.time_selection
        else None,
        time_mode=request.time_mode,
        date_preset=request.date_preset,
        start_date=request.start_date,
        end_date=request.end_date,
        start_time=request.start_time,
        end_time=request.end_time,
    )
    if time_selection:
        runtime_config["time_selection"] = time_selection
        runtime_config["granularity"] = derive_granularity_from_time_selection(
            time_selection,
            request.granularity,
        )
        if time_selection["mode"] == "custom":
            runtime_config["custom_date_range"] = {
                "start_date": time_selection["start_date"],
                "end_date": time_selection["end_date"],
                "start_time": time_selection["start_time"],
                "end_time": time_selection["end_time"],
            }
        else:
            runtime_config["date_preset"] = time_selection["preset"]

        normalized_date_range = build_date_range_from_time_selection(time_selection)
        runtime_config.update(normalized_date_range)
    elif request.granularity:
        runtime_config["granularity"] = request.granularity

    return logical_type, runtime_config


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
        success_rate = (
            (test_result.steps_passed / test_result.steps_total)
            if test_result.steps_total > 0
            else 0.0
        )
        step_results_json = [
            {
                "step_id": s.step_id,
                "action": s.action,
                "status": s.status.value,
                "duration_ms": s.duration_ms,
                "error": s.error,
            }
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
            tested_at=datetime.now(timezone.utc),
        )
        history.tested_at = datetime.now(timezone.utc)
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
    component_version: Optional[str] = None,
) -> None:
    """保存测试历史记录到数据库"""
    import uuid

    try:
        # 计算成功率
        success_rate = (
            (test_result.steps_passed / test_result.steps_total)
            if test_result.steps_total > 0
            else 0.0
        )

        # 格式化步骤结果为JSON
        step_results_json = [
            {
                "step_id": s.step_id,
                "action": s.action,
                "status": s.status.value,
                "duration_ms": s.duration_ms,
                "error": s.error,
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
            tested_by="version_manager",  # 来自版本管理页
        )

        history.tested_at = datetime.now(timezone.utc)
        db.add(history)
        await db.commit()
        logger.info(f"Test history saved: {history.test_id}")

    except Exception as e:
        logger.warning(f"Failed to save test history: {e}")
        await db.rollback()


# ==================== API Endpoints ====================


@router.get("", response_model=VersionListResponse)
async def list_versions(
    platform: Optional[str] = Query(None, description="平台筛选"),
    component_type: Optional[str] = Query(None, description="组件类型筛选"),
    status: Optional[str] = Query(
        None, description="状态筛选: stable/testing/inactive"
    ),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db),
    request: Request = None,  # [*] Phase 3: 用于获取缓存服务
):
    """
    查询组件版本列表

    支持按平台、组件类型、状态筛选,分页查询
    [*] Phase 3: 添加缓存支持(5分钟TTL)
    """
    # [*] Phase 3: 尝试从缓存获取
    if request and hasattr(request.app.state, "cache_service"):
        cache_service = request.app.state.cache_service
        cached_data = await cache_service.get(
            "component_versions",
            platform=platform,
            component_type=component_type,
            status=status,
            page=page,
            page_size=page_size,
        )
        if cached_data is not None:
            logger.debug(
                f"[Cache] 组件版本列表缓存命中: platform={platform}, page={page}"
            )
            return VersionListResponse(**cached_data)

    try:
        ComponentVersionService(db)

        # 构建查询条件
        conditions = []
        active_component_names = list_active_component_names()
        if active_component_names:
            conditions.append(ComponentVersion.component_name.in_(active_component_names))

        # 平台筛选
        if platform:
            conditions.append(ComponentVersion.component_name.like(f"{platform}/%"))

        # 状态筛选
        if status == "stable":
            conditions.append(ComponentVersion.is_stable)
        elif status == "testing":
            conditions.append(ComponentVersion.is_testing)
        elif status == "inactive":
            conditions.append(not ComponentVersion.is_active)

        # v4.8.0: 排除非组件文件(config 文件、工具文件等)
        conditions.extend(
            [
                not_(ComponentVersion.file_path.like("%_config.py")),
                not_(ComponentVersion.file_path.like("%overlay_guard.py")),
                not_(ComponentVersion.component_name.like("%_config")),
                not_(ComponentVersion.component_name.like("%overlay_guard")),
            ]
        )

        stmt = (
            select(ComponentVersion)
            .where(*conditions)
            .order_by(
                ComponentVersion.success_rate.desc(), ComponentVersion.created_at.desc()
            )
        )
        result = await db.execute(stmt)
        versions = result.scalars().all()

        if component_type:
            expected = component_type.strip().lower()
            filtered_versions = []
            for row in versions:
                _, logical_type, _, _ = parse_component_name(row.component_name)
                if str(logical_type or "").lower() == expected:
                    filtered_versions.append(row)
            versions = filtered_versions

        # canonical-first: 同一逻辑组件只保留一个“当前工作行”
        # 选择规则：updated_at 更新更晚者优先；其后 created_at、更大的 id 作为稳定 tie-breaker
        latest_by_component = {}
        for row in versions:
            current = latest_by_component.get(row.component_name)
            if current is None:
                latest_by_component[row.component_name] = row
                continue

            current_key = (
                current.updated_at or current.created_at,
                current.created_at,
                current.id,
            )
            row_key = (
                row.updated_at or row.created_at,
                row.created_at,
                row.id,
            )
            if row_key > current_key:
                latest_by_component[row.component_name] = row

        collapsed_versions = sorted(
            latest_by_component.values(),
            key=lambda v: (
                -(v.success_rate or 0.0),
                -(v.created_at.timestamp() if v.created_at else 0),
            ),
        )
        total = len(collapsed_versions)
        offset = (page - 1) * page_size
        versions_page = collapsed_versions[offset : offset + page_size]

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
                updated_at=v.updated_at.isoformat(),
            )
            for v in versions_page
        ]

        result = VersionListResponse(
            data=data, total=total, page=page, page_size=page_size
        )

        # [*] Phase 3: 写入缓存
        if request and hasattr(request.app.state, "cache_service"):
            cache_service = request.app.state.cache_service
            await cache_service.set(
                "component_versions",
                result.dict(),
                ttl=300,  # 5分钟TTL
                platform=platform,
                component_type=component_type,
                status=status,
                page=page,
                page_size=page_size,
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
async def get_version(version_id: int, db: AsyncSession = Depends(get_async_db)):
    """获取版本详情"""
    try:
        result = await db.execute(
            select(ComponentVersion).where(ComponentVersion.id == version_id)
        )
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
            test_start_at=(
                version.test_start_at.isoformat() if version.test_start_at else None
            ),
            test_end_at=(
                version.test_end_at.isoformat() if version.test_end_at else None
            ),
            description=version.description,
            created_by=version.created_by,
            created_at=version.created_at.isoformat(),
            updated_at=version.updated_at.isoformat(),
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
    db: AsyncSession = Depends(get_async_db),
    http_request: Request = None,
):
    """注册新版本。新注册版本默认是草稿版本，不会直接成为稳定版本。"""
    try:
        service = ComponentVersionService(db)

        version = service.register_version(
            component_name=request.component_name,
            version=request.version,
            file_path=request.file_path,
            description=request.description,
            is_stable=request.is_stable,
            created_by=request.created_by,
        )

        # 失效组件版本列表缓存，使新注册版本立即出现在列表中
        if http_request and hasattr(http_request.app.state, "cache_service"):
            try:
                cache_service = http_request.app.state.cache_service
                await cache_service.invalidate("component_versions")
                logger.debug("[Cache] component_versions invalidated after register")
            except Exception as ce:
                logger.warning(f"[Cache] Failed to invalidate component_versions: {ce}")

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
            test_start_at=(
                version.test_start_at.isoformat() if version.test_start_at else None
            ),
            test_end_at=(
                version.test_end_at.isoformat() if version.test_end_at else None
            ),
            description=version.description,
            created_by=version.created_by,
            created_at=version.created_at.isoformat(),
            updated_at=version.updated_at.isoformat(),
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
    version_id: int, request: ABTestRequest, db: AsyncSession = Depends(get_async_db)
):
    """启动A/B测试"""
    try:
        service = ComponentVersionService(db)

        # 获取版本
        result = await db.execute(
            select(ComponentVersion).where(ComponentVersion.id == version_id)
        )
        version = result.scalar_one_or_none()
        if not version:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                "Version not found",
                status_code=404,
                recovery_suggestion="请检查版本ID",
            )

        # 启动A/B测试
        updated_version = service.start_ab_test(
            component_name=version.component_name,
            test_version=version.version,
            test_ratio=request.test_ratio,
            duration_days=request.duration_days,
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
            "test_end_at": updated_version.test_end_at.isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to start A/B test for version {version_id}: {e}")
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            str(e),
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.post("/{version_id}/stop-ab-test")
async def stop_ab_test(version_id: int, db: AsyncSession = Depends(get_async_db)):
    """停止A/B测试"""
    try:
        # 获取版本
        result = await db.execute(
            select(ComponentVersion).where(ComponentVersion.id == version_id)
        )
        version = result.scalar_one_or_none()
        if not version:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                "Version not found",
                status_code=404,
                recovery_suggestion="请检查版本ID",
            )

        if not version.is_testing:
            return error_response(
                ErrorCode.DATA_VALIDATION_FAILED,
                "Version is not in A/B testing",
                status_code=400,
                recovery_suggestion="请先加入A/B测试",
            )

        # 停止测试
        version.is_testing = False
        version.test_ratio = 0
        await db.commit()

        logger.info(f"A/B test stopped: {version.component_name} v{version.version}")

        return {"success": True, "message": "A/B测试已停止"}

    except Exception as e:
        logger.error(f"Failed to stop A/B test for version {version_id}: {e}")
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            str(e),
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.post("/{version_id}/promote")
async def promote_to_stable(
    version_id: int,
    db: AsyncSession = Depends(get_async_db),
    http_request: Request = None,
):
    """提升为稳定版本"""
    try:
        # 获取版本
        result = await db.execute(
            select(ComponentVersion).where(ComponentVersion.id == version_id)
        )
        version = result.scalar_one_or_none()
        if not version:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                "Version not found",
                status_code=404,
                recovery_suggestion="请检查版本ID",
            )

        if not is_active_component_name(version.component_name):
            return {
                "success": False,
                "message": "inactive components cannot be promoted to stable from the default path",
            }
        if version.file_path and is_archive_only_file(version.file_path):
            return {
                "success": False,
                "message": "archive-only component files cannot be promoted to stable",
            }

        now = datetime.now(timezone.utc)

        stable_result = await db.execute(
            select(ComponentVersion).where(
                ComponentVersion.component_name == version.component_name,
                ComponentVersion.is_stable == True,
                ComponentVersion.id != version.id,
            )
        )
        for other_stable in stable_result.scalars().all():
            other_stable.is_stable = False
            other_stable.updated_at = now

        if version.file_path:
            same_path_result = await db.execute(
                select(ComponentVersion).where(
                    ComponentVersion.file_path == version.file_path,
                    ComponentVersion.is_stable == True,
                    ComponentVersion.id != version.id,
                )
            )
            for same_path_stable in same_path_result.scalars().all():
                same_path_stable.is_stable = False
                same_path_stable.updated_at = now

        version.is_stable = True
        version.is_testing = False
        version.updated_at = now

        await db.commit()
        await db.refresh(version)

        if http_request and hasattr(http_request.app.state, "cache_service"):
            try:
                cache_service = http_request.app.state.cache_service
                await cache_service.invalidate("component_versions")
                logger.debug("[Cache] component_versions invalidated after promote")
            except Exception as ce:
                logger.warning(f"[Cache] Failed to invalidate component_versions: {ce}")

        logger.info(
            f"Version promoted to stable: {version.component_name} v{version.version}"
        )

        return {"success": True, "message": "已提升为稳定版本"}

    except Exception as e:
        logger.error(f"Failed to promote version {version_id}: {e}")
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            str(e),
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.patch("/{version_id}")
async def update_version(
    version_id: int,
    request: VersionUpdateRequest,
    db: AsyncSession = Depends(get_async_db),
    http_request: Request = None,
):
    """更新版本"""
    try:
        # 获取版本
        result = await db.execute(
            select(ComponentVersion).where(ComponentVersion.id == version_id)
        )
        version = result.scalar_one_or_none()
        if not version:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                "Version not found",
                status_code=404,
                recovery_suggestion="请检查版本ID",
            )

        # 更新字段
        if request.is_active is not None:
            version.is_active = request.is_active
        if request.description is not None:
            version.description = request.description

        await db.commit()

        # 失效组件版本列表缓存，使前端禁用/启用后立即看到最新状态与操作按钮
        if http_request and hasattr(http_request.app.state, "cache_service"):
            try:
                cache_service = http_request.app.state.cache_service
                await cache_service.invalidate("component_versions")
                logger.debug("[Cache] component_versions invalidated after update")
            except Exception as ce:
                logger.warning(f"[Cache] Failed to invalidate component_versions: {ce}")

        logger.info(f"Version updated: {version.component_name} v{version.version}")

        return {"success": True, "message": "版本已更新"}

    except Exception as e:
        logger.error(f"Failed to update version {version_id}: {e}")
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            str(e),
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.delete("/{version_id}")
async def delete_version(
    version_id: int, request: Request = None, db: AsyncSession = Depends(get_async_db)
):
    """
    删除组件版本。可删除条件: !is_testing && !is_active (非测试中且已禁用)。
    稳定版在禁用后也可删除。
    """
    from pathlib import Path

    try:
        result = await db.execute(
            select(ComponentVersion).where(ComponentVersion.id == version_id)
        )
        version = result.scalar_one_or_none()

        if not version:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                "版本不存在",
                status_code=404,
                recovery_suggestion="请检查版本ID",
            )

        if version.is_testing:
            return error_response(
                ErrorCode.DATA_VALIDATION_FAILED,
                "无法删除正在测试的版本,请先停止A/B测试",
                status_code=400,
                recovery_suggestion="请先停止A/B测试",
            )
        if version.is_active:
            return error_response(
                ErrorCode.DATA_VALIDATION_FAILED,
                "无法删除启用中的版本,请先禁用",
                status_code=400,
                recovery_suggestion="请先禁用版本",
            )

        # 记录删除信息
        component_name = version.component_name
        version_str = version.version
        file_path = version.file_path

        # 删除前检查：是否还有其他版本引用同一 file_path
        other_result = await db.execute(
            select(ComponentVersion).where(
                ComponentVersion.file_path == file_path,
                ComponentVersion.id != version_id,
            )
        )
        other_versions = other_result.scalars().all()
        should_delete_file = (
            len(other_versions) == 0 and file_path and file_path.endswith(".py")
        )

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

        logger.info(
            f"Deleted version: {component_name} v{version_str} (file: {file_path}, file_deleted={file_deleted})"
        )

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
                "file_path": file_path,
            },
        }

    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete version {version_id}: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            f"删除版本失败: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.get("/{component_name}/statistics")
async def get_component_statistics(
    component_name: str, db: AsyncSession = Depends(get_async_db)
):
    """获取组件所有版本的统计信息"""
    try:
        service = ComponentVersionService(db)
        stats = service.get_version_statistics(component_name)

        return {"success": True, "component_name": component_name, "versions": stats}

    except Exception as e:
        logger.error(f"Failed to get statistics for {component_name}: {e}")
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            str(e),
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.post("/batch-register-python", response_model=BatchRegisterResponse)
async def batch_register_python_components(
    request: BatchRegisterRequest = None,
    db: AsyncSession = Depends(get_async_db),
    http_request: Request = None,
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
    from datetime import datetime, timezone
    from pathlib import Path

    from backend.services.component_name_utils import (
        is_standard_component_name,
        parse_filename_to_component_and_version,
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
                logger.warning(
                    f"Platform components directory not found: {platform_dir}"
                )
                continue

            for py_file in platform_dir.glob("*.py"):
                # 跳过 __init__.py
                if py_file.name.startswith("__"):
                    continue
                if not _is_canonical_component_file(platform, py_file.name):
                    results.append(
                        BatchRegisterResult(
                            component_name=f"{platform}/{py_file.stem}",
                            file_path=str(py_file.relative_to(project_root)).replace(
                                "\\", "/"
                            ),
                            version="",
                            status="skipped",
                            error="non-canonical component file",
                        )
                    )
                    skipped_count += 1
                    continue

                comp_name, default_version = parse_filename_to_component_and_version(
                    py_file.name, platform
                )
                if not comp_name:
                    continue
                component_name = comp_name
                if not is_active_component_name(component_name):
                    results.append(
                        BatchRegisterResult(
                            component_name=component_name,
                            file_path=str(py_file.relative_to(project_root)).replace("\\", "/"),
                            version="",
                            status="skipped",
                            error="inactive component",
                        )
                    )
                    skipped_count += 1
                    continue
                relative_path = str(py_file.relative_to(project_root)).replace(
                    "\\", "/"
                )
                if not is_standard_component_name(component_name):
                    logger.warning(
                        f"Non-standard component_name (will register): {component_name}"
                    )

                try:
                    # 先提取组件类型(用于后续更新描述)
                    component_type = "unknown"
                    try:
                        spec = importlib.util.spec_from_file_location(
                            "component", py_file
                        )
                        module = importlib.util.module_from_spec(spec)
                        sys.modules["component"] = module
                        spec.loader.exec_module(module)

                        for attr_name in dir(module):
                            attr = getattr(module, attr_name)
                            if isinstance(attr, type) and hasattr(
                                attr, "component_type"
                            ):
                                component_type = getattr(
                                    attr, "component_type", "unknown"
                                )
                                break
                    except Exception:
                        sys.modules.pop("component", None)
                        # 从文件名推断
                        if "login" in py_file.stem:
                            component_type = "login"
                        elif "navigation" in py_file.stem:
                            component_type = "navigation"
                        elif "date_picker" in py_file.stem:
                            component_type = "date_picker"
                        elif (
                            "shop_selector" in py_file.stem
                            or "shop_switch" in py_file.stem
                        ):
                            component_type = "shop_switch"
                        elif "overlay_guard" in py_file.stem:
                            component_type = "overlay_guard"
                        elif "metrics_selector" in py_file.stem:
                            component_type = "metrics_selector"
                        elif "analytics" in py_file.stem:
                            component_type = "analytics"
                        elif "export" in py_file.stem:
                            component_type = "export"
                        else:
                            component_type = "other"
                    else:
                        sys.modules.pop("component", None)

                    # 检查是否已存在(基于 component_name + version,这是唯一约束)
                    existing_result = await db.execute(
                        select(ComponentVersion).where(
                            ComponentVersion.component_name == component_name,
                            ComponentVersion.version == default_version,
                        )
                    )
                    existing = existing_result.scalar_one_or_none()

                    if existing:
                        # 如果 file_path 相同,跳过
                        if existing.file_path == relative_path:
                            results.append(
                                BatchRegisterResult(
                                    component_name=component_name,
                                    file_path=relative_path,
                                    version=existing.version,
                                    status="skipped",
                                    error=None,
                                )
                            )
                            skipped_count += 1
                            continue
                        else:
                            # file_path 不同,更新 file_path(从YAML迁移到Python的情况)
                            existing.file_path = relative_path
                            existing.updated_at = datetime.now(timezone.utc)
                            # 如果描述还是旧的,更新描述
                            if (
                                "YAML" in existing.description
                                or "DEPRECATED" in existing.description
                            ):
                                existing.description = (
                                    f"Python component: {component_type}"
                                )

                            results.append(
                                BatchRegisterResult(
                                    component_name=component_name,
                                    file_path=relative_path,
                                    version=existing.version,
                                    status="updated",
                                    error=None,
                                )
                            )
                            registered_count += 1  # 计入更新
                            logger.info(
                                f"Updated Python component file_path: {component_name} -> {relative_path}"
                            )
                            continue

                    # 注册新版本，默认非稳定（与录制保存一致）
                    new_version = ComponentVersion(
                        component_name=component_name,
                        version=default_version,
                        file_path=relative_path,
                        description=f"Python component: {component_type}",
                        is_stable=False,
                        is_active=True,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    db.add(new_version)  # AsyncSession.add is sync

                    results.append(
                        BatchRegisterResult(
                            component_name=component_name,
                            file_path=relative_path,
                            version=default_version,
                            status="registered",
                            error=None,
                        )
                    )
                    registered_count += 1
                    logger.info(f"Registered Python component: {component_name}")

                except Exception as e:
                    results.append(
                        BatchRegisterResult(
                            component_name=component_name,
                            file_path=relative_path,
                            version="",
                            status="error",
                            error=str(e),
                        )
                    )
                    error_count += 1
                    logger.error(f"Failed to register {component_name}: {e}")

        await db.commit()

        # 失效组件版本列表缓存，使批量注册后列表立即更新
        if http_request and hasattr(http_request.app.state, "cache_service"):
            try:
                cache_service = http_request.app.state.cache_service
                await cache_service.invalidate("component_versions")
                logger.debug(
                    "[Cache] component_versions invalidated after batch-register"
                )
            except Exception as ce:
                logger.warning(f"[Cache] Failed to invalidate component_versions: {ce}")

        logger.info(
            f"Batch registration completed: {registered_count} registered, "
            f"{skipped_count} skipped, {error_count} errors"
        )

        return BatchRegisterResponse(
            success=error_count == 0,
            registered_count=registered_count,
            skipped_count=skipped_count,
            error_count=error_count,
            details=results,
        )

    except Exception as e:
        await db.rollback()
        logger.error(f"Batch registration failed: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            str(e),
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.post("/{version_id}/test")
async def test_component_version(
    version_id: int,
    request: ComponentTestRequest,
    db: AsyncSession = Depends(get_async_db),
):
    """
    测试组件版本 - v4.7.4: HTTP 轮询进度

    从版本管理页调用,测试已注册的组件版本
    进度通过 GET /component-versions/{version_id}/test/{test_id}/status 接口查询

    重构说明:移除 WebSocket,统一使用 HTTP 轮询
    """

    # #region agent log
    import json
    from pathlib import Path

    import yaml

    from backend.services.component_test_service import ComponentTestService
    from modules.core.path_manager import get_project_root

    log_file = get_project_root() / ".cursor" / "debug.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "location": "component_versions.py:522",
                    "message": "test_component_version called",
                    "data": {
                        "version_id": version_id,
                        "account_id": request.account_id,
                    },
                    "timestamp": __import__("datetime").datetime.now().isoformat(),
                    "sessionId": "debug-session",
                    "hypothesisId": "H1",
                }
            )
            + "\n"
        )
    # #endregion

    try:
        # 1. 获取版本信息
        result = await db.execute(
            select(ComponentVersion).where(ComponentVersion.id == version_id)
        )
        version = result.scalar_one_or_none()

        if not version:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                "版本不存在",
                status_code=404,
                recovery_suggestion="请检查版本ID",
            )

        if not version.is_active:
            return error_response(
                ErrorCode.DATA_VALIDATION_FAILED,
                "该版本已禁用,无法测试",
                status_code=400,
                recovery_suggestion="请先启用版本",
            )

        # 2. 验证账号
        from modules.core.db import PlatformAccount

        account_result = await db.execute(
            select(PlatformAccount).where(
                PlatformAccount.account_id == request.account_id
            )
        )
        account = account_result.scalar_one_or_none()

        if not account:
            return error_response(
                ErrorCode.DATA_NOT_FOUND,
                "账号不存在",
                status_code=404,
                recovery_suggestion="请检查账号ID",
            )

        # #region agent log
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "location": "component_versions.py:548",
                        "message": "Account found",
                        "data": {
                            "account_id": account.account_id,
                            "platform": account.platform,
                        },
                        "timestamp": __import__("datetime").datetime.now().isoformat(),
                        "sessionId": "debug-session",
                        "hypothesisId": "H3",
                    }
                )
                + "\n"
            )
        # #endregion

        logger.info(
            f"Testing component version: {version.component_name} v{version.version} "
            f"with account: {request.account_id}"
        )

        # 3. 读取组件文件(支持 YAML 和 Python 组件)
        project_root = Path(__file__).parent.parent.parent
        component_path = project_root / version.file_path

        if not component_path.exists():
            return error_response(
                ErrorCode.FILE_NOT_FOUND,
                f"组件文件不存在: {version.file_path}",
                status_code=404,
                recovery_suggestion="请检查组件路径或重新上传",
            )

        # v4.8.0: 判断是 Python 组件还是 YAML 组件；用 parse_component_name 取标准化 comp_type 保证类发现一致
        is_python_component = version.file_path.endswith(".py")
        from backend.services.component_name_utils import parse_component_name

        _platform_parsed, comp_type, _domain, _sub = parse_component_name(
            version.component_name
        )
        rest = (
            version.component_name.split("/")[-1]
            if "/" in version.component_name
            else version.component_name
        )
        logical_component = (
            comp_type
            if comp_type
            in (
                "login",
                "navigation",
                "export",
                "date_picker",
                "shop_switch",
                "filters",
            )
            else rest
        )
        # 兼容历史 component_name 如 miaoshou_login -> login
        if logical_component.endswith("_login"):
            logical_component = "login"
        is_discovery_component = logical_component in ("date_picker", "filters")
        logical_type, runtime_config = _build_component_test_runtime_config(
            request, version.component_name
        )
        fixed_data_domain = runtime_config.get("data_domain")
        fixed_sub_domain = runtime_config.get("sub_domain")

        if logical_type == "export":
            if "granularity" not in runtime_config or "time_selection" not in runtime_config:
                return error_response(
                    ErrorCode.PARAMETER_INVALID,
                    "导出组件测试需要提供快捷时间或自定义时间范围",
                    status_code=400,
                    recovery_suggestion="请选择快捷时间，或选择自定义时间范围并提供粒度",
                )
            if str(fixed_data_domain or "").lower() == "services" and not fixed_sub_domain:
                return error_response(
                    ErrorCode.PARAMETER_INVALID,
                    "服务数据域导出测试需要选择子数据域",
                    status_code=400,
                    recovery_suggestion="请选择服务子数据域",
                )

        if is_python_component:
            # Python 组件:从文件路径提取平台和组件名
            # 例如: modules/platforms/shopee/components/login.py
            path_parts = version.file_path.replace("\\", "/").split("/")
            if "platforms" in path_parts:
                platform_idx = path_parts.index("platforms") + 1
                if platform_idx < len(path_parts):
                    platform = path_parts[platform_idx]
                else:
                    platform = version.component_name.split("/")[0]
            component_config = {}  # Python 组件不需要 YAML 配置

            # 1.8: 发现模式组件测试策略门禁（flow_only 不允许单组件测试）
            if is_discovery_component:
                try:
                    from modules.apps.collection_center.component_loader import (
                        ComponentLoader,
                    )

                    loader = ComponentLoader()
                    comp_cls = loader.load_python_component_from_path(
                        version.file_path,
                        version_id=version.id,
                        platform=platform,
                        component_type=logical_component,
                    )
                    test_mode = (
                        str(getattr(comp_cls, "test_mode", "") or "").strip().lower()
                    )
                    test_config = getattr(comp_cls, "test_config", {}) or {}
                    if test_mode in ("", "flow_only"):
                        return error_response(
                            ErrorCode.DATA_VALIDATION_FAILED,
                            f"{logical_component} 组件当前 test_mode={test_mode or 'flow_only'}，仅支持完整链路验证（flow_only）",
                            status_code=400,
                            recovery_suggestion="请在组件中设置 test_mode='standalone' 并提供 test_config 后再单组件测试",
                        )
                    if test_mode != "standalone":
                        return error_response(
                            ErrorCode.DATA_VALIDATION_FAILED,
                            f"{logical_component} 组件 test_mode={test_mode} 非法",
                            status_code=400,
                            recovery_suggestion="允许值仅 flow_only / standalone",
                        )
                    if not isinstance(test_config, dict):
                        return error_response(
                            ErrorCode.DATA_VALIDATION_FAILED,
                            f"{logical_component} 组件 test_config 必须是字典",
                            status_code=400,
                            recovery_suggestion="请提供 test_config.test_url 或 test_config.test_data_domain",
                        )
                    has_url = bool(
                        test_config.get("test_url") or test_config.get("url")
                    )
                    has_domain = bool(
                        test_config.get("test_data_domain")
                        or test_config.get("data_domain")
                    )
                    if not has_url and not has_domain:
                        return error_response(
                            ErrorCode.DATA_VALIDATION_FAILED,
                            f"{logical_component} standalone 测试缺少 test_config",
                            status_code=400,
                            recovery_suggestion="请提供 test_config.test_url 或 test_config.test_data_domain",
                        )
                except Exception as e:
                    return error_response(
                        ErrorCode.INTERNAL_SERVER_ERROR,
                        f"读取发现模式组件测试策略失败: {e}",
                        status_code=500,
                        recovery_suggestion="请检查组件元数据（test_mode/test_config）并重试",
                    )
        else:
            # YAML 组件
            with open(component_path, "r", encoding="utf-8") as f:
                component_config = yaml.safe_load(f)
            platform = component_config.get(
                "platform", version.component_name.split("/")[0]
            )
        # 使用逻辑组件名（如 login、orders_export），供 component_loader 按类名约定查找；Python 已用 parse_component_name 得到 logical_component
        if is_python_component:
            component_name = _derive_python_test_component_name(
                version_component_name=version.component_name,
                logical_component=logical_component,
                component_path=component_path,
            )
        else:
            component_name = (
                version.component_name.split("/")[-1]
                if "/" in version.component_name
                else component_path.stem
            )

        # 4. 使用统一服务准备账号信息 [*]
        account_info = ComponentTestService.prepare_account_info(account)

        # #region agent log
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "location": "component_versions.py:573",
                        "message": "Account info prepared",
                        "data": {
                            "has_username": bool(account_info.get("username")),
                            "has_password": bool(account_info.get("password")),
                            "platform": account_info.get("platform"),
                        },
                        "timestamp": __import__("datetime").datetime.now().isoformat(),
                        "sessionId": "debug-session",
                        "hypothesisId": "H3",
                    }
                )
                + "\n"
            )
        # #endregion

        # 5. 生成测试ID(用于 HTTP 轮询状态查询)
        test_id = f"test_{uuid.uuid4().hex[:12]}"
        logger.info(f"Starting test with ID: {test_id}")

        # #region agent log
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "location": "component_versions.py:600",
                        "message": "Starting background test",
                        "data": {
                            "test_id": test_id,
                            "platform": platform,
                            "component_name": component_name,
                        },
                        "timestamp": __import__("datetime").datetime.now().isoformat(),
                        "sessionId": "debug-session",
                        "hypothesisId": "H2",
                    }
                )
                + "\n"
            )
        # #endregion

        # 6. 使用独立进程运行测试(subprocess 方案)
        # [*] v4.7.4: 移除 WebSocket,使用 HTTP 轮询获取进度
        # 进度和结果保存在 temp/ 目录下,通过状态查询接口获取

        # 创建进度/结果目录
        import os

        test_dir = project_root / "temp" / "component_tests" / test_id
        test_dir.mkdir(parents=True, exist_ok=True)

        config_path = test_dir / "config.json"
        result_path = test_dir / "result.json"
        progress_path = test_dir / "progress.json"

        # 写入配置文件
        import json as json_lib

        test_config = {
            "platform": platform,
            "account_id": request.account_id,
            "component_name": component_name,
            "component_path": str(component_path),
            "headless": False,
            "screenshot_on_error": True,
            "account_info": account_info,
            "version_id": version_id,  # 用于更新统计
            "test_dir": str(
                test_dir
            ),  # 验证码回传：子进程轮询 verification_response.json 的目录
            "runtime_config": runtime_config,
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json_lib.dump(test_config, f, ensure_ascii=False)

        # 写入初始进度
        initial_progress = {
            "status": "running",
            "progress": 0,
            "current_step": "Starting test...",
            "step_index": 0,
            "step_total": 0,
            "message": "Starting test...",
        }
        with open(progress_path, "w", encoding="utf-8") as f:
            json_lib.dump(initial_progress, f, ensure_ascii=False)

        def run_test_in_subprocess():
            """在独立进程中运行测试"""
            import subprocess  # nosec B404

            try:
                # 启动 subprocess
                script_path = project_root / "tools" / "run_component_test.py"
                logger.info(f"Starting subprocess test: {script_path}")

                proc = subprocess.Popen(  # nosec B603
                    [
                        sys.executable,
                        str(script_path),
                        str(config_path),
                        str(result_path),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

                # 等待子进程完成(子进程会写入进度文件)
                stdout, stderr = proc.communicate()

                if proc.returncode != 0:
                    logger.error(f"Subprocess exited with code {proc.returncode}")
                    logger.error(f"STDERR: {stderr[:1000] if stderr else 'none'}")

                    # 写入失败状态
                    with open(progress_path, "w", encoding="utf-8") as f:
                        json_lib.dump(
                            {
                                "status": "failed",
                                "progress": 100,
                                "current_step": "Test failed",
                                "error": stderr[:500] if stderr else "Unknown error",
                            },
                            f,
                            ensure_ascii=False,
                        )
                else:
                    # v4.8.0: 根据实际测试结果设置进度状态
                    # 读取结果文件确定实际测试状态
                    final_status = "completed"  # 默认为完成
                    final_step = "Test completed"
                    final_error = None

                    if os.path.exists(result_path):
                        try:
                            with open(result_path, "r", encoding="utf-8") as f:
                                temp_result = json_lib.load(f)

                            # 检查实际测试状态
                            test_status = temp_result.get("status", "failed")
                            test_error = temp_result.get("error")

                            if test_status != "passed":
                                final_status = "failed"
                                final_step = "Test failed"
                                final_error = (
                                    test_error or f"Test status: {test_status}"
                                )
                        except Exception as read_err:
                            logger.warning(
                                f"Failed to read result for status: {read_err}"
                            )

                    with open(progress_path, "w", encoding="utf-8") as f:
                        progress_data = {
                            "status": final_status,
                            "progress": 100,
                            "current_step": final_step,
                        }
                        if final_error:
                            progress_data["error"] = final_error
                        if temp_result.get("phase") is not None:
                            progress_data["phase"] = temp_result["phase"]
                        if temp_result.get("phase_component_name") is not None:
                            progress_data["phase_component_name"] = temp_result[
                                "phase_component_name"
                            ]
                        if temp_result.get("phase_component_version") is not None:
                            progress_data["phase_component_version"] = temp_result[
                                "phase_component_version"
                            ]
                        json_lib.dump(progress_data, f, ensure_ascii=False)

                    # 更新版本统计与测试历史（使用同步 Session，避免线程内新建事件循环导致 asyncpg 跨 loop 报错）
                    if os.path.exists(result_path):
                        with open(result_path, "r", encoding="utf-8") as f:
                            result_dict = json_lib.load(f)

                        stats_update_error = None
                        try:
                            from sqlalchemy import select

                            from backend.models.database import SessionLocal
                            from tools.test_component import (
                                ComponentTestResult,
                                StepResult,
                                TestStatus,
                            )

                            db = SessionLocal()
                            try:
                                res = db.execute(
                                    select(ComponentVersion).where(
                                        ComponentVersion.id == version_id
                                    )
                                )
                                test_version = res.scalar_one_or_none()
                                if test_version:
                                    test_version.usage_count += 1
                                    if result_dict.get("status") == "passed":
                                        test_version.success_count += 1
                                    else:
                                        test_version.failure_count += 1
                                    if test_version.usage_count > 0:
                                        test_version.success_rate = (
                                            test_version.success_count
                                            / test_version.usage_count
                                        )
                                    db.commit()
                                    logger.info(
                                        f"Updated version stats: usage={test_version.usage_count}"
                                    )

                                test_result_obj = ComponentTestResult(
                                    component_name=result_dict.get(
                                        "component_name", component_name
                                    ),
                                    platform=result_dict.get("platform", platform),
                                    status=TestStatus(
                                        result_dict.get("status", "failed")
                                    ),
                                    start_time=result_dict.get("start_time"),
                                    end_time=result_dict.get("end_time"),
                                    duration_ms=result_dict.get("duration_ms", 0),
                                    steps_total=result_dict.get("steps_total", 0),
                                    steps_passed=result_dict.get("steps_passed", 0),
                                    steps_failed=result_dict.get("steps_failed", 0),
                                    error=result_dict.get("error"),
                                )
                                for sr_dict in result_dict.get("step_results", []):
                                    test_result_obj.step_results.append(
                                        StepResult(
                                            step_id=sr_dict.get("step_id", ""),
                                            action=sr_dict.get("action", ""),
                                            status=TestStatus(
                                                sr_dict.get("status", "failed")
                                            ),
                                            duration_ms=sr_dict.get("duration_ms", 0),
                                            error=sr_dict.get("error"),
                                            screenshot=sr_dict.get("screenshot"),
                                        )
                                    )
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
                            logger.error(
                                f"Failed to update version stats: {e}", exc_info=True
                            )
                            stats_update_error = str(e)
                            if progress_path and os.path.exists(progress_path):
                                try:
                                    with open(
                                        progress_path, "r", encoding="utf-8"
                                    ) as f:
                                        progress_data = json_lib.load(f)
                                    progress_data["stats_update_error"] = (
                                        stats_update_error
                                    )
                                    with open(
                                        progress_path, "w", encoding="utf-8"
                                    ) as f:
                                        json_lib.dump(
                                            progress_data, f, ensure_ascii=False
                                        )
                                except Exception as exc:
                                    logger.debug(
                                        "Failed to append agent log for test %s: %s",
                                        test_id,
                                        exc,
                                    )

                    logger.info(f"Test {test_id} completed")

            except Exception as e:
                logger.error(f"Subprocess test failed: {e}", exc_info=True)
                # 写入错误状态
                with open(progress_path, "w", encoding="utf-8") as f:
                    json_lib.dump(
                        {
                            "status": "failed",
                            "progress": 100,
                            "current_step": "Test failed",
                            "error": str(e),
                        },
                        f,
                        ensure_ascii=False,
                    )

        # 9. 在独立线程中启动 subprocess 测试
        from concurrent.futures import ThreadPoolExecutor

        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(run_test_in_subprocess)

        # 10. 立即返回test_id给前端(用于 HTTP 轮询)
        logger.info(f"Test {test_id} started in background task")

        # #region agent log
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "location": "component_versions.py:730",
                        "message": "Returning test_id to frontend",
                        "data": {"test_id": test_id},
                        "timestamp": __import__("datetime").datetime.now().isoformat(),
                        "sessionId": "debug-session",
                        "hypothesisId": "H4",
                    }
                )
                + "\n"
            )
        # #endregion

        return {
            "success": True,
            "test_id": test_id,
            "message": "测试已在后台启动,请轮询状态接口获取进度",
            "version_info": {
                "component_name": version.component_name,
                "version": version.version,
            },
        }

    except ValueError as ve:
        # #region agent log
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "location": "component_versions.py:660",
                        "message": "ValueError caught",
                        "data": {"error": str(ve)},
                        "timestamp": __import__("datetime").datetime.now().isoformat(),
                        "sessionId": "debug-session",
                        "hypothesisId": "H3",
                    }
                )
                + "\n"
            )
        # #endregion
        # 密码解密失败等业务异常
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            str(ve),
            status_code=500,
            detail=str(ve),
            recovery_suggestion="请稍后重试",
        )
    except RuntimeError as re:
        # #region agent log
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "location": "component_versions.py:668",
                        "message": "RuntimeError caught",
                        "data": {"error": str(re)},
                        "timestamp": __import__("datetime").datetime.now().isoformat(),
                        "sessionId": "debug-session",
                        "hypothesisId": "H2",
                    }
                )
                + "\n"
            )
        # #endregion
        # 测试进程失败等运行时异常
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            str(re),
            status_code=500,
            detail=str(re),
            recovery_suggestion="请稍后重试",
        )
    except Exception as e:
        # #region agent log
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(
                json.dumps(
                    {
                        "location": "component_versions.py:676",
                        "message": "General exception caught",
                        "data": {"error": str(e), "type": type(e).__name__},
                        "timestamp": __import__("datetime").datetime.now().isoformat(),
                        "sessionId": "debug-session",
                        "hypothesisId": "H1",
                    }
                )
                + "\n"
            )
        # #endregion
        logger.error(f"Failed to test component version: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            f"测试组件失败: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )


@router.get("/{version_id}/test/{test_id}/status")
async def get_test_status(
    version_id: int, test_id: str, db: AsyncSession = Depends(get_async_db)
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
    test_dir = project_root / "temp" / "component_tests" / test_id

    progress_path = test_dir / "progress.json"
    result_path = test_dir / "result.json"

    # 检查测试目录是否存在
    if not test_dir.exists():
        return error_response(
            ErrorCode.DATA_NOT_FOUND,
            f"测试 {test_id} 不存在",
            status_code=404,
            recovery_suggestion="请检查测试ID",
        )

    # 读取进度文件
    progress_data = {"status": "unknown", "progress": 0, "current_step": "未知状态"}

    if progress_path.exists():
        try:
            with open(progress_path, "r", encoding="utf-8") as f:
                progress_data = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read progress file: {e}")

    # 如果测试完成,读取结果文件
    test_result = None
    if progress_data.get("status") in ["completed", "failed"] and result_path.exists():
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                test_result = json.load(f)

            # [*] v4.7.4: 如果缺少 success_rate,计算它(兼容旧数据)
            if (
                "success_rate" not in test_result
                or test_result.get("success_rate") is None
            ):
                steps_total = test_result.get("steps_total", 0)
                steps_passed = test_result.get("steps_passed", 0)
                if steps_total > 0:
                    test_result["success_rate"] = (
                        steps_passed / steps_total
                    ) * 100  # 百分比
                else:
                    test_result["success_rate"] = 0.0
        except Exception as e:
            logger.warning(f"Failed to read result file: {e}")

    resp = {
        "status": progress_data.get("status", "running"),
        "progress": progress_data.get("progress", 0),
        "current_step": progress_data.get("current_step")
        or progress_data.get("message", ""),
        "step_index": progress_data.get("step_index", 0),
        "step_total": progress_data.get("step_total", 0),
        "test_result": test_result,
        "error": progress_data.get("error"),
        "stats_update_error": progress_data.get("stats_update_error"),
        "phase": progress_data.get("phase"),
        "phase_component_name": progress_data.get("phase_component_name"),
        "phase_component_version": progress_data.get("phase_component_version"),
    }
    if progress_data.get("status") == "verification_required":
        resp["verification_type"] = progress_data.get(
            "verification_type", "graphical_captcha"
        )
        resp["verification_input_mode"] = verification_input_mode(
            progress_data.get("verification_type")
        )
        resp["verification_screenshot"] = progress_data.get(
            "verification_screenshot", ""
        )
        resp["verification_id"] = progress_data.get("verification_id")
        resp["verification_message"] = progress_data.get("verification_message")
        resp["verification_expires_at"] = progress_data.get("verification_expires_at")
        resp["verification_attempt_count"] = progress_data.get(
            "verification_attempt_count", 0
        )
        resp["verification_screenshot_url"] = (
            f"/component-versions/{version_id}/test/{test_id}/verification-screenshot"
        )
    if progress_data.get("verification_timeout"):
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
        return error_response(
            ErrorCode.DATA_NOT_FOUND,
            f"测试 {test_id} 不存在",
            status_code=404,
            recovery_suggestion="请检查测试ID",
        )
    progress_path = test_dir / "progress.json"
    if not progress_path.exists():
        return error_response(
            ErrorCode.FILE_NOT_FOUND,
            "进度文件不存在",
            status_code=404,
            recovery_suggestion="请重新发起测试",
        )
    import json

    try:
        with open(progress_path, "r", encoding="utf-8") as f:
            progress_data = json.load(f)
    except Exception as ex:
        logger.error(f"读取进度失败: {ex}")
        return error_response(
            ErrorCode.FILE_READ_ERROR,
            "读取进度失败",
            status_code=500,
            detail=str(ex),
            recovery_suggestion="请重新发起测试",
        )
    if progress_data.get("status") != "verification_required":
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            "当前测试不需要验证码截图",
            status_code=400,
            recovery_suggestion="请确认测试状态",
        )
    filename = (
        progress_data.get("verification_screenshot") or "verification_screenshot.png"
    )
    file_path = test_dir / filename
    if not file_path.exists():
        return error_response(
            ErrorCode.FILE_NOT_FOUND,
            "验证码截图文件不存在",
            status_code=404,
            recovery_suggestion="请上传验证码截图",
        )
    return FileResponse(path=str(file_path), media_type="image/png", filename=filename)


@router.post("/{version_id}/test/{test_id}/resume")
async def post_test_resume(
    version_id: int,
    test_id: str,
    body: TestResumeRequest,
):
    """提交验证码并恢复测试（仅当测试 status 为 verification_required 时有效）。"""
    import json
    from pathlib import Path

    project_root = Path(__file__).parent.parent.parent
    test_dir = project_root / "temp" / "component_tests" / test_id
    if not test_dir.exists():
        return error_response(
            ErrorCode.DATA_NOT_FOUND,
            f"测试 {test_id} 不存在",
            status_code=404,
            recovery_suggestion="请检查测试ID",
        )
    progress_path = test_dir / "progress.json"
    if not progress_path.exists():
        return error_response(
            ErrorCode.FILE_NOT_FOUND,
            "进度文件不存在",
            status_code=400,
            recovery_suggestion="请重新发起测试",
        )
    try:
        with open(progress_path, "r", encoding="utf-8") as f:
            progress_data = json.load(f)
    except Exception as ex:
        logger.error(f"读取进度失败: {ex}")
        return error_response(
            ErrorCode.FILE_READ_ERROR,
            "读取进度失败",
            status_code=500,
            detail=str(ex),
            recovery_suggestion="请重新发起测试",
        )
    if progress_data.get("status") != "verification_required":
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            "验证已超时或测试已结束，请重新发起测试",
            status_code=400,
            recovery_suggestion="请重新发起测试",
        )
    value, response_data = extract_resume_submission(
        captcha_code=body.captcha_code,
        otp=body.otp,
        manual_completed=body.manual_completed,
    )
    if not response_data:
        return error_response(
            ErrorCode.PARAMETER_INVALID,
            "请提供 captcha_code、otp 或 manual_completed",
            status_code=400,
            recovery_suggestion="请填写验证码/OTP，或在完成人工验证后点击继续",
        )

    verification_id = str(progress_data.get("verification_id") or "").strip()
    if verification_id:
        try:
            store = VerificationStateStore(
                storage_path=_get_test_verification_store_path(test_dir)
            )
            submitted_payload = VerificationService(store=store).mark_submitted(
                verification_id=verification_id
            )
            progress_data["status"] = submitted_payload["state"]
            progress_data["verification_attempt_count"] = submitted_payload.get(
                "attempt_count", progress_data.get("verification_attempt_count", 0)
            )
            with open(progress_path, "w", encoding="utf-8") as f:
                json.dump(progress_data, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Mark component test verification submitted failed: {e}")

    response_path = test_dir / "verification_response.json"
    try:
        with open(response_path, "w", encoding="utf-8") as f:
            json.dump(response_data, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Write verification_response.json failed: {e}")
        return error_response(
            ErrorCode.FILE_WRITE_ERROR,
            "写入回传文件失败",
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )
    return {"success": True, "message": "验证码已提交，测试将继续执行"}


@router.get("/test-history", response_model=TestHistoryListResponse)
async def get_test_history(
    component_name: Optional[str] = Query(None, description="组件名称(可选筛选)"),
    limit: int = Query(5, ge=1, le=50, description="返回数量"),
    db: AsyncSession = Depends(get_async_db),
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
            count_stmt = count_stmt.where(
                ComponentTestHistory.component_name == component_name
            )
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0

        # 格式化响应
        items = []
        for record in history_records:
            items.append(
                TestHistoryResponse(
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
                    tested_by=record.tested_by,
                )
            )

        return TestHistoryListResponse(total=total, items=items)

    except Exception as e:
        logger.error(f"Failed to get test history: {e}", exc_info=True)
        return error_response(
            ErrorCode.INTERNAL_SERVER_ERROR,
            f"获取测试历史失败: {str(e)}",
            status_code=500,
            detail=str(e),
            recovery_suggestion="请稍后重试",
        )
