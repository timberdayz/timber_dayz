#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Python 组件批量注册脚本

功能：
1. 扫描 modules/platforms/ 下所有 Python 组件
2. 验证组件元数据完整性
3. 注册到 ComponentVersion 表（已存在则跳过）

使用方式：
    python scripts/register_python_components.py --dry-run     # 预览模式
    python scripts/register_python_components.py               # 执行注册
    python scripts/register_python_components.py --platform shopee  # 指定平台
"""

import argparse
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session

from backend.models.database import SessionLocal
from modules.core.db import ComponentVersion
from modules.core.logger import get_logger

logger = get_logger(__name__)

# 支持的平台
SUPPORTED_PLATFORMS = ["shopee", "tiktok", "miaoshou"]


def get_component_metadata(file_path: Path) -> dict:
    """
    从 Python 组件文件中提取元数据（增强版：导入失败时降级使用文件路径推断）
    
    Returns:
        dict: {
            "platform": str,
            "component_type": str,
            "data_domain": str or None,
            "class_name": str
        }
    """
    # 先尝试从文件路径推断（不依赖导入，作为降级方案）
    parts = file_path.parts
    inferred_platform = None
    inferred_component_type = None
    
    if "platforms" in parts:
        idx = parts.index("platforms")
        if idx + 1 < len(parts):
            inferred_platform = parts[idx + 1]
            component_name = file_path.stem
            
            # 推断组件类型
            if "login" in component_name:
                inferred_component_type = "login"
            elif "navigation" in component_name:
                inferred_component_type = "navigation"
            elif "date_picker" in component_name:
                inferred_component_type = "date_picker"
            elif "export" in component_name:
                inferred_component_type = "export"
            elif "shop_selector" in component_name or "shop_switch" in component_name:
                inferred_component_type = "shop_selector"
            elif "overlay_guard" in component_name:
                inferred_component_type = "overlay_guard"
            elif "metrics_selector" in component_name:
                inferred_component_type = "metrics_selector"
            elif "analytics" in component_name:
                inferred_component_type = "analytics"
            else:
                inferred_component_type = "other"
    
    # 尝试加载模块获取更准确的元数据
    try:
        spec = importlib.util.spec_from_file_location("component", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # 查找组件类
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and hasattr(attr, "platform"):
                # 读取类属性（覆盖推断值）
                platform = getattr(attr, "platform", inferred_platform)
                component_type = getattr(attr, "component_type", inferred_component_type)
                data_domain = getattr(attr, "data_domain", None)
                
                return {
                    "platform": platform,
                    "component_type": component_type,
                    "data_domain": data_domain,
                    "class_name": attr_name
                }
    except Exception as e:
        # 导入失败，使用推断值（降级方案）
        logger.debug(f"[DEBUG] 无法导入 {file_path}，使用推断元数据: {e}")
    
    # 如果推断值可用，返回推断的元数据
    if inferred_platform and inferred_component_type:
        return {
            "platform": inferred_platform,
            "component_type": inferred_component_type,
            "data_domain": None,
            "class_name": None
        }
    
    return None


def get_component_name(file_path: Path, metadata: dict) -> str:
    """
    生成组件名称
    
    格式: {platform}/{component_name}
    例如: shopee/login, tiktok/orders_export
    """
    platform = metadata.get("platform", "unknown")
    component_name = file_path.stem
    return f"{platform}/{component_name}"


def get_python_components(platforms: list = None) -> list:
    """
    扫描所有 Python 组件
    
    Returns:
        list: [{
            "file_path": Path,
            "relative_path": str,
            "metadata": dict,
            "component_name": str
        }]
    """
    components = []
    platforms_dir = project_root / "modules" / "platforms"
    
    if not platforms_dir.exists():
        logger.error(f"[ERROR] 平台目录不存在: {platforms_dir}")
        return components
    
    target_platforms = platforms if platforms else SUPPORTED_PLATFORMS
    
    for platform in target_platforms:
        platform_dir = platforms_dir / platform / "components"
        
        if not platform_dir.exists():
            logger.warning(f"[WARN] 平台组件目录不存在: {platform_dir}")
            continue
        
        for py_file in platform_dir.glob("*.py"):
            # 跳过 __init__.py
            if py_file.name.startswith("__"):
                continue
            
            # v4.8.0: 排除配置类文件（不是组件）
            if py_file.name.endswith("_config.py"):
                continue
            
            # v4.8.0: 排除工具类文件
            if py_file.name in ("overlay_guard.py",):
                continue
            
            # 获取元数据
            metadata = get_component_metadata(py_file)
            if metadata is None:
                logger.warning(f"[WARN] 无法获取组件元数据: {py_file}")
                continue
            
            # 生成相对路径
            relative_path = py_file.relative_to(project_root)
            
            # 生成组件名称
            component_name = get_component_name(py_file, metadata)
            
            components.append({
                "file_path": py_file,
                "relative_path": str(relative_path).replace("\\", "/"),
                "metadata": metadata,
                "component_name": component_name
            })
    
    return components


def register_components(
    db: Session, 
    components: list, 
    dry_run: bool = False
) -> dict:
    """
    注册组件到 ComponentVersion 表
    
    规则：
    - 检查 component_name + file_path 是否已存在
    - 已存在则跳过
    - 新组件注册为 1.0.0 版本
    """
    result = {
        "registered": [],
        "skipped": [],
        "errors": []
    }
    
    for component in components:
        try:
            component_name = component["component_name"]
            file_path = component["relative_path"]
            metadata = component["metadata"]
            
            # 检查是否已存在（基于 component_name + version，匹配数据库唯一约束）
            version = "1.0.0"
            existing = db.query(ComponentVersion).filter(
                ComponentVersion.component_name == component_name,
                ComponentVersion.version == version
            ).first()
            
            if existing:
                if dry_run:
                    logger.info(f"[DRY-RUN] 跳过（已存在）: {component_name} v{version}")
                else:
                    logger.info(f"[SKIP] 已存在: {component_name} v{version}")
                result["skipped"].append({
                    "component_name": component_name,
                    "file_path": file_path,
                    "version": version,
                    "existing_id": existing.id
                })
                continue
            
            # 注册新组件
            if dry_run:
                logger.info(f"[DRY-RUN] 将注册: {component_name} v{version} -> {file_path}")
                result["registered"].append({
                    "component_name": component_name,
                    "file_path": file_path,
                    "version": version
                })
            else:
                new_version = ComponentVersion(
                    component_name=component_name,
                    version=version,
                    file_path=file_path,
                    description=f"Python component: {metadata.get('component_type', 'unknown')}",
                    is_stable=True,  # Python 组件默认为稳定版本
                    is_active=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(new_version)
                logger.info(f"[OK] 已注册: {component_name} v{version}")
                result["registered"].append({
                    "component_name": component_name,
                    "file_path": file_path,
                    "version": version
                })
        
        except Exception as e:
            logger.error(f"[ERROR] 注册组件失败 {component['component_name']}: {e}")
            result["errors"].append({
                "component_name": component["component_name"],
                "error": str(e)
            })
    
    if not dry_run:
        db.commit()
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Python 组件批量注册脚本")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，不实际执行注册"
    )
    parser.add_argument(
        "--platform",
        type=str,
        choices=SUPPORTED_PLATFORMS,
        help="指定平台（默认所有平台）"
    )
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("Python 组件批量注册脚本")
    logger.info("=" * 60)
    
    if args.dry_run:
        logger.info("[MODE] 预览模式 - 不会实际执行任何操作")
    
    # 1. 扫描组件
    logger.info("")
    logger.info("[STEP 1] 扫描 Python 组件")
    logger.info("-" * 40)
    
    platforms = [args.platform] if args.platform else None
    components = get_python_components(platforms)
    
    logger.info(f"[INFO] 找到 {len(components)} 个 Python 组件")
    
    if not components:
        logger.info("[DONE] 没有组件需要注册")
        return 0
    
    # 按平台分组显示
    platform_counts = {}
    for comp in components:
        platform = comp["metadata"].get("platform", "unknown")
        platform_counts[platform] = platform_counts.get(platform, 0) + 1
    
    for platform, count in sorted(platform_counts.items()):
        logger.info(f"  - {platform}: {count} 个组件")
    
    # 2. 注册组件
    logger.info("")
    logger.info("[STEP 2] 注册组件到数据库")
    logger.info("-" * 40)
    
    db = SessionLocal()
    try:
        result = register_components(db, components, args.dry_run)
    finally:
        db.close()
    
    # 3. 输出统计
    logger.info("")
    logger.info("=" * 60)
    logger.info("注册统计")
    logger.info("=" * 60)
    logger.info(f"  已注册: {len(result['registered'])}")
    logger.info(f"  已跳过: {len(result['skipped'])}")
    logger.info(f"  错误: {len(result['errors'])}")
    
    if args.dry_run:
        logger.info("")
        logger.info("[NOTE] 这是预览模式，实际运行请移除 --dry-run 参数")
    
    # 返回退出码
    if len(result["errors"]) > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

