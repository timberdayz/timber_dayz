#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
库存管理API路由（v4.10.0更新：原产品管理）

提供SKU级库存管理功能：
- 库存列表（带图片）
- 库存详情
- 图片管理
- SKU搜索
"""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Optional
from datetime import datetime
from pathlib import Path

from backend.models.database import get_db, get_async_db
from backend.utils.api_response import success_response, error_response, pagination_response
from backend.utils.error_codes import ErrorCode, get_error_type
from modules.core.db import (
    FactProductMetric,  # 使用产品指标表（含产品基本信息）
    ProductImage,
    CatalogFile
)
from backend.services.image_processor import get_image_processor
# [WARN] v4.6.0 DSS架构重构：已删除MaterializedViewService（改为直接查询原始表）
# v4.17.0+: 不再导入旧的固定表类，使用动态表名
from modules.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

# 图片处理器
image_processor = get_image_processor()


@router.get("/products")
async def get_products(
    platform: Optional[str] = Query(None, description="平台筛选"),
    shop_id: Optional[str] = Query(None, description="店铺筛选"),
    keyword: Optional[str] = Query(None, description="关键词搜索（SKU/名称）"),
    category: Optional[str] = Query(None, description="分类筛选"),
    status: Optional[str] = Query(None, description="状态筛选：active/inactive"),
    has_image: Optional[bool] = Query(None, description="是否有图片"),
    low_stock: Optional[bool] = Query(None, description="低库存预警"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取库存列表（带缩略图）
    
    用于：
    - 库存管理界面
    - 销售看板（产品维度）
    - 库存看板（产品列表）
    """
    try:
        logger.info(f"[GetProducts] 查询: platform={platform}, keyword={keyword}, category={category}")
        
        # v4.17.0+: 使用动态表名查询B类数据表
        from sqlalchemy import text
        from backend.services.platform_table_manager import get_platform_table_manager
        from modules.core.db import DimPlatform
        
        platform_table_manager = get_platform_table_manager(db)
        
        # 构建查询条件（不包含platform，因为platform用于表名）
        conditions = ["1=1"]
        params = {}
        
        if keyword:
            conditions.append("(raw_data->>'SKU' ILIKE :keyword OR raw_data->>'商品名称' ILIKE :keyword)")
            params["keyword"] = f"%{keyword}%"
        
        if low_stock:
            # 低库存：可用库存 < 10（从JSONB字段读取）
            conditions.append("(raw_data->>'可用库存')::numeric < 10")
        
        where_clause = " AND ".join(conditions)
        
        # 确定要查询的平台
        if platform:
            # 单平台查询
            platforms = [platform]
        else:
            # 跨平台查询：从dim_platforms表查询所有平台
            platform_rows = db.execute(
                text("SELECT platform_code FROM dim_platforms WHERE is_active = true")
            ).fetchall()
            platforms = [row[0] for row in platform_rows] if platform_rows else []
        
        if not platforms:
            return pagination_response([], 0, page, page_size)
        
        # 构建UNION ALL查询（跨平台）
        union_queries = []
        for platform_code in platforms:
            table_name = platform_table_manager.get_table_name(
                platform=platform_code,
                data_domain='inventory',
                sub_domain=None,
                granularity='snapshot'
            )
            union_queries.append(f"""
                SELECT 
                    raw_data,
                    metric_date,
                    granularity,
                    created_at,
                    updated_at
                FROM b_class."{table_name}"
                WHERE {where_clause}
            """)
        
        # 查询总数（所有平台）
        count_queries = []
        for platform_code in platforms:
            table_name = platform_table_manager.get_table_name(
                platform=platform_code,
                data_domain='inventory',
                sub_domain=None,
                granularity='snapshot'
            )
            count_queries.append(f'SELECT COUNT(*) FROM b_class."{table_name}" WHERE {where_clause}')
        
        total = 0
        for count_sql in count_queries:
            try:
                count = db.execute(text(count_sql), params).scalar() or 0
                total += count
            except Exception as e:
                logger.warning(f"查询表 {count_sql.split('FROM')[1].split('WHERE')[0].strip()} 失败（可能不存在）: {e}")
        
        # 查询数据（分页，使用UNION ALL）
        offset = (page - 1) * page_size
        union_sql = " UNION ALL ".join(union_queries)
        data_sql = f"""
            SELECT * FROM (
                {union_sql}
            ) AS combined_data
            ORDER BY metric_date DESC, created_at DESC
            LIMIT :limit OFFSET :offset
        """
        params["limit"] = page_size
        params["offset"] = offset
        
        result = db.execute(text(data_sql), params)
        rows = result.fetchall()
        
        # 转换为字典列表（从JSONB字段提取数据）
        mv_result = {
            "data": [],
            "total": total,
            "page": page,
            "page_size": page_size
        }
        
        for row in rows:
            raw_data = row[0] if row[0] else {}
            product = {
                "platform_code": raw_data.get("平台代码") or raw_data.get("平台"),
                "shop_id": raw_data.get("店铺ID") or raw_data.get("店铺"),
                "platform_sku": raw_data.get("SKU"),
                "product_name": raw_data.get("商品名称"),
                "warehouse": raw_data.get("仓库"),
                "available_stock": float(raw_data.get("可用库存", 0)) if raw_data.get("可用库存") else 0,
                "total_stock": float(raw_data.get("总库存", 0)) if raw_data.get("总库存") else 0,
                "reserved_stock": float(raw_data.get("预留库存", 0)) if raw_data.get("预留库存") else 0,
                "in_transit_stock": float(raw_data.get("在途库存", 0)) if raw_data.get("在途库存") else 0,
                "stock_status": raw_data.get("库存状态"),
                "image_url": raw_data.get("图片URL"),
                "metric_date": row[1],
                "granularity": row[2],
                "created_at": row[3],
                "updated_at": row[4]
            }
            mv_result["data"].append(product)
        
        # 加载图片信息（保留旧逻辑，因为图片在单独表中）
        results = []
        for product in mv_result["data"]:
            platform_sku = product.get("platform_sku")
            platform_code = product.get("platform_code")
            shop_id_value = product.get("shop_id")
            
            # [*] v4.10.0修复：inventory域数据platform_code和shop_id可能为NULL
            # 图片查询优先级：1) ProductImage表 2) fact_product_metrics表的image_url字段
            images = []
            if platform_code and shop_id_value:
                # 标准查询：使用platform_code + shop_id + platform_sku
                result = await db.execute(
                    select(ProductImage).where(
                        and_(
                            ProductImage.platform_sku == platform_sku,
                            ProductImage.platform_code == platform_code,
                            ProductImage.shop_id == shop_id_value
                        )
                    ).order_by(ProductImage.is_main_image.desc(), ProductImage.image_order)
                )
                images = result.scalars().all()
            else:
                # [*] v4.10.0新增：inventory域数据可能platform_code/shop_id为NULL
                # 只使用platform_sku查询（图片可能只关联SKU，不关联平台/店铺）
                result = await db.execute(
                    select(ProductImage).where(
                        ProductImage.platform_sku == platform_sku
                    ).order_by(ProductImage.is_main_image.desc(), ProductImage.image_order)
                )
                images = result.scalars().all()
            
            # 图片处理：优先使用ProductImage表，其次使用fact表的image_url
            if images:
                # 使用ProductImage表的图片
                main_image = images[0].thumbnail_url
                all_images = [img.image_url for img in images]
            elif product.get('image_url'):
                # [*] v4.10.0新增：如果ProductImage表没有图片，使用fact表的image_url
                # mv_inventory_by_sku视图已包含image_url字段
                main_image = product.get('image_url')
                all_images = [product.get('image_url')]
            else:
                # 无图片
                main_image = None
                all_images = []
            
            # 组装库存数据（使用mv_inventory_by_sku视图字段）
            # [WARN] v4.10.0更新：inventory域数据字段较少，不包含价格、销售指标等
            inventory_data = {
                'platform_code': platform_code,
                'shop_id': shop_id_value,
                'platform_sku': platform_sku,
                'product_name': product.get('product_name'),
                'warehouse': product.get('warehouse'),
                
                # 库存信息（inventory域核心字段）
                'stock': product.get('available_stock') or product.get('total_stock') or 0,
                'total_stock': product.get('total_stock') or 0,
                'available_stock': product.get('available_stock') or 0,
                'reserved_stock': product.get('reserved_stock') or 0,
                'in_transit_stock': product.get('in_transit_stock') or 0,
                'stock_status': product.get('stock_status'),
                
                # inventory域不包含的字段（设为默认值）
                'category': None,  # inventory域可能没有分类
                'brand': None,  # inventory域可能没有品牌
                'price': 0,  # inventory域不包含价格
                'currency': 'CNY',  # 默认货币
                'price_rmb': 0,
                'sales_volume': 0,  # inventory域不包含销售指标
                'sales_amount': 0,
                'sales_amount_rmb': 0,
                'page_views': 0,  # inventory域不包含流量指标
                'unique_visitors': 0,
                'click_through_rate': 0,
                'conversion_rate': 0,
                'add_to_cart_rate': 0,
                'product_health_score': 0,
                
                # 图片信息（优先级：ProductImage表 > fact表的image_url）
                'thumbnail_url': main_image,
                'image_url': product.get('image_url') or main_image,  # v4.10.0新增：使用视图的image_url字段
                'image_count': len(images) if images else (1 if product.get('image_url') else 0),
                'all_images': all_images,
                
                # 时间戳
                'metric_date': product.get('metric_date').isoformat() if product.get('metric_date') else None,
                'granularity': product.get('granularity'),
                'created_at': product.get('created_at').isoformat() if product.get('created_at') else None,
                'updated_at': product.get('updated_at').isoformat() if product.get('updated_at') else None
            }
            
            results.append(inventory_data)
        
        # 统计信息
        stats = {
            'total_products': mv_result["total"],
            'total_stock': sum(p['stock'] for p in results),
            'low_stock_count': len([p for p in results if p['stock'] < 10]),
            'with_image_count': len([p for p in results if p['thumbnail_url']])
        }
        
        logger.info(
            f"[GetProducts] 原始表查询完成: "
            f"total={mv_result['total']}, "
            f"page={page}, "
            f"results={len(results)}"
        )
        
        # 使用success_response包装分页数据（包含额外的stats和performance信息）
        pagination_data = {
            'data': results,
            'total': mv_result["total"],
            'page': page,
            'page_size': page_size,
            'total_pages': (mv_result["total"] + page_size - 1) // page_size,
            'has_previous': page > 1,
            'has_next': page * page_size < mv_result["total"],
            'stats': stats,
            'performance': {
                'query_time_ms': mv_result['query_time_ms'],
                'data_source': 'materialized_view'  # v4.8.0标识
            }
        }
        
        return success_response(data=pagination_data)
        
    except Exception as e:
        logger.error(f"[GetProducts] 查询失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询库存列表失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.get("/products/{sku}")
async def get_product_detail(
    sku: str,
    platform: str = Query(..., description="平台编码"),
    shop_id: str = Query(..., description="店铺ID"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取库存详情（含完整图片）
    
    用于：
    - 库存详情页
    - 看板产品快速查看
    """
    try:
        logger.info(f"[GetProductDetail] 查询: sku={sku}, platform={platform}, shop_id={shop_id}")
        
        # 查询产品（获取最新指标数据）
        result = await db.execute(
            select(FactProductMetric).where(
                and_(
                    FactProductMetric.platform_sku == sku,
                    FactProductMetric.platform_code == platform,
                    FactProductMetric.shop_id == shop_id
                )
            ).order_by(FactProductMetric.metric_date.desc())
        )
        product = result.scalar_one_or_none()
        
        if not product:
            return error_response(
                code=ErrorCode.INVENTORY_NOT_FOUND,
                message=f"库存记录未找到: {sku}",
                error_type=get_error_type(ErrorCode.INVENTORY_NOT_FOUND),
                recovery_suggestion="请检查SKU、平台和店铺ID是否正确，或确认该产品已入库",
                status_code=404
            )
        
        # 查询产品图片
        result = await db.execute(
            select(ProductImage).where(
                and_(
                    ProductImage.platform_sku == sku,
                    ProductImage.platform_code == platform,
                    ProductImage.shop_id == shop_id
                )
            ).order_by(ProductImage.is_main_image.desc(), ProductImage.image_order)
        )
        images = result.scalars().all()
        
        # 组装图片信息
        image_list = []
        for img in images:
            image_list.append({
                'id': img.id,
                'image_url': img.image_url,
                'thumbnail_url': img.thumbnail_url,
                'is_main': img.is_main_image,
                'order': img.image_order,
                'width': img.width,
                'height': img.height,
                'size': img.file_size,
                'format': img.format,
                'quality_score': img.quality_score
            })
        
        # 组装产品详情（使用FactProductMetric字段）
        detail = {
            'platform_code': product.platform_code,
            'shop_id': product.shop_id,
            'platform_sku': product.platform_sku,
            'product_name': product.product_name,
            'category': product.category,
            'brand': product.brand,
            'price': float(product.price) if product.price else 0,
            'currency': product.currency,
            # [*] v4.6.3修复：优先使用available_stock（可售库存）
            'stock': (
                product.available_stock if product.available_stock is not None else
                (product.total_stock if product.total_stock is not None else (product.stock or 0))
            ),
            'total_stock': product.total_stock,
            'available_stock': product.available_stock,
            'reserved_stock': product.reserved_stock,
            'in_transit_stock': product.in_transit_stock,
            
            # 销售指标
            'sales_volume': product.sales_volume or 0,
            'sales_amount': float(product.sales_amount) if product.sales_amount else 0,
            
            # 流量指标
            'page_views': product.page_views or 0,
            
            # v4.6.3新增：仓库和规格信息
            'warehouse': product.warehouse,
            'specification': product.specification,
            'unique_visitors': product.unique_visitors or 0,
            'click_through_rate': float(product.click_through_rate) if product.click_through_rate else 0,
            'conversion_rate': float(product.conversion_rate) if product.conversion_rate else 0,
            
            # 图片列表
            'images': image_list,
            
            # 时间戳
            'metric_date': product.metric_date.isoformat() if product.metric_date else None,
            'granularity': product.granularity,
            'created_at': product.created_at.isoformat() if product.created_at else None,
            'updated_at': product.updated_at.isoformat() if product.updated_at else None
        }
        
        logger.info(f"[GetProductDetail] 查询成功: sku={sku}, images={len(image_list)}")
        
        return {
            'success': True,
            'data': detail
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[GetProductDetail] 查询失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="查询库存详情失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )


@router.post("/products/{sku}/images")
async def upload_product_image(
    sku: str,
    platform: str = Query(..., description="平台编码"),
    shop_id: str = Query(..., description="店铺ID"),
    file: UploadFile = File(...),
    is_main: bool = Query(False, description="是否设为主图"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    上传产品图片
    
    用于：
    - 手动补充产品图片
    - 更新产品主图
    """
    try:
        logger.info(f"[UploadImage] sku={sku}, platform={platform}, filename={file.filename}")
        
        # 验证产品存在
        result = await db.execute(
            select(FactProductMetric).where(
                and_(
                    FactProductMetric.platform_sku == sku,
                    FactProductMetric.platform_code == platform,
                    FactProductMetric.shop_id == shop_id
                )
            )
        )
        product = result.scalar_one_or_none()
        
        if not product:
            return error_response(
                code=ErrorCode.INVENTORY_NOT_FOUND,
                message=f"库存记录未找到: {sku}",
                error_type=get_error_type(ErrorCode.INVENTORY_NOT_FOUND),
                recovery_suggestion="请检查SKU、平台和店铺ID是否正确，或确认该产品已入库",
                status_code=404
            )
        
        # 读取图片数据
        image_data = await file.read()
        
        # 处理图片（压缩+缩略图）
        result = image_processor.process_product_image(
            image_data,
            sku,
            index=0  # 将自动根据现有图片数量调整
        )
        
        # 保存图片记录到数据库
        product_image = ProductImage(
            platform_code=platform,
            shop_id=shop_id,
            platform_sku=sku,
            image_url=result['original_url'],
            thumbnail_url=result['thumbnail_url'],
            file_size=result['file_size'],
            width=result['width'],
            height=result['height'],
            format=result['format'],
            is_main_image=is_main,
            image_order=(await db.execute(
                select(func.count(ProductImage.id)).where(
                    ProductImage.platform_sku == sku
                )
            )).scalar() or 0
        )
        
        db.add(product_image)
        await db.commit()
        await db.refresh(product_image)
        
        logger.info(f"[UploadImage] 上传成功: sku={sku}, image_id={product_image.id}")
        
        return {
            'success': True,
            'message': '图片上传成功',
            'image': {
                'id': product_image.id,
                'image_url': product_image.image_url,
                'thumbnail_url': product_image.thumbnail_url,
                'is_main': product_image.is_main_image
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"[UploadImage] 上传失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.FILE_WRITE_ERROR,
            message="图片上传失败",
            error_type=get_error_type(ErrorCode.FILE_WRITE_ERROR),
            detail=str(e),
            recovery_suggestion="请检查文件格式和大小，确保有足够的磁盘空间，或联系系统管理员",
            status_code=500
        )


@router.delete("/products/images/{image_id}")
async def delete_product_image(
    image_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """删除产品图片"""
    try:
        logger.info(f"[DeleteImage] image_id={image_id}")
        
        # 查询图片记录
        result = await db.execute(select(ProductImage).where(ProductImage.id == image_id))
        image = result.scalar_one_or_none()
        
        if not image:
            return error_response(
                code=ErrorCode.FILE_NOT_FOUND,
                message="图片未找到",
                error_type=get_error_type(ErrorCode.FILE_NOT_FOUND),
                recovery_suggestion="请检查图片ID是否正确，或确认该图片已上传",
                status_code=404
            )
        
        # 删除物理文件
        try:
            original_path = Path(image.image_url.replace('/static/product_images/', 'data/product_images/'))
            thumbnail_path = Path(image.thumbnail_url.replace('/static/product_images/', 'data/product_images/'))
            
            if original_path.exists():
                original_path.unlink()
            if thumbnail_path.exists():
                thumbnail_path.unlink()
        except Exception as e:
            logger.warning(f"[DeleteImage] 删除物理文件失败（继续）: {e}")
        
        # 删除数据库记录
        await db.delete(image)
        await db.commit()
        
        logger.info(f"[DeleteImage] 删除成功: image_id={image_id}")
        
        return {
            'success': True,
            'message': '图片删除成功'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"[DeleteImage] 删除失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.FILE_WRITE_ERROR,
            message="图片删除失败",
            error_type=get_error_type(ErrorCode.FILE_WRITE_ERROR),
            detail=str(e),
            recovery_suggestion="请检查图片是否存在，或联系系统管理员",
            status_code=500
        )


@router.get("/stats/platform-summary")
async def get_platform_summary(
    platform: Optional[str] = Query(None, description="平台筛选"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    平台库存汇总统计
    
    用于：
    - 销售看板概览
    - 库存看板概览
    """
    try:
        logger.info(f"[PlatformSummary] platform={platform}")
        
        # 子查询：获取每个SKU的最新数据（v4.10.0更新：同时包含products和inventory域）
        latest_date_subq = select(
            FactProductMetric.platform_code,
            FactProductMetric.shop_id,
            FactProductMetric.platform_sku,
            FactProductMetric.data_domain,  # v4.10.0新增：包含data_domain用于分组
            func.max(FactProductMetric.metric_date).label('latest_date')
        ).group_by(
            FactProductMetric.platform_code,
            FactProductMetric.shop_id,
            FactProductMetric.platform_sku,
            FactProductMetric.data_domain  # v4.10.0新增：按data_domain分组
        ).subquery()
        
        query = select(FactProductMetric).join(
            latest_date_subq,
            and_(
                FactProductMetric.platform_code == latest_date_subq.c.platform_code,
                FactProductMetric.shop_id == latest_date_subq.c.shop_id,
                FactProductMetric.platform_sku == latest_date_subq.c.platform_sku,
                FactProductMetric.data_domain == latest_date_subq.c.data_domain,  # v4.10.0新增：匹配data_domain
                FactProductMetric.metric_date == latest_date_subq.c.latest_date
            )
        )
        
        # v4.10.0更新：同时包含products和inventory域的数据
        query = query.filter(
            or_(
                FactProductMetric.data_domain == 'products',
                FactProductMetric.data_domain == 'inventory',
                and_(
                    FactProductMetric.data_domain.is_(None),
                    FactProductMetric.platform_code.isnot(None)  # 向后兼容：NULL data_domain但platform_code不为空
                )
            )
        )
        
        if platform:
            query = query.where(FactProductMetric.platform_code == platform)
        
        # 统计指标
        # [*] v4.18.2修复：使用异步查询
        from sqlalchemy import case
        count_result = await db.execute(select(func.count()).select_from(query.subquery()))
        total_products = count_result.scalar() or 0
        
        # [*] v4.6.3修复：统计库存时使用available_stock优先
        total_stock_query = select(
            func.sum(case(
                (FactProductMetric.available_stock.isnot(None), FactProductMetric.available_stock),
                (FactProductMetric.total_stock.isnot(None), FactProductMetric.total_stock),
                else_=FactProductMetric.stock
            ))
        ).select_from(query.subquery())
        total_stock_result = await db.execute(total_stock_query)
        total_stock = total_stock_result.scalar() or 0
        
        total_value_query = select(
            func.sum(case(
                (FactProductMetric.available_stock.isnot(None), FactProductMetric.available_stock),
                (FactProductMetric.total_stock.isnot(None), FactProductMetric.total_stock),
                else_=FactProductMetric.stock
            ) * FactProductMetric.price)
        ).select_from(query.subquery())
        total_value_result = await db.execute(total_value_query)
        total_value = total_value_result.scalar() or 0
        
        # [*] v4.6.3修复：低库存判断使用available_stock优先
        stock_field = case(
            (FactProductMetric.available_stock.isnot(None), FactProductMetric.available_stock),
            (FactProductMetric.total_stock.isnot(None), FactProductMetric.total_stock),
            else_=FactProductMetric.stock
        )
        low_stock_query = select(func.count()).select_from(
            query.where(stock_field < 10).subquery()
        )
        low_stock_result = await db.execute(low_stock_query)
        low_stock_count = low_stock_result.scalar() or 0
        
        out_of_stock_query = select(func.count()).select_from(
            query.where(stock_field == 0).subquery()
        )
        out_of_stock_result = await db.execute(out_of_stock_query)
        out_of_stock_count = out_of_stock_result.scalar() or 0
        
        # 分平台统计（v4.10.0更新：处理inventory域platform_code可能为NULL的情况）
        platform_stats = []
        if not platform:
            # 查询所有非NULL的platform_code
            platforms_result = await db.execute(
                select(FactProductMetric.platform_code).where(
                    FactProductMetric.platform_code.isnot(None)
                ).distinct()
            )
            platforms = platforms_result.scalars().all()
            
            for plt in platforms:
                if plt:
                    plt_query_subq = select(
                        FactProductMetric.platform_code,
                        FactProductMetric.shop_id,
                        FactProductMetric.platform_sku,
                        FactProductMetric.data_domain,  # v4.10.0新增
                        func.max(FactProductMetric.metric_date).label('latest_date')
                    ).where(
                        FactProductMetric.platform_code == plt
                    ).group_by(
                        FactProductMetric.platform_code,
                        FactProductMetric.shop_id,
                        FactProductMetric.platform_sku,
                        FactProductMetric.data_domain  # v4.10.0新增
                    ).subquery()
                    
                    plt_query = select(FactProductMetric).join(
                        plt_query_subq,
                        and_(
                            FactProductMetric.platform_code == plt_query_subq.c.platform_code,
                            FactProductMetric.shop_id == plt_query_subq.c.shop_id,
                            FactProductMetric.platform_sku == plt_query_subq.c.platform_sku,
                            FactProductMetric.data_domain == plt_query_subq.c.data_domain,  # v4.10.0新增
                            FactProductMetric.metric_date == plt_query_subq.c.latest_date
                        )
                    ).where(
                        or_(
                            FactProductMetric.data_domain == 'products',
                            FactProductMetric.data_domain == 'inventory',
                            and_(
                                FactProductMetric.data_domain.is_(None),
                                FactProductMetric.platform_code.isnot(None)
                            )
                        )
                    )
                    
                    # [*] v4.18.2修复：使用异步查询
                    # [*] v4.6.3修复：统计时使用available_stock优先
                    plt_count_result = await db.execute(select(func.count()).select_from(plt_query.subquery()))
                    plt_count = plt_count_result.scalar() or 0
                    
                    plt_stock_query = select(
                        func.sum(case(
                            (FactProductMetric.available_stock.isnot(None), FactProductMetric.available_stock),
                            (FactProductMetric.total_stock.isnot(None), FactProductMetric.total_stock),
                            else_=FactProductMetric.stock
                        ))
                    ).select_from(plt_query.subquery())
                    plt_stock_result = await db.execute(plt_stock_query)
                    plt_stock = plt_stock_result.scalar() or 0
                    
                    platform_stats.append({
                        'platform': plt,
                        'product_count': plt_count,
                        'total_stock': plt_stock
                    })
        
        logger.info(f"[PlatformSummary] 查询完成: total={total_products}")
        
        return {
            'success': True,
            'data': {
                'total_products': total_products,
                'total_stock': int(total_stock),
                'total_value': float(total_value),
                'low_stock_count': low_stock_count,
                'out_of_stock_count': out_of_stock_count,
                'platform_breakdown': platform_stats
            }
        }
        
    except Exception as e:
        logger.error(f"[PlatformSummary] 查询失败: {e}", exc_info=True)
        return error_response(
            code=ErrorCode.DATABASE_QUERY_ERROR,
            message="统计查询失败",
            error_type=get_error_type(ErrorCode.DATABASE_QUERY_ERROR),
            detail=str(e),
            recovery_suggestion="请检查数据库连接和查询参数，或联系系统管理员",
            status_code=500
        )

