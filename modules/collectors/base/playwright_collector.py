#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Playwright基础采集器
提供统一的Playwright采集框架
"""

import asyncio
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext
import logging

logger = logging.getLogger(__name__)

class PlaywrightCollector:
    """Playwright基础采集器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化Playwright采集器
        
        Args:
            config: 配置信息，包含浏览器设置、代理设置等
        """
        self.config = config
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.screenshot_dir = Path("temp/media/screenshots")
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        
        # 浏览器配置
        self.browser_config = {
            "headless": config.get("headless", False),
            "slow_mo": config.get("slow_mo", 100),
            "timeout": config.get("timeout", 30000),
        }
        
        # 代理配置
        self.proxy_config = config.get("proxy", {})
        # 下载目录（可选，由上层按账号/数据类型传入）。注意：Python不支持在new_context传downloads_path
        self.downloads_path = config.get("downloads_path")
        
    def start_browser(self) -> bool:
        """
        启动浏览器
        
        Returns:
            bool: 是否成功启动
        """
        try:
            logger.info("[START] 启动Playwright浏览器...")
            
            self.playwright = sync_playwright().start()
            
            # 配置浏览器启动参数
            launch_args = {
                "headless": self.browser_config["headless"],
                "slow_mo": self.browser_config["slow_mo"],
            }
            
            # 添加代理配置
            if self.proxy_config:
                launch_args["proxy"] = self.proxy_config
                logger.info(f"[LINK] 使用代理: {self.proxy_config.get('server', 'unknown')}")
            
            # 启动浏览器
            self.browser = self.playwright.chromium.launch(**launch_args)
            
            # 创建上下文
            context_args = {
                "viewport": {"width": 1920, "height": 1080},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "accept_downloads": True,
                "bypass_csp": True,
                "ignore_https_errors": True,
            }
            
            # 设置下载路径
            if hasattr(self, 'downloads_path') and self.downloads_path:
                context_args["accept_downloads"] = True
            
            self.context = self.browser.new_context(**context_args)
            
            # 创建页面
            self.page = self.context.new_page()
            self.page.set_default_timeout(self.browser_config["timeout"])
            
            logger.info("[OK] 浏览器启动成功")
            return True
            
        except Exception as e:
            logger.error(f"[FAIL] 浏览器启动失败: {e}")
            return False
    
    def close_browser(self):
        """关闭浏览器"""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if hasattr(self, 'playwright'):
                self.playwright.stop()
            logger.info("[LOCK] 浏览器已关闭")
        except Exception as e:
            logger.error(f"[FAIL] 关闭浏览器时出错: {e}")
    
    def take_screenshot(self, name: str) -> Optional[str]:
        """
        截图
        
        Args:
            name: 截图名称
            
        Returns:
            str: 截图文件路径，失败返回None
        """
        try:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{timestamp}_{name}.png"
            filepath = self.screenshot_dir / filename
            
            if self.page:
                self.page.screenshot(path=str(filepath))
                logger.info(f"[CAM] 截图保存: {filepath}")
                return str(filepath)
            return None
        except Exception as e:
            logger.error(f"[FAIL] 截图失败: {e}")
            return None
    
    def wait_for_element(self, selector: str, timeout: int = 10000) -> bool:
        """
        等待元素出现
        
        Args:
            selector: 元素选择器
            timeout: 超时时间（毫秒）
            
        Returns:
            bool: 是否找到元素
        """
        try:
            if self.page:
                self.page.wait_for_selector(selector, timeout=timeout)
                return True
            return False
        except Exception as e:
            logger.warning(f"[WARN] 等待元素超时 {selector}: {e}")
            return False
    
    def click_element(self, selector: str) -> bool:
        """
        点击元素
        
        Args:
            selector: 元素选择器
            
        Returns:
            bool: 是否点击成功
        """
        try:
            if self.page and self.wait_for_element(selector):
                self.page.click(selector)
                logger.info(f"[MOUSE] 点击元素: {selector}")
                return True
            return False
        except Exception as e:
            logger.error(f"[FAIL] 点击元素失败 {selector}: {e}")
            return False
    
    def fill_input(self, selector: str, value: str) -> bool:
        """
        填充输入框
        
        Args:
            selector: 元素选择器
            value: 输入值
            
        Returns:
            bool: 是否填充成功
        """
        try:
            if self.page and self.wait_for_element(selector):
                self.page.fill(selector, value)
                logger.info(f"[EDIT] 填充输入框 {selector}: {value}")
                return True
            return False
        except Exception as e:
            logger.error(f"[FAIL] 填充输入框失败 {selector}: {e}")
            return False
    
    def get_text(self, selector: str) -> Optional[str]:
        """
        获取元素文本
        
        Args:
            selector: 元素选择器
            
        Returns:
            str: 元素文本，失败返回None
        """
        try:
            if self.page and self.wait_for_element(selector):
                text = self.page.text_content(selector)
                return text.strip() if text else None
            return None
        except Exception as e:
            logger.error(f"[FAIL] 获取文本失败 {selector}: {e}")
            return None
    
    def navigate_to(self, url: str) -> bool:
        """
        导航到指定URL
        
        Args:
            url: 目标URL
            
        Returns:
            bool: 是否导航成功
        """
        try:
            if self.page:
                logger.info(f"[WEB] 导航到: {url}")
                self.page.goto(url)
                self.page.wait_for_load_state("networkidle")
                return True
            return False
        except Exception as e:
            logger.error(f"[FAIL] 导航失败 {url}: {e}")
            return False
    
    def wait_for_download(self, timeout: int = 30000):
        """
        等待文件下载
        
        Args:
            timeout: 超时时间（毫秒）
            
        Returns:
            Download: 下载对象，失败返回None
        """
        try:
            if self.page:
                with self.page.expect_download(timeout=timeout) as download_info:
                    download = download_info.value
                    return download
            return None
        except Exception as e:
            logger.error(f"[FAIL] 等待下载失败: {e}")
            return None
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start_browser()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close_browser()
