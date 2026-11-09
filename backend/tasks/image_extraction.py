#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Celery异步图片提取任务(v3.0)

功能:
- 从Excel文件提取嵌入的产品图片
- 处理图片(压缩、缩略图)
- 保存到product_images表
"""

from __future__ import annotations

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.celery_app import celery_app
from backend.services.image_extractor import get_image_extractor
from backend.services.image_processor import get_image_processor
from backend.services.excel_parser import ExcelParser
from backend.models.database import SessionLocal
from modules.core.db import ProductImage
from modules.core.logger import get_logger

logger = get_logger(__name__)


# [*] ignore_result=True(2026-11-09)
#
# 为什么要它: ``ignore_result=False`` 时, Celery 在 ``send_task()`` 末尾会回调
# ``backend.on_task_call()``, Redis 结果后端在这里**同步订阅**该任务的 pubsub
# 通道 —— 于是**每次派发任务都要额外连一次 Redis**。
# Redis 不可达时, kombu 的重试是嵌套的(外层 reconnect 套内层 ensure, 默认各
# 20 次 × 1 秒), 实测单次 ``delay()`` 要**阻塞 16~17 秒**才抛错 —— 在 async
# 上下文里等于**把整个事件循环冻住**, 表现就是「Redis 一抖, 整个 API 挂起」。
#
# 本任务的返回值**没有任何调用方读取**(调用方只关心「有没有派发出去」),
# 所以直接声明「不关心结果」, 从根上跳过那次多余的 Redis 订阅。
#
# 代价: worker 执行完后不再往 Redis 写任务结果(省一次写, 也少占一个 key)。
# 若将来真要读这个任务的结果, 需同时去掉这里的 ``ignore_result=True``。
@celery_app.task(name="extract_product_images", ignore_result=True)
def extract_product_images_task(
    file_id: int, file_path: str, platform_code: str, shop_id: str
):
    """
    异步提取Excel中的产品图片

    Args:
        file_id: 文件ID
        file_path: Excel文件路径
        platform_code: 平台编码
        shop_id: 店铺ID
    """
    logger.info(f"[ImageTask] 开始: file_id={file_id}, path={file_path}")

    db = SessionLocal()

    try:
        # 1. 读取Excel(获取SKU列表)
        df = ExcelParser.read_excel(file_path, nrows=None)  # 读取全部数据

        # 查找SKU列(多种可能的列名)
        sku_candidates = [
            "*商品SKU",
            "商品SKU",
            "SKU",
            "platform_sku",
            "sku",
            "product_sku",
        ]
        sku_column = None

        for candidate in sku_candidates:
            if candidate in df.columns:
                sku_column = candidate
                break

        if not sku_column:
            logger.warning(f"[ImageTask] 未找到SKU列,跳过图片提取: file_id={file_id}")
            return {"success": False, "reason": "no_sku_column"}

        logger.info(f"[ImageTask] 找到SKU列: {sku_column}")

        # 2. 提取图片并关联SKU
        extractor = get_image_extractor()
        sku_images = extractor.extract_with_sku_mapping(
            Path(file_path), sku_column=sku_column, header_row=0  # 假设第0行是表头
        )

        if not sku_images:
            logger.info(f"[ImageTask] 文件中无图片,跳过: file_id={file_id}")
            return {"success": True, "extracted": 0}

        logger.info(f"[ImageTask] 提取到{len(sku_images)}个SKU的图片")

        # 3. 处理图片并保存
        processor = get_image_processor()
        saved_count = 0

        for sku, images in sku_images.items():
            for img_idx, img_info in enumerate(images):
                try:
                    # 处理图片(压缩+缩略图)
                    result = processor.process_product_image(
                        img_info["data"], sku, img_idx
                    )

                    # 保存到数据库
                    product_image = ProductImage(
                        platform_code=platform_code,
                        shop_id=shop_id,
                        platform_sku=sku,
                        image_url=result["original_url"],
                        thumbnail_url=result["thumbnail_url"],
                        file_size=result["file_size"],
                        width=result["width"],
                        height=result["height"],
                        format=result["format"],
                        is_main_image=(img_idx == 0),  # 第一张为主图
                        image_order=img_idx,
                    )

                    db.add(product_image)
                    saved_count += 1

                except Exception as e:
                    logger.error(
                        f"[ImageTask] 处理图片失败: sku={sku}, index={img_idx}, error={e}"
                    )
                    continue

        db.commit()
        logger.info(f"[ImageTask] 完成: file_id={file_id}, 保存{saved_count}张图片")

        return {
            "success": True,
            "file_id": file_id,
            "extracted": saved_count,
            "sku_count": len(sku_images),
        }

    except Exception as e:
        logger.error(f"[ImageTask] 失败: file_id={file_id}, error={e}", exc_info=True)
        db.rollback()
        return {"success": False, "file_id": file_id, "error": str(e)}
    finally:
        db.close()
