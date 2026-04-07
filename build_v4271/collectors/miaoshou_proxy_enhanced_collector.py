#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
妙手ERP专用代理增强采集器
集成专用代理管理器，解决VPN环境下的访问问题

作者: AI Assistant
日期: 2025-01-08
"""

import sys
sys.path.append('.')

from playwright.sync_api import sync_playwright
import time
from pathlib import Path
from typing import Dict, Optional, List
from config.proxy_manager import ProxyManager
from loguru import logger


class MiaoshouProxyEnhancedCollector:
    """妙手ERP专用代理增强采集器"""
    
    def __init__(self, account_config: Dict):
        """
        初始化采集器
        
        Args:
            account_config: 账号配置
        """
        self.account_config = account_config
        self.login_url = account_config.get('login_url', 'https://erp.91miaoshou.com')
        self.username = account_config.get('username', '')
        self.password = account_config.get('password', '')
        
        # 初始化代理管理器
        self.proxy_manager = ProxyManager()
        
        # Playwright 相关
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        
        # 设置日志
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志"""
        log_file = Path("temp/logs") / f"miaoshou_enhanced_{time.strftime('%Y%m%d')}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        logger.add(
            log_file,
            rotation="1 day",
            retention="30 days",
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
        )
    
    def setup_browser(self) -> bool:
        """
        设置浏览器 - 使用代理管理器智能选择
        
        Returns:
            bool: 设置是否成功
        """
        try:
            # 获取代理设置
            proxy_type, proxy_config, browser_args = self.proxy_manager.get_proxy_setting(self.login_url)
            
            logger.info(f"🔧 代理设置 - URL: {self.login_url}")
            logger.info(f"   代理类型: {proxy_type}")
            logger.info(f"   代理配置: {proxy_config}")
            logger.info(f"   浏览器参数: {browser_args}")
            
            # 启动 Playwright
            self.playwright = sync_playwright().start()
            
            # 根据代理类型配置浏览器
            launch_args = {
                'headless': False,  # 显示浏览器便于调试
                'args': browser_args,
            }
            
            # 如果有自定义代理配置
            if proxy_config.get('type') == 'custom' and proxy_config.get('server'):
                launch_args['proxy'] = {
                    'server': proxy_config['server']
                }
                if proxy_config.get('username'):
                    launch_args['proxy']['username'] = proxy_config['username']
                    launch_args['proxy']['password'] = proxy_config.get('password', '')
            
            # 启动浏览器
            self.browser = self.playwright.chromium.launch(**launch_args)
            
            # 创建上下文
            context_args = {
                'ignore_https_errors': True,
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                'viewport': {'width': 1366, 'height': 768},
            }
            
            self.context = self.browser.new_context(**context_args)
            self.page = self.context.new_page()
            self.page.set_default_timeout(30000)
            
            logger.info(f"✅ 浏览器设置成功 - 代理类型: {proxy_type}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 浏览器设置失败: {e}")
            return False
    
    def test_website_access(self) -> Dict:
        """
        测试网站访问性能
        
        Returns:
            Dict: 访问测试结果
        """
        if not self.page:
            return {'success': False, 'error': '浏览器未初始化'}
        
        try:
            logger.info(f"🧪 测试访问: {self.login_url}")
            start_time = time.time()
            
            # 访问网站
            response = self.page.goto(self.login_url, wait_until='domcontentloaded')
            load_time = time.time() - start_time
            
            # 获取页面信息
            status = response.status if response else 'Unknown'
            title = self.page.title()
            current_url = self.page.url
            
            # 检查关键元素
            has_username_field = self.page.locator('input[name*="user"], input[name*="account"], input[type="text"]').count() > 0
            has_password_field = self.page.locator('input[type="password"]').count() > 0
            has_login_button = self.page.locator('button:has-text("登录"), input[type="submit"]').count() > 0
            
            # 检查妙手ERP标识
            page_content = self.page.content()
            has_miaoshou_content = '妙手' in page_content or 'miaoshou' in page_content.lower()
            
            # 判断访问质量
            if load_time < 3.0:
                access_quality = 'excellent'
                quality_desc = '极佳 - 可能使用直连'
            elif load_time < 8.0:
                access_quality = 'good' 
                quality_desc = '良好 - 正常访问速度'
            else:
                access_quality = 'poor'
                quality_desc = '较差 - 可能网络受限'
            
            result = {
                'success': True,
                'status_code': status,
                'title': title,
                'current_url': current_url,
                'load_time': round(load_time, 2),
                'access_quality': access_quality,
                'quality_desc': quality_desc,
                'elements_found': {
                    'username_field': has_username_field,
                    'password_field': has_password_field,
                    'login_button': has_login_button,
                    'miaoshou_content': has_miaoshou_content,
                },
                'ready_for_login': has_username_field and has_password_field and has_miaoshou_content
            }
            
            logger.info(f"✅ 访问测试完成:")
            logger.info(f"   加载时间: {load_time:.2f}s")
            logger.info(f"   访问质量: {quality_desc}")
            logger.info(f"   登录准备: {'就绪' if result['ready_for_login'] else '未就绪'}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 访问测试失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def login(self) -> bool:
        """
        执行登录
        
        Returns:
            bool: 登录是否成功
        """
        if not self.page:
            logger.error("❌ 浏览器未初始化")
            return False
        
        if not self.username or not self.password:
            logger.error("❌ 用户名或密码未配置")
            return False
        
        try:
            logger.info(f"🔐 开始登录: {self.username}")
            
            # 等待页面加载
            self.page.wait_for_load_state('domcontentloaded')
            
            # 查找并填写用户名
            username_selectors = [
                'input[name*="user"]',
                'input[name*="account"]', 
                'input[placeholder*="用户名"]',
                'input[placeholder*="账号"]',
                'input[type="text"]'
            ]
            
            username_filled = False
            for selector in username_selectors:
                try:
                    username_field = self.page.locator(selector).first
                    if username_field.count() > 0:
                        username_field.fill(self.username)
                        username_filled = True
                        logger.info(f"✅ 用户名填写成功: {selector}")
                        break
                except:
                    continue
            
            if not username_filled:
                logger.error("❌ 找不到用户名输入框")
                return False
            
            # 查找并填写密码
            password_field = self.page.locator('input[type="password"]').first
            if password_field.count() > 0:
                password_field.fill(self.password)
                logger.info("✅ 密码填写成功")
            else:
                logger.error("❌ 找不到密码输入框")
                return False
            
            # 查找并点击登录按钮
            login_selectors = [
                'button:has-text("登录")',
                'input[type="submit"]',
                'button[type="submit"]',
                '.login-btn',
                '#login-btn'
            ]
            
            login_clicked = False
            for selector in login_selectors:
                try:
                    login_button = self.page.locator(selector).first
                    if login_button.count() > 0:
                        login_button.click()
                        login_clicked = True
                        logger.info(f"✅ 登录按钮点击成功: {selector}")
                        break
                except:
                    continue
            
            if not login_clicked:
                logger.error("❌ 找不到登录按钮")
                return False
            
            # 等待登录结果
            time.sleep(3)
            
            # 检查登录是否成功
            current_url = self.page.url
            if 'login' not in current_url.lower() and current_url != self.login_url:
                logger.info(f"🎉 登录成功! 当前页面: {current_url}")
                return True
            else:
                logger.warning(f"⚠️ 登录可能失败，仍在登录页面: {current_url}")
                return False
            
        except Exception as e:
            logger.error(f"❌ 登录过程出错: {e}")
            return False
    
    def collect_data(self) -> Dict:
        """
        采集数据 - 示例实现
        
        Returns:
            Dict: 采集结果
        """
        if not self.page:
            return {'success': False, 'error': '浏览器未初始化'}
        
        try:
            logger.info("📊 开始数据采集...")
            
            # 这里实现具体的数据采集逻辑
            # 例如：导航到订单页面、提取订单数据等
            
            # 示例：获取页面基本信息
            title = self.page.title()
            url = self.page.url
            
            # 示例：提取一些基本元素
            links = self.page.locator('a').count()
            buttons = self.page.locator('button').count()
            
            result = {
                'success': True,
                'data': {
                    'page_title': title,
                    'page_url': url,
                    'elements_count': {
                        'links': links,
                        'buttons': buttons,
                    },
                    'collection_time': time.strftime('%Y-%m-%d %H:%M:%S')
                }
            }
            
            logger.info(f"✅ 数据采集完成: {result['data']}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 数据采集失败: {e}")
            return {'success': False, 'error': str(e)}
    
    def cleanup(self):
        """清理资源"""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            logger.info("✅ 资源清理完成")
        except Exception as e:
            logger.error(f"❌ 资源清理失败: {e}")
    
    def run_full_process(self) -> Dict:
        """
        运行完整流程
        
        Returns:
            Dict: 运行结果
        """
        logger.info("🚀 开始妙手ERP增强采集流程")
        
        try:
            # 1. 设置浏览器
            if not self.setup_browser():
                return {'success': False, 'error': '浏览器设置失败'}
            
            # 2. 测试网站访问
            access_result = self.test_website_access()
            if not access_result['success']:
                return {'success': False, 'error': f"网站访问失败: {access_result.get('error')}"}
            
            # 3. 执行登录
            if not self.login():
                return {'success': False, 'error': '登录失败'}
            
            # 4. 采集数据
            collect_result = self.collect_data()
            if not collect_result['success']:
                return {'success': False, 'error': f"数据采集失败: {collect_result.get('error')}"}
            
            # 5. 返回完整结果
            result = {
                'success': True,
                'access_info': access_result,
                'collection_result': collect_result,
                'summary': {
                    'login_url': self.login_url,
                    'username': self.username,
                    'access_quality': access_result.get('access_quality'),
                    'load_time': access_result.get('load_time'),
                    'collection_time': collect_result['data'].get('collection_time')
                }
            }
            
            logger.info("🎉 妙手ERP增强采集流程完成")
            return result
            
        except Exception as e:
            logger.error(f"❌ 采集流程出错: {e}")
            return {'success': False, 'error': str(e)}
        
        finally:
            self.cleanup()


def test_enhanced_collector():
    """测试增强采集器"""
    print("🧪 测试妙手ERP增强采集器")
    print("="*60)
    
    # 测试账号配置
    test_account = {
        'login_url': 'https://erp.91miaoshou.com',
        'username': 'test_user',  # 请替换为实际用户名
        'password': 'test_pass',  # 请替换为实际密码
        'platform': 'miaoshou',
        'description': '妙手ERP测试账号'
    }
    
    # 创建采集器
    collector = MiaoshouProxyEnhancedCollector(test_account)
    
    # 运行完整流程
    result = collector.run_full_process()
    
    # 显示结果
    print("\n📊 采集结果:")
    print("="*40)
    
    if result['success']:
        print("🎉 采集成功!")
        summary = result.get('summary', {})
        print(f"   登录URL: {summary.get('login_url')}")
        print(f"   用户名: {summary.get('username')}")
        print(f"   访问质量: {summary.get('access_quality')}")
        print(f"   加载时间: {summary.get('load_time')}s")
        print(f"   采集时间: {summary.get('collection_time')}")
    else:
        print(f"❌ 采集失败: {result.get('error')}")
    
    return result


if __name__ == "__main__":
    # 首先测试代理管理器
    print("🔧 测试代理管理器...")
    from config.proxy_manager import test_proxy_manager
    test_proxy_manager()
    
    print("\n" + "="*80)
    
    # 然后测试增强采集器
    test_enhanced_collector() 