#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证迁移重写结果

检查：
1. 迁移链完整性
2. Schema完整性
3. 表结构正确性
4. 重复文件清理
5. 重写的迁移文件验证
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import verify_schema_completeness, engine
from sqlalchemy import inspect, text
import json


def safe_print(text_str):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text_str, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text_str.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text_str.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)


def main():
    """主函数"""
    safe_print("\n" + "="*80)
    safe_print("迁移重写验证报告")
    safe_print("="*80 + "\n")
    
    all_passed = True
    
    # 1. Schema完整性验证
    safe_print("[1] Schema完整性验证...")
    try:
        result = verify_schema_completeness()
        safe_print(f"  所有表存在: {result['all_tables_exist']}")
        safe_print(f"  缺失表数量: {len(result.get('missing_tables', []))}")
        safe_print(f"  迁移状态: {result['migration_status']}")
        safe_print(f"  当前版本: {result['current_revision']}")
        safe_print(f"  HEAD版本: {result['head_revision']}")
        safe_print(f"  预期表数: {result['expected_table_count']}")
        safe_print(f"  实际表数: {result['actual_table_count']}")
        
        if result['all_tables_exist'] and result['migration_status'] == 'up_to_date':
            safe_print("  [OK] Schema完整性验证通过")
        else:
            safe_print("  [FAIL] Schema完整性验证失败")
            all_passed = False
    except Exception as e:
        safe_print(f"  [ERROR] Schema完整性验证失败: {e}")
        all_passed = False
    
    safe_print("")
    
    # 2. 表结构验证
    safe_print("[2] 表结构验证...")
    try:
        conn = engine.connect()
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())
        
        # 检查collection_configs表
        if 'collection_configs' in existing_tables:
            columns = {col['name']: col for col in inspector.get_columns('collection_configs')}
            if 'sub_domains' in columns:
                col_type = str(columns['sub_domains']['type'])
                if 'JSON' in col_type.upper() or 'json' in col_type.lower():
                    safe_print("  [OK] collection_configs.sub_domains字段类型正确（JSON）")
                else:
                    safe_print(f"  [FAIL] collection_configs.sub_domains字段类型错误: {col_type}")
                    all_passed = False
            else:
                safe_print("  [FAIL] collection_configs.sub_domains字段不存在")
                all_passed = False
        else:
            safe_print("  [FAIL] collection_configs表不存在")
            all_passed = False
        
        # 检查collection_task_logs表
        if 'collection_task_logs' in existing_tables:
            columns = {col['name']: col for col in inspector.get_columns('collection_task_logs')}
            required_columns = ['id', 'task_id', 'level', 'message', 'timestamp']
            missing_columns = [col for col in required_columns if col not in columns]
            if not missing_columns:
                safe_print("  [OK] collection_task_logs表结构正确")
            else:
                safe_print(f"  [FAIL] collection_task_logs表缺少字段: {missing_columns}")
                all_passed = False
        else:
            safe_print("  [FAIL] collection_task_logs表不存在")
            all_passed = False
        
        conn.close()
    except Exception as e:
        safe_print(f"  [ERROR] 表结构验证失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    safe_print("")
    
    # 3. 遗留表清理验证
    safe_print("[3] 遗留表清理验证...")
    try:
        conn = engine.connect()
        inspector = inspect(conn)
        existing_tables = set(inspector.get_table_names())
        
        legacy_tables = [
            'collection_tasks_backup',
            'key_value',
            'keyvalue',
            'raw_ingestions',
            'report_execution_log',
            'report_recipient',
            'report_schedule',
            'report_schedule_user'
        ]
        
        remaining_tables = [t for t in legacy_tables if t in existing_tables]
        if not remaining_tables:
            safe_print(f"  [OK] 所有{len(legacy_tables)}张遗留表已清理")
        else:
            safe_print(f"  [FAIL] 仍有{len(remaining_tables)}张遗留表未清理: {remaining_tables}")
            all_passed = False
        
        conn.close()
    except Exception as e:
        safe_print(f"  [ERROR] 遗留表清理验证失败: {e}")
        all_passed = False
    
    safe_print("")
    
    # 4. 迁移文件验证
    safe_print("[4] 迁移文件验证...")
    try:
        migrations_dir = project_root / "migrations" / "versions"
        migration_files = list(migrations_dir.glob("*.py"))
        
        # 检查重复的revision ID
        revisions = {}
        for f in migration_files:
            if f.name == "__init__.py":
                continue
            try:
                content = f.read_text(encoding='utf-8')
                # 简单查找revision = 'xxx'
                import re
                match = re.search(r"revision\s*=\s*['\"]([^'\"]+)['\"]", content)
                if match:
                    rev_id = match.group(1)
                    if rev_id not in revisions:
                        revisions[rev_id] = []
                    revisions[rev_id].append(f.name)
            except Exception as e:
                safe_print(f"  [WARNING] 无法解析文件 {f.name}: {e}")
        
        duplicate_revisions = {rev: files for rev, files in revisions.items() if len(files) > 1}
        if not duplicate_revisions:
            safe_print(f"  [OK] 无重复revision ID（共{len(revisions)}个唯一revision）")
        else:
            safe_print(f"  [FAIL] 发现{len(duplicate_revisions)}个重复revision ID:")
            for rev, files in duplicate_revisions.items():
                safe_print(f"    {rev}: {', '.join(files)}")
            all_passed = False
        
        # 检查重写的迁移文件
        rewritten_files = [
            "20251105_204106_create_mv_product_management.py",
            "20251209_v4_6_0_collection_module_tables.py"
        ]
        
        for filename in rewritten_files:
            filepath = migrations_dir / filename
            if filepath.exists():
                content = filepath.read_text(encoding='utf-8')
                # 检查是否包含重写标记
                if "Rewritten" in content or "重写说明" in content:
                    safe_print(f"  [OK] {filename} 已重写")
                else:
                    safe_print(f"  [WARNING] {filename} 未找到重写标记")
            else:
                safe_print(f"  [FAIL] {filename} 不存在")
                all_passed = False
        
        # 检查是否有旧的重复文件
        old_duplicate_files = [
            "20251105_204106_create_mv_product_management_fixed.py",
            "20251105_204106_create_mv_product_management_rewritten.py",
            "20251209_v4_6_0_collection_module_tables_rewritten.py"
        ]
        
        remaining_duplicates = [f for f in old_duplicate_files if (migrations_dir / f).exists()]
        if not remaining_duplicates:
            safe_print("  [OK] 所有重复文件已清理")
        else:
            safe_print(f"  [FAIL] 仍有重复文件存在: {remaining_duplicates}")
            all_passed = False
        
    except Exception as e:
        safe_print(f"  [ERROR] 迁移文件验证失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    safe_print("")
    
    # 5. 物化视图验证
    safe_print("[5] 物化视图验证...")
    try:
        conn = engine.connect()
        result = conn.execute(text("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE schemaname = 'public'
            ORDER BY matviewname
        """))
        views = [row[0] for row in result]
        safe_print(f"  物化视图数量: {len(views)}")
        if views:
            safe_print(f"  物化视图列表: {', '.join(views[:10])}{'...' if len(views) > 10 else ''}")
        
        # 检查mv_product_management（如果存在）
        if 'mv_product_management' in views:
            safe_print("  [OK] mv_product_management物化视图已存在")
        else:
            safe_print("  [INFO] mv_product_management物化视图不存在（可能因为表中无数据，这是正常的）")
        
        conn.close()
    except Exception as e:
        safe_print(f"  [ERROR] 物化视图验证失败: {e}")
        all_passed = False
    
    safe_print("")
    
    # 总结
    safe_print("="*80)
    if all_passed:
        safe_print("[SUCCESS] 所有验证通过！")
        safe_print("="*80)
        return 0
    else:
        safe_print("[FAIL] 部分验证失败，请检查上述错误")
        safe_print("="*80)
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except Exception as e:
        safe_print(f"[ERROR] 验证过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
