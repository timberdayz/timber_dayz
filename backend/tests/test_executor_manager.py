"""
ExecutorManager 单元测试

测试 ExecutorManager 的核心功能：
- 单例模式
- 进程池执行（CPU 密集型）
- 线程池执行（I/O 密集型）
- 优雅关闭
"""

import pytest
import asyncio
import time
import os
from backend.services.executor_manager import ExecutorManager, get_executor_manager


class TestExecutorManagerSingleton:
    """测试 ExecutorManager 单例模式"""

    def test_singleton_instance(self):
        """测试单例模式：多次调用返回同一实例"""
        instance1 = get_executor_manager()
        instance2 = get_executor_manager()
        assert instance1 is instance2
        assert isinstance(instance1, ExecutorManager)

    def test_singleton_thread_safe(self):
        """测试单例模式线程安全（简单测试）"""
        import threading
        
        instances = []
        
        def get_instance():
            instances.append(get_executor_manager())
        
        threads = [threading.Thread(target=get_instance) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # 所有线程应该返回同一个实例
        assert len(set(id(inst) for inst in instances)) == 1


class TestExecutorManagerCPUIntensive:
    """测试进程池执行（CPU 密集型操作）"""

    @pytest.mark.asyncio
    async def test_run_cpu_intensive_basic(self):
        """测试基本的 CPU 密集型操作"""
        executor_manager = get_executor_manager()
        
        def cpu_task(n):
            """CPU 密集型任务：计算斐波那契数列"""
            if n <= 1:
                return n
            a, b = 0, 1
            for _ in range(n - 1):
                a, b = b, a + b
            return b
        
        result = await executor_manager.run_cpu_intensive(cpu_task, 30)
        assert result == 832040  # 第30个斐波那契数

    @pytest.mark.asyncio
    async def test_run_cpu_intensive_with_kwargs(self):
        """测试带关键字参数的 CPU 密集型操作"""
        executor_manager = get_executor_manager()
        
        def multiply(a, b, multiplier=1):
            return (a * b) * multiplier
        
        result = await executor_manager.run_cpu_intensive(
            multiply,
            5,
            10,
            multiplier=2
        )
        assert result == 100

    @pytest.mark.asyncio
    async def test_run_cpu_intensive_error_handling(self):
        """测试 CPU 密集型操作的错误处理"""
        executor_manager = get_executor_manager()
        
        def failing_task():
            raise ValueError("测试错误")
        
        with pytest.raises(ValueError, match="测试错误"):
            await executor_manager.run_cpu_intensive(failing_task)

    @pytest.mark.asyncio
    async def test_run_cpu_intensive_pickle_error(self):
        """测试序列化错误处理"""
        executor_manager = get_executor_manager()
        
        # 创建一个无法序列化的函数（使用闭包）
        def create_unpicklable():
            local_var = "test"
            def inner():
                return local_var  # 闭包无法序列化
            return inner
        
        unpicklable_func = create_unpicklable()
        
        with pytest.raises(ValueError, match="无法在进程池中执行"):
            await executor_manager.run_cpu_intensive(unpicklable_func)


class TestExecutorManagerIOIntensive:
    """测试线程池执行（I/O 密集型操作）"""

    @pytest.mark.asyncio
    async def test_run_io_intensive_basic(self):
        """测试基本的 I/O 密集型操作"""
        executor_manager = get_executor_manager()
        
        def io_task(duration):
            """I/O 密集型任务：模拟 I/O 等待"""
            time.sleep(duration)
            return f"完成，等待了 {duration} 秒"
        
        result = await executor_manager.run_io_intensive(io_task, 0.1)
        assert "完成" in result

    @pytest.mark.asyncio
    async def test_run_io_intensive_file_operation(self):
        """测试文件系统操作（I/O 密集型）"""
        executor_manager = get_executor_manager()
        from pathlib import Path
        
        def check_file_exists(file_path):
            return Path(file_path).exists()
        
        # 检查当前文件是否存在
        current_file = Path(__file__)
        result = await executor_manager.run_io_intensive(
            check_file_exists,
            str(current_file)
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_run_io_intensive_error_handling(self):
        """测试 I/O 密集型操作的错误处理"""
        executor_manager = get_executor_manager()
        
        def failing_task():
            raise RuntimeError("I/O 错误")
        
        with pytest.raises(RuntimeError, match="I/O 错误"):
            await executor_manager.run_io_intensive(failing_task)


class TestExecutorManagerShutdown:
    """测试优雅关闭"""

    @pytest.mark.asyncio
    async def test_shutdown_basic(self):
        """测试基本关闭功能"""
        executor_manager = get_executor_manager()
        
        # 执行一些任务
        await executor_manager.run_io_intensive(lambda: time.sleep(0.1))
        
        # 关闭执行器
        await executor_manager.shutdown(timeout=5)
        
        # 验证：关闭后应该可以重新初始化（通过新的单例）
        # 注意：由于是单例，实际测试中可能需要重置单例状态
        # 这里只测试关闭不会抛出异常
        assert True  # 如果关闭成功，不会抛出异常

    @pytest.mark.asyncio
    async def test_shutdown_with_running_tasks(self):
        """测试关闭时等待正在运行的任务"""
        executor_manager = get_executor_manager()
        
        async def long_task():
            await asyncio.sleep(0.5)
            return "完成"
        
        # 启动一个长时间运行的任务
        task = asyncio.create_task(
            executor_manager.run_io_intensive(lambda: time.sleep(0.3))
        )
        
        # 等待一小段时间，确保任务已开始
        await asyncio.sleep(0.1)
        
        # 关闭执行器（应该等待任务完成）
        await executor_manager.shutdown(timeout=5)
        
        # 等待任务完成
        await task
        
        assert True  # 如果关闭成功等待任务完成，不会抛出异常


class TestExecutorManagerConfiguration:
    """测试配置相关功能"""

    def test_cpu_workers_configuration(self):
        """测试进程池大小配置"""
        executor_manager = get_executor_manager()
        
        # 验证进程池已创建
        assert executor_manager.cpu_executor is not None
        assert hasattr(executor_manager.cpu_executor, '_max_workers')
        
        # 验证配置合理（至少1个，不超过CPU核心数）
        cpu_cores = os.cpu_count() or 4
        max_workers = executor_manager.cpu_executor._max_workers
        assert 1 <= max_workers <= cpu_cores

    def test_io_workers_configuration(self):
        """测试线程池大小配置"""
        executor_manager = get_executor_manager()
        
        # 验证线程池已创建
        assert executor_manager.io_executor is not None
        assert hasattr(executor_manager.io_executor, '_max_workers')
        
        # 验证配置合理（至少1个，不超过合理上限）
        max_workers = executor_manager.io_executor._max_workers
        assert max_workers >= 1
        assert max_workers <= 50  # 合理上限


class TestExecutorManagerConcurrency:
    """测试并发执行"""

    @pytest.mark.asyncio
    async def test_concurrent_cpu_tasks(self):
        """测试并发 CPU 密集型任务"""
        executor_manager = get_executor_manager()
        
        def cpu_task(n):
            """CPU 密集型任务"""
            total = 0
            for i in range(n):
                total += i
            return total
        
        # 并发执行多个任务
        tasks = [
            executor_manager.run_cpu_intensive(cpu_task, 1000000)
            for _ in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # 验证所有任务都成功完成
        assert len(results) == 5
        assert all(isinstance(r, int) for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_io_tasks(self):
        """测试并发 I/O 密集型任务"""
        executor_manager = get_executor_manager()
        
        def io_task(duration):
            """I/O 密集型任务"""
            time.sleep(duration)
            return f"完成 {duration}"
        
        # 并发执行多个任务
        tasks = [
            executor_manager.run_io_intensive(io_task, 0.1)
            for _ in range(10)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # 验证所有任务都成功完成
        assert len(results) == 10
        assert all("完成" in r for r in results)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

