#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
账号管理API (v4.7.0)

功能：
- 平台账号的CRUD操作
- 从local_accounts.py批量导入
- 导出账号配置（备份）
- 账号统计信息
"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field

from backend.models.database import get_db, get_async_db
from modules.core.db import PlatformAccount
from backend.services.encryption_service import get_encryption_service
from modules.core.logger import get_logger

# v4.18.0: 使用集中的schemas（Contract-First架构）
from backend.schemas.account import (
    CapabilitiesModel,
    AccountCreate,
    AccountUpdate,
    AccountResponse,
    AccountStats,
    AccountImportResponse,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/accounts", tags=["账号管理"])


class BatchCreateRequest(BaseModel):
    """批量创建请求"""
    parent_account: str = Field(..., description="主账号")
    platform: str = Field(..., description="平台代码")
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    shops: List[dict] = Field(..., description="店铺列表")


# ImportResponse已移动到backend/schemas/account.py（重命名为AccountImportResponse）


# ==================== API Endpoints ====================

@router.post("/", response_model=AccountResponse)
async def create_account(
    account: AccountCreate,
    db: AsyncSession = Depends(get_async_db),
    # current_user: str = Depends(get_current_user)  # 暂时注释掉认证
):
    """
    创建账号
    
    - 自动加密密码
    - 检查account_id唯一性
    - 填充审计字段
    """
    # 检查account_id是否已存在
    result = await db.execute(select(PlatformAccount).where(PlatformAccount.account_id == account.account_id))
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail=f"账号ID '{account.account_id}' 已存在")
    
    # 加密密码
    encryption_service = get_encryption_service()
    encrypted_password = encryption_service.encrypt_password(account.password)
    
    # 创建记录
    db_account = PlatformAccount(
        account_id=account.account_id,
        parent_account=account.parent_account,
        platform=account.platform,
        account_alias=account.account_alias,
        store_name=account.store_name,
        shop_type=account.shop_type,
        shop_region=account.shop_region,
        username=account.username,
        password_encrypted=encrypted_password,
        login_url=account.login_url,
        email=account.email,
        phone=account.phone,
        region=account.region,
        currency=account.currency,
        capabilities=account.capabilities.dict(),
        enabled=account.enabled,
        proxy_required=account.proxy_required,
        notes=account.notes,
        created_by="system",  # TODO: 替换为实际用户
        updated_by="system"
    )
    
    db.add(db_account)
    await db.commit()
    await db.refresh(db_account)
    
    logger.info(f"账号创建成功: {account.account_id}")
    
    return db_account


@router.get("/", response_model=List[AccountResponse])
async def list_accounts(
    platform: Optional[str] = Query(None, description="平台筛选"),
    enabled: Optional[bool] = Query(None, description="启用状态筛选"),
    shop_type: Optional[str] = Query(None, description="店铺类型筛选"),
    search: Optional[str] = Query(None, description="搜索（店铺名或账号ID）"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    账号列表
    
    支持筛选：
    - platform: 平台代码
    - enabled: 启用状态
    - shop_type: 店铺类型
    - search: 模糊搜索店铺名或账号ID
    """
    stmt = select(PlatformAccount)
    
    if platform:
        stmt = stmt.where(PlatformAccount.platform.ilike(platform))
    if enabled is not None:
        stmt = stmt.where(PlatformAccount.enabled == enabled)
    if shop_type:
        stmt = stmt.where(PlatformAccount.shop_type == shop_type)
    if search:
        stmt = stmt.where(
            (PlatformAccount.store_name.ilike(f"%{search}%")) |
            (PlatformAccount.account_id.ilike(f"%{search}%"))
        )
    
    stmt = stmt.order_by(PlatformAccount.created_at.desc())
    result = await db.execute(stmt)
    accounts = result.scalars().all()
    
    logger.info(f"查询账号列表: {len(accounts)} 条记录")
    
    return accounts


@router.get("/{account_id}", response_model=AccountResponse)
async def get_account(
    account_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取账号详情
    
    密码字段不返回
    """
    result = await db.execute(select(PlatformAccount).where(PlatformAccount.account_id == account_id))
    account = result.scalar_one_or_none()
    
    if not account:
        raise HTTPException(status_code=404, detail=f"账号 '{account_id}' 不存在")
    
    return account


@router.put("/{account_id}", response_model=AccountResponse)
async def update_account(
    account_id: str,
    account_update: AccountUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """
    更新账号
    
    - 密码更新时重新加密
    - 更新审计字段
    """
    result = await db.execute(select(PlatformAccount).where(PlatformAccount.account_id == account_id))
    db_account = result.scalar_one_or_none()
    
    if not db_account:
        raise HTTPException(status_code=404, detail=f"账号 '{account_id}' 不存在")
    
    # 更新字段
    update_data = account_update.dict(exclude_unset=True)
    
    # 特殊处理密码
    if "password" in update_data and update_data["password"]:
        encryption_service = get_encryption_service()
        encrypted_password = encryption_service.encrypt_password(update_data["password"])
        db_account.password_encrypted = encrypted_password
        update_data.pop("password")
    
    # 特殊处理capabilities
    if "capabilities" in update_data:
        # 如果capabilities是Pydantic模型，转换为字典；如果已经是字典，直接使用
        capabilities_value = update_data["capabilities"]
        if not isinstance(capabilities_value, dict):
            # 不是字典，可能是Pydantic模型，尝试转换为字典
            if hasattr(capabilities_value, "dict"):
                update_data["capabilities"] = capabilities_value.dict()
            else:
                # 其他情况，尝试转换为字典
                update_data["capabilities"] = dict(capabilities_value) if capabilities_value else {}
    
    # 更新其他字段
    for field, value in update_data.items():
        setattr(db_account, field, value)
    
    # 更新审计字段
    db_account.updated_by = "system"  # TODO: 替换为实际用户
    db_account.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(db_account)
    
    logger.info(f"账号更新成功: {account_id}")
    
    return db_account


@router.delete("/{account_id}")
async def delete_account(
    account_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    删除账号
    
    硬删除（不可恢复）
    """
    result = await db.execute(select(PlatformAccount).where(PlatformAccount.account_id == account_id))
    db_account = result.scalar_one_or_none()
    
    if not db_account:
        raise HTTPException(status_code=404, detail=f"账号 '{account_id}' 不存在")
    
    await db.delete(db_account)
    await db.commit()
    
    logger.info(f"账号删除成功: {account_id}")
    
    return {"message": f"账号 '{account_id}' 已删除"}


@router.post("/batch", response_model=List[AccountResponse])
async def batch_create_accounts(
    batch_request: BatchCreateRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    批量创建账号（多店铺）
    
    用于一次性添加多个店铺（共用同一主账号）
    """
    created_accounts = []
    encryption_service = get_encryption_service()
    encrypted_password = encryption_service.encrypt_password(batch_request.password)
    
    for shop in batch_request.shops:
        account_id = f"{batch_request.platform}_{shop.get('shop_region', 'unknown').lower()}_{shop.get('store_name', 'shop')}"
        
        # 检查是否已存在
        result = await db.execute(select(PlatformAccount).where(PlatformAccount.account_id == account_id))
        existing = result.scalar_one_or_none()
        
        if existing:
            logger.warning(f"账号 {account_id} 已存在，跳过")
            continue
        
        # 创建账号
        db_account = PlatformAccount(
            account_id=account_id,
            parent_account=batch_request.parent_account,
            platform=batch_request.platform,
            account_alias=shop.get("account_alias"),
            store_name=shop.get("store_name"),
            shop_type=shop.get("shop_type", "local"),
            shop_region=shop.get("shop_region"),
            username=batch_request.username,
            password_encrypted=encrypted_password,
            login_url=shop.get("login_url"),
            region="CN",
            currency=shop.get("currency", "CNY"),
            capabilities={
                "orders": True,
                "products": True,
                "services": shop.get("shop_type") == "local",  # 本地店支持客服
                "analytics": True,
                "finance": True,
                "inventory": True
            },
            enabled=True,
            created_by="system",
            updated_by="system"
        )
        
        db.add(db_account)
        created_accounts.append(db_account)
    
    await db.commit()
    
    logger.info(f"批量创建成功: {len(created_accounts)} 个账号")
    
    return created_accounts


@router.post("/import-from-local", response_model=AccountImportResponse)
async def import_from_local_accounts(
    db: AsyncSession = Depends(get_async_db)
):
    """
    从local_accounts.py导入账号
    
    - 跳过已存在的账号
    - 加密密码
    - 返回导入统计
    """
    try:
        from local_accounts import LOCAL_ACCOUNTS
    except ImportError:
        raise HTTPException(status_code=500, detail="无法导入local_accounts模块")
    
    imported_count = 0
    skipped_count = 0
    failed_count = 0
    details = []
    
    encryption_service = get_encryption_service()
    
    for platform_group, accounts in LOCAL_ACCOUNTS.items():
        for account in accounts:
            account_id = account.get('account_id')
            
            try:
                # 检查是否已存在
                result = await db.execute(select(PlatformAccount).where(PlatformAccount.account_id == account_id))
                existing = result.scalar_one_or_none()
                
                if existing:
                    skipped_count += 1
                    details.append({"account_id": account_id, "status": "skipped", "reason": "已存在"})
                    continue
                
                # 加密密码
                encrypted_password = encryption_service.encrypt_password(
                    account.get('password', '')
                )
                
                # 创建记录
                db_account = PlatformAccount(
                    account_id=account_id,
                    platform=account.get('platform', ''),
                    store_name=account.get('store_name', ''),
                    username=account.get('username', ''),
                    password_encrypted=encrypted_password,
                    login_url=account.get('login_url', ''),
                    email=account.get('E-mail', ''),
                    phone=account.get('phone', ''),
                    region=account.get('region', 'CN'),
                    currency=account.get('currency', 'CNY'),
                    shop_region=account.get('shop_region', ''),
                    capabilities=account.get('capabilities', {
                        "orders": True,
                        "products": True,
                        "services": True,
                        "analytics": True,
                        "finance": True,
                        "inventory": True
                    }),
                    enabled=account.get('enabled', False),
                    proxy_required=account.get('proxy_required', False),
                    notes=account.get('notes', ''),
                    created_by="import",
                    updated_by="import"
                )
                
                db.add(db_account)
                imported_count += 1
                details.append({"account_id": account_id, "status": "imported"})
                
            except Exception as e:
                failed_count += 1
                details.append({"account_id": account_id, "status": "failed", "reason": str(e)})
                logger.error(f"导入账号失败 {account_id}: {e}")
    
    await db.commit()
    
    logger.info(f"导入完成: 成功{imported_count}, 跳过{skipped_count}, 失败{failed_count}")
    
    return AccountImportResponse(
        message=f"导入完成：成功 {imported_count} 个，跳过 {skipped_count} 个，失败 {failed_count} 个",
        imported_count=imported_count,
        skipped_count=skipped_count,
        failed_count=failed_count,
        details=details
    )


@router.get("/stats/summary", response_model=AccountStats)
async def get_account_stats(
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取账号统计信息
    
    - 总账号数
    - 活跃账号数
    - 禁用账号数
    - 支持平台数
    - 各平台账号数分布
    """
    result = await db.execute(select(PlatformAccount))
    all_accounts = result.scalars().all()
    
    total = len(all_accounts)
    active = sum(1 for a in all_accounts if a.enabled)
    inactive = total - active
    
    # 平台分布
    platform_breakdown = {}
    for account in all_accounts:
        platform = account.platform
        platform_breakdown[platform] = platform_breakdown.get(platform, 0) + 1
    
    platforms = len(platform_breakdown)
    
    return AccountStats(
        total=total,
        active=active,
        inactive=inactive,
        platforms=platforms,
        platform_breakdown=platform_breakdown
    )

