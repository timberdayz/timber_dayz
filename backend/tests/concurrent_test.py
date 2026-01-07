"""
并发压力测试工具
"""

import asyncio
import aiohttp
import time
import json
from datetime import datetime
from typing import List, Dict, Any
from dataclasses import dataclass
import statistics

@dataclass
class TestResult:
    """测试结果数据类"""
    test_name: str
    total_requests: int
    successful_requests: int
    failed_requests: int
    total_time: float
    average_response_time: float
    min_response_time: float
    max_response_time: float
    requests_per_second: float
    error_rate: float
    errors: List[str]

class ConcurrentTester:
    """并发测试器"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = None
        self.results = []
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=100, limit_per_host=50)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    async def make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """发送HTTP请求"""
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()
        
        try:
            async with self.session.request(method, url, **kwargs) as response:
                response_time = time.time() - start_time
                text = await response.text()
                
                return {
                    "success": response.status < 400,
                    "status_code": response.status,
                    "response_time": response_time,
                    "response_size": len(text),
                    "error": None if response.status < 400 else f"HTTP {response.status}"
                }
        except Exception as e:
            response_time = time.time() - start_time
            return {
                "success": False,
                "status_code": 0,
                "response_time": response_time,
                "response_size": 0,
                "error": str(e)
            }
    
    async def test_health_check(self, concurrent_users: int, requests_per_user: int) -> TestResult:
        """测试健康检查端点"""
        print(f"开始健康检查测试: {concurrent_users}个并发用户, 每用户{requests_per_user}个请求")
        
        start_time = time.time()
        tasks = []
        
        # 创建并发任务
        for user_id in range(concurrent_users):
            for request_id in range(requests_per_user):
                task = self.make_request("GET", "/health")
                tasks.append(task)
        
        # 执行所有请求
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        
        # 处理结果
        successful = [r for r in results if isinstance(r, dict) and r.get("success", False)]
        failed = [r for r in results if isinstance(r, dict) and not r.get("success", False)]
        exceptions = [r for r in results if isinstance(r, Exception)]
        
        response_times = [r["response_time"] for r in successful]
        errors = [r.get("error", "Unknown error") for r in failed] + [str(e) for e in exceptions]
        
        return TestResult(
            test_name="Health Check",
            total_requests=len(tasks),
            successful_requests=len(successful),
            failed_requests=len(failed) + len(exceptions),
            total_time=total_time,
            average_response_time=statistics.mean(response_times) if response_times else 0,
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            requests_per_second=len(tasks) / total_time if total_time > 0 else 0,
            error_rate=(len(failed) + len(exceptions)) / len(tasks) * 100 if tasks else 0,
            errors=errors[:10]  # 只保留前10个错误
        )
    
    async def test_api_endpoints(self, concurrent_users: int, requests_per_user: int) -> List[TestResult]:
        """测试多个API端点"""
        endpoints = [
            ("GET", "/api/dashboard/overview"),
            ("GET", "/api/inventory/"),
            ("GET", "/api/finance/accounts-receivable"),
            ("GET", "/api/roles/"),
            ("POST", "/api/auth/login", {"json": {"username": "test", "password": "test"}})
        ]
        
        results = []
        
        for method, endpoint, *args in endpoints:
            print(f"测试端点: {method} {endpoint}")
            
            start_time = time.time()
            tasks = []
            
            # 创建并发任务
            for user_id in range(concurrent_users):
                for request_id in range(requests_per_user):
                    kwargs = args[0] if args else {}
                    task = self.make_request(method, endpoint, **kwargs)
                    tasks.append(task)
            
            # 执行所有请求
            request_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            total_time = time.time() - start_time
            
            # 处理结果
            successful = [r for r in request_results if isinstance(r, dict) and r.get("success", False)]
            failed = [r for r in request_results if isinstance(r, dict) and not r.get("success", False)]
            exceptions = [r for r in request_results if isinstance(r, Exception)]
            
            response_times = [r["response_time"] for r in successful]
            errors = [r.get("error", "Unknown error") for r in failed] + [str(e) for e in exceptions]
            
            result = TestResult(
                test_name=f"{method} {endpoint}",
                total_requests=len(tasks),
                successful_requests=len(successful),
                failed_requests=len(failed) + len(exceptions),
                total_time=total_time,
                average_response_time=statistics.mean(response_times) if response_times else 0,
                min_response_time=min(response_times) if response_times else 0,
                max_response_time=max(response_times) if response_times else 0,
                requests_per_second=len(tasks) / total_time if total_time > 0 else 0,
                error_rate=(len(failed) + len(exceptions)) / len(tasks) * 100 if tasks else 0,
                errors=errors[:10]
            )
            
            results.append(result)
        
        return results
    
    async def test_database_operations(self, concurrent_users: int, operations_per_user: int) -> TestResult:
        """测试数据库操作"""
        print(f"开始数据库操作测试: {concurrent_users}个并发用户, 每用户{operations_per_user}个操作")
        
        start_time = time.time()
        tasks = []
        
        # 创建数据库操作任务
        for user_id in range(concurrent_users):
            for op_id in range(operations_per_user):
                # 测试不同的数据库操作
                if op_id % 3 == 0:
                    # 查询操作
                    task = self.make_request("GET", "/api/dashboard/overview")
                elif op_id % 3 == 1:
                    # 用户列表查询
                    task = self.make_request("GET", "/api/users/")
                else:
                    # 角色列表查询
                    task = self.make_request("GET", "/api/roles/")
                
                tasks.append(task)
        
        # 执行所有请求
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        
        # 处理结果
        successful = [r for r in results if isinstance(r, dict) and r.get("success", False)]
        failed = [r for r in results if isinstance(r, dict) and not r.get("success", False)]
        exceptions = [r for r in results if isinstance(r, Exception)]
        
        response_times = [r["response_time"] for r in successful]
        errors = [r.get("error", "Unknown error") for r in failed] + [str(e) for e in exceptions]
        
        return TestResult(
            test_name="Database Operations",
            total_requests=len(tasks),
            successful_requests=len(successful),
            failed_requests=len(failed) + len(exceptions),
            total_time=total_time,
            average_response_time=statistics.mean(response_times) if response_times else 0,
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            requests_per_second=len(tasks) / total_time if total_time > 0 else 0,
            error_rate=(len(failed) + len(exceptions)) / len(tasks) * 100 if tasks else 0,
            errors=errors[:10]
        )
    
    def print_test_result(self, result: TestResult):
        """打印测试结果"""
        print(f"\n{'='*60}")
        print(f"测试名称: {result.test_name}")
        print(f"{'='*60}")
        print(f"总请求数: {result.total_requests}")
        print(f"成功请求: {result.successful_requests}")
        print(f"失败请求: {result.failed_requests}")
        print(f"总耗时: {result.total_time:.2f}秒")
        print(f"平均响应时间: {result.average_response_time:.3f}秒")
        print(f"最小响应时间: {result.min_response_time:.3f}秒")
        print(f"最大响应时间: {result.max_response_time:.3f}秒")
        print(f"每秒请求数: {result.requests_per_second:.2f}")
        print(f"错误率: {result.error_rate:.2f}%")
        
        if result.errors:
            print(f"\n错误示例:")
            for error in result.errors[:5]:
                print(f"  - {error}")
    
    def save_test_results(self, results: List[TestResult], filename: str):
        """保存测试结果到文件"""
        try:
            data = {
                "test_time": datetime.now().isoformat(),
                "results": [
                    {
                        "test_name": r.test_name,
                        "total_requests": r.total_requests,
                        "successful_requests": r.successful_requests,
                        "failed_requests": r.failed_requests,
                        "total_time": r.total_time,
                        "average_response_time": r.average_response_time,
                        "min_response_time": r.min_response_time,
                        "max_response_time": r.max_response_time,
                        "requests_per_second": r.requests_per_second,
                        "error_rate": r.error_rate,
                        "errors": r.errors
                    }
                    for r in results
                ]
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"\n测试结果已保存到: {filename}")
        except Exception as e:
            print(f"保存测试结果失败: {e}")

async def run_concurrent_tests():
    """运行并发测试"""
    print("🚀 开始并发压力测试")
    print("="*60)
    
    # 测试配置
    test_configs = [
        {"users": 10, "requests": 5, "name": "轻量级测试"},
        {"users": 25, "requests": 4, "name": "中等负载测试"},
        {"users": 50, "requests": 3, "name": "高负载测试"},
        {"users": 100, "requests": 2, "name": "极限负载测试"}
    ]
    
    all_results = []
    
    async with ConcurrentTester() as tester:
        for config in test_configs:
            print(f"\n🧪 {config['name']}: {config['users']}个并发用户, 每用户{config['requests']}个请求")
            print("-" * 60)
            
            # 健康检查测试
            health_result = await tester.test_health_check(config["users"], config["requests"])
            tester.print_test_result(health_result)
            all_results.append(health_result)
            
            # API端点测试
            api_results = await tester.test_api_endpoints(config["users"], config["requests"])
            for result in api_results:
                tester.print_test_result(result)
                all_results.append(result)
            
            # 数据库操作测试
            db_result = await tester.test_database_operations(config["users"], config["requests"])
            tester.print_test_result(db_result)
            all_results.append(db_result)
            
            # 等待一段时间再进行下一轮测试
            print(f"\n⏳ 等待5秒后进行下一轮测试...")
            await asyncio.sleep(5)
    
    # 保存所有测试结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"temp/outputs/concurrent_test_results_{timestamp}.json"
    tester.save_test_results(all_results, filename)
    
    print(f"\n🎉 并发压力测试完成！")
    print(f"总共执行了 {len(all_results)} 个测试")
    print(f"结果已保存到: {filename}")

if __name__ == "__main__":
    asyncio.run(run_concurrent_tests())
