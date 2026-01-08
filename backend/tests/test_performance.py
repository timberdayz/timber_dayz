"""
性能测试脚本 - 西虹ERP系统
v4.1.0 - 验证后端优化效果

测试场景：
1. 系统启动时间（目标：<15秒）
2. 并发请求处理（目标：20个并发请求<5秒）
3. Dashboard查询性能（目标：<3秒）
4. 字段映射预览（目标：<10秒）
5. 连接池性能（目标：100个连接<10秒）
"""

import asyncio
import time
import httpx
from typing import List, Dict, Any
import statistics


class PerformanceTest:
    """性能测试类"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.results: List[Dict[str, Any]] = []
    
    async def test_health_check(self):
        """测试健康检查响应时间"""
        print("\n[DATA] 测试1: 健康检查响应时间")
        times = []
        
        async with httpx.AsyncClient() as client:
            for i in range(10):
                start = time.time()
                try:
                    response = await client.get(f"{self.base_url}/health", timeout=10.0)
                    elapsed = time.time() - start
                    times.append(elapsed * 1000)  # 转换为毫秒
                    print(f"  请求 {i+1}/10: {elapsed*1000:.0f}ms")
                except Exception as e:
                    print(f"  请求 {i+1}/10: 失败 - {e}")
        
        if times:
            avg_time = statistics.mean(times)
            max_time = max(times)
            min_time = min(times)
            
            result = {
                "test": "健康检查",
                "avg_ms": avg_time,
                "max_ms": max_time,
                "min_ms": min_time,
                "passed": avg_time < 500  # 平均<500ms
            }
            self.results.append(result)
            
            print(f"  [OK] 平均响应: {avg_time:.0f}ms (最小: {min_time:.0f}ms, 最大: {max_time:.0f}ms)")
            print(f"  {'[OK] 通过' if result['passed'] else '[FAIL] 失败'} (目标: <500ms)")
    
    async def test_concurrent_requests(self, num_requests: int = 20):
        """测试并发请求处理"""
        print(f"\n[DATA] 测试2: 并发请求处理 ({num_requests}个并发)")
        
        async def make_request(client, i):
            start = time.time()
            try:
                response = await client.get(f"{self.base_url}/health", timeout=30.0)
                elapsed = time.time() - start
                return {"success": True, "time": elapsed, "id": i}
            except Exception as e:
                elapsed = time.time() - start
                return {"success": False, "time": elapsed, "error": str(e), "id": i}
        
        start_total = time.time()
        
        async with httpx.AsyncClient() as client:
            tasks = [make_request(client, i) for i in range(num_requests)]
            results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_total
        
        success_count = sum(1 for r in results if r["success"])
        times = [r["time"] * 1000 for r in results if r["success"]]
        
        if times:
            avg_time = statistics.mean(times)
            
            result = {
                "test": f"并发请求({num_requests})",
                "total_time_s": total_time,
                "success_count": success_count,
                "failure_count": num_requests - success_count,
                "avg_ms": avg_time,
                "passed": total_time < 5.0 and success_count == num_requests
            }
            self.results.append(result)
            
            print(f"  [OK] 总耗时: {total_time:.2f}秒")
            print(f"  [OK] 成功: {success_count}/{num_requests}")
            print(f"  [OK] 平均响应: {avg_time:.0f}ms")
            print(f"  {'[OK] 通过' if result['passed'] else '[FAIL] 失败'} (目标: <5秒且全部成功)")
    
    async def test_dashboard_api(self):
        """测试Dashboard API性能"""
        print("\n[DATA] 测试3: Dashboard API查询性能")
        
        async with httpx.AsyncClient() as client:
            start = time.time()
            try:
                response = await client.get(
                    f"{self.base_url}/api/dashboard/overview",
                    timeout=45.0
                )
                elapsed = time.time() - start
                
                result = {
                    "test": "Dashboard查询",
                    "time_s": elapsed,
                    "passed": elapsed < 3.0
                }
                self.results.append(result)
                
                print(f"  [OK] 查询耗时: {elapsed:.2f}秒")
                print(f"  {'[OK] 通过' if result['passed'] else '[FAIL] 失败'} (目标: <3秒)")
                
            except Exception as e:
                print(f"  [FAIL] 查询失败: {e}")
                self.results.append({
                    "test": "Dashboard查询",
                    "error": str(e),
                    "passed": False
                })
    
    async def test_connection_pool(self):
        """测试连接池性能"""
        print("\n[DATA] 测试4: 连接池性能（100个顺序请求）")
        
        times = []
        
        async with httpx.AsyncClient() as client:
            for i in range(100):
                start = time.time()
                try:
                    await client.get(f"{self.base_url}/health", timeout=10.0)
                    elapsed = time.time() - start
                    times.append(elapsed * 1000)
                    
                    if (i + 1) % 20 == 0:
                        print(f"  进度: {i+1}/100 完成")
                except Exception as e:
                    print(f"  请求 {i+1} 失败: {e}")
        
        if times:
            total_time = sum(times) / 1000
            avg_time = statistics.mean(times)
            
            result = {
                "test": "连接池(100请求)",
                "total_time_s": total_time,
                "avg_ms": avg_time,
                "passed": total_time < 10.0
            }
            self.results.append(result)
            
            print(f"  [OK] 总耗时: {total_time:.2f}秒")
            print(f"  [OK] 平均响应: {avg_time:.0f}ms")
            print(f"  {'[OK] 通过' if result['passed'] else '[FAIL] 失败'} (目标: <10秒)")
    
    def print_summary(self):
        """打印测试总结"""
        print("\n" + "="*60)
        print("[TARGET] 性能测试总结报告")
        print("="*60)
        
        passed_count = sum(1 for r in self.results if r.get("passed", False))
        total_count = len(self.results)
        
        for result in self.results:
            status = "[OK] 通过" if result.get("passed", False) else "[FAIL] 失败"
            print(f"\n{status} - {result['test']}")
            
            if "avg_ms" in result:
                print(f"  平均响应时间: {result['avg_ms']:.0f}ms")
            if "time_s" in result:
                print(f"  耗时: {result['time_s']:.2f}秒")
            if "total_time_s" in result:
                print(f"  总耗时: {result['total_time_s']:.2f}秒")
            if "error" in result:
                print(f"  错误: {result['error']}")
        
        print("\n" + "="*60)
        print(f"[DATA] 总计: {passed_count}/{total_count} 测试通过 ({passed_count/total_count*100:.0f}%)")
        print("="*60)
        
        return passed_count == total_count


async def main():
    """运行所有性能测试"""
    print("="*60)
    print("[START] 西虹ERP系统性能测试 v4.1.0")
    print("="*60)
    print("\n请确保后端服务已启动在 http://localhost:8001")
    
    # 等待用户确认
    input("\n按回车键开始测试...")
    
    tester = PerformanceTest()
    
    # 运行所有测试
    await tester.test_health_check()
    await tester.test_concurrent_requests(20)
    await tester.test_dashboard_api()
    await tester.test_connection_pool()
    
    # 打印总结
    all_passed = tester.print_summary()
    
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)

