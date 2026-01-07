"""
数据同步执行器集成测试

测试数据同步服务在进程池中执行 Excel 读取：
- 验证 ExcelParser.read_excel 在进程池中执行
- 验证数据同步不会阻塞事件循环
"""

import pytest
import asyncio
import time
from pathlib import Path
from backend.services.executor_manager import get_executor_manager
from backend.services.excel_parser import ExcelParser


class TestDataSyncExecutorIntegration:
    """数据同步执行器集成测试"""

    @pytest.mark.asyncio
    async def test_excel_parser_in_process_pool(self):
        """测试 ExcelParser.read_excel 可以在进程池中执行"""
        executor_manager = get_executor_manager()
        
        # 创建一个简单的测试 Excel 文件（如果存在）
        # 注意：实际测试需要真实的 Excel 文件
        # 这里只测试函数是否可以序列化并在进程池中执行
        
        # 测试函数是否可以序列化
        import pickle
        try:
            pickle.dumps(ExcelParser.read_excel)
            can_pickle = True
        except Exception:
            can_pickle = False
        
        assert can_pickle, "ExcelParser.read_excel 必须可序列化"

    @pytest.mark.asyncio
    async def test_event_loop_responsiveness(self):
        """测试事件循环响应性（数据同步期间）"""
        executor_manager = get_executor_manager()
        
        async def cpu_intensive_task():
            """模拟 CPU 密集型任务"""
            def heavy_computation():
                total = 0
                for i in range(10000000):
                    total += i
                return total
            
            return await executor_manager.run_cpu_intensive(heavy_computation)
        
        async def check_responsiveness():
            """检查事件循环响应性"""
            start_time = time.time()
            await asyncio.sleep(0.01)  # 10ms 延迟
            elapsed = (time.time() - start_time) * 1000  # 转换为毫秒
            return elapsed
        
        # 启动 CPU 密集型任务
        cpu_task = asyncio.create_task(cpu_intensive_task())
        
        # 在 CPU 密集型任务运行期间，检查事件循环响应性
        responsiveness_times = []
        for _ in range(5):
            elapsed = await check_responsiveness()
            responsiveness_times.append(elapsed)
            await asyncio.sleep(0.01)
        
        # 等待 CPU 任务完成
        await cpu_task
        
        # 验证事件循环响应时间（应该 < 100ms）
        avg_responsiveness = sum(responsiveness_times) / len(responsiveness_times)
        assert avg_responsiveness < 100, f"事件循环响应时间 {avg_responsiveness}ms 超过 100ms"

    @pytest.mark.asyncio
    async def test_concurrent_data_sync_tasks(self):
        """测试并发数据同步任务"""
        executor_manager = get_executor_manager()
        
        def mock_excel_read(file_path):
            """模拟 Excel 读取（CPU 密集型）"""
            # 模拟读取时间
            time.sleep(0.1)
            return {"rows": 100, "columns": 10}
        
        # 并发执行多个"数据同步"任务
        tasks = [
            executor_manager.run_cpu_intensive(mock_excel_read, f"file_{i}.xlsx")
            for i in range(5)
        ]
        
        start_time = time.time()
        results = await asyncio.gather(*tasks)
        elapsed = time.time() - start_time
        
        # 验证所有任务都成功完成
        assert len(results) == 5
        assert all("rows" in r for r in results)
        
        # 验证并发执行（总时间应该小于串行执行时间）
        # 串行执行时间：5 * 0.1 = 0.5 秒
        # 并发执行时间应该明显小于 0.5 秒（取决于进程池大小）
        assert elapsed < 0.5, f"并发执行时间 {elapsed}s 应该小于串行时间 0.5s"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

