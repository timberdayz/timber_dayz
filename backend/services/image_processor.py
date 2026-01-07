#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图片处理服务（v3.0核心模块）

功能：
- 图片压缩（优化存储）
- 缩略图生成（列表显示）
- 格式转换（统一JPEG）
- 图片存储（本地/OSS）
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple
from io import BytesIO
import hashlib

from modules.core.logger import get_logger

logger = get_logger(__name__)


class ImageProcessor:
    """图片处理器"""
    
    def __init__(self, storage_root: Path = None):
        """初始化图片处理器
        
        Args:
            storage_root: 图片存储根目录（默认: data/product_images）
        """
        if storage_root is None:
            storage_root = Path("data/product_images")
        
        self.storage_root = Path(storage_root)
        self.storage_root.mkdir(parents=True, exist_ok=True)
        
        # 子目录
        self.original_dir = self.storage_root / "original"
        self.thumbnail_dir = self.storage_root / "thumbnails"
        self.original_dir.mkdir(exist_ok=True)
        self.thumbnail_dir.mkdir(exist_ok=True)
    
    def process_product_image(
        self, 
        image_data: bytes, 
        sku: str, 
        index: int = 0,
        create_thumbnail: bool = True
    ) -> Dict[str, any]:
        """处理产品图片
        
        Args:
            image_data: 图片二进制数据
            sku: 产品SKU
            index: 图片序号（同一SKU可能有多张图片）
            create_thumbnail: 是否生成缩略图
            
        Returns:
            图片信息字典
        """
        try:
            from PIL import Image
            
            # 打开图片
            img = Image.open(BytesIO(image_data))
            original_format = img.format or 'PNG'
            original_size = (img.width, img.height)
            
            logger.info(f"处理图片: SKU={sku}, index={index}, size={original_size}, format={original_format}")
            
            # 转换为RGB（处理RGBA/P模式）
            if img.mode in ('RGBA', 'P', 'LA'):
                # 创建白色背景
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 生成文件名（使用hash避免冲突）
            file_hash = hashlib.md5(image_data).hexdigest()[:8]
            filename = f"{sku}_{index}_{file_hash}.jpg"
            
            # 处理原图（压缩，最大1920x1920）
            img_original = img.copy()
            if img_original.width > 1920 or img_original.height > 1920:
                img_original.thumbnail((1920, 1920), Image.LANCZOS)
            
            # 保存原图
            original_path = self.original_dir / filename
            img_original.save(original_path, 'JPEG', quality=90, optimize=True)
            original_size_kb = original_path.stat().st_size / 1024
            
            logger.debug(f"原图保存: {original_path.name}, {original_size_kb:.1f}KB")
            
            # 生成缩略图
            thumbnail_path = None
            if create_thumbnail:
                img_thumbnail = img.copy()
                img_thumbnail.thumbnail((200, 200), Image.LANCZOS)
                
                thumbnail_path = self.thumbnail_dir / filename
                img_thumbnail.save(thumbnail_path, 'JPEG', quality=85, optimize=True)
                thumbnail_size_kb = thumbnail_path.stat().st_size / 1024
                
                logger.debug(f"缩略图保存: {thumbnail_path.name}, {thumbnail_size_kb:.1f}KB")
            
            # 返回结果
            result = {
                'sku': sku,
                'index': index,
                'original_path': str(original_path),
                'thumbnail_path': str(thumbnail_path) if thumbnail_path else None,
                'original_url': f"/static/product_images/original/{filename}",
                'thumbnail_url': f"/static/product_images/thumbnails/{filename}" if thumbnail_path else None,
                'file_size': len(image_data),
                'width': img.width,
                'height': img.height,
                'format': 'JPEG'
            }
            
            logger.info(f"图片处理完成: SKU={sku}, 原图={original_size_kb:.1f}KB")
            return result
            
        except ImportError:
            logger.error("Pillow未安装: pip install Pillow")
            raise
        except Exception as e:
            logger.error(f"图片处理失败: {e}", exc_info=True)
            raise
    
    def batch_process_images(
        self, 
        images_map: Dict[int, List[Dict]], 
        sku_map: Dict[int, str]
    ) -> List[Dict]:
        """批量处理图片
        
        Args:
            images_map: {行号: [图片数据]}
            sku_map: {行号: SKU}
            
        Returns:
            图片信息列表
        """
        results = []
        
        for row_idx, images in images_map.items():
            sku = sku_map.get(row_idx)
            
            if not sku:
                logger.warning(f"行{row_idx}未找到SKU，跳过图片处理")
                continue
            
            for img_idx, img_info in enumerate(images):
                try:
                    result = self.process_product_image(
                        img_info['data'],
                        sku,
                        img_idx
                    )
                    results.append(result)
                    
                except Exception as e:
                    logger.error(f"处理图片失败: SKU={sku}, index={img_idx}, error={e}")
                    continue
        
        logger.info(f"批量处理完成: {len(results)}张图片")
        return results
    
    def get_storage_stats(self) -> Dict[str, any]:
        """获取存储统计信息"""
        original_files = list(self.original_dir.glob("*.jpg"))
        thumbnail_files = list(self.thumbnail_dir.glob("*.jpg"))
        
        original_size = sum(f.stat().st_size for f in original_files)
        thumbnail_size = sum(f.stat().st_size for f in thumbnail_files)
        
        return {
            'original_count': len(original_files),
            'thumbnail_count': len(thumbnail_files),
            'original_size_mb': original_size / (1024 * 1024),
            'thumbnail_size_mb': thumbnail_size / (1024 * 1024),
            'total_size_mb': (original_size + thumbnail_size) / (1024 * 1024)
        }


def get_image_processor(storage_root: Path = None) -> ImageProcessor:
    """获取图片处理器实例"""
    return ImageProcessor(storage_root)

