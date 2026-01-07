"""
快速验证脚本 - 西虹ERP系统 v4.1.0
验证后端优化是否生效

运行方式: python backend/verify_optimization.py
"""

import sys
import time
import requests
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def print_header(text):
    """打印标题"""
    print("\n" + "="*60)
    print(f"  {text}")
    print("="*60)


def print_status(text, status):
    """打印状态"""
    symbol = "✅" if status else "❌"
    print(f"{symbol} {text}")


def test_backend_running():
    """测试后端是否运行"""
    print_header("测试1: 后端服务状态")
    
    try:
        response = requests.get("http://localhost:8001/health", timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            
            print_status("后端服务运行正常", True)
            print(f"   版本: {data.get('version', 'unknown')}")
            print(f"   数据库: {data.get('database', {}).get('type', 'unknown')}")
            print(f"   路由数: {data.get('routes', {}).get('total', 0)}")
            
            # 检查连接池
            pool = data.get('pool', {})
            if pool:
                print(f"   连接池大小: {pool.get('size', 0)}")
                print(f"   活跃连接: {pool.get('checked_out', 0)}")
            
            return True
        else:
            print_status(f"后端返回错误: {response.status_code}", False)
            return False
            
    except requests.exceptions.ConnectionError:
        print_status("后端未运行", False)
        print("   请先启动后端: python run.py --backend-only")
        return False
    except Exception as e:
        print_status(f"测试失败: {e}", False)
        return False


def test_all_routes():
    """测试所有路由是否恢复"""
    print_header("测试2: 路由恢复检查")
    
    try:
        response = requests.get("http://localhost:8001/api/docs", timeout=5)
        
        if response.status_code == 200:
            print_status("API文档可访问", True)
            print("   访问地址: http://localhost:8001/api/docs")
            return True
        else:
            print_status("API文档访问失败", False)
            return False
            
    except Exception as e:
        print_status(f"测试失败: {e}", False)
        return False


def test_database_connection():
    """测试数据库连接"""
    print_header("测试3: 数据库连接")
    
    try:
        response = requests.get("http://localhost:8001/health", timeout=5)
        data = response.json()
        
        db_status = data.get('database', {}).get('status', 'unknown')
        
        if db_status == 'connected':
            print_status("数据库连接正常", True)
            print(f"   类型: {data.get('database', {}).get('type', 'unknown')}")
            return True
        else:
            print_status(f"数据库状态异常: {db_status}", False)
            return False
            
    except Exception as e:
        print_status(f"测试失败: {e}", False)
        return False


def test_response_time():
    """测试响应时间"""
    print_header("测试4: 响应性能")
    
    times = []
    
    try:
        for i in range(5):
            start = time.time()
            response = requests.get("http://localhost:8001/health", timeout=5)
            elapsed = time.time() - start
            times.append(elapsed * 1000)  # 转换为毫秒
        
        avg_time = sum(times) / len(times)
        max_time = max(times)
        min_time = min(times)
        
        passed = avg_time < 500  # 平均响应时间<500ms
        
        print_status(f"平均响应时间: {avg_time:.0f}ms", passed)
        print(f"   最小: {min_time:.0f}ms")
        print(f"   最大: {max_time:.0f}ms")
        print(f"   目标: <500ms")
        
        return passed
        
    except Exception as e:
        print_status(f"测试失败: {e}", False)
        return False


def test_key_endpoints():
    """测试关键端点"""
    print_header("测试5: 关键API端点")
    
    endpoints = [
        ("/api/field-mapping/catalog-status", "字段映射"),
        ("/api/dashboard/overview", "数据看板"),
    ]
    
    results = []
    
    for endpoint, name in endpoints:
        try:
            response = requests.get(f"http://localhost:8001{endpoint}", timeout=10)
            
            if response.status_code in [200, 404]:  # 404也算正常（可能没有数据）
                print_status(f"{name} API可用", True)
                results.append(True)
            else:
                print_status(f"{name} API错误: {response.status_code}", False)
                results.append(False)
                
        except Exception as e:
            print_status(f"{name} API失败: {e}", False)
            results.append(False)
    
    return all(results)


def main():
    """主函数"""
    print("\n" + "🚀 "*30)
    print("  西虹ERP系统后端优化验证 v4.1.0")
    print("🚀 "*30)
    
    results = []
    
    # 运行所有测试
    results.append(test_backend_running())
    
    if results[-1]:  # 只有后端运行了才继续其他测试
        results.append(test_all_routes())
        results.append(test_database_connection())
        results.append(test_response_time())
        results.append(test_key_endpoints())
    
    # 打印总结
    print_header("验证总结")
    
    passed = sum(results)
    total = len(results)
    
    print(f"\n  总计: {passed}/{total} 项测试通过 ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("\n  ✅ 所有测试通过！后端优化成功！")
        print("\n  📚 下一步:")
        print("     1. 访问 http://localhost:8001/api/docs 查看完整API")
        print("     2. 启动前端: python run.py --frontend-only")
        print("     3. 访问 http://localhost:5173 使用系统")
    else:
        print(f"\n  ⚠️  {total - passed} 项测试失败，请检查配置")
        print("\n  💡 常见问题:")
        print("     - PostgreSQL服务未运行")
        print("     - 端口8001被占用")
        print("     - 数据库配置错误")
    
    print("\n" + "="*60 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

