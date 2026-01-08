#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通知配置API - v4.20.0
提供SMTP配置、通知模板、告警规则管理功能
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from backend.models.database import get_async_db
from backend.routers.users import require_admin
from backend.schemas.notification_config import (
    SMTPConfigResponse,
    SMTPConfigUpdate,
    TestEmailRequest,
    NotificationTemplateResponse,
    NotificationTemplateCreate,
    NotificationTemplateUpdate,
    NotificationTemplateListResponse,
    AlertRuleResponse,
    AlertRuleCreate,
    AlertRuleUpdate,
    AlertRuleListResponse
)
from backend.services.notification_config_service import get_notification_config_service
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/system/notification", tags=["通知配置"])

# 限流配置（如果可用）
try:
    from backend.middleware.rate_limiter import role_based_rate_limit
except ImportError:
    role_based_rate_limit = None


# ==================== SMTP配置 API ====================

@router.get("/smtp-config", response_model=SMTPConfigResponse)
async def get_smtp_config(
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取SMTP配置
    
    需要管理员权限
    """
    try:
        service = get_notification_config_service(db)
        config = await service.get_smtp_config()
        
        if not config:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="SMTP配置不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail="请先配置SMTP服务器",
                status_code=404
            )
        
        return SMTPConfigResponse(
            id=config.id,
            smtp_server=config.smtp_server,
            smtp_port=config.smtp_port,
            use_tls=config.use_tls,
            username=config.username,
            from_email=config.from_email,
            from_name=config.from_name,
            is_active=config.is_active,
            updated_at=config.updated_at,
            updated_by=config.updated_by
        )
    except Exception as e:
        logger.error(f"获取SMTP配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取SMTP配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.put("/smtp-config", response_model=SMTPConfigResponse)
async def update_smtp_config(
    config_update: SMTPConfigUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    更新SMTP配置
    
    需要管理员权限
    密码将自动加密存储
    """
    # 限流配置
    if role_based_rate_limit:
        @role_based_rate_limit(requests_per_minute=5, requests_per_hour=20)
        async def _update():
            pass
        await _update()
    
    try:
        service = get_notification_config_service(db)
        
        # 转换为字典（排除None值）
        update_data = config_update.model_dump(exclude_unset=True, exclude_none=True)
        
        # 测试连接（如果提供了密码或服务器配置）
        if "password" in update_data or "smtp_server" in update_data or "smtp_port" in update_data:
            # 先创建临时配置对象用于测试
            existing_config = await service.get_smtp_config()
            test_config = existing_config if existing_config else None
            
            # 如果更新了配置，需要先更新再测试
            if test_config:
                for key, value in update_data.items():
                    if key != "password" and value is not None:
                        setattr(test_config, key, value)
            
            # 这里暂时跳过连接测试，因为需要先保存配置才能测试
            # 实际应该在保存后测试，如果失败则回滚
        
        # 更新配置
        updated_config = await service.update_smtp_config(
            update_data,
            updated_by_user_id=current_user.user_id
        )
        
        # 记录审计日志
        from backend.services.audit_service import audit_service
        await audit_service.log_action(
            user_id=current_user.user_id,
            action="update_smtp_config",
            resource="notification_config",
            resource_id=str(updated_config.id),
            details={"config_id": updated_config.id},
            is_success=True
        )
        
        return SMTPConfigResponse(
            id=updated_config.id,
            smtp_server=updated_config.smtp_server,
            smtp_port=updated_config.smtp_port,
            use_tls=updated_config.use_tls,
            username=updated_config.username,
            from_email=updated_config.from_email,
            from_name=updated_config.from_name,
            is_active=updated_config.is_active,
            updated_at=updated_config.updated_at,
            updated_by=updated_config.updated_by
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"更新SMTP配置失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="更新SMTP配置失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/test-email", response_model=dict)
async def send_test_email(
    request: TestEmailRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    发送测试邮件
    
    需要管理员权限
    """
    try:
        service = get_notification_config_service(db)
        
        # 先测试SMTP连接
        is_connected, error_message = await service.test_smtp_connection()
        if not is_connected:
            return error_response(
                code=ErrorCode.CONNECTION_ERROR,
                message="SMTP连接失败",
                error_type=get_error_type(ErrorCode.CONNECTION_ERROR),
                detail=error_message,
                status_code=400
            )
        
        # 发送测试邮件
        is_sent, error_message = await service.send_test_email(
            to_email=request.to_email,
            subject=request.subject,
            content=request.content
        )
        
        if not is_sent:
            return error_response(
                code=ErrorCode.INTERNAL_SERVER_ERROR,
                message="发送测试邮件失败",
                error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
                detail=error_message,
                status_code=500
            )
        
        return success_response(
            data={"to_email": request.to_email},
            message="测试邮件发送成功"
        )
    except Exception as e:
        logger.error(f"发送测试邮件失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="发送测试邮件失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


# ==================== 通知模板 API ====================

@router.get("/templates", response_model=NotificationTemplateListResponse)
async def list_templates(
    template_type: Optional[str] = Query(None, description="模板类型（email/sms/push）"),
    is_active: Optional[bool] = Query(None, description="是否启用"),
    page: int = Query(1, ge=1, description="页码（1-based）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数（最大100）"),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取通知模板列表（支持筛选、分页）
    
    需要管理员权限
    """
    try:
        service = get_notification_config_service(db)
        templates, total = await service.list_templates(
            template_type=template_type,
            is_active=is_active,
            page=page,
            page_size=page_size
        )
        
        total_pages = (total + page_size - 1) // page_size
        
        return NotificationTemplateListResponse(
            data=[
                NotificationTemplateResponse(
                    id=t.id,
                    template_name=t.template_name,
                    template_type=t.template_type,
                    subject=t.subject,
                    content=t.content,
                    variables=t.variables,
                    is_active=t.is_active,
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                    created_by=t.created_by,
                    updated_by=t.updated_by
                )
                for t in templates
            ],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages
        )
    except Exception as e:
        logger.error(f"获取通知模板列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取通知模板列表失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/templates", response_model=NotificationTemplateResponse)
async def create_template(
    template: NotificationTemplateCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    创建通知模板
    
    需要管理员权限
    """
    try:
        service = get_notification_config_service(db)
        new_template = await service.create_template(
            template.model_dump(),
            created_by_user_id=current_user.user_id
        )
        
        return NotificationTemplateResponse(
            id=new_template.id,
            template_name=new_template.template_name,
            template_type=new_template.template_type,
            subject=new_template.subject,
            content=new_template.content,
            variables=new_template.variables,
            is_active=new_template.is_active,
            created_at=new_template.created_at,
            updated_at=new_template.updated_at,
            created_by=new_template.created_by,
            updated_by=new_template.updated_by
        )
    except ValueError as e:
        await db.rollback()
        return error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message="创建通知模板失败",
            error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
            detail=str(e),
            status_code=400
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"创建通知模板失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="创建通知模板失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/templates/{template_id}", response_model=NotificationTemplateResponse)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取通知模板详情
    
    需要管理员权限
    """
    try:
        service = get_notification_config_service(db)
        template = await service.get_template(template_id)
        
        if not template:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="通知模板不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"模板ID {template_id} 不存在",
                status_code=404
            )
        
        return NotificationTemplateResponse(
            id=template.id,
            template_name=template.template_name,
            template_type=template.template_type,
            subject=template.subject,
            content=template.content,
            variables=template.variables,
            is_active=template.is_active,
            created_at=template.created_at,
            updated_at=template.updated_at,
            created_by=template.created_by,
            updated_by=template.updated_by
        )
    except Exception as e:
        logger.error(f"获取通知模板详情失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取通知模板详情失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.put("/templates/{template_id}", response_model=NotificationTemplateResponse)
async def update_template(
    template_id: int,
    template: NotificationTemplateUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    更新通知模板
    
    需要管理员权限
    """
    try:
        service = get_notification_config_service(db)
        updated_template = await service.update_template(
            template_id,
            template.model_dump(exclude_unset=True, exclude_none=True),
            updated_by_user_id=current_user.user_id
        )
        
        if not updated_template:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="通知模板不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"模板ID {template_id} 不存在",
                status_code=404
            )
        
        return NotificationTemplateResponse(
            id=updated_template.id,
            template_name=updated_template.template_name,
            template_type=updated_template.template_type,
            subject=updated_template.subject,
            content=updated_template.content,
            variables=updated_template.variables,
            is_active=updated_template.is_active,
            created_at=updated_template.created_at,
            updated_at=updated_template.updated_at,
            created_by=updated_template.created_by,
            updated_by=updated_template.updated_by
        )
    except ValueError as e:
        await db.rollback()
        return error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message="更新通知模板失败",
            error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
            detail=str(e),
            status_code=400
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"更新通知模板失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="更新通知模板失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.delete("/templates/{template_id}", response_model=dict)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    删除通知模板
    
    需要管理员权限
    """
    try:
        service = get_notification_config_service(db)
        deleted = await service.delete_template(template_id)
        
        if not deleted:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="通知模板不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"模板ID {template_id} 不存在",
                status_code=404
            )
        
        return success_response(
            data={"template_id": template_id},
            message="通知模板删除成功"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"删除通知模板失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="删除通知模板失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


# ==================== 告警规则 API ====================

@router.get("/alert-rules", response_model=AlertRuleListResponse)
async def list_alert_rules(
    rule_type: Optional[str] = Query(None, description="规则类型（system/performance/security/business）"),
    enabled: Optional[bool] = Query(None, description="是否启用"),
    page: int = Query(1, ge=1, description="页码（1-based）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数（最大100）"),
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取告警规则列表（支持筛选、分页）
    
    需要管理员权限
    """
    try:
        service = get_notification_config_service(db)
        rules, total = await service.list_alert_rules(
            rule_type=rule_type,
            enabled=enabled,
            page=page,
            page_size=page_size
        )
        
        total_pages = (total + page_size - 1) // page_size
        
        return AlertRuleListResponse(
            data=[
                AlertRuleResponse(
                    id=r.id,
                    rule_name=r.rule_name,
                    rule_type=r.rule_type,
                    condition=r.condition,
                    template_id=r.template_id,
                    recipients=r.recipients,
                    enabled=r.enabled,
                    priority=r.priority,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                    created_by=r.created_by,
                    updated_by=r.updated_by
                )
                for r in rules
            ],
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages
        )
    except Exception as e:
        logger.error(f"获取告警规则列表失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取告警规则列表失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.post("/alert-rules", response_model=AlertRuleResponse)
async def create_alert_rule(
    rule: AlertRuleCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    创建告警规则
    
    需要管理员权限
    """
    try:
        service = get_notification_config_service(db)
        new_rule = await service.create_alert_rule(
            rule.model_dump(),
            created_by_user_id=current_user.user_id
        )
        
        return AlertRuleResponse(
            id=new_rule.id,
            rule_name=new_rule.rule_name,
            rule_type=new_rule.rule_type,
            condition=new_rule.condition,
            template_id=new_rule.template_id,
            recipients=new_rule.recipients,
            enabled=new_rule.enabled,
            priority=new_rule.priority,
            created_at=new_rule.created_at,
            updated_at=new_rule.updated_at,
            created_by=new_rule.created_by,
            updated_by=new_rule.updated_by
        )
    except ValueError as e:
        await db.rollback()
        return error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message="创建告警规则失败",
            error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
            detail=str(e),
            status_code=400
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"创建告警规则失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="创建告警规则失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/alert-rules/{rule_id}", response_model=AlertRuleResponse)
async def get_alert_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    获取告警规则详情
    
    需要管理员权限
    """
    try:
        service = get_notification_config_service(db)
        rule = await service.get_alert_rule(rule_id)
        
        if not rule:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="告警规则不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"规则ID {rule_id} 不存在",
                status_code=404
            )
        
        return AlertRuleResponse(
            id=rule.id,
            rule_name=rule.rule_name,
            rule_type=rule.rule_type,
            condition=rule.condition,
            template_id=rule.template_id,
            recipients=rule.recipients,
            enabled=rule.enabled,
            priority=rule.priority,
            created_at=rule.created_at,
            updated_at=rule.updated_at,
            created_by=rule.created_by,
            updated_by=rule.updated_by
        )
    except Exception as e:
        logger.error(f"获取告警规则详情失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="获取告警规则详情失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.put("/alert-rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    rule_id: int,
    rule: AlertRuleUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    更新告警规则
    
    需要管理员权限
    """
    try:
        service = get_notification_config_service(db)
        updated_rule = await service.update_alert_rule(
            rule_id,
            rule.model_dump(exclude_unset=True, exclude_none=True),
            updated_by_user_id=current_user.user_id
        )
        
        if not updated_rule:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="告警规则不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"规则ID {rule_id} 不存在",
                status_code=404
            )
        
        return AlertRuleResponse(
            id=updated_rule.id,
            rule_name=updated_rule.rule_name,
            rule_type=updated_rule.rule_type,
            condition=updated_rule.condition,
            template_id=updated_rule.template_id,
            recipients=updated_rule.recipients,
            enabled=updated_rule.enabled,
            priority=updated_rule.priority,
            created_at=updated_rule.created_at,
            updated_at=updated_rule.updated_at,
            created_by=updated_rule.created_by,
            updated_by=updated_rule.updated_by
        )
    except ValueError as e:
        await db.rollback()
        return error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message="更新告警规则失败",
            error_type=get_error_type(ErrorCode.VALIDATION_ERROR),
            detail=str(e),
            status_code=400
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"更新告警规则失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="更新告警规则失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )


@router.delete("/alert-rules/{rule_id}", response_model=dict)
async def delete_alert_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_async_db),
    current_user = Depends(require_admin)
):
    """
    删除告警规则
    
    需要管理员权限
    """
    try:
        service = get_notification_config_service(db)
        deleted = await service.delete_alert_rule(rule_id)
        
        if not deleted:
            return error_response(
                code=ErrorCode.DATA_NOT_FOUND,
                message="告警规则不存在",
                error_type=get_error_type(ErrorCode.DATA_NOT_FOUND),
                detail=f"规则ID {rule_id} 不存在",
                status_code=404
            )
        
        return success_response(
            data={"rule_id": rule_id},
            message="告警规则删除成功"
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"删除告警规则失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message="删除告警规则失败",
            error_type=get_error_type(ErrorCode.INTERNAL_SERVER_ERROR),
            detail=str(e),
            status_code=500
        )
