"""
执行器管理器 - 统一管理进程池和线程池

v4.19.0新增：执行器统一管理和资源优化
- 单例模式，线程安全
- 环境感知的资源配置
- CPU密集型操作使用进程池（完全隔离）
- I/O密集型操作使用线程池
"""

import threading
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import asyncio
import os
import time
from modules.core.logger import get_logger

logger = get_logger(__name__)


# ⭐ 模块级函数（可被pickle序列化到进程池）
def _cpu_test_task():
    """简单的CPU测试任务（用于健康检查）"""
    return sum(range(1000))


def _io_test_task():
    """简单的I/O测试任务（用于健康检查）"""
    import time
    time.sleep(0.01)  # 10ms延迟，模拟I/O操作
    return "ok"


class ExecutorManager:
    """执行器管理器 - 线程安全的单例模式"""
    _instance = None
    _lock = threading.Lock()
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:  # 双重检查锁定
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 防止重复初始化
        if ExecutorManager._initialized:
            return
        
        with ExecutorManager._lock:
            # 再次检查，防止多线程竞争
            if ExecutorManager._initialized:
                return
            
            # 获取CPU核心数
            cpu_cores = os.cpu_count() or 4
            
            # CPU密集型操作：进程池配置（环境变量优先，带验证）
            cpu_workers_env = os.getenv("CPU_EXECUTOR_WORKERS")
            if cpu_workers_env is not None:
                try:
                    cpu_workers = int(cpu_workers_env)
                    if cpu_workers < 0:
                        raise ValueError("CPU_EXECUTOR_WORKERS must be >= 0")
                    if cpu_workers == 0:
                        # 0表示使用默认值
                        cpu_workers = max(1, cpu_cores - 1)
                except ValueError as e:
                    logger.warning(f"Invalid CPU_EXECUTOR_WORKERS: {cpu_workers_env}, using default. Error: {e}")
                    cpu_workers = max(1, cpu_cores - 1)
            else:
                # 自动检测CPU核心数
                # ⭐ 业界常用做法：CPU核心数 - 1（为主进程预留1核）
                cpu_workers = max(1, cpu_cores - 1)
            
            # I/O线程池配置（环境变量优先，带验证）
            io_workers_env = os.getenv("IO_EXECUTOR_WORKERS")
            if io_workers_env is not None:
                try:
                    io_workers = int(io_workers_env)
                    if io_workers < 0:
                        raise ValueError("IO_EXECUTOR_WORKERS must be >= 0")
                    if io_workers == 0:
                        # 0表示使用默认值
                        io_workers = min(cpu_cores * 5, 20)
                except ValueError as e:
                    logger.warning(f"Invalid IO_EXECUTOR_WORKERS: {io_workers_env}, using default. Error: {e}")
                    io_workers = min(cpu_cores * 5, 20)
            else:
                io_workers = min(cpu_cores * 5, 20)
            
            # CPU密集型操作：使用进程池
            self.cpu_executor = ProcessPoolExecutor(
                max_workers=cpu_workers
            )
            
            # I/O密集型操作：使用线程池
            self.io_executor = ThreadPoolExecutor(
                max_workers=io_workers
            )
            
            # 存储配置值（用于监控API，避免访问私有属性）
            self.cpu_max_workers = cpu_workers
            self.io_max_workers = io_workers
            
            ExecutorManager._initialized = True
            logger.info(f"[ExecutorManager] 初始化完成 - CPU进程池: {cpu_workers}个, I/O线程池: {io_workers}个")
    
    async def run_cpu_intensive(self, func, *args, **kwargs):
        """
        运行CPU密集型操作（进程池）
        
        ⭐ v4.19.8修复：检测守护进程环境，自动降级使用线程池
        - Celery Worker 是守护进程，不允许创建子进程
        - 在守护进程中自动使用线程池代替进程池
        - 后端 API 仍使用进程池，保持最佳性能
        """
        import pickle
        import multiprocessing
        from functools import partial
        
        # ⭐ v4.19.8修复：检测是否在守护进程中运行
        # Celery Worker 等守护进程不允许创建子进程
        try:
            current_process = multiprocessing.current_process()
            is_daemon = getattr(current_process, 'daemon', False)
            
            if is_daemon:
                # 在守护进程中，降级使用线程池
                logger.debug(f"[ExecutorManager] 守护进程环境，使用线程池执行: {func.__name__}")
                return await self.run_io_intensive(func, *args, **kwargs)
        except Exception as e:
            # 如果检测失败，继续尝试进程池（可能会抛出AssertionError）
            logger.debug(f"[ExecutorManager] 守护进程检测失败，继续尝试进程池: {e}")
        
        try:
            loop = asyncio.get_running_loop()
            # ⚠️ 注意：pickle错误可能在run_in_executor调用时立即抛出（序列化参数时）
            # 也可能在await future时抛出（序列化函数或执行时）
            # ⭐ v4.19.0修复：run_in_executor不支持关键字参数，使用partial包装
            if kwargs:
                # 使用 functools.partial 绑定关键字参数
                wrapped_func = partial(func, *args, **kwargs)
                # 注意：partial 对象需要可序列化，func 和参数都需要可序列化
                future = loop.run_in_executor(
                    self.cpu_executor,
                    wrapped_func
                )
            else:
                # 没有关键字参数，直接传递位置参数
                future = loop.run_in_executor(
                    self.cpu_executor,
                    func,
                    *args
                )
            return await future
        except (pickle.PicklingError, AttributeError, TypeError) as e:
            # 如果无法序列化，记录错误并抛出明确的异常
            logger.error(f"无法序列化函数 {func.__name__} 到进程池: {e}")
            raise ValueError(
                f"函数 {func.__name__} 无法在进程池中执行。"
                f"请使用包装函数或确保函数及其参数可被pickle序列化。"
                f"错误详情: {str(e)}"
            ) from e
        except AssertionError as e:
            # ⭐ v4.19.8修复：捕获守护进程创建子进程的断言错误
            # Python 会抛出 "daemonic processes are not allowed to have children"
            if "daemonic processes" in str(e).lower():
                logger.warning(f"[ExecutorManager] 守护进程断言错误，降级使用线程池: {func.__name__}")
                return await self.run_io_intensive(func, *args, **kwargs)
            raise
        except Exception as e:
            # 捕获其他可能的错误（包括进程池执行错误）
            # ⚠️ 注意：可能包括以下异常类型：
            # - BrokenProcessPool: 进程池中的进程崩溃
            # - TimeoutError: 任务执行超时（如果设置了超时）
            # - RuntimeError: 进程池已关闭
            # - 其他执行时异常：函数执行过程中抛出的异常
            logger.error(f"进程池执行失败: {func.__name__}, 错误类型: {type(e).__name__}, 错误: {e}")
            raise
    
    async def run_io_intensive(self, func, *args, **kwargs):
        """
        运行I/O密集型操作（线程池）
        
        ⭐ v4.19.8修复：run_in_executor 不支持关键字参数，使用 partial 包装
        """
        from functools import partial
        
        try:
            loop = asyncio.get_running_loop()
            # ⭐ v4.19.8修复：run_in_executor 不支持关键字参数，使用 partial 包装
            if kwargs:
                # 使用 functools.partial 绑定关键字参数
                wrapped_func = partial(func, *args, **kwargs)
                return await loop.run_in_executor(
                    self.io_executor,
                    wrapped_func
                )
            else:
                # 没有关键字参数，直接传递位置参数
                return await loop.run_in_executor(
                    self.io_executor,
                    func,
                    *args
                )
        except RuntimeError as e:
            # 线程池已关闭或其他运行时错误
            logger.error(f"线程池执行失败: {func.__name__}, 错误类型: {type(e).__name__}, 错误: {e}")
            raise
        except Exception as e:
            # 捕获其他可能的错误（包括任务执行异常）
            logger.error(f"线程池执行失败: {func.__name__}, 错误类型: {type(e).__name__}, 错误: {e}")
            raise
    
    async def shutdown(self, timeout: int = 30):
        """优雅关闭执行器"""
        # 使用标志位跟踪关闭请求状态（避免访问私有属性）
        cpu_shutdown_requested = False
        io_shutdown_requested = False
        
        # 关闭进程池（不等待，允许任务继续执行）
        if not cpu_shutdown_requested:
            try:
                self.cpu_executor.shutdown(wait=False)
                cpu_shutdown_requested = True
                logger.info("[ExecutorManager] 进程池关闭请求已发送")
            except Exception as e:
                logger.warning(f"[ExecutorManager] 关闭进程池时出错: {e}")
        
        # 关闭线程池（不等待，允许任务继续执行）
        if not io_shutdown_requested:
            try:
                self.io_executor.shutdown(wait=False)
                io_shutdown_requested = True
                logger.info("[ExecutorManager] 线程池关闭请求已发送")
            except Exception as e:
                logger.warning(f"[ExecutorManager] 关闭线程池时出错: {e}")
        
        # 等待任务完成（最多等待timeout秒）
        # ⚠️ 注意：ProcessPoolExecutor和ThreadPoolExecutor没有公开API检查任务状态
        # 这里只能等待，无法精确判断任务是否完成
        start_time = time.time()
        wait_interval = 0.5  # 每0.5秒检查一次
        
        while (time.time() - start_time) < timeout:
            elapsed = time.time() - start_time
            if elapsed >= timeout * 0.8:  # 80%时间后准备强制关闭
                logger.info(f"[ExecutorManager] 等待时间已过80%({elapsed:.1f}秒)，准备强制关闭")
                break
            await asyncio.sleep(wait_interval)
        
        # 强制关闭（等待剩余任务完成）
        # ⚠️ 注意：即使第一次调用shutdown(wait=False)成功，也需要调用shutdown(wait=True)等待任务完成
        # shutdown()方法是幂等的，可以安全地多次调用
        if cpu_shutdown_requested:
            try:
                logger.info("[ExecutorManager] 等待进程池任务完成...")
                self.cpu_executor.shutdown(wait=True)
                logger.info("[ExecutorManager] 进程池已完全关闭")
            except Exception as e:
                logger.warning(f"[ExecutorManager] 等待进程池关闭时出错: {e}")
        else:
            # 如果第一次调用失败，尝试直接关闭
            try:
                logger.info("[ExecutorManager] 强制关闭进程池（等待任务完成）")
                self.cpu_executor.shutdown(wait=True)
            except Exception as e:
                logger.warning(f"[ExecutorManager] 强制关闭进程池时出错: {e}")
        
        if io_shutdown_requested:
            try:
                logger.info("[ExecutorManager] 等待线程池任务完成...")
                self.io_executor.shutdown(wait=True)
                logger.info("[ExecutorManager] 线程池已完全关闭")
            except Exception as e:
                logger.warning(f"[ExecutorManager] 等待线程池关闭时出错: {e}")
        else:
            # 如果第一次调用失败，尝试直接关闭
            try:
                logger.info("[ExecutorManager] 强制关闭线程池（等待任务完成）")
                self.io_executor.shutdown(wait=True)
            except Exception as e:
                logger.warning(f"[ExecutorManager] 强制关闭线程池时出错: {e}")
        
        logger.info("[ExecutorManager] 所有执行器已关闭")
    
    async def check_health(self, timeout: float = 2.0):
        """
        检查执行器健康状态
        
        Args:
            timeout: 健康检查超时时间（秒），默认2秒
            
        Returns:
            Dict[str, Any]: 健康状态信息
            - cpu_executor: 进程池健康状态
                - status: "healthy" | "unhealthy" | "error"
                - max_workers: 最大worker数
                - response_time_ms: 响应时间（毫秒）
                - error: 错误信息（如果有）
            - io_executor: 线程池健康状态
                - status: "healthy" | "unhealthy" | "error"
                - max_workers: 最大worker数
                - response_time_ms: 响应时间（毫秒）
                - error: 错误信息（如果有）
            - overall_status: "healthy" | "unhealthy" | "error"
        """
        from typing import Dict, Any
        
        # ⭐ 修复：安全导入 BrokenProcessPool（兼容不同Python版本和环境）
        try:
            from concurrent.futures import BrokenProcessPool
        except ImportError:
            # 如果无法导入 BrokenProcessPool，使用 RuntimeError 作为替代
            # BrokenProcessPool 是 RuntimeError 的子类，捕获 RuntimeError 也能捕获 BrokenProcessPool
            BrokenProcessPool = RuntimeError
        
        health_status = {
            "cpu_executor": {
                "status": "unknown",
                "max_workers": self.cpu_max_workers,
                "response_time_ms": None,
                "error": None
            },
            "io_executor": {
                "status": "unknown",
                "max_workers": self.io_max_workers,
                "response_time_ms": None,
                "error": None
            },
            "overall_status": "unknown"
        }
        
        # 检查进程池健康状态
        try:
            # ⭐ 使用模块级函数（可被pickle序列化）
            start_time = time.time()
            result = await asyncio.wait_for(
                self.run_cpu_intensive(_cpu_test_task),
                timeout=timeout
            )
            response_time = (time.time() - start_time) * 1000  # 转换为毫秒
            
            health_status["cpu_executor"]["status"] = "healthy"
            health_status["cpu_executor"]["response_time_ms"] = round(response_time, 2)
            
        except asyncio.TimeoutError:
            health_status["cpu_executor"]["status"] = "unhealthy"
            health_status["cpu_executor"]["error"] = f"进程池响应超时（>{timeout}秒）"
        except (BrokenProcessPool, RuntimeError) as e:
            # ⭐ 修复：同时捕获 BrokenProcessPool 和 RuntimeError
            # 因为 BrokenProcessPool 是 RuntimeError 的子类，在某些环境下可能无法导入
            if "BrokenProcessPool" in str(type(e)) or "broken" in str(e).lower():
                health_status["cpu_executor"]["status"] = "error"
                health_status["cpu_executor"]["error"] = "进程池已损坏"
            else:
                health_status["cpu_executor"]["status"] = "error"
                health_status["cpu_executor"]["error"] = f"进程池错误: {str(e)}"
        except Exception as e:
            health_status["cpu_executor"]["status"] = "error"
            health_status["cpu_executor"]["error"] = f"进程池错误: {str(e)}"
        except Exception as e:
            health_status["cpu_executor"]["status"] = "error"
            health_status["cpu_executor"]["error"] = f"进程池检查失败: {str(e)}"
        
        # 检查线程池健康状态
        try:
            # ⭐ 使用模块级函数（可被pickle序列化，虽然线程池不需要pickle，但保持一致）
            start_time = time.time()
            result = await asyncio.wait_for(
                self.run_io_intensive(_io_test_task),
                timeout=timeout
            )
            response_time = (time.time() - start_time) * 1000  # 转换为毫秒
            
            health_status["io_executor"]["status"] = "healthy"
            health_status["io_executor"]["response_time_ms"] = round(response_time, 2)
            
        except asyncio.TimeoutError:
            health_status["io_executor"]["status"] = "unhealthy"
            health_status["io_executor"]["error"] = f"线程池响应超时（>{timeout}秒）"
        except RuntimeError as e:
            health_status["io_executor"]["status"] = "error"
            health_status["io_executor"]["error"] = f"线程池错误: {str(e)}"
        except Exception as e:
            health_status["io_executor"]["status"] = "error"
            health_status["io_executor"]["error"] = f"线程池检查失败: {str(e)}"
        
        # 确定整体状态
        cpu_ok = health_status["cpu_executor"]["status"] == "healthy"
        io_ok = health_status["io_executor"]["status"] == "healthy"
        
        if cpu_ok and io_ok:
            health_status["overall_status"] = "healthy"
        elif health_status["cpu_executor"]["status"] == "error" or health_status["io_executor"]["status"] == "error":
            health_status["overall_status"] = "error"
        else:
            health_status["overall_status"] = "unhealthy"
        
        return health_status


def get_executor_manager() -> ExecutorManager:
    """
    获取ExecutorManager单例实例
    
    Returns:
        ExecutorManager: 执行器管理器实例
    """
    return ExecutorManager()

