#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
登录状态检测器 (v4.8.0)

功能：
1. 检测当前浏览器会话是否已登录
2. 支持平台特定的检测规则
3. 提供综合判断逻辑（URL + 元素 + Cookie）
4. 支持等待自动跳转检测
5. 详细日志记录和调试模式

使用场景：
- Inspector 录制时判断是否需要自动登录
- 数据采集前验证登录状态

v4.8.0 更新 (2025-12-25):
- 增加Cookie检测方法
- 增加等待自动跳转逻辑
- 优化元素检测（超时、重试）
- 完善各平台检测规则
- 增强综合判断逻辑
- 增加调试模式和详细日志
"""

import os
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
from pathlib import Path

from modules.core.logger import get_logger

logger = get_logger(__name__)

# 调试模式开关
DEBUG_LOGIN_DETECTION = os.environ.get("DEBUG_LOGIN_DETECTION", "false").lower() == "true"


class LoginStatus(Enum):
    """登录状态枚举"""
    LOGGED_IN = "logged_in"
    NOT_LOGGED_IN = "not_logged_in"
    UNKNOWN = "unknown"


@dataclass
class LoginDetectionResult:
    """登录检测结果"""
    status: LoginStatus
    confidence: float  # 0.0 - 1.0
    reason: str
    detected_by: str  # url, element, cookie, combined, redirect, fallback
    current_url: Optional[str] = None
    matched_pattern: Optional[str] = None
    detection_time_ms: int = 0  # 检测耗时（毫秒）
    details: Optional[Dict[str, Any]] = None  # 详细检测信息（调试用）


# 平台特定的登录检测配置
LOGIN_DETECTION_CONFIG: Dict[str, Dict[str, Any]] = {
    "shopee": {
        "login_page_url_keywords": [
            "/account/signin",
            "/login",
            "/auth",
        ],
        "logged_in_page_url_keywords": [
            "/portal",
            "/seller",
            "/dashboard",
            "/product/list",
            "/order/list",
        ],
        # 登录URL中的重定向参数（检测自动跳转用）
        "redirect_param_patterns": [
            "redirect=",
            "return_url=",
            "callback=",
        ],
        "login_form_selectors": [
            "input[name='username']",
            "input[name='password']",
            "input[type='password']",
            "button:has-text('登录')",
            "button:has-text('Log in')",
            "button:has-text('Sign in')",
        ],
        "logged_in_selectors": [
            "[data-testid='seller-menu']",
            "text=我的店铺",
            "text=店铺信息",
            ".seller-header",
            "[class*='shop-name']",
            "[class*='user-avatar']",
            ".navbar-user",
        ],
        "auth_cookies": ["SPC_EC", "SPC_U", "SPC_SI"],
        # 元素检测超时（毫秒）
        "element_check_timeout": 5000,
    },
    "tiktok": {
        "login_page_url_keywords": [
            "/login",
            "/signin",
            "/auth",
            "/passport",
        ],
        "logged_in_page_url_keywords": [
            "/seller",
            "/dashboard",
            "/manage",
            "/order",
            "/product",
            "/analytics",
        ],
        "redirect_param_patterns": [
            "redirect_url=",
            "redirect=",
            "return_url=",
        ],
        "login_form_selectors": [
            "input[type='email']",
            "input[type='password']",
            "input[name='email']",
            "input[name='username']",
            "button:has-text('Login')",
            "button:has-text('Log in')",
            "button:has-text('Sign in')",
        ],
        "logged_in_selectors": [
            "[data-testid='user-avatar']",
            "text=管理中心",
            "text=Seller Center",
            ".user-menu",
            "[class*='avatar']",
            "[class*='user-info']",
        ],
        "auth_cookies": ["sessionid", "passport_csrf_token", "ttwid"],
        "element_check_timeout": 5000,
    },
    "miaoshou": {
        "login_page_url_keywords": [
            "/login",
            "/signin",
            "redirect=",  # 妙手ERP特殊：URL包含redirect=表示未登录
        ],
        "logged_in_page_url_keywords": [
            "/welcome",
            "/dashboard",
            "/home",
            "/workbench",
            "/order",
            "/product",
            "/inventory",
        ],
        "redirect_param_patterns": [
            "redirect=",
            "?redirect=",
        ],
        # 妙手ERP特殊规则：URL包含redirect=但跳转到/welcome表示已登录
        "redirect_to_logged_in_check": {
            "from_pattern": "redirect=",
            "to_pattern": "/welcome",
            "exclude_pattern": "redirect=",  # 跳转后URL不应包含redirect=
        },
        "login_form_selectors": [
            "input[placeholder*='手机号']",
            "input[placeholder*='子账号']",
            "input[placeholder*='邮箱']",
            "input[placeholder*='密码']",
            "input[type='password']",
            "button:has-text('登录')",
            "button:has-text('立即登录')",
            "button.login-button",
        ],
        "logged_in_selectors": [
            "text=工作台",
            "text=欢迎",
            "text=首页",
            ".user-info",
            "[class*='welcome']",
            "[class*='navbar']",
            ".ant-layout-header",
            # 妙手ERP特殊：登录页特有元素不存在
        ],
        "auth_cookies": ["JSESSIONID", "token", "SESSION"],
        "element_check_timeout": 8000,  # 妙手ERP加载较慢
    },
    "amazon": {
        "login_page_url_keywords": [
            "/signin",
            "/ap/signin",
            "/ap/oa",
            "/ap/register",
        ],
        "logged_in_page_url_keywords": [
            "/home",
            "/dashboard",
            "/inventory",
            "/orders",
            "/fba",
            "/payments",
        ],
        "redirect_param_patterns": [
            "openid.return_to=",
            "return_to=",
        ],
        "login_form_selectors": [
            "input[name='email']",
            "input[name='password']",
            "#ap_email",
            "#ap_password",
            "input[type='submit'][value*='Sign']",
            "#signInSubmit",
        ],
        "logged_in_selectors": [
            "#sc-quicklinks",
            "[data-testid='sc-header']",
            "text=Seller Central",
            ".sc-header-menu",
            "#navbar",
        ],
        "auth_cookies": ["session-id", "ubid-main", "at-main"],
        "element_check_timeout": 5000,
    },
}

# 默认配置（用于未知平台）
DEFAULT_DETECTION_CONFIG: Dict[str, Any] = {
    "login_page_url_keywords": [
        "/login",
        "/signin",
        "/auth",
        "/account",
    ],
    "logged_in_page_url_keywords": [
        "/dashboard",
        "/home",
        "/welcome",
        "/portal",
    ],
    "redirect_param_patterns": [
        "redirect=",
        "return_url=",
    ],
    "login_form_selectors": [
        "input[type='password']",
        "input[name='password']",
        "button:has-text('登录')",
        "button:has-text('Login')",
        "button:has-text('Sign in')",
    ],
    "logged_in_selectors": [
        "[class*='user']",
        "[class*='avatar']",
        "text=退出",
        "text=Logout",
    ],
    "auth_cookies": [],
    "element_check_timeout": 5000,
}


class LoginStatusDetector:
    """
    登录状态检测器 (v4.8.0)
    
    使用方法:
        detector = LoginStatusDetector(platform="shopee")
        result = await detector.detect(page)
        
        if result.status == LoginStatus.NOT_LOGGED_IN:
            # 执行登录
            pass
    
    增强功能:
        - Cookie检测：检查认证Cookie是否存在
        - 等待自动跳转：检测URL自动跳转
        - 综合判断：URL + 元素 + Cookie
        - 调试模式：详细日志和截图
    """
    
    def __init__(self, platform: str, debug: bool = None):
        """
        初始化检测器
        
        Args:
            platform: 平台名称 (shopee, tiktok, miaoshou, amazon)
            debug: 是否启用调试模式（None表示使用环境变量）
        """
        self.platform = platform.lower()
        self.config = LOGIN_DETECTION_CONFIG.get(
            self.platform, DEFAULT_DETECTION_CONFIG
        )
        self.debug = debug if debug is not None else DEBUG_LOGIN_DETECTION
        
        # 检测结果缓存
        self._cache: Optional[LoginDetectionResult] = None
        self._cache_url: Optional[str] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 30.0  # 缓存有效期（秒）
        
        logger.info(f"[LoginDetector] Initialized for platform: {self.platform}, debug={self.debug}")
    
    async def detect(self, page, wait_for_redirect: bool = True) -> LoginDetectionResult:
        """
        检测登录状态（综合判断）
        
        Args:
            page: Playwright Page 对象
            wait_for_redirect: 是否等待自动跳转（默认True）
            
        Returns:
            LoginDetectionResult: 检测结果
        """
        start_time = time.time()
        current_url = page.url
        
        # 检查缓存
        if self._is_cache_valid(current_url):
            logger.info(f"[LoginDetector] Using cached result: {self._cache.status.value}")
            return self._cache
        
        # 收集检测详情（调试用）
        details = {} if self.debug else None
        
        try:
            # 1. 等待自动跳转检测（如果URL包含重定向参数）
            if wait_for_redirect:
                redirect_result = await self._check_redirect(page)
                if redirect_result and redirect_result.confidence >= 0.8:
                    self._log_result("redirect", redirect_result, start_time)
                    self._update_cache(current_url, redirect_result)
                    return redirect_result
                if details is not None:
                    details["redirect_check"] = redirect_result.__dict__ if redirect_result else None
            
            # 更新当前URL（可能已跳转）
            current_url = page.url
            
            # 2. URL 检测
            url_result = self._check_url(current_url)
            if details is not None:
                details["url_check"] = url_result.__dict__
            
            # 如果URL明确表示已登录，快速返回
            if url_result.status == LoginStatus.LOGGED_IN and url_result.confidence >= 0.85:
                self._log_result("url", url_result, start_time)
                self._update_cache(current_url, url_result)
                return url_result
            
            # 3. Cookie 检测
            cookie_result = await self._check_cookies(page)
            if details is not None:
                details["cookie_check"] = cookie_result.__dict__
            
            # 4. 元素检测
            element_result = await self._check_elements(page)
            if details is not None:
                details["element_check"] = element_result.__dict__
            
            # 5. 综合判断
            combined_result = self._combine_results(
                url_result, element_result, cookie_result, current_url, details
            )
            
            # 计算检测耗时
            detection_time_ms = int((time.time() - start_time) * 1000)
            combined_result.detection_time_ms = detection_time_ms
            combined_result.details = details
            
            self._log_result("combined", combined_result, start_time)
            self._update_cache(current_url, combined_result)
            
            # 调试模式：检测失败时截图
            if self.debug and combined_result.status == LoginStatus.UNKNOWN:
                await self._save_debug_screenshot(page, "unknown_status")
            
            return combined_result
            
        except Exception as e:
            logger.error(f"[LoginDetector] Detection failed with error: {e}")
            # 检测失败，返回保守结果
            fallback_result = LoginDetectionResult(
                status=LoginStatus.NOT_LOGGED_IN,
                confidence=0.3,
                reason=f"Detection failed with error: {str(e)}",
                detected_by="error_fallback",
                current_url=current_url,
                detection_time_ms=int((time.time() - start_time) * 1000)
            )
            
            if self.debug:
                await self._save_debug_screenshot(page, "detection_error")
            
            return fallback_result
    
    async def _check_redirect(self, page) -> Optional[LoginDetectionResult]:
        """
        检测URL是否自动跳转（用于持久化会话已登录的情况）
        
        流程：
        1. 检查当前URL是否包含重定向参数
        2. 等待最多5秒，检测URL是否变化
        3. 如果跳转到已登录页面，返回已登录结果
        """
        initial_url = page.url
        redirect_patterns = self.config.get("redirect_param_patterns", [])
        
        # 检查URL是否包含重定向参数
        has_redirect_param = any(
            pattern.lower() in initial_url.lower() 
            for pattern in redirect_patterns
        )
        
        if not has_redirect_param:
            return None
        
        logger.info(f"[LoginDetector] URL contains redirect param, waiting for auto-redirect...")
        
        # 等待自动跳转（最多5秒）
        max_wait_time = 5.0
        check_interval = 0.5
        waited = 0.0
        
        while waited < max_wait_time:
            await page.wait_for_timeout(int(check_interval * 1000))
            waited += check_interval
            
            current_url = page.url
            
            # 检查是否已跳转
            if current_url != initial_url:
                logger.info(f"[LoginDetector] URL changed: {initial_url[:50]}... -> {current_url[:50]}...")
                
                # 检查是否跳转到已登录页面
                logged_in_keywords = self.config.get("logged_in_page_url_keywords", [])
                for keyword in logged_in_keywords:
                    if keyword.lower() in current_url.lower():
                        # 妙手ERP特殊处理：确保跳转后不再包含redirect参数
                        redirect_check = self.config.get("redirect_to_logged_in_check", {})
                        exclude_pattern = redirect_check.get("exclude_pattern", "")
                        
                        if exclude_pattern and exclude_pattern.lower() in current_url.lower():
                            logger.info(f"[LoginDetector] URL still contains redirect param, continuing wait...")
                            continue
                        
                        return LoginDetectionResult(
                            status=LoginStatus.LOGGED_IN,
                            confidence=0.9,
                            reason=f"Auto-redirected from login page to: {keyword}",
                            detected_by="redirect",
                            current_url=current_url,
                            matched_pattern=keyword
                        )
        
        logger.info(f"[LoginDetector] No redirect detected after {max_wait_time}s")
        return None
    
    def _check_url(self, url: str) -> LoginDetectionResult:
        """
        通过 URL 检测登录状态
        """
        url_lower = url.lower()
        
        # 妙手ERP特殊处理：/welcome 且不包含 redirect= 表示已登录
        if self.platform == "miaoshou":
            if "/welcome" in url_lower and "redirect=" not in url_lower:
                return LoginDetectionResult(
                    status=LoginStatus.LOGGED_IN,
                    confidence=0.9,
                    reason="URL is /welcome without redirect param (miaoshou specific)",
                    detected_by="url",
                    current_url=url,
                    matched_pattern="/welcome"
                )
        
        # 检查已登录页 URL（优先级更高，因为更可靠）
        for keyword in self.config.get("logged_in_page_url_keywords", []):
            if keyword.lower() in url_lower:
                # 排除包含重定向参数的情况
                redirect_patterns = self.config.get("redirect_param_patterns", [])
                has_redirect = any(p.lower() in url_lower for p in redirect_patterns)
                
                if not has_redirect:
                    return LoginDetectionResult(
                        status=LoginStatus.LOGGED_IN,
                        confidence=0.85,
                        reason=f"URL contains logged-in page keyword: {keyword}",
                        detected_by="url",
                        current_url=url,
                        matched_pattern=keyword
                    )
        
        # 检查登录页 URL
        for keyword in self.config.get("login_page_url_keywords", []):
            if keyword.lower() in url_lower:
                return LoginDetectionResult(
                    status=LoginStatus.NOT_LOGGED_IN,
                    confidence=0.85,
                    reason=f"URL contains login page keyword: {keyword}",
                    detected_by="url",
                    current_url=url,
                    matched_pattern=keyword
                )
        
        # URL 无法明确判断
        return LoginDetectionResult(
            status=LoginStatus.UNKNOWN,
            confidence=0.3,
            reason="URL does not match any known patterns",
            detected_by="url",
            current_url=url
        )
    
    async def _check_cookies(self, page) -> LoginDetectionResult:
        """
        通过Cookie检测登录状态
        """
        auth_cookies = self.config.get("auth_cookies", [])
        
        if not auth_cookies:
            return LoginDetectionResult(
                status=LoginStatus.UNKNOWN,
                confidence=0.1,
                reason="No auth cookies configured for this platform",
                detected_by="cookie",
                current_url=page.url
            )
        
        try:
            # 获取当前页面的所有Cookie
            cookies = await page.context.cookies()
            cookie_names = {c.get("name", "") for c in cookies}
            
            # 检查认证Cookie是否存在
            found_cookies = []
            for auth_cookie in auth_cookies:
                if auth_cookie in cookie_names:
                    found_cookies.append(auth_cookie)
            
            if found_cookies:
                # 计算置信度（找到的Cookie数量 / 配置的Cookie数量）
                confidence = min(0.85, 0.5 + len(found_cookies) * 0.15)
                return LoginDetectionResult(
                    status=LoginStatus.LOGGED_IN,
                    confidence=confidence,
                    reason=f"Auth cookies found: {', '.join(found_cookies)}",
                    detected_by="cookie",
                    current_url=page.url,
                    matched_pattern=str(found_cookies)
                )
            else:
                return LoginDetectionResult(
                    status=LoginStatus.NOT_LOGGED_IN,
                    confidence=0.6,
                    reason=f"No auth cookies found (expected: {', '.join(auth_cookies)})",
                    detected_by="cookie",
                    current_url=page.url
                )
                
        except Exception as e:
            logger.warning(f"[LoginDetector] Cookie check failed: {e}")
            return LoginDetectionResult(
                status=LoginStatus.UNKNOWN,
                confidence=0.1,
                reason=f"Cookie check failed: {str(e)}",
                detected_by="cookie",
                current_url=page.url
            )
    
    async def _check_elements(self, page) -> LoginDetectionResult:
        """
        通过页面元素检测登录状态（带重试机制）
        """
        timeout = self.config.get("element_check_timeout", 5000)
        max_retries = 2
        
        for retry in range(max_retries):
            # 1. 检查登录表单元素（未登录标识）
            login_form_result = await self._check_login_form_elements(page, timeout)
            if login_form_result.status == LoginStatus.NOT_LOGGED_IN:
                return login_form_result
            
            # 2. 检查已登录元素
            logged_in_result = await self._check_logged_in_elements(page, timeout)
            if logged_in_result.status == LoginStatus.LOGGED_IN:
                return logged_in_result
            
            # 如果第一次检测不确定，等待后重试
            if retry < max_retries - 1:
                logger.info(f"[LoginDetector] Element check inconclusive, retrying ({retry + 1}/{max_retries})...")
                await page.wait_for_timeout(1000)
        
        # 无法通过元素判断
        return LoginDetectionResult(
            status=LoginStatus.UNKNOWN,
            confidence=0.2,
            reason="No login form or logged-in elements found after retries",
            detected_by="element",
            current_url=page.url
        )
    
    async def _check_login_form_elements(self, page, timeout: int) -> LoginDetectionResult:
        """检查登录表单元素"""
        for selector in self.config.get("login_form_selectors", []):
            try:
                locator = self._get_locator(page, selector)
                count = await locator.count()
                if count > 0:
                    # 使用较短超时检查可见性
                    try:
                        is_visible = await locator.first.is_visible()
                        if is_visible:
                            return LoginDetectionResult(
                                status=LoginStatus.NOT_LOGGED_IN,
                                confidence=0.85,
                                reason=f"Login form element visible: {selector}",
                                detected_by="element",
                                current_url=page.url,
                                matched_pattern=selector
                            )
                    except Exception:
                        pass
            except Exception as e:
                if self.debug:
                    logger.debug(f"[LoginDetector] Error checking selector {selector}: {e}")
                continue
        
        return LoginDetectionResult(
            status=LoginStatus.UNKNOWN,
            confidence=0.3,
            reason="No login form elements found",
            detected_by="element",
            current_url=page.url
        )
    
    async def _check_logged_in_elements(self, page, timeout: int) -> LoginDetectionResult:
        """检查已登录元素"""
        for selector in self.config.get("logged_in_selectors", []):
            try:
                locator = self._get_locator(page, selector)
                count = await locator.count()
                if count > 0:
                    try:
                        is_visible = await locator.first.is_visible()
                        if is_visible:
                            return LoginDetectionResult(
                                status=LoginStatus.LOGGED_IN,
                                confidence=0.8,
                                reason=f"Logged-in element visible: {selector}",
                                detected_by="element",
                                current_url=page.url,
                                matched_pattern=selector
                            )
                    except Exception:
                        pass
            except Exception as e:
                if self.debug:
                    logger.debug(f"[LoginDetector] Error checking selector {selector}: {e}")
                continue
        
        return LoginDetectionResult(
            status=LoginStatus.UNKNOWN,
            confidence=0.3,
            reason="No logged-in elements found",
            detected_by="element",
            current_url=page.url
        )
    
    def _get_locator(self, page, selector: str):
        """
        根据选择器获取定位器（使用官方 API）
        """
        # 处理 text= 前缀
        if selector.startswith("text="):
            return page.get_by_text(selector[5:])
        
        # 处理 role= 前缀
        if selector.startswith("role="):
            import re
            match = re.match(r'role=(\w+)\[name=([^\]]+)\]', selector)
            if match:
                role = match.group(1)
                name = match.group(2)
                return page.get_by_role(role, name=name)
            # 简单 role 选择器
            return page.locator(f'[role="{selector[5:]}"]')
        
        # 处理 placeholder= 前缀
        if selector.startswith("placeholder="):
            return page.get_by_placeholder(selector[12:])
        
        # 处理 label= 前缀
        if selector.startswith("label="):
            return page.get_by_label(selector[6:])
        
        # 处理 :has-text() 伪选择器
        if ":has-text(" in selector:
            return page.locator(selector)
        
        # 处理 [class*=] 属性选择器
        if "[class*=" in selector or "[data-" in selector:
            return page.locator(selector)
        
        # 默认 CSS 选择器
        return page.locator(selector)
    
    def _combine_results(
        self,
        url_result: LoginDetectionResult,
        element_result: LoginDetectionResult,
        cookie_result: LoginDetectionResult,
        current_url: str,
        details: Optional[Dict] = None
    ) -> LoginDetectionResult:
        """
        综合多个检测结果（URL + 元素 + Cookie）
        """
        results = [
            ("url", url_result),
            ("element", element_result),
            ("cookie", cookie_result),
        ]
        
        # 统计各状态的投票
        logged_in_votes = 0
        logged_in_confidence = 0.0
        not_logged_in_votes = 0
        not_logged_in_confidence = 0.0
        
        for name, result in results:
            if result.status == LoginStatus.LOGGED_IN:
                logged_in_votes += 1
                logged_in_confidence = max(logged_in_confidence, result.confidence)
            elif result.status == LoginStatus.NOT_LOGGED_IN:
                not_logged_in_votes += 1
                not_logged_in_confidence = max(not_logged_in_confidence, result.confidence)
        
        # 决策逻辑
        # 1. 如果多数检测认为已登录
        if logged_in_votes >= 2:
            return LoginDetectionResult(
                status=LoginStatus.LOGGED_IN,
                confidence=min(0.95, logged_in_confidence + 0.1),
                reason=f"Multiple detections agree: logged in ({logged_in_votes}/3)",
                detected_by="combined",
                current_url=current_url
            )
        
        # 2. 如果多数检测认为未登录
        if not_logged_in_votes >= 2:
            return LoginDetectionResult(
                status=LoginStatus.NOT_LOGGED_IN,
                confidence=min(0.95, not_logged_in_confidence + 0.1),
                reason=f"Multiple detections agree: not logged in ({not_logged_in_votes}/3)",
                detected_by="combined",
                current_url=current_url
            )
        
        # 3. 如果Cookie存在，倾向于认为已登录
        if cookie_result.status == LoginStatus.LOGGED_IN and cookie_result.confidence >= 0.6:
            return LoginDetectionResult(
                status=LoginStatus.LOGGED_IN,
                confidence=cookie_result.confidence,
                reason=f"Cookie indicates logged in: {cookie_result.reason}",
                detected_by="combined",
                current_url=current_url,
                matched_pattern=cookie_result.matched_pattern
            )
        
        # 4. 如果元素检测明确
        if element_result.status != LoginStatus.UNKNOWN and element_result.confidence >= 0.7:
            return element_result
        
        # 5. 如果URL检测明确
        if url_result.status != LoginStatus.UNKNOWN and url_result.confidence >= 0.7:
            return url_result
        
        # 6. 无法确定，返回保守结果（假设未登录）
        return LoginDetectionResult(
            status=LoginStatus.NOT_LOGGED_IN,
            confidence=0.4,
            reason="Cannot determine login status, assuming not logged in (conservative)",
            detected_by="fallback",
            current_url=current_url
        )
    
    def _log_result(self, method: str, result: LoginDetectionResult, start_time: float):
        """记录检测结果日志"""
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        status_str = result.status.value.upper()
        if result.status == LoginStatus.LOGGED_IN:
            status_tag = "[LOGGED_IN]"
        elif result.status == LoginStatus.NOT_LOGGED_IN:
            status_tag = "[NOT_LOGGED_IN]"
        else:
            status_tag = "[UNKNOWN]"
        
        logger.info(
            f"[LoginDetector] {status_tag} by {method} "
            f"(confidence={result.confidence:.2f}, time={elapsed_ms}ms): {result.reason}"
        )
        
        if self.debug:
            logger.debug(f"[LoginDetector] URL: {result.current_url}")
            if result.matched_pattern:
                logger.debug(f"[LoginDetector] Matched: {result.matched_pattern}")
    
    def _is_cache_valid(self, current_url: str) -> bool:
        """检查缓存是否有效"""
        if self._cache is None:
            return False
        
        # 检查URL是否变化
        if self._cache_url != current_url:
            return False
        
        # 检查缓存是否过期
        if time.time() - self._cache_time > self._cache_ttl:
            return False
        
        return True
    
    def _update_cache(self, url: str, result: LoginDetectionResult):
        """更新缓存"""
        self._cache = result
        self._cache_url = url
        self._cache_time = time.time()
    
    def clear_cache(self):
        """清除缓存"""
        self._cache = None
        self._cache_url = None
        self._cache_time = 0
    
    async def _save_debug_screenshot(self, page, suffix: str):
        """保存调试截图"""
        try:
            debug_dir = Path("temp/debug/login_detection")
            debug_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{self.platform}_{suffix}_{timestamp}.png"
            filepath = debug_dir / filename
            
            await page.screenshot(path=str(filepath))
            logger.info(f"[LoginDetector] Debug screenshot saved: {filepath}")
        except Exception as e:
            logger.warning(f"[LoginDetector] Failed to save screenshot: {e}")
    
    def needs_login(self, result: LoginDetectionResult) -> bool:
        """
        根据检测结果判断是否需要登录
        
        Args:
            result: 检测结果
            
        Returns:
            bool: 是否需要登录
        """
        # 已登录且置信度高，不需要登录
        if result.status == LoginStatus.LOGGED_IN and result.confidence >= 0.7:
            return False
        
        # 未登录或置信度低，需要登录
        return True


def get_platform_config(platform: str) -> Dict[str, Any]:
    """
    获取平台特定的登录检测配置
    
    Args:
        platform: 平台名称
        
    Returns:
        Dict: 配置字典
    """
    return LOGIN_DETECTION_CONFIG.get(platform.lower(), DEFAULT_DETECTION_CONFIG)


def add_platform_config(platform: str, config: Dict[str, Any]) -> None:
    """
    添加或更新平台配置
    
    Args:
        platform: 平台名称
        config: 配置字典
    """
    LOGIN_DETECTION_CONFIG[platform.lower()] = config
    logger.info(f"[LoginDetector] Added/updated config for platform: {platform}")
