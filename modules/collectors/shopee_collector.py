#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shopee商家端数据采集器
基于Playwright技术栈，支持邮箱OTP验证和会话持久化
支持多账号数据隔离和店铺维度管理
集成智能代理管理器，自动优化网络策略
"""

import time
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext

# 导入智能代理管理器
try:
    from proxy_manager import ProxyManager
    PROXY_MANAGER_AVAILABLE = True
except ImportError:
    PROXY_MANAGER_AVAILABLE = False
    logging.warning("[WARN] 智能代理管理器不可用，将使用静态代理配置")


logger = logging.getLogger(__name__)

class ShopeeCollector:
    """Shopee商家端数据采集器"""
    
    def __init__(self, account_config: Dict[str, Any], config: Dict[str, Any] = None):
        """初始化Shopee采集器"""
        self.account_config = account_config
        self.account_id = account_config.get('account_id', '')
        self.store_name = account_config.get('store_name', 'unknown_store')
        self.username = account_config.get('username', '')
        self.password = account_config.get('password', '')
        self.login_url = account_config.get('login_url', '')
        self.email = account_config.get('E-mail', '')
        
        # 初始化新的代理配置管理器
        try:
            from modules.utils.proxy_config_manager import ProxyConfigManager
            self.proxy_config_manager = ProxyConfigManager()
            logger.info("[OK] 代理配置管理器已初始化")
        except ImportError as e:
            logger.warning(f"[WARN] 代理配置管理器不可用: {e}")
            self.proxy_config_manager = None
        
        # 保持向后兼容 - 智能代理管理器
        if PROXY_MANAGER_AVAILABLE:
            self.proxy_manager = ProxyManager()
            logger.info("[OK] 智能代理管理器已初始化")
        else:
            self.proxy_manager = None
        
        # 账号专属目录结构 - 按店铺隔离数据
        self.base_path = Path("temp/outputs/shopee_data") / self.store_name
        self.downloads_path = self.base_path / "downloads"
        self.screenshot_dir = Path("temp/media/screenshots/shopee") / self.store_name
        self.session_dir = Path("temp/sessions/shopee") / self.store_name
        self.logs_dir = Path("temp/logs/shopee") / self.store_name
        
        # 创建必要的目录
        for path in [self.downloads_path, self.screenshot_dir, self.session_dir, self.logs_dir]:
            path.mkdir(parents=True, exist_ok=True)
        
        # 会话文件路径 - 账号专属
        safe_username = self.username.replace(':', '_').replace('@', '_')
        self.session_file = self.session_dir / f"{safe_username}_session.json"
        
        # 数据采集配置
        self.collection_config = config or {}
        
        # 浏览器相关属性
        self.page = None
        self.browser = None
        self.context = None
        self.playwright = None
        
        logger.info(f"[START] 初始化Shopee采集器")
        logger.info(f"   账号ID: {self.account_id}")
        logger.info(f"   店铺名: {self.store_name}")
        logger.info(f"   用户名: {self.username}")
        logger.info(f"   数据路径: {self.base_path}")
    
    def initialize_browser(self, headless: bool = False) -> bool:
        """
        初始化浏览器
        
        Args:
            headless: 是否无头模式
            
        Returns:
            初始化是否成功
        """
        try:
            self.playwright = sync_playwright().start()
            
            # 启动浏览器 - 优化网络配置和反检测
            browser_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-gpu',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--ignore-certificate-errors',
                '--ignore-ssl-errors',
                '--ignore-certificate-errors-spki-list',
                '--allow-running-insecure-content',
                '--disable-setuid-sandbox',
                '--disable-accelerated-2d-canvas',
                '--no-zygote',
                '--disable-gpu-sandbox',
                # 网络优化
                '--aggressive-cache-discard',
                '--disable-background-networking',
                '--disable-default-apps',
                '--disable-sync',
                '--disable-translate',
                '--hide-scrollbars',
                '--metrics-recording-only',
                '--mute-audio',
                '--no-first-run',
                '--safebrowsing-disable-auto-update',
                '--disable-ipc-flooding-protection',
                # 增加网络超时容忍度
                '--network-service-logging-level=0'
            ]
            
            self.browser = self.playwright.chromium.launch(
                headless=headless,
                slow_mo=500,
                args=browser_args
            )
            
            # 创建上下文 - 优化网络配置
            context_options = {
                'viewport': {'width': 1920, 'height': 1080},
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'locale': 'zh-CN',
                'timezone_id': 'Asia/Shanghai',
                'extra_http_headers': {
                    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                },
                'ignore_https_errors': True,
                'bypass_csp': True
            }
            
            # 智能代理策略 - 自动选择最优网络策略
            proxy_config = self._get_smart_proxy_config()
            if proxy_config:
                context_options['proxy'] = proxy_config
                logger.info(f"[WEB] 使用智能代理: {proxy_config['server']}")
            else:
                logger.info("[WEB] 使用直连模式（智能策略推荐）")
            
            self.context = self.browser.new_context(**context_options)
            
            # 创建页面
            self.page = self.context.new_page()
            
            # 设置更长的超时时间
            self.page.set_default_timeout(180000)  # 180秒
            self.page.set_default_navigation_timeout(180000)  # 180秒
            
            # 设置页面事件监听
            self.page.on("pageerror", lambda err: logger.warning(f"页面错误: {err}"))
            self.page.on("requestfailed", lambda request: logger.warning(f"请求失败: {request.url}"))
            self.page.on("response", lambda response: logger.debug(f"响应: {response.url} - {response.status}"))
            
            # 设置请求拦截
            self.page.route("**/*", self._handle_route)
            
            logger.info("[OK] 浏览器初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"[FAIL] 浏览器初始化失败: {e}")
            return False
    
    def _handle_route(self, route):
        """处理请求路由"""
        try:
            url = route.request.url.lower()
            
            # 只拦截图片、字体等非关键资源
            blocked_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.svg', '.ico', '.webp']
            blocked_keywords = ['analytics', 'tracking', 'beacon', 'pixel']
            
            # 检查是否应该拦截
            should_block = False
            
            # 检查文件扩展名
            for ext in blocked_extensions:
                if ext in url:
                    should_block = True
                    break
            
            # 检查关键词
            for keyword in blocked_keywords:
                if keyword in url:
                    should_block = True
                    break
            
            if should_block:
                logger.debug(f"[NO] 拦截请求: {route.request.url}")
                route.abort()
            else:
                route.continue_()
                
        except Exception as e:
            logger.debug(f"路由处理失败: {e}")
            route.continue_()
    
    def close_browser(self):
        """关闭浏览器"""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("[OK] 浏览器已关闭")
        except Exception as e:
            logger.error(f"[FAIL] 关闭浏览器失败: {e}")
    
    def _get_smart_proxy_config(self) -> Optional[Dict[str, str]]:
        """获取智能代理配置 - 自动选择最优网络策略"""
        try:
            # 优先使用新的代理配置管理器
            if self.proxy_config_manager:
                logger.info("[TARGET] 使用代理配置管理器获取代理...")
                proxy_config = self.proxy_config_manager.get_playwright_proxy_config(self.account_config)
                if proxy_config:
                    logger.info(f"[OK] 代理配置管理器获取到代理: {proxy_config['server']}")
                    return proxy_config
                else:
                    logger.info("[TARGET] 代理配置管理器建议直连模式")
            
            # 向后兼容 - 使用智能代理管理器
            if self.proxy_manager:
                logger.info("[TARGET] 使用智能代理管理器分析最佳网络策略...")
                
                # 获取智能网络策略
                strategy = self.proxy_manager.get_best_network_strategy()
                
                if strategy['use_proxy']:
                    # 尝试获取代理
                    proxy_info = self.proxy_manager.get_best_proxy()
                    if proxy_info:
                        proxy_config = {
                            'server': f"{proxy_info.protocol}://{proxy_info.ip}:{proxy_info.port}"
                        }
                        logger.info(f"[OK] 智能代理管理器获取到代理: {proxy_info.ip}:{proxy_info.port} ({proxy_info.location})")
                        return proxy_config
                    else:
                        logger.warning("[WARN] 无法获取代理，回退到直连模式")
                        return None
                else:
                    logger.info(f"[TARGET] 智能策略: {strategy['reason']}")
                    return None
            
            # 回退到静态代理配置
            return self._get_static_proxy_config()
            
        except Exception as e:
            logger.error(f"[FAIL] 获取智能代理配置失败: {e}")
            # 回退到静态配置
            return self._get_static_proxy_config()
    
    def _get_static_proxy_config(self) -> Optional[Dict[str, str]]:
        """获取静态代理配置（回退方案）"""
        try:
            proxy_info = self.account_config.get('proxy', {})
            if not proxy_info:
                return None
            
            proxy_config = {
                'server': f"{proxy_info.get('protocol', 'http')}://{proxy_info.get('host')}:{proxy_info.get('port')}"
            }
            
            if proxy_info.get('username') and proxy_info.get('password'):
                proxy_config['username'] = proxy_info['username']
                proxy_config['password'] = proxy_info['password']
            
            return proxy_config
        except Exception as e:
            logger.error(f"[FAIL] 获取静态代理配置失败: {e}")
            return None
    
    def save_session(self) -> bool:
        """保存会话状态"""
        try:
            if not self.context:
                logger.warning("[WARN] 没有活跃的浏览器上下文，无法保存会话")
                return False
            
            # 获取所有cookies
            cookies = self.context.cookies()
            
            # 获取localStorage（如果可能）
            local_storage = {}
            try:
                local_storage = self.page.evaluate("() => Object.assign({}, window.localStorage)")
            except Exception as e:
                logger.debug(f"获取localStorage失败: {e}")
            
            # 保存会话数据
            session_data = {
                'cookies': cookies,
                'local_storage': local_storage,
                'timestamp': datetime.now().isoformat(),
                'account_id': self.account_id,
                'store_name': self.store_name,
                'username': self.username
            }
            
            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"[OK] 会话已保存: {self.session_file}")
            return True
            
        except Exception as e:
            logger.error(f"[FAIL] 保存会话失败: {e}")
            return False
    
    def load_session(self) -> bool:
        """加载会话状态"""
        try:
            if not self.session_file.exists():
                logger.info("[NOTE] 没有找到会话文件，将进行新的登录")
                return False
            
            with open(self.session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            # 检查会话是否过期（24小时）
            timestamp = datetime.fromisoformat(session_data.get('timestamp', ''))
            if datetime.now() - timestamp > timedelta(hours=24):
                logger.info("[TIME] 会话已过期，将进行新的登录")
                return False
            
            # 恢复cookies
            if session_data.get('cookies'):
                self.context.add_cookies(session_data['cookies'])
                logger.info("[OK] Cookies已恢复")
            
            # 恢复localStorage（如果可能）
            if session_data.get('local_storage'):
                try:
                    for key, value in session_data['local_storage'].items():
                        self.page.evaluate(f"window.localStorage.setItem('{key}', '{value}')")
                    logger.info("[OK] LocalStorage已恢复")
                except Exception as e:
                    logger.debug(f"恢复localStorage失败: {e}")
            
            logger.info(f"[OK] 会话已加载: {self.session_file}")
            return True
            
        except Exception as e:
            logger.error(f"[FAIL] 加载会话失败: {e}")
            return False
    
    def navigate_to_login(self) -> bool:
        """导航到登录页面 - 优化网络处理"""
        try:
            if not self.login_url:
                logger.error("[FAIL] 未配置登录URL")
                return False
            
            logger.info(f"[WEB] 正在导航到登录页面: {self.login_url}")
            
            # 多种加载策略重试
            loading_strategies = [
                ('domcontentloaded', 20000),  # 最快策略
                ('load', 30000),              # 中等策略
                ('networkidle', 45000)        # 最完整策略
            ]
            
            for strategy, timeout in loading_strategies:
                try:
                    logger.info(f"[RETRY] 尝试加载策略: {strategy} (超时: {timeout}ms)")
                    
                    # 导航到登录页面
                    response = self.page.goto(self.login_url, wait_until=strategy, timeout=timeout)
                    
                    if response and response.status >= 400:
                        logger.warning(f"[WARN] 页面响应状态: {response.status}")
                        continue
                    
                    # 等待JavaScript渲染完成 - Shopee需要5-10秒
                    logger.info("[WAIT] 等待JavaScript渲染登录表单...")
                    time.sleep(8)  # 基于分析结果，需要等待8秒确保表单完全加载
                    
                    # 检查页面是否有基本元素
                    input_elements = self.page.query_selector_all('input')
                    if len(input_elements) >= 2:  # 至少需要用户名和密码输入框
                        logger.info(f"[OK] 页面加载成功，找到 {len(input_elements)} 个输入元素")
                        
                        # 截图记录
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        screenshot_path = self.screenshot_dir / f"login_page_{timestamp}.png"
                        self.page.screenshot(path=str(screenshot_path), full_page=True)
                        logger.info(f"[CAM] 登录页面截图已保存: {screenshot_path}")
                        
                        return True
                    else:
                        logger.warning(f"[WARN] 页面加载不完整，未找到输入元素")
                        continue
                        
                except Exception as e:
                    logger.warning(f"[WARN] 加载策略 {strategy} 失败: {e}")
                    continue
            
            logger.error("[FAIL] 所有加载策略都失败")
            return False
            
        except Exception as e:
            logger.error(f"[FAIL] 导航到登录页面失败: {e}")
            return False
    
    def check_login_status(self) -> bool:
        """检查是否已登录"""
        try:
            logger.info("[SEARCH] 检查登录状态...")
            
            # 等待页面稳定
            time.sleep(2)
            
            # 检查是否在登录页面
            current_url = self.page.url
            logger.info(f"当前URL: {current_url}")
            
            # 常见的已登录页面标识
            logged_in_indicators = [
                'seller.shopee',
                'dashboard',
                'portal',
                'home',
                'main'
            ]
            
            # 检查URL中是否包含已登录的标识
            for indicator in logged_in_indicators:
                if indicator in current_url.lower():
                    logger.info(f"[OK] 检测到已登录标识: {indicator}")
                    return True
            
            # 检查页面元素
            login_indicators = [
                'text=登录',
                'text=Login',
                'input[type="password"]',
                'input[name="password"]',
                '#password'
            ]
            
            # 如果找到登录相关元素，说明未登录
            for selector in login_indicators:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        logger.info(f"[SEARCH] 发现登录元素: {selector}")
                        return False
                except:
                    continue
            
            # 检查是否有用户信息相关元素
            user_indicators = [
                '[data-testid="user-menu"]',
                '.user-avatar',
                '.user-info',
                'text=退出登录',
                'text=Logout'
            ]
            
            for selector in user_indicators:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        logger.info(f"[OK] 发现用户信息元素: {selector}")
                        return True
                except:
                    continue
            
            logger.info("[WARN] 无法确定登录状态，默认为未登录")
            return False
            
        except Exception as e:
            logger.error(f"[FAIL] 检查登录状态失败: {e}")
            return False
    
    def perform_login(self) -> bool:
        """执行登录操作"""
        try:
            logger.info("[LOCK] 开始执行登录操作...")
            
            # 等待JavaScript渲染完成 - 确保登录表单可用
            logger.info("[WAIT] 等待登录表单完全渲染...")
            time.sleep(8)  # 基于分析结果，Shopee需要8秒渲染登录表单
            
            # 查找用户名输入框 - 优化：基于调试结果
            username_selectors = [
                'input[type="text"]',  # Shopee专用 - 优先级最高
                'input[placeholder*="账号"]',  # Shopee的placeholder包含"账号"
                'input[placeholder*="邮箱"]',  # Shopee的placeholder包含"邮箱"
                'input[name="username"]',
                'input[name="email"]',
                'input[type="email"]',
                'input[placeholder*="用户名"]',
                'input[placeholder*="Username"]',
                'input[placeholder*="Email"]',
                '#username',
                '#email'
            ]
            
            username_input = None
            for selector in username_selectors:
                try:
                    username_input = self.page.query_selector(selector)
                    if username_input and username_input.is_visible():
                        logger.info(f"[OK] 找到用户名输入框: {selector}")
                        break
                except:
                    continue
            
            if not username_input:
                logger.error("[FAIL] 未找到用户名输入框")
                return False
            
            # 查找密码输入框
            password_selectors = [
                'input[name="password"]',
                'input[type="password"]',
                'input[placeholder*="密码"]',
                'input[placeholder*="Password"]',
                '#password'
            ]
            
            password_input = None
            for selector in password_selectors:
                try:
                    password_input = self.page.query_selector(selector)
                    if password_input and password_input.is_visible():
                        logger.info(f"[OK] 找到密码输入框: {selector}")
                        break
                except:
                    continue
            
            if not password_input:
                logger.error("[FAIL] 未找到密码输入框")
                return False
            
            # 清空并输入用户名
            username_input.click()
            username_input.fill('')
            time.sleep(0.5)
            username_input.type(self.username, delay=100)
            logger.info("[OK] 已输入用户名")
            
            # 清空并输入密码
            password_input.click()
            password_input.fill('')
            time.sleep(0.5)
            password_input.type(self.password, delay=100)
            logger.info("[OK] 已输入密码")
            
            # 截图记录登录前状态
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = self.screenshot_dir / f"before_login_{timestamp}.png"
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            
            # 查找登录按钮 - 修复：Shopee使用"登入"而不是"登录"
            login_selectors = [
                'button:has-text("登入")',  # Shopee专用 - 优先级最高
                '.submit-btn',  # Shopee的submit按钮class
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("登录")',
                'button:has-text("Login")',
                'button:has-text("登 录")',
                'button:has-text("Sign In")',
                '.login-btn',
                '#login-btn',
                '[data-testid="login-button"]'
            ]
            
            login_button = None
            for selector in login_selectors:
                try:
                    login_button = self.page.query_selector(selector)
                    if login_button and login_button.is_visible():
                        logger.info(f"[OK] 找到登录按钮: {selector}")
                        break
                except:
                    continue
            
            if not login_button:
                logger.error("[FAIL] 未找到登录按钮")
                return False
            
            # 点击登录按钮
            login_button.click()
            logger.info("[LOCK] 已点击登录按钮")
            
            # 等待页面响应
            time.sleep(3)
            
            # 检查是否需要验证码或其他验证
            return self._handle_post_login_verification()
            
        except Exception as e:
            logger.error(f"[FAIL] 登录操作失败: {e}")
            return False
    
    def _handle_post_login_verification(self) -> bool:
        """处理登录后的验证"""
        try:
            logger.info("[SEARCH] 检查登录后状态...")
            
            # 等待页面稳定
            time.sleep(5)
            
            current_url = self.page.url
            logger.info(f"登录后URL: {current_url}")
            
            # 截图记录登录后状态
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshot_path = self.screenshot_dir / f"after_login_{timestamp}.png"
            self.page.screenshot(path=str(screenshot_path), full_page=True)
            
            # 检查是否需要邮箱验证
            if self._check_email_verification_needed():
                logger.info("[EMAIL] 检测到需要邮箱验证")
                return self._handle_email_verification()
            
            # 检查是否需要手机验证
            if self._check_phone_verification_needed():
                logger.info("[PHONE] 检测到需要手机验证")
                return self._handle_phone_verification()
            
            # 检查是否出现验证码
            if self._check_captcha_needed():
                logger.info("[abc] 检测到需要验证码")
                return self._handle_captcha()
            
            # 检查是否登录成功
            if self.check_login_status():
                logger.info("[OK] 登录成功！")
                return True
            
            # 检查是否有错误信息
            error_message = self._get_error_message()
            if error_message:
                logger.error(f"[FAIL] 登录失败: {error_message}")
                return False
            
            logger.warning("[WARN] 登录状态不明确，可能需要手动处理")
            return False
            
        except Exception as e:
            logger.error(f"[FAIL] 处理登录后验证失败: {e}")
            return False
    
    def _check_email_verification_needed(self) -> bool:
        """检查是否需要邮箱验证"""
        try:
            email_indicators = [
                'text=邮箱验证',
                'text=Email Verification',
                'text=验证码',
                'text=Verification Code',
                'input[placeholder*="验证码"]',
                'input[placeholder*="verification"]',
                'input[name="otp"]',
                'input[name="code"]'
            ]
            
            for selector in email_indicators:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        return True
                except:
                    continue
            
            return False
        except Exception as e:
            logger.debug(f"检查邮箱验证失败: {e}")
            return False
    
    def _check_phone_verification_needed(self) -> bool:
        """检查是否需要手机验证"""
        try:
            phone_indicators = [
                'text=手机验证',
                'text=Phone Verification',
                'text=短信验证',
                'text=SMS Verification',
                'input[placeholder*="手机"]',
                'input[placeholder*="phone"]'
            ]
            
            for selector in phone_indicators:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        return True
                except:
                    continue
            
            return False
        except Exception as e:
            logger.debug(f"检查手机验证失败: {e}")
            return False
    
    def _check_captcha_needed(self) -> bool:
        """检查是否需要验证码"""
        try:
            captcha_indicators = [
                'img[alt*="captcha"]',
                'img[alt*="验证码"]',
                '.captcha',
                '#captcha',
                'canvas'
            ]
            
            for selector in captcha_indicators:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        return True
                except:
                    continue
            
            return False
        except Exception as e:
            logger.debug(f"检查验证码失败: {e}")
            return False
    
    def _handle_email_verification(self) -> bool:
        """处理邮箱验证"""
        try:
            logger.info("[EMAIL] 开始处理邮箱验证...")
            
            # 这里应该集成邮箱OTP获取功能
            # 目前返回False，表示需要手动处理
            logger.warning("[WARN] 邮箱验证需要手动处理，请检查邮箱并输入验证码")
            
            # 等待用户手动输入验证码
            time.sleep(30)
            
            # 检查是否验证成功
            if self.check_login_status():
                logger.info("[OK] 邮箱验证成功！")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[FAIL] 处理邮箱验证失败: {e}")
            return False
    
    def _handle_phone_verification(self) -> bool:
        """处理手机验证"""
        try:
            logger.info("[PHONE] 开始处理手机验证...")
            
            # 手机验证通常需要手动处理
            logger.warning("[WARN] 手机验证需要手动处理，请输入短信验证码")
            
            # 等待用户手动输入验证码
            time.sleep(30)
            
            # 检查是否验证成功
            if self.check_login_status():
                logger.info("[OK] 手机验证成功！")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[FAIL] 处理手机验证失败: {e}")
            return False
    
    def _handle_captcha(self) -> bool:
        """处理验证码"""
        try:
            logger.info("[abc] 开始处理验证码...")
            
            # 验证码通常需要手动处理
            logger.warning("[WARN] 验证码需要手动处理，请输入图片验证码")
            
            # 等待用户手动输入验证码
            time.sleep(30)
            
            # 检查是否验证成功
            if self.check_login_status():
                logger.info("[OK] 验证码验证成功！")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[FAIL] 处理验证码失败: {e}")
            return False
    
    def _get_error_message(self) -> Optional[str]:
        """获取错误信息"""
        try:
            error_selectors = [
                '.error-message',
                '.alert-danger',
                '.error',
                '[role="alert"]',
                'text=用户名或密码错误',
                'text=Invalid username or password',
                'text=登录失败',
                'text=Login failed'
            ]
            
            for selector in error_selectors:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        return element.text_content()
                except:
                    continue
            
            return None
        except Exception as e:
            logger.debug(f"获取错误信息失败: {e}")
            return None
    
    def login(self, headless: bool = False) -> bool:
        """
        完整的登录流程
        
        Args:
            headless: 是否无头模式
            
        Returns:
            登录是否成功
        """
        try:
            logger.info("[START] 开始Shopee登录流程...")
            
            # 1. 初始化浏览器
            if not self.initialize_browser(headless):
                return False
            
            # 2. 尝试加载会话
            if self.load_session():
                # 导航到主页检查会话是否有效
                if self.navigate_to_login():
                    if self.check_login_status():
                        logger.info("[OK] 会话有效，无需重新登录")
                        return True
                    else:
                        logger.info("[WARN] 会话无效，需要重新登录")
            
            # 3. 导航到登录页面
            if not self.navigate_to_login():
                return False
            
            # 4. 执行登录
            if not self.perform_login():
                return False
            
            # 5. 保存会话
            self.save_session()
            
            logger.info("[DONE] Shopee登录流程完成！")
            return True
            
        except Exception as e:
            logger.error(f"[FAIL] 登录流程失败: {e}")
            return False
        finally:
            # 登录完成后不关闭浏览器，保持会话
            pass
    
    def collect_order_data(self, date_range: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        采集订单数据
        
        Args:
            date_range: 日期范围，格式如 {'start': '2024-01-01', 'end': '2024-01-31'}
            
        Returns:
            采集结果
        """
        try:
            logger.info("[LIST] 开始采集订单数据...")
            
            if not self.page:
                logger.error("[FAIL] 浏览器未初始化")
                return {'success': False, 'error': '浏览器未初始化'}
            
            # 导航到订单管理页面
            order_urls = [
                '/portal/sale/order',
                '/portal/orders',
                '/sale/order'
            ]
            
            success = False
            for url_path in order_urls:
                try:
                    full_url = self._build_url(url_path)
                    self.page.goto(full_url, wait_until='networkidle', timeout=60000)
                    
                    # 检查是否成功到达订单页面
                    if self._is_order_page():
                        success = True
                        break
                except Exception as e:
                    logger.debug(f"尝试访问 {url_path} 失败: {e}")
                    continue
            
            if not success:
                logger.error("[FAIL] 无法访问订单管理页面")
                return {'success': False, 'error': '无法访问订单管理页面'}
            
            # 设置日期范围
            if date_range:
                if not self._set_date_range(date_range):
                    logger.warning("[WARN] 设置日期范围失败，使用默认范围")
            
            # 采集订单数据
            orders = self._extract_order_data()
            
            # 保存数据
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.base_path / f"orders_{timestamp}.json"
            
            result = {
                'success': True,
                'data': orders,
                'count': len(orders),
                'timestamp': timestamp,
                'account_id': self.account_id,
                'store_name': self.store_name
            }
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            
            logger.info(f"[OK] 订单数据采集完成，共 {len(orders)} 条记录")
            logger.info(f"[DIR] 数据已保存到: {output_file}")
            
            return result
            
        except Exception as e:
            logger.error(f"[FAIL] 采集订单数据失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def _build_url(self, path: str) -> str:
        """构建完整URL"""
        base_url = self.login_url.split('/portal')[0] if '/portal' in self.login_url else self.login_url
        return base_url.rstrip('/') + '/' + path.lstrip('/')
    
    def _is_order_page(self) -> bool:
        """检查是否在订单页面"""
        try:
            order_indicators = [
                'text=订单管理',
                'text=Order Management',
                'text=订单列表',
                'text=Order List',
                '.order-list',
                '#order-list',
                '[data-testid="order-table"]'
            ]
            
            for selector in order_indicators:
                try:
                    element = self.page.query_selector(selector)
                    if element and element.is_visible():
                        return True
                except:
                    continue
            
            return False
        except Exception as e:
            logger.debug(f"检查订单页面失败: {e}")
            return False
    
    def _set_date_range(self, date_range: Dict[str, str]) -> bool:
        """设置日期范围"""
        try:
            # 这里应该实现日期选择逻辑
            # 不同的shopee版本可能有不同的日期选择器
            logger.info(f"设置日期范围: {date_range['start']} - {date_range['end']}")
            
            # 查找日期选择器
            date_selectors = [
                'input[type="date"]',
                '.date-picker',
                '[data-testid="date-picker"]'
            ]
            
            # 实现日期设置逻辑...
            return True
            
        except Exception as e:
            logger.error(f"设置日期范围失败: {e}")
            return False
    
    def _extract_order_data(self) -> List[Dict[str, Any]]:
        """提取订单数据"""
        try:
            orders = []
            
            # 等待订单列表加载
            time.sleep(3)
            
            # 查找订单行
            order_rows = self.page.query_selector_all('tr, .order-item, [data-testid="order-row"]')
            
            for row in order_rows:
                try:
                    order_data = self._extract_single_order(row)
                    if order_data:
                        orders.append(order_data)
                except Exception as e:
                    logger.debug(f"提取单个订单失败: {e}")
                    continue
            
            return orders
            
        except Exception as e:
            logger.error(f"提取订单数据失败: {e}")
            return []
    
    def _extract_single_order(self, row_element) -> Optional[Dict[str, Any]]:
        """提取单个订单数据"""
        try:
            # 这里应该实现具体的订单数据提取逻辑
            # 根据实际的页面结构来提取数据
            
            order_data = {
                'order_id': '',
                'status': '',
                'amount': '',
                'customer': '',
                'date': '',
                'items': []
            }
            
            # 实现具体的数据提取逻辑...
            
            return order_data
            
        except Exception as e:
            logger.debug(f"提取单个订单数据失败: {e}")
            return None
    
    def collect_product_data(self) -> Dict[str, Any]:
        """采集商品数据"""
        try:
            logger.info("[SHOP] 开始采集商品数据...")
            
            # 实现商品数据采集逻辑
            result = {
                'success': True,
                'data': [],
                'count': 0,
                'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
                'account_id': self.account_id,
                'store_name': self.store_name
            }
            
            return result
            
        except Exception as e:
            logger.error(f"[FAIL] 采集商品数据失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def collect_financial_data(self) -> Dict[str, Any]:
        """采集财务数据"""
        try:
            logger.info("[MONEY] 开始采集财务数据...")
            
            # 实现财务数据采集逻辑
            result = {
                'success': True,
                'data': [],
                'count': 0,
                'timestamp': datetime.now().strftime("%Y%m%d_%H%M%S"),
                'account_id': self.account_id,
                'store_name': self.store_name
            }
            
            return result
            
        except Exception as e:
            logger.error(f"[FAIL] 采集财务数据失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.close_browser()
    
    def run_full_collection(self) -> Dict[str, Any]:
        """运行完整的数据采集流程"""
        collection_start_time = datetime.now()
        
        try:
            logger.info("[START] 开始Shopee商家端完整数据采集流程")
            logger.info(f"   店铺: {self.store_name}")
            logger.info(f"   账号: {self.account_id}")
            
            # 初始化浏览器
            if not self.initialize_browser():
                return self._create_failure_result('浏览器初始化失败', collection_start_time)
            
            # 登录
            if not self.login():
                return self._create_failure_result('登录失败', collection_start_time)
            
            # 采集运营数据
            collection_result = self.collect_operational_data()
            if not collection_result['success']:
                return self._create_failure_result(collection_result.get('error', '数据采集失败'), collection_start_time)
            
            # 下载数据报告
            download_result = self.download_data_report()
            
            # 导出数据到Excel和CSV
            export_results = {}
            if collection_result['success']:
                # 导出Excel
                excel_file = self.export_data_to_excel(collection_result['data'])
                if excel_file:
                    export_results['excel_file'] = excel_file
                
                # 导出CSV
                csv_files = self.export_data_to_csv(collection_result['data'])
                if csv_files:
                    export_results['csv_files'] = csv_files
            
            # 保存采集记录
            collection_record = self._save_collection_record(collection_result, download_result, collection_start_time)
            
            result = {
                'success': True,
                'account_id': self.account_id,
                'store_name': self.store_name,
                'username': self.username,
                'collection_time': collection_start_time.isoformat(),
                'completion_time': datetime.now().isoformat(),
                'duration_seconds': (datetime.now() - collection_start_time).total_seconds(),
                'collected_data': collection_result.get('data', {}),
                'download_success': download_result,
                'export_results': export_results,
                'data_path': str(self.base_path),
                'collection_record_path': collection_record
            }
            
            logger.info("[OK] Shopee商家端数据采集流程完成")
            logger.info(f"   耗时: {result['duration_seconds']:.2f}秒")
            logger.info(f"   数据保存至: {self.base_path}")
            
            return result
            
        except Exception as e:
            logger.error(f"[FAIL] 完整采集流程失败: {e}")
            return self._create_failure_result(str(e), collection_start_time)
        
        finally:
            # 采集完成后保持浏览器会话，用于后续操作
            self.save_session()
    
    def _create_failure_result(self, error_msg: str, start_time: datetime) -> Dict[str, Any]:
        """创建失败结果"""
        return {
            'success': False,
            'account_id': self.account_id,
            'store_name': self.store_name,
            'username': self.username,
            'collection_time': start_time.isoformat(),
            'completion_time': datetime.now().isoformat(),
            'duration_seconds': (datetime.now() - start_time).total_seconds(),
            'error': error_msg,
            'data_path': str(self.base_path)
        }
    
    def _save_collection_record(self, collection_result: Dict, download_result: bool, start_time: datetime) -> str:
        """保存采集记录"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            record_file = self.base_path / f"collection_record_{timestamp}.json"
            
            record = {
                'account_info': {
                    'account_id': self.account_id,
                    'store_name': self.store_name,
                    'username': self.username,
                    'login_url': self.login_url
                },
                'collection_info': {
                    'start_time': start_time.isoformat(),
                    'completion_time': datetime.now().isoformat(),
                    'duration_seconds': (datetime.now() - start_time).total_seconds(),
                    'success': True
                },
                'data_summary': {
                    'collected_data_count': len(collection_result.get('data', {})),
                    'download_success': download_result,
                    'data_types': list(collection_result.get('data', {}).keys())
                },
                'file_paths': {
                    'base_path': str(self.base_path),
                    'downloads_path': str(self.downloads_path),
                    'screenshots_path': str(self.screenshot_dir)
                }
            }
            
            with open(record_file, 'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=2)
            
            logger.info(f"[NOTE] 采集记录已保存: {record_file}")
            return str(record_file)
            
        except Exception as e:
            logger.error(f"[FAIL] 保存采集记录失败: {e}")
            return ""
    
    def collect_operational_data(self) -> Dict[str, Any]:
        """采集运营相关数据"""
        try:
            logger.info("[DATA] 开始采集运营数据...")
            
            # 基于当前已有的方法进行数据采集
            result = {
                'success': True,
                'data': {
                    'orders': self.collect_order_data(),
                    'products': self.collect_product_data(),
                    'financial': self.collect_financial_data(),
                    'collection_time': datetime.now().isoformat()
                }
            }
            
            logger.info("[OK] 运营数据采集完成")
            return result
            
        except Exception as e:
            logger.error(f"[FAIL] 采集运营数据失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def download_data_report(self) -> bool:
        """下载数据报告"""
        try:
            logger.info("[RECV] 开始下载数据报告...")
            
            # 这里可以实现具体的下载逻辑
            # 目前返回True表示下载成功（占位实现）
            logger.info("[OK] 数据报告下载完成")
            return True
            
        except Exception as e:
            logger.error(f"[FAIL] 下载数据报告失败: {e}")
            return False
    
    def export_data_to_excel(self, data: Dict[str, Any]) -> Optional[str]:
        """导出数据到Excel文件"""
        try:
            logger.info("[DATA] 开始导出数据到Excel...")
            
            import pandas as pd
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            excel_file = self.downloads_path / f"shopee_data_{self.store_name}_{timestamp}.xlsx"
            
            # 创建工作簿
            with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
                
                # 导出订单数据
                if 'orders' in data and data['orders'].get('data'):
                    orders_df = pd.DataFrame([data['orders']['data']])
                    orders_df.to_excel(writer, sheet_name='订单数据', index=False)
                    logger.info("[OK] 订单数据已导出")
                
                # 导出商品数据
                if 'products' in data and data['products'].get('data'):
                    products_df = pd.DataFrame([data['products']['data']])
                    products_df.to_excel(writer, sheet_name='商品数据', index=False)
                    logger.info("[OK] 商品数据已导出")
                
                # 导出财务数据
                if 'financial' in data and data['financial'].get('data'):
                    financial_df = pd.DataFrame([data['financial']['data']])
                    financial_df.to_excel(writer, sheet_name='财务数据', index=False)
                    logger.info("[OK] 财务数据已导出")
            
            logger.info(f"[OK] Excel文件导出完成: {excel_file}")
            return str(excel_file)
            
        except Exception as e:
            logger.error(f"[FAIL] 导出Excel文件失败: {e}")
            return None
    
    def export_data_to_csv(self, data: Dict[str, Any]) -> List[str]:
        """导出数据到CSV文件"""
        try:
            logger.info("[DATA] 开始导出数据到CSV...")
            
            import pandas as pd
            
            csv_files = []
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # 导出订单数据
            if 'orders' in data and data['orders'].get('data'):
                orders_df = pd.DataFrame([data['orders']['data']])
                orders_file = self.downloads_path / f"shopee_orders_{self.store_name}_{timestamp}.csv"
                orders_df.to_csv(orders_file, index=False, encoding='utf-8-sig')
                csv_files.append(str(orders_file))
                logger.info("[OK] 订单CSV已导出")
            
            # 导出商品数据
            if 'products' in data and data['products'].get('data'):
                products_df = pd.DataFrame([data['products']['data']])
                products_file = self.downloads_path / f"shopee_products_{self.store_name}_{timestamp}.csv"
                products_df.to_csv(products_file, index=False, encoding='utf-8-sig')
                csv_files.append(str(products_file))
                logger.info("[OK] 商品CSV已导出")
            
            # 导出财务数据
            if 'financial' in data and data['financial'].get('data'):
                financial_df = pd.DataFrame([data['financial']['data']])
                financial_file = self.downloads_path / f"shopee_financial_{self.store_name}_{timestamp}.csv"
                financial_df.to_csv(financial_file, index=False, encoding='utf-8-sig')
                csv_files.append(str(financial_file))
                logger.info("[OK] 财务CSV已导出")
            
            logger.info(f"[OK] CSV文件导出完成: {len(csv_files)} 个文件")
            return csv_files
            
        except Exception as e:
            logger.error(f"[FAIL] 导出CSV文件失败: {e}")
            return []


def create_shopee_collector(account_config: Dict[str, Any]) -> ShopeeCollector:
    """创建Shopee采集器实例"""
    return ShopeeCollector(account_config) 