from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from backend.services.platform_login_entry_service import get_platform_login_entry
from modules.apps.collection_center.browser_config_helper import (
    enforce_official_playwright_browser,
    get_browser_context_args,
)
from modules.apps.collection_center.transition_gates import (
    GateResult,
    GateStatus,
    evaluate_login_ready,
)
from modules.core.logger import get_logger

logger = get_logger(__name__)

_executor_pool: Optional[ThreadPoolExecutor] = None


def _get_executor_pool() -> ThreadPoolExecutor:
    global _executor_pool
    if _executor_pool is None:
        _executor_pool = ThreadPoolExecutor(
            max_workers=4,
            thread_name_prefix="runtime_session_io",
        )
    return _executor_pool


async def _load_session_async(
    platform: str,
    account_id: str,
    *,
    max_age_days: int = 30,
) -> Optional[Dict[str, Any]]:
    from modules.utils.sessions.session_manager import SessionManager

    loop = asyncio.get_event_loop()

    def _load() -> Optional[Dict[str, Any]]:
        manager = SessionManager()
        return manager.load_session(platform, account_id, max_age_days=max_age_days)

    return await loop.run_in_executor(_get_executor_pool(), _load)


def _bootstrap_session_from_profile_sync(
    platform: str,
    account_id: str,
    account_config: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    from playwright.sync_api import sync_playwright
    from modules.utils.sessions.session_manager import SessionManager

    manager = SessionManager()
    profile_path = manager.get_persistent_profile_path(platform, account_id)
    if not _profile_contains_state(profile_path):
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
    except Exception as exc:
        logger.warning(
            "Bootstrap session from profile failed for %s/%s: %s",
            platform,
            account_id,
            exc,
        )
        return None

    manager.save_session(
        platform,
        account_id,
        storage_state,
        metadata={"bootstrapped_from_profile": True},
    )
    return {"storage_state": storage_state}


async def _save_session_async(
    platform: str,
    account_id: str,
    storage_state: Dict[str, Any],
) -> bool:
    from modules.utils.sessions.session_manager import SessionManager

    loop = asyncio.get_event_loop()

    def _save() -> bool:
        manager = SessionManager()
        return manager.save_session(platform, account_id, storage_state)

    return await loop.run_in_executor(_get_executor_pool(), _save)


async def load_or_bootstrap_runtime_storage_state(
    *,
    platform: str,
    session_owner_id: str,
    account: Optional[Dict[str, Any]] = None,
    max_age_days: int = 30,
) -> Optional[Dict[str, Any]]:
    session_data = await _load_session_async(
        platform,
        session_owner_id,
        max_age_days=max_age_days,
    )
    if session_data and isinstance(session_data.get("storage_state"), dict):
        return session_data["storage_state"]

    loop = asyncio.get_event_loop()
    bootstrapped = await loop.run_in_executor(
        _get_executor_pool(),
        lambda: _bootstrap_session_from_profile_sync(
            platform,
            session_owner_id,
            account,
        ),
    )
    if bootstrapped and isinstance(bootstrapped.get("storage_state"), dict):
        return bootstrapped["storage_state"]
    return None


async def _get_fingerprint_context_options_async(
    platform: str,
    account_id: str,
    account: Optional[Dict[str, Any]] = None,
    proxy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from modules.utils.sessions.device_fingerprint import DeviceFingerprintManager

    loop = asyncio.get_event_loop()

    def _get() -> Dict[str, Any]:
        manager = DeviceFingerprintManager()
        return manager.get_playwright_context_options(
            platform,
            account_id,
            account,
            proxy=proxy,
        )

    return await loop.run_in_executor(_get_executor_pool(), _get)


def _build_playwright_context_options_from_fingerprint(
    fingerprint_options: Dict[str, Any],
) -> Dict[str, Any]:
    allowed = {
        "user_agent",
        "viewport",
        "locale",
        "timezone_id",
        "device_scale_factor",
        "is_mobile",
        "has_touch",
        "color_scheme",
        "reduced_motion",
        "forced_colors",
        "extra_http_headers",
        "ignore_https_errors",
        "java_script_enabled",
        "accept_downloads",
    }
    result: Dict[str, Any] = {}
    for key, value in (fingerprint_options or {}).items():
        if key in allowed and value is not None:
            result[key] = value
    return result


def _profile_contains_state(profile_path: Path) -> bool:
    try:
        return profile_path.exists() and any(profile_path.iterdir())
    except Exception:
        return False


def runtime_profile_exists(platform: str, session_owner_id: str) -> bool:
    from modules.utils.sessions.session_manager import SessionManager

    manager = SessionManager()
    profile_path = manager.get_persistent_profile_path(platform, session_owner_id)
    return _profile_contains_state(profile_path)


@dataclass(frozen=True)
class RuntimeSessionScope:
    session_owner_id: str
    shop_account_id: str
    use_account_session_fingerprint: bool


@dataclass
class RuntimeContextBundle:
    mode: str
    context: Any
    page: Any
    reused_session: bool
    storage_state: Optional[Dict[str, Any]] = None
    context_options: Dict[str, Any] = field(default_factory=dict)
    session_owner_id: str = ""
    profile_path: Optional[str] = None
    strategy_reason: Optional[str] = None
    session_source: Optional[str] = None


@dataclass(frozen=True)
class RuntimeStrategyDecision:
    mode: str
    reason: str
    used_storage_state: bool
    used_persistent_profile: bool
    fallback_allowed: bool


def choose_runtime_strategy(
    *,
    platform: str,
    session_owner_id: str | None,
    has_storage_state: bool,
    has_persistent_profile: bool,
    force_persistent_profile: bool,
    execution_kind: str,
    component_type: str | None,
    parallel_mode: bool,
) -> RuntimeStrategyDecision:
    if force_persistent_profile:
        return RuntimeStrategyDecision(
            mode="persistent_profile",
            reason="forced",
            used_storage_state=False,
            used_persistent_profile=True,
            fallback_allowed=False,
        )

    if parallel_mode:
        return RuntimeStrategyDecision(
            mode="persistent_profile",
            reason="parallel_bootstrap",
            used_storage_state=False,
            used_persistent_profile=True,
            fallback_allowed=True,
        )

    if has_storage_state:
        return RuntimeStrategyDecision(
            mode="storage_state_fanout",
            reason="storage_state_available",
            used_storage_state=True,
            used_persistent_profile=False,
            fallback_allowed=bool(has_persistent_profile or session_owner_id),
        )

    if has_persistent_profile:
        return RuntimeStrategyDecision(
            mode="persistent_profile",
            reason="storage_state_missing",
            used_storage_state=False,
            used_persistent_profile=True,
            fallback_allowed=True,
        )

    return RuntimeStrategyDecision(
        mode="storage_state_fanout",
        reason="fresh_login_required",
        used_storage_state=False,
        used_persistent_profile=False,
        fallback_allowed=bool(session_owner_id),
    )


def resolve_runtime_session_scope(
    *,
    requested_account_id: Any,
    account: Dict[str, Any],
) -> RuntimeSessionScope:
    try:
        shop_account_id = str(
            requested_account_id
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
            return RuntimeSessionScope(
                session_owner_id="",
                shop_account_id=shop_account_id,
                use_account_session_fingerprint=False,
            )
        return RuntimeSessionScope(
            session_owner_id=session_owner_id,
            shop_account_id=shop_account_id,
            use_account_session_fingerprint=True,
        )
    except Exception as exc:
        logger.warning("Failed to resolve runtime session scope: %s", exc)
        return RuntimeSessionScope(
            session_owner_id="",
            shop_account_id="",
            use_account_session_fingerprint=False,
        )


async def build_runtime_context_options(
    *,
    platform: str,
    session_owner_id: str,
    account: Optional[Dict[str, Any]],
    storage_state: Optional[Dict[str, Any]] = None,
    proxy: Optional[Dict[str, Any]] = None,
    accept_downloads: bool = True,
    headless: Optional[bool] = None,
) -> Dict[str, Any]:
    context_options: Dict[str, Any]
    if session_owner_id:
        try:
            fingerprint_options = await _get_fingerprint_context_options_async(
                platform,
                session_owner_id,
                account,
                proxy=proxy,
            )
            context_options = _build_playwright_context_options_from_fingerprint(
                fingerprint_options
            )
        except Exception as exc:
            logger.warning(
                "Failed to load fingerprint context options for %s/%s: %s",
                platform,
                session_owner_id,
                exc,
            )
            context_options = get_browser_context_args()
    else:
        context_options = get_browser_context_args()

    context_options = dict(context_options)
    context_options["accept_downloads"] = accept_downloads
    if storage_state:
        context_options["storage_state"] = storage_state
    if "locale" not in context_options:
        context_options["locale"] = "zh-CN"
    if not context_options.get("viewport") and headless is not None:
        context_options["viewport"] = (
            {"width": 1920, "height": 1080} if headless else None
        )
    return context_options


async def open_persistent_runtime_bundle(
    *,
    browser_type: Any,
    platform: str,
    session_owner_id: str,
    account: Optional[Dict[str, Any]],
    launch_kwargs: Optional[Dict[str, Any]] = None,
    proxy: Optional[Dict[str, Any]] = None,
    profile_path_override: Optional[str] = None,
) -> RuntimeContextBundle:
    from modules.utils.sessions.session_manager import SessionManager

    manager = SessionManager()
    profile_path = (
        Path(profile_path_override)
        if profile_path_override
        else manager.get_persistent_profile_path(platform, session_owner_id)
    )
    reused_session = _profile_contains_state(profile_path)
    context_options = await build_runtime_context_options(
        platform=platform,
        session_owner_id=session_owner_id,
        account=account,
        proxy=proxy,
        accept_downloads=True,
        headless=bool((launch_kwargs or {}).get("headless", True)),
    )
    launch_options = enforce_official_playwright_browser(dict(launch_kwargs or {}))

    context = await browser_type.launch_persistent_context(
        user_data_dir=str(profile_path),
        **launch_options,
        **context_options,
    )
    if getattr(context, "pages", None):
        page = context.pages[0]
        for extra_page in context.pages[1:]:
            try:
                await extra_page.close()
            except Exception:
                pass
    else:
        page = await context.new_page()
    return RuntimeContextBundle(
        mode="persistent_profile",
        context=context,
        page=page,
        reused_session=reused_session,
        storage_state=None,
        context_options=context_options,
        session_owner_id=session_owner_id,
        profile_path=str(profile_path),
    )


async def open_storage_state_runtime_bundle(
    *,
    browser: Any,
    platform: str,
    session_owner_id: str,
    account: Optional[Dict[str, Any]],
    storage_state: Optional[Dict[str, Any]],
    proxy: Optional[Dict[str, Any]] = None,
    headless: Optional[bool] = None,
) -> RuntimeContextBundle:
    context_options = await build_runtime_context_options(
        platform=platform,
        session_owner_id=session_owner_id,
        account=account,
        storage_state=storage_state,
        proxy=proxy,
        accept_downloads=True,
        headless=headless,
    )
    context = await browser.new_context(**context_options)
    page = await context.new_page()
    return RuntimeContextBundle(
        mode="storage_state_fanout",
        context=context,
        page=page,
        reused_session=bool(storage_state),
        storage_state=storage_state,
        context_options=context_options,
        session_owner_id=session_owner_id,
    )


async def snapshot_runtime_storage_state(
    *,
    platform: str,
    session_owner_id: str,
    context: Any,
    persist: bool = True,
) -> Optional[Dict[str, Any]]:
    try:
        storage_state = await context.storage_state()
    except Exception as exc:
        logger.warning(
            "Failed to read storage state for %s/%s: %s",
            platform,
            session_owner_id,
            exc,
        )
        return None

    if persist and session_owner_id:
        try:
            await _save_session_async(platform, session_owner_id, storage_state)
        except Exception as exc:
            logger.warning(
                "Failed to persist storage state for %s/%s: %s",
                platform,
                session_owner_id,
                exc,
            )
    return storage_state


async def persist_runtime_session_state(
    *,
    platform: str,
    session_owner_id: str,
    storage_state: Dict[str, Any],
) -> bool:
    return await _save_session_async(platform, session_owner_id, storage_state)


def _normalize_probe_base_url(
    platform: str,
    account: Optional[Dict[str, Any]],
) -> str:
    login_url = str(
        (account or {}).get("login_url") or get_platform_login_entry(platform) or ""
    ).strip()
    if not login_url:
        return ""

    parsed = urlparse(login_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return login_url.rstrip("/")


def _homepage_probe_url(
    platform: str,
    account: Optional[Dict[str, Any]],
) -> Optional[str]:
    base_url = _normalize_probe_base_url(platform, account)
    if not base_url:
        return None

    if platform == "tiktok":
        return f"{base_url}/homepage"
    if platform == "miaoshou":
        return f"{base_url}/welcome"
    if platform == "shopee":
        return f"{base_url}/"
    return base_url


def _login_gate_probe_url(
    platform: str,
    account: Optional[Dict[str, Any]],
) -> Optional[str]:
    return str(
        (account or {}).get("login_url") or get_platform_login_entry(platform) or ""
    ).strip() or None


def build_runtime_login_gate_probe_urls(
    *,
    platform: str,
    account: Optional[Dict[str, Any]],
) -> list[str]:
    candidates = [
        _homepage_probe_url(platform, account),
        _login_gate_probe_url(platform, account),
    ]
    urls: list[str] = []
    for candidate in candidates:
        value = str(candidate or "").strip()
        if value and value not in urls:
            urls.append(value)
    return urls


async def _wait_for_probe_page_ready(page: Any, *, settle_ms: int = 800) -> None:
    for state, timeout in (("domcontentloaded", 5000), ("load", 5000), ("networkidle", 3000)):
        try:
            await page.wait_for_load_state(state, timeout=timeout)
        except Exception:
            continue
    if hasattr(page, "wait_for_timeout"):
        await page.wait_for_timeout(settle_ms)


async def prime_runtime_page_for_login_gate(
    *,
    page: Any,
    platform: str,
    account: Optional[Dict[str, Any]],
) -> None:
    current_url = str(getattr(page, "url", "") or "").strip().lower()
    if current_url and current_url != "about:blank":
        return

    login_url = str(
        (account or {}).get("login_url") or get_platform_login_entry(platform) or ""
    ).strip()
    if not login_url:
        return

    await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
    await _wait_for_probe_page_ready(page, settle_ms=800)


async def check_login_gate_ready(
    *,
    page: Any,
    platform: str,
) -> tuple[bool, GateResult]:
    current_url = getattr(page, "url", "")
    if not isinstance(current_url, str):
        return True, GateResult(
            stage="login_gate",
            status=GateStatus.READY,
            reason="non-string page url; skipping login gate check",
            current_url=str(current_url),
            matched_signal="mock_url",
        )

    from modules.utils.login_status_detector import LoginStatusDetector

    detector = LoginStatusDetector(platform, debug=False)
    detection_result = await detector.detect(page, wait_for_redirect=True)
    gate_result = evaluate_login_ready(
        status=detection_result.status.value,
        confidence=detection_result.confidence,
        current_url=str(getattr(page, "url", "") or ""),
        matched_signal=detection_result.matched_pattern or detection_result.detected_by,
        detected_by=getattr(detection_result, "detected_by", None),
    )
    return gate_result.status is GateStatus.READY, gate_result


async def probe_runtime_login_gate(
    *,
    page: Any,
    platform: str,
    account: Optional[Dict[str, Any]],
) -> tuple[bool, GateResult]:
    await _wait_for_probe_page_ready(page, settle_ms=500)
    ready, gate_result = await check_login_gate_ready(page=page, platform=platform)
    if ready:
        return ready, gate_result

    current_url = str(getattr(page, "url", "") or "").strip()
    for probe_url in build_runtime_login_gate_probe_urls(platform=platform, account=account):
        if probe_url == current_url:
            continue
        await page.goto(probe_url, wait_until="domcontentloaded", timeout=60000)
        await _wait_for_probe_page_ready(page, settle_ms=800)
        ready, gate_result = await check_login_gate_ready(page=page, platform=platform)
        if ready:
            return ready, gate_result

    return ready, gate_result
