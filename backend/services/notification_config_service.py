"""
通知配置服务
提供SMTP配置、通知模板、告警规则管理功能

v4.20.0: 系统管理模块API实现
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, delete
from modules.core.db import SMTPConfig, NotificationTemplate, AlertRule
from modules.core.logger import get_logger
from backend.services.encryption_service import get_encryption_service

logger = get_logger(__name__)


class NotificationConfigService:
    """通知配置服务类"""
    
    def __init__(self, db: AsyncSession):
        """初始化服务（仅支持异步）"""
        self.db = db
        self.encryption_service = get_encryption_service()
    
    # ==================== SMTP配置 ====================
    
    async def get_smtp_config(self) -> Optional[SMTPConfig]:
        """获取SMTP配置（仅返回激活的配置）"""
        try:
            result = await self.db.execute(
                select(SMTPConfig).where(SMTPConfig.is_active == True).order_by(SMTPConfig.updated_at.desc())
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"获取SMTP配置失败: {e}", exc_info=True)
            return None
    
    async def update_smtp_config(
        self,
        config_update: Dict[str, Any],
        updated_by_user_id: Optional[int] = None
    ) -> SMTPConfig:
        """更新或创建SMTP配置"""
        try:
            # 获取现有配置
            existing_config = await self.get_smtp_config()
            
            # 如果密码需要更新，加密密码
            if "password" in config_update and config_update["password"]:
                plain_password = config_update.pop("password")
                config_update["password_encrypted"] = self.encryption_service.encrypt_password(plain_password)
            
            if existing_config:
                # 更新现有配置
                for key, value in config_update.items():
                    if value is not None:
                        setattr(existing_config, key, value)
                existing_config.updated_by = updated_by_user_id
                existing_config.updated_at = datetime.utcnow()
                await self.db.commit()
                await self.db.refresh(existing_config)
                return existing_config
            else:
                # 创建新配置
                if "password_encrypted" not in config_update:
                    raise ValueError("创建SMTP配置时必须提供密码")
                
                new_config = SMTPConfig(
                    **config_update,
                    updated_by=updated_by_user_id
                )
                self.db.add(new_config)
                await self.db.commit()
                await self.db.refresh(new_config)
                return new_config
        except Exception as e:
            await self.db.rollback()
            logger.error(f"更新SMTP配置失败: {e}", exc_info=True)
            raise
    
    async def test_smtp_connection(self, smtp_config: Optional[SMTPConfig] = None) -> Tuple[bool, Optional[str]]:
        """
        测试SMTP连接
        
        Returns:
            (is_success, error_message)
        """
        if not smtp_config:
            smtp_config = await self.get_smtp_config()
        
        if not smtp_config:
            return False, "SMTP配置不存在"
        
        try:
            # 解密密码
            password = self.encryption_service.decrypt_password(smtp_config.password_encrypted)
            
            # 测试连接
            if smtp_config.use_tls:
                server = smtplib.SMTP(smtp_config.smtp_server, smtp_config.smtp_port, timeout=10)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(smtp_config.smtp_server, smtp_config.smtp_port, timeout=10)
            
            server.login(smtp_config.username, password)
            server.quit()
            
            return True, None
        except Exception as e:
            logger.error(f"SMTP连接测试失败: {e}", exc_info=True)
            return False, str(e)
    
    async def send_test_email(
        self,
        to_email: str,
        subject: str = "测试邮件",
        content: str = "这是一封测试邮件",
        smtp_config: Optional[SMTPConfig] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        发送测试邮件
        
        Returns:
            (is_success, error_message)
        """
        if not smtp_config:
            smtp_config = await self.get_smtp_config()
        
        if not smtp_config:
            return False, "SMTP配置不存在"
        
        try:
            # 解密密码
            password = self.encryption_service.decrypt_password(smtp_config.password_encrypted)
            
            # 创建邮件
            msg = MIMEMultipart()
            msg['From'] = f"{smtp_config.from_name or 'System'} <{smtp_config.from_email}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(content, 'plain', 'utf-8'))
            
            # 发送邮件
            if smtp_config.use_tls:
                server = smtplib.SMTP(smtp_config.smtp_server, smtp_config.smtp_port, timeout=10)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(smtp_config.smtp_server, smtp_config.smtp_port, timeout=10)
            
            server.login(smtp_config.username, password)
            server.send_message(msg)
            server.quit()
            
            return True, None
        except Exception as e:
            logger.error(f"发送测试邮件失败: {e}", exc_info=True)
            return False, str(e)
    
    # ==================== 通知模板 ====================
    
    async def list_templates(
        self,
        template_type: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[NotificationTemplate], int]:
        """获取通知模板列表（分页、筛选）"""
        try:
            conditions = []
            
            if template_type:
                conditions.append(NotificationTemplate.template_type == template_type)
            
            if is_active is not None:
                conditions.append(NotificationTemplate.is_active == is_active)
            
            # 查询总数
            count_query = select(func.count(NotificationTemplate.id))
            if conditions:
                count_query = count_query.where(and_(*conditions))
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar() or 0
            
            # 查询数据
            query = select(NotificationTemplate).order_by(NotificationTemplate.created_at.desc())
            if conditions:
                query = query.where(and_(*conditions))
            
            # 分页
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            
            result = await self.db.execute(query)
            templates = result.scalars().all()
            
            return templates, total
        except Exception as e:
            logger.error(f"获取通知模板列表失败: {e}", exc_info=True)
            raise
    
    async def get_template(self, template_id: int) -> Optional[NotificationTemplate]:
        """获取通知模板详情"""
        try:
            result = await self.db.execute(
                select(NotificationTemplate).where(NotificationTemplate.id == template_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"获取通知模板详情失败: {e}", exc_info=True)
            return None
    
    async def create_template(
        self,
        template_data: Dict[str, Any],
        created_by_user_id: Optional[int] = None
    ) -> NotificationTemplate:
        """创建通知模板"""
        try:
            # 检查模板名称是否已存在
            existing = await self.db.execute(
                select(NotificationTemplate).where(
                    NotificationTemplate.template_name == template_data["template_name"]
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"模板名称 '{template_data['template_name']}' 已存在")
            
            new_template = NotificationTemplate(
                **template_data,
                created_by=created_by_user_id,
                updated_by=created_by_user_id
            )
            self.db.add(new_template)
            await self.db.commit()
            await self.db.refresh(new_template)
            return new_template
        except Exception as e:
            await self.db.rollback()
            logger.error(f"创建通知模板失败: {e}", exc_info=True)
            raise
    
    async def update_template(
        self,
        template_id: int,
        template_data: Dict[str, Any],
        updated_by_user_id: Optional[int] = None
    ) -> Optional[NotificationTemplate]:
        """更新通知模板"""
        try:
            template = await self.get_template(template_id)
            if not template:
                return None
            
            # 如果更新模板名称，检查是否冲突
            if "template_name" in template_data and template_data["template_name"] != template.template_name:
                existing = await self.db.execute(
                    select(NotificationTemplate).where(
                        NotificationTemplate.template_name == template_data["template_name"],
                        NotificationTemplate.id != template_id
                    )
                )
                if existing.scalar_one_or_none():
                    raise ValueError(f"模板名称 '{template_data['template_name']}' 已存在")
            
            for key, value in template_data.items():
                if value is not None:
                    setattr(template, key, value)
            
            template.updated_by = updated_by_user_id
            template.updated_at = datetime.utcnow()
            
            await self.db.commit()
            await self.db.refresh(template)
            return template
        except Exception as e:
            await self.db.rollback()
            logger.error(f"更新通知模板失败: {e}", exc_info=True)
            raise
    
    async def delete_template(self, template_id: int) -> bool:
        """删除通知模板"""
        try:
            template = await self.get_template(template_id)
            if not template:
                return False
            
            await self.db.delete(template)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"删除通知模板失败: {e}", exc_info=True)
            raise
    
    # ==================== 告警规则 ====================
    
    async def list_alert_rules(
        self,
        rule_type: Optional[str] = None,
        enabled: Optional[bool] = None,
        page: int = 1,
        page_size: int = 20
    ) -> Tuple[List[AlertRule], int]:
        """获取告警规则列表（分页、筛选）"""
        try:
            conditions = []
            
            if rule_type:
                conditions.append(AlertRule.rule_type == rule_type)
            
            if enabled is not None:
                conditions.append(AlertRule.enabled == enabled)
            
            # 查询总数
            count_query = select(func.count(AlertRule.id))
            if conditions:
                count_query = count_query.where(and_(*conditions))
            
            count_result = await self.db.execute(count_query)
            total = count_result.scalar() or 0
            
            # 查询数据
            query = select(AlertRule).order_by(AlertRule.created_at.desc())
            if conditions:
                query = query.where(and_(*conditions))
            
            # 分页
            offset = (page - 1) * page_size
            query = query.offset(offset).limit(page_size)
            
            result = await self.db.execute(query)
            rules = result.scalars().all()
            
            return rules, total
        except Exception as e:
            logger.error(f"获取告警规则列表失败: {e}", exc_info=True)
            raise
    
    async def get_alert_rule(self, rule_id: int) -> Optional[AlertRule]:
        """获取告警规则详情"""
        try:
            result = await self.db.execute(
                select(AlertRule).where(AlertRule.id == rule_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(f"获取告警规则详情失败: {e}", exc_info=True)
            return None
    
    async def create_alert_rule(
        self,
        rule_data: Dict[str, Any],
        created_by_user_id: Optional[int] = None
    ) -> AlertRule:
        """创建告警规则"""
        try:
            # 检查规则名称是否已存在
            existing = await self.db.execute(
                select(AlertRule).where(
                    AlertRule.rule_name == rule_data["rule_name"]
                )
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"规则名称 '{rule_data['rule_name']}' 已存在")
            
            new_rule = AlertRule(
                **rule_data,
                created_by=created_by_user_id,
                updated_by=created_by_user_id
            )
            self.db.add(new_rule)
            await self.db.commit()
            await self.db.refresh(new_rule)
            return new_rule
        except Exception as e:
            await self.db.rollback()
            logger.error(f"创建告警规则失败: {e}", exc_info=True)
            raise
    
    async def update_alert_rule(
        self,
        rule_id: int,
        rule_data: Dict[str, Any],
        updated_by_user_id: Optional[int] = None
    ) -> Optional[AlertRule]:
        """更新告警规则"""
        try:
            rule = await self.get_alert_rule(rule_id)
            if not rule:
                return None
            
            # 如果更新规则名称，检查是否冲突
            if "rule_name" in rule_data and rule_data["rule_name"] != rule.rule_name:
                existing = await self.db.execute(
                    select(AlertRule).where(
                        AlertRule.rule_name == rule_data["rule_name"],
                        AlertRule.id != rule_id
                    )
                )
                if existing.scalar_one_or_none():
                    raise ValueError(f"规则名称 '{rule_data['rule_name']}' 已存在")
            
            for key, value in rule_data.items():
                if value is not None:
                    setattr(rule, key, value)
            
            rule.updated_by = updated_by_user_id
            rule.updated_at = datetime.utcnow()
            
            await self.db.commit()
            await self.db.refresh(rule)
            return rule
        except Exception as e:
            await self.db.rollback()
            logger.error(f"更新告警规则失败: {e}", exc_info=True)
            raise
    
    async def delete_alert_rule(self, rule_id: int) -> bool:
        """删除告警规则"""
        try:
            rule = await self.get_alert_rule(rule_id)
            if not rule:
                return False
            
            delete_stmt = delete(AlertRule).where(AlertRule.id == rule_id)
            await self.db.execute(delete_stmt)
            await self.db.commit()
            return True
        except Exception as e:
            await self.db.rollback()
            logger.error(f"删除告警规则失败: {e}", exc_info=True)
            raise


def get_notification_config_service(db: AsyncSession) -> NotificationConfigService:
    """获取通知配置服务实例"""
    return NotificationConfigService(db)
