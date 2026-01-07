#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComponentVersion 表数据迁移脚本

将 file_path 字段从 .yaml 路径迁移为 .py 路径

使用方法:
    # 预览模式（不执行实际更新）
    python scripts/migrate_component_versions_to_python.py --dry-run
    
    # 执行迁移
    python scripts/migrate_component_versions_to_python.py

迁移规则:
    - shopee/login_v1.0.yaml -> shopee/components/login.py
    - tiktok/orders_export_v1.0.yaml -> tiktok/components/orders_export.py
    - miaoshou/date_picker.yaml -> miaoshou/components/date_picker.py
"""

import sys
import re
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.utils.config import get_settings
from modules.core.logger import get_logger

# 获取配置
settings = get_settings()

logger = get_logger(__name__)


def convert_yaml_path_to_python(yaml_path: str) -> str:
    """
    将 YAML 组件路径转换为 Python 组件路径
    
    Args:
        yaml_path: YAML 文件路径，如 "config/collection_components/shopee/login.yaml"
        
    Returns:
        Python 文件路径，如 "modules/platforms/shopee/components/login.py"
    """
    if not yaml_path:
        return yaml_path
    
    # 已经是 .py 文件，不需要转换
    if yaml_path.endswith('.py'):
        return yaml_path
    
    # 不是 .yaml 文件，返回原值
    if not yaml_path.endswith('.yaml') and not yaml_path.endswith('.yml'):
        return yaml_path
    
    # 解析路径
    path_parts = yaml_path.replace('\\', '/').split('/')
    filename = path_parts[-1]
    
    # 移除 .yaml/.yml 扩展名
    base_name = filename.rsplit('.', 1)[0]
    
    # 移除版本号后缀（如 _v1.0, _v2.1.0）
    base_name = re.sub(r'_v\d+(\.\d+)*$', '', base_name)
    
    # 查找平台
    platform = None
    for p in ['shopee', 'tiktok', 'miaoshou', 'amazon']:
        if p in path_parts:
            platform = p
            break
    
    # 移除平台前缀（如 miaoshou_login -> login）
    if platform and base_name.startswith(f'{platform}_'):
        base_name = base_name[len(platform)+1:]  # 移除前缀
    
    if not platform:
        logger.warning(f"Cannot determine platform from path: {yaml_path}")
        return yaml_path
    
    # 构建新路径（使用 modules/platforms 目录结构）
    new_path = f"modules/platforms/{platform}/components/{base_name}.py"
    
    return new_path


def migrate_component_versions(dry_run: bool = True) -> dict:
    """
    迁移 ComponentVersion 表的 file_path 字段
    
    Args:
        dry_run: 如果为 True，只预览不执行实际更新
        
    Returns:
        迁移统计信息
    """
    stats = {
        'total': 0,
        'converted': 0,
        'skipped': 0,
        'failed': 0,
        'conversions': []
    }
    
    # 创建数据库连接
    engine = create_engine(settings.DATABASE_URL)
    
    with Session(engine) as session:
        # 查询所有记录
        result = session.execute(
            text("SELECT id, component_name, version, file_path FROM component_versions ORDER BY id")
        )
        
        rows = result.fetchall()
        stats['total'] = len(rows)
        
        print(f"\n{'='*80}")
        print(f"ComponentVersion Migration - {'DRY RUN' if dry_run else 'EXECUTING'}")
        print(f"{'='*80}")
        print(f"Total records: {stats['total']}")
        print(f"{'='*80}\n")
        
        for row in rows:
            id_, component_name, version, file_path = row
            
            # 转换路径
            new_path = convert_yaml_path_to_python(file_path)
            
            if new_path == file_path:
                # 无需转换
                print(f"[SKIP] {component_name} v{version}: {file_path} (already Python or unchanged)")
                stats['skipped'] += 1
                continue
            
            # 记录转换
            conversion = {
                'id': id_,
                'component_name': component_name,
                'version': version,
                'old_path': file_path,
                'new_path': new_path
            }
            stats['conversions'].append(conversion)
            
            print(f"[CONVERT] {component_name} v{version}:")
            print(f"          Old: {file_path}")
            print(f"          New: {new_path}")
            
            if not dry_run:
                try:
                    session.execute(
                        text("UPDATE component_versions SET file_path = :new_path WHERE id = :id"),
                        {'new_path': new_path, 'id': id_}
                    )
                    stats['converted'] += 1
                except Exception as e:
                    print(f"[ERROR] Failed to update {component_name} v{version}: {e}")
                    stats['failed'] += 1
            else:
                stats['converted'] += 1
        
        # 提交事务
        if not dry_run:
            session.commit()
            print("\n[OK] Changes committed to database")
        
        # 打印统计
        print(f"\n{'='*80}")
        print("Migration Summary")
        print(f"{'='*80}")
        print(f"  Total:     {stats['total']}")
        print(f"  Converted: {stats['converted']}")
        print(f"  Skipped:   {stats['skipped']}")
        print(f"  Failed:    {stats['failed']}")
        
        if dry_run and stats['converted'] > 0:
            print(f"\n[INFO] This was a dry run. To execute, run without --dry-run flag")
        
        print(f"{'='*80}\n")
    
    return stats


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='Migrate ComponentVersion file_path from .yaml to .py'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without executing'
    )
    
    args = parser.parse_args()
    
    try:
        stats = migrate_component_versions(dry_run=args.dry_run)
        
        # 返回码
        if stats['failed'] > 0:
            sys.exit(1)
        sys.exit(0)
        
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

