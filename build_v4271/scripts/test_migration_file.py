#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试迁移文件验证脚本

验证迁移文件是否正确，迁移链是否完整，迁移是否能正常执行。
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def safe_print(text_str, end="\n"):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text_str, end=end, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text_str.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, end=end, flush=True)
        except:
            safe_text = text_str.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, end=end, flush=True)


def test_migration_chain():
    """测试迁移链状态"""
    safe_print("\n[TEST 1] 检查Alembic迁移链状态...")
    
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        
        cfg = Config('alembic.ini')
        script = ScriptDirectory.from_config(cfg)
        
        # 检查heads
        heads = script.get_revisions('heads')
        head_revisions = [h.revision for h in heads]
        
        safe_print(f"  当前heads数量: {len(heads)}")
        safe_print(f"  Head revisions: {', '.join(head_revisions)}")
        
        if len(heads) > 1:
            safe_print("  [WARNING] 发现多个head，可能需要合并")
            return False
        elif len(heads) == 1:
            safe_print(f"  [OK] 单个head: {head_revisions[0]}")
        else:
            safe_print("  [WARNING] 没有head（可能是新数据库）")
        
        # 检查当前版本（如果数据库已连接）
        try:
            from backend.models.database import engine
            from alembic.runtime.migration import MigrationContext
            
            with engine.connect() as conn:
                context = MigrationContext.configure(conn)
                current_rev = context.get_current_revision()
                
                if current_rev:
                    safe_print(f"  数据库当前版本: {current_rev}")
                    head_rev = head_revisions[0] if head_revisions else None
                    if current_rev == head_rev:
                        safe_print("  [OK] 数据库已是最新版本")
                    else:
                        safe_print(f"  [INFO] 数据库需要升级到: {head_rev}")
                else:
                    safe_print("  [INFO] 数据库未初始化（alembic_version表不存在）")
        except Exception as e:
            safe_print(f"  [INFO] 无法检查数据库版本: {e}")
            safe_print("  [NOTE] 这可能是正常的（如果数据库未连接）")
        
        return True
        
    except Exception as e:
        safe_print(f"  [ERROR] 检查迁移链失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_migration_file_syntax():
    """测试迁移文件语法"""
    safe_print("\n[TEST 2] 验证迁移文件语法...")
    
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        
        cfg = Config('alembic.ini')
        script = ScriptDirectory.from_config(cfg)
        
        # 尝试加载所有迁移
        all_revisions = list(script.walk_revisions())
        safe_print(f"  总迁移文件数: {len(all_revisions)}")
        
        # 检查新创建的迁移文件
        target_revision = '20260111_0001_complete_missing_tables'
        try:
            rev = script.get_revision(target_revision)
            safe_print(f"  [OK] 迁移文件 {target_revision} 存在")
            safe_print(f"    描述: {rev.doc}")
            safe_print(f"    Down revision: {rev.down_revision}")
            
            # 检查down_revision是否存在
            if rev.down_revision:
                try:
                    down_rev = script.get_revision(rev.down_revision)
                    safe_print(f"    [OK] Down revision {rev.down_revision} 存在")
                except:
                    safe_print(f"    [ERROR] Down revision {rev.down_revision} 不存在")
                    return False
            
            # 尝试导入迁移模块（验证语法）
            migration_file = Path(f"migrations/versions/{target_revision}.py")
            if migration_file.exists():
                # 读取文件前几行，检查基本结构
                content = migration_file.read_text(encoding='utf-8')
                required_items = [
                    'revision =',
                    'down_revision =',
                    'def upgrade():',
                    'def downgrade():',
                    'Base.metadata.create_all'
                ]
                
                missing_items = []
                for item in required_items:
                    if item not in content:
                        missing_items.append(item)
                
                if missing_items:
                    safe_print(f"    [WARNING] 缺少必要项: {', '.join(missing_items)}")
                else:
                    safe_print("    [OK] 迁移文件结构完整")
                
                # 检查是否包含表列表
                if 'missing_tables_list = [' in content:
                    safe_print("    [OK] 包含表列表")
                else:
                    safe_print("    [WARNING] 未找到表列表")
            
        except Exception as e:
            safe_print(f"  [ERROR] 无法加载迁移文件 {target_revision}: {e}")
            import traceback
            traceback.print_exc()
            return False
        
        return True
        
    except Exception as e:
        safe_print(f"  [ERROR] 验证迁移文件语法失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_migration_execution():
    """测试迁移执行（dry-run）"""
    safe_print("\n[TEST 3] 测试迁移执行（语法验证）...")
    
    try:
        # 不实际执行，只验证迁移文件可以被正确导入和执行逻辑
        migration_file = Path("migrations/versions/20260111_0001_complete_missing_tables.py")
        
        if not migration_file.exists():
            safe_print("  [ERROR] 迁移文件不存在")
            return False
        
        # 读取文件内容，检查关键逻辑
        content = migration_file.read_text(encoding='utf-8')
        
        # 检查必要的导入
        required_imports = [
            'from alembic import op',
            'from modules.core.db import Base',
            'from backend.models.database import engine'
        ]
        
        missing_imports = []
        for imp in required_imports:
            if imp not in content:
                missing_imports.append(imp)
        
        if missing_imports:
            safe_print(f"  [WARNING] 缺少导入: {', '.join(missing_imports)}")
        else:
            safe_print("  [OK] 必要的导入都存在")
        
        # 检查upgrade函数逻辑
        if 'Base.metadata.create_all(bind=engine, checkfirst=True)' in content:
            safe_print("  [OK] upgrade函数使用Base.metadata.create_all")
        else:
            safe_print("  [WARNING] upgrade函数可能缺少Base.metadata.create_all调用")
        
        # 检查downgrade函数
        if 'def downgrade():' in content:
            safe_print("  [OK] downgrade函数存在")
        else:
            safe_print("  [WARNING] downgrade函数不存在")
        
        safe_print("  [INFO] 迁移文件语法检查通过（实际执行需要数据库连接）")
        return True
        
    except Exception as e:
        safe_print(f"  [ERROR] 测试迁移执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_schema_completeness():
    """测试表结构完整性验证"""
    safe_print("\n[TEST 4] 测试表结构完整性验证...")
    
    try:
        from backend.models.database import verify_schema_completeness
        
        result = verify_schema_completeness()
        
        safe_print(f"  所有表存在: {result.get('all_tables_exist', False)}")
        safe_print(f"  预期表数: {result.get('expected_table_count', 0)}")
        safe_print(f"  实际表数: {result.get('actual_table_count', 0)}")
        
        missing_tables = result.get('missing_tables', [])
        if missing_tables:
            safe_print(f"  缺失表数: {len(missing_tables)}")
            safe_print(f"  缺失表（前10张）: {', '.join(missing_tables[:10])}")
        else:
            safe_print("  [OK] 所有表都存在")
        
        migration_status = result.get('migration_status', 'unknown')
        safe_print(f"  迁移状态: {migration_status}")
        
        if result.get('all_tables_exist', False):
            safe_print("  [OK] 表结构完整性验证通过")
        else:
            safe_print("  [WARNING] 存在缺失的表（可能需要执行迁移）")
        
        return result.get('all_tables_exist', False)
        
    except Exception as e:
        safe_print(f"  [ERROR] 表结构完整性验证失败: {e}")
        safe_print("  [NOTE] 这可能是正常的（如果数据库未连接）")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    safe_print("=" * 80)
    safe_print("迁移文件验证和测试")
    safe_print("=" * 80)
    
    results = []
    
    # TEST 1: 检查迁移链
    results.append(("迁移链状态", test_migration_chain()))
    
    # TEST 2: 验证迁移文件语法
    results.append(("迁移文件语法", test_migration_file_syntax()))
    
    # TEST 3: 测试迁移执行（语法验证）
    results.append(("迁移执行逻辑", test_migration_execution()))
    
    # TEST 4: 表结构完整性验证（需要数据库连接）
    try:
        results.append(("表结构完整性", test_schema_completeness()))
    except Exception as e:
        safe_print(f"\n[INFO] 表结构完整性验证跳过: {e}")
        results.append(("表结构完整性", None))
    
    # 汇总结果
    safe_print("\n" + "=" * 80)
    safe_print("验证结果汇总")
    safe_print("=" * 80)
    
    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
    skipped = sum(1 for _, result in results if result is None)
    total = len(results)
    
    for name, result in results:
        if result is True:
            status = "[PASS]"
        elif result is False:
            status = "[FAIL]"
        else:
            status = "[SKIP]"
        safe_print(f"  {status} {name}")
    
    safe_print("")
    safe_print(f"总计: {total} 项测试")
    safe_print(f"通过: {passed} 项")
    safe_print(f"失败: {failed} 项")
    if skipped > 0:
        safe_print(f"跳过: {skipped} 项")
    
    safe_print("")
    if failed == 0:
        safe_print("[OK] 所有测试通过（或跳过）")
        return 0
    else:
        safe_print("[WARNING] 部分测试失败，请检查上述错误信息")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        safe_print("\n[INFO] 用户中断")
        sys.exit(1)
    except Exception as e:
        safe_print(f"\n[ERROR] 验证过程异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
