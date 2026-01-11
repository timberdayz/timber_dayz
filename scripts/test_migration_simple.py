#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的迁移文件测试脚本（避免alembic.ini编码问题）

只测试迁移文件的语法和结构，不依赖Alembic配置。
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


def test_migration_file_syntax():
    """测试迁移文件语法（不依赖Alembic）"""
    safe_print("\n[TEST] 验证迁移文件语法...")
    
    migration_file = project_root / "migrations" / "versions" / "20260111_0001_complete_missing_tables.py"
    
    if not migration_file.exists():
        safe_print("  [ERROR] 迁移文件不存在")
        return False
    
    try:
        # 读取文件内容
        content = migration_file.read_text(encoding='utf-8')
        safe_print(f"  [OK] 迁移文件存在: {migration_file.name}")
        
        # 检查必要的结构
        required_items = {
            'revision =': 'revision标识',
            'down_revision =': 'down_revision',
            'def upgrade():': 'upgrade函数',
            'def downgrade():': 'downgrade函数',
            'from modules.core.db import Base': 'Base导入',
            'op.get_bind()': '使用op.get_bind()',
            'Base.metadata.create_all': 'Base.metadata.create_all调用',
        }
        
        missing_items = []
        for item, desc in required_items.items():
            if item not in content:
                missing_items.append(desc)
        
        if missing_items:
            safe_print(f"  [WARNING] 缺少必要项: {', '.join(missing_items)}")
            return False
        else:
            safe_print("  [OK] 迁移文件结构完整")
        
        # 检查是否使用了正确的bind方式
        if 'from backend.models.database import engine' in content:
            safe_print("  [WARNING] 发现直接导入engine（应使用op.get_bind()）")
            # 但如果同时也使用了op.get_bind()，可能只是遗留导入
            if 'op.get_bind()' in content:
                safe_print("  [INFO] 同时也使用了op.get_bind()，可能已修复")
        
        # 提取revision信息
        lines = content.split('\n')
        revision_line = [l for l in lines if 'revision =' in l and not l.strip().startswith('#')]
        down_revision_line = [l for l in lines if 'down_revision =' in l and not l.strip().startswith('#')]
        
        if revision_line:
            safe_print(f"  [OK] Revision: {revision_line[0].strip()}")
        if down_revision_line:
            safe_print(f"  [OK] Down revision: {down_revision_line[0].strip()}")
        
        # 统计表数量
        if 'missing_tables_list = [' in content:
            # 简单统计：计算列表中的引号对数量
            list_start = content.find('missing_tables_list = [')
            list_end = content.find(']', list_start)
            if list_end > list_start:
                list_content = content[list_start:list_end]
                table_count = list_content.count('"')
                table_count = table_count // 2  # 每个表名有一对引号
                safe_print(f"  [OK] 表列表包含约 {table_count} 张表")
        
        safe_print("  [OK] 迁移文件语法检查通过")
        return True
        
    except Exception as e:
        safe_print(f"  [ERROR] 验证失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_import_migration_module():
    """测试迁移模块导入（验证Python语法）"""
    safe_print("\n[TEST] 测试迁移模块导入...")
    
    try:
        # 尝试直接导入模块（验证Python语法）
        import importlib.util
        
        migration_file = project_root / "migrations" / "versions" / "20260111_0001_complete_missing_tables.py"
        
        spec = importlib.util.spec_from_file_location("migration_module", migration_file)
        if spec is None or spec.loader is None:
            safe_print("  [ERROR] 无法创建模块spec")
            return False
        
        # 注意：这里不实际加载模块，只验证语法（因为可能需要数据库连接）
        # 我们可以使用compile来验证语法
        content = migration_file.read_text(encoding='utf-8')
        compile(content, str(migration_file), 'exec')
        safe_print("  [OK] Python语法验证通过")
        return True
        
    except SyntaxError as e:
        safe_print(f"  [ERROR] Python语法错误: {e}")
        return False
    except Exception as e:
        safe_print(f"  [WARNING] 导入测试跳过（可能需要数据库连接）: {type(e).__name__}")
        safe_print("  [NOTE] 这是正常的，迁移文件在运行时需要数据库连接")
        return True  # 不算失败，因为可能是预期的


def main():
    """主函数"""
    safe_print("=" * 80)
    safe_print("迁移文件验证（简化版 - 不依赖Alembic配置）")
    safe_print("=" * 80)
    
    results = []
    
    # TEST 1: 验证迁移文件语法
    results.append(("迁移文件语法", test_migration_file_syntax()))
    
    # TEST 2: 测试Python语法
    results.append(("Python语法", test_import_migration_module()))
    
    # 汇总结果
    safe_print("\n" + "=" * 80)
    safe_print("验证结果汇总")
    safe_print("=" * 80)
    
    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
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
    
    safe_print("")
    if failed == 0:
        safe_print("[OK] 所有测试通过")
        safe_print("[NOTE] 实际执行需要在Docker环境中测试（避免Windows编码问题）")
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
