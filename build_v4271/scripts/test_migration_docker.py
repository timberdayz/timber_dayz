#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Docker环境迁移测试脚本

在Docker环境中测试迁移文件的执行和验证。
"""

import subprocess
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


def run_docker_command(cmd, description):
    """运行Docker命令"""
    safe_print(f"\n[TEST] {description}...")
    
    try:
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.stdout:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    safe_print(f"  {line}")
        
        if result.stderr:
            for line in result.stderr.strip().split('\n'):
                if line.strip():
                    safe_print(f"  [STDERR] {line}")
        
        if result.returncode == 0:
            safe_print(f"  [OK] {description}完成")
            return True, result.stdout, result.stderr
        else:
            safe_print(f"  [ERROR] {description}失败 (exit code: {result.returncode})")
            return False, result.stdout, result.stderr
            
    except subprocess.TimeoutExpired:
        safe_print(f"  [ERROR] {description}超时（超过2分钟）")
        return False, "", ""
    except Exception as e:
        safe_print(f"  [ERROR] {description}异常: {e}")
        import traceback
        traceback.print_exc()
        return False, "", ""


def test_docker_environment():
    """测试Docker环境"""
    safe_print("\n[TEST 1] 检查Docker环境...")
    
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=postgres", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.returncode == 0 and "postgres" in result.stdout:
            safe_print("  [OK] PostgreSQL容器正在运行")
            safe_print(f"  容器: {result.stdout.strip()}")
            return True
        else:
            safe_print("  [WARNING] PostgreSQL容器未运行")
            safe_print("  提示: 请先启动PostgreSQL容器")
            safe_print("  命令: docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres")
            return False
            
    except Exception as e:
        safe_print(f"  [ERROR] 检查Docker环境失败: {e}")
        return False


def test_alembic_heads():
    """测试Alembic heads"""
    cmd = [
        "docker-compose", "-f", "docker-compose.yml", "-f", "docker-compose.dev.yml",
        "run", "--rm", "--no-deps",
        "backend",
        "alembic", "heads"
    ]
    
    success, stdout, stderr = run_docker_command(cmd, "检查Alembic迁移heads")
    
    if success:
        # 检查是否有多个head
        if stdout and stdout.count('\n') > 0:
            safe_print("  [WARNING] 发现多个head，可能需要合并")
        else:
            safe_print("  [OK] 单个head（正常）")
    
    return success


def test_alembic_current():
    """测试Alembic当前版本"""
    cmd = [
        "docker-compose", "-f", "docker-compose.yml", "-f", "docker-compose.dev.yml",
        "run", "--rm", "--no-deps",
        "backend",
        "alembic", "current"
    ]
    
    success, stdout, stderr = run_docker_command(cmd, "检查Alembic当前版本")
    return success


def test_alembic_upgrade():
    """测试Alembic迁移执行"""
    cmd = [
        "docker-compose", "-f", "docker-compose.yml", "-f", "docker-compose.dev.yml",
        "run", "--rm", "--no-deps",
        "backend",
        "alembic", "upgrade", "head"
    ]
    
    success, stdout, stderr = run_docker_command(cmd, "执行Alembic迁移（upgrade head）")
    
    if success:
        # 检查迁移输出
        if "20260111_0001_complete_missing_tables" in stdout:
            safe_print("  [OK] 新迁移文件已执行")
        elif "Running upgrade" in stdout:
            safe_print("  [INFO] 迁移已执行（可能是最新版本）")
        else:
            safe_print("  [INFO] 迁移执行完成")
    
    return success


def test_schema_completeness():
    """测试表结构完整性"""
    cmd = [
        "docker-compose", "-f", "docker-compose.yml", "-f", "docker-compose.dev.yml",
        "run", "--rm", "--no-deps",
        "backend",
        "python", "-c",
        "from backend.models.database import verify_schema_completeness; "
        "result = verify_schema_completeness(); "
        "print(f'所有表存在: {result[\"all_tables_exist\"]}'); "
        "print(f'预期表数: {result[\"expected_table_count\"]}'); "
        "print(f'实际表数: {result[\"actual_table_count\"]}'); "
        "if result[\"missing_tables\"]: "
        "  print(f'缺失表数: {len(result[\"missing_tables\"])}'); "
        "  print(f'缺失表: {result[\"missing_tables\"][:10]}'); "
        "print(f'迁移状态: {result[\"migration_status\"]}'); "
        "exit(0 if result[\"all_tables_exist\"] else 1)"
    ]
    
    success, stdout, stderr = run_docker_command(cmd, "验证表结构完整性")
    return success


def main():
    """主函数"""
    safe_print("=" * 80)
    safe_print("Docker环境迁移测试")
    safe_print("=" * 80)
    
    results = []
    
    # TEST 1: 检查Docker环境
    docker_available = test_docker_environment()
    results.append(("Docker环境", docker_available))
    
    if not docker_available:
        safe_print("\n[ERROR] Docker环境不可用，测试终止")
        safe_print("请先启动PostgreSQL容器:")
        safe_print("  docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres")
        return 1
    
    # TEST 2: 检查Alembic heads
    results.append(("Alembic heads", test_alembic_heads()))
    
    # TEST 3: 检查当前版本
    results.append(("Alembic当前版本", test_alembic_current()))
    
    # TEST 4: 执行迁移
    results.append(("Alembic迁移执行", test_alembic_upgrade()))
    
    # TEST 5: 检查迁移后版本
    results.append(("迁移后版本", test_alembic_current()))
    
    # TEST 6: 验证表结构完整性
    results.append(("表结构完整性", test_schema_completeness()))
    
    # 汇总结果
    safe_print("\n" + "=" * 80)
    safe_print("测试结果汇总")
    safe_print("=" * 80)
    
    passed = sum(1 for _, result in results if result)
    failed = sum(1 for _, result in results if not result)
    total = len(results)
    
    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        safe_print(f"  {status} {name}")
    
    safe_print("")
    safe_print(f"总计: {total} 项测试")
    safe_print(f"通过: {passed} 项")
    safe_print(f"失败: {failed} 项")
    
    safe_print("")
    if failed == 0:
        safe_print("[OK] 所有测试通过")
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
        safe_print(f"\n[ERROR] 测试过程异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
