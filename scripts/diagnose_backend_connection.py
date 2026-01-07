#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后端连接诊断脚本

用于诊断前端无法连接后端的问题
"""

import subprocess
import sys
import json
from pathlib import Path

def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def check_container_status():
    """检查后端容器状态"""
    safe_print("\n" + "="*80)
    safe_print("[诊断] 检查后端容器状态")
    safe_print("="*80)
    
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=backend", "--format", "{{.Names}}|{{.Status}}|{{.Ports}}"],
            capture_output=True,
            text=True,
            timeout=5,
            encoding='utf-8',
            errors='ignore'
        )
        
        if "backend" in result.stdout:
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if line.strip():
                    parts = line.split('|')
                    if len(parts) >= 3:
                        safe_print(f"  容器名称: {parts[0]}")
                        safe_print(f"  状态: {parts[1]}")
                        safe_print(f"  端口映射: {parts[2]}")
                        if "healthy" in parts[1].lower():
                            safe_print("  [OK] 容器健康检查通过")
                        elif "unhealthy" in parts[1].lower():
                            safe_print("  [WARNING] 容器健康检查未通过")
            return True
        else:
            safe_print("  [ERROR] 后端容器未运行")
            return False
    except Exception as e:
        safe_print(f"  [ERROR] 检查失败: {e}")
        return False

def check_database_connection():
    """检查数据库连接"""
    safe_print("\n" + "="*80)
    safe_print("[诊断] 检查数据库连接")
    safe_print("="*80)
    
    try:
        result = subprocess.run(
            ["docker", "exec", "xihong_erp_postgres", "psql", "-U", "erp_dev", "-d", "xihong_erp_dev", 
             "-c", "SELECT current_database(), current_user, version();"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        
        if result.returncode == 0:
            safe_print("  [OK] 数据库连接正常")
            safe_print(f"  输出:\n{result.stdout}")
            return True
        else:
            safe_print("  [ERROR] 数据库连接失败")
            safe_print(f"  错误: {result.stderr[:200]}")
            return False
    except Exception as e:
        safe_print(f"  [ERROR] 检查失败: {e}")
        return False

def check_backend_health():
    """检查后端健康检查端点"""
    safe_print("\n" + "="*80)
    safe_print("[诊断] 检查后端健康检查端点")
    safe_print("="*80)
    
    try:
        import urllib.request
        import json
        
        url = "http://localhost:8001/health"
        req = urllib.request.Request(url)
        req.add_header('Accept', 'application/json')
        
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                safe_print("  [OK] 健康检查端点响应正常")
                safe_print(f"  状态码: {response.status}")
                safe_print(f"  响应内容:")
                safe_print(json.dumps(data, indent=2, ensure_ascii=False))
                
                # 检查数据库状态
                if data.get('database', {}).get('status') == 'connected':
                    safe_print("  [OK] 数据库连接状态: 已连接")
                else:
                    safe_print("  [WARNING] 数据库连接状态异常")
                
                return True
            else:
                safe_print(f"  [ERROR] 健康检查返回错误状态码: {response.status}")
                return False
    except urllib.error.URLError as e:
        safe_print(f"  [ERROR] 无法连接到后端服务: {e}")
        safe_print("  可能原因:")
        safe_print("    1. 后端服务未启动")
        safe_print("    2. 端口8001被占用")
        safe_print("    3. 防火墙阻止连接")
        return False
    except Exception as e:
        safe_print(f"  [ERROR] 检查失败: {e}")
        return False

def check_login_endpoint():
    """检查登录端点"""
    safe_print("\n" + "="*80)
    safe_print("[诊断] 检查登录端点")
    safe_print("="*80)
    
    try:
        import urllib.request
        import json
        
        url = "http://localhost:8001/api/auth/login"
        data = json.dumps({"username": "test", "password": "test"}).encode('utf-8')
        
        req = urllib.request.Request(url, data=data)
        req.add_header('Content-Type', 'application/json')
        
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                response_data = json.loads(response.read().decode('utf-8'))
                safe_print(f"  [INFO] 登录端点可访问，状态码: {response.status}")
                safe_print(f"  响应: {json.dumps(response_data, indent=2, ensure_ascii=False)}")
                
                if response.status == 401 or response.status == 422:
                    safe_print("  [OK] 端点正常响应（认证失败是预期的）")
                return True
        except urllib.error.HTTPError as e:
            if e.code == 401 or e.code == 422:
                safe_print(f"  [OK] 登录端点可访问（返回 {e.code} 是预期的）")
                return True
            else:
                safe_print(f"  [WARNING] 登录端点返回异常状态码: {e.code}")
                return False
    except urllib.error.URLError as e:
        safe_print(f"  [ERROR] 无法连接到登录端点: {e}")
        return False
    except Exception as e:
        safe_print(f"  [ERROR] 检查失败: {e}")
        return False

def check_backend_logs():
    """检查后端日志中的错误"""
    safe_print("\n" + "="*80)
    safe_print("[诊断] 检查后端日志（最近50行）")
    safe_print("="*80)
    
    try:
        result = subprocess.run(
            ["docker", "logs", "xihong_erp_backend_dev", "--tail", "50"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            error_lines = [line for line in lines if any(keyword in line.upper() for keyword in ['ERROR', 'EXCEPTION', 'FAILED', 'TRACEBACK'])]
            
            if error_lines:
                safe_print("  [WARNING] 发现错误日志:")
                for line in error_lines[-10:]:  # 只显示最后10个错误
                    safe_print(f"    {line[:200]}")
            else:
                safe_print("  [OK] 未发现明显的错误日志")
            
            # 显示最后几行日志
            safe_print("\n  最后10行日志:")
            for line in lines[-10:]:
                safe_print(f"    {line}")
        else:
            safe_print(f"  [WARNING] 无法获取日志: {result.stderr[:200]}")
    except Exception as e:
        safe_print(f"  [ERROR] 检查失败: {e}")

def check_environment_variables():
    """检查后端环境变量"""
    safe_print("\n" + "="*80)
    safe_print("[诊断] 检查后端环境变量")
    safe_print("="*80)
    
    try:
        result = subprocess.run(
            ["docker", "exec", "xihong_erp_backend_dev", "env"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        
        if result.returncode == 0:
            env_vars = result.stdout.strip().split('\n')
            relevant_vars = [var for var in env_vars if any(keyword in var.upper() for keyword in ['DATABASE', 'REDIS', 'API', 'PORT'])]
            
            safe_print("  相关环境变量:")
            for var in sorted(relevant_vars):
                # 隐藏密码
                if 'PASSWORD' in var or 'PASS' in var:
                    parts = var.split('=')
                    if len(parts) == 2:
                        safe_print(f"    {parts[0]}=***")
                else:
                    safe_print(f"    {var}")
        else:
            safe_print(f"  [WARNING] 无法获取环境变量")
    except Exception as e:
        safe_print(f"  [ERROR] 检查失败: {e}")

def check_frontend_config():
    """检查前端配置"""
    safe_print("\n" + "="*80)
    safe_print("[诊断] 检查前端API配置")
    safe_print("="*80)
    
    try:
        api_file = Path(__file__).parent.parent / "frontend" / "src" / "api" / "index.js"
        if api_file.exists():
            content = api_file.read_text(encoding='utf-8')
            
            if 'baseURL' in content:
                # 查找baseURL配置
                import re
                match = re.search(r"baseURL:\s*['\"]([^'\"]+)['\"]", content)
                if match:
                    base_url = match.group(1)
                    safe_print(f"  当前baseURL配置: {base_url}")
                    
                    if base_url.startswith('http://') or base_url.startswith('https://'):
                        safe_print("  [WARNING] 使用绝对URL，可能无法通过代理")
                        safe_print("  建议: 使用相对路径 '/api' 或环境变量")
                    elif base_url == '/api':
                        safe_print("  [OK] 使用相对路径，将通过Vite代理")
                    elif 'VITE_API_BASE_URL' in content:
                        safe_print("  [OK] 使用环境变量配置")
                else:
                    safe_print("  [WARNING] 无法找到baseURL配置")
        else:
            safe_print("  [WARNING] 无法找到前端API配置文件")
    except Exception as e:
        safe_print(f"  [ERROR] 检查失败: {e}")

def main():
    """主函数"""
    safe_print("="*80)
    safe_print("后端连接诊断脚本")
    safe_print("="*80)
    
    results = []
    
    # 1. 检查容器状态
    results.append(("容器状态", check_container_status()))
    
    # 2. 检查数据库连接
    results.append(("数据库连接", check_database_connection()))
    
    # 3. 检查健康检查端点
    results.append(("健康检查端点", check_backend_health()))
    
    # 4. 检查登录端点
    results.append(("登录端点", check_login_endpoint()))
    
    # 5. 检查后端日志
    check_backend_logs()
    
    # 6. 检查环境变量
    check_environment_variables()
    
    # 7. 检查前端配置
    check_frontend_config()
    
    # 总结
    safe_print("\n" + "="*80)
    safe_print("诊断总结")
    safe_print("="*80)
    
    for name, result in results:
        status = "[OK]" if result else "[FAIL]"
        safe_print(f"  {status} {name}")
    
    safe_print("\n建议:")
    safe_print("  1. 如果容器状态异常，检查: docker ps -a")
    safe_print("  2. 如果数据库连接失败，运行: python scripts/fix_database_user.py")
    safe_print("  3. 如果API端点无法访问，检查端口映射: docker ps | grep backend")
    safe_print("  4. 如果前端无法连接，确保使用相对路径 '/api' 或配置正确的环境变量")
    safe_print("  5. 查看完整日志: docker logs xihong_erp_backend_dev -f")

if __name__ == "__main__":
    main()


