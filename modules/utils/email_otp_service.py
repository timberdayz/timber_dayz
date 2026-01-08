#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
邮箱验证码服务
自动从邮箱获取验证码，支持多种邮箱服务商
"""

import imaplib
import email
import email.message
import re
import time
from typing import Optional, Dict, Any, List
from email.header import decode_header
import logging

logger = logging.getLogger(__name__)

class EmailOTPService:
    """邮箱验证码服务"""
    
    def __init__(self, email_config: Dict[str, Any]):
        """
        初始化邮箱验证码服务
        
        Args:
            email_config: 邮箱配置
        """
        self.email_config = email_config
        self.email = email_config.get('email', '')
        self.password = email_config.get('password', '')
        self.imap_server = email_config.get('imap_server', '')
        self.imap_port = email_config.get('imap_port', 993)
        self.smtp_server = email_config.get('smtp_server', '')
        self.smtp_port = email_config.get('smtp_port', 587)
        
        # 验证码关键词
        self.otp_keywords = [
            '验证码', 'verification code', 'otp', 'one-time password',
            'security code', 'authentication code', 'login code',
            'shopee', 'amazon', 'lazada', '妙手', 'erp'
        ]
        
        # 验证码正则表达式
        self.otp_patterns = [
            r'\b\d{4,6}\b',  # 4-6位数字
            r'[A-Z0-9]{4,8}',  # 4-8位大写字母和数字组合
            r'\b\d{3}-\d{3}\b',  # 3-3格式
            r'\b\d{4}-\d{4}\b',  # 4-4格式
        ]
    
    def connect_imap(self) -> Optional[imaplib.IMAP4_SSL]:
        """连接IMAP服务器"""
        try:
            logger.info(f"[LINK] 连接IMAP服务器: {self.imap_server}:{self.imap_port}")
            imap = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            imap.login(self.email, self.password)
            logger.info("[OK] IMAP连接成功")
            return imap
        except Exception as e:
            logger.error(f"[FAIL] IMAP连接失败: {e}")
            return None
    
    def search_otp_emails(self, imap: imaplib.IMAP4_SSL, minutes_back: int = 10) -> List[str]:
        """
        搜索包含验证码的邮件
        
        Args:
            imap: IMAP连接
            minutes_back: 搜索多少分钟内的邮件
            
        Returns:
            邮件ID列表
        """
        try:
            # 选择收件箱
            imap.select('INBOX')
            
            # 构建搜索条件
            search_criteria = f'(SINCE "{self._get_date_string(minutes_back)}")'
            logger.info(f"[SEARCH] 搜索邮件: {search_criteria}")
            
            # 搜索邮件
            status, messages = imap.search(None, search_criteria)
            if status != 'OK':
                logger.error(f"[FAIL] 邮件搜索失败: {status}")
                return []
            
            email_ids = messages[0].split()
            logger.info(f"[EMAIL] 找到 {len(email_ids)} 封邮件")
            
            # 过滤包含验证码关键词的邮件
            otp_email_ids = []
            for email_id in email_ids:
                try:
                    # 获取邮件头信息
                    status, msg_data = imap.fetch(email_id, '(BODY[HEADER])')
                    if status != 'OK':
                        continue
                    
                    # 解析邮件头
                    email_message = email.message_from_bytes(msg_data[0][1])
                    subject = self._decode_header(email_message['subject'] or '')
                    
                    # 检查是否包含验证码关键词
                    if self._contains_otp_keywords(subject):
                        otp_email_ids.append(email_id.decode())
                        logger.info(f"[OK] 找到验证码邮件: {subject}")
                
                except Exception as e:
                    logger.debug(f"处理邮件 {email_id} 失败: {e}")
                    continue
            
            logger.info(f"[EMAIL] 找到 {len(otp_email_ids)} 封验证码邮件")
            return otp_email_ids
            
        except Exception as e:
            logger.error(f"[FAIL] 搜索验证码邮件失败: {e}")
            return []
    
    def extract_otp_from_email(self, imap: imaplib.IMAP4_SSL, email_id: str) -> Optional[str]:
        """
        从邮件中提取验证码
        
        Args:
            imap: IMAP连接
            email_id: 邮件ID
            
        Returns:
            验证码
        """
        try:
            # 获取邮件内容
            status, msg_data = imap.fetch(email_id, '(RFC822)')
            if status != 'OK':
                logger.error(f"[FAIL] 获取邮件内容失败: {status}")
                return None
            
            # 解析邮件
            email_message = email.message_from_bytes(msg_data[0][1])
            
            # 获取邮件正文
            body = self._get_email_body(email_message)
            if not body:
                logger.warning("[WARN] 邮件正文为空")
                return None
            
            # 提取验证码
            otp = self._extract_otp_from_text(body)
            if otp:
                logger.info(f"[OK] 从邮件中提取到验证码: {otp}")
                return otp
            
            logger.warning("[WARN] 未从邮件中提取到验证码")
            return None
            
        except Exception as e:
            logger.error(f"[FAIL] 提取验证码失败: {e}")
            return None
    
    def get_latest_otp(self, minutes_back: int = 10, max_attempts: int = 3) -> Optional[str]:
        """
        获取最新的验证码
        
        Args:
            minutes_back: 搜索多少分钟内的邮件
            max_attempts: 最大尝试次数
            
        Returns:
            验证码
        """
        for attempt in range(max_attempts):
            try:
                logger.info(f"[RETRY] 第 {attempt + 1} 次尝试获取验证码...")
                
                # 连接IMAP
                imap = self.connect_imap()
                if not imap:
                    continue
                
                try:
                    # 搜索验证码邮件
                    otp_email_ids = self.search_otp_emails(imap, minutes_back)
                    if not otp_email_ids:
                        logger.warning("[WARN] 未找到验证码邮件")
                        time.sleep(5)
                        continue
                    
                    # 获取最新的验证码邮件
                    latest_email_id = otp_email_ids[-1]
                    otp = self.extract_otp_from_email(imap, latest_email_id)
                    
                    if otp:
                        return otp
                    
                finally:
                    # 关闭IMAP连接
                    try:
                        imap.close()
                        imap.logout()
                    except:
                        pass
            
                # 等待一段时间后重试
                if attempt < max_attempts - 1:
                    logger.info(f"[WAIT] 等待 10 秒后重试...")
                    time.sleep(10)
            
        except Exception as e:
                logger.error(f"[FAIL] 第 {attempt + 1} 次尝试失败: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(5)
        
        logger.error("[FAIL] 所有尝试都失败了")
            return None
    
    def _get_date_string(self, minutes_back: int) -> str:
        """获取日期字符串"""
        import datetime
        now = datetime.datetime.now()
        past_time = now - datetime.timedelta(minutes=minutes_back)
        return past_time.strftime("%d-%b-%Y")
    
    def _decode_header(self, header: str) -> str:
        """解码邮件头"""
        try:
            decoded_parts = decode_header(header)
            decoded_string = ""
            for part, encoding in decoded_parts:
                if isinstance(part, bytes):
                    if encoding:
                        decoded_string += part.decode(encoding)
                    else:
                        decoded_string += part.decode('utf-8', errors='ignore')
                else:
                    decoded_string += part
            return decoded_string
        except Exception as e:
            logger.debug(f"解码邮件头失败: {e}")
            return header
    
    def _contains_otp_keywords(self, text: str) -> bool:
        """检查文本是否包含验证码关键词"""
        text_lower = text.lower()
        for keyword in self.otp_keywords:
            if keyword.lower() in text_lower:
                return True
            return False
        
    def _get_email_body(self, email_message: email.message.Message) -> str:
        """获取邮件正文"""
        body = ""
        
        if email_message.is_multipart():
            for part in email_message.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition"))
                
                if content_type == "text/plain" and "attachment" not in content_disposition:
                try:
                        body += part.get_payload(decode=True).decode()
                    except:
                        pass
        else:
            try:
                body = email_message.get_payload(decode=True).decode()
            except:
                pass
        
        return body
    
    def _extract_otp_from_text(self, text: str) -> Optional[str]:
        """从文本中提取验证码"""
        for pattern in self.otp_patterns:
            matches = re.findall(pattern, text)
            if matches:
                # 返回最后一个匹配的验证码（通常是最新的）
                return matches[-1]
        return None


def create_email_otp_service(account_config: Dict[str, Any]) -> Optional[EmailOTPService]:
    """
    创建邮箱验证码服务
    
    Args:
        account_config: 账号配置
        
    Returns:
        邮箱验证码服务实例
    """
    try:
        # 从账号配置中提取邮箱信息
        email_config = {
            'email': account_config.get('email', ''),
            'password': account_config.get('email_password', ''),
            'imap_server': account_config.get('imap_server', ''),
            'imap_port': account_config.get('imap_port', 993),
            'smtp_server': account_config.get('smtp_server', ''),
            'smtp_port': account_config.get('smtp_port', 587)
        }
        
        # 检查必要的配置
        if not email_config['email'] or not email_config['password']:
            logger.warning("[WARN] 邮箱配置不完整")
            return None
        
        # 根据邮箱域名设置默认服务器
        if not email_config['imap_server']:
            email_domain = email_config['email'].split('@')[-1].lower()
            if '163.com' in email_domain:
                email_config['imap_server'] = 'imap.163.com'
            elif 'qq.com' in email_domain:
                email_config['imap_server'] = 'imap.qq.com'
            elif 'gmail.com' in email_domain:
                email_config['imap_server'] = 'imap.gmail.com'
            elif 'outlook.com' in email_domain or 'hotmail.com' in email_domain:
                email_config['imap_server'] = 'outlook.office365.com'
            else:
                logger.warning(f"[WARN] 未知邮箱域名: {email_domain}")
                return None
        
    return EmailOTPService(email_config)
        
    except Exception as e:
        logger.error(f"[FAIL] 创建邮箱验证码服务失败: {e}")
        return None


# 常用邮箱配置
EMAIL_CONFIGS = {
    '163.com': {
        'imap_server': 'imap.163.com',
        'imap_port': 993,
        'smtp_server': 'smtp.163.com',
        'smtp_port': 587
    },
    'qq.com': {
        'imap_server': 'imap.qq.com',
        'imap_port': 993,
        'smtp_server': 'smtp.qq.com',
        'smtp_port': 587
    },
    'gmail.com': {
        'imap_server': 'imap.gmail.com',
        'imap_port': 993,
        'smtp_server': 'smtp.gmail.com',
        'smtp_port': 587
    },
    'outlook.com': {
        'imap_server': 'outlook.office365.com',
        'imap_port': 993,
        'smtp_server': 'smtp.office365.com',
        'smtp_port': 587
    }
}


if __name__ == "__main__":
    # 测试代码
    print("[TEST] 邮箱验证码服务测试")
    print("=" * 50)
    
    # 测试配置
    test_config = {
        'email': 'test@163.com',
        'password': 'test_password',
        'imap_server': 'imap.163.com',
        'imap_port': 993
    }
    
    # 创建服务
    service = EmailOTPService(test_config)
    print(f"[OK] 服务创建成功: {service.email}")
        
    # 测试验证码提取
    test_text = "您的验证码是 123456，请在5分钟内完成验证。"
    otp = service._extract_otp_from_text(test_text)
    print(f"[OK] 验证码提取测试: {otp}")
    
    print("\n[DONE] 测试完成") 