#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动文件修复服务（零手动干预）

功能：
1. 自动检测损坏的.xls文件
2. 使用Excel COM自动修复（Windows）
3. 缓存修复结果到data/raw/repaired/
4. 透明集成到ExcelParser（用户无感知）
"""

import os
import sys
import platform
from pathlib import Path
from typing import Optional
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 全局缓存：检测Windows环境和Excel是否可用
_EXCEL_COM_AVAILABLE = None
# 延迟初始化，避免循环导入
_REPAIR_CACHE_DIR = None

def _get_repair_cache_dir() -> Path:
    """获取修复缓存目录"""
    global _REPAIR_CACHE_DIR
    if _REPAIR_CACHE_DIR is None:
        from modules.core.path_manager import get_data_raw_dir
        _REPAIR_CACHE_DIR = get_data_raw_dir() / "repaired"
    return _REPAIR_CACHE_DIR


def _check_excel_com_available() -> bool:
    """检测Excel COM是否可用（只检测一次）"""
    global _EXCEL_COM_AVAILABLE
    
    if _EXCEL_COM_AVAILABLE is not None:
        return _EXCEL_COM_AVAILABLE
    
    # 非Windows系统
    if platform.system() != 'Windows':
        logger.info("非Windows系统，Excel COM修复不可用")
        _EXCEL_COM_AVAILABLE = False
        return False
    
    # 检查pywin32
    try:
        import win32com.client
        # 尝试启动Excel（快速测试）
        excel = win32com.client.Dispatch("Excel.Application")
        excel.Visible = False
        excel.Quit()
        logger.info("Excel COM可用，自动修复已启用")
        _EXCEL_COM_AVAILABLE = True
        return True
    except Exception as e:
        logger.warning(f"Excel COM不可用（{e}），将跳过自动修复")
        _EXCEL_COM_AVAILABLE = False
        return False


def get_repaired_path(original_path: Path) -> Path:
    """
    获取修复后文件的缓存路径（支持任意目录）
    
    Args:
        original_path: 原始.xls文件路径
    
    Returns:
        修复后的.xlsx文件路径（可能不存在）
    """
    # ⭐ 智能路径处理：支持data/raw、temp/outputs等任意目录
    from modules.core.path_manager import get_data_raw_dir, get_output_dir, get_downloads_dir
    
    original_path = Path(original_path).absolute()
    
    # 尝试提取相对路径（使用统一路径管理）
    base_dirs = [get_data_raw_dir(), get_output_dir(), get_downloads_dir()]
    relative_part = None
    
    for base_dir in base_dirs:
        try:
            relative_part = original_path.relative_to(base_dir.absolute())
            break
        except ValueError:
            continue
    
    # 如果不在任何基准目录下，使用文件名+哈希
    if not relative_part:
        import hashlib
        path_hash = hashlib.md5(str(original_path).encode()).hexdigest()[:8]
        relative_part = Path(f"other/{original_path.stem}_{path_hash}")
    
    # 构建缓存路径：data/raw/repaired/<相对路径>.xlsx
    repaired_path = _get_repair_cache_dir() / relative_part.parent / (relative_part.stem + ".xlsx")
    return repaired_path


def auto_repair_xls(xls_path: Path, max_size_mb: float = 50.0) -> Optional[Path]:
    """
    自动修复损坏的.xls文件（支持大文件）
    
    策略：
    1. 检查缓存中是否已有修复版本
    2. 检查文件大小（>50MB可能失败）
    3. 检查Excel COM是否可用
    4. 调用COM修复（增加超时和错误恢复）
    5. 返回修复后的.xlsx路径
    
    Args:
        xls_path: 损坏的.xls文件路径
        max_size_mb: 最大文件大小（MB），超过则警告但仍尝试
    
    Returns:
        Path: 修复后的.xlsx文件路径，失败返回None
    """
    if not xls_path.suffix.lower() == '.xls':
        logger.debug(f"跳过非.xls文件: {xls_path.name}")
        return None
    
    # Step 1: 检查缓存
    repaired_path = get_repaired_path(xls_path)
    if repaired_path.exists():
        logger.info(f"使用修复缓存: {repaired_path.name}")
        return repaired_path
    
    # Step 2: 检查文件大小
    file_size_mb = xls_path.stat().st_size / (1024 * 1024)
    if file_size_mb > max_size_mb:
        logger.warning(f"大文件修复（{file_size_mb:.1f}MB > {max_size_mb}MB），可能失败或耗时较长")
    
    # Step 3: 检查Excel COM
    if not _check_excel_com_available():
        logger.debug("Excel COM不可用，跳过自动修复")
        return None
    
    # Step 4: 执行修复（增强错误处理）
    try:
        logger.info(f"自动修复.xls文件: {xls_path.name} ({file_size_mb:.1f}MB)")
        
        # 确保输出目录存在
        repaired_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 调用COM修复
        import win32com.client
        
        excel = None
        try:
            excel = win32com.client.DispatchEx('Excel.Application')
            excel.Visible = False
            excel.DisplayAlerts = False
            
            # ⭐ 大文件优化：关闭自动计算和事件
            excel.EnableEvents = False
            excel.Calculation = -4135  # xlCalculationManual
            
            # 打开文件（增加错误恢复）
            abs_path = str(xls_path.absolute())
            try:
                workbook = excel.Workbooks.Open(
                    abs_path, 
                    UpdateLinks=False, 
                    ReadOnly=True,
                    CorruptLoad=1  # xlRepairFile = 1 (尝试修复)
                )
            except Exception as open_err:
                logger.warning(f"常规打开失败，尝试修复模式: {open_err}")
                # 尝试修复模式打开
                workbook = excel.Workbooks.Open(
                    abs_path,
                    CorruptLoad=1,  # xlRepairFile
                    ReadOnly=True
                )
            
            # 另存为.xlsx
            abs_output = str(repaired_path.absolute())
            workbook.SaveAs(abs_output, FileFormat=51)  # xlOpenXMLWorkbook = 51
            workbook.Close(False)
            
            logger.info(f"修复成功: {xls_path.name} -> {repaired_path.name} ({repaired_path.stat().st_size / 1024:.1f}KB)")
            return repaired_path
            
        finally:
            if excel:
                try:
                    excel.Calculation = -4105  # xlCalculationAutomatic (恢复)
                    excel.Quit()
                except:
                    pass
    
    except Exception as e:
        logger.error(f"自动修复失败: {xls_path.name} ({type(e).__name__}: {str(e)[:200]})")
        # 清理失败的输出文件
        if repaired_path.exists():
            try:
                repaired_path.unlink()
            except:
                pass
        return None


def batch_repair_all_xls(source_dir: Optional[Path] = None, file_pattern: str = "*.xls"):
    """
    批量修复指定目录下的所有.xls文件
    
    Args:
        source_dir: 源目录
        file_pattern: 文件匹配模式
    
    Returns:
        dict: 修复统计 {success: int, failed: int, cached: int}
    """
    if not _check_excel_com_available():
        logger.warning("Excel COM不可用，批量修复已跳过")
        return {"success": 0, "failed": 0, "cached": 0}
    
    # 如果未指定source_dir，使用默认值（data/raw）
    if source_dir is None:
        from modules.core.path_manager import get_data_raw_dir
        source_dir = get_data_raw_dir()
    
    logger.info(f"开始批量修复: {source_dir} ({file_pattern})")
    
    stats = {"success": 0, "failed": 0, "cached": 0}
    
    for xls_file in source_dir.rglob(file_pattern):
        # 跳过已在repaired目录中的文件
        if "repaired" in str(xls_file):
            continue
        
        repaired_path = get_repaired_path(xls_file)
        
        # 检查缓存
        if repaired_path.exists():
            stats["cached"] += 1
            logger.debug(f"已缓存: {xls_file.name}")
            continue
        
        # 执行修复
        result = auto_repair_xls(xls_file)
        if result:
            stats["success"] += 1
        else:
            stats["failed"] += 1
    
    logger.info(f"批量修复完成: 成功{stats['success']}, 失败{stats['failed']}, 缓存{stats['cached']}")
    return stats


# 启动时检测Excel COM（全局初始化）
_check_excel_com_available()

