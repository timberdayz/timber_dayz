from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import inspect
import os
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl, urlparse, urlsplit

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

STANDARD_HEADLESS_VIEWPORT = {"width": 1920, "height": 1080}

_executor_pool: Optional[ThreadPoolExecutor] = None


def _extract_storage_state_payload(storage_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(storage_state, dict):
        return {}
    wrapped = storage_state.get("storage_state")
    if isinstance(wrapped, dict):
        return wrapped
    return storage_state


def _storage_state_cookies(storage_state: Optional[Dict[str, Any]]) -> list[Dict[str, Any]]:
    payload = _extract_storage_state_payload(storage_state)
    cookies = payload.get("cookies")
    return cookies if isinstance(cookies, list) else []


def _storage_state_origins(storage_state: Optional[Dict[str, Any]]) -> list[Dict[str, Any]]:
    payload = _extract_storage_state_payload(storage_state)
    origins = payload.get("origins")
    return origins if isinstance(origins, list) else []


def _tiktok_quality_cookie_summary(storage_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cookies = _storage_state_cookies(storage_state)
    names = {str(cookie.get("name") or "").strip() for cookie in cookies if isinstance(cookie, dict)}
    domains = {
        str(cookie.get("domain") or "").strip().lower()
        for cookie in cookies
        if isinstance(cookie, dict)
    }
    seller_domains = {
        domain
        for domain in domains
        if "tiktokshopglobalselling.com" in domain
    }
    return {
        "cookies": cookies,
        "cookie_count": len(cookies),
        "cookie_names": names,
        "domains": domains,
        "seller_domains": seller_domains,
    }


def tiktok_storage_state_quality_score(storage_state: Optional[Dict[str, Any]]) -> int:
    summary = _tiktok_quality_cookie_summary(storage_state)
    names = summary["cookie_names"]
    seller_domains = summary["seller_domains"]
    score = 0
    if "sessionid" in names:
        score += 3
    if "sid_tt" in names:
        score += 3
    if "passport_csrf_token" in names:
        score += 2
    if "user_oec_info" in names:
        score += 3
    if "global_seller_id_unified_seller_env" in names:
        score += 2
    if "app_id_unified_seller_env" in names:
        score += 1
    if "oec_seller_id_unified_seller_env" in names:
        score += 1
    if any(domain.startswith("seller.") for domain in seller_domains):
        score += 2
    if len(seller_domains) >= 2:
        score += 1
    if summary["cookie_count"] >= 20:
        score += 2
    if summary["cookie_count"] >= 30:
        score += 2
    return score


def tiktok_storage_state_meets_quality_gate(storage_state: Optional[Dict[str, Any]]) -> bool:
    summary = _tiktok_quality_cookie_summary(storage_state)
    names = summary["cookie_names"]
    seller_domains = summary["seller_domains"]
    required_auth = {"sessionid", "sid_tt", "passport_csrf_token"}
    auth_hits = len(required_auth.intersection(names))
    seller_hits = len(
        {
            "user_oec_info",
            "global_seller_id_unified_seller_env",
            "app_id_unified_seller_env",
            "oec_seller_id_unified_seller_env",
        }.intersection(names)
    )
    return (
        auth_hits >= 2
        and seller_hits >= 1
        and bool(seller_domains)
        and summary["cookie_count"] >= 12
    )


def _tiktok_should_promote_storage_state(
    old_state: Optional[Dict[str, Any]],
    new_state: Optional[Dict[str, Any]],
) -> bool:
    old_quality = tiktok_storage_state_meets_quality_gate(old_state)
    new_quality = tiktok_storage_state_meets_quality_gate(new_state)
    if not new_quality:
        return False
    if not old_quality:
        return True
    return tiktok_storage_state_quality_score(new_state) >= tiktok_storage_state_quality_score(old_state)


def _tiktok_session_cookie_gate_from_state(storage_state: Optional[Dict[str, Any]]) -> bool:
    return tiktok_storage_state_meets_quality_gate(storage_state)


async def apply_stealth_init_scripts(context: Any) -> None:
    """
    Compatibility shim for legacy executor paths.

    Historically some flows injected Playwright init scripts for "stealth".
    The current collection runtime policy intentionally avoids injecting any
    browser scripts in formal runtime sessions (see backend tests).

    Keep this as a no-op to prevent AttributeError crashes while preserving
    the "no injection" constraint.
    """

    _ = context
    return None


def apply_stealth_init_scripts_sync(context: Any) -> None:
    """
    Sync variant of `apply_stealth_init_scripts`, also a no-op by policy.
    """

    _ = context
    return None


def _storage_state_supports_indexed_db(*, platform: str) -> bool:
    normalized = str(platform or "").strip().lower()
    return normalized == "tiktok"


def _require_indexed_db_for_platform(*, platform: str) -> bool:
    """
    Debug/verification flag:
    - When enabled, fail fast if the installed Playwright does not support
      `storage_state(indexed_db=True)` so we can validate the root-cause hypothesis.
    """
    normalized = str(platform or "").strip().lower()
    if normalized != "tiktok":
        return False
    return os.getenv("TIKTOK_STORAGE_STATE_REQUIRE_INDEXED_DB", "false").lower() == "true"


async def read_context_storage_state(
    *,
    platform: str,
    context: Any,
) -> Dict[str, Any]:
    """
    Read a storage_state snapshot for runtime session reuse.

    TikTok seller flows may rely on IndexedDB-backed session artifacts; attempt to
    include IndexedDB when supported by the installed Playwright version.
    """
    kwargs: Dict[str, Any] = {}
    if _storage_state_supports_indexed_db(platform=platform):
        kwargs["indexed_db"] = True
    try:
        return await context.storage_state(**kwargs)
    except TypeError:
        if _require_indexed_db_for_platform(platform=platform):
            raise
        logger.info(
            "storage_state(indexed_db=...) unsupported; falling back to cookies/localStorage only (%s)",
            platform,
        )
        return await context.storage_state()


def read_context_storage_state_sync(
    *,
    platform: str,
    context: Any,
) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {}
    if _storage_state_supports_indexed_db(platform=platform):
        kwargs["indexed_db"] = True
    try:
        return context.storage_state(**kwargs)
    except TypeError:
        if _require_indexed_db_for_platform(platform=platform):
            raise
        logger.info(
            "storage_state(indexed_db=...) unsupported; falling back to cookies/localStorage only (%s)",
            platform,
        )
        return context.storage_state()


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
                storage_state = read_context_storage_state_sync(
                    platform=platform,
                    context=context,
                )
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

    if str(platform or "").strip().lower() == "tiktok":
        if not tiktok_storage_state_meets_quality_gate(storage_state):
            logger.warning(
                "Skip promoting bootstrapped TikTok storage_state without seller-quality session (score=%s) for %s/%s",
                tiktok_storage_state_quality_score(storage_state),
                platform,
                account_id,
            )
            return {"storage_state": storage_state}

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
    candidate = await load_runtime_session_candidate(
        platform=platform,
        session_owner_id=session_owner_id,
        account=account,
        max_age_days=max_age_days,
    )
    return candidate.storage_state


async def load_runtime_session_candidate(
    *,
    platform: str,
    session_owner_id: str,
    account: Optional[Dict[str, Any]] = None,
    max_age_days: int = 30,
) -> RuntimeSessionCandidate:
    session_data = await _load_session_async(
        platform,
        session_owner_id,
        max_age_days=max_age_days,
    )
    metadata = session_data.get("metadata") if isinstance(session_data, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    manual_seeded = bool(metadata.get("manual_seeded") or metadata.get("protected"))

    if session_data and isinstance(session_data.get("storage_state"), dict):
        candidate = session_data["storage_state"]
        if str(platform or "").strip().lower() == "tiktok" and not manual_seeded:
            if not tiktok_storage_state_meets_quality_gate(candidate):
                logger.warning(
                    "Ignore low-quality persisted TikTok storage_state during runtime bootstrap (score=%s) for %s/%s",
                    tiktok_storage_state_quality_score(candidate),
                    platform,
                    session_owner_id,
                )
            else:
                return RuntimeSessionCandidate(storage_state=candidate, metadata=metadata)
        else:
            return RuntimeSessionCandidate(storage_state=candidate, metadata=metadata)

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
        boot_metadata = bootstrapped.get("metadata") if isinstance(bootstrapped, dict) else {}
        boot_metadata = boot_metadata if isinstance(boot_metadata, dict) else {}
        return RuntimeSessionCandidate(
            storage_state=bootstrapped["storage_state"],
            metadata=boot_metadata,
        )
    return RuntimeSessionCandidate(storage_state=None, metadata=metadata)


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


def _apply_runtime_viewport_policy(
    context_options: Dict[str, Any],
    *,
    headless: Optional[bool],
) -> Dict[str, Any]:
    normalized = dict(context_options or {})
    if headless is False:
        normalized["viewport"] = dict(STANDARD_HEADLESS_VIEWPORT)
    elif headless is True:
        normalized["viewport"] = dict(STANDARD_HEADLESS_VIEWPORT)
    return normalized


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
    session_metadata: Dict[str, Any] = field(default_factory=dict)
    available_page_urls: list[str] = field(default_factory=list)
    selected_page_url: Optional[str] = None
    context_summary: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeStrategyDecision:
    mode: str
    reason: str
    used_storage_state: bool
    used_persistent_profile: bool
    fallback_allowed: bool


@dataclass(frozen=True)
class RuntimeSessionCandidate:
    storage_state: Optional[Dict[str, Any]]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def manual_seeded(self) -> bool:
        return bool(self.metadata.get("manual_seeded") or self.metadata.get("protected"))


def choose_runtime_strategy(
    *,
    platform: str,
    session_owner_id: str | None,
    has_storage_state: bool,
    has_manual_storage_state: bool,
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

    if has_persistent_profile:
        return RuntimeStrategyDecision(
            mode="persistent_profile",
            reason="persistent_profile_available",
            used_storage_state=False,
            used_persistent_profile=True,
            fallback_allowed=True,
        )

    if has_manual_storage_state:
        return RuntimeStrategyDecision(
            mode="storage_state_fanout",
            reason="manual_storage_state_available",
            used_storage_state=True,
            used_persistent_profile=False,
            fallback_allowed=bool(has_persistent_profile or session_owner_id),
        )

    if has_storage_state:
        return RuntimeStrategyDecision(
            mode="storage_state_fanout",
            reason="storage_state_available",
            used_storage_state=True,
            used_persistent_profile=False,
            fallback_allowed=bool(has_persistent_profile or session_owner_id),
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
    if str(platform or "").strip().lower() == "tiktok":
        context_options.pop("permissions", None)
    if "locale" not in context_options:
        context_options["locale"] = "zh-CN"
    # Runtime viewport is a shared baseline and should not inherit oversized
    # account-fingerprint viewport values.
    context_options = _apply_runtime_viewport_policy(
        context_options,
        headless=headless,
    )
    return context_options


def summarize_runtime_context_options(context_options: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(context_options or {})
    extra_headers = normalized.get("extra_http_headers", {}) or {}
    return {
        "user_agent": normalized.get("user_agent"),
        "locale": normalized.get("locale"),
        "timezone_id": normalized.get("timezone_id"),
        "accept_language": extra_headers.get("Accept-Language"),
        "viewport": normalized.get("viewport"),
        "has_storage_state": "storage_state" in normalized,
        "accept_downloads": normalized.get("accept_downloads"),
    }


def list_context_page_urls(context: Any) -> list[str]:
    urls: list[str] = []
    for page in list(getattr(context, "pages", []) or []):
        try:
            urls.append(str(getattr(page, "url", "") or ""))
        except Exception:
            urls.append("")
    return urls


def normalize_persistent_profile_context_options(
    *,
    platform: str,
    context_options: Dict[str, Any],
) -> Dict[str, Any]:
    normalized = dict(context_options or {})
    if str(platform or "").strip().lower() != "tiktok":
        return normalized

    # TikTok persistent-profile restore is more reliable when we let Chromium
    # reuse the original profile environment as-is instead of layering runtime
    # fingerprint overrides on top of it.
    stripped = dict(normalized)
    for key in (
        "user_agent",
        "viewport",
        "locale",
        "timezone_id",
        "extra_http_headers",
        "device_scale_factor",
        "is_mobile",
        "has_touch",
        "color_scheme",
        "reduced_motion",
        "forced_colors",
        "permissions",
    ):
        stripped.pop(key, None)
    return stripped


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
    context_options = normalize_persistent_profile_context_options(
        platform=platform,
        context_options=context_options,
    )
    launch_options = enforce_official_playwright_browser(dict(launch_kwargs or {}))

    context = await browser_type.launch_persistent_context(
        user_data_dir=str(profile_path),
        **launch_options,
        **context_options,
    )
    page_urls = list_context_page_urls(context)
    if getattr(context, "pages", None):
        page = context.pages[0]
        if str(platform or "").strip().lower() != "tiktok":
            for extra_page in context.pages[1:]:
                try:
                    await extra_page.close()
                except Exception:
                    pass
    else:
        page = await context.new_page()
        page_urls = list_context_page_urls(context)
    selected_page_url = str(getattr(page, "url", "") or "")
    context_summary = summarize_runtime_context_options(context_options)
    if str(platform or "").strip().lower() == "tiktok":
        logger.info(
            "TikTok persistent runtime: profile=%s pages=%s selected=%s context=%s",
            str(profile_path),
            page_urls,
            selected_page_url,
            context_summary,
        )
    return RuntimeContextBundle(
        mode="persistent_profile",
        context=context,
        page=page,
        reused_session=reused_session,
        storage_state=None,
        context_options=context_options,
        session_owner_id=session_owner_id,
        profile_path=str(profile_path),
        available_page_urls=page_urls,
        selected_page_url=selected_page_url,
        context_summary=context_summary,
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
        available_page_urls=list_context_page_urls(context),
        selected_page_url=str(getattr(page, "url", "") or ""),
        context_summary=summarize_runtime_context_options(context_options),
    )


async def snapshot_runtime_storage_state(
    *,
    platform: str,
    session_owner_id: str,
    context: Any,
    persist: bool = True,
) -> Optional[Dict[str, Any]]:
    normalized_platform = str(platform or "").strip().lower()
    try:
        storage_state = await read_context_storage_state(
            platform=platform,
            context=context,
        )
    except Exception as exc:
        logger.warning(
            "Failed to read storage state for %s/%s: %s",
            platform,
            session_owner_id,
            exc,
        )
        return None

    # TikTok: localStorage/indexedDB-backed session artifacts are often written during
    # the homepage bootstrap/redirect window. If we snapshot too early, `origins` may be empty,
    # and persisting that snapshot would downgrade future reuse quality.
    if normalized_platform == "tiktok":
        def _seller_local_storage_max(state: Dict[str, Any]) -> int:
            try:
                origins = state.get("origins") if isinstance(state, dict) else None
                origins = origins if isinstance(origins, list) else []
                best = 0
                for origin_entry in origins:
                    if not isinstance(origin_entry, dict):
                        continue
                    origin_url = str(origin_entry.get("origin") or "").strip().lower()
                    if "seller.tiktokshopglobalselling.com" not in origin_url:
                        continue
                    local_storage = origin_entry.get("localStorage")
                    if isinstance(local_storage, list):
                        best = max(best, len(local_storage))
                return int(best)
            except Exception:
                return 0

        attempts = 0
        while attempts < 20:
            attempts += 1
            try:
                origins = storage_state.get("origins") if isinstance(storage_state, dict) else None
                origins = origins if isinstance(origins, list) else []
                if origins and _seller_local_storage_max(storage_state) > 0:
                    break
            except Exception:
                origins = []

            try:
                await asyncio.sleep(1.0)
            except Exception:
                pass

            try:
                storage_state = await read_context_storage_state(
                    platform=platform,
                    context=context,
                )
            except Exception:
                break

        try:
            origins = storage_state.get("origins") if isinstance(storage_state, dict) else None
            origin_count = len(origins) if isinstance(origins, list) else 0
            local_storage_items = 0
            seller_origin_items = 0
            if isinstance(origins, list):
                for origin_entry in origins:
                    if not isinstance(origin_entry, dict):
                        continue
                    local_storage = origin_entry.get("localStorage")
                    if isinstance(local_storage, list):
                        local_storage_items += len(local_storage)
                        origin_url = str(origin_entry.get("origin") or "").strip().lower()
                        if "seller.tiktokshopglobalselling.com" in origin_url:
                            seller_origin_items = max(seller_origin_items, len(local_storage))
            logger.info(
                "TikTok storage_state snapshot attempts=%s origins=%s localStorage=%s sellerLocalStorage=%s (%s/%s)",
                attempts,
                origin_count,
                local_storage_items,
                seller_origin_items,
                platform,
                session_owner_id,
            )
        except Exception:
            pass

    if persist and session_owner_id:
        try:
            if normalized_platform == "tiktok":
                origins = storage_state.get("origins") if isinstance(storage_state, dict) else None
                origins = origins if isinstance(origins, list) else []
                seller_local_storage = 0
                if isinstance(storage_state, dict):
                    seller_local_storage = _seller_local_storage_max(storage_state)
                if not origins or seller_local_storage <= 0:
                    logger.warning(
                        "Skip persisting TikTok storage_state without seller localStorage (origins=%s sellerLocalStorage=%s) (%s/%s)",
                        len(origins),
                        seller_local_storage,
                        platform,
                        session_owner_id,
                    )
                    return storage_state
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
        region = str(
            (account or {}).get("shop_region")
            or (account or {}).get("region")
            or ""
        ).strip().upper()
        if region:
            return f"{base_url}/homepage?shop_region={region}"
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
        maybe_wait = page.wait_for_timeout(settle_ms)
        if inspect.isawaitable(maybe_wait):
            await maybe_wait


async def wait_for_runtime_page_stable(
    *,
    page: Any,
    platform: str,
    timeout_ms: int = 30000,
    poll_ms: int = 500,
    stable_cycles: int = 3,
) -> None:
    normalized_platform = str(platform or "").strip().lower()
    stable_hits = 0
    waited = 0
    last_url = None

    while waited <= timeout_ms:
        await _wait_for_probe_page_ready(page, settle_ms=min(max(poll_ms, 100), 800))

        current_url = str(getattr(page, "url", "") or "").strip()
        same_url = bool(current_url) and current_url == last_url
        last_url = current_url or last_url

        is_loading = False
        if normalized_platform == "tiktok":
            try:
                from modules.platforms.tiktok.components._navigation import page_looks_loading

                is_loading = await page_looks_loading(page)
            except Exception:
                is_loading = False

        dom_ready = True
        try:
            dom_ready = bool(
                await page.evaluate(
                    """() => {
                      try {
                        if (!document || !document.body) return false;
                        const ready = document.readyState;
                        if (ready !== "interactive" && ready !== "complete") return false;
                        const rect = document.body.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0;
                      } catch (error) {
                        return false;
                      }
                    }"""
                )
            )
        except Exception:
            dom_ready = bool(current_url)

        if current_url and same_url and dom_ready and not is_loading:
            stable_hits += 1
            if stable_hits >= stable_cycles:
                return
        else:
            stable_hits = 0

        waited += poll_ms
        if hasattr(page, "wait_for_timeout"):
            maybe_wait = page.wait_for_timeout(poll_ms)
            if inspect.isawaitable(maybe_wait):
                await maybe_wait
        else:
            await asyncio.sleep(poll_ms / 1000)


async def prime_runtime_page_for_login_gate(
    *,
    page: Any,
    platform: str,
    account: Optional[Dict[str, Any]],
) -> None:
    if not hasattr(page, "goto"):
        return

    current_url = str(getattr(page, "url", "") or "").strip().lower()
    if current_url and current_url != "about:blank":
        await wait_for_runtime_page_stable(page=page, platform=platform)
        return

    login_url = str(
        (account or {}).get("login_url") or get_platform_login_entry(platform) or ""
    ).strip()
    if not login_url:
        return
    await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
    await wait_for_runtime_page_stable(page=page, platform=platform)


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
    if str(platform or "").strip().lower() == "tiktok":
        current_url = str(getattr(page, "url", "") or "")
        wrapped_state: Dict[str, Any] = {}
        try:
            raw_state = await read_context_storage_state(
                platform=platform,
                context=page.context,
            )
            wrapped_state = {"storage_state": raw_state} if isinstance(raw_state, dict) else {}
        except Exception:
            wrapped_state = {}
        has_quality_session = _tiktok_session_cookie_gate_from_state(wrapped_state)
        if (
            str(getattr(detection_result, "status", "")).lower() == "logged_in"
            and has_quality_session
            and "tiktokshopglobalselling.com" in current_url.lower()
            and "/account/login" not in current_url.lower()
        ):
            return True, GateResult(
                stage="login_gate",
                status=GateStatus.READY,
                reason="tiktok seller-quality session confirmed",
                confidence=max(float(getattr(detection_result, "confidence", 0.0) or 0.0), 0.9),
                current_url=current_url,
                matched_signal="seller_quality_session",
            )
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

    normalized_platform = str(platform or "").strip().lower()
    # TikTok seller pages often perform their own redirect + cache initialization.
    # During that phase, forcing extra goto probes can interrupt the flow and make
    # verification/challenge loops impossible to complete. Prefer observing the
    # current page state (no extra goto) and only do a single navigation when the
    # page is still at about:blank.
    if normalized_platform == "tiktok":
        from modules.platforms.tiktok.components.login import TiktokLogin
        from modules.platforms.tiktok.components._navigation import wait_until_bootstrap_finishes
        from modules.components.base import ExecutionContext
        from modules.utils.login_status_detector import LoginStatus, LoginStatusDetector

        detector = LoginStatusDetector(platform, debug=False)
        tiktok_login_helper = TiktokLogin(
            ExecutionContext(
                platform="tiktok",
                account=account or {},
                logger=logger,
                config={"params": {"login_success_target": "homepage"}},
            )
        )

        async def _tiktok_check_ready_bootstrap(*, allow_transient_login_form: bool) -> tuple[bool, GateResult]:
            details: Dict[str, Any] = {}
            result = await detector.detect(page, wait_for_redirect=True)
            if details is not None:
                # Preserve a compatible shape for callers that previously relied on
                # the detector attaching details. `detect()` already returns a
                # LoginDetectionResult with optional details; keep `details` here
                # for future extensions without breaking the call site.
                details.update(getattr(result, "details", {}) or {})
            normalized_url = str(result.current_url or "").strip().lower()

            # During TikTok auto-redirect bootstrap, a login form can briefly appear
            # even when the session is valid and about to redirect to homepage.
            if (
                allow_transient_login_form
                and result.status == LoginStatus.NOT_LOGGED_IN
                and str(result.detected_by or "").strip().lower() == "element"
                and any(
                    marker in normalized_url
                    for marker in ("/login", "/signin", "/account/login", "redirect=")
                )
            ):
                return (
                    False,
                    GateResult(
                        stage="login_gate",
                        status=GateStatus.FAILED,
                        reason="bootstrap: login surface may redirect; waiting",
                        confidence=float(getattr(result, "confidence", 0.0) or 0.0),
                        current_url=result.current_url,
                        matched_signal=getattr(result, "matched_pattern", None),
                    ),
                )

            if await tiktok_login_helper._target_looks_ready(page):
                return (
                    True,
                    GateResult(
                        stage="login_gate",
                        status=GateStatus.READY,
                        reason="homepage target ready",
                        confidence=max(
                            0.9,
                            float(getattr(result, "confidence", 0.0) or 0.0),
                        ),
                        current_url=str(getattr(page, "url", "") or ""),
                        matched_signal="homepage_ready",
                    ),
                )

            if await tiktok_login_helper._session_shell_looks_ready(page):
                return (
                    False,
                    GateResult(
                        stage="login_gate",
                        status=GateStatus.FAILED,
                        reason="homepage shell ready; waiting target context",
                        confidence=float(getattr(result, "confidence", 0.0) or 0.0),
                        current_url=str(getattr(page, "url", "") or ""),
                        matched_signal="shell_ready_waiting",
                    ),
                )

            gate_result = evaluate_login_ready(
                status=result.status.value if hasattr(result.status, "value") else str(result.status),
                confidence=float(getattr(result, "confidence", 0.0) or 0.0),
                current_url=result.current_url,
                matched_signal=getattr(result, "matched_pattern", None),
                detected_by=getattr(result, "detected_by", None),
            )
            gate_url = str(gate_result.current_url or "").strip().lower()
            if "/account/login" in gate_url or "/login" in gate_url:
                return (
                    False,
                    GateResult(
                        stage="login_gate",
                        status=GateStatus.FAILED,
                        reason="login entry still bootstrapping",
                        confidence=gate_result.confidence,
                        current_url=gate_result.current_url,
                        matched_signal=gate_result.matched_signal,
                    ),
                )
            return (gate_result.status == GateStatus.READY), gate_result

        current_url = str(getattr(page, "url", "") or "").strip()
        if not current_url or current_url == "about:blank":
            try:
                # Prefer the already-resolved account login_url (consistent with other platforms),
                # then fall back to platform login entry service.
                login_url = str((account or {}).get("login_url") or "").strip()
                if not login_url:
                    entry = await get_platform_login_entry(platform=platform, account=account)
                    login_url = str((entry or {}).get("login_url") or "").strip()
                if login_url:
                    await page.goto(login_url, wait_until="domcontentloaded", timeout=60000)
                    await wait_until_bootstrap_finishes(page, timeout_ms=30000, poll_ms=500, stable_cycles=4)
                    ready, gate_result = await _tiktok_check_ready_bootstrap(
                        allow_transient_login_form=True
                    )
                    if ready:
                        return ready, gate_result
            except Exception:
                # Keep probing as "not ready" without forcing more navigation.
                pass

        # Observe-only stability wait: allow redirects/spinners to settle.
        for _ in range(60):  # ~30s
            try:
                await wait_until_bootstrap_finishes(page, timeout_ms=4000, poll_ms=500, stable_cycles=2)
                ready, gate_result = await _tiktok_check_ready_bootstrap(
                    allow_transient_login_form=True
                )
                if ready:
                    return ready, gate_result
            except Exception:
                # If the page is reloading, keep observing.
                continue
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
