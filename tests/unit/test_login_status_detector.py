#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
登录状态检测器单元测试

测试场景：
1. URL检测逻辑
2. Cookie检测逻辑
3. 综合判断逻辑
4. needs_login判断
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass
from typing import List, Dict, Any

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# 配置 pytest-asyncio 或使用 anyio
pytest_plugins = ('anyio',)

from modules.utils.login_status_detector import (
    LoginStatusDetector,
    LoginStatus,
    LoginDetectionResult,
    LOGIN_DETECTION_CONFIG,
    DEFAULT_DETECTION_CONFIG,
    get_platform_config,
    add_platform_config,
)


class TestLoginStatusEnum:
    """测试登录状态枚举"""
    
    def test_status_values(self):
        """测试枚举值"""
        assert LoginStatus.LOGGED_IN.value == "logged_in"
        assert LoginStatus.NOT_LOGGED_IN.value == "not_logged_in"
        assert LoginStatus.UNKNOWN.value == "unknown"


class TestLoginDetectionResult:
    """测试检测结果数据类"""
    
    def test_create_result(self):
        """测试创建检测结果"""
        result = LoginDetectionResult(
            status=LoginStatus.LOGGED_IN,
            confidence=0.9,
            reason="Test reason",
            detected_by="test",
            current_url="https://example.com/dashboard"
        )
        
        assert result.status == LoginStatus.LOGGED_IN
        assert result.confidence == 0.9
        assert result.reason == "Test reason"
        assert result.detected_by == "test"
        assert result.current_url == "https://example.com/dashboard"
        assert result.matched_pattern is None
        assert result.detection_time_ms == 0


class TestLoginStatusDetectorInit:
    """测试检测器初始化"""
    
    def test_init_known_platform(self):
        """测试已知平台初始化"""
        detector = LoginStatusDetector("shopee")
        assert detector.platform == "shopee"
        assert detector.config == LOGIN_DETECTION_CONFIG["shopee"]
    
    def test_init_unknown_platform(self):
        """测试未知平台初始化（使用默认配置）"""
        detector = LoginStatusDetector("unknown_platform")
        assert detector.platform == "unknown_platform"
        assert detector.config == DEFAULT_DETECTION_CONFIG
    
    def test_init_case_insensitive(self):
        """测试平台名称大小写不敏感"""
        detector = LoginStatusDetector("SHOPEE")
        assert detector.platform == "shopee"
        assert detector.config == LOGIN_DETECTION_CONFIG["shopee"]


class TestURLDetection:
    """测试URL检测逻辑"""
    
    def test_shopee_login_page_detected(self):
        """测试Shopee登录页面检测"""
        detector = LoginStatusDetector("shopee")
        
        # 登录页面URL（包含 /account/signin）
        # 注意：seller.shopee.sg域名中的seller不应该影响检测
        result = detector._check_url("https://shopee.sg/account/signin")
        assert result.status == LoginStatus.NOT_LOGGED_IN
        assert result.confidence >= 0.8
        assert result.detected_by == "url"
        
        # 也测试包含 /login 的URL
        result2 = detector._check_url("https://shopee.sg/login")
        assert result2.status == LoginStatus.NOT_LOGGED_IN
    
    def test_shopee_logged_in_page_detected(self):
        """测试Shopee已登录页面检测"""
        detector = LoginStatusDetector("shopee")
        
        # 已登录页面URL（明确的dashboard路径）
        result = detector._check_url("https://shopee.sg/portal/dashboard")
        assert result.status == LoginStatus.LOGGED_IN
        assert result.confidence >= 0.8
        
        # 也测试 /seller 路径
        result2 = detector._check_url("https://shopee.sg/seller/home")
        assert result2.status == LoginStatus.LOGGED_IN
    
    def test_miaoshou_redirect_handling(self):
        """测试妙手ERP redirect参数处理"""
        detector = LoginStatusDetector("miaoshou")
        
        # 带redirect参数的URL（未登录）
        result = detector._check_url("https://erp.miaohou.com/login?redirect=/welcome")
        assert result.status == LoginStatus.NOT_LOGGED_IN
        
        # /welcome不带redirect参数（已登录）
        result = detector._check_url("https://erp.miaohou.com/welcome")
        assert result.status == LoginStatus.LOGGED_IN
    
    def test_unknown_url_returns_unknown(self):
        """测试未知URL返回UNKNOWN状态"""
        detector = LoginStatusDetector("shopee")
        
        result = detector._check_url("https://some-random-site.com/page")
        assert result.status == LoginStatus.UNKNOWN
        assert result.confidence < 0.5


class TestCookieDetection:
    """测试Cookie检测逻辑"""
    
    @pytest.mark.anyio
    async def test_auth_cookies_found(self):
        """测试找到认证Cookie"""
        detector = LoginStatusDetector("shopee")
        
        # Mock page with cookies
        mock_context = AsyncMock()
        mock_context.cookies.return_value = [
            {"name": "SPC_EC", "value": "xxx"},
            {"name": "SPC_U", "value": "yyy"},
            {"name": "other_cookie", "value": "zzz"}
        ]
        
        mock_page = MagicMock()
        mock_page.url = "https://seller.shopee.sg/dashboard"
        mock_page.context = mock_context
        
        result = await detector._check_cookies(mock_page)
        
        assert result.status == LoginStatus.LOGGED_IN
        assert result.confidence >= 0.6
        assert "SPC_EC" in result.reason or "SPC_U" in result.reason
    
    @pytest.mark.anyio
    async def test_auth_cookies_not_found(self):
        """测试未找到认证Cookie"""
        detector = LoginStatusDetector("shopee")
        
        # Mock page without auth cookies
        mock_context = AsyncMock()
        mock_context.cookies.return_value = [
            {"name": "random_cookie", "value": "xxx"},
        ]
        
        mock_page = MagicMock()
        mock_page.url = "https://seller.shopee.sg/login"
        mock_page.context = mock_context
        
        result = await detector._check_cookies(mock_page)
        
        assert result.status == LoginStatus.NOT_LOGGED_IN
        assert result.confidence >= 0.5


class TestElementDetection:
    """测试元素检测逻辑"""
    
    @pytest.mark.anyio
    async def test_login_form_detected(self):
        """测试检测到登录表单"""
        detector = LoginStatusDetector("shopee")
        
        # Mock page with login form
        mock_locator = AsyncMock()
        mock_locator.count.return_value = 1
        mock_locator.first.is_visible.return_value = True
        
        mock_page = MagicMock()
        mock_page.url = "https://seller.shopee.sg/login"
        mock_page.locator.return_value = mock_locator
        mock_page.get_by_text.return_value = mock_locator
        
        result = await detector._check_login_form_elements(mock_page, 5000)
        
        assert result.status == LoginStatus.NOT_LOGGED_IN
        assert result.confidence >= 0.7
    
    @pytest.mark.anyio
    async def test_logged_in_element_detected(self):
        """测试检测到已登录元素"""
        detector = LoginStatusDetector("shopee")
        
        # Mock page with logged-in element
        mock_locator = AsyncMock()
        mock_locator.count.return_value = 1
        mock_locator.first.is_visible.return_value = True
        
        mock_page = MagicMock()
        mock_page.url = "https://seller.shopee.sg/dashboard"
        mock_page.locator.return_value = mock_locator
        mock_page.get_by_text.return_value = mock_locator
        
        result = await detector._check_logged_in_elements(mock_page, 5000)
        
        assert result.status == LoginStatus.LOGGED_IN
        assert result.confidence >= 0.7


class TestCombinedResults:
    """测试综合判断逻辑"""
    
    def test_majority_logged_in(self):
        """测试多数检测认为已登录"""
        detector = LoginStatusDetector("shopee")
        
        url_result = LoginDetectionResult(
            status=LoginStatus.LOGGED_IN,
            confidence=0.85,
            reason="URL match",
            detected_by="url"
        )
        element_result = LoginDetectionResult(
            status=LoginStatus.LOGGED_IN,
            confidence=0.8,
            reason="Element found",
            detected_by="element"
        )
        cookie_result = LoginDetectionResult(
            status=LoginStatus.UNKNOWN,
            confidence=0.3,
            reason="No cookies",
            detected_by="cookie"
        )
        
        combined = detector._combine_results(
            url_result, element_result, cookie_result, 
            "https://example.com/dashboard"
        )
        
        assert combined.status == LoginStatus.LOGGED_IN
        assert combined.confidence >= 0.8
    
    def test_majority_not_logged_in(self):
        """测试多数检测认为未登录"""
        detector = LoginStatusDetector("shopee")
        
        url_result = LoginDetectionResult(
            status=LoginStatus.NOT_LOGGED_IN,
            confidence=0.85,
            reason="Login URL",
            detected_by="url"
        )
        element_result = LoginDetectionResult(
            status=LoginStatus.NOT_LOGGED_IN,
            confidence=0.8,
            reason="Login form found",
            detected_by="element"
        )
        cookie_result = LoginDetectionResult(
            status=LoginStatus.NOT_LOGGED_IN,
            confidence=0.6,
            reason="No auth cookies",
            detected_by="cookie"
        )
        
        combined = detector._combine_results(
            url_result, element_result, cookie_result,
            "https://example.com/login"
        )
        
        assert combined.status == LoginStatus.NOT_LOGGED_IN
        assert combined.confidence >= 0.8
    
    def test_cookie_priority_when_uncertain(self):
        """测试不确定时Cookie优先"""
        detector = LoginStatusDetector("shopee")
        
        url_result = LoginDetectionResult(
            status=LoginStatus.UNKNOWN,
            confidence=0.3,
            reason="URL unknown",
            detected_by="url"
        )
        element_result = LoginDetectionResult(
            status=LoginStatus.UNKNOWN,
            confidence=0.3,
            reason="No elements",
            detected_by="element"
        )
        cookie_result = LoginDetectionResult(
            status=LoginStatus.LOGGED_IN,
            confidence=0.7,
            reason="Auth cookies found",
            detected_by="cookie"
        )
        
        combined = detector._combine_results(
            url_result, element_result, cookie_result,
            "https://example.com/page"
        )
        
        assert combined.status == LoginStatus.LOGGED_IN


class TestNeedsLogin:
    """测试needs_login判断"""
    
    def test_logged_in_high_confidence(self):
        """测试已登录高置信度 - 不需要登录"""
        detector = LoginStatusDetector("shopee")
        
        result = LoginDetectionResult(
            status=LoginStatus.LOGGED_IN,
            confidence=0.9,
            reason="Logged in",
            detected_by="combined"
        )
        
        assert detector.needs_login(result) is False
    
    def test_logged_in_low_confidence(self):
        """测试已登录低置信度 - 需要登录（保守策略）"""
        detector = LoginStatusDetector("shopee")
        
        result = LoginDetectionResult(
            status=LoginStatus.LOGGED_IN,
            confidence=0.5,  # 低于0.7
            reason="Maybe logged in",
            detected_by="combined"
        )
        
        assert detector.needs_login(result) is True
    
    def test_not_logged_in(self):
        """测试未登录 - 需要登录"""
        detector = LoginStatusDetector("shopee")
        
        result = LoginDetectionResult(
            status=LoginStatus.NOT_LOGGED_IN,
            confidence=0.9,
            reason="Not logged in",
            detected_by="url"
        )
        
        assert detector.needs_login(result) is True
    
    def test_unknown_status(self):
        """测试未知状态 - 需要登录（保守策略）"""
        detector = LoginStatusDetector("shopee")
        
        result = LoginDetectionResult(
            status=LoginStatus.UNKNOWN,
            confidence=0.5,
            reason="Cannot determine",
            detected_by="fallback"
        )
        
        assert detector.needs_login(result) is True


class TestCacheManagement:
    """测试缓存管理"""
    
    def test_cache_valid_same_url(self):
        """测试同一URL缓存有效"""
        detector = LoginStatusDetector("shopee")
        
        # 模拟缓存
        cached_result = LoginDetectionResult(
            status=LoginStatus.LOGGED_IN,
            confidence=0.9,
            reason="Cached",
            detected_by="combined"
        )
        detector._cache = cached_result
        detector._cache_url = "https://example.com/dashboard"
        detector._cache_time = 9999999999  # 未来时间
        
        assert detector._is_cache_valid("https://example.com/dashboard") is True
    
    def test_cache_invalid_different_url(self):
        """测试不同URL缓存无效"""
        detector = LoginStatusDetector("shopee")
        
        detector._cache = LoginDetectionResult(
            status=LoginStatus.LOGGED_IN,
            confidence=0.9,
            reason="Cached",
            detected_by="combined"
        )
        detector._cache_url = "https://example.com/dashboard"
        detector._cache_time = 9999999999
        
        assert detector._is_cache_valid("https://example.com/other") is False
    
    def test_clear_cache(self):
        """测试清除缓存"""
        detector = LoginStatusDetector("shopee")
        
        detector._cache = LoginDetectionResult(
            status=LoginStatus.LOGGED_IN,
            confidence=0.9,
            reason="Cached",
            detected_by="combined"
        )
        detector._cache_url = "https://example.com/dashboard"
        detector._cache_time = 9999999999
        
        detector.clear_cache()
        
        assert detector._cache is None
        assert detector._cache_url is None


class TestPlatformConfig:
    """测试平台配置函数"""
    
    def test_get_known_platform_config(self):
        """测试获取已知平台配置"""
        config = get_platform_config("shopee")
        assert "login_page_url_keywords" in config
        assert "logged_in_selectors" in config
    
    def test_get_unknown_platform_config(self):
        """测试获取未知平台配置"""
        config = get_platform_config("unknown_platform")
        assert config == DEFAULT_DETECTION_CONFIG
    
    def test_add_platform_config(self):
        """测试添加平台配置"""
        custom_config = {
            "login_page_url_keywords": ["/custom-login"],
            "logged_in_page_url_keywords": ["/custom-dashboard"],
            "auth_cookies": ["custom_cookie"]
        }
        
        add_platform_config("custom_platform", custom_config)
        
        retrieved_config = get_platform_config("custom_platform")
        assert retrieved_config == custom_config
        
        # 清理
        if "custom_platform" in LOGIN_DETECTION_CONFIG:
            del LOGIN_DETECTION_CONFIG["custom_platform"]


class TestAllPlatformsConfig:
    """测试所有平台配置完整性"""
    
    @pytest.mark.parametrize("platform", ["shopee", "tiktok", "miaoshou", "amazon"])
    def test_platform_config_has_required_fields(self, platform):
        """测试平台配置包含必需字段"""
        config = LOGIN_DETECTION_CONFIG[platform]
        
        assert "login_page_url_keywords" in config
        assert "logged_in_page_url_keywords" in config
        assert "login_form_selectors" in config
        assert "logged_in_selectors" in config
        assert "auth_cookies" in config
        
        # 检查非空
        assert len(config["login_page_url_keywords"]) > 0
        assert len(config["logged_in_page_url_keywords"]) > 0
        assert len(config["login_form_selectors"]) > 0
        assert len(config["logged_in_selectors"]) > 0

