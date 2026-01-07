#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
产品图片提取服务（v3.0核心模块）

功能：
- 从Excel文件提取嵌入的产品图片
- 关联图片到SKU/行号
- 支持多种Excel格式
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple
from io import BytesIO

from modules.core.logger import get_logger

logger = get_logger(__name__)


class ImageExtractor:
    """图片提取器"""
    
    def __init__(self):
        self.supported_formats = ['xlsx', 'xls']
    
    def extract_from_excel(self, file_path: Path) -> Dict[int, List[Dict]]:
        """从Excel提取所有嵌入图片
        
        Args:
            file_path: Excel文件路径
            
        Returns:
            {行号: [{data: bytes, format: str, column: int}]}
        """
        file_path = Path(file_path)
        
        # 根据扩展名选择提取方法
        if file_path.suffix.lower() == '.xlsx':
            return self._extract_from_xlsx(file_path)
        elif file_path.suffix.lower() == '.xls':
            logger.warning(f"XLS格式图片提取未实现，跳过: {file_path.name}")
            return {}
        else:
            logger.warning(f"不支持的文件格式: {file_path.suffix}")
            return {}
    
    def _extract_from_xlsx(self, file_path: Path) -> Dict[int, List[Dict]]:
        """从XLSX文件提取图片"""
        try:
            from openpyxl import load_workbook
            from openpyxl.drawing.image import Image as OpenpyxlImage
            
            logger.info(f"开始提取图片: {file_path.name}")
            
            # 加载工作簿（不用data_only，需要读取图片）
            workbook = load_workbook(file_path, data_only=False, keep_vba=False)
            sheet = workbook.active
            
            images_by_row = {}
            image_count = 0
            
            # 遍历所有图片对象
            for image in sheet._images:
                try:
                    # 获取图片锚点（关联的单元格）
                    anchor = image.anchor
                    row_idx = anchor._from.row + 1  # openpyxl从0开始，转换为Excel行号
                    col_idx = anchor._from.col
                    
                    # 提取图片数据
                    image_data = image._data()
                    
                    if row_idx not in images_by_row:
                        images_by_row[row_idx] = []
                    
                    images_by_row[row_idx].append({
                        'data': image_data,
                        'format': getattr(image, 'format', 'png').lower(),
                        'column': col_idx,
                        'size': len(image_data)
                    })
                    
                    image_count += 1
                    
                except Exception as e:
                    logger.warning(f"提取单张图片失败: {e}")
                    continue
            
            logger.info(f"图片提取完成: {file_path.name}，共{image_count}张图片，分布在{len(images_by_row)}行")
            return images_by_row
            
        except ImportError:
            logger.error("openpyxl未安装，无法提取图片")
            return {}
        except Exception as e:
            logger.error(f"图片提取失败: {e}", exc_info=True)
            return {}
    
    def extract_with_sku_mapping(
        self, 
        file_path: Path, 
        sku_column: str = '*商品SKU',
        header_row: int = 0
    ) -> Dict[str, List[Dict]]:
        """提取图片并关联到SKU
        
        Args:
            file_path: Excel文件路径
            sku_column: SKU列名
            header_row: 表头行号（0开始）
            
        Returns:
            {sku: [{data: bytes, format: str, size: int}]}
        """
        import pandas as pd
        
        try:
            # 1. 读取SKU数据
            df = pd.read_excel(file_path, header=header_row, engine='openpyxl')
            
            if sku_column not in df.columns:
                logger.warning(f"未找到SKU列: {sku_column}")
                return {}
            
            # 2. 提取图片（按行号）
            images_by_row = self.extract_from_excel(file_path)
            
            # 3. 关联SKU
            sku_images = {}
            
            for row_idx, images in images_by_row.items():
                # Excel行号转DataFrame索引（考虑header_row）
                df_idx = row_idx - header_row - 1
                
                if 0 <= df_idx < len(df):
                    sku = df.iloc[df_idx][sku_column]
                    
                    if pd.notna(sku):
                        sku_str = str(sku).strip()
                        
                        if sku_str not in sku_images:
                            sku_images[sku_str] = []
                        
                        sku_images[sku_str].extend(images)
            
            logger.info(f"SKU-图片关联完成: {len(sku_images)}个SKU，共{sum(len(imgs) for imgs in sku_images.values())}张图片")
            return sku_images
            
        except Exception as e:
            logger.error(f"SKU-图片关联失败: {e}", exc_info=True)
            return {}


def get_image_extractor() -> ImageExtractor:
    """获取图片提取器实例"""
    return ImageExtractor()

