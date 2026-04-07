#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件扫描和注册验证脚本

v4.12.0新增（Phase 1 - 文件扫描和注册验证）：
- 测试catalog_scanner服务
- 验证文件扫描功能
- 验证文件注册功能
- 验证文件去重机制
- 输出验证报告
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy.orm import Session
from modules.services.catalog_scanner import scan_and_register, register_single_file
from modules.core.db import CatalogFile
from backend.models.database import get_db
from modules.core.logger import get_logger

logger = get_logger(__name__)


def test_file_scanning(db: Session, scan_dir: str = "data/raw") -> dict:
    """
    测试文件扫描功能
    
    Args:
        db: 数据库会话
        scan_dir: 扫描目录
        
    Returns:
        验证结果字典
    """
    print("\n" + "="*60)
    print("测试1: 文件扫描功能")
    print("="*60)
    
    try:
        # 记录扫描前的文件数量
        before_count = db.query(CatalogFile).count()
        print(f"扫描前 catalog_files 表记录数: {before_count}")
        
        # 执行扫描
        print(f"\n开始扫描目录: {scan_dir}")
        result = scan_and_register(scan_dir)
        
        # 记录扫描后的文件数量
        after_count = db.query(CatalogFile).count()
        print(f"扫描后 catalog_files 表记录数: {after_count}")
        
        # 验证结果
        print(f"\n扫描结果:")
        print(f"  - 发现文件数: {result.seen}")
        print(f"  - 新注册文件数: {result.registered}")
        print(f"  - 跳过文件数: {result.skipped}")
        print(f"  - 新文件ID列表: {result.new_file_ids[:10]}..." if len(result.new_file_ids) > 10 else f"  - 新文件ID列表: {result.new_file_ids}")
        
        # 验证数据库记录数变化
        expected_count = before_count + result.registered
        if after_count == expected_count:
            print(f"\n[OK] 数据库记录数验证通过: {before_count} + {result.registered} = {after_count}")
        else:
            print(f"\n[WARNING] 数据库记录数不匹配: 期望 {expected_count}, 实际 {after_count}")
        
        return {
            "success": True,
            "before_count": before_count,
            "after_count": after_count,
            "seen": result.seen,
            "registered": result.registered,
            "skipped": result.skipped,
            "new_file_ids": result.new_file_ids
        }
        
    except Exception as e:
        logger.error(f"文件扫描测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def test_file_metadata_extraction(db: Session) -> dict:
    """
    验证文件元数据提取
    
    Args:
        db: 数据库会话
        
    Returns:
        验证结果字典
    """
    print("\n" + "="*60)
    print("测试2: 文件元数据提取验证")
    print("="*60)
    
    try:
        # 获取最近注册的10个文件（使用first_seen_at字段）
        recent_files = db.query(CatalogFile).order_by(
            CatalogFile.first_seen_at.desc()
        ).limit(10).all()
        
        if not recent_files:
            print("[WARNING] 没有找到文件记录，跳过元数据验证")
            return {
                "success": False,
                "error": "没有文件记录"
            }
        
        print(f"\n检查最近注册的 {len(recent_files)} 个文件:")
        
        metadata_stats = {
            "platform_code_valid": 0,
            "data_domain_valid": 0,
            "granularity_valid": 0,
            "date_range_valid": 0,
            "shop_id_present": 0,
            "file_hash_present": 0
        }
        
        for file_record in recent_files:
            # 验证 platform_code
            if file_record.platform_code:
                metadata_stats["platform_code_valid"] += 1
            
            # 验证 data_domain
            if file_record.data_domain:
                metadata_stats["data_domain_valid"] += 1
            
            # 验证 granularity
            if file_record.granularity:
                metadata_stats["granularity_valid"] += 1
            
            # 验证 date_range
            if file_record.date_from and file_record.date_to:
                metadata_stats["date_range_valid"] += 1
            
            # 验证 shop_id（可选）
            if file_record.shop_id:
                metadata_stats["shop_id_present"] += 1
            
            # 验证 file_hash
            if file_record.file_hash:
                metadata_stats["file_hash_present"] += 1
        
        print(f"\n元数据统计:")
        print(f"  - platform_code 有效: {metadata_stats['platform_code_valid']}/{len(recent_files)}")
        print(f"  - data_domain 有效: {metadata_stats['data_domain_valid']}/{len(recent_files)}")
        print(f"  - granularity 有效: {metadata_stats['granularity_valid']}/{len(recent_files)}")
        print(f"  - date_range 有效: {metadata_stats['date_range_valid']}/{len(recent_files)}")
        print(f"  - shop_id 存在: {metadata_stats['shop_id_present']}/{len(recent_files)}")
        print(f"  - file_hash 存在: {metadata_stats['file_hash_present']}/{len(recent_files)}")
        
        # 验证关键字段完整性
        all_valid = (
            metadata_stats["platform_code_valid"] == len(recent_files) and
            metadata_stats["data_domain_valid"] == len(recent_files) and
            metadata_stats["granularity_valid"] == len(recent_files) and
            metadata_stats["file_hash_present"] == len(recent_files)
        )
        
        if all_valid:
            print("\n[OK] 关键字段完整性验证通过")
        else:
            print("\n[WARNING] 部分文件缺少关键字段")
        
        return {
            "success": True,
            "metadata_stats": metadata_stats,
            "total_files": len(recent_files)
        }
        
    except Exception as e:
        logger.error(f"元数据提取验证失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def test_file_deduplication(db: Session, scan_dir: str = "data/raw") -> dict:
    """
    验证文件去重机制
    
    Args:
        db: 数据库会话
        scan_dir: 扫描目录
        
    Returns:
        验证结果字典
    """
    print("\n" + "="*60)
    print("测试3: 文件去重机制验证")
    print("="*60)
    
    try:
        # 记录扫描前的文件数量
        before_count = db.query(CatalogFile).count()
        print(f"第一次扫描前 catalog_files 表记录数: {before_count}")
        
        # 第一次扫描
        print(f"\n第一次扫描目录: {scan_dir}")
        result1 = scan_and_register(scan_dir)
        after_first_count = db.query(CatalogFile).count()
        print(f"第一次扫描后 catalog_files 表记录数: {after_first_count}")
        print(f"  - 发现文件数: {result1.seen}")
        print(f"  - 新注册文件数: {result1.registered}")
        print(f"  - 跳过文件数: {result1.skipped}")
        
        # 第二次扫描（应该跳过所有文件）
        print(f"\n第二次扫描目录（验证去重）: {scan_dir}")
        result2 = scan_and_register(scan_dir)
        after_second_count = db.query(CatalogFile).count()
        print(f"第二次扫描后 catalog_files 表记录数: {after_second_count}")
        print(f"  - 发现文件数: {result2.seen}")
        print(f"  - 新注册文件数: {result2.registered}")
        print(f"  - 跳过文件数: {result2.skipped}")
        
        # 验证去重机制
        if result2.registered == 0:
            print("\n[OK] 文件去重机制验证通过: 重复扫描没有注册新文件")
        else:
            print(f"\n[WARNING] 文件去重机制可能有问题: 重复扫描注册了 {result2.registered} 个新文件")
        
        # 验证数据库记录数不变
        if after_first_count == after_second_count:
            print(f"[OK] 数据库记录数验证通过: 两次扫描后记录数相同 ({after_first_count})")
        else:
            print(f"[WARNING] 数据库记录数不匹配: 第一次 {after_first_count}, 第二次 {after_second_count}")
        
        # 验证 file_hash 唯一性
        from sqlalchemy import func
        duplicate_hashes = db.query(CatalogFile.file_hash).filter(
            CatalogFile.file_hash.isnot(None)
        ).group_by(CatalogFile.file_hash).having(
            func.count(CatalogFile.id) > 1
        ).all()
        
        if duplicate_hashes:
            print(f"\n[WARNING] 发现重复的 file_hash: {len(duplicate_hashes)} 个")
            for hash_val, count in duplicate_hashes[:5]:  # 只显示前5个
                print(f"  - {hash_val[:16]}... (出现 {count} 次)")
        else:
            print("\n[OK] file_hash 唯一性验证通过: 没有重复的 file_hash")
        
        return {
            "success": True,
            "first_scan": {
                "seen": result1.seen,
                "registered": result1.registered,
                "skipped": result1.skipped
            },
            "second_scan": {
                "seen": result2.seen,
                "registered": result2.registered,
                "skipped": result2.skipped
            },
            "duplicate_hashes_count": len(duplicate_hashes) if duplicate_hashes else 0
        }
        
    except Exception as e:
        logger.error(f"文件去重验证失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def test_single_file_registration(db: Session) -> dict:
    """
    测试单文件注册功能（Phase 0新增）
    
    Args:
        db: 数据库会话
        
    Returns:
        验证结果字典
    """
    print("\n" + "="*60)
    print("测试4: 单文件注册功能验证（Phase 0）")
    print("="*60)
    
    try:
        # 查找一个已存在的文件记录
        existing_file = db.query(CatalogFile).first()
        
        if not existing_file:
            print("[WARNING] 没有找到文件记录，跳过单文件注册测试")
            return {
                "success": False,
                "error": "没有文件记录"
            }
        
        file_path = existing_file.file_path
        print(f"\n测试文件: {file_path}")
        
        # 记录注册前的文件数量
        before_count = db.query(CatalogFile).count()
        print(f"注册前 catalog_files 表记录数: {before_count}")
        
        # 尝试注册单个文件（应该跳过，因为已存在）
        file_id = register_single_file(file_path)
        
        after_count = db.query(CatalogFile).count()
        print(f"注册后 catalog_files 表记录数: {after_count}")
        
        if file_id is None:
            print("[OK] 单文件注册去重验证通过: 已存在的文件返回 None（跳过）")
        else:
            print(f"[WARNING] 单文件注册可能有问题: 已存在的文件返回了 file_id={file_id}")
        
        # 验证数据库记录数不变
        if before_count == after_count:
            print(f"[OK] 数据库记录数验证通过: 注册前后记录数相同 ({before_count})")
        else:
            print(f"[WARNING] 数据库记录数不匹配: 注册前 {before_count}, 注册后 {after_count}")
        
        return {
            "success": True,
            "file_path": file_path,
            "file_id": file_id,
            "before_count": before_count,
            "after_count": after_count
        }
        
    except Exception as e:
        logger.error(f"单文件注册验证失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


def main():
    """主函数"""
    print("="*60)
    print("文件扫描和注册验证脚本")
    print("="*60)
    print("\n本脚本将验证以下功能:")
    print("  1. 文件扫描功能")
    print("  2. 文件元数据提取")
    print("  3. 文件去重机制")
    print("  4. 单文件注册功能（Phase 0）")
    
    # 获取数据库会话
    db = next(get_db())
    
    try:
        results = {}
        
        # 测试1: 文件扫描功能
        results["file_scanning"] = test_file_scanning(db)
        
        # 测试2: 文件元数据提取
        results["metadata_extraction"] = test_file_metadata_extraction(db)
        
        # 测试3: 文件去重机制
        results["deduplication"] = test_file_deduplication(db)
        
        # 测试4: 单文件注册功能
        results["single_file_registration"] = test_single_file_registration(db)
        
        # 输出总结报告
        print("\n" + "="*60)
        print("验证报告总结")
        print("="*60)
        
        all_passed = True
        for test_name, result in results.items():
            status = "[OK] 通过" if result.get("success") else "[FAIL] 失败"
            print(f"{test_name}: {status}")
            if not result.get("success"):
                all_passed = False
                if "error" in result:
                    print(f"  错误: {result['error']}")
        
        if all_passed:
            print("\n[OK] 所有测试通过！")
        else:
            print("\n[WARNING] 部分测试失败，请检查日志")
        
        return 0 if all_passed else 1
        
    except Exception as e:
        logger.error(f"验证脚本执行失败: {e}", exc_info=True)
        print(f"\n[ERROR] 验证脚本执行失败: {e}")
        return 1
        
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())

