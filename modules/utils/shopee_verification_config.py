#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Shopee验证码处理统一配置管理

模块化设计：
- 统一配置管理，避免硬编码
- 支持多邮箱类型的配置
- 便于扩展和维护
"""

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any

@dataclass
class VerificationConfig:
    """验证码处理配置"""
    
    # 全局等待时间配置（解决时机问题）
    button_click_wait: float = 5.0  # 点击"发送至邮箱"按钮后等待时间
    page_load_wait: float = 3.0     # 页面加载等待时间
    element_find_timeout: int = 10000  # 元素查找超时时间（毫秒）
    
    # 重试配置
    max_retries: int = 3            # 最大重试次数
    retry_interval: float = 2.0     # 重试间隔时间
    
    # 验证码获取配置
    email_check_interval: float = 5.0    # 邮件检查间隔
    email_max_wait_time: int = 120       # 邮件等待最大时间（秒）
    verification_code_timeout: int = 300  # 验证码总超时时间（秒）
    
    # 调试配置
    enable_debug_screenshots: bool = True  # 启用调试截图
    enable_detailed_logging: bool = True   # 启用详细日志
    debug_screenshot_dir: str = "temp/debug_screenshots"

class ShopeeVerificationConfig:
    """Shopee验证码处理配置类"""
    
    def __init__(self):
        self.config = VerificationConfig()
        
        # QQ邮箱密码登录选择器（修复：使用用户提供的精确选择器）
        self.qq_password_login_selectors = [
            # 用户提供的精确选择器（优先级最高）
            'a#switcher_plogin',  # ID选择器，最精确
            'a.link#switcher_plogin',  # 类+ID选择器
            'a[id="switcher_plogin"]',  # 属性选择器
            'a:has-text("密码登录")#switcher_plogin',  # 组合选择器
            
            # 通用备用选择器
            'a:has-text("密码登录")',
            'span:has-text("密码登录")', 
            'div:has-text("密码登录")',
            'button:has-text("密码登录")',
            
            # QQ邮箱特有选择器
            '.u-tab:nth-child(2)',  # 第二个tab通常是密码登录
            '.login-type-switch:has-text("密码")',
            '.account-login:has-text("密码")', 
            
            # 新版QQ邮箱选择器（2024年更新）
            '.login-mode-switcher:has-text("密码")',
            '.auth-method-tab[data-method="password"]',
            '.login-way-switch:has-text("密码")',
            'button[data-login-type="password"]'
        ]
        
        # Shopee发送至邮箱按钮选择器
        self.email_button_selectors = [
            # 基础文本选择器
            'button:has-text("发送至邮箱")',
            'span:has-text("发送至邮箱")',
            'div:has-text("发送至邮箱")',
            'a:has-text("发送至邮箱")',
            
            # CSS类选择器
            '.email-send-btn',
            '.send-email-btn',
            '.verification-email-btn',
            '.email-verification-send',
            
            # 属性选择器
            'button[data-action="send-email"]',
            'button[data-type="email"]',
            'input[value*="邮箱"]',
            'button[title*="邮箱"]',
            
            # 通用按钮选择器（包含邮箱关键词）
            'button:contains("邮箱")',
            'span:contains("邮箱")',
            'div:contains("邮箱")'
        ]
        
        # Shopee验证码弹窗选择器
        self.verification_popup_selectors = [
            '.phone-verify-container',
            '.verification-modal',
            '.verify-modal',
            '.otp-modal',
            '.security-verification',
            '.two-factor-modal',
            '.email-verification-modal',
            '[class*="verify"]',
            '[class*="verification"]',
            '[class*="otp"]'
        ]

        # 手机验证码相关：切换/发送到电话按钮选择器（优先）
        self.phone_button_selectors = [
            'button:has-text("发送至电话")',
            'button:has-text("发送至手机")',
            'button:has-text("手机验证")',
            'button:has-text("通过短信接收")',
            'span:has-text("发送至电话")',
            'a:has-text("发送至电话")',
            '.phone-verify-container button:has-text("电话")',
            '*[role="button"]:has-text("发送至电话")',
        ]

        # 验证码输入框选择器
        self.verification_input_selectors = [
            'input[type="text"][maxlength="6"]',
            'input[placeholder*="验证码"]',
            'input[placeholder*="verification"]',
            'input[name*="otp"]',
            'input[name*="verification"]',
            'input[class*="verification"]',
            'input[class*="otp"]',
            '.verification-input input',
            '.otp-input input'
        ]

        # 确认按钮选择器
        self.confirm_button_selectors = [
            'button:has-text("确认")',
            'button:has-text("确定")',
            'button:has-text("提交")',
            'button:has-text("验证")',
            'button:has-text("Confirm")',
            'button:has-text("Submit")',
            '.confirm-btn',
            '.submit-btn',
            '.verification-submit'
        ]

        # 邮箱类型配置
        self.email_configs = {
            'qq.com': {
                'login_url': 'https://mail.qq.com',
                'needs_password_switch': True,
                'password_switch_selectors': self.qq_password_login_selectors,
                'username_selectors': [
                    'input[name="u"]',
                    'input[id="u"]',
                    'input[placeholder*="邮箱"]',
                    'input[placeholder*="账号"]',
                    'input[type="text"]'
                ],
                'password_selectors': [
                    'input[name="p"]',
                    'input[id="p"]',
                    'input[type="password"]',
                    'input[placeholder*="密码"]'
                ]
            },
            '163.com': {
                'login_url': 'https://mail.163.com',
                'needs_password_switch': False,
                'username_selectors': [
                    'input[name="email"]',
                    'input[name="username"]',
                    'input[type="text"]'
                ],
                'password_selectors': [
                    'input[name="password"]',
                    'input[type="password"]'
                ]
            },
            'gmail.com': {
                'login_url': 'https://mail.google.com',
                'needs_password_switch': False,
                'username_selectors': [
                    'input[type="email"]',
                    'input[name="identifier"]'
                ],
                'password_selectors': [
                    'input[type="password"]',
                    'input[name="password"]'
                ]
            }
        }
    
    def log_config_info(self, logger):
        """记录配置信息"""
        logger.info("[DATA] 验证码处理配置信息:")
        logger.info(f"  [TIME] 按钮点击等待时间: {self.config.button_click_wait}秒")
        logger.info(f"  [FILE] 页面加载等待时间: {self.config.page_load_wait}秒")
        logger.info(f"  [RETRY] 最大重试次数: {self.config.max_retries}")
        logger.info(f"  [EMAIL] 邮件检查间隔: {self.config.email_check_interval}秒")
        logger.info(f"  [SEARCH] QQ密码登录选择器: {len(self.qq_password_login_selectors)}个")
        logger.info(f"  [EMAIL] 邮箱按钮选择器: {len(self.email_button_selectors)}个")

# 全局配置实例
_global_config = None

def get_verification_config() -> ShopeeVerificationConfig:
    """获取全局验证码处理配置"""
    global _global_config
    if _global_config is None:
        _global_config = ShopeeVerificationConfig()
    return _global_config

def get_email_button_wait_time() -> float:
    """获取邮箱按钮点击等待时间"""
    return get_verification_config().config.button_click_wait

def get_email_login_config(email_domain: str) -> Dict[str, Any]:
    """根据邮箱域名获取登录配置"""
    config = get_verification_config()
    return config.email_configs.get(email_domain, config.email_configs['qq.com'])

def get_debug_screenshot_path(operation_name: str) -> str:
    """获取调试截图路径"""
    config = get_verification_config()
    screenshot_dir = Path(config.config.debug_screenshot_dir)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    return str(screenshot_dir / f"{operation_name}_{timestamp}.png") 