#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
组件迁移脚本 - 从旧项目迁移已验证的Python组件到新项目临时目录

使用方法:
    python migrate_components.py
"""

import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

# 设置输出编码为UTF-8（Windows兼容）
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

# 项目路径配置
OLD_PROJECT_ROOT = Path(r"F:\Vscode\python_programme\AI_code\xihong_erp - collect")
NEW_PROJECT_ROOT = Path(r"F:\Vscode\python_programme\AI_code\xihong_erp")
MIGRATION_TEMP_DIR = NEW_PROJECT_ROOT / "migration_temp" / "legacy_components"

# 需要迁移的文件和目录
MIGRATION_PATHS = [
    # 基础适配器
    ("modules/platforms/adapter_base.py", "modules/platforms/adapter_base.py"),
    
    # Shopee 平台
    ("modules/platforms/shopee/adapter.py", "modules/platforms/shopee/adapter.py"),
    ("modules/platforms/shopee/components/", "modules/platforms/shopee/components/"),
    
    # TikTok 平台
    ("modules/platforms/tiktok/adapter.py", "modules/platforms/tiktok/adapter.py"),
    ("modules/platforms/tiktok/components/", "modules/platforms/tiktok/components/"),
    
    # Miaoshou 平台
    ("modules/platforms/miaoshou/adapter.py", "modules/platforms/miaoshou/adapter.py"),
    ("modules/platforms/miaoshou/components/", "modules/platforms/miaoshou/components/"),
]


def should_skip_file(file_path: Path) -> bool:
    """判断是否应该跳过该文件"""
    skip_patterns = [
        "__pycache__",
        ".pyc",
        ".pyo",
        ".pyd",
        ".so",
        ".egg",
        ".egg-info",
        ".dist-info",
        ".git",
        ".idea",
        ".vscode",
        ".DS_Store",
        "*.swp",
        "*.swo",
        "*~",
    ]
    
    file_str = str(file_path)
    return any(pattern in file_str for pattern in skip_patterns)


def copy_file_or_dir(src: Path, dst: Path, dry_run: bool = False) -> tuple[bool, str]:
    """复制文件或目录"""
    if not src.exists():
        return False, f"源文件不存在: {src}"
    
    try:
        if src.is_file():
            # 复制单个文件
            if dry_run:
                return True, f"[DRY RUN] 将复制文件: {src} -> {dst}"
            
            # 确保目标目录存在
            dst.parent.mkdir(parents=True, exist_ok=True)
            
            # 复制文件
            shutil.copy2(src, dst)
            return True, f"已复制文件: {src.name}"
            
        elif src.is_dir():
            # 复制整个目录
            if dry_run:
                return True, f"[DRY RUN] 将复制目录: {src} -> {dst}"
            
            # 确保目标目录存在
            dst.mkdir(parents=True, exist_ok=True)
            
            # 遍历目录中的所有文件
            copied_count = 0
            for root, dirs, files in os.walk(src):
                # 过滤掉需要跳过的目录
                dirs[:] = [d for d in dirs if not should_skip_file(Path(root) / d)]
                
                for file in files:
                    src_file = Path(root) / file
                    
                    # 跳过不需要的文件
                    if should_skip_file(src_file):
                        continue
                    
                    # 计算相对路径
                    rel_path = src_file.relative_to(src)
                    dst_file = dst / rel_path
                    
                    # 确保目标目录存在
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # 复制文件
                    shutil.copy2(src_file, dst_file)
                    copied_count += 1
            
            return True, f"已复制目录: {copied_count} 个文件"
        
        else:
            return False, f"未知类型: {src}"
            
    except Exception as e:
        return False, f"复制失败: {str(e)}"


def main():
    """主函数"""
    print("=" * 80)
    print("组件迁移脚本 - 从旧项目迁移已验证的Python组件")
    print("=" * 80)
    print(f"旧项目路径: {OLD_PROJECT_ROOT}")
    print(f"新项目路径: {NEW_PROJECT_ROOT}")
    print(f"迁移目标目录: {MIGRATION_TEMP_DIR}")
    print("=" * 80)
    print()
    
    # 检查旧项目路径
    if not OLD_PROJECT_ROOT.exists():
        print(f"[ERROR] 旧项目路径不存在: {OLD_PROJECT_ROOT}")
        return
    
    # 检查新项目路径
    if not NEW_PROJECT_ROOT.exists():
        print(f"[ERROR] 新项目路径不存在: {NEW_PROJECT_ROOT}")
        return
    
    # 先执行一次dry run
    print("\n" + "=" * 80)
    print("步骤 1/2: 执行预览 (DRY RUN)")
    print("=" * 80)
    
    dry_run_results = []
    for old_rel_path, new_rel_path in MIGRATION_PATHS:
        src = OLD_PROJECT_ROOT / old_rel_path
        dst = MIGRATION_TEMP_DIR / new_rel_path
        
        success, message = copy_file_or_dir(src, dst, dry_run=True)
        dry_run_results.append((old_rel_path, success, message))
        
        status = "✅" if success else "❌"
        print(f"{status} {old_rel_path}: {message}")
    
    # 执行实际迁移
    print("\n" + "=" * 80)
    print("步骤 2/2: 执行实际迁移")
    print("=" * 80)
    
    migration_results = []
    total_files = 0
    
    for old_rel_path, new_rel_path in MIGRATION_PATHS:
        src = OLD_PROJECT_ROOT / old_rel_path
        dst = MIGRATION_TEMP_DIR / new_rel_path
        
        success, message = copy_file_or_dir(src, dst, dry_run=False)
        migration_results.append((old_rel_path, success, message))
        
        status = "✅" if success else "❌"
        print(f"{status} {old_rel_path}: {message}")
        
        if success and "个文件" in message:
            # 提取文件数量
            try:
                count = int(message.split("个文件")[0].split()[-1])
                total_files += count
            except:
                pass
    
    # 生成迁移报告
    print("\n" + "=" * 80)
    print("迁移完成报告")
    print("=" * 80)
    print(f"[OK] 成功: {sum(1 for _, s, _ in migration_results if s)} 项")
    print(f"[FAIL] 失败: {sum(1 for _, s, _ in migration_results if not s)} 项")
    print(f"[INFO] 总文件数: {total_files}")
    print(f"[INFO] 目标目录: {MIGRATION_TEMP_DIR}")
    print()
    
    # 列出失败的项目
    failed = [(path, msg) for path, s, msg in migration_results if not s]
    if failed:
        print("失败的迁移项:")
        for path, msg in failed:
            print(f"  [FAIL] {path}: {msg}")
        print()
    
    print("[OK] 迁移完成！")
    print(f"[INFO] 说明文档将创建在: {MIGRATION_TEMP_DIR / 'README.md'}")


if __name__ == "__main__":
    main()

