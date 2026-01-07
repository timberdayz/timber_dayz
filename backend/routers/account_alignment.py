#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
账号对齐API - v4.3.6 现代化ERP版
运行时仅用DB+缓存，YAML作为导入/导出通道

v4.18.0: 添加response_model支持Contract-First架构
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict
import yaml
import csv
import io

from backend.models.database import get_db, get_async_db
from backend.utils.api_response import success_response, error_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.services.account_alignment import get_account_alignment_service
from modules.core.db import AccountAlias
from modules.core.logger import get_logger

# v4.18.0: 导入schemas（Contract-First架构）
from backend.schemas.account_alignment import (
    AlignmentStatsResponse,
    MissingSuggestionsResponse,
    AliasListResponse,
    AddAliasRequest,
    AddAliasResponse,
    BatchAddAliasesRequest,
    BatchAddAliasesResponse,
    BackfillRequest,
    BackfillResponse,
    ImportResponse,
    UpdateAliasRequest,
    UpdateAliasResponse,
    DistinctRawStoresResponse,
)

router = APIRouter(prefix="/account-alignment", tags=["账号对齐"])
logger = get_logger(__name__)


@router.get("/stats", response_model=AlignmentStatsResponse)
async def get_alignment_stats(db: AsyncSession = Depends(get_async_db)):
    """
    获取对齐统计
    
    Returns:
        {
            "total_orders": int,
            "aligned": int,
            "unaligned": int,
            "coverage_rate": float,
            "unique_raw_labels": int
        }
    """
    try:
        service = get_account_alignment_service(db)
        stats = service.get_alignment_stats()
        
        return AlignmentStatsResponse(
            total_orders=stats.total_orders,
            aligned=stats.aligned,
            unaligned=stats.unaligned,
            coverage_rate=round(stats.coverage_rate, 2),
            unique_raw_labels=stats.unique_raw_labels
        )
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取统计失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            status_code=500
        )


@router.get("/suggestions", response_model=MissingSuggestionsResponse)
async def get_missing_mappings(min_orders: int = 5, db: AsyncSession = Depends(get_async_db)):
    """
    获取缺失映射建议
    
    Args:
        min_orders: 最小订单数（过滤低频店铺）
        
    Returns:
        list: 建议映射列表
    """
    try:
        service = get_account_alignment_service(db)
        suggestions = service.suggest_missing_mappings(min_orders)
        
        return MissingSuggestionsResponse(
            success=True,
            suggestions=suggestions,
            count=len(suggestions)
        )
    except Exception as e:
        logger.error(f"获取建议失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取建议失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/list-aliases", response_model=AliasListResponse)
async def list_all_aliases(
    platform: str = 'miaoshou',
    active_only: bool = True,
    db: AsyncSession = Depends(get_async_db)
):
    """
    列出所有别名映射（供UI显示和编辑）
    
    Args:
        platform: 平台代码
        active_only: 仅活跃的映射
        
    Returns:
        list: 别名列表
    """
    try:
        from sqlalchemy import select
        
        stmt = select(AccountAlias).where(AccountAlias.platform == platform)
        if active_only:
            stmt = stmt.where(AccountAlias.active == True)
        
        stmt = stmt.order_by(AccountAlias.account, AccountAlias.site, AccountAlias.store_label_raw)
        
        result = await db.execute(stmt)
        aliases = result.scalars().all()
        
        from backend.schemas.account_alignment import AliasResponse
        return AliasListResponse(
            success=True,
            aliases=[
                AliasResponse(
                    id=a.id,
                    account=a.account,
                    site=a.site,
                    store_label_raw=a.store_label_raw,
                    target_id=a.target_id,
                    confidence=a.confidence,
                    active=a.active,
                    notes=a.notes,
                    created_by=a.created_by,
                    created_at=a.created_at.isoformat() if a.created_at else None,
                    updated_at=a.updated_at.isoformat() if a.updated_at else None
                )
                for a in aliases
            ],
            count=len(aliases)
        )
    except Exception as e:
        logger.error(f"列出别名失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="列出别名失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.post("/add-alias", response_model=AddAliasResponse)
async def add_alias(request: Dict, db: AsyncSession = Depends(get_async_db)):
    """
    添加单个别名映射
    
    Request:
        {
            "account": str,
            "site": str,
            "store_label_raw": str,
            "target_id": str,
            "notes": str (可选)
        }
    """
    try:
        service = get_account_alignment_service(db)
        success = service.add_alias(
            account=request.get('account'),
            site=request.get('site'),
            store_label_raw=request['store_label_raw'],
            target_id=request['target_id'],
            notes=request.get('notes'),
            created_by='web_ui'
        )
        
        if success:
            return AddAliasResponse(success=True, message="别名添加成功")
        else:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="别名添加失败",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                status_code=400
            )
            
    except KeyError as e:
        return error_response(
            code=ErrorCode.DATA_REQUIRED_FIELD_MISSING,
            message=f"缺少必填字段: {e}",
            error_type=get_error_type(ErrorCode.DATA_REQUIRED_FIELD_MISSING),
            recovery_suggestion="请检查请求参数，确保所有必填字段都已提供",
            status_code=400
        )
    except Exception as e:
        logger.error(f"添加别名失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="添加别名失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.post("/batch-add-aliases", response_model=BatchAddAliasesResponse)
async def batch_add_aliases(request: Dict, db: AsyncSession = Depends(get_async_db)):
    """
    批量添加别名映射
    
    Request:
        {
            "mappings": [
                {
                    "account": str,
                    "site": str,
                    "store_label_raw": str,
                    "target_id": str,
                    "notes": str (可选)
                },
                ...
            ]
        }
    """
    try:
        service = get_account_alignment_service(db)
        mappings = request.get('mappings', [])
        
        success_count, failed_count = service.batch_add_aliases(
            mappings,
            created_by='web_ui_batch'
        )
        
        return BatchAddAliasesResponse(
            success=True,
            added=success_count,
            skipped=failed_count,
            errors=[]
        )
    except Exception as e:
        logger.error(f"批量添加失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="批量添加失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据格式和数据库连接，或联系系统管理员",
            status_code=500
        )


@router.post("/backfill", response_model=BackfillResponse)
async def backfill_alignment(limit: int = None, db: AsyncSession = Depends(get_async_db)):
    """
    执行回填（将别名映射应用到历史订单）
    
    Args:
        limit: 限制处理数量（None=全量）
        
    Returns:
        对齐统计
    """
    try:
        service = get_account_alignment_service(db)
        stats = service.backfill_alignment(limit)
        
        return BackfillResponse(
            success=True,
            updated=stats.aligned,
            message=f"回填完成：对齐{stats.aligned}个订单，覆盖率{stats.coverage_rate:.1f}%"
        )
    except Exception as e:
        logger.error(f"回填失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="回填失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.post("/import-yaml", response_model=ImportResponse)
async def import_yaml_aliases(file: UploadFile = File(...), db: AsyncSession = Depends(get_async_db)):
    """
    导入YAML格式别名（批量导入通道）
    
    格式：
    ```yaml
    shop_aliases:
      'miaoshou:账号:站点:店铺名': 'target_id'
    ```
    """
    try:
        content = await file.read()
        data = yaml.safe_load(content.decode('utf-8'))
        shop_aliases = data.get('shop_aliases', {})
        
        if not shop_aliases:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="YAML文件中未找到shop_aliases节点",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查YAML文件格式，确保包含shop_aliases节点",
                status_code=400
            )
        
        # 转换为批量添加格式
        mappings = []
        for key, target_id in shop_aliases.items():
            if not target_id or target_id == '':
                continue  # 跳过空值
            
            # 解析key: 'platform:account:site:label'
            parts = key.split(':')
            if len(parts) != 4:
                logger.warning(f"跳过格式错误的key: {key}")
                continue
            
            mappings.append({
                'account': parts[1] if parts[1] else None,
                'site': parts[2] if parts[2] else None,
                'store_label_raw': parts[3],
                'target_id': target_id,
                'notes': f'YAML导入: {file.filename}'
            })
        
        # 批量添加
        service = get_account_alignment_service(db)
        success_count, failed_count = service.batch_add_aliases(mappings, created_by='yaml_import')
        
        return ImportResponse(
            success=True,
            imported=success_count,
            skipped=failed_count,
            errors=[]
        )
    except yaml.YAMLError as e:
        return error_response(
            code=ErrorCode.DATA_FORMAT_INVALID,
            message=f"YAML格式错误: {str(e)}",
            error_type=get_error_type(ErrorCode.DATA_FORMAT_INVALID),
            recovery_suggestion="请检查YAML文件格式是否正确，或参考示例文件",
            status_code=400
        )
    except Exception as e:
        logger.error(f"YAML导入失败: {e}")
        return error_response(
            code=ErrorCode.FILE_READ_ERROR,
            message="YAML导入失败",
            error_type=get_error_type(ErrorCode.FILE_READ_ERROR),
            detail=str(e),
            recovery_suggestion="请检查文件格式和内容，或联系系统管理员",
            status_code=500
        )


@router.post("/import-csv", response_model=ImportResponse)
async def import_csv_aliases(file: UploadFile = File(...), db: AsyncSession = Depends(get_async_db)):
    """
    导入CSV格式别名（批量导入通道）
    
    CSV格式（必须包含表头）：
    account,site,store_label_raw,target_id,notes
    虾皮巴西_东朗照明主体,菲律宾,菲律宾1店,shopee_ph_1,主力店
    """
    try:
        content = await file.read()
        csv_text = content.decode('utf-8')
        
        reader = csv.DictReader(io.StringIO(csv_text))
        mappings = []
        
        for row in reader:
            if not row.get('store_label_raw') or not row.get('target_id'):
                continue  # 跳过不完整的行
            
            mappings.append({
                'account': row.get('account'),
                'site': row.get('site'),
                'store_label_raw': row['store_label_raw'],
                'target_id': row['target_id'],
                'notes': row.get('notes', f'CSV导入: {file.filename}')
            })
        
        # 批量添加
        service = get_account_alignment_service(db)
        success_count, failed_count = service.batch_add_aliases(mappings, created_by='csv_import')
        
        return ImportResponse(
            success=True,
            imported=success_count,
            skipped=failed_count,
            errors=[]
        )
    except Exception as e:
        logger.error(f"CSV导入失败: {e}")
        return error_response(
            code=ErrorCode.FILE_READ_ERROR,
            message="CSV导入失败",
            error_type=get_error_type(ErrorCode.FILE_READ_ERROR),
            detail=str(e),
            recovery_suggestion="请检查CSV文件格式和内容，或联系系统管理员",
            status_code=500
        )


@router.get("/export-yaml")
async def export_yaml_aliases(
    platform: str = 'miaoshou',
    active_only: bool = True,
    db: AsyncSession = Depends(get_async_db)
):
    """
    导出别名为YAML格式（备份/分享）
    
    Returns:
        YAML文本内容
    """
    try:
        from sqlalchemy import select
        from fastapi.responses import Response
        
        stmt = select(AccountAlias).where(AccountAlias.platform == platform)
        if active_only:
            stmt = stmt.where(AccountAlias.active == True)
        
        result = await db.execute(stmt)
        aliases = result.scalars().all()
        
        # 构建YAML结构
        shop_aliases = {}
        for a in aliases:
            key = f"{a.platform}:{a.account or ''}:{a.site or ''}:{a.store_label_raw}"
            shop_aliases[key] = a.target_id
        
        yaml_content = yaml.dump(
            {'shop_aliases': shop_aliases},
            allow_unicode=True,
            sort_keys=True
        )
        
        return Response(
            content=yaml_content,
            media_type="application/x-yaml",
            headers={
                "Content-Disposition": f"attachment; filename=shop_aliases_export.yaml"
            }
        )
    except Exception as e:
        logger.error(f"YAML导出失败: {e}")
        return error_response(
            code=ErrorCode.FILE_WRITE_ERROR,
            message="YAML导出失败",
            error_type=get_error_type(ErrorCode.FILE_WRITE_ERROR),
            detail=str(e),
            recovery_suggestion="请检查磁盘空间和文件权限，或联系系统管理员",
            status_code=500
        )


@router.get("/export-csv")
async def export_csv_aliases(
    platform: str = 'miaoshou',
    active_only: bool = True,
    db: AsyncSession = Depends(get_async_db)
):
    """
    导出别名为CSV格式（Excel友好）
    
    Returns:
        CSV文本内容
    """
    try:
        from sqlalchemy import select
        from fastapi.responses import Response
        
        stmt = select(AccountAlias).where(AccountAlias.platform == platform)
        if active_only:
            stmt = stmt.where(AccountAlias.active == True)
        
        result = await db.execute(stmt)
        aliases = result.scalars().all()
        
        # 构建CSV
        output = io.StringIO()
        writer = csv.writer(output)
        
        # 表头
        writer.writerow(['account', 'site', 'store_label_raw', 'target_id', 'notes', 'confidence', 'created_at'])
        
        # 数据行
        for a in aliases:
            writer.writerow([
                a.account or '',
                a.site or '',
                a.store_label_raw,
                a.target_id,
                a.notes or '',
                a.confidence,
                a.created_at.strftime('%Y-%m-%d %H:%M:%S') if a.created_at else ''
            ])
        
        csv_content = output.getvalue()
        
        return Response(
            content=csv_content.encode('utf-8-sig'),  # BOM for Excel
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=shop_aliases_export.csv"
            }
        )
    except Exception as e:
        logger.error(f"CSV导出失败: {e}")
        return error_response(
            code=ErrorCode.FILE_WRITE_ERROR,
            message="CSV导出失败",
            error_type=get_error_type(ErrorCode.FILE_WRITE_ERROR),
            detail=str(e),
            recovery_suggestion="请检查磁盘空间和文件权限，或联系系统管理员",
            status_code=500
        )


@router.put("/update-alias/{alias_id}", response_model=UpdateAliasResponse)
async def update_alias(alias_id: int, request: Dict, db: AsyncSession = Depends(get_async_db)):
    """
    更新别名映射
    
    Args:
        alias_id: 别名ID
        request: {"target_id": str, "notes": str, "active": bool}
    """
    try:
        result = await db.execute(select(AccountAlias).where(AccountAlias.id == alias_id))
        alias = result.scalar_one_or_none()
        if not alias:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="别名不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查别名ID是否正确，或确认该别名已创建",
                status_code=404
            )
        
        # 更新字段
        if 'target_id' in request:
            alias.target_id = request['target_id']
        if 'notes' in request:
            alias.notes = request['notes']
        if 'active' in request:
            alias.active = request['active']
        
        alias.updated_by = 'web_ui'
        
        await db.commit()
        
        return UpdateAliasResponse(success=True, message="别名更新成功")
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"更新别名失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="更新别名失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.delete("/delete-alias/{alias_id}", response_model=UpdateAliasResponse)
async def delete_alias(alias_id: int, db: AsyncSession = Depends(get_async_db)):
    """
    删除别名映射（软删除：设置active=false）
    """
    try:
        result = await db.execute(select(AccountAlias).where(AccountAlias.id == alias_id))
        alias = result.scalar_one_or_none()
        if not alias:
            return error_response(
                code=ErrorCode.DATA_VALIDATION_FAILED,
                message="别名不存在",
                error_type=get_error_type(ErrorCode.DATA_VALIDATION_FAILED),
                recovery_suggestion="请检查别名ID是否正确，或确认该别名已创建",
                status_code=404
            )
        
        alias.active = False
        alias.updated_by = 'web_ui'
        
        await db.commit()
        
        return UpdateAliasResponse(success=True, message="别名已停用")
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"删除别名失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="删除别名失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和权限，或联系系统管理员",
            status_code=500
        )


@router.get("/distinct-raw-stores", response_model=DistinctRawStoresResponse)
async def get_distinct_raw_stores(
    platform: str = 'miaoshou',
    data_domain: str = 'orders',
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取未对齐的唯一店铺名列表（供UI快速配置）
    
    Returns:
        list: 唯一店铺名及其统计信息
    """
    try:
        from sqlalchemy import text
        
        stmt = text("""
            SELECT 
                o.account,
                o.site,
                o.store_label_raw,
                COUNT(*) as order_count,
                SUM(o.total_amount_rmb) as total_gmv,
                MIN(o.order_date_local) as first_order,
                MAX(o.order_date_local) as last_order
            FROM fact_orders o
            LEFT JOIN account_aliases a ON (
                a.platform = :platform
                AND a.data_domain = :domain
                AND a.account = o.account
                AND a.site = o.site
                AND a.store_label_raw = o.store_label_raw
                AND a.active = TRUE
            )
            WHERE o.platform_code = :platform
              AND o.shop_id = 'none'
              AND o.aligned_account_id IS NULL
              AND o.store_label_raw IS NOT NULL
              AND a.id IS NULL  -- 未配置别名的
            GROUP BY o.account, o.site, o.store_label_raw
            ORDER BY order_count DESC
        """)
        
        result = await db.execute(stmt, {
            "platform": platform,
            "domain": data_domain
        })
        results = result.all()
        
        stores = []
        for row in results:
            store_info = f"{row[0]}:{row[1]}:{row[2]} (订单:{row[3]})"
            stores.append(store_info)
        
        return DistinctRawStoresResponse(
            success=True,
            stores=stores,
            count=len(stores)
        )
    except Exception as e:
        logger.error(f"获取未对齐店铺失败: {e}")
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="获取未对齐店铺失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


def _generate_suggested_id(account: str, site: str, store_label: str) -> str:
    """生成建议的target_id（简化版）"""
    import re
    
    # 平台前缀
    prefix = 'shopee'
    if account and 'tiktok' in account.lower():
        prefix = 'tiktok'
    
    # 站点代码
    site_map = {
        '菲律宾': 'ph', '新加坡': 'sg', '马来': 'my', '马来西亚': 'my',
        '泰国': 'th', '越南': 'vn', '印尼': 'id', '巴西': 'br'
    }
    site_code = site_map.get(site, site.lower()[:2] if site else '')
    
    # 店铺标识
    match = re.search(r'(\d+)店', store_label)
    if match:
        suffix = match.group(1)
    elif '3c' in store_label.lower():
        suffix = '3c'
    elif '玩具' in store_label:
        suffix = 'toys'
    else:
        suffix = re.sub(r'[^\w]', '_', store_label.lower())[:10]
    
    # 组合
    if site_code and suffix:
        return f"{prefix}_{site_code}_{suffix}"
    elif suffix:
        return f"{prefix}_{suffix}"
    else:
        return f"{prefix}_unknown"
