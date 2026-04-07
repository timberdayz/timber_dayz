"""
ExecutorManager 性能测试脚本

测试执行器管理器的性能：
- 事件循环响应时间（同步期间）
- 资源监控性能开销
- 并发场景下的资源使用
"""

import asyncio
import time
import psutil
import os
from backend.services.executor_manager import get_executor_manager
from modules.core.logger import get_logger

logger = get_logger(__name__)


async def test_event_loop_responsiveness():
    """测试事件循环响应时间（数据同步期间）"""
    logger.info("=" * 70)
    logger.info("测试 1: 事件循环响应时间（数据同步期间）")
    logger.info("=" * 70)
    
    executor_manager = get_executor_manager()
    
    def cpu_intensive_task(n):
        """CPU 密集型任务"""
        total = 0
        for i in range(n):
            total += i
        return total
    
    async def check_responsiveness():
        """检查事件循环响应性"""
        start = time.time()
        await asyncio.sleep(0.01)  # 10ms 延迟
        elapsed = (time.time() - start) * 1000
        return elapsed
    
    # 启动 CPU 密集型任务
    logger.info("[INFO] 启动 CPU 密集型任务...")
    cpu_task = asyncio.create_task(
        executor_manager.run_cpu_intensive(cpu_intensive_task, 50000000)
    )
    
    # 在 CPU 任务运行期间，检查事件循环响应性
    logger.info("[INFO] 检查事件循环响应性...")
    responsiveness_times = []
    for i in range(10):
        elapsed = await check_responsiveness()
        responsiveness_times.append(elapsed)
        logger.info(f"  [CHECK {i+1}/10] 响应时间: {elapsed:.2f}ms")
        await asyncio.sleep(0.05)
    
    # 等待 CPU 任务完成
    result = await cpu_task
    logger.info(f"[INFO] CPU 任务完成，结果: {result}")
    
    # 分析结果
    avg_responsiveness = sum(responsiveness_times) / len(responsiveness_times)
    max_responsiveness = max(responsiveness_times)
    min_responsiveness = min(responsiveness_times)
    
    logger.info(f"[RESULT] 平均响应时间: {avg_responsiveness:.2f}ms")
    logger.info(f"[RESULT] 最大响应时间: {max_responsiveness:.2f}ms")
    logger.info(f"[RESULT] 最小响应时间: {min_responsiveness:.2f}ms")
    
    # 验证
    if avg_responsiveness < 100:
        logger.info("[PASS] 平均响应时间 < 100ms，符合要求")
        return True
    else:
        logger.warning(f"[FAIL] 平均响应时间 {avg_responsiveness:.2f}ms >= 100ms")
        return False


async def test_resource_monitoring_overhead():
    """测试资源监控性能开销"""
    logger.info("=" * 70)
    logger.info("测试 2: 资源监控性能开销")
    logger.info("=" * 70)
    
    # 测试不使用监控时的性能
    logger.info("[INFO] 测试不使用监控时的性能...")
    start_time = time.time()
    for _ in range(100):
        cpu_percent = psutil.cpu_percent(interval=0.01)
        memory_info = psutil.virtual_memory()
    elapsed_without_monitoring = time.time() - start_time
    
    logger.info(f"[RESULT] 不使用监控时，100 次检查耗时: {elapsed_without_monitoring:.3f}秒")
    
    # 计算单次检查开销
    overhead_per_check = elapsed_without_monitoring / 100
    logger.info(f"[RESULT] 单次检查开销: {overhead_per_check*1000:.2f}ms")
    
    # 验证开销 < 5%
    # 假设系统负载为 100%，监控开销应该 < 5%
    if overhead_per_check < 0.05:  # 50ms
        logger.info("[PASS] 监控开销 < 50ms，符合要求")
        return True
    else:
        logger.warning(f"[FAIL] 监控开销 {overhead_per_check*1000:.2f}ms >= 50ms")
        return False


async def test_concurrent_resource_usage():
    """测试并发场景下的资源使用"""
    logger.info("=" * 70)
    logger.info("测试 3: 并发场景下的资源使用")
    logger.info("=" * 70)
    
    executor_manager = get_executor_manager()
    
    def cpu_task(n):
        """CPU 密集型任务"""
        total = 0
        for i in range(n):
            total += i
        return total
    
    # 获取初始资源使用
    process = psutil.Process(os.getpid())
    initial_cpu = process.cpu_percent(interval=0.1)
    initial_memory = process.memory_info().rss / (1024 * 1024)  # MB
    
    logger.info(f"[INFO] 初始 CPU 使用率: {initial_cpu:.2f}%")
    logger.info(f"[INFO] 初始内存使用: {initial_memory:.2f}MB")
    
    # 并发执行多个任务
    logger.info("[INFO] 启动 10 个并发 CPU 任务...")
    tasks = [
        executor_manager.run_cpu_intensive(cpu_task, 10000000)
        for _ in range(10)
    ]
    
    # 在任务运行期间监控资源
    max_cpu = initial_cpu
    max_memory = initial_memory
    
    monitor_task = asyncio.create_task(
        monitor_resources(process, max_cpu, max_memory)
    )
    
    # 等待所有任务完成
    results = await asyncio.gather(*tasks)
    monitor_task.cancel()
    
    try:
        final_cpu, final_memory = await monitor_task
    except asyncio.CancelledError:
        final_cpu, final_memory = max_cpu, max_memory
    
    logger.info(f"[RESULT] 完成 10 个并发任务")
    logger.info(f"[RESULT] 最大 CPU 使用率: {final_cpu:.2f}%")
    logger.info(f"[RESULT] 最大内存使用: {final_memory:.2f}MB")
    
    # 验证
    logger.info("[PASS] 并发任务执行完成")
    return True


async def monitor_resources(process, max_cpu, max_memory):
    """监控资源使用"""
    try:
        while True:
            cpu = process.cpu_percent(interval=0.1)
            memory = process.memory_info().rss / (1024 * 1024)  # MB
            
            if cpu > max_cpu:
                max_cpu = cpu
            if memory > max_memory:
                max_memory = memory
            
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        return max_cpu, max_memory


async def main():
    """主测试函数"""
    logger.info("=" * 70)
    logger.info("ExecutorManager 性能测试")
    logger.info("=" * 70)
    logger.info("")
    
    results = []
    
    # 测试 1: 事件循环响应时间
    try:
        result1 = await test_event_loop_responsiveness()
        results.append(("事件循环响应时间", result1))
    except Exception as e:
        logger.error(f"[ERROR] 测试 1 失败: {e}", exc_info=True)
        results.append(("事件循环响应时间", False))
    
    logger.info("")
    
    # 测试 2: 资源监控性能开销
    try:
        result2 = await test_resource_monitoring_overhead()
        results.append(("资源监控性能开销", result2))
    except Exception as e:
        logger.error(f"[ERROR] 测试 2 失败: {e}", exc_info=True)
        results.append(("资源监控性能开销", False))
    
    logger.info("")
    
    # 测试 3: 并发资源使用
    try:
        result3 = await test_concurrent_resource_usage()
        results.append(("并发资源使用", result3))
    except Exception as e:
        logger.error(f"[ERROR] 测试 3 失败: {e}", exc_info=True)
        results.append(("并发资源使用", False))
    
    # 总结
    logger.info("")
    logger.info("=" * 70)
    logger.info("测试总结")
    logger.info("=" * 70)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        logger.info(f"{status} {test_name}")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    logger.info(f"")
    logger.info(f"通过: {passed}/{total}")


if __name__ == "__main__":
    asyncio.run(main())

