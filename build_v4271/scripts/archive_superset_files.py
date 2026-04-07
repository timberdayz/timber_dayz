"""
归档Superset相关文件
将Superset相关文件移动到backups/20250201_superset_cleanup/目录
"""
import os
import shutil
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent
BACKUP_DIR = ROOT_DIR / "backups" / "20250201_superset_cleanup"

# 需要归档的文件和目录
FILES_TO_ARCHIVE = [
    "docker-compose.superset.yml",
    "superset_config.py",
]

DIRS_TO_ARCHIVE = {
    "docs": ["*SUPERSET*"],
    "scripts": ["*superset*"],
    "sql": ["*superset*"],
}

SPECIFIC_FILES = [
    "backend/routers/superset_proxy.py",
    "frontend/src/components/SupersetChart.vue",
]

def create_backup_structure():
    """创建备份目录结构"""
    subdirs = ["docs", "scripts", "sql", "backend", "frontend"]
    for subdir in subdirs:
        (BACKUP_DIR / subdir).mkdir(parents=True, exist_ok=True)
    print(f"✓ 创建备份目录: {BACKUP_DIR}")

def archive_files():
    """归档文件"""
    archived_count = 0
    
    # 归档根目录文件
    for filename in FILES_TO_ARCHIVE:
        src = ROOT_DIR / filename
        if src.exists():
            dst = BACKUP_DIR / filename
            shutil.move(str(src), str(dst))
            print(f"✓ 归档: {filename}")
            archived_count += 1
        else:
            print(f"⚠ 未找到: {filename}")
    
    # 归档特定文件
    for filepath in SPECIFIC_FILES:
        src = ROOT_DIR / filepath
        if src.exists():
            # 保持目录结构
            dst = BACKUP_DIR / filepath
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            print(f"✓ 归档: {filepath}")
            archived_count += 1
        else:
            print(f"⚠ 未找到: {filepath}")
    
    # 归档目录中的文件
    for dir_name, patterns in DIRS_TO_ARCHIVE.items():
        src_dir = ROOT_DIR / dir_name
        if not src_dir.exists():
            continue
        
        for pattern in patterns:
            # 使用glob查找匹配文件
            for filepath in src_dir.glob(pattern):
                if filepath.is_file():
                    dst = BACKUP_DIR / dir_name / filepath.name
                    shutil.move(str(filepath), str(dst))
                    print(f"✓ 归档: {dir_name}/{filepath.name}")
                    archived_count += 1
    
    return archived_count

if __name__ == "__main__":
    print("=" * 60)
    print("归档Superset相关文件")
    print("=" * 60)
    
    create_backup_structure()
    count = archive_files()
    
    print("=" * 60)
    print(f"✓ 完成！共归档 {count} 个文件")
    print(f"备份位置: {BACKUP_DIR}")
    print("=" * 60)

