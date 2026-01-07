"""
长时间运行稳定性测试工具
"""

import asyncio
import aiohttp
import time
import json
import psutil
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Any
from dataclasses import dataclass
import statistics
import signal
import sys

@dataclass
class StabilityMetrics:
    """稳定性指标数据类"""
    timestamp: datetime
    test_duration: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_response_time: float
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    error_rate: float
    requests_per_second: float

class StabilityTester:
    """稳定性测试器"""
    
    def __init__(self, base_url: str = "http://localhost:8000", duration_hours: int = 24):
        self.base_url = base_url
        self.duration_hours = duration_hours
        self.session = None
        self.is_running = False
        self.metrics_history = []
        self.start_time = None
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.response_times = []
        self.errors = []
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """信号处理器"""
        print(f"\n收到信号 {signum}，正在停止测试...")
        self.is_running = False
    
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
    
    async def make_request(self, endpoint: str) -> Dict[str, Any]:
        """发送HTTP请求"""
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()
        
        try:
            async with self.session.get(url) as response:
                response_time = time.time() - start_time
                text = await response.text()
                
                success = response.status < 400
                if success:
                    self.successful_requests += 1
                else:
                    self.failed_requests += 1
                    self.errors.append(f"HTTP {response.status}: {text[:100]}")
                
                self.total_requests += 1
                self.response_times.append(response_time)
                
                return {
                    "success": success,
                    "status_code": response.status,
                    "response_time": response_time,
                    "response_size": len(text)
                }
        except Exception as e:
            response_time = time.time() - start_time
            self.failed_requests += 1
            self.total_requests += 1
            self.response_times.append(response_time)
            self.errors.append(str(e))
            
            return {
                "success": False,
                "status_code": 0,
                "response_time": response_time,
                "response_size": 0,
                "error": str(e)
            }
    
    async def run_stability_test(self):
        """运行稳定性测试"""
        print(f"🚀 开始稳定性测试，持续时间: {self.duration_hours} 小时")
        print("="*60)
        
        self.is_running = True
        self.start_time = datetime.now()
        
        # 测试端点列表
        endpoints = [
            "/health",
            "/api/dashboard/overview",
            "/api/inventory/",
            "/api/finance/accounts-receivable",
            "/api/roles/",
            "/api/users/"
        ]
        
        # 启动监控线程
        monitor_thread = threading.Thread(target=self._monitor_system, daemon=True)
        monitor_thread.start()
        
        try:
            while self.is_running:
                # 检查是否达到测试时间
                elapsed = (datetime.now() - self.start_time).total_seconds()
                if elapsed >= self.duration_hours * 3600:
                    print(f"\n⏰ 测试时间达到 {self.duration_hours} 小时，停止测试")
                    break
                
                # 随机选择端点进行测试
                import random
                endpoint = random.choice(endpoints)
                
                # 发送请求
                await self.make_request(endpoint)
                
                # 每100个请求显示一次进度
                if self.total_requests % 100 == 0:
                    elapsed_hours = elapsed / 3600
                    print(f"进度: {elapsed_hours:.2f}小时 / {self.duration_hours}小时, "
                          f"总请求: {self.total_requests}, "
                          f"成功率: {self.successful_requests/self.total_requests*100:.1f}%")
                
                # 随机间隔（1-5秒）
                await asyncio.sleep(random.uniform(1, 5))
                
        except KeyboardInterrupt:
            print("\n⏹️ 用户中断测试")
        except Exception as e:
            print(f"\n❌ 测试过程中发生错误: {e}")
        finally:
            self.is_running = False
            await self._generate_final_report()
    
    def _monitor_system(self):
        """系统监控线程"""
        while self.is_running:
            try:
                # 获取系统指标
                cpu_percent = psutil.cpu_percent(interval=1)
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
                memory_used_mb = memory.used / (1024 * 1024)
                
                # 计算测试指标
                elapsed = (datetime.now() - self.start_time).total_seconds()
                requests_per_second = self.total_requests / elapsed if elapsed > 0 else 0
                error_rate = self.failed_requests / self.total_requests * 100 if self.total_requests > 0 else 0
                avg_response_time = statistics.mean(self.response_times[-100:]) if self.response_times else 0
                
                # 记录指标
                metrics = StabilityMetrics(
                    timestamp=datetime.now(),
                    test_duration=elapsed,
                    total_requests=self.total_requests,
                    successful_requests=self.successful_requests,
                    failed_requests=self.failed_requests,
                    average_response_time=avg_response_time,
                    cpu_percent=cpu_percent,
                    memory_percent=memory_percent,
                    memory_used_mb=memory_used_mb,
                    error_rate=error_rate,
                    requests_per_second=requests_per_second
                )
                
                self.metrics_history.append(metrics)
                
                # 每5分钟记录一次详细指标
                if len(self.metrics_history) % 300 == 0:  # 5分钟 = 300秒
                    print(f"\n📊 系统指标 (运行时间: {elapsed/3600:.2f}小时)")
                    print(f"  CPU使用率: {cpu_percent:.1f}%")
                    print(f"  内存使用率: {memory_percent:.1f}% ({memory_used_mb:.1f}MB)")
                    print(f"  总请求数: {self.total_requests}")
                    print(f"  成功率: {(self.successful_requests/self.total_requests*100):.1f}%")
                    print(f"  平均响应时间: {avg_response_time:.3f}秒")
                    print(f"  每秒请求数: {requests_per_second:.2f}")
                
                time.sleep(1)  # 每秒监控一次
                
            except Exception as e:
                print(f"监控线程错误: {e}")
                time.sleep(5)
    
    async def _generate_final_report(self):
        """生成最终报告"""
        print(f"\n📋 生成稳定性测试报告...")
        
        if not self.metrics_history:
            print("❌ 没有收集到监控数据")
            return
        
        # 计算总体统计
        total_duration = (datetime.now() - self.start_time).total_seconds()
        final_metrics = self.metrics_history[-1]
        
        # 计算趋势
        cpu_values = [m.cpu_percent for m in self.metrics_history]
        memory_values = [m.memory_percent for m in self.metrics_history]
        response_times = [m.average_response_time for m in self.metrics_history]
        
        report = {
            "test_summary": {
                "start_time": self.start_time.isoformat(),
                "end_time": datetime.now().isoformat(),
                "total_duration_hours": total_duration / 3600,
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "final_success_rate": final_metrics.error_rate,
                "final_requests_per_second": final_metrics.requests_per_second
            },
            "system_performance": {
                "cpu": {
                    "average": statistics.mean(cpu_values),
                    "max": max(cpu_values),
                    "min": min(cpu_values),
                    "final": final_metrics.cpu_percent
                },
                "memory": {
                    "average_percent": statistics.mean(memory_values),
                    "max_percent": max(memory_values),
                    "min_percent": min(memory_values),
                    "final_percent": final_metrics.memory_percent,
                    "final_used_mb": final_metrics.memory_used_mb
                },
                "response_time": {
                    "average": statistics.mean(response_times),
                    "max": max(response_times),
                    "min": min(response_times),
                    "final": final_metrics.average_response_time
                }
            },
            "stability_analysis": {
                "cpu_stability": "stable" if max(cpu_values) - min(cpu_values) < 20 else "unstable",
                "memory_stability": "stable" if max(memory_values) - min(memory_values) < 20 else "unstable",
                "response_time_stability": "stable" if max(response_times) - min(response_times) < 1.0 else "unstable",
                "error_rate_stability": "stable" if final_metrics.error_rate < 5 else "unstable"
            },
            "detailed_metrics": [
                {
                    "timestamp": m.timestamp.isoformat(),
                    "test_duration": m.test_duration,
                    "total_requests": m.total_requests,
                    "successful_requests": m.successful_requests,
                    "failed_requests": m.failed_requests,
                    "average_response_time": m.average_response_time,
                    "cpu_percent": m.cpu_percent,
                    "memory_percent": m.memory_percent,
                    "memory_used_mb": m.memory_used_mb,
                    "error_rate": m.error_rate,
                    "requests_per_second": m.requests_per_second
                }
                for m in self.metrics_history
            ],
            "errors": self.errors[-50:]  # 最后50个错误
        }
        
        # 保存报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"temp/outputs/stability_test_report_{timestamp}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            
            print(f"📄 稳定性测试报告已保存到: {filename}")
            
            # 打印摘要
            print(f"\n📊 稳定性测试摘要")
            print(f"{'='*60}")
            print(f"测试持续时间: {total_duration/3600:.2f} 小时")
            print(f"总请求数: {self.total_requests}")
            print(f"成功请求: {self.successful_requests}")
            print(f"失败请求: {self.failed_requests}")
            print(f"最终成功率: {(self.successful_requests/self.total_requests*100):.1f}%")
            print(f"最终每秒请求数: {final_metrics.requests_per_second:.2f}")
            print(f"最终CPU使用率: {final_metrics.cpu_percent:.1f}%")
            print(f"最终内存使用率: {final_metrics.memory_percent:.1f}%")
            print(f"最终平均响应时间: {final_metrics.average_response_time:.3f}秒")
            
            # 稳定性分析
            print(f"\n🔍 稳定性分析")
            print(f"CPU稳定性: {report['stability_analysis']['cpu_stability']}")
            print(f"内存稳定性: {report['stability_analysis']['memory_stability']}")
            print(f"响应时间稳定性: {report['stability_analysis']['response_time_stability']}")
            print(f"错误率稳定性: {report['stability_analysis']['error_rate_stability']}")
            
        except Exception as e:
            print(f"保存报告失败: {e}")

async def run_stability_test(duration_hours: int = 24):
    """运行稳定性测试"""
    print(f"🚀 开始 {duration_hours} 小时稳定性测试")
    print("按 Ctrl+C 可以提前停止测试")
    print("="*60)
    
    async with StabilityTester(duration_hours=duration_hours) as tester:
        await tester.run_stability_test()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="稳定性测试工具")
    parser.add_argument("--duration", type=int, default=24, help="测试持续时间（小时）")
    args = parser.parse_args()
    
    try:
        asyncio.run(run_stability_test(args.duration))
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
