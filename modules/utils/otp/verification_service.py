#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统一验证码服务

提供多种验证码通道的统一接口，支持邮箱OTP、短信OTP等。
"""

import time
from typing import Dict, Optional, Any
from loguru import logger
from .email_otp_client import EmailOTPClient
from .browser_email_client import run_browser_email_otp


class VerificationCodeService:
    """统一验证码服务"""
    
    def __init__(self):
        """初始化验证码服务"""
        self.email_client = None
        self._clients = {}
    
    def request_otp(
        self, 
        channel: str, 
        context: Dict[str, Any],
        timeout_seconds: int = 120
    ) -> Optional[str]:
        """
        请求获取验证码
        
        Args:
            channel: 验证码通道 ('email', 'sms', 'totp')
            context: 上下文信息，包含账号配置等
            timeout_seconds: 超时时间（秒）
            
        Returns:
            验证码字符串，失败返回None
        """
        logger.info(f"开始请求 {channel} 验证码，超时时间: {timeout_seconds}秒")
        
        try:
            if channel == "email":
                return self._request_email_otp(context, timeout_seconds)
            elif channel == "sms":
                # TODO: 实现短信OTP
                logger.warning("短信OTP功能尚未实现")
                return None
            elif channel == "totp":
                # TODO: 实现TOTP
                logger.warning("TOTP功能尚未实现")
                return None
            else:
                logger.error(f"不支持的验证码通道: {channel}")
                return None
                
        except Exception as e:
            logger.error(f"获取 {channel} 验证码失败: {e}")
            return None
    
    def _request_email_otp(
        self, 
        context: Dict[str, Any], 
        timeout_seconds: int
    ) -> Optional[str]:
        """
        请求邮箱验证码
        
        Args:
            context: 包含邮箱配置的上下文
            timeout_seconds: 超时时间
            
        Returns:
            验证码字符串
        """
        # 从上下文中提取邮箱配置
        email_address = context.get("E-mail") or context.get("Email account")
        email_license = context.get("Email License")  # IMAP授权码
        email_password = context.get("Email password")  # 网页登录密码
        
        if not email_address or (not email_license and not email_password):
            logger.error("邮箱配置不完整：缺少邮箱地址或密码/授权码")
            return None
        
        # 优先尝试IMAP模式（如果有授权码）
        if email_license:
            logger.info("尝试IMAP模式获取验证码...")
            otp_code = self._try_imap_otp(context, timeout_seconds, email_license)
            if otp_code:
                return otp_code
            
            logger.warning("IMAP模式失败，回退到浏览器模式...")
        else:
            logger.info("未配置IMAP授权码，使用浏览器模式...")
        
        # 回退到浏览器模式（使用网页登录密码）
        if email_password:
            logger.info("尝试浏览器模式获取验证码...")
            return self._try_browser_otp(context, timeout_seconds, email_password)
        else:
            logger.error("没有可用的邮箱密码进行浏览器登录")
            return None
    
    def _try_imap_otp(
        self, 
        context: Dict[str, Any], 
        timeout_seconds: int,
        email_license: str
    ) -> Optional[str]:
        """尝试IMAP模式获取验证码"""
        try:
            email_config = {
                "email_address": context.get("E-mail") or context.get("Email account"),
                "email_password": email_license,
                "imap_host": "imap.163.com",
                "imap_port": 993,
                "use_ssl": True,
                "platform": context.get("platform", "unknown"),
                "account_id": context.get("account_id", "unknown")
            }
            
            # 创建或复用邮箱客户端
            client_key = f"{email_config['email_address']}_{email_config['platform']}_imap"
            if client_key not in self._clients:
                self._clients[client_key] = EmailOTPClient(email_config)
            
            email_client = self._clients[client_key]
            
            # 记录开始时间
            start_time = time.time()
            
            logger.info(f"开始IMAP监听邮箱 {email_config['email_address']} 的验证码...")
            
            # 轮询获取验证码
            poll_interval = 2
            max_interval = 5
            
            while time.time() - start_time < timeout_seconds:
                try:
                    otp_code = email_client.get_latest_otp(
                        since_timestamp=start_time,
                        max_age_seconds=timeout_seconds
                    )
                    
                    if otp_code:
                        elapsed_time = time.time() - start_time
                        logger.success(f"IMAP模式成功获取验证码: {otp_code}，耗时: {elapsed_time:.2f}秒")
                        return otp_code
                    
                    time.sleep(poll_interval)
                    if poll_interval < max_interval:
                        poll_interval += 1
                        
                except Exception as e:
                    logger.debug(f"IMAP轮询时出错: {e}")
                    # 如果出现"不安全登录"错误，立即放弃IMAP模式
                    if "Unsafe Login" in str(e):
                        logger.warning("检测到163邮箱安全限制，放弃IMAP模式")
                        return None
                    time.sleep(poll_interval)
            
            logger.warning("IMAP模式超时")
            return None
            
        except Exception as e:
            logger.error(f"IMAP模式失败: {e}")
            return None
    
    def _try_browser_otp(
        self,
        context: Dict[str, Any],
        timeout_seconds: int, 
        email_password: str
    ) -> Optional[str]:
        """尝试浏览器模式获取验证码"""
        try:
            email_address = context.get("E-mail") or context.get("Email account")
            email_url = context.get("Email address", "https://mail.163.com")
            
            browser_config = {
                "email_address": email_address,
                "email_password": email_password,
                "email_url": email_url,
                "platform": context.get("platform", "unknown"),
                "account_id": context.get("account_id", "unknown")
            }
            
            logger.info(f"开始浏览器模式登录邮箱: {email_url}")
            
            # 使用浏览器模式获取验证码
            otp_code = run_browser_email_otp(browser_config, timeout_seconds)
            
            if otp_code:
                logger.success(f"浏览器模式成功获取验证码: {otp_code}")
                return otp_code
            else:
                logger.error("浏览器模式未能获取验证码")
                return None
                
        except Exception as e:
            logger.error(f"浏览器模式失败: {e}")
            return None
    
    def cleanup(self):
        """清理资源"""
        logger.debug("清理验证码服务资源...")
        for client in self._clients.values():
            if hasattr(client, 'cleanup'):
                try:
                    client.cleanup()
                except Exception as e:
                    logger.warning(f"清理客户端资源时出错: {e}")
        self._clients.clear()
