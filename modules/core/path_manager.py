#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一路径配置管理工具

v4.12.0新增（Phase 6 - 路径配置管理优化）：
- 统一项目根目录获取
- 统一数据目录路径管理
- 支持环境变量覆盖
- 支持配置文件配置（可选）
- 路径缓存机制（避免重复计算）

注意：path_manager.py 专注于路径管理，与 secrets_manager.py（密钥和环境变量）互补，不冲突
"""

import os
from pathlib import Path
from typing import Optional
from functools import lru_cache

# 路径缓存（避免重复计算）
_project_root: Optional[Path] = None


@lru_cache(maxsize=1)
def get_project_root() -> Path:
    """
    获取项目根目录（统一入口）
    
    优先级：
    1. 环境变量 PROJECT_ROOT
    2. 从当前文件位置向上查找（包含backend和frontend目录的目录）
    3. 当前工作目录（如果包含backend和frontend）
    4. 向上查找当前工作目录的父目录
    
    Returns:
        Path: 项目根目录路径
    """
    global _project_root
    
    # 如果已缓存，直接返回
    if _project_root is not None:
        return _project_root
    
    # 优先级1: 环境变量（容器环境可能没有frontend目录，只检查backend）
    env_root = os.getenv("PROJECT_ROOT")
    if env_root:
        root = Path(env_root).resolve()
        # v4.19.8修复：容器环境可能没有frontend目录，只检查backend即可
        # 这样后端Docker容器（没有frontend目录）也能正确识别项目根目录
        if root.exists() and (root / "backend").exists():
            _project_root = root
            return _project_root
    
    # 优先级2: 从当前文件位置向上查找
    current_file = Path(__file__).resolve()
    for parent in current_file.parents:
        if (parent / "backend").exists() and (parent / "frontend").exists():
            _project_root = parent
            return _project_root
    
    # 优先级3: 当前工作目录
    cwd = Path.cwd()
    if (cwd / "backend").exists() and (cwd / "frontend").exists():
        _project_root = cwd
        return _project_root
    
    # 优先级4: 向上查找当前工作目录的父目录
    for parent in cwd.parents:
        if (parent / "backend").exists() and (parent / "frontend").exists():
            _project_root = parent
            return _project_root
    
    # 如果都找不到，使用当前文件所在目录的父目录（fallback）
    _project_root = current_file.parent.parent
    return _project_root


@lru_cache(maxsize=1)
def get_data_dir() -> Path:
    """
    获取数据目录路径（data/）
    
    优先级：
    1. 环境变量 DATA_DIR
    2. 项目根目录 / data
    
    Returns:
        Path: 数据目录路径
    """
    env_data_dir = os.getenv("DATA_DIR")
    if env_data_dir:
        return Path(env_data_dir).resolve()
    
    return get_project_root() / "data"


@lru_cache(maxsize=1)
def get_data_raw_dir() -> Path:
    """
    获取原始数据目录路径（data/raw）
    
    Returns:
        Path: 原始数据目录路径
    """
    return get_data_dir() / "raw"


@lru_cache(maxsize=1)
def get_data_processed_dir() -> Path:
    """
    获取处理后数据目录路径（data/processed）
    
    Returns:
        Path: 处理后数据目录路径
    """
    return get_data_dir() / "processed"


@lru_cache(maxsize=1)
def get_data_input_dir() -> Path:
    """
    获取输入数据目录路径（data/input）
    
    Returns:
        Path: 输入数据目录路径
    """
    return get_data_dir() / "input"


@lru_cache(maxsize=1)
def get_downloads_dir() -> Path:
    """
    获取下载目录路径（downloads/）
    
    优先级：
    1. 环境变量 DOWNLOADS_DIR
    2. 项目根目录 / downloads
    
    Returns:
        Path: 下载目录路径
    """
    env_downloads_dir = os.getenv("DOWNLOADS_DIR")
    if env_downloads_dir:
        return Path(env_downloads_dir).resolve()
    
    return get_project_root() / "downloads"


@lru_cache(maxsize=1)
def get_output_dir() -> Path:
    """
    获取输出目录路径（temp/outputs/）
    
    优先级：
    1. 环境变量 OUTPUT_DIR
    2. 项目根目录 / temp / outputs
    
    Returns:
        Path: 输出目录路径
    """
    env_output_dir = os.getenv("OUTPUT_DIR")
    if env_output_dir:
        return Path(env_output_dir).resolve()
    
    return get_project_root() / "temp" / "outputs"


@lru_cache(maxsize=1)
def get_temp_dir() -> Path:
    """
    获取临时目录路径（temp/）
    
    优先级：
    1. 环境变量 TEMP_DIR
    2. 项目根目录 / temp
    
    Returns:
        Path: 临时目录路径
    """
    env_temp_dir = os.getenv("TEMP_DIR")
    if env_temp_dir:
        return Path(env_temp_dir).resolve()
    
    return get_project_root() / "temp"


@lru_cache(maxsize=1)
def get_config_dir() -> Path:
    """
    获取配置目录路径（config/）
    
    Returns:
        Path: 配置目录路径
    """
    return get_project_root() / "config"


@lru_cache(maxsize=1)
def get_logs_dir() -> Path:
    """
    获取日志目录路径（temp/logs/）
    
    Returns:
        Path: 日志目录路径
    """
    return get_temp_dir() / "logs"


@lru_cache(maxsize=1)
def get_media_dir() -> Path:
    """
    获取媒体目录路径（temp/media/）
    
    Returns:
        Path: 媒体目录路径
    """
    return get_temp_dir() / "media"


def reset_cache():
    """
    重置路径缓存（用于测试或重新加载配置）
    """
    global _project_root
    _project_root = None
    
    # 清除所有lru_cache
    get_project_root.cache_clear()
    get_data_dir.cache_clear()
    get_data_raw_dir.cache_clear()
    get_data_processed_dir.cache_clear()
    get_data_input_dir.cache_clear()
    get_downloads_dir.cache_clear()
    get_output_dir.cache_clear()
    get_temp_dir.cache_clear()
    get_config_dir.cache_clear()
    get_logs_dir.cache_clear()
    get_media_dir.cache_clear()


# 便捷函数：获取常用路径
def get_path(name: str) -> Path:
    """
    通过名称获取路径（便捷函数）
    
    Args:
        name: 路径名称（如 'data_raw', 'downloads', 'output'）
        
    Returns:
        Path: 对应的路径
        
    Raises:
        ValueError: 如果路径名称不存在
    """
    path_map = {
        'project_root': get_project_root(),
        'data': get_data_dir(),
        'data_raw': get_data_raw_dir(),
        'data_processed': get_data_processed_dir(),
        'data_input': get_data_input_dir(),
        'downloads': get_downloads_dir(),
        'output': get_output_dir(),
        'temp': get_temp_dir(),
        'config': get_config_dir(),
        'logs': get_logs_dir(),
        'media': get_media_dir(),
    }
    
    if name not in path_map:
        raise ValueError(f"未知的路径名称: {name}。可用名称: {', '.join(path_map.keys())}")
    
    return path_map[name]


def to_relative_path(file_path: Path, base_dir: Path = None) -> str:
    """
    将文件路径转换为相对路径（用于数据库存储）
    
    v4.18.0 新增：统一路径存储格式，支持云端部署
    
    Args:
        file_path: 文件路径（Path对象或字符串）
        base_dir: 基准目录（默认为项目根目录）
        
    Returns:
        str: 相对路径字符串（使用正斜杠）
        
    Examples:
        >>> to_relative_path(Path("F:/project/data/raw/file.xlsx"))
        'data/raw/file.xlsx'
        >>> to_relative_path(Path("data/raw/file.xlsx"))
        'data/raw/file.xlsx'
    """
    if base_dir is None:
        base_dir = get_project_root()
    
    file_path = Path(file_path) if isinstance(file_path, str) else file_path
    
    # 如果已经是相对路径，直接标准化
    if not file_path.is_absolute():
        return str(file_path).replace("\\", "/")
    
    # 尝试获取相对路径
    try:
        relative = file_path.relative_to(base_dir)
        return str(relative).replace("\\", "/")
    except ValueError:
        pass
    
    # 如果无法相对于基准目录，尝试从路径中提取关键部分
    path_str = str(file_path).replace("\\", "/")
    
    # 关键路径标识
    key_paths = ["data/raw/", "data/input/", "data/processed/", "downloads/", "temp/outputs/", "temp/"]
    for key_path in key_paths:
        if key_path in path_str:
            idx = path_str.find(key_path)
            return path_str[idx:]
    
    # 如果找不到关键路径，返回文件名（最后的fallback）
    return file_path.name


def to_absolute_path(relative_path: str, base_dir: Path = None) -> Path:
    """
    将相对路径转换为绝对路径（用于文件读取）
    
    v4.18.0 新增：统一路径解析，支持云端部署
    
    Args:
        relative_path: 相对路径字符串
        base_dir: 基准目录（默认为项目根目录）
        
    Returns:
        Path: 绝对路径
        
    Examples:
        >>> to_absolute_path("data/raw/file.xlsx")
        Path('/app/data/raw/file.xlsx')  # 假设项目根目录为/app
    """
    if base_dir is None:
        base_dir = get_project_root()
    
    # 标准化路径分隔符
    normalized_path = relative_path.replace("\\", "/")
    
    # 如果已经是绝对路径
    path_obj = Path(normalized_path)
    if path_obj.is_absolute():
        return path_obj
    
    # 从基准目录解析
    return base_dir / normalized_path
