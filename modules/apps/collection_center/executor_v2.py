"""
采集执行引擎 V2 - Collection Executor V2

组件驱动的采集执行引擎,支持:
- 组件加载和执行
- 弹窗自动处理
- 状态回调和进度报告
- 超时控制和取消检测
- 验证码暂停处理
"""

import os
import asyncio
import uuid
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Awaitable, Tuple, Union
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse

from modules.core.logger import get_logger
from backend.services.verification_protocol import apply_verification_result_to_params, verification_input_mode
from backend.services.main_account_session_coordinator import (
    MainAccountSessionCoordinator,
    get_main_account_session_coordinator,
)
from backend.services.platform_login_entry_service import get_platform_login_entry
from modules.core.path_manager import get_data_raw_dir
from modules.apps.collection_center.component_loader import ComponentLoader
from modules.apps.collection_center.browser_config_helper import (
    enforce_official_playwright_browser,
)
from modules.apps.collection_center.popup_handler import UniversalPopupHandler, StepPopupHandler
from modules.apps.collection_center.python_component_adapter import PythonComponentAdapter, create_adapter
from modules.apps.collection_center.transition_gates import (
    GateStatus,
    evaluate_export_complete,
    evaluate_login_ready,
)
from backend.services.collection_contracts import (
    count_collection_targets,
    normalize_collection_date_range,
    normalize_domain_subtypes,
)

logger = get_logger(__name__)

MAIN_ACCOUNT_SESSION_STEP_MESSAGES = {
    "waiting_for_main_account_session": "等待主账号会话",
    "preparing_main_account_session": "准备主账号会话",
    "switching_target_shop": "切换目标店铺",
    "target_shop_ready": "目标店铺已就绪",
}

# 用于 SessionManager/DeviceFingerprintManager 同步 IO 的线程池(避免阻塞事件循环)
_executor_pool: Optional[ThreadPoolExecutor] = None


def _get_executor_pool() -> ThreadPoolExecutor:
    global _executor_pool
    if _executor_pool is None:
        _executor_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="collection_io")
    return _executor_pool


def _normalize_account_id(account_id: Any, account: Dict[str, Any]) -> Tuple[str, bool]:
    """
    规范化 account_id 并判断是否使用按账号会话/指纹。
    以执行器入参 account_id 为事实标准，与 account 中的 account_id 保持一致。
    若缺失或无法安全转为字符串则回退到完整登录+全局指纹。
    """
    try:
        sid = str(account_id).strip() if account_id is not None else ""
        if not sid:
            logger.warning("account_id is missing or empty, disabling account session and fingerprint")
            return "", False
        acc_id = (account or {}).get("account_id")
        if acc_id is not None and str(acc_id).strip() != sid:
            logger.warning(
                "account_id from param (%s) differs from account.account_id (%s), using param",
                sid, acc_id,
            )
        return sid, True
    except Exception as e:
        logger.warning("Failed to normalize account_id: %s, disabling account session and fingerprint", e)
        return "", False


def _resolve_session_scope(account_id: Any, account: Dict[str, Any]) -> Tuple[str, str, bool]:
    """Resolve session owner and shop-account IDs for runtime execution."""
    try:
        shop_account_id = str(
            account_id
            or (account or {}).get("shop_account_id")
            or (account or {}).get("account_id")
            or ""
        ).strip()
        session_owner_id = str(
            (account or {}).get("main_account_id")
            or (account or {}).get("parent_account")
            or ""
        ).strip()
        if not session_owner_id:
            logger.warning(
                "session owner id is missing or empty for shop account %s; disabling account session and fingerprint",
                shop_account_id,
            )
            return "", shop_account_id, False
        return session_owner_id, shop_account_id, True
    except Exception as e:
        logger.warning("Failed to resolve session scope: %s", e)
        return "", "", False


def _extract_platform_shop_context(platform: str, current_url: str) -> Dict[str, Optional[str]]:
    parsed = urlparse(str(current_url or ""))
    query = parse_qs(parsed.query)
    detected_platform_shop_id = None
    for key in ("cnsc_shop_id", "shop_id"):
        values = query.get(key) or []
        if values and str(values[0]).strip():
            detected_platform_shop_id = str(values[0]).strip()
            break
    detected_region = None
    for key in ("shop_region", "region"):
        values = query.get(key) or []
        if values and str(values[0]).strip():
            detected_region = str(values[0]).strip().upper()
            break
    return {
        "platform": str(platform or "").strip().lower() or None,
        "detected_platform_shop_id": detected_platform_shop_id,
        "detected_region": detected_region,
        "current_url": str(current_url or "").strip() or None,
    }


async def _record_platform_shop_discovery_async(
    *,
    platform: str,
    page: Any,
    params: Dict[str, Any],
    account: Optional[Dict[str, Any]] = None,
) -> None:
    main_account_id = str(params.get("main_account_id") or "").strip()
    shop_account_id = str(params.get("shop_account_id") or "").strip()
    if not main_account_id or not shop_account_id:
        return

    payload = _extract_platform_shop_context(platform, str(getattr(page, "url", "") or ""))
    detected_platform_shop_id = payload.get("detected_platform_shop_id")
    if not detected_platform_shop_id:
        return

    detected_store_name = (
        str((account or {}).get("store_name") or params.get("shop_name") or "").strip() or None
    )

    try:
        from backend.models.database import AsyncSessionLocal
        from backend.services.platform_shop_discovery_service import (
            get_platform_shop_discovery_service,
        )

        async with AsyncSessionLocal() as db:
            service = get_platform_shop_discovery_service()
            await service.record_runtime_discovery(
                db,
                platform=str(platform or "").lower(),
                main_account_id=main_account_id,
                shop_account_id=shop_account_id,
                detected_store_name=detected_store_name,
                detected_platform_shop_id=detected_platform_shop_id,
                detected_region=payload.get("detected_region"),
                raw_payload=payload,
            )
    except Exception as e:
        logger.warning("Failed to record platform shop discovery: %s", e)


async def _load_session_async(platform: str, account_id: str, max_age_days: int = 30) -> Optional[Dict[str, Any]]:
    """在线程池中加载会话，避免阻塞事件循环。返回 session_data 或 None。"""
    from modules.utils.sessions.session_manager import SessionManager
    loop = asyncio.get_event_loop()
    def _load() -> Optional[Dict[str, Any]]:
        sm = SessionManager()
        return sm.load_session(platform, account_id, max_age_days=max_age_days)
    return await loop.run_in_executor(_get_executor_pool(), _load)


def _bootstrap_session_from_profile_sync(
    platform: str,
    account_id: str,
    account_config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """Best-effort bridge from persistent profile to storage_state session."""
    from playwright.sync_api import sync_playwright
    from modules.utils.sessions.session_manager import SessionManager

    session_manager = SessionManager()
    profile_path = session_manager.get_persistent_profile_path(platform, account_id)

    try:
        if not profile_path.exists() or not any(profile_path.iterdir()):
            logger.debug("No persistent profile found for %s/%s", platform, account_id)
            return None
    except Exception:
        logger.debug("Persistent profile probe failed for %s/%s", platform, account_id)
        return None

    launch_options = enforce_official_playwright_browser({"headless": True})

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_path),
                accept_downloads=False,
                **launch_options,
            )
            try:
                storage_state = context.storage_state()
            finally:
                context.close()
    except Exception as e:
        logger.warning(
            "Bootstrap session from profile failed for %s/%s: %s",
            platform,
            account_id,
            e,
        )
        return None

    try:
        session_manager.save_session(
            platform,
            account_id,
            storage_state,
            metadata={
                "bootstrapped_from_profile": True,
                "saved_at": time.time(),
            },
        )
    except Exception as e:
        logger.warning(
            "Saving bootstrapped session failed for %s/%s: %s",
            platform,
            account_id,
            e,
        )

    return {"storage_state": storage_state}


async def _load_or_bootstrap_session_async(
    platform: str,
    account_id: str,
    account_config: Optional[Dict[str, Any]] = None,
    *,
    max_age_days: int = 30,
) -> Optional[Dict[str, Any]]:
    session_data = await _load_session_async(
        platform,
        account_id,
        max_age_days=max_age_days,
    )
    if session_data and isinstance(session_data.get("storage_state"), dict):
        return session_data

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _get_executor_pool(),
        lambda: _bootstrap_session_from_profile_sync(
            platform,
            account_id,
            account_config=account_config,
        ),
    )


async def _save_session_async(platform: str, account_id: str, storage_state: Dict[str, Any]) -> bool:
    """在线程池中保存会话。"""
    from modules.utils.sessions.session_manager import SessionManager
    loop = asyncio.get_event_loop()
    def _save() -> bool:
        sm = SessionManager()
        return sm.save_session(platform, account_id, storage_state)
    return await loop.run_in_executor(_get_executor_pool(), _save)


def _build_runtime_task_params(
    *,
    task_id: str,
    account: Dict[str, Any],
    platform: str,
    granularity: str,
    normalized_date_range: Dict[str, Any],
    task_download_dir: Union[str, Path],
    screenshot_dir: Union[str, Path],
    reused_session: bool,
) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "account": account,
        "params": {
            "date_from": normalized_date_range.get("date_from", ""),
            "date_to": normalized_date_range.get("date_to", ""),
            "granularity": granularity,
        },
        "task": {
            "id": task_id,
            "download_dir": str(task_download_dir),
            "screenshot_dir": str(screenshot_dir),
        },
        "platform": platform,
        "granularity": granularity,
        "reused_session": reused_session,
        "downloads_path": str(task_download_dir),
        "start_date": normalized_date_range.get("start_date"),
        "end_date": normalized_date_range.get("end_date"),
    }

    time_selection = normalized_date_range.get("time_selection")
    if time_selection:
        params["time_selection"] = time_selection
        params["params"]["time_selection"] = time_selection
        if str(time_selection.get("mode") or "").strip().lower() == "custom":
            params["custom_date_range"] = {
                "start_date": time_selection.get("start_date"),
                "end_date": time_selection.get("end_date"),
                "start_time": time_selection.get("start_time", "00:00:00"),
                "end_time": time_selection.get("end_time", "23:59:59"),
            }

    return params


def _build_runtime_account(platform: str, account: Dict[str, Any]) -> Dict[str, Any]:
    runtime_account = dict(account or {})
    runtime_account["login_url"] = get_platform_login_entry(platform)
    return runtime_account


async def _get_fingerprint_context_options_async(
    platform: str, account_id: str, account: Optional[Dict[str, Any]] = None, proxy: Optional[Dict] = None
) -> Dict[str, Any]:
    """在线程池中获取按账号的 Playwright context 选项。"""
    from modules.utils.sessions.device_fingerprint import DeviceFingerprintManager
    loop = asyncio.get_event_loop()
    def _get() -> Dict[str, Any]:
        fm = DeviceFingerprintManager()
        return fm.get_playwright_context_options(platform, account_id, account, proxy=proxy)
    return await loop.run_in_executor(_get_executor_pool(), _get)


def _build_playwright_context_options_from_fingerprint(fp_options: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 DeviceFingerprintManager 返回的选项转为 Playwright new_context 可用的参数。
    过滤不兼容项(如 permissions 以 list 形式表示授予，此处不授予权限以保持与指纹一致)。
    """
    # Playwright new_context 常用参数（不含 downloads_path：当前 Playwright API 不在 new_context 接受该参数，下载路径由组件通过 save_as 指定）
    allowed = {
        "user_agent", "viewport", "locale", "timezone_id", "device_scale_factor",
        "is_mobile", "has_touch", "color_scheme", "reduced_motion", "forced_colors",
        "extra_http_headers", "ignore_https_errors", "java_script_enabled",
        "accept_downloads",
    }
    out = {}
    for k, v in fp_options.items():
        if k in allowed and v is not None:
            out[k] = v
    # permissions: 指纹中为 denied，不传给 new_context 即不授予，符合预期
    if "permissions" in fp_options and isinstance(fp_options["permissions"], list) and not fp_options["permissions"]:
        pass  # 不授予任何权限
    return out


# Phase 9.4: 版本管理支持(懒加载,避免循环依赖)
_version_service = None

def _get_version_service():
    """懒加载版本管理服务(避免导入时的循环依赖)"""
    global _version_service
    if _version_service is None:
        try:
            from backend.services.component_version_service import ComponentVersionService
            from backend.models.database import SessionLocal
            
            db = SessionLocal()
            _version_service = ComponentVersionService(db)
            logger.info("ComponentVersionService initialized for executor")
        except Exception as e:
            logger.warning(f"Failed to initialize ComponentVersionService: {e}")
            _version_service = False  # 标记为尝试过但失败
    
    return _version_service if _version_service is not False else None


@dataclass
class CollectionResult:
    """采集结果(v4.7.0)"""
    task_id: str
    status: str  # completed, partial_success, failed, cancelled, paused
    files_collected: int = 0
    collected_files: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    duration_seconds: float = 0.0
    # v4.7.0: 任务粒度优化
    completed_domains: List[str] = field(default_factory=list)
    failed_domains: List[Dict[str, str]] = field(default_factory=list)
    total_domains: int = 0


@dataclass
class TaskContext:
    """任务上下文(用于任务恢复)v4.7.0"""
    task_id: str
    platform: str
    account_id: str
    data_domains: List[str]
    date_range: Dict[str, str]
    granularity: str
    
    # v4.7.0: 子域支持
    sub_domains: Optional[List[str]] = None
    
    # 执行状态
    current_component_index: int = 0
    current_step_index: int = 0
    current_data_domain_index: int = 0
    collected_files: List[str] = field(default_factory=list)
    
    # v4.7.0: 任务粒度优化
    completed_domains: List[str] = field(default_factory=list)
    failed_domains: List[Dict[str, str]] = field(default_factory=list)
    
    # 验证码状态
    verification_required: bool = False
    verification_type: Optional[str] = None
    screenshot_path: Optional[str] = None


class StepExecutionError(Exception):
    """步骤执行错误"""
    pass


class VerificationRequiredError(Exception):
    """需要验证码"""
    def __init__(self, verification_type: str, screenshot_path: str = None):
        self.verification_type = verification_type
        self.screenshot_path = screenshot_path
        super().__init__(f"Verification required: {verification_type}")


class TaskCancelledError(Exception):
    """任务被取消"""
    pass


class CollectionExecutorV2:
    """
    组件驱动的采集执行引擎
    
    功能:
    1. 组件加载和顺序执行
    2. 弹窗自动处理
    3. 状态回调和进度报告
    4. 超时控制
    5. 任务取消检测
    6. 验证码暂停处理
    7. 文件处理和注册
    8. [*] Phase 9.1: 并行执行支持(多域并行采集)
    """
    
    # 默认超时配置
    DEFAULT_COMPONENT_TIMEOUT = int(os.getenv('COMPONENT_TIMEOUT', 300))  # 5分钟
    DEFAULT_TASK_TIMEOUT = int(os.getenv('TASK_TIMEOUT', 1800))  # 30分钟
    DEFAULT_DOWNLOAD_TIMEOUT = int(os.getenv('DOWNLOAD_TIMEOUT', 120))  # 2分钟
    
    def __init__(
        self,
        component_loader: ComponentLoader = None,
        popup_handler: UniversalPopupHandler = None,
        status_callback: Callable[..., Awaitable[None]] = None,
        is_cancelled_callback: Callable[[str], Awaitable[bool]] = None,
        verification_required_callback: Callable[[str, str, Optional[str]], Awaitable[Optional[str]]] = None,
        main_account_session_coordinator: MainAccountSessionCoordinator = None,
    ):
        """
        初始化执行引擎
        
        Args:
            component_loader: 组件加载器
            popup_handler: 弹窗处理器
            status_callback: 状态回调函数 (task_id, progress, message) -> None
            is_cancelled_callback: 取消检测函数 (task_id) -> bool
            verification_required_callback: 验证码需要时回调 (task_id, verification_type, screenshot_path) -> 回传值或 None(超时)
        """
        self.component_loader = component_loader or ComponentLoader()
        self.popup_handler = popup_handler or UniversalPopupHandler()
        self.status_callback = status_callback
        self.is_cancelled_callback = is_cancelled_callback
        self.verification_required_callback = verification_required_callback
        self.main_account_session_coordinator = (
            main_account_session_coordinator or get_main_account_session_coordinator()
        )
        
        # 任务上下文缓存(用于暂停/恢复)
        self._task_contexts: Dict[str, TaskContext] = {}
        
        # 下载目录
        self.temp_dir = Path(os.getenv('TEMP_DIR', 'temp'))
        self.downloads_dir = self.temp_dir / 'downloads'
        self.screenshots_dir = self.temp_dir / 'screenshots'
        
        # 确保目录存在
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)
        
        # v4.8.0: Python 组件模式(移除 YAML 支持)
        # 设置为 True 强制使用 Python 组件
        self.use_python_components = True  # 默认使用 Python 组件
        
        logger.info("CollectionExecutorV2 initialized (Python components mode)")

    async def _run_with_main_account_session_lock(
        self,
        *,
        task_id: str,
        platform: str,
        main_account_id: str,
        operation: Callable[[], Awaitable[Any]],
    ) -> Any:
        if (
            self.main_account_session_coordinator.is_locked(platform, main_account_id)
            or self.main_account_session_coordinator.waiter_count(platform, main_account_id) > 0
        ):
            await self._update_status(
                task_id,
                5,
                MAIN_ACCOUNT_SESSION_STEP_MESSAGES["waiting_for_main_account_session"],
            )

        async with self.main_account_session_coordinator.acquire(platform, main_account_id):
            await self._update_status(
                task_id,
                5,
                MAIN_ACCOUNT_SESSION_STEP_MESSAGES["preparing_main_account_session"],
            )
            return await operation()

    async def _execute_shared_login_phase(
        self,
        *,
        task_id: str,
        platform: str,
        account: Dict[str, Any],
        params: Dict[str, Any],
        context: TaskContext,
        browser: Any,
        play_context: Any,
        page: Any,
        adapter: Optional[PythonComponentAdapter],
        runtime_manifests: Optional[Dict[str, Any]],
        session_platform: str,
        session_account_id: str,
        save_session_after_login: bool,
        start_time: datetime,
        total_domains_count: int,
    ) -> Tuple[Any, Any, Optional[CollectionResult]]:
        await self._update_status(task_id, 5, "姝ｅ湪鐧诲綍...")
        await self._check_cancelled(task_id)
        await self.popup_handler.close_popups(page, platform=platform)

        login_success = False
        while True:
            try:
                if runtime_manifests is not None:
                    login_manifest = runtime_manifests.get("login")
                    login_result = await self._run_runtime_manifest_component(
                        page=page,
                        manifest=login_manifest,
                        account=account,
                        config=params,
                    )
                    login_success = bool(getattr(login_result, "success", False))
                else:
                    login_success = await self._execute_python_component(
                        page=page,
                        adapter=adapter,
                        component_type="login",
                        params=params,
                    )
                break
            except VerificationRequiredError as e:
                if self._requires_headful_login_fallback(e.verification_type):
                    fallback_result = await self._run_headful_login_fallback(
                        task_id=task_id,
                        platform=platform,
                        account=account,
                        params=params,
                        browser=browser,
                        old_context=play_context,
                        session_platform=session_platform,
                        session_account_id=session_account_id,
                        runtime_manifests=runtime_manifests,
                    )
                    if len(fallback_result) == 4:
                        login_success, play_context, page, fallback_outcome = fallback_result
                    else:
                        login_success, play_context, page = fallback_result
                        fallback_outcome = "success" if login_success else "failed"
                    if not login_success and fallback_outcome == "timeout":
                        return play_context, page, self._build_verification_timeout_result(
                            task_id=task_id,
                            verification_type=e.verification_type,
                            context=context,
                            start_time=start_time,
                            total_domains_count=total_domains_count,
                        )
                    break

                value = await self._wait_verification_and_continue(
                    task_id, e.verification_type, e.screenshot_path, page, params, adapter, is_login=True
                )
                if value is None:
                    return play_context, page, self._build_verification_timeout_result(
                        task_id=task_id,
                        verification_type=e.verification_type,
                        context=context,
                        start_time=start_time,
                        total_domains_count=total_domains_count,
                    )
                apply_verification_result_to_params(
                    params,
                    verification_type=e.verification_type,
                    value=value,
                )
                continue

        if not login_success:
            raise StepExecutionError("鐧诲綍缁勪欢鎵ц澶辫触")

        if params.get("shop_account_id"):
            await self._update_status(
                task_id,
                12,
                MAIN_ACCOUNT_SESSION_STEP_MESSAGES["switching_target_shop"],
            )
        await self._ensure_login_gate_ready(page, platform)
        await self._update_status(
            task_id,
            15,
            MAIN_ACCOUNT_SESSION_STEP_MESSAGES["target_shop_ready"],
        )
        logger.info(
            "Task %s: [Python] Login completed successfully (reused_session=%s)",
            task_id,
            params.get("reused_session", False),
        )
        await _record_platform_shop_discovery_async(
            platform=platform,
            page=page,
            params=params,
            account=account,
        )
        if save_session_after_login and session_platform and session_account_id:
            try:
                storage_state = await page.context.storage_state()
                ok = await _save_session_async(session_platform, session_account_id, storage_state)
                if ok:
                    logger.info(
                        "Task %s: session saved for %s/%s",
                        task_id,
                        session_platform,
                        session_account_id,
                    )
                else:
                    logger.warning(
                        "Task %s: session save returned False for %s/%s",
                        task_id,
                        session_platform,
                        session_account_id,
                    )
            except Exception as e:
                logger.warning("Task %s: save_session failed: %s", task_id, e)
        context.current_component_index = 1
        return play_context, page, None

    @staticmethod
    def _verification_timeout_status(verification_type: str | None) -> str:
        return (
            "manual_intervention_required"
            if verification_input_mode(verification_type) == "manual_continue"
            else "paused"
        )

    @staticmethod
    def _verification_timeout_message(verification_type: str | None) -> str:
        return (
            "等待人工处理超时"
            if verification_input_mode(verification_type) == "manual_continue"
            else "验证码等待超时"
        )

    def _build_verification_timeout_result(
        self,
        *,
        task_id: str,
        verification_type: str | None,
        context: TaskContext,
        start_time: datetime,
        total_domains_count: int,
    ) -> CollectionResult:
        return CollectionResult(
            task_id=task_id,
            status=self._verification_timeout_status(verification_type),
            files_collected=len(context.collected_files),
            collected_files=context.collected_files,
            error_message=self._verification_timeout_message(verification_type),
            duration_seconds=(datetime.now() - start_time).total_seconds(),
            completed_domains=context.completed_domains,
            failed_domains=context.failed_domains,
            total_domains=total_domains_count,
        )

    async def _ensure_login_gate_ready(self, page: Any, platform: str) -> None:
        from modules.utils.login_status_detector import LoginStatusDetector

        detector = LoginStatusDetector(platform, debug=False)
        detection_result = await detector.detect(page, wait_for_redirect=True)
        gate_result = evaluate_login_ready(
            status=detection_result.status.value,
            confidence=detection_result.confidence,
            current_url=str(getattr(page, "url", "") or ""),
            matched_signal=detection_result.matched_pattern or detection_result.detected_by,
        )
        if gate_result.status is not GateStatus.READY:
            raise StepExecutionError(
                f"login gate not ready: status={detection_result.status.value}, "
                f"confidence={detection_result.confidence:.2f}, url={getattr(page, 'url', '')}"
            )

    def _ensure_export_complete(
        self,
        file_path: Optional[str],
        *,
        component_name: Optional[str] = None,
        success_message: Optional[str] = None,
    ) -> Optional[str]:
        gate_result = evaluate_export_complete(
            file_path=file_path,
            component_name=component_name,
            success_message=success_message,
        )
        if gate_result.status is not GateStatus.READY:
            raise StepExecutionError(f"export completion failed: {gate_result.reason}")
        return file_path

    def _resolve_file_landing_semantics(
        self,
        *,
        platform: str,
        data_domain: str,
        sub_domain: Optional[str],
    ) -> Dict[str, str]:
        collection_platform = str(platform or "").strip().lower()
        business_platform = collection_platform
        landing_sub_domain = str(sub_domain or "").strip().lower()
        normalized_domain = str(data_domain or "").strip().lower()

        if (
            collection_platform == "miaoshou"
            and normalized_domain == "orders"
            and landing_sub_domain in {"shopee", "tiktok"}
        ):
            business_platform = landing_sub_domain
            landing_sub_domain = ""

        return {
            "business_platform": business_platform,
            "landing_sub_domain": landing_sub_domain,
            "collection_platform": collection_platform,
        }
    
    def _load_component_with_version(
        self,
        component_name: str,
        params: Dict[str, Any],
        enable_ab_test: bool = True,
        force_version: str = None
    ) -> Dict[str, Any]:
        """
        加载组件,支持版本选择(Phase 9.4)
        
        Args:
            component_name: 组件名称(如shopee/login)
            params: 组件参数
            enable_ab_test: 是否启用A/B测试
            force_version: 强制使用指定版本
        
        Returns:
            加载的组件配置
        """
        version_service = _get_version_service()
        
        # 解析 platform / 组件名（如 "shopee/login" -> shopee, login）
        parts = component_name.split("/", 1)
        platform = parts[0] if len(parts) >= 2 else ""
        comp_name = parts[1] if len(parts) >= 2 else component_name

        # 如果版本服务不可用，优先 Python 组件
        if version_service is None:
            logger.debug(f"Version service not available, loading default component: {component_name}")
            component = self.component_loader.build_component_dict_from_python(platform, comp_name, params)
            if component:
                return component
            return self.component_loader.load(component_name, params)

        try:
            # 使用版本服务选择版本
            selected_version = version_service.select_version_for_use(
                component_name=component_name,
                force_version=force_version,
                enable_ab_test=enable_ab_test,
            )

            if selected_version and getattr(selected_version, "file_path", "").strip().endswith(".py"):
                # 按 file_path 加载，元数据优先类发现（兼容历史类名）
                comp_type_derived = (
                    "export" if comp_name.endswith("_export") else comp_name
                )
                try:
                    Klass = self.component_loader.load_python_component_from_path(
                        selected_version.file_path,
                        version_id=selected_version.id,
                        platform=platform,
                        component_type=comp_type_derived,
                    )
                    comp_type = getattr(Klass, "component_type", "export" if "_export" in comp_name else "login")
                    plat = getattr(Klass, "platform", platform)
                    component = {
                        "name": comp_name,
                        "platform": plat,
                        "type": comp_type,
                        "data_domain": getattr(Klass, "data_domain", None),
                        "_params": params or {},
                        "_python_component_class": Klass,
                        "_version_id": selected_version.id,
                        "_version_number": selected_version.version,
                    }
                    return component
                except Exception as e:
                    logger.warning(f"Failed to load from file_path {getattr(selected_version, 'file_path')}: {e}, falling back")

            if selected_version and getattr(selected_version, "file_path", "").strip().endswith(".yaml"):
                # 版本表仍存 .yaml 路径时，按组件名尝试 Python 组件（YAML 已迁离）
                logger.debug(f"Version file_path is .yaml, loading Python component: {platform}/{comp_name}")
                component = self.component_loader.build_component_dict_from_python(
                    platform, comp_name, params
                )
                if component:
                    component["_version_id"] = selected_version.id
                    component["_version_number"] = selected_version.version
                    return component

            # 无版本或默认：仅 Python 组件
            component = self.component_loader.build_component_dict_from_python(
                platform, comp_name, params
            )
            if component:
                if selected_version:
                    component["_version_id"] = selected_version.id
                    component["_version_number"] = selected_version.version
                return component
            raise FileNotFoundError(
                f"Python component not found: {component_name} "
                f"(expected modules/platforms/{platform}/components/{comp_name}.py)"
            )

        except Exception as e:
            logger.warning(f"Failed to use version service for {component_name}: {e}, falling back to default")
            component = self.component_loader.build_component_dict_from_python(
                platform, comp_name, params
            )
            if component:
                return component
            raise FileNotFoundError(
                f"Python component not found: {component_name} "
                f"(expected modules/platforms/{platform}/components/{comp_name}.py)"
            )
    
    def _load_execution_order(self, platform: str) -> Optional[List[Dict]]:
        """
        加载平台执行顺序配置(Phase 7.2优化)。
        迁离 YAML：从 Python 模块 execution_order 读取，不再读 execution_order.yaml。
        """
        try:
            from modules.apps.collection_center.execution_order import get_execution_order
            execution_seq = get_execution_order(platform)
            if execution_seq:
                logger.info(f"Loaded execution order for {platform}: {len(execution_seq)} components")
            return execution_seq
        except Exception as e:
            logger.warning(f"Failed to load execution order for {platform}: {e}")
        return None
    
    def _get_default_execution_order(self) -> List[Dict]:
        """
        获取硬编码的默认执行顺序(向后兼容)
        
        Returns:
            默认执行顺序列表
        """
        return [
            {'component': 'login', 'required': True, 'index': 0},
            {'component': 'export', 'required': True, 'index': 1},
        ]
    
    def _evaluate_condition(self, condition: Optional[str], params: Dict[str, Any]) -> bool:
        """
        评估条件表达式(Phase 7.2优化)
        
        Args:
            condition: 条件字符串(如 "{{not account.has_multiple_shops}}")
            params: 参数字典
        
        Returns:
            True表示条件满足,False表示不满足
        """
        if not condition:
            return True
        
        try:
            # 简单的变量替换和评估
            # TODO: 实现更完整的表达式评估器
            
            # 替换变量
            import re
            def replace_var(match):
                var_path = match.group(1).strip()
                
                # 处理 not 运算符
                negate = False
                if var_path.startswith('not '):
                    negate = True
                    var_path = var_path[4:].strip()
                
                # 获取变量值
                parts = var_path.split('.')
                value = params
                for part in parts:
                    if isinstance(value, dict):
                        value = value.get(part)
                    else:
                        value = None
                    if value is None:
                        break
                
                # 应用 not
                if negate:
                    value = not value
                
                return str(value).lower() if isinstance(value, bool) else str(value)
            
            evaluated = re.sub(r'\{\{(.+?)\}\}', replace_var, condition)
            
            # 评估布尔值
            if evaluated.lower() in ('true', '1', 'yes'):
                return True
            elif evaluated.lower() in ('false', '0', 'no', 'none'):
                return False
            
            return bool(evaluated)
        
        except Exception as e:
            logger.warning(f"Failed to evaluate condition '{condition}': {e}")
            return True  # 默认执行
    
    async def start_browser(self, debug_mode: bool = False):
        """
        启动浏览器(v4.7.0 - 环境感知配置)
        
        根据环境自动选择有头/无头模式:
        - 开发环境:默认有头模式(便于观察)
        - 生产环境:自动无头模式(适合Docker)
        - 调试模式:强制有头模式(覆盖生产环境配置)
        
        Args:
            debug_mode: 调试模式(临时启用有头浏览器)
            
        Returns:
            tuple: (playwright, browser, context)
        """
        from playwright.async_api import async_playwright
        from backend.utils.config import get_settings
        
        settings = get_settings()
        browser_config = settings.browser_config.copy()
        
        # v4.7.0: 调试模式覆盖(生产环境临时有头)
        if debug_mode:
            browser_config['headless'] = False
            logger.info("Debug mode enabled: forcing headful browser")
        
        logger.info(f"Starting browser: environment={settings.ENVIRONMENT}, headless={browser_config['headless']}, slow_mo={browser_config.get('slow_mo', 0)}")
        
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(
            **enforce_official_playwright_browser(browser_config)
        )
        
        # 创建浏览器上下文(反检测指纹)；下载路径由组件通过 download.save_as() 指定，不传 downloads_path
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            accept_downloads=True,
        )
        
        return playwright, browser, context
    
    async def execute(
        self,
        task_id: str,
        platform: str,
        account_id: str,
        account: Dict[str, Any],
        data_domains: List[str],
        date_range: Dict[str, str],
        granularity: str,
        page = None,  # Playwright Page对象(兼容旧调用; 推荐传 browser 由执行器自建 context)
        context: TaskContext = None,  # 用于恢复任务
        sub_domains: Optional[List[str]] = None,  # v4.7.0: 子域数组
        debug_mode: bool = False,  # v4.7.0: 调试模式
        browser = None,  # 推荐: Playwright Browser 对象, 执行器自建带指纹与会话的 context
        proxy: Optional[Dict[str, str]] = None,  # 代理预留, 当前不注入
        runtime_manifests: Optional[Dict[str, Any]] = None,
    ) -> CollectionResult:
        """
        执行采集任务(v4.7.0 - 任务粒度优化)

        v4.7.0 更新:
        - 支持子域数组循环(sub_domains)
        - 支持部分成功机制(单域失败不影响其他域)
        - 实时更新进度字段(completed_domains, failed_domains)
        - 一次登录后循环采集所有域(浏览器复用)
        - 会话与指纹: 按 account_id 持久化/复用会话、按账号固定指纹(DeviceFingerprintManager)

        Args:
            task_id: 任务ID
            platform: 平台代码(shopee/tiktok/miaoshou)
            account_id: 账号ID
            account: 账号信息(包含username, password等)
            data_domains: 数据域列表
            date_range: 日期范围 {"start": "2025-01-01", "end": "2025-01-31"}
            granularity: 粒度(daily/weekly/monthly)
            page: Playwright Page对象(若传 browser 则忽略; 否则从 page 取 browser 后自建 context)
            context: 任务上下文(用于恢复任务)
            sub_domains: 子域数组(v4.7.0)
            debug_mode: 调试模式(v4.7.0,仅用于日志记录)
            browser: 推荐传入, 执行器自建带指纹与可选会话的 context
            proxy: 代理预留, 当前不向 context 注入

        Returns:
            CollectionResult: 采集结果
        """
        start_time = datetime.now()

        # 1.0 统一约定: 规范化 account_id, 决定是否使用按账号会话/指纹
        session_owner_id, shop_account_id, use_account_session_fingerprint = _resolve_session_scope(account_id, account)
        if not use_account_session_fingerprint or not session_owner_id:
            unresolved_shop_account_id = str(
                shop_account_id
                or account_id
                or (account or {}).get("shop_account_id")
                or (account or {}).get("account_id")
                or ""
            ).strip() or "unknown"
            raise ValueError(
                f"Missing main_account_id for collection execution: shop_account_id={unresolved_shop_account_id}"
            )

        normalized_sub_domains = normalize_domain_subtypes(
            data_domains=data_domains,
            sub_domains=sub_domains,
        )
        normalized_date_range = normalize_collection_date_range(date_range)
        total_domains_count = count_collection_targets(data_domains, normalized_sub_domains)
        runtime_account = _build_runtime_account(platform, account)

        logger.info(f"Task {task_id}: Starting collection for {total_domains_count} domains (debug_mode={debug_mode}, use_account_session_fingerprint={use_account_session_fingerprint})")

        # 创建或恢复任务上下文(使用规范化后的 account_id)
        if context is None:
            context = TaskContext(
                task_id=task_id,
                platform=platform,
                account_id=shop_account_id or account_id,
                data_domains=data_domains,
                date_range=normalized_date_range,
                granularity=granularity,
                sub_domains=normalized_sub_domains,
            )
        else:
            context.account_id = shop_account_id or context.account_id

        self._task_contexts[task_id] = context

        task_download_dir = self.downloads_dir / task_id
        task_download_dir.mkdir(parents=True, exist_ok=True)
        runtime_account = _build_runtime_account(platform, account)

        step_popup_handler = StepPopupHandler(self.popup_handler, platform)

        # 加载会话与指纹(仅当 use_account_session_fingerprint 时)
        storage_state: Optional[Dict[str, Any]] = None
        reused_session = False
        if use_account_session_fingerprint and session_owner_id:
            try:
                session_data = await _load_or_bootstrap_session_async(
                    platform,
                    session_owner_id,
                    runtime_account,
                )
                if session_data and isinstance(session_data.get("storage_state"), dict):
                    storage_state = session_data["storage_state"]
                    reused_session = True
                    logger.info("Task %s: session loaded for %s/%s (reused_session=True)", task_id, platform, session_owner_id)
                else:
                    if session_data is None:
                        logger.debug("Task %s: no valid session for %s/%s, will full login", task_id, platform, session_owner_id)
                    else:
                        logger.warning("Task %s: session_data missing storage_state, will full login", task_id)
            except Exception as e:
                logger.warning("Task %s: load_session failed: %s, will full login", task_id, e)

        if use_account_session_fingerprint and session_owner_id:
            try:
                fp_options = await _get_fingerprint_context_options_async(platform, session_owner_id, account, proxy=proxy)
                context_options = _build_playwright_context_options_from_fingerprint(fp_options)
            except Exception as e:
                logger.warning("Task %s: get fingerprint failed: %s, fallback to global context args", task_id, e)
                from modules.apps.collection_center.browser_config_helper import get_browser_context_args
                context_options = get_browser_context_args()
        else:
            from modules.apps.collection_center.browser_config_helper import get_browser_context_args
            context_options = get_browser_context_args()

        context_options.setdefault("accept_downloads", True)
        if storage_state:
            context_options["storage_state"] = storage_state

        params = _build_runtime_task_params(
            task_id=task_id,
            account=runtime_account,
            platform=platform,
            granularity=granularity,
            normalized_date_range=normalized_date_range,
            task_download_dir=task_download_dir,
            screenshot_dir=self.screenshots_dir / task_id,
            reused_session=reused_session,
        )
        params["main_account_id"] = session_owner_id
        if shop_account_id:
            params["shop_account_id"] = shop_account_id
        session_platform = platform
        session_account_id = session_owner_id

        # 获取 browser: 优先使用入参 browser, 否则从 page 取(后关闭传入的 page/context)
        browser_instance = browser
        page_context_to_close = None
        if browser_instance is None and page is not None:
            try:
                browser_instance = page.context.browser
                page_context_to_close = page.context
            except Exception as e:
                logger.warning("Could not get browser from page: %s", e)
        if browser_instance is None:
            raise ValueError("execute() requires either browser= or page= to be provided")

        # 执行器统一建 context: 由执行器创建带指纹与可选会话的 context
        play_context = await browser_instance.new_context(**context_options)
        page = await play_context.new_page()
        params["reused_session"] = reused_session
        adapter = None
        if runtime_manifests is None:
            adapter = create_adapter(
                platform=platform,
                account=runtime_account,
                config=params,
            )
        if context.current_component_index == 0 and not params.get("_main_account_shared_state_prepared"):
            async def _coordinated_login():
                return await self._execute_shared_login_phase(
                    task_id=task_id,
                    platform=platform,
                    account=runtime_account,
                    params=params,
                    context=context,
                    browser=browser,
                    play_context=play_context,
                    page=page,
                    adapter=adapter,
                    runtime_manifests=runtime_manifests,
                    session_platform=session_platform,
                    session_account_id=session_account_id,
                    save_session_after_login=use_account_session_fingerprint and bool(session_owner_id),
                    start_time=start_time,
                    total_domains_count=total_domains_count,
                )

            play_context, page, login_result = await self._run_with_main_account_session_lock(
                task_id=task_id,
                platform=platform,
                main_account_id=session_owner_id,
                operation=_coordinated_login,
            )
            params["_main_account_shared_state_prepared"] = True
            if isinstance(login_result, CollectionResult):
                return login_result

        if page_context_to_close is not None:
            try:
                await page_context_to_close.close()
            except Exception as e:
                logger.debug("Close passed-in context: %s", e)

        try:
            if self.use_python_components:
                return await self._execute_with_python_components(
                    task_id=task_id,
                    platform=platform,
                    account=runtime_account,
                    params=params,
                    context=context,
                    browser=browser_instance,
                    play_context=play_context,
                    page=page,
                    step_popup_handler=step_popup_handler,
                    task_download_dir=task_download_dir,
                    data_domains=data_domains,
                    sub_domains=sub_domains,
                    total_domains_count=total_domains_count,
                    start_time=start_time,
                    save_session_after_login=use_account_session_fingerprint and bool(session_owner_id),
                    session_platform=platform,
                    session_account_id=session_owner_id,
                    runtime_manifests=runtime_manifests,
                )

            # ===== 以下为旧的 YAML 组件执行流程(将被废弃) =====
            
            # 检查是否需要跳过登录(恢复任务)
            if context.current_component_index == 0:
                # 1. 执行登录组件([*] Phase 9.4: 使用版本选择) + 步骤可观测成对打点
                await self._update_status(task_id, 5, "正在加载登录组件...")
                await self._check_cancelled(task_id)
                login_start_time = datetime.now()
                await self._update_status(
                    task_id, 5, "登录开始",
                    details={"step_id": "login", "component": "login", "data_domain": None}
                )
                login_component = self._load_component_with_version(
                    f"{platform}/login",
                    params,
                    enable_ab_test=True  # 启用A/B测试
                )
                await self._update_status(task_id, 10, "正在登录...")
                login_success = False
                try:
                    login_success = await self._execute_component(page, login_component, step_popup_handler)
                    duration_ms = int((datetime.now() - login_start_time).total_seconds() * 1000)
                    await self._update_status(
                        task_id, 10, "登录结束",
                        details={"step_id": "login", "component": "login", "success": login_success, "duration_ms": duration_ms}
                    )
                except Exception as e:
                    duration_ms = int((datetime.now() - login_start_time).total_seconds() * 1000)
                    await self._update_status(
                        task_id, 10, "登录失败",
                        details={"step_id": "login", "component": "login", "success": False, "duration_ms": duration_ms, "error": str(e)}
                    )
                    raise
                if not login_success:
                    raise StepExecutionError("登录组件执行失败,成功标准验证未通过")
                logger.info(f"Task {task_id}: Login component completed successfully")
                context.current_component_index = 1
            
            # Phase 9 架构简化(方案B):导出组件自包含
            # 执行顺序简化为: Login -> Export(循环各数据域)
            # 
            # 导出组件现在包含完整流程:
            # - 导航到目标页面
            # - 切换店铺(如需要)
            # - 选择日期范围
            # - 设置筛选条件
            # - 触发导出并下载文件
            #
            # 导出组件可以通过 component_call 调用子组件(date_picker, shop_switch, filters)
            # 执行器只关心 action 字段,不理解业务含义
            
            context.current_component_index = 1  # 登录完成后直接进入导出阶段
            
            # 2. 循环执行各数据域导出(v4.7.0: 支持子域和部分成功)
            domain_index = 0
            for i, domain in enumerate(data_domains):
                # 跳过已完成的数据域(恢复任务)
                if i < context.current_data_domain_index:
                    continue
                
                context.current_data_domain_index = i
                
                # v4.7.0: 如果当前数据域有子域,循环采集每个子域
                sub_domain_list = normalized_sub_domains.get(domain) or [None]
                
                for sub_domain in sub_domain_list:
                    # v4.7.0: 构造完整域名(domain:sub_domain)
                    full_domain = f"{domain}:{sub_domain}" if sub_domain else domain
                    
                    # 跳过已完成的域(恢复任务)
                    if full_domain in context.completed_domains:
                        continue
                    
                    domain_index += 1
                    progress = 20 + int(70 * domain_index / total_domains_count)
                    await self._update_status(task_id, progress, f"正在采集 {full_domain}...")
                    await self._check_cancelled(task_id)
                    domain_export_start = datetime.now()
                    await self._update_status(
                        task_id, progress, f"采集 {full_domain} 开始",
                        current_domain=full_domain,
                        details={"step_id": f"export_{full_domain.replace(':', '_')}", "component": f"{domain}_export", "data_domain": full_domain}
                    )
                    # 更新参数中的数据域
                    params['params']['data_domain'] = domain
                    if sub_domain:
                        params['params']['sub_domain'] = sub_domain
                    
                    try:
                        # 加载并执行导出组件
                        component_name = f"{platform}/{domain}_export"
                        if sub_domain:
                            # 尝试子域特定组件,如 shopee/services_agent_export([*] Phase 9.4: 版本选择)
                            component_name = f"{platform}/{domain}_{sub_domain}_export"
                            try:
                                export_component = self._load_component_with_version(component_name, params, enable_ab_test=True)
                            except FileNotFoundError:
                                # 回退到通用组件
                                component_name = f"{platform}/{domain}_export"
                                export_component = self._load_component_with_version(component_name, params, enable_ab_test=True)
                        else:
                            export_component = self._load_component_with_version(component_name, params, enable_ab_test=True)
                        
                        file_path = await self._execute_export_component(
                            page, 
                            export_component, 
                            step_popup_handler,
                            task_download_dir
                        )
                        
                        file_path = self._ensure_export_complete(file_path) if file_path else file_path
                        if file_path:
                            context.collected_files.append(file_path)
                        # v4.7.0: 标记为成功 + 步骤结束打点
                        context.completed_domains.append(full_domain)
                        duration_ms = int((datetime.now() - domain_export_start).total_seconds() * 1000)
                        await self._update_status(
                            task_id, progress, f"采集 {full_domain} 成功",
                            current_domain=full_domain,
                            details={"step_id": f"export_{full_domain.replace(':', '_')}", "component": f"{domain}_export", "data_domain": full_domain, "success": True, "duration_ms": duration_ms}
                        )
                        logger.info(f"Task {task_id}: Successfully collected {full_domain}")
                    
                    except FileNotFoundError as e:
                        # 组件不存在,标记为失败但继续 + 步骤结束打点
                        error_msg = f"Export component not found: {component_name}"
                        duration_ms = int((datetime.now() - domain_export_start).total_seconds() * 1000)
                        await self._update_status(
                            task_id, progress, f"采集 {full_domain} 失败",
                            current_domain=full_domain,
                            details={"step_id": f"export_{full_domain.replace(':', '_')}", "component": f"{domain}_export", "data_domain": full_domain, "success": False, "duration_ms": duration_ms, "error": error_msg}
                        )
                        logger.warning(f"Task {task_id}: {error_msg}")
                        context.failed_domains.append({
                            "domain": full_domain,
                            "error": error_msg
                        })
                        continue
                    
                    except VerificationRequiredError as e:
                        duration_ms = int((datetime.now() - domain_export_start).total_seconds() * 1000)
                        await self._update_status(
                            task_id, progress, f"采集 {full_domain} 暂停(验证码)",
                            current_domain=full_domain,
                            details={"step_id": f"export_{full_domain.replace(':', '_')}", "component": f"{domain}_export", "data_domain": full_domain, "success": False, "duration_ms": duration_ms, "error": f"需要验证码: {e.verification_type}"}
                        )
                        value = await self._wait_verification_and_continue(
                            task_id, e.verification_type, e.screenshot_path, page, params, None, is_login=False, domain_info=full_domain
                        )
                        if value is None:
                            context.failed_domains.append({"domain": full_domain, "error": "验证码等待超时"})
                            return CollectionResult(
                                task_id=task_id,
                                status="failed",
                                files_collected=len(context.collected_files),
                                collected_files=context.collected_files,
                                error_message="验证码等待超时",
                                duration_seconds=(datetime.now() - start_time).total_seconds(),
                                completed_domains=context.completed_domains,
                                failed_domains=context.failed_domains,
                                total_domains=total_domains_count,
                            )
                        if (e.verification_type or "").lower() in ("otp", "sms", "email_code"):
                            params.setdefault("params", {})["otp"] = value
                        else:
                            params.setdefault("params", {})["captcha_code"] = value
                        try:
                            file_path = await self._execute_export_component(page, export_component, step_popup_handler, task_download_dir)
                            file_path = self._ensure_export_complete(file_path) if file_path else file_path
                            if file_path:
                                context.collected_files.append(file_path)
                            context.completed_domains.append(full_domain)
                        except Exception as retry_e:
                            context.failed_domains.append({"domain": full_domain, "error": str(retry_e)})
                        continue

                    except Exception as e:
                        # v4.7.0: 部分成功机制 - 单域失败不影响其他域 + 步骤结束打点
                        error_msg = f"{type(e).__name__}: {str(e)}"
                        duration_ms = int((datetime.now() - domain_export_start).total_seconds() * 1000)
                        await self._update_status(
                            task_id, progress, f"采集 {full_domain} 失败",
                            current_domain=full_domain,
                            details={"step_id": f"export_{full_domain.replace(':', '_')}", "component": f"{domain}_export", "data_domain": full_domain, "success": False, "duration_ms": duration_ms, "error": error_msg}
                        )
                        logger.error(f"Task {task_id}: Failed to collect {full_domain} - {error_msg}")
                        context.failed_domains.append({
                            "domain": full_domain,
                            "error": error_msg
                        })
                        continue
            
            # 4. 处理采集到的文件 + 步骤可观测成对打点
            file_process_start = datetime.now()
            await self._update_status(
                task_id, 95, "文件处理开始",
                details={"step_id": "file_process", "component": "file_process", "data_domain": None}
            )
            processed_files = await self._process_files(
                context.collected_files, 
                platform, 
                data_domains, 
                granularity,
                account=account,
                date_range=date_range
            )
            duration_ms = int((datetime.now() - file_process_start).total_seconds() * 1000)
            await self._update_status(
                task_id, 95, "文件处理结束",
                details={"step_id": "file_process", "component": "file_process", "success": True, "duration_ms": duration_ms}
            )
            
            # 5. v4.7.0: 根据成功/失败情况决定最终状态
            duration = (datetime.now() - start_time).total_seconds()
            
            completed_count = len(context.completed_domains)
            failed_count = len(context.failed_domains)
            
            if completed_count == 0 and failed_count > 0:
                # 全部失败
                final_status = "failed"
                final_message = f"采集失败,0/{total_domains_count} 个域成功"
            elif failed_count > 0:
                # 部分成功
                final_status = "partial_success"
                final_message = f"部分成功,{completed_count}/{total_domains_count} 个域成功,{failed_count} 个失败"
            else:
                # 全部成功
                final_status = "completed"
                final_message = f"采集完成,共采集 {len(processed_files)} 个文件"
            
            await self._update_status(task_id, 100, final_message)
            
            logger.info(f"Task {task_id}: {final_status} - completed={completed_count}, failed={failed_count}, files={len(processed_files)}")
            
            # v4.7.4: 完成状态通过 HTTP 轮询获取,不再使用 WebSocket
            
            # 清理任务上下文
            self._task_contexts.pop(task_id, None)
            
            return CollectionResult(
                task_id=task_id,
                status=final_status,
                files_collected=len(processed_files),
                collected_files=processed_files,
                duration_seconds=duration,
                completed_domains=context.completed_domains,
                failed_domains=context.failed_domains,
                total_domains=total_domains_count,
            )

        except TaskCancelledError:
            logger.info(f"Task {task_id} was cancelled")
            
            # v4.7.4: 取消状态通过 HTTP 轮询获取,不再使用 WebSocket
            
            return CollectionResult(
                task_id=task_id,
                status="cancelled",
                files_collected=len(context.collected_files),
                collected_files=context.collected_files,
                error_message="任务已取消",
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                completed_domains=context.completed_domains,
                failed_domains=context.failed_domains,
                total_domains=total_domains_count,
            )
        
        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
            
            # 保存错误截图
            try:
                if page:
                    screenshot_path = self.screenshots_dir / task_id / "error.png"
                    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
                    await page.screenshot(path=str(screenshot_path))
            except Exception as screenshot_error:
                logger.error(f"Failed to save error screenshot: {screenshot_error}")
            
            # v4.7.4: 失败状态通过 HTTP 轮询获取,不再使用 WebSocket
            
            return CollectionResult(
                task_id=task_id,
                status="failed",
                files_collected=len(context.collected_files),
                collected_files=context.collected_files,
                error_message=str(e),
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                completed_domains=context.completed_domains,
                failed_domains=context.failed_domains,
                total_domains=total_domains_count,
            )
        finally:
            try:
                if play_context is not None:
                    await play_context.close()
            except Exception as _e:
                logger.debug("Close play_context: %s", _e)

    def _record_version_usage(self, component: Dict[str, Any], success: bool) -> None:
        """
        记录版本使用情况(Phase 9.4)
        
        Args:
            component: 组件配置
            success: 是否成功
        """
        version_id = component.get('_version_id')
        version_number = component.get('_version_number')
        component_name = component.get('name', 'unknown')
        
        if not version_id or not version_number:
            # 没有版本信息,跳过记录
            return
        
        try:
            version_service = _get_version_service()
            if version_service:
                # 从组件名称中提取实际的组件路径(移除版本号)
                # 例如:shopee_login_v1.0 -> shopee/login
                base_name = component_name.rsplit('_v', 1)[0] if '_v' in component_name else component_name
                base_name = base_name.replace('_', '/')
                
                version_service.record_usage(
                    component_name=base_name,
                    version=version_number,
                    success=success
                )
                
                logger.debug(
                    f"Recorded version usage: {base_name} v{version_number}, "
                    f"success={success}"
                )
        except Exception as e:
            logger.warning(f"Failed to record version usage: {e}")
    
    async def _execute_python_component(
        self,
        page,
        adapter: Optional[PythonComponentAdapter],
        component_type: str,
        params: Dict[str, Any] = None,
        component: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        使用 Python 组件执行。当 component 含 _python_component_class 时直接使用该类，
        否则通过 adapter 按 component_type 加载。
        """
        params = params or {}
        Klass = (component or {}).get("_python_component_class")

        if Klass:
            try:
                logger.info(f"[PythonComponent] Executing: {component_type} (from file_path)")
                from modules.components.base import ExecutionContext
                account = params.get("account", params)
                config = params.get("params", params) if isinstance(params.get("params"), dict) else params
                ctx = ExecutionContext(
                    platform=(component or {}).get("platform", ""),
                    account=account,
                    config=config,
                )
                instance = Klass(ctx)
                result = await instance.run(page)
                if result.success:
                    logger.info(f"[PythonComponent] {component_type} completed successfully")
                    if getattr(result, "file_path", None):
                        logger.info(f"[PythonComponent] File saved: {result.file_path}")
                    return True
                else:
                    logger.error(f"[PythonComponent] {component_type} failed: {result.message}")
                    return False
            except VerificationRequiredError:
                raise
            except Exception as e:
                logger.error(f"[PythonComponent] {component_type} exception: {e}")
                return False

        if not adapter:
            logger.error("[PythonComponent] No _python_component_class and no adapter")
            return False
        try:
            logger.info(f"[PythonComponent] Executing: {component_type} (via adapter)")
            result = await adapter.execute_component(component_type, page, params)
            if result.success:
                logger.info(f"[PythonComponent] {component_type} completed successfully")
                if result.file_path:
                    logger.info(f"[PythonComponent] File saved: {result.file_path}")
                return True
            else:
                logger.error(f"[PythonComponent] {component_type} failed: {result.message}")
                return False
        except VerificationRequiredError:
            raise
        except Exception as e:
            logger.error(f"[PythonComponent] {component_type} exception: {e}")
            return False

    def _load_runtime_manifest_component_class(self, manifest: Any):
        """Load a Python component class from a stable runtime manifest."""
        if manifest is None:
            raise StepExecutionError(
                "runtime manifest is required for stable component execution"
            )

        file_path = getattr(manifest, "file_path", None) or manifest.get("file_path")
        platform = getattr(manifest, "platform", None) or manifest.get("platform")
        component_type = getattr(manifest, "component_type", None) or manifest.get(
            "component_type"
        )

        if not file_path or not platform or not component_type:
            raise StepExecutionError(
                "runtime manifest missing file_path/platform/component_type"
            )

        return self.component_loader.load_python_component_from_path(
            file_path,
            platform=platform,
            component_type=component_type,
        )

    async def _run_runtime_manifest_component(
        self,
        *,
        page,
        manifest: Any,
        account: Dict[str, Any],
        config: Dict[str, Any],
        run_args: Optional[List[Any]] = None,
        run_kwargs: Optional[Dict[str, Any]] = None,
    ):
        """Execute a component resolved from a stable runtime manifest."""
        from modules.components.base import ExecutionContext

        component_class = self._load_runtime_manifest_component_class(manifest)
        platform = getattr(manifest, "platform", None) or manifest.get("platform")
        ctx = ExecutionContext(
            platform=platform,
            account=account,
            config=config,
        )
        component = component_class(ctx)
        args = run_args or []
        kwargs = run_kwargs or {}
        return await component.run(page, *args, **kwargs)

    async def _wait_verification_and_continue(
        self,
        task_id: str,
        verification_type: str,
        screenshot_path: Optional[str],
        page,
        params: Dict[str, Any],
        adapter,
        is_login: bool,
        domain_info: Optional[str] = None,
    ) -> Optional[str]:
        """
        验证码分支：调用回调持久化并阻塞等待；返回用户回传的值或 None(超时)。
        不负责填入页面，由调用方根据返回值决定是填入后重试组件还是置失败。
        """
        if not self.verification_required_callback:
            return None
        try:
            value = await self.verification_required_callback(task_id, verification_type, screenshot_path)
            return value
        except Exception as e:
            logger.error(f"Verification callback failed for task {task_id}: {e}")
            return None

    @staticmethod
    def _requires_headful_login_fallback(verification_type: str | None) -> bool:
        return verification_input_mode(verification_type) == "manual_continue"

    async def _prime_runtime_page_for_login_gate(self, page: Any, platform: str, account: Dict[str, Any]) -> None:
        current_url = str(getattr(page, "url", "") or "").strip().lower()
        if current_url and current_url != "about:blank":
            return

        login_url = get_platform_login_entry(platform)
        if not login_url:
            return

        await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
        if hasattr(page, "wait_for_timeout"):
            await page.wait_for_timeout(800)

    async def _recreate_runtime_page_with_saved_session(
        self,
        *,
        browser,
        old_context,
        platform: str,
        account: Dict[str, Any],
        account_id: str,
    ):
        storage_state = None
        if account_id:
            session_data = await _load_or_bootstrap_session_async(
                platform,
                account_id,
                account,
            )
            if session_data and isinstance(session_data.get("storage_state"), dict):
                storage_state = session_data["storage_state"]

        if account_id:
            fp_options = await _get_fingerprint_context_options_async(platform, account_id, account)
            context_options = _build_playwright_context_options_from_fingerprint(fp_options)
        else:
            from modules.apps.collection_center.browser_config_helper import get_browser_context_args

            context_options = get_browser_context_args()

        context_options.setdefault("accept_downloads", True)
        if storage_state:
            context_options["storage_state"] = storage_state
        if not context_options.get("viewport"):
            context_options["viewport"] = {"width": 1920, "height": 1080}
        if "locale" not in context_options:
            context_options["locale"] = "zh-CN"

        try:
            await old_context.close()
        except Exception as e:
            logger.debug("Close old runtime context before session recreation failed: %s", e)

        new_context = await browser.new_context(**context_options)
        new_page = await new_context.new_page()
        await self._prime_runtime_page_for_login_gate(new_page, platform, account)
        return new_context, new_page

    async def _run_headful_login_fallback(
        self,
        *,
        task_id: str,
        platform: str,
        account: Dict[str, Any],
        params: Dict[str, Any],
        browser,
        old_context,
        session_platform: str,
        session_account_id: str,
        runtime_manifests: Optional[Dict[str, Any]] = None,
    ):
        from playwright.async_api import async_playwright

        account_id = session_account_id or str(account.get("account_id") or "").strip()

        async with async_playwright() as playwright:
            headed_browser = await playwright.chromium.launch(
                **enforce_official_playwright_browser({"headless": False, "args": ["--start-maximized"]})
            )
            try:
                if account_id:
                    fp_options = await _get_fingerprint_context_options_async(platform, account_id, account)
                    context_options = _build_playwright_context_options_from_fingerprint(fp_options)
                else:
                    from modules.apps.collection_center.browser_config_helper import get_browser_context_args

                    context_options = get_browser_context_args()
                context_options.setdefault("accept_downloads", True)
                context_options["viewport"] = None
                context_options.setdefault("locale", "zh-CN")

                headed_context = await headed_browser.new_context(**context_options)
                try:
                    headed_page = await headed_context.new_page()
                    while True:
                        try:
                            if runtime_manifests is not None:
                                login_manifest = runtime_manifests.get("login")
                                login_result = await self._run_runtime_manifest_component(
                                    page=headed_page,
                                    manifest=login_manifest,
                                    account=account,
                                    config=params,
                                )
                                login_success = bool(getattr(login_result, "success", False))
                            else:
                                adapter = create_adapter(
                                    platform=platform,
                                    account=account,
                                    config=params,
                                )
                                login_success = await self._execute_python_component(
                                    page=headed_page,
                                    adapter=adapter,
                                    component_type="login",
                                    params=params,
                                )
                            if not login_success:
                                return False, old_context, None, "failed"
                            break
                        except VerificationRequiredError as e:
                            value = await self._wait_verification_and_continue(
                                task_id,
                                e.verification_type,
                                e.screenshot_path,
                                headed_page,
                                params,
                                None,
                                is_login=True,
                            )
                            if value is None:
                                return False, old_context, None, "timeout"
                            apply_verification_result_to_params(
                                params,
                                verification_type=e.verification_type,
                                value=value,
                            )
                            continue

                    await self._ensure_login_gate_ready(headed_page, platform)
                    if session_platform and session_account_id:
                        storage_state = await headed_context.storage_state()
                        await _save_session_async(session_platform, session_account_id, storage_state)
                finally:
                    await headed_context.close()
            finally:
                await headed_browser.close()

        if browser is None:
            return False, old_context, None

        new_context, new_page = await self._recreate_runtime_page_with_saved_session(
            browser=browser,
            old_context=old_context,
            platform=platform,
            account=account,
            account_id=account_id,
        )
        return True, new_context, new_page, "success"

    async def _execute_with_python_components(
        self,
        task_id: str,
        platform: str,
        account: Dict[str, Any],
        params: Dict[str, Any],
        context: TaskContext,
        browser,
        play_context,
        page,
        step_popup_handler: StepPopupHandler,
        task_download_dir: Path,
        data_domains: List[str],
        sub_domains: Optional[List[str]],
        total_domains_count: int,
        start_time: datetime,
        save_session_after_login: bool = False,
        session_platform: str = "",
        session_account_id: str = "",
        runtime_manifests: Optional[Dict[str, Any]] = None,
    ) -> CollectionResult:
        """
        v4.8.0: 使用 Python 组件执行采集流程

        执行顺序:
        1. Login(登录组件); 若 save_session_after_login 则在成功后保存会话
        2. Loop: Export(循环执行各数据域的导出组件)
        """
        adapter = None
        if runtime_manifests is None:
            adapter = create_adapter(
                platform=platform,
                account=account,
                config=params,
            )

        # 1. 执行登录组件( params 中已含 reused_session 标记)；支持验证码暂停→回传→同一 page 继续
        if context.current_component_index == 0 and not params.get("_main_account_shared_state_prepared"):
            await self._update_status(task_id, 5, "正在登录...")
            await self._check_cancelled(task_id)
            await self.popup_handler.close_popups(page, platform=platform)

            login_success = False
            while True:
                try:
                    if runtime_manifests is not None:
                        login_manifest = runtime_manifests.get("login")
                        login_result = await self._run_runtime_manifest_component(
                            page=page,
                            manifest=login_manifest,
                            account=account,
                            config=params,
                        )
                        login_success = bool(getattr(login_result, "success", False))
                    else:
                        login_success = await self._execute_python_component(
                            page=page,
                            adapter=adapter,
                            component_type="login",
                            params=params,
                        )
                    break
                except VerificationRequiredError as e:
                    if self._requires_headful_login_fallback(e.verification_type):
                        fallback_result = await self._run_headful_login_fallback(
                            task_id=task_id,
                            platform=platform,
                            account=account,
                            params=params,
                            browser=browser,
                            old_context=play_context,
                            session_platform=session_platform,
                            session_account_id=session_account_id,
                            runtime_manifests=runtime_manifests,
                        )
                        if len(fallback_result) == 4:
                            login_success, play_context, page, fallback_outcome = fallback_result
                        else:
                            login_success, play_context, page = fallback_result
                            fallback_outcome = "success" if login_success else "failed"
                        if not login_success and fallback_outcome == "timeout":
                            return self._build_verification_timeout_result(
                                task_id=task_id,
                                verification_type=e.verification_type,
                                context=context,
                                start_time=start_time,
                                total_domains_count=total_domains_count,
                            )
                        break
                    value = await self._wait_verification_and_continue(
                        task_id, e.verification_type, e.screenshot_path, page, params, adapter, is_login=True
                    )
                    if value is None:
                        return self._build_verification_timeout_result(
                            task_id=task_id,
                            verification_type=e.verification_type,
                            context=context,
                            start_time=start_time,
                            total_domains_count=total_domains_count,
                        )
                    if value is None:
                        raise StepExecutionError("验证码等待超时")
                    apply_verification_result_to_params(
                        params,
                        verification_type=e.verification_type,
                        value=value,
                    )
                    # 同一 page 继续：再次执行登录组件(组件内根据 params 中的 captcha_code/otp 填入并提交)
                    continue

            if not login_success:
                raise StepExecutionError("登录组件执行失败")

            await self._ensure_login_gate_ready(page, platform)
            logger.info(f"Task {task_id}: [Python] Login completed successfully (reused_session=%s)", params.get("reused_session", False))
            await _record_platform_shop_discovery_async(
                platform=platform,
                page=page,
                params=params,
                account=account,
                )
            if save_session_after_login and session_platform and session_account_id:
                try:
                    storage_state = await page.context.storage_state()
                    ok = await _save_session_async(session_platform, session_account_id, storage_state)
                    if ok:
                        logger.info("Task %s: session saved for %s/%s", task_id, session_platform, session_account_id)
                    else:
                        logger.warning("Task %s: session save returned False for %s/%s", task_id, session_platform, session_account_id)
                except Exception as e:
                    logger.warning("Task %s: save_session failed: %s", task_id, e)
            context.current_component_index = 1
        
        # 2. 循环执行各数据域导出
        domain_index = 0
        for i, domain in enumerate(data_domains):
            if i < context.current_data_domain_index:
                continue
            
            context.current_data_domain_index = i
            sub_domain_list = normalize_domain_subtypes(
                data_domains=data_domains,
                sub_domains=sub_domains,
            ).get(domain) or [None]
            
            for sub_domain in sub_domain_list:
                full_domain = f"{domain}:{sub_domain}" if sub_domain else domain
                
                if full_domain in context.completed_domains:
                    continue
                
                domain_index += 1
                progress = 20 + int(70 * domain_index / total_domains_count)
                await self._update_status(task_id, progress, f"正在采集 {full_domain}...")
                await self._check_cancelled(task_id)
                
                # 更新参数（域级参数通过 config 传入，组件从 self.config 读取）
                export_params = params.copy()
                export_params['params'] = {
                    **export_params.get('params', {}),
                    'data_domain': domain,
                }
                if sub_domain:
                    export_params['params']['sub_domain'] = sub_domain
                
                try:
                    # 回调更新 current_domain
                    if self.status_callback:
                        try:
                            await self.status_callback(task_id, progress, f"正在采集 {full_domain}...", full_domain)
                        except TypeError:
                            await self.status_callback(task_id, progress, f"正在采集 {full_domain}...")
                    
                    # 检查弹窗
                    await self.popup_handler.close_popups(page, platform=platform)
                    
                    # 每域用含该域参数的 config 创建 adapter，以便组件从 config 读取 data_domain/sub_domain
                    if runtime_manifests is not None:
                        export_manifest = runtime_manifests.get("exports_by_domain", {}).get(full_domain)
                        if export_manifest is None:
                            raise StepExecutionError(
                                f"runtime manifest missing for export domain {full_domain}"
                            )
                        export_result = await self._run_runtime_manifest_component(
                            page=page,
                            manifest=export_manifest,
                            account=account,
                            config=export_params,
                        )
                    else:
                        domain_adapter = create_adapter(platform=platform, account=account, config=export_params)
                        export_result = await domain_adapter.export(
                            page=page,
                            data_domain=domain,
                        )
                    
                    if export_result.success:
                        component_name = f"{platform}/{domain}_{sub_domain}_export" if sub_domain else f"{platform}/{domain}_export"
                        file_path = self._ensure_export_complete(
                            export_result.file_path,
                            component_name=component_name,
                            success_message=getattr(export_result, "message", None),
                        )
                        if file_path:
                            context.collected_files.append(file_path)
                        context.completed_domains.append(full_domain)
                        logger.info(f"Task {task_id}: [Python] Successfully collected {full_domain}")
                    else:
                        raise StepExecutionError(f"Export failed: {export_result.message}")
                
                except FileNotFoundError as e:
                    error_msg = f"Export component not found: {component_name}"
                    logger.warning(f"Task {task_id}: {error_msg}")
                    context.failed_domains.append({
                        "domain": full_domain,
                        "error": error_msg
                    })
                    continue
                
                except VerificationRequiredError as e:
                    value = await self._wait_verification_and_continue(
                        task_id, e.verification_type, e.screenshot_path, page, export_params, adapter, is_login=False, domain_info=full_domain
                    )
                    if value is None:
                        context.failed_domains.append(
                            {
                                "domain": full_domain,
                                "error": self._verification_timeout_message(e.verification_type),
                            }
                        )
                        return self._build_verification_timeout_result(
                            task_id=task_id,
                            verification_type=e.verification_type,
                            context=context,
                            start_time=start_time,
                            total_domains_count=total_domains_count,
                        )
                    if value is None:
                        context.failed_domains.append({"domain": full_domain, "error": "验证码等待超时"})
                        return CollectionResult(
                            task_id=task_id,
                            status="failed",
                            files_collected=len(context.collected_files),
                            collected_files=context.collected_files,
                            error_message="验证码等待超时",
                            duration_seconds=(datetime.now() - start_time).total_seconds(),
                            completed_domains=context.completed_domains,
                            failed_domains=context.failed_domains,
                            total_domains=total_domains_count,
                        )
                    apply_verification_result_to_params(
                        export_params,
                        verification_type=e.verification_type,
                        value=value,
                    )
                    try:
                        if runtime_manifests is not None:
                            export_manifest = runtime_manifests.get("exports_by_domain", {}).get(full_domain)
                            export_result = await self._run_runtime_manifest_component(
                                page=page,
                                manifest=export_manifest,
                                account=account,
                                config=export_params,
                            )
                        else:
                            domain_adapter = create_adapter(platform=platform, account=account, config=export_params)
                            export_result = await domain_adapter.export(page=page, data_domain=domain)
                        if export_result.success:
                            component_name = f"{platform}/{domain}_{sub_domain}_export" if sub_domain else f"{platform}/{domain}_export"
                            file_path = self._ensure_export_complete(
                                export_result.file_path,
                                component_name=component_name,
                                success_message=getattr(export_result, "message", None),
                            )
                            if file_path:
                                context.collected_files.append(file_path)
                            context.completed_domains.append(full_domain)
                            logger.info(f"Task {task_id}: [Python] Successfully collected {full_domain} (after verification)")
                        else:
                            raise StepExecutionError(export_result.message or "Export failed")
                    except Exception as retry_e:
                        context.failed_domains.append({"domain": full_domain, "error": str(retry_e)})
                    continue

                except Exception as e:
                    error_msg = f"{type(e).__name__}: {str(e)}"
                    logger.error(f"Task {task_id}: Failed to collect {full_domain} - {error_msg}")
                    context.failed_domains.append({
                        "domain": full_domain,
                        "error": error_msg
                    })
                    continue

        # 3. 处理采集到的文件
        await self._update_status(task_id, 95, "Processing files...")
        processed_files = await self._process_files(
            context.collected_files,
            platform,
            data_domains,
            params.get('params', {}).get('granularity', 'daily'),
            account=account,
            date_range=context.date_range
        )
        
        # 4. 生成最终结果
        duration = (datetime.now() - start_time).total_seconds()
        completed_count = len(context.completed_domains)
        failed_count = len(context.failed_domains)
        
        if completed_count == 0 and failed_count > 0:
            final_status = "failed"
            final_message = f"Collection failed, 0/{total_domains_count} domains succeeded"
        elif failed_count > 0:
            final_status = "partial_success"
            final_message = f"Partial success, {completed_count}/{total_domains_count} domains succeeded, {failed_count} failed"
        else:
            final_status = "completed"
            final_message = f"Collection completed, {len(processed_files)} files collected"
        
        await self._update_status(task_id, 100, final_message)
        logger.info(f"Task {task_id}: [Python] {final_status} - completed={completed_count}, failed={failed_count}, files={len(processed_files)}")
        
        self._task_contexts.pop(task_id, None)
        
        return CollectionResult(
            task_id=task_id,
            status=final_status,
            files_collected=len(processed_files),
            collected_files=processed_files,
            duration_seconds=duration,
            completed_domains=context.completed_domains,
            failed_domains=context.failed_domains,
            total_domains=total_domains_count,
        )
    
    async def _execute_component(
        self,
        page,
        component: Dict[str, Any],
        step_popup_handler: StepPopupHandler,
    ) -> bool:
        """
        执行组件中的所有步骤并验证成功标准(v4.7.0+: Phase 7.1)
        迁离 YAML：若组件含 _python_component_class 则通过 adapter 执行 Python 组件。
        """
        component_name = component.get("name", "unknown")
        component_type = component.get("type", "")

        # Python 组件：含 _python_component_class 时直接使用该类，不得再通过 adapter 按 comp_name 加载
        if component.get("_python_component_class"):
            params = component.get("_params", {})
            return await self._execute_python_component(
                page=page,
                adapter=None,
                component_type=component_type,
                params=params,
                component=component,
            )

        # Phase 11: 检测发现模式组件
        if component_type in ["date_picker", "filters"]:
            return await self._execute_discovery_component(page, component, step_popup_handler)
        
        # v4.7.0: 执行预检测
        pre_check = component.get('pre_check', [])
        if pre_check:
            pre_check_result = await self._run_pre_checks(page, component, pre_check)
            if not pre_check_result:
                logger.warning(f"Component {component_name}: Pre-check failed, skipping")
                return False
        
        steps = component.get('steps', [])
        
        # 组件执行前检查弹窗
        popup_handling = component.get('popup_handling', {})
        if popup_handling.get('check_before_steps', True):
            await self.popup_handler.close_popups(page, platform=component.get('platform'))
        
        # 执行所有步骤(v4.7.2增强:智能重试+Optional步骤处理)
        step_failed = False
        for i, step in enumerate(steps):
            step_name = step.get('action', 'unknown')
            optional = step.get('optional', False)
            max_retries = step.get('max_retries', 2)  # [*] 可配置重试次数,默认2次
            
            # 步骤执行前检查弹窗
            await step_popup_handler.before_step(page, step, component)
            
            success = False
            last_error = None
            
            # [*] 改进:支持多次重试
            for attempt in range(max_retries + 1):
                try:
                    # 执行步骤
                    await self._execute_step(page, step, component)
                    success = True
                    break  # 成功,退出重试循环
                
                except Exception as e:
                    last_error = e
                    
                    if attempt < max_retries:
                        # [*] 还有重试机会,处理弹窗后重试
                        logger.warning(
                            f"Component {component_name}: Step {i} ({step_name}) failed "
                            f"(attempt {attempt + 1}/{max_retries + 1}): {str(e)[:100]}"
                        )
                        
                        # [*] 关键改进:关闭弹窗并等待页面稳定
                        await step_popup_handler.on_error(page, step, component)
                        
                        logger.info(f"Retrying step {i} ({step_name})...")
                    else:
                        # [*] 所有重试都失败了
                        logger.error(
                            f"Component {component_name}: Step {i} ({step_name}) failed "
                            f"after {max_retries + 1} attempts: {str(e)[:100]}"
                        )
            
            # [*] 改进:根据步骤类型决定是否继续
            if not success:
                if optional:
                    # [*] Optional 步骤失败,记录警告但继续执行
                    logger.warning(
                        f"Component {component_name}: Optional step {i} ({step_name}) failed, "
                        f"continuing with next steps"
                    )
                else:
                    # [*] 必需步骤失败,标记并退出
                    logger.error(
                        f"Component {component_name}: Required step {i} ({step_name}) failed, "
                        f"stopping component execution"
                    )
                    step_failed = True
                    break  # 退出步骤循环
            
            # 步骤执行后检查弹窗
            await step_popup_handler.after_step(page, step, component)
        
        # 组件执行后检查弹窗
        if popup_handling.get('check_after_steps', True):
            await self.popup_handler.close_popups(page, platform=component.get('platform'))
        
        # Phase 7.1: 验证成功标准
        success_criteria = component.get('success_criteria', [])
        success_result = False
        
        if success_criteria:
            verification_result = await self._verify_success_criteria(
                page, 
                success_criteria, 
                component
            )
            
            if verification_result['success']:
                logger.info(f"Component {component_name}: Success criteria verified")
                success_result = True
            else:
                logger.warning(
                    f"Component {component_name}: Success criteria verification failed: "
                    f"{verification_result['reason']}"
                )
                
                # 检查是否有错误处理器
                error_handlers = component.get('error_handlers', [])
                if error_handlers:
                    error_handled = await self._handle_errors(page, error_handlers, component)
                    if error_handled:
                        # 错误已处理,重新验证
                        retry_verification = await self._verify_success_criteria(page, success_criteria, component)
                        success_result = retry_verification['success']
                    else:
                        success_result = False
                else:
                    success_result = False
        else:
            # 没有成功标准,只要步骤执行完就认为成功
            if step_failed:
                logger.warning(f"Component {component_name}: Steps failed but no success criteria to verify")
                success_result = False
            else:
                logger.debug(f"Component {component_name}: No success criteria, assuming success")
                success_result = True
        
        # [*] Phase 9.4: 记录版本使用情况
        self._record_version_usage(component, success_result)
        
        return success_result
    
    async def _execute_discovery_component(
        self,
        page,
        component: Dict[str, Any],
        step_popup_handler: StepPopupHandler
    ) -> bool:
        """
        执行发现模式组件(Phase 11)
        
        发现模式组件结构:
        - open_action: 打开动作(如点击日期控件)
        - available_options: 可用选项列表
        - params.date_range 或 params.filter_value: 要选择的选项 key
        
        执行流程:
        1. 执行 open_action(打开选择器)
        2. 根据参数找到对应的选项
        3. 点击该选项
        
        Args:
            page: Playwright Page对象
            component: 发现模式组件配置
            step_popup_handler: 步骤弹窗处理器
        
        Returns:
            bool: 是否执行成功
        """
        component_name = component.get('name', 'unknown')
        component_type = component.get('type', '')
        params = component.get('_params', {})
        
        logger.info(f"Executing discovery component: {component_name} (type: {component_type})")
        
        # 获取 open_action
        open_action = component.get('open_action')
        if not open_action:
            logger.error(f"Discovery component {component_name}: Missing open_action")
            return False
        
        # 获取 available_options
        available_options = component.get('available_options', [])
        if not available_options:
            logger.error(f"Discovery component {component_name}: No available options")
            return False
        
        # 确定要选择的选项 key
        # date_picker 使用 date_range,filters 使用 filter_value
        option_key = params.get('date_range') or params.get('filter_value')
        if not option_key:
            # 使用默认选项
            option_key = component.get('default_option')
            if not option_key and available_options:
                option_key = available_options[0].get('key')
        
        logger.info(f"Discovery component {component_name}: Selecting option '{option_key}'")
        
        # 找到对应的选项
        selected_option = None
        for opt in available_options:
            if opt.get('key') == option_key:
                selected_option = opt
                break
        
        if not selected_option:
            logger.error(f"Discovery component {component_name}: Option '{option_key}' not found")
            logger.info(f"Available options: {[o.get('key') for o in available_options]}")
            return False
        
        try:
            # 1. 执行 open_action(打开选择器)
            await step_popup_handler.before_step(page, open_action, component)
            
            open_step = {
                'action': 'click',
                'selectors': open_action.get('selectors', []),
                'selector': self._get_primary_selector_from_list(open_action.get('selectors', [])),
                'timeout': open_action.get('timeout', 5000),
            }
            await self._execute_step(page, open_step, component)
            
            # 等待选项出现
            await asyncio.sleep(0.5)
            
            # 2. 点击选中的选项
            option_step = {
                'action': 'click',
                'selectors': selected_option.get('selectors', []),
                'selector': self._get_primary_selector_from_list(selected_option.get('selectors', [])),
                'timeout': 5000,
            }
            await self._execute_step(page, option_step, component)
            
            logger.info(f"Discovery component {component_name}: Successfully selected '{option_key}'")
            return True
            
        except Exception as e:
            logger.error(f"Discovery component {component_name}: Failed to execute: {e}")
            return False
    
    def _get_primary_selector_from_list(self, selectors: list) -> str:
        """从选择器列表中获取主选择器(用于降级)"""
        if not selectors:
            return ''
        
        # 优先使用 text 类型(更稳定)
        for sel in selectors:
            if sel.get('type') == 'text':
                return f"text={sel.get('value', '')}"
        
        # 其次使用 css 类型
        for sel in selectors:
            if sel.get('type') == 'css':
                return sel.get('value', '')
        
        # 降级使用第一个
        first = selectors[0]
        if first.get('type') == 'text':
            return f"text={first.get('value', '')}"
        return first.get('value', '')
    
    async def _execute_step(self, page, step: Dict[str, Any], component: Dict[str, Any]) -> Any:
        """
        执行单个步骤(v4.7.0: 支持optional和retry,Phase 2.5.5: 支持fallback)
        
        Args:
            page: Playwright Page对象
            step: 步骤配置
            component: 组件配置(用于获取平台等信息)
            
        Returns:
            Any: 步骤执行结果
        """
        action = step.get('action')
        timeout = step.get('timeout', 5000)
        optional = step.get('optional', False)  # v4.7.0: 可选步骤
        retry_config = step.get('retry')  # v4.7.0: 重试配置
        fallback_methods = step.get('fallback_methods')  # Phase 2.5.5: 降级方法
        
        # Phase 2.5.5: 如果配置了fallback,使用降级策略
        if fallback_methods:
            return await self._execute_with_fallback(page, step, component)
        
        # v4.7.0: 如果配置了重试,使用重试机制
        if retry_config:
            return await self._execute_step_with_retry(page, step, component)
        
        # v4.7.0: 对于需要定位元素的操作,支持optional
        needs_element = action in ['click', 'fill', 'select', 'check_element', 'wait']
        
        if optional and needs_element:
            # 快速检测元素是否存在
            selector = step.get('selector')
            if selector and not await self._check_element_exists_quick(page, selector):
                logger.info(f"Optional step skipped: {action} {selector} - element not found")
                return None  # 跳过,不报错
        
        if action == 'navigate':
            url = step.get('url')
            wait_until = step.get('wait_until', 'load')
            await page.goto(url, wait_until=wait_until, timeout=timeout)
        
        elif action == 'click':
            wait_for = step.get('wait_for')
            delay = step.get('delay', 0)
            
            if wait_for:
                await page.wait_for_selector(wait_for, timeout=timeout)
            
            # Phase 10: 使用多选择器降级
            locator = await self._get_locator_with_fallback(page, step, timeout)
            await locator.click(timeout=timeout)
            
            if delay > 0:
                await asyncio.sleep(delay / 1000)
        
        elif action == 'fill':
            value = step.get('value', '')
            clear = step.get('clear', True)
            
            # Phase 10: 使用多选择器降级
            locator = await self._get_locator_with_fallback(page, step, timeout)
            
            if clear:
                await locator.clear(timeout=timeout)
            
            await locator.fill(value, timeout=timeout)
        
        elif action == 'wait':
            wait_type = step.get('type', 'timeout')
            
            if wait_type == 'timeout':
                duration = step.get('duration', 1000)
                await asyncio.sleep(duration / 1000)
            
            elif wait_type == 'selector':
                selector = step.get('selector')
                state = step.get('state', 'visible')
                smart_wait = step.get('smart_wait', False)  # Phase 2.5.4.2: 自适应等待
                
                if smart_wait:
                    # 使用自适应等待策略
                    await self._smart_wait_for_element(page, selector, timeout, state)
                else:
                    # 使用标准等待
                    await page.wait_for_selector(selector, state=state, timeout=timeout)
            
            elif wait_type == 'navigation':
                wait_until = step.get('wait_until', 'load')
                await page.wait_for_load_state(wait_until, timeout=timeout)
        
        elif action == 'select':
            value = step.get('value')
            by = step.get('by', 'value')
            
            # Phase 10: 使用多选择器降级
            locator = await self._get_locator_with_fallback(page, step, timeout)
            
            if by == 'value':
                await locator.select_option(value=value, timeout=timeout)
            elif by == 'label':
                await locator.select_option(label=value, timeout=timeout)
            elif by == 'index':
                await locator.select_option(index=int(value), timeout=timeout)
        
        elif action == 'check_element':
            selector = step.get('selector')
            expect = step.get('expect', 'visible')
            on_fail = step.get('on_fail', 'error')
            
            try:
                locator = page.locator(selector).first
                
                if expect == 'exists':
                    await locator.wait_for(state='attached', timeout=timeout)
                elif expect == 'not_exists':
                    await locator.wait_for(state='detached', timeout=timeout)
                elif expect == 'visible':
                    await locator.wait_for(state='visible', timeout=timeout)
                elif expect == 'hidden':
                    await locator.wait_for(state='hidden', timeout=timeout)
            
            except Exception as e:
                if on_fail == 'error':
                    raise
                elif on_fail == 'skip':
                    logger.warning(f"check_element failed, skipping: {e}")
                # on_fail == 'continue' 什么都不做
        
        elif action == 'screenshot':
            path = step.get('path', f'screenshot_{uuid.uuid4().hex[:8]}.png')
            full_page = step.get('full_page', False)
            await page.screenshot(path=path, full_page=full_page)
        
        elif action == 'component_call':
            component_path = step.get('component')
            component_params = step.get('params', {})
            
            # 合并参数
            merged_params = {**component.get('_params', {}), **component_params}
            
            # 加载并执行子组件
            sub_component = self.component_loader.load(component_path, merged_params)
            step_popup_handler = StepPopupHandler(
                self.popup_handler, 
                sub_component.get('platform')
            )
            await self._execute_component(page, sub_component, step_popup_handler)
        
        elif action == 'close_popups':
            platform = component.get('platform')
            await self.popup_handler.close_popups(page, platform=platform)
        
        else:
            logger.warning(f"Unknown action: {action}")
    
    async def _check_element_exists_quick(self, page, selector: str, timeout: int = 1000) -> bool:
        """
        快速检测元素是否存在(v4.7.0新增)
        
        Args:
            page: Playwright Page对象
            selector: 元素选择器
            timeout: 超时时间(毫秒,默认1秒)
            
        Returns:
            bool: 元素是否存在
        """
        try:
            await page.wait_for_selector(selector, state='attached', timeout=timeout)
            return True
        except Exception:
            return False
    
    async def _get_locator_with_fallback(
        self,
        page,
        step: Dict[str, Any],
        timeout: int = 5000
    ):
        """
        获取元素定位器,支持多选择器降级(Phase 10)
        
        按优先级尝试多个选择器:
        1. 如果配置了 selectors 数组,按优先级逐个尝试
        2. 降级到传统 selector 字段
        
        Args:
            page: Playwright Page对象
            step: 步骤配置(包含 selector 或 selectors)
            timeout: 超时时间(毫秒)
            
        Returns:
            Locator: 成功匹配的定位器
            
        Raises:
            Exception: 所有选择器都失败时抛出异常
        """
        selectors = step.get('selectors', [])
        legacy_selector = step.get('selector')
        
        # 如果没有 selectors 数组,使用传统 selector
        if not selectors and legacy_selector:
            return page.locator(legacy_selector).first
        
        # 按优先级排序
        sorted_selectors = sorted(selectors, key=lambda x: x.get('priority', 99))
        
        errors = []
        for sel_config in sorted_selectors:
            sel_type = sel_config.get('type', 'css')
            sel_value = sel_config.get('value', '')
            
            if not sel_value:
                continue
            
            try:
                # 根据类型构建定位器
                if sel_type == 'role':
                    # 解析 role[name="xxx"] 格式
                    if '[name=' in sel_value:
                        role = sel_value.split('[')[0]
                        name = sel_value.split('name="')[1].rstrip('"]')
                        locator = page.get_by_role(role, name=name)
                    else:
                        locator = page.get_by_role(sel_value)
                elif sel_type == 'text':
                    locator = page.get_by_text(sel_value)
                elif sel_type == 'css':
                    locator = page.locator(sel_value)
                elif sel_type == 'xpath':
                    locator = page.locator(f'xpath={sel_value}')
                else:
                    locator = page.locator(sel_value)
                
                # 快速验证元素是否存在
                await locator.first.wait_for(state='attached', timeout=1000)
                logger.debug(f"Selector matched: {sel_type}={sel_value}")
                return locator.first
                
            except Exception as e:
                errors.append(f"{sel_type}={sel_value}: {str(e)[:50]}")
                continue
        
        # 所有 selectors 都失败,尝试 legacy selector
        if legacy_selector:
            logger.debug(f"Fallback to legacy selector: {legacy_selector}")
            return page.locator(legacy_selector).first
        
        # 全部失败
        error_msg = f"All selectors failed: {'; '.join(errors[:3])}"
        logger.warning(error_msg)
        raise Exception(error_msg)
    
    async def _smart_wait_for_element(
        self,
        page,
        selector: str,
        max_timeout: int = 30000,
        state: str = 'visible'
    ) -> bool:
        """
        自适应等待元素(Phase 2.5.4.2)
        
        多层次等待策略,处理网络延迟和弹窗遮挡:
        1. 快速检测(1秒)- 元素已存在
        2. 关闭弹窗 + 重试(10秒)- 弹窗遮挡
        3. 等待网络空闲(5秒)- 网络慢
        4. 长时间等待(剩余时间)- 页面加载慢
        
        Args:
            page: Playwright Page对象
            selector: 元素选择器
            max_timeout: 最大超时时间(毫秒)
            state: 等待状态(visible/attached/hidden/detached)
            
        Returns:
            bool: 元素是否成功等待到
            
        Raises:
            Exception: 所有策略都失败时抛出异常
        """
        start_time = asyncio.get_event_loop().time()
        remaining_timeout = max_timeout
        
        # 策略1: 快速检测(1秒)
        try:
            logger.debug(f"Smart wait strategy 1: Quick check (1s) for {selector}")
            await page.wait_for_selector(selector, state=state, timeout=1000)
            logger.debug(f"Element found immediately: {selector}")
            return True
        except Exception:
            elapsed = int((asyncio.get_event_loop().time() - start_time) * 1000)
            remaining_timeout = max(0, max_timeout - elapsed)
            logger.debug(f"Quick check failed, remaining timeout: {remaining_timeout}ms")
        
        # 策略2: 关闭弹窗 + 重试(10秒)
        if remaining_timeout > 0:
            try:
                logger.debug(f"Smart wait strategy 2: Close popups + retry (10s)")
                # 尝试关闭弹窗
                await self.popup_handler.close_popups(page)
                
                # 重试等待
                retry_timeout = min(10000, remaining_timeout)
                await page.wait_for_selector(selector, state=state, timeout=retry_timeout)
                logger.info(f"Element found after closing popups: {selector}")
                return True
            except Exception as e:
                elapsed = int((asyncio.get_event_loop().time() - start_time) * 1000)
                remaining_timeout = max(0, max_timeout - elapsed)
                logger.debug(f"Popup strategy failed: {e}, remaining: {remaining_timeout}ms")
        
        # 策略3: 等待网络空闲(5秒)
        if remaining_timeout > 0:
            try:
                logger.debug(f"Smart wait strategy 3: Wait for network idle (5s)")
                network_timeout = min(5000, remaining_timeout)
                await page.wait_for_load_state('networkidle', timeout=network_timeout)
                
                # 网络空闲后再次尝试
                elapsed = int((asyncio.get_event_loop().time() - start_time) * 1000)
                remaining_timeout = max(0, max_timeout - elapsed)
                
                if remaining_timeout > 0:
                    retry_timeout = min(5000, remaining_timeout)
                    await page.wait_for_selector(selector, state=state, timeout=retry_timeout)
                    logger.info(f"Element found after network idle: {selector}")
                    return True
            except Exception as e:
                elapsed = int((asyncio.get_event_loop().time() - start_time) * 1000)
                remaining_timeout = max(0, max_timeout - elapsed)
                logger.debug(f"Network idle strategy failed: {e}, remaining: {remaining_timeout}ms")
        
        # 策略4: 长时间等待(剩余时间)
        if remaining_timeout > 0:
            try:
                logger.debug(f"Smart wait strategy 4: Long wait ({remaining_timeout}ms)")
                await page.wait_for_selector(selector, state=state, timeout=remaining_timeout)
                logger.info(f"Element found with long wait: {selector}")
                return True
            except Exception as e:
                logger.error(f"All smart wait strategies failed for {selector}: {e}")
                raise
        else:
            raise Exception(f"Smart wait timeout: {selector} not found after {max_timeout}ms")
    
    async def _run_pre_checks(
        self,
        page,
        component: Dict[str, Any],
        pre_checks: List[Dict[str, Any]]
    ) -> bool:
        """
        执行预检测(v4.7.0新增)
        
        Args:
            page: Playwright Page对象
            component: 组件配置
            pre_checks: 预检测配置列表
            
        Returns:
            bool: 是否通过所有预检测
        """
        for check in pre_checks:
            check_type = check.get('type')
            on_failure = check.get('on_failure', 'skip_task')
            
            try:
                if check_type == 'url_accessible':
                    # URL可访问性检测
                    url = check.get('url')
                    if not await self._check_url_accessible(page, url):
                        logger.warning(f"Pre-check failed: URL not accessible: {url}")
                        if on_failure == 'skip_task':
                            return False
                        elif on_failure == 'fail_task':
                            raise Exception(f"URL not accessible: {url}")
                        # on_failure == 'continue' 则继续
                
                elif check_type == 'element_exists':
                    # 元素存在性检测
                    selector = check.get('selector')
                    timeout = check.get('timeout', 3000)
                    if not await self._check_element_exists_quick(page, selector, timeout):
                        logger.warning(f"Pre-check failed: Element not found: {selector}")
                        if on_failure == 'skip_task':
                            return False
                        elif on_failure == 'fail_task':
                            raise Exception(f"Element not found: {selector}")
                        # on_failure == 'continue' 则继续
                
                else:
                    logger.warning(f"Unknown pre-check type: {check_type}")
            
            except Exception as e:
                logger.error(f"Pre-check error: {e}")
                if on_failure in ['skip_task', 'fail_task']:
                    return False
        
        return True
    
    async def _check_url_accessible(self, page, url: str, timeout: int = 5000) -> bool:
        """
        检查URL是否可访问(v4.7.0新增)
        
        Args:
            page: Playwright Page对象
            url: 要检查的URL
            timeout: 超时时间(毫秒)
            
        Returns:
            bool: URL是否可访问
        """
        try:
            response = await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
            if response and response.status >= 400:
                logger.warning(f"URL returned error status: {response.status}")
                return False
            return True
        except Exception as e:
            logger.error(f"URL accessibility check failed: {e}")
            return False
    
    async def _verify_success_criteria(
        self,
        page,
        success_criteria: List[Dict[str, Any]],
        component: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        验证组件的成功标准(Phase 7.1: 显式成功验证机制)
        
        Args:
            page: Playwright Page对象
            success_criteria: 成功标准列表
            component: 组件配置(用于获取参数)
        
        Returns:
            Dict: {
                'success': bool,
                'reason': str,  # 失败原因
                'passed_criteria': List[str],  # 通过的验证项
                'failed_criteria': List[str]  # 失败的验证项
            }
        """
        # P1增强:验证前先处理弹窗,避免弹窗遮挡验证元素
        try:
            await self.popup_handler.close_popups(page, platform=component.get('platform'))
            await page.wait_for_timeout(500)  # 等待弹窗关闭动画
        except Exception as e:
            logger.debug(f"Pre-verification popup handling failed: {e}")
        
        passed = []
        failed = []
        
        for criterion in success_criteria:
            criterion_type = criterion.get('type')
            optional = criterion.get('optional', False)
            comment = criterion.get('comment', '')
            
            try:
                result = False
                
                if criterion_type == 'url_contains':
                    # URL包含特定字符串
                    value = criterion.get('value')
                    current_url = page.url
                    result = value in current_url if value else False
                    
                elif criterion_type == 'url_matches':
                    # URL匹配正则表达式
                    import re
                    pattern = criterion.get('value')
                    current_url = page.url
                    result = bool(re.search(pattern, current_url)) if pattern else False
                    
                elif criterion_type == 'element_exists':
                    # 元素存在
                    selector = criterion.get('selector')
                    timeout = criterion.get('timeout', 5000)
                    if selector:
                        try:
                            await page.wait_for_selector(selector, timeout=timeout, state='attached')
                            result = True
                        except:
                            result = False
                    
                elif criterion_type == 'element_visible':
                    # 元素可见
                    selector = criterion.get('selector')
                    timeout = criterion.get('timeout', 5000)
                    if selector:
                        try:
                            await page.wait_for_selector(selector, timeout=timeout, state='visible')
                            result = True
                        except:
                            result = False
                    
                elif criterion_type == 'element_text_contains':
                    # 元素文本包含特定内容
                    selector = criterion.get('selector')
                    value = criterion.get('value')
                    timeout = criterion.get('timeout', 5000)
                    if selector and value:
                        try:
                            await page.wait_for_selector(selector, timeout=timeout, state='visible')
                            text = await page.locator(selector).first.inner_text()
                            result = value.lower() in text.lower()
                        except:
                            result = False
                    
                elif criterion_type == 'page_contains_text':
                    # 页面包含文本
                    value = criterion.get('value')
                    if value:
                        try:
                            text = await page.inner_text('body')
                            result = value.lower() in text.lower()
                        except:
                            result = False
                    
                elif criterion_type == 'custom_js':
                    # 自定义JavaScript验证
                    script = criterion.get('script')
                    if script:
                        try:
                            result = await page.evaluate(script)
                            result = bool(result)
                        except:
                            result = False
                
                else:
                    logger.warning(f"Unknown success criterion type: {criterion_type}")
                    continue
                
                # 记录验证结果
                if result:
                    passed.append(f"{criterion_type}: {comment or 'passed'}")
                else:
                    if optional:
                        # 可选验证失败不影响整体
                        logger.debug(f"Optional criterion failed: {criterion_type}")
                    else:
                        failed.append(f"{criterion_type}: {comment or 'failed'}")
            
            except Exception as e:
                if not optional:
                    failed.append(f"{criterion_type}: Exception - {str(e)}")
                logger.debug(f"Criterion verification error: {e}")
        
        # 判断整体成功(所有非可选验证必须通过)
        success = len(failed) == 0
        
        return {
            'success': success,
            'reason': f"Failed: {', '.join(failed)}" if failed else "All criteria passed",
            'passed_criteria': passed,
            'failed_criteria': failed
        }
    
    async def _handle_errors(
        self,
        page,
        error_handlers: List[Dict[str, Any]],
        component: Dict[str, Any]
    ) -> bool:
        """
        处理错误(Phase 7.1: 错误处理器支持)
        
        Args:
            page: Playwright Page对象
            error_handlers: 错误处理器配置列表
            component: 组件配置
        
        Returns:
            bool: 是否成功处理错误
        """
        for handler in error_handlers:
            selector = handler.get('selector')
            action = handler.get('action', 'fail_task')
            message = handler.get('message', '')
            
            try:
                # 检查错误元素是否存在
                if selector:
                    element_exists = await self._check_element_exists_quick(page, selector)
                    if element_exists:
                        logger.warning(f"Error detected: {message}")
                        
                        if action == 'fail_task':
                            raise StepExecutionError(f"Error handler triggered: {message}")
                        elif action == 'retry_login':
                            logger.info("Retry login requested by error handler")
                            # TODO: 实现重新登录逻辑
                            return False
                        elif action == 'close_popup':
                            await self.popup_handler.close_popups(page, platform=component.get('platform'))
                            return True
            
            except Exception as e:
                logger.error(f"Error handler failed: {e}")
        
        return False
    
    async def _execute_step_with_retry(
        self, 
        page, 
        step: Dict[str, Any], 
        component: Dict[str, Any]
    ) -> Any:
        """
        执行步骤并支持重试(v4.7.0新增)
        
        Args:
            page: Playwright Page对象
            step: 步骤配置
            component: 组件配置
            
        Returns:
            Any: 步骤执行结果
        """
        retry_config = step.get('retry', {})
        max_attempts = retry_config.get('max_attempts', 3)
        delay = retry_config.get('delay', 2000)  # 毫秒
        on_retry = retry_config.get('on_retry', 'wait')  # wait/close_popup
        
        last_error = None
        
        for attempt in range(1, max_attempts + 1):
            try:
                # 临时移除retry配置,避免递归
                step_copy = step.copy()
                step_copy.pop('retry', None)
                
                # 执行步骤
                result = await self._execute_step(page, step_copy, component)
                
                # 成功
                if attempt > 1:
                    logger.info(f"Step succeeded on retry attempt {attempt}/{max_attempts}")
                return result
            
            except Exception as e:
                last_error = e
                logger.warning(f"Step failed on attempt {attempt}/{max_attempts}: {e}")
                
                # 最后一次尝试失败,抛出异常
                if attempt >= max_attempts:
                    logger.error(f"Step failed after {max_attempts} attempts")
                    raise
                
                # 执行重试前操作
                if on_retry == 'close_popup':
                    try:
                        await self.popup_handler.close_popups(page, platform=component.get('platform'))
                        logger.info("Closed popups before retry")
                    except Exception as popup_err:
                        logger.warning(f"Failed to close popups: {popup_err}")
                
                # 延迟后重试
                await asyncio.sleep(delay / 1000)
        
        # 理论上不会到达这里
        raise last_error
    
    async def _execute_with_fallback(
        self,
        page,
        step: Dict[str, Any],
        component: Dict[str, Any]
    ) -> Any:
        """
        使用降级策略执行步骤(Phase 2.5.5)
        
        尝试primary方法,失败后依次尝试fallback方法
        
        Args:
            page: Playwright Page对象
            step: 步骤配置
            component: 组件配置
            
        Returns:
            Any: 步骤执行结果
            
        Example YAML:
            - action: click
              selector: button.primary-btn
              fallback_methods:
                - selector: button.secondary-btn
                  description: "备用按钮"
                - selector: a.link-btn
                  description: "链接按钮"
        """
        fallback_methods = step.get('fallback_methods', [])
        primary_selector = step.get('selector')
        
        # 尝试primary方法
        try:
            # 临时移除fallback_methods,避免递归
            step_copy = step.copy()
            step_copy.pop('fallback_methods', None)
            
            result = await self._execute_step(page, step_copy, component)
            logger.debug(f"Primary method succeeded: {primary_selector}")
            return result
        
        except Exception as primary_error:
            logger.warning(f"Primary method failed: {primary_selector} - {primary_error}")
            
            # 如果没有fallback方法,直接抛出异常
            if not fallback_methods:
                raise
            
            # 依次尝试fallback方法
            last_error = primary_error
            
            for i, fallback in enumerate(fallback_methods, 1):
                fallback_selector = fallback.get('selector')
                fallback_desc = fallback.get('description', f'fallback {i}')
                
                try:
                    logger.info(f"Trying fallback method {i}/{len(fallback_methods)}: {fallback_desc}")
                    
                    # 创建fallback步骤
                    fallback_step = step.copy()
                    fallback_step.pop('fallback_methods', None)  # 移除fallback配置
                    fallback_step['selector'] = fallback_selector  # 使用fallback选择器
                    
                    # 如果fallback有自己的timeout,使用它
                    if 'timeout' in fallback:
                        fallback_step['timeout'] = fallback['timeout']
                    
                    # 执行fallback步骤
                    result = await self._execute_step(page, fallback_step, component)
                    
                    logger.info(f"Fallback method succeeded: {fallback_desc} ({fallback_selector})")
                    return result
                
                except Exception as fallback_error:
                    logger.warning(f"Fallback method {i} failed: {fallback_desc} - {fallback_error}")
                    last_error = fallback_error
                    continue
            
            # 所有方法都失败
            logger.error(
                f"All methods failed (1 primary + {len(fallback_methods)} fallbacks) "
                f"for action: {step.get('action')}"
            )
            raise last_error
    
    async def _execute_export_component(
        self,
        page,
        component: Dict[str, Any],
        step_popup_handler: StepPopupHandler,
        download_dir: Path,
    ) -> Optional[str]:
        """
        执行导出组件并等待文件下载。
        迁离 YAML：若组件含 _python_component_class 则通过 adapter.export 执行。
        """
        # Python 组件：通过 adapter.export 执行
        if component.get("_python_component_class"):
            params = component.get("_params", {})
            account = params.get("account", params)
            config = params.get("params", params) if isinstance(params.get("params"), dict) else params
            if not isinstance(config, dict):
                config = params
            config = dict(config) if config else {}
            config.setdefault("task", {})["download_dir"] = str(download_dir)
            config.setdefault("downloads_path", str(download_dir))
            adapter = create_adapter(
                platform=component["platform"],
                account=account,
                config=config,
            )
            data_domain = (config.get("data_domain") or (params.get("params") or {}).get("data_domain"))
            if not data_domain and component.get("name"):
                # 从组件名推断，如 orders_export -> orders
                name = component["name"]
                if name.endswith("_export"):
                    data_domain = name[:-7]
            result = await adapter.export(page=page, data_domain=data_domain or "orders")
            if result and getattr(result, "file_path", None):
                return result.file_path
            return None

        steps = component.get("steps", [])
        download_path = None
        
        # 组件执行前检查弹窗
        popup_handling = component.get('popup_handling', {})
        if popup_handling.get('check_before_steps', True):
            await self.popup_handler.close_popups(page, platform=component.get('platform'))
        
        for i, step in enumerate(steps):
            action = step.get('action')
            
            # 步骤执行前检查弹窗
            await step_popup_handler.before_step(page, step, component)
            
            try:
                if action == 'wait_for_download':
                    # 等待文件下载
                    timeout = step.get('timeout', self.DEFAULT_DOWNLOAD_TIMEOUT * 1000)
                    save_as = step.get('save_as')
                    
                    async with page.expect_download(timeout=timeout) as download_info:
                        # 下载会在前面的点击操作触发
                        pass
                    
                    download = await download_info.value
                    
                    # 确定保存路径
                    if save_as:
                        file_path = download_dir / save_as
                    else:
                        file_path = download_dir / download.suggested_filename
                    
                    await download.save_as(str(file_path))
                    download_path = str(file_path)
                    
                    logger.info(f"Downloaded file: {download_path}")
                
                else:
                    # 执行普通步骤
                    await self._execute_step(page, step, component)
            
            except Exception as e:
                # 错误时检查弹窗
                await step_popup_handler.on_error(page, step, component)
                
                # 检查是否是验证码
                if await self._check_verification(page):
                    screenshot_path = await self._save_verification_screenshot(page, component.get('platform'))
                    raise VerificationRequiredError('unknown', screenshot_path)
                
                raise StepExecutionError(f"Export step {i} failed: {e}") from e
            
            # 步骤执行后检查弹窗
            await step_popup_handler.after_step(page, step, component)
        
        # Phase 12.4: 如果没有 wait_for_download 步骤,自动扫描下载目录
        if download_path is None:
            logger.info("No wait_for_download step found, scanning download directory...")
            download_path = await self._scan_latest_download(download_dir, timeout=30)
            if download_path:
                logger.info(f"Auto-detected downloaded file: {download_path}")
        
        return download_path
    
    async def _scan_latest_download(
        self, 
        download_dir: Path, 
        timeout: int = 30,
        file_extensions: tuple = ('.xlsx', '.xls', '.csv', '.xlsm')
    ) -> Optional[str]:
        """
        扫描下载目录,查找最新下载的文件(兜底机制)
        
        Args:
            download_dir: 下载目录
            timeout: 超时时间(秒)
            file_extensions: 允许的文件扩展名
            
        Returns:
            Optional[str]: 最新文件的路径,如果未找到则返回None
        """
        import time
        
        start_time = time.time()
        
        # 记录执行前的文件列表
        before_files = set()
        for ext in file_extensions:
            before_files.update(download_dir.glob(f"*{ext}"))
        
        logger.debug(f"Before files count: {len(before_files)}")
        
        # 等待一段时间让文件下载完成
        await asyncio.sleep(2)
        
        # 轮询检查新文件
        check_interval = 1  # 每秒检查一次
        while time.time() - start_time < timeout:
            current_files = set()
            for ext in file_extensions:
                current_files.update(download_dir.glob(f"*{ext}"))
            
            new_files = current_files - before_files
            
            if new_files:
                # 过滤掉临时文件(.crdownload, .tmp等)
                valid_files = [
                    f for f in new_files 
                    if not any(f.name.endswith(ext) for ext in ['.crdownload', '.tmp', '.part'])
                ]
                
                if valid_files:
                    # 找到最新的文件(按修改时间)
                    latest_file = max(valid_files, key=lambda f: f.stat().st_mtime)
                    
                    # 检查文件是否完整(大小>0且不是临时文件)
                    if latest_file.stat().st_size > 0:
                        logger.info(f"Found new download: {latest_file.name} ({latest_file.stat().st_size} bytes)")
                        return str(latest_file)
            
            await asyncio.sleep(check_interval)
        
        logger.warning(f"No new download detected within {timeout} seconds")
        return None
    
    async def _check_verification(self, page) -> bool:
        """
        检查是否出现验证码
        
        Args:
            page: Playwright Page对象
            
        Returns:
            bool: 是否出现验证码
        """
        verification_selectors = [
            '[class*="captcha"]',
            '[class*="verify"]',
            '[class*="slider"]',
            '#captcha',
            '.captcha-container',
        ]
        
        for selector in verification_selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible(timeout=500):
                    return True
            except Exception:
                pass
        
        return False
    
    async def _save_verification_screenshot(self, page, platform: str = None) -> str:
        """
        保存验证码截图
        
        Args:
            page: Playwright Page对象
            platform: 平台代码
            
        Returns:
            str: 截图路径
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        screenshot_path = self.screenshots_dir / f"verification_{platform}_{timestamp}.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        
        await page.screenshot(path=str(screenshot_path))
        
        return str(screenshot_path)
    
    async def _process_files(
        self, 
        file_paths: List[str], 
        platform: str, 
        data_domains: List[str],
        granularity: str,
        account: Optional[Dict[str, Any]] = None,
        date_range: Optional[Dict[str, str]] = None
    ) -> List[str]:
        """
        处理采集到的文件(v4.8.0更新:对齐数据同步模块要求)
        
        - 使用 StandardFileName.generate() 生成标准文件名
        - 移动到 data/raw/YYYY/ 目录
        - 使用 MetadataManager.create_meta_file() 生成 .meta.json 伴生文件
        - 调用 register_single_file() 注册到 catalog_files 表
        
        Args:
            file_paths: 文件路径列表
            platform: 平台代码
            data_domains: 数据域列表
            granularity: 粒度
            account: 账号信息(可选)
            date_range: 日期范围(可选)
            
        Returns:
            List[str]: 处理后的文件路径
        """
        from modules.core.file_naming import StandardFileName
        from modules.services.metadata_manager import MetadataManager
        
        processed = []
        
        # 提取账号信息
        account = account or {}
        account_label = account.get("label") or account.get("username") or "unknown"
        shop_id = account.get("shop_id") or account.get("store_name")
        
        # 提取日期范围
        date_range = date_range or {}
        date_from = date_range.get("start_date") or date_range.get("date_from")
        date_to = date_range.get("end_date") or date_range.get("date_to")
        
        for idx, file_path in enumerate(file_paths):
            try:
                source_path = Path(file_path)
                if not source_path.exists():
                    logger.warning(f"File not found: {file_path}")
                    continue
                
                # 推断数据域(从文件路径或data_domains列表)
                data_domain = self._infer_data_domain_from_path(file_path, data_domains, idx)
                sub_domain = self._infer_sub_domain_from_path(file_path, data_domain=data_domain)
                
                landing_semantics = self._resolve_file_landing_semantics(
                    platform=platform,
                    data_domain=data_domain,
                    sub_domain=sub_domain,
                )

                # 1. 生成标准文件名
                ext = source_path.suffix.lstrip('.') or 'xlsx'
                standard_filename = StandardFileName.generate(
                    source_platform=landing_semantics["business_platform"],
                    data_domain=data_domain,
                    granularity=granularity,
                    sub_domain=landing_semantics["landing_sub_domain"],
                    ext=ext
                )
                
                # 2. 准备目标目录(data/raw/YYYY/)
                year = datetime.now().strftime("%Y")
                target_dir = Path(get_data_raw_dir()) / year
                target_dir.mkdir(parents=True, exist_ok=True)
                
                target_path = target_dir / standard_filename
                
                # 如果目标文件已存在,添加序号
                if target_path.exists():
                    base_name = target_path.stem
                    counter = 1
                    while target_path.exists():
                        target_path = target_dir / f"{base_name}_{counter}{target_path.suffix}"
                        counter += 1
                
                # 3. 移动文件
                shutil.move(str(source_path), str(target_path))
                logger.info(f"[OK] File moved: {source_path.name} -> {target_path}")
                
                # 4. 生成 .meta.json 伴生文件
                try:
                    business_metadata = {
                        "source_platform": landing_semantics["business_platform"],
                        "data_domain": data_domain,
                        "sub_domain": landing_semantics["landing_sub_domain"],
                        "granularity": granularity,
                        "date_from": date_from,
                        "date_to": date_to,
                        "shop_id": shop_id
                    }
                    
                    collection_info = {
                        "method": "python_component",
                        "collection_platform": landing_semantics["collection_platform"],
                        "account": account_label,
                        "shop_id": shop_id,
                        "original_path": str(source_path),
                        "collected_at": datetime.now().isoformat()
                    }
                    
                    meta_path = MetadataManager.create_meta_file(
                        file_path=target_path,
                        business_metadata=business_metadata,
                        collection_info=collection_info
                    )
                    logger.info(f"[OK] Meta file created: {meta_path.name}")
                    
                except Exception as meta_error:
                    logger.warning(f"[WARN] Failed to create meta file for {target_path}: {meta_error}")
                
                # 5. 注册到 catalog_files 表
                try:
                    from modules.services.catalog_scanner import register_single_file
                    catalog_id = register_single_file(str(target_path))
                    if catalog_id:
                        logger.info(f"[OK] File registered: {target_path.name} (id={catalog_id})")
                    else:
                        logger.warning(f"[WARN] File registration returned None: {target_path}")
                except Exception as reg_error:
                    logger.warning(f"[WARN] Failed to register file {target_path}: {reg_error}")
                
                processed.append(str(target_path))
            
            except Exception as e:
                logger.error(f"[FAIL] Failed to process file {file_path}: {e}")
        
        return processed
    
    def _infer_data_domain_from_path(self, file_path: str, data_domains: List[str], index: int) -> str:
        """
        从文件路径推断数据域
        
        Args:
            file_path: 文件路径
            data_domains: 数据域列表
            index: 文件索引
            
        Returns:
            str: 数据域
        """
        path_lower = file_path.lower()
        
        # 优先从路径中推断
        domain_keywords = {
            'orders': ['order', 'profit_statistics', '/stat/'],
            'products': ['product', 'goods', 'sku'],
            'inventory': ['warehouse', 'inventory', 'stock'],
            'finance': ['finance', 'settlement', 'payment'],
            'services': ['service', 'chat', 'cs', 'agent'],
            'analytics': ['analytics', 'traffic', 'overview', 'performance']
        }
        
        for domain, keywords in domain_keywords.items():
            for keyword in keywords:
                if keyword in path_lower:
                    return domain
        
        # 降级:使用 data_domains 列表
        if data_domains and index < len(data_domains):
            # 处理可能包含子域的情况(如 "services.agent")
            domain = data_domains[index]
            if '.' in domain:
                return domain.split('.')[0]
            return domain
        
        return "unknown"
    
    def _infer_sub_domain_from_path(self, file_path: str, data_domain: Optional[str] = None) -> str:
        """
        从文件路径推断子数据域
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: 子数据域(空字符串表示无子域)
        """
        from backend.services.component_name_utils import DATA_DOMAIN_SUB_TYPES

        path_lower = str(file_path or "").lower().replace("\\", "/")
        path_parts = [part for part in path_lower.split("/") if part]

        candidate_domains: List[str] = []
        if data_domain:
            candidate_domains.append(str(data_domain).strip().lower())
        candidate_domains.extend(
            domain for domain in DATA_DOMAIN_SUB_TYPES.keys()
            if domain not in candidate_domains
        )

        for domain in candidate_domains:
            allowed_subtypes = [str(item).strip().lower() for item in DATA_DOMAIN_SUB_TYPES.get(domain, [])]
            if not allowed_subtypes:
                continue

            if domain in path_parts:
                domain_index = path_parts.index(domain)
                trailing_parts = path_parts[domain_index + 1:]
                for subtype in allowed_subtypes:
                    if subtype in trailing_parts:
                        return subtype

            for subtype in allowed_subtypes:
                if f"/{subtype}/" in path_lower:
                    return subtype

        return ""
    
    async def _update_status(
        self,
        task_id: str,
        progress: int,
        message: str,
        current_domain: str = None,
        details: Dict[str, Any] = None,
    ) -> None:
        """
        更新任务状态；可选传入 details 写入步骤日志(step_id/component/data_domain/success/duration_ms/error)。
        """
        logger.debug(f"Task {task_id}: {progress}% - {message}")
        if self.status_callback:
            try:
                if details is not None:
                    try:
                        await self.status_callback(task_id, progress, message, current_domain, details)
                    except TypeError:
                        await self.status_callback(task_id, progress, message, current_domain)
                else:
                    try:
                        await self.status_callback(task_id, progress, message, current_domain)
                    except TypeError:
                        await self.status_callback(task_id, progress, message)
            except Exception as e:
                logger.error(f"Status callback failed: {e}")
        
        # v4.7.4: 进度通过 HTTP 轮询获取,不再使用 WebSocket
    
    async def _check_cancelled(self, task_id: str) -> None:
        """
        检查任务是否被取消
        
        Args:
            task_id: 任务ID
            
        Raises:
            TaskCancelledError: 任务被取消
        """
        if self.is_cancelled_callback:
            try:
                is_cancelled = await self.is_cancelled_callback(task_id)
                if is_cancelled:
                    raise TaskCancelledError(f"Task {task_id} was cancelled")
            except TaskCancelledError:
                raise
            except Exception as e:
                logger.error(f"Cancelled callback failed: {e}")
    
    def get_task_context(self, task_id: str) -> Optional[TaskContext]:
        """
        获取任务上下文(用于任务恢复)
        
        Args:
            task_id: 任务ID
            
        Returns:
            Optional[TaskContext]: 任务上下文
        """
        return self._task_contexts.get(task_id)
    
    async def resume_task(self, task_id: str, page, account: Dict[str, Any]) -> CollectionResult:
        """
        恢复暂停的任务
        
        Args:
            task_id: 任务ID
            page: Playwright Page对象
            account: 账号信息
            
        Returns:
            CollectionResult: 采集结果
        """
        context = self._task_contexts.get(task_id)
        
        if not context:
            return CollectionResult(
                task_id=task_id,
                status="failed",
                error_message="Task context not found",
            )
        
        # 重置验证码状态
        context.verification_required = False
        context.verification_type = None
        context.screenshot_path = None
        
        # 继续执行
        return await self.execute(
            task_id=task_id,
            platform=context.platform,
            account_id=context.account_id,
            account=account,
            data_domains=context.data_domains,
            date_range=context.date_range,
            granularity=context.granularity,
            page=page,
            context=context,
        )
    
    async def execute_parallel_domains(
        self,
        task_id: str,
        platform: str,
        account_id: str,
        account: Dict[str, Any],
        data_domains: List[str],
        date_range: Dict[str, str],
        granularity: str,
        browser,  # Playwright Browser对象
        max_parallel: int = 3,  # 最大并发数
        debug_mode: bool = False,
        runtime_manifests: Optional[Dict[str, Any]] = None,
    ) -> CollectionResult:
        """
        [*] Phase 9.1: 并行执行多个数据域
        
        每个数据域使用独立的浏览器上下文(BrowserContext),共享登录Cookie
        
        Args:
            task_id: 任务ID
            platform: 平台代码
            account_id: 账号ID
            account: 账号信息
            data_domains: 数据域列表
            date_range: 日期范围
            granularity: 粒度
            browser: Playwright Browser对象
            max_parallel: 最大并发数(防止资源耗尽)
            debug_mode: 调试模式
            
        Returns:
            CollectionResult: 采集结果
        """
        start_time = datetime.now()
        session_owner_id, shop_account_id, use_account_session_fingerprint = _resolve_session_scope(account_id, account)
        if not use_account_session_fingerprint or not session_owner_id:
            unresolved_shop_account_id = str(
                shop_account_id
                or account_id
                or (account or {}).get("shop_account_id")
                or (account or {}).get("account_id")
                or ""
            ).strip() or "unknown"
            raise ValueError(
                f"Missing main_account_id for collection execution: shop_account_id={unresolved_shop_account_id}"
            )
        normalized_date_range = normalize_collection_date_range(date_range)
        logger.info(f"Task {task_id}: Starting PARALLEL collection for {len(data_domains)} domains (max_parallel={max_parallel}, use_account_session_fingerprint={use_account_session_fingerprint})")

        context = TaskContext(
            task_id=task_id,
            platform=platform,
            account_id=shop_account_id or account_id,
            data_domains=data_domains,
            date_range=date_range,
            granularity=granularity,
        )
        self._task_contexts[task_id] = context

        task_download_dir = self.downloads_dir / task_id
        task_download_dir.mkdir(parents=True, exist_ok=True)

        storage_state: Optional[Dict[str, Any]] = None
        reused_session = False
        if use_account_session_fingerprint and session_owner_id:
            try:
                session_data = await _load_or_bootstrap_session_async(
                    platform,
                    session_owner_id,
                    account,
                )
                if session_data and isinstance(session_data.get("storage_state"), dict):
                    storage_state = session_data["storage_state"]
                    reused_session = True
                    logger.info("Task %s: [parallel] session loaded for %s/%s", task_id, platform, session_owner_id)
            except Exception as e:
                logger.warning("Task %s: [parallel] load_session failed: %s", task_id, e)

        if use_account_session_fingerprint and session_owner_id:
            try:
                fp_options = await _get_fingerprint_context_options_async(platform, session_owner_id, account, proxy=None)
                login_context_options = _build_playwright_context_options_from_fingerprint(fp_options)
            except Exception as e:
                logger.warning("Task %s: [parallel] get fingerprint failed: %s, fallback to default", task_id, e)
                from modules.apps.collection_center.browser_config_helper import get_browser_context_args
                login_context_options = get_browser_context_args()
        else:
            from modules.apps.collection_center.browser_config_helper import get_browser_context_args
            login_context_options = get_browser_context_args()

        login_context_options.setdefault("accept_downloads", True)
        if storage_state:
            login_context_options["storage_state"] = storage_state

        coordinator_cm = None
        if (
            self.main_account_session_coordinator.is_locked(platform, session_owner_id)
            or self.main_account_session_coordinator.waiter_count(platform, session_owner_id) > 0
        ):
            await self._update_status(
                task_id,
                5,
                MAIN_ACCOUNT_SESSION_STEP_MESSAGES["waiting_for_main_account_session"],
            )

        await self._update_status(task_id, 5, "正在登录...")
        login_start_time = datetime.now()
        await self._update_status(
            task_id, 5, "登录开始",
            details={"step_id": "login", "component": "login", "data_domain": None}
        )
        login_context = await browser.new_context(**login_context_options)
        login_page = await login_context.new_page()

        params = _build_runtime_task_params(
            task_id=task_id,
            account=runtime_account,
            platform=platform,
            granularity=granularity,
            normalized_date_range=normalized_date_range,
            task_download_dir=task_download_dir,
            screenshot_dir=self.screenshots_dir / task_id,
            reused_session=reused_session,
        )
        params["main_account_id"] = session_owner_id
        if shop_account_id:
            params["shop_account_id"] = shop_account_id
        adapter = None
        if runtime_manifests is None:
            adapter = create_adapter(platform=platform, account=runtime_account, config=params)
        try:
            coordinator_cm = self.main_account_session_coordinator.acquire(platform, session_owner_id)
            await coordinator_cm.__aenter__()
            await self._update_status(
                task_id,
                5,
                MAIN_ACCOUNT_SESSION_STEP_MESSAGES["preparing_main_account_session"],
            )
            step_popup_handler = StepPopupHandler(self.popup_handler, platform)
            if runtime_manifests is not None:
                login_manifest = runtime_manifests.get("login")
                login_result = await self._run_runtime_manifest_component(
                    page=login_page,
                    manifest=login_manifest,
                    account=account,
                    config=params,
                )
                login_success = bool(getattr(login_result, "success", False))
            else:
                adapter = create_adapter(platform=platform, account=account, config=params)
                login_success = await self._execute_python_component(
                    page=login_page,
                    adapter=adapter,
                    component_type="login",
                    params=params,
                )
            duration_ms = int((datetime.now() - login_start_time).total_seconds() * 1000)
            await self._update_status(
                task_id, 10, "登录结束",
                details={"step_id": "login", "component": "login", "success": login_success, "duration_ms": duration_ms}
            )
            if not login_success:
                raise StepExecutionError("登录组件执行失败")
            if params.get("shop_account_id"):
                await self._update_status(
                    task_id,
                    12,
                    MAIN_ACCOUNT_SESSION_STEP_MESSAGES["switching_target_shop"],
                )
            await self._ensure_login_gate_ready(login_page, platform)
            await self._update_status(
                task_id,
                15,
                MAIN_ACCOUNT_SESSION_STEP_MESSAGES["target_shop_ready"],
            )
            await _record_platform_shop_discovery_async(
                platform=platform,
                page=login_page,
                params=params,
                account=account,
            )
            cookies = await login_context.cookies()
            storage_state = await login_context.storage_state()
            logger.info(f"Task {task_id}: Login completed, extracted {len(cookies)} cookies (reused_session=%s)", reused_session)
            if use_account_session_fingerprint and session_owner_id:
                try:
                    ok = await _save_session_async(platform, session_owner_id, storage_state)
                    if ok:
                        logger.info("Task %s: [parallel] session saved for %s/%s", task_id, platform, session_owner_id)
                except Exception as e:
                    logger.warning("Task %s: [parallel] save_session failed: %s", task_id, e)
        except Exception as e:
            duration_ms = int((datetime.now() - login_start_time).total_seconds() * 1000)
            await self._update_status(
                task_id, 10, "登录失败",
                details={"step_id": "login", "component": "login", "success": False, "duration_ms": duration_ms, "error": str(e)}
            )
            raise
        finally:
            if coordinator_cm is not None:
                await coordinator_cm.__aexit__(None, None, None)
            await login_page.close()
            await login_context.close()
        
        # 2. 并行执行各个数据域
        await self._update_status(task_id, 15, f"开始并行采集 {len(data_domains)} 个数据域...")
        
        # 将数据域分组,每组max_parallel个
        domain_batches = []
        for i in range(0, len(data_domains), max_parallel):
            batch = data_domains[i:i+max_parallel]
            domain_batches.append(batch)
        
        logger.info(f"Task {task_id}: Split into {len(domain_batches)} batches (max_parallel={max_parallel})")
        
        domain_context_options: Optional[Dict[str, Any]] = None
        if use_account_session_fingerprint and session_owner_id:
            try:
                fp_opts = await _get_fingerprint_context_options_async(platform, session_owner_id, account, proxy=None)
                domain_context_options = _build_playwright_context_options_from_fingerprint(fp_opts)
            except Exception:
                domain_context_options = None
        if domain_context_options is None:
            from modules.apps.collection_center.browser_config_helper import get_browser_context_args
            domain_context_options = get_browser_context_args()
        domain_context_options = dict(domain_context_options)
        domain_context_options.setdefault("accept_downloads", True)

        for batch_index, batch in enumerate(domain_batches):
            logger.info(f"Task {task_id}: Processing batch {batch_index+1}/{len(domain_batches)} with {len(batch)} domains")
            tasks = []
            for domain in batch:
                task = self._execute_single_domain_parallel(
                    task_id=task_id,
                    platform=platform,
                    account=account,
                    data_domain=domain,
                    date_range=date_range,
                    granularity=granularity,
                    browser=browser,
                    storage_state=storage_state,
                    task_download_dir=task_download_dir,
                    domain_index=data_domains.index(domain),
                    total_domains=len(data_domains),
                    context_options=domain_context_options,
                    runtime_manifests=runtime_manifests,
                )
                tasks.append(task)
            
            # 并行执行这一批
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            for i, result in enumerate(results):
                domain = batch[i]
                if isinstance(result, Exception):
                    error_msg = f"{type(result).__name__}: {str(result)}"
                    logger.error(f"Task {task_id}: Domain {domain} failed - {error_msg}")
                    context.failed_domains.append({"domain": domain, "error": error_msg})
                elif result:
                    # 成功
                    file_path, success = result
                    if success:
                        context.completed_domains.append(domain)
                        if file_path:
                            context.collected_files.append(file_path)
                        logger.info(f"Task {task_id}: Domain {domain} completed")
                    else:
                        context.failed_domains.append({"domain": domain, "error": "Execution failed"})
        
        # 3. 处理采集到的文件 + 步骤可观测成对打点
        file_process_start = datetime.now()
        await self._update_status(
            task_id, 95, "文件处理开始",
            details={"step_id": "file_process", "component": "file_process", "data_domain": None}
        )
        processed_files = await self._process_files(
            context.collected_files,
            platform,
            data_domains,
            granularity,
            account=account,
            date_range=date_range
        )
        duration_ms_fp = int((datetime.now() - file_process_start).total_seconds() * 1000)
        await self._update_status(
            task_id, 95, "文件处理结束",
            details={"step_id": "file_process", "component": "file_process", "success": True, "duration_ms": duration_ms_fp}
        )
        # 4. 生成最终结果
        duration = (datetime.now() - start_time).total_seconds()
        completed_count = len(context.completed_domains)
        failed_count = len(context.failed_domains)
        
        if completed_count == 0 and failed_count > 0:
            final_status = "failed"
            final_message = f"采集失败,0/{len(data_domains)} 个域成功"
        elif failed_count > 0:
            final_status = "partial_success"
            final_message = f"部分成功,{completed_count}/{len(data_domains)} 个域成功,{failed_count} 个失败"
        else:
            final_status = "completed"
            final_message = f"采集完成,共采集 {len(processed_files)} 个文件"
        
        await self._update_status(task_id, 100, final_message)
        logger.info(f"Task {task_id}: Parallel execution completed in {duration:.1f}s - {final_status}")
        
        # 清理
        self._task_contexts.pop(task_id, None)
        
        return CollectionResult(
            task_id=task_id,
            status=final_status,
            files_collected=len(processed_files),
            collected_files=processed_files,
            duration_seconds=duration,
            completed_domains=context.completed_domains,
            failed_domains=context.failed_domains,
            total_domains=len(data_domains),
        )
    
    async def _execute_single_domain_parallel(
        self,
        task_id: str,
        platform: str,
        account: Dict[str, Any],
        data_domain: str,
        date_range: Dict[str, str],
        granularity: str,
        browser,
        storage_state: Dict,
        task_download_dir: Path,
        domain_index: int,
        total_domains: int,
        context_options: Optional[Dict[str, Any]] = None,
        runtime_manifests: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """
        [*] Phase 9.1: 在独立浏览器上下文中执行单个数据域采集(带指纹与会话)
        """
        domain_context = None
        domain_page = None
        opts = dict(context_options or {})
        opts["storage_state"] = storage_state
        opts.setdefault("accept_downloads", True)

        domain_export_start = datetime.now()
        progress = 20 + int(70 * domain_index / total_domains)
        try:
            domain_context = await browser.new_context(**opts)
            domain_page = await domain_context.new_page()
            logger.info(f"Task {task_id}: [{domain_index+1}/{total_domains}] Starting {data_domain} in parallel context")
            await self._update_status(
                task_id, progress, f"[并行] 采集 {data_domain} 开始",
                current_domain=data_domain,
                details={"step_id": f"export_{data_domain}", "component": f"{data_domain}_export", "data_domain": data_domain}
            )
            
            # 准备参数（与顺序路径一致的 config 结构）
            normalized_date_range = normalize_collection_date_range(date_range)
            params = _build_runtime_task_params(
                task_id=task_id,
                account=account,
                platform=platform,
                granularity=granularity,
                normalized_date_range=normalized_date_range,
                task_download_dir=task_download_dir,
                screenshot_dir=self.screenshots_dir / task_id,
                reused_session=bool(storage_state),
            )
            params['params']['data_domain'] = data_domain
            
            if runtime_manifests is not None:
                export_manifest = runtime_manifests.get("exports_by_domain", {}).get(data_domain)
                if export_manifest is None:
                    raise StepExecutionError(
                        f"runtime manifest missing for export domain {data_domain}"
                    )
                export_result = await self._run_runtime_manifest_component(
                    page=domain_page,
                    manifest=export_manifest,
                    account=account,
                    config=params,
                )
            else:
                domain_adapter = create_adapter(platform=platform, account=account, config=params)
                export_result = await domain_adapter.export(
                    page=domain_page,
                    data_domain=data_domain,
                )
            file_path = (
                self._ensure_export_complete(
                    export_result.file_path,
                    component_name=f"{platform}/{data_domain}_export",
                    success_message=getattr(export_result, "message", None),
                )
                if export_result.success
                else None
            )
            duration_ms = int((datetime.now() - domain_export_start).total_seconds() * 1000)
            await self._update_status(
                task_id, progress, f"[并行] 采集 {data_domain} " + ("成功" if export_result.success else "失败"),
                current_domain=data_domain,
                details={"step_id": f"export_{data_domain}", "component": f"{data_domain}_export", "data_domain": data_domain, "success": export_result.success, "duration_ms": duration_ms}
            )
            logger.info(f"Task {task_id}: [{domain_index+1}/{total_domains}] {data_domain} completed (success={export_result.success})")
            return (file_path, export_result.success)
        except Exception as e:
            duration_ms = int((datetime.now() - domain_export_start).total_seconds() * 1000)
            await self._update_status(
                task_id, progress, f"[并行] 采集 {data_domain} 失败",
                current_domain=data_domain,
                details={"step_id": f"export_{data_domain}", "component": f"{data_domain}_export", "data_domain": data_domain, "success": False, "duration_ms": duration_ms, "error": str(e)}
            )
            logger.error(f"Task {task_id}: [{domain_index+1}/{total_domains}] {data_domain} failed - {e}")
            return (None, False)
        
        finally:
            # 清理
            if domain_page:
                try:
                    await domain_page.close()
                except:
                    pass
            if domain_context:
                try:
                    await domain_context.close()
                except:
                    pass
