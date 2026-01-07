#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据库用户修复脚本（改进版）

修复PostgreSQL数据库用户不存在的问题
先检查现有数据库用户，然后根据情况决定操作
当数据库数据卷使用旧配置创建时，需要重新初始化
"""

import subprocess
import sys
from pathlib import Path

def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def check_container_running():
    """检查PostgreSQL容器是否运行"""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=xihong_erp_postgres", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5,
            encoding='utf-8',
            errors='ignore'
        )
        return "xihong_erp_postgres" in result.stdout
    except:
        return False

def find_available_superuser():
    """查找可用的超级用户"""
    safe_print("\n[检查] 查找可用的超级用户...")
    # 按优先级尝试不同的超级用户
    candidates = ['postgres', 'erp_user']
    
    for user in candidates:
        try:
            result = subprocess.run(
                ["docker", "exec", "xihong_erp_postgres", "psql", "-U", user, "-d", "postgres", 
                 "-c", "SELECT 1;"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8',
                errors='ignore'
            )
            if result.returncode == 0:
                safe_print(f"  [OK] 找到可用的超级用户: {user}")
                return user
        except:
            continue
    
    safe_print("  [ERROR] 未找到可用的超级用户")
    return None

def list_all_users(superuser):
    """列出所有数据库用户"""
    safe_print(f"\n[检查] 列出所有数据库用户（使用 {superuser} 连接）...")
    try:
        result = subprocess.run(
            ["docker", "exec", "xihong_erp_postgres", "psql", "-U", superuser, "-d", "postgres", 
             "-c", "SELECT rolname, rolsuper, rolcreaterole FROM pg_roles WHERE rolname NOT LIKE 'pg_%' ORDER BY rolname;"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        
        if result.returncode == 0:
            safe_print("  现有用户列表:")
            lines = result.stdout.strip().split('\n')
            for line in lines[2:-1]:  # 跳过标题和分隔线
                if line.strip():
                    safe_print(f"    {line}")
            return result.stdout
        else:
            safe_print(f"  [ERROR] 查询失败: {result.stderr[:200]}")
            return None
    except Exception as e:
        safe_print(f"  [ERROR] 查询异常: {e}")
        return None

def list_all_databases(superuser):
    """列出所有数据库"""
    safe_print(f"\n[检查] 列出所有数据库（使用 {superuser} 连接）...")
    try:
        result = subprocess.run(
            ["docker", "exec", "xihong_erp_postgres", "psql", "-U", superuser, "-d", "postgres", 
             "-c", "SELECT datname, pg_size_pretty(pg_database_size(datname)) as size FROM pg_database WHERE datistemplate = false ORDER BY datname;"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        
        if result.returncode == 0:
            safe_print("  现有数据库列表:")
            lines = result.stdout.strip().split('\n')
            for line in lines[2:-1]:  # 跳过标题和分隔线
                if line.strip():
                    safe_print(f"    {line}")
            return result.stdout
        else:
            safe_print(f"  [WARNING] 查询失败: {result.stderr[:200]}")
            return None
    except Exception as e:
        safe_print(f"  [WARNING] 查询异常: {e}")
        return None

def check_target_user(superuser, username='erp_dev'):
    """检查目标用户是否存在"""
    safe_print(f"\n[检查] 检查目标用户 '{username}' 是否存在...")
    try:
        result = subprocess.run(
            ["docker", "exec", "xihong_erp_postgres", "psql", "-U", superuser, "-d", "postgres", 
             "-c", f"SELECT 1 FROM pg_roles WHERE rolname='{username}';"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        
        if "1" in result.stdout:
            safe_print(f"  [OK] 用户 '{username}' 已存在")
            return True
        else:
            safe_print(f"  [INFO] 用户 '{username}' 不存在")
            return False
    except Exception as e:
        safe_print(f"  [ERROR] 检查失败: {e}")
        return False

def check_target_database(superuser, dbname='xihong_erp_dev'):
    """检查目标数据库是否存在"""
    safe_print(f"\n[检查] 检查目标数据库 '{dbname}' 是否存在...")
    try:
        result = subprocess.run(
            ["docker", "exec", "xihong_erp_postgres", "psql", "-U", superuser, "-d", "postgres", 
             "-c", f"SELECT 1 FROM pg_database WHERE datname='{dbname}';"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        
        if "1" in result.stdout:
            safe_print(f"  [OK] 数据库 '{dbname}' 已存在")
            # 检查数据库所有者
            result2 = subprocess.run(
                ["docker", "exec", "xihong_erp_postgres", "psql", "-U", superuser, "-d", "postgres", 
                 "-c", f"SELECT d.datname, u.rolname as owner FROM pg_database d JOIN pg_roles u ON d.datdba = u.oid WHERE d.datname='{dbname}';"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8',
                errors='ignore'
            )
            if result2.returncode == 0:
                lines = result2.stdout.strip().split('\n')
                for line in lines[2:-1]:
                    if line.strip():
                        safe_print(f"    {line}")
            return True
        else:
            safe_print(f"  [INFO] 数据库 '{dbname}' 不存在")
            return False
    except Exception as e:
        safe_print(f"  [ERROR] 检查失败: {e}")
        return False

def check_existing_tables(superuser, dbname='xihong_erp'):
    """检查现有数据库中的表数量"""
    safe_print(f"\n[检查] 检查数据库 '{dbname}' 中的表数量...")
    try:
        # 先检查数据库是否存在
        result = subprocess.run(
            ["docker", "exec", "xihong_erp_postgres", "psql", "-U", superuser, "-d", "postgres", 
             "-c", f"SELECT 1 FROM pg_database WHERE datname='{dbname}';"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        
        if "1" not in result.stdout:
            safe_print(f"  [INFO] 数据库 '{dbname}' 不存在，跳过表检查")
            return 0
        
        # 检查表数量
        result = subprocess.run(
            ["docker", "exec", "xihong_erp_postgres", "psql", "-U", superuser, "-d", dbname, 
             "-c", "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        
        if result.returncode == 0:
            # 提取数字
            import re
            count = re.search(r'\d+', result.stdout)
            if count:
                table_count = int(count.group())
                safe_print(f"  [INFO] 数据库 '{dbname}' 中有 {table_count} 个表")
                if table_count > 0:
                    safe_print(f"  [WARNING] 数据库 '{dbname}' 中包含数据，操作时需谨慎")
                return table_count
        return 0
    except Exception as e:
        safe_print(f"  [WARNING] 检查表数量失败: {e}")
        return 0

def safe_create_user(superuser, username='erp_dev', password='dev_pass_2025'):
    """安全创建数据库用户（不删除现有数据）"""
    safe_print(f"\n[修复] 创建数据库用户 '{username}'（使用 {superuser} 连接）...")
    try:
        # 检查用户是否已存在
        if check_target_user(superuser, username):
            safe_print(f"  [INFO] 用户 '{username}' 已存在，跳过创建")
        else:
            # 创建用户
            cmd = f"CREATE USER {username} WITH PASSWORD '{password}';"
            result = subprocess.run(
                ["docker", "exec", "xihong_erp_postgres", "psql", "-U", superuser, "-d", "postgres", "-c", cmd],
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8',
                errors='ignore'
            )
            
            if result.returncode == 0:
                safe_print(f"  [OK] 用户 '{username}' 创建成功")
            elif "already exists" in result.stderr.lower():
                safe_print(f"  [INFO] 用户 '{username}' 已存在")
            else:
                safe_print(f"  [ERROR] 用户创建失败: {result.stderr[:200]}")
                return False
        
        return True
    except Exception as e:
        safe_print(f"  [ERROR] 创建用户异常: {e}")
        return False

def safe_create_database(superuser, dbname='xihong_erp_dev', owner='erp_dev'):
    """安全创建数据库（不删除现有数据）"""
    safe_print(f"\n[修复] 创建数据库 '{dbname}'（所有者: {owner}）...")
    try:
        # 检查数据库是否已存在
        if check_target_database(superuser, dbname):
            safe_print(f"  [INFO] 数据库 '{dbname}' 已存在，跳过创建")
            # 如果数据库存在但所有者不对，尝试修改所有者
            result = subprocess.run(
                ["docker", "exec", "xihong_erp_postgres", "psql", "-U", superuser, "-d", "postgres", 
                 "-c", f"ALTER DATABASE {dbname} OWNER TO {owner};"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8',
                errors='ignore'
            )
            if result.returncode == 0:
                safe_print(f"  [OK] 数据库所有者已设置为 '{owner}'")
            return True
        
        # 创建数据库
        cmd = f"CREATE DATABASE {dbname} OWNER {owner};"
        result = subprocess.run(
            ["docker", "exec", "xihong_erp_postgres", "psql", "-U", superuser, "-d", "postgres", "-c", cmd],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        
        if result.returncode == 0:
            safe_print(f"  [OK] 数据库 '{dbname}' 创建成功")
            
            # 授权
            cmd = f"GRANT ALL PRIVILEGES ON DATABASE {dbname} TO {owner};"
            result = subprocess.run(
                ["docker", "exec", "xihong_erp_postgres", "psql", "-U", superuser, "-d", "postgres", "-c", cmd],
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8',
                errors='ignore'
            )
            if result.returncode == 0:
                safe_print(f"  [OK] 数据库权限已授予 '{owner}'")
            return True
        elif "already exists" in result.stderr.lower():
            safe_print(f"  [INFO] 数据库 '{dbname}' 已存在")
            return True
        else:
            safe_print(f"  [ERROR] 数据库创建失败: {result.stderr[:200]}")
            return False
    except Exception as e:
        safe_print(f"  [ERROR] 创建数据库异常: {e}")
        return False

def main():
    """主函数"""
    safe_print("="*80)
    safe_print("数据库用户修复脚本（改进版）")
    safe_print("先检查现有数据库用户，然后根据情况决定操作")
    safe_print("="*80)
    
    # 1. 检查PostgreSQL容器是否运行
    if not check_container_running():
        safe_print("\n[ERROR] PostgreSQL容器未运行")
        safe_print("  请先启动PostgreSQL容器:")
        safe_print("    docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev up -d postgres")
        sys.exit(1)
    else:
        safe_print("\n[OK] PostgreSQL容器正在运行")
    
    # 2. 查找可用的超级用户
    superuser = find_available_superuser()
    if not superuser:
        safe_print("\n[ERROR] 无法找到可用的超级用户")
        safe_print("  请手动检查PostgreSQL容器状态:")
        safe_print("    docker exec -it xihong_erp_postgres psql -U postgres")
        sys.exit(1)
    
    # 3. 列出所有现有用户
    list_all_users(superuser)
    
    # 4. 列出所有现有数据库
    list_all_databases(superuser)
    
    # 5. 检查现有数据库中的表数量（评估是否有重要数据）
    old_db_names = ['xihong_erp', 'xihong_erp_dev']
    has_data = False
    for dbname in old_db_names:
        table_count = check_existing_tables(superuser, dbname)
        if table_count > 0:
            has_data = True
    
    # 6. 检查目标用户是否存在
    target_user = 'erp_dev'
    target_db = 'xihong_erp_dev'
    user_exists = check_target_user(superuser, target_user)
    db_exists = check_target_database(superuser, target_db)
    
    # 7. 根据检查结果决定操作
    safe_print("\n" + "="*80)
    safe_print("诊断结果:")
    safe_print("="*80)
    safe_print(f"  目标用户 '{target_user}': {'存在' if user_exists else '不存在'}")
    safe_print(f"  目标数据库 '{target_db}': {'存在' if db_exists else '不存在'}")
    safe_print(f"  现有数据: {'有数据需要保护' if has_data else '无重要数据'}")

    if user_exists and db_exists:
        safe_print("\n[OK] 数据库用户和数据库都已存在，无需修复")
        safe_print("  如果后端仍然无法连接，请检查:")
        safe_print("    1. 密码是否正确")
        safe_print("    2. 数据库连接URL是否正确")
        safe_print("    3. 网络连接是否正常")
        return
    
    # 8. 执行修复操作
    if has_data:
        safe_print("\n[提示] 检测到现有数据，将使用安全方式创建用户（不会删除数据）")
    
    safe_print("\n[开始] 执行修复操作...")
    
    # 创建用户
    if not safe_create_user(superuser, target_user, 'dev_pass_2025'):
        safe_print("\n[失败] 用户创建失败")
        safe_print("\n手动修复方案:")
        safe_print(f"  docker exec -it xihong_erp_postgres psql -U {superuser}")
        safe_print(f"  CREATE USER {target_user} WITH PASSWORD 'dev_pass_2025';")
        safe_print(f"  CREATE DATABASE {target_db} OWNER {target_user};")
        sys.exit(1)
    
    # 创建数据库
    if not safe_create_database(superuser, target_db, target_user):
        safe_print("\n[失败] 数据库创建失败")
        safe_print("\n手动修复方案:")
        safe_print(f"  docker exec -it xihong_erp_postgres psql -U {superuser}")
        safe_print(f"  CREATE DATABASE {target_db} OWNER {target_user};")
        sys.exit(1)
    
    # 9. 验证修复结果
    safe_print("\n[验证] 验证修复结果...")
    if check_target_user(superuser, target_user) and check_target_database(superuser, target_db):
        safe_print("\n" + "="*80)
        safe_print("[成功] 数据库用户修复完成！")
        safe_print("="*80)
        safe_print(f"  用户: {target_user}")
        safe_print(f"  数据库: {target_db}")
        if has_data:
            safe_print("  注意: 现有数据已保留")
        safe_print("\n  现在可以重新启动后端服务:")
        safe_print("    python run.py --use-docker")
    else:
        safe_print("\n[失败] 修复验证失败，请手动检查")
        sys.exit(1)

if __name__ == "__main__":
    main()

