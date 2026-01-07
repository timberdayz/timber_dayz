#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
邮箱OTP客户端

通过IMAP连接邮箱，获取并解析验证码邮件。
支持163邮箱等主流邮箱服务商。
"""

import imaplib
import email
import email.utils
import email.message
from email import message_from_bytes
import re
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from email.header import decode_header
from loguru import logger


class EmailOTPClient:
    """邮箱OTP客户端"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化邮箱客户端
        
        Args:
            config: 邮箱配置
                - email_address: 邮箱地址
                - email_password: 邮箱密码/授权码
                - imap_host: IMAP服务器地址
                - imap_port: IMAP端口
                - use_ssl: 是否使用SSL
                - platform: 平台名称
                - account_id: 账号ID
        """
        self.config = config
        self.email_address = config["email_address"]
        self.email_password = config["email_password"]
        self.imap_host = config.get("imap_host", "imap.163.com")
        self.imap_port = config.get("imap_port", 993)
        self.use_ssl = config.get("use_ssl", True)
        self.platform = config.get("platform", "unknown")
        self.account_id = config.get("account_id", "unknown")
        
        self.imap_client = None
        self._connected = False
        
        logger.info(f"初始化邮箱OTP客户端: {self.email_address} ({self.platform})")
    
    def connect(self) -> bool:
        """
        连接到IMAP服务器
        
        Returns:
            连接是否成功
        """
        try:
            if self._connected and self.imap_client:
                # 尝试执行一个简单命令来测试连接
                try:
                    self.imap_client.noop()
                    return True
                except:
                    logger.debug("现有连接已失效，重新连接...")
                    self._connected = False
            
            # 建立新连接
            if self.use_ssl:
                self.imap_client = imaplib.IMAP4_SSL(self.imap_host, self.imap_port)
            else:
                self.imap_client = imaplib.IMAP4(self.imap_host, self.imap_port)
            
            # 登录
            result = self.imap_client.login(self.email_address, self.email_password)
            if result[0] == 'OK':
                self._connected = True
                logger.success(f"成功连接到邮箱服务器: {self.email_address}")
                return True
            else:
                logger.error(f"邮箱登录失败: {result}")
                return False
                
        except Exception as e:
            logger.error(f"连接邮箱服务器失败: {e}")
            self._connected = False
            return False
    
    def disconnect(self):
        """断开IMAP连接"""
        try:
            if self.imap_client and self._connected:
                self.imap_client.logout()
                logger.debug(f"已断开邮箱连接: {self.email_address}")
        except Exception as e:
            logger.warning(f"断开邮箱连接时出错: {e}")
        finally:
            self.imap_client = None
            self._connected = False
    
    def get_latest_otp(
        self, 
        since_timestamp: Optional[float] = None,
        max_age_seconds: int = 300
    ) -> Optional[str]:
        """
        获取最新的验证码
        
        Args:
            since_timestamp: 开始时间戳
            max_age_seconds: 最大邮件年龄（秒）
            
        Returns:
            验证码字符串，未找到返回None
        """
        if not self.connect():
            logger.error("无法连接到邮箱服务器")
            return None
        
        try:
            # 选择收件箱
            status, messages = self.imap_client.select("INBOX")
            if status != 'OK':
                logger.error(f"无法选择收件箱: {messages}")
                return None
            
            # 构建搜索条件
            search_criteria = ["UNSEEN"]  # 未读邮件
            
            # 如果指定了开始时间，添加时间条件
            if since_timestamp:
                since_date = datetime.fromtimestamp(since_timestamp, tz=timezone.utc)
                date_str = since_date.strftime("%d-%b-%Y")
                search_criteria.append(f'SINCE "{date_str}"')
            
            # 搜索邮件
            search_query = " ".join(search_criteria)
            status, message_ids = self.imap_client.search(None, search_query)
            
            if status != 'OK':
                logger.warning(f"搜索邮件失败: {message_ids}")
                return None
            
            if not message_ids[0]:
                logger.debug("没有找到新邮件")
                return None
            
            # 获取邮件ID列表
            mail_ids = message_ids[0].split()
            
            # 从最新邮件开始检查
            for mail_id in reversed(mail_ids):
                try:
                    otp_code = self._parse_email_for_otp(
                        mail_id, 
                        since_timestamp=since_timestamp,
                        max_age_seconds=max_age_seconds
                    )
                    if otp_code:
                        return otp_code
                except Exception as e:
                    logger.warning(f"解析邮件 {mail_id} 时出错: {e}")
                    continue
            
            logger.debug("没有找到包含验证码的邮件")
            return None
            
        except Exception as e:
            logger.error(f"获取验证码邮件时出错: {e}")
            return None
    
    def _parse_email_for_otp(
        self, 
        mail_id: bytes, 
        since_timestamp: Optional[float] = None,
        max_age_seconds: int = 300
    ) -> Optional[str]:
        """
        解析邮件获取验证码
        
        Args:
            mail_id: 邮件ID
            since_timestamp: 开始时间戳
            max_age_seconds: 最大邮件年龄
            
        Returns:
            验证码字符串
        """
        try:
            # 获取邮件
            status, msg_data = self.imap_client.fetch(mail_id, '(RFC822)')
            if status != 'OK':
                logger.warning(f"获取邮件失败: {mail_id}")
                return None
            
            # 解析邮件
            email_body = msg_data[0][1]
            email_message = message_from_bytes(email_body)
            
            # 获取邮件时间
            email_date = self._parse_email_date(email_message)
            
            # 检查邮件时间是否在有效范围内
            if since_timestamp and email_date:
                if email_date < since_timestamp:
                    logger.debug(f"邮件时间太早，跳过: {email_date}")
                    return None
                
                if time.time() - email_date > max_age_seconds:
                    logger.debug(f"邮件太旧，跳过: {email_date}")
                    return None
            
            # 获取发件人和主题
            sender = self._decode_header(email_message.get('From', ''))
            subject = self._decode_header(email_message.get('Subject', ''))
            
            logger.debug(f"检查邮件 - 发件人: {sender}, 主题: {subject}")
            
            # 检查是否是验证码邮件（基于发件人和主题）
            if not self._is_otp_email(sender, subject):
                logger.debug("不是验证码邮件，跳过")
                return None
            
            # 提取邮件内容
            email_content = self._extract_email_content(email_message)
            
            # 从内容中提取验证码
            otp_code = self._extract_otp_from_content(email_content)
            
            if otp_code:
                logger.info(f"从邮件中提取到验证码: {otp_code} (发件人: {sender})")
                
                # 保存邮件内容到临时文件（脱敏处理）
                self._save_email_content(
                    mail_id.decode(), 
                    sender, 
                    subject, 
                    email_content, 
                    otp_code
                )
                
                return otp_code
            
            return None
            
        except Exception as e:
            logger.error(f"解析邮件时出错: {e}")
            return None
    
    def _parse_email_date(self, email_message: email.message.Message) -> Optional[float]:
        """解析邮件日期"""
        try:
            date_str = email_message.get('Date', '')
            if date_str:
                # 解析邮件日期
                parsed_date = email.utils.parsedate_tz(date_str)
                if parsed_date:
                    timestamp = email.utils.mktime_tz(parsed_date)
                    return timestamp
        except Exception as e:
            logger.debug(f"解析邮件日期失败: {e}")
        return None
    
    def _decode_header(self, header: str) -> str:
        """解码邮件头"""
        try:
            decoded_parts = decode_header(header)
            decoded_header = ""
            
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    if encoding:
                        decoded_header += part.decode(encoding)
                    else:
                        decoded_header += part.decode('utf-8', errors='ignore')
                else:
                    decoded_header += part
            
            return decoded_header
        except Exception as e:
            logger.debug(f"解码邮件头失败: {e}")
            return header
    
    def _is_otp_email(self, sender: str, subject: str) -> bool:
        """
        判断是否是验证码邮件
        
        基于发件人和主题的关键词进行判断
        """
        # 验证码邮件的发件人关键词
        sender_keywords = [
            "shopee", "miaoshou", "91miaoshou", "验证码", "verification",
            "noreply", "no-reply", "system", "security", "auth"
        ]
        
        # 验证码邮件的主题关键词
        subject_keywords = [
            "验证码", "verification", "code", "otp", "登录", "login", 
            "安全", "security", "确认", "confirm", "激活", "activate"
        ]
        
        sender_lower = sender.lower()
        subject_lower = subject.lower()
        
        # 检查发件人关键词
        sender_match = any(keyword in sender_lower for keyword in sender_keywords)
        
        # 检查主题关键词
        subject_match = any(keyword in subject_lower for keyword in subject_keywords)
        
        return sender_match or subject_match
    
    def _extract_email_content(self, email_message: email.message.Message) -> str:
        """提取邮件内容"""
        content = ""
        
        try:
            if email_message.is_multipart():
                for part in email_message.walk():
                    content_type = part.get_content_type()
                    if content_type in ["text/plain", "text/html"]:
                        payload = part.get_payload(decode=True)
                        if payload:
                            # 尝试不同的编码
                            for encoding in ['utf-8', 'gbk', 'gb2312']:
                                try:
                                    content += payload.decode(encoding)
                                    break
                                except:
                                    continue
                            else:
                                content += payload.decode('utf-8', errors='ignore')
            else:
                payload = email_message.get_payload(decode=True)
                if payload:
                    for encoding in ['utf-8', 'gbk', 'gb2312']:
                        try:
                            content = payload.decode(encoding)
                            break
                        except:
                            continue
                    else:
                        content = payload.decode('utf-8', errors='ignore')
        
        except Exception as e:
            logger.warning(f"提取邮件内容失败: {e}")
        
        return content
    
    def _extract_otp_from_content(self, content: str) -> Optional[str]:
        """
        从邮件内容中提取验证码
        
        使用多种正则表达式模式匹配验证码
        """
        if not content:
            return None
        
        # 验证码的正则表达式模式（按优先级排序）
        otp_patterns = [
            # 6位数字验证码（最常见）
            r'(?:验证码|verification code|code)[^\d]*(\d{6})',
            r'(\d{6})(?:\s*(?:是您的|is your)?(?:验证码|verification code))',
            
            # 4位数字验证码
            r'(?:验证码|verification code|code)[^\d]*(\d{4})',
            r'(\d{4})(?:\s*(?:是您的|is your)?(?:验证码|verification code))',
            
            # 通用数字验证码（4-8位）
            r'(?:验证码|verification code|code)[^\d]*(\d{4,8})',
            r'(\d{4,8})(?:\s*(?:是您的|is your)?(?:验证码|verification code))',
            
            # 纯数字匹配（作为后备）
            r'\b(\d{6})\b',  # 6位独立数字
            r'\b(\d{4})\b',  # 4位独立数字
        ]
        
        content_lower = content.lower()
        
        for pattern in otp_patterns:
            matches = re.findall(pattern, content_lower, re.IGNORECASE | re.DOTALL)
            if matches:
                # 返回第一个匹配的验证码
                otp_code = matches[0].strip()
                if otp_code.isdigit() and 4 <= len(otp_code) <= 8:
                    logger.debug(f"使用模式 '{pattern}' 匹配到验证码: {otp_code}")
                    return otp_code
        
        logger.debug("未能从邮件内容中提取到验证码")
        return None
    
    def _save_email_content(
        self, 
        mail_id: str, 
        sender: str, 
        subject: str, 
        content: str, 
        otp_code: str
    ):
        """
        保存邮件内容到临时文件（脱敏处理）
        
        用于调试和问题排查
        """
        try:
            import os
            from pathlib import Path
            
            # 创建临时目录
            temp_dir = Path("temp/outputs/otp_emails")
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"otp_email_{timestamp}_{mail_id}.txt"
            filepath = temp_dir / filename
            
            # 脱敏处理内容
            masked_content = content
            if len(content) > 1000:
                masked_content = content[:500] + "\n... [内容过长，已截断] ...\n" + content[-500:]
            
            # 写入文件
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"邮件ID: {mail_id}\n")
                f.write(f"发件人: {sender}\n")
                f.write(f"主题: {subject}\n")
                f.write(f"提取的验证码: {otp_code}\n")
                f.write(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("-" * 50 + "\n")
                f.write(f"邮件内容:\n{masked_content}\n")
            
            logger.debug(f"已保存邮件内容到: {filepath}")
            
        except Exception as e:
            logger.warning(f"保存邮件内容失败: {e}")
    
    def cleanup(self):
        """清理资源"""
        self.disconnect()
