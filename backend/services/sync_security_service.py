#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据同步安全服务（Sync Security Service）

v4.12.0新增：
- 数据同步相关的安全功能
- 字段级权限检查
- 数据脱敏
- 数据加密（可选）

职责：
- 检查字段级权限
- 实现数据脱敏逻辑
- 集成现有权限系统（auth_service）
"""

from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
import re

from modules.core.logger import get_logger

logger = get_logger(__name__)


class SyncSecurityService:
    """
    数据同步安全服务
    
    职责：
    - 检查字段级权限
    - 实现数据脱敏逻辑
    - 集成现有权限系统
    """
    
    # 敏感字段列表（配置文件）
    SENSITIVE_FIELDS = {
        "orders": [
            "buyer_name", "buyer_phone", "buyer_email", "buyer_address",
            "receiver_name", "receiver_phone", "receiver_address",
            "payment_account", "payment_method",
        ],
        "products": [
            "supplier_name", "supplier_contact", "cost_price",
            "purchase_price", "wholesale_price",
        ],
        "inventory": [
            "warehouse_location", "warehouse_manager",
        ],
        "finance": [
            "bank_account", "account_number", "tax_id",
        ],
    }
    
    # 脱敏规则（字段名 -> 脱敏函数）
    MASKING_RULES = {
        "phone": lambda x: f"{x[:3]}****{x[-4:]}" if len(x) > 7 else "****",
        "email": lambda x: f"{x.split('@')[0][:2]}***@{x.split('@')[1]}" if '@' in x else "***",
        "name": lambda x: f"{x[0]}**" if len(x) > 1 else "**",
        "address": lambda x: f"{x[:6]}***" if len(x) > 6 else "***",
        "account": lambda x: f"****{x[-4:]}" if len(x) > 4 else "****",
        "id": lambda x: f"{x[:4]}****{x[-4:]}" if len(x) > 8 else "****",
    }
    
    def __init__(self, db: Session):
        self.db = db
    
    def check_field_permission(
        self,
        user_id: Optional[int],
        resource_type: str,
        field_name: str
    ) -> bool:
        """
        检查字段级权限
        
        Args:
            user_id: 用户ID（可选）
            resource_type: 资源类型（orders/products/inventory等）
            field_name: 字段名
            
        Returns:
            是否有权限访问该字段
        """
        try:
            # 如果用户ID为空，默认允许（系统操作）
            if not user_id:
                return True
            
            # 检查是否为敏感字段
            sensitive_fields = self.SENSITIVE_FIELDS.get(resource_type, [])
            if field_name not in sensitive_fields:
                # 非敏感字段，默认允许
                return True
            
            # 敏感字段需要检查权限
            # 集成现有权限系统（auth_service）
            try:
                from backend.services.auth_service import auth_service
                from modules.core.db import DimUser, DimRole
                
                # 获取用户信息
                user = self.db.query(DimUser).filter(DimUser.user_id == user_id).first()
                if not user:
                    return False
                
                # 检查是否为超级用户
                if user.is_superuser:
                    return True
                
                # 检查用户角色权限
                # 这里简化处理，实际应该检查角色的permissions字段
                # 假设有finance.read权限的用户可以访问财务敏感字段
                if resource_type == "finance":
                    # 检查是否有finance相关权限
                    for role in user.roles:
                        if role.is_active:
                            permissions = role.permissions
                            if isinstance(permissions, str):
                                import json
                                try:
                                    permissions = json.loads(permissions)
                                except:
                                    permissions = []
                            
                            if isinstance(permissions, list):
                                if any("finance" in perm.lower() for perm in permissions):
                                    return True
                
                # 默认不允许访问敏感字段
                return False
                
            except Exception as e:
                logger.warning(f"[SyncSecurity] 权限检查失败: {e}")
                # 权限检查失败时，默认拒绝访问敏感字段
                return False
                
        except Exception as e:
            logger.error(f"[SyncSecurity] 字段权限检查异常: {e}", exc_info=True)
            return False
    
    def mask_sensitive_data(
        self,
        data: Dict[str, Any],
        resource_type: str,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        数据脱敏
        
        Args:
            data: 原始数据字典
            resource_type: 资源类型
            user_id: 用户ID（可选，用于权限检查）
            
        Returns:
            脱敏后的数据字典
        """
        try:
            masked_data = data.copy()
            sensitive_fields = self.SENSITIVE_FIELDS.get(resource_type, [])
            
            for field_name, field_value in masked_data.items():
                # 检查是否为敏感字段
                if field_name not in sensitive_fields:
                    continue
                
                # 检查权限
                if self.check_field_permission(user_id, resource_type, field_name):
                    # 有权限，不脱敏
                    continue
                
                # 无权限，进行脱敏
                if field_value is None or field_value == "":
                    continue
                
                field_value_str = str(field_value)
                
                # 根据字段类型选择脱敏规则
                if "phone" in field_name.lower():
                    masked_data[field_name] = self.MASKING_RULES["phone"](field_value_str)
                elif "email" in field_name.lower():
                    masked_data[field_name] = self.MASKING_RULES["email"](field_value_str)
                elif "name" in field_name.lower():
                    masked_data[field_name] = self.MASKING_RULES["name"](field_value_str)
                elif "address" in field_name.lower():
                    masked_data[field_name] = self.MASKING_RULES["address"](field_value_str)
                elif "account" in field_name.lower():
                    masked_data[field_name] = self.MASKING_RULES["account"](field_value_str)
                elif "id" in field_name.lower() and len(field_value_str) > 8:
                    masked_data[field_name] = self.MASKING_RULES["id"](field_value_str)
                else:
                    # 默认脱敏：保留前2个字符，其余用*替换
                    if len(field_value_str) > 2:
                        masked_data[field_name] = f"{field_value_str[:2]}{'*' * (len(field_value_str) - 2)}"
                    else:
                        masked_data[field_name] = "**"
            
            return masked_data
            
        except Exception as e:
            logger.error(f"[SyncSecurity] 数据脱敏异常: {e}", exc_info=True)
            return data
    
    def mask_list_data(
        self,
        data_list: List[Dict[str, Any]],
        resource_type: str,
        user_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        批量数据脱敏
        
        Args:
            data_list: 数据列表
            resource_type: 资源类型
            user_id: 用户ID（可选）
            
        Returns:
            脱敏后的数据列表
        """
        try:
            return [
                self.mask_sensitive_data(item, resource_type, user_id)
                for item in data_list
            ]
        except Exception as e:
            logger.error(f"[SyncSecurity] 批量数据脱敏异常: {e}", exc_info=True)
            return data_list
    
    def encrypt_sensitive_data(
        self,
        data: str,
        field_name: str
    ) -> str:
        """
        加密敏感数据（可选功能）
        
        Args:
            data: 原始数据
            field_name: 字段名
            
        Returns:
            加密后的数据（Base64编码）
        """
        try:
            # 这里简化实现，实际应该使用AES等加密算法
            # 当前仅做Base64编码示例
            import base64
            
            encoded = base64.b64encode(data.encode('utf-8')).decode('utf-8')
            return f"encrypted:{encoded}"
            
        except Exception as e:
            logger.error(f"[SyncSecurity] 数据加密异常: {e}", exc_info=True)
            return data
    
    def decrypt_sensitive_data(
        self,
        encrypted_data: str
    ) -> str:
        """
        解密敏感数据（可选功能）
        
        Args:
            encrypted_data: 加密后的数据
            
        Returns:
            解密后的原始数据
        """
        try:
            if not encrypted_data.startswith("encrypted:"):
                return encrypted_data
            
            import base64
            
            encoded = encrypted_data.replace("encrypted:", "")
            decoded = base64.b64decode(encoded).decode('utf-8')
            return decoded
            
        except Exception as e:
            logger.error(f"[SyncSecurity] 数据解密异常: {e}", exc_info=True)
            return encrypted_data

