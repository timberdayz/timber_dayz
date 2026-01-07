"""
智能重试策略服务 (Phase 9.3)

提供：
1. 指数退避重试
2. 步骤级备用选择器
3. 组件级降级策略
"""

import asyncio
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
from pathlib import Path

from modules.core.logger import get_logger

logger = get_logger(__name__)


class RetryStrategy:
    """智能重试策略"""
    
    def __init__(self):
        self.retry_history = []  # 记录重试历史
    
    def calculate_backoff_delay(
        self,
        attempt: int,
        strategy: str = "exponential",
        base: float = 1.0,
        multiplier: float = 2.0,
        max_delay: float = 60.0
    ) -> float:
        """
        计算退避延迟时间
        
        Args:
            attempt: 当前尝试次数（1-based）
            strategy: 退避策略（exponential/linear/fixed）
            base: 基础延迟（秒）
            multiplier: 倍数
            max_delay: 最大延迟（秒）
            
        Returns:
            延迟时间（秒）
        """
        if strategy == "exponential":
            # 指数退避：1秒、2秒、4秒、8秒...
            delay = base * (multiplier ** (attempt - 1))
        elif strategy == "linear":
            # 线性增长：1秒、2秒、3秒、4秒...
            delay = base * attempt
        elif strategy == "fixed":
            # 固定延迟：1秒、1秒、1秒...
            delay = base
        else:
            delay = base
        
        # 限制最大延迟
        return min(delay, max_delay)
    
    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        retry_config: Optional[Dict[str, Any]] = None,
        step_id: str = "unknown",
        **kwargs
    ) -> Any:
        """
        执行函数并支持智能重试
        
        Args:
            func: 要执行的异步函数
            *args: 函数参数
            retry_config: 重试配置
            step_id: 步骤ID（用于日志）
            **kwargs: 函数关键字参数
            
        Returns:
            函数执行结果
        """
        # 默认配置
        if retry_config is None:
            retry_config = {}
        
        enabled = retry_config.get('enabled', True)
        if not enabled:
            # 不重试，直接执行
            return await func(*args, **kwargs)
        
        max_attempts = retry_config.get('max_attempts', 3)
        backoff_strategy = retry_config.get('backoff_strategy', 'exponential')
        backoff_base = retry_config.get('backoff_base', 1.0)
        backoff_multiplier = retry_config.get('backoff_multiplier', 2.0)
        
        last_error = None
        
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"[{step_id}] Attempt {attempt}/{max_attempts}")
                
                # 执行函数
                result = await func(*args, **kwargs)
                
                # 成功
                if attempt > 1:
                    logger.info(f"[{step_id}] Succeeded on retry attempt {attempt}")
                    self._record_retry(step_id, attempt, success=True)
                
                return result
            
            except Exception as e:
                last_error = e
                logger.warning(
                    f"[{step_id}] Failed on attempt {attempt}/{max_attempts}: "
                    f"{type(e).__name__}: {str(e)}"
                )
                
                # 最后一次尝试失败
                if attempt >= max_attempts:
                    logger.error(f"[{step_id}] Failed after {max_attempts} attempts")
                    self._record_retry(step_id, max_attempts, success=False, error=str(e))
                    raise
                
                # 计算延迟
                delay = self.calculate_backoff_delay(
                    attempt=attempt,
                    strategy=backoff_strategy,
                    base=backoff_base,
                    multiplier=backoff_multiplier
                )
                
                logger.info(f"[{step_id}] Waiting {delay:.1f}s before retry...")
                await asyncio.sleep(delay)
        
        # 理论上不会到达这里
        raise last_error
    
    async def execute_with_fallback_selectors(
        self,
        page,
        action: str,
        main_selector: str,
        fallback_selectors: List[Dict[str, Any]],
        step_id: str = "unknown",
        timeout: int = 10000,
        **action_kwargs
    ) -> Any:
        """
        执行操作，支持备用选择器
        
        Args:
            page: Playwright Page对象
            action: 操作类型（click/fill/wait等）
            main_selector: 主选择器
            fallback_selectors: 备用选择器列表
            step_id: 步骤ID
            timeout: 超时时间
            **action_kwargs: 操作的额外参数
            
        Returns:
            操作结果
        """
        all_selectors = [
            {'selector': main_selector, 'reason': 'Primary selector'}
        ] + fallback_selectors
        
        last_error = None
        
        for i, selector_config in enumerate(all_selectors, 1):
            selector = selector_config['selector']
            reason = selector_config.get('reason', 'Fallback selector')
            
            try:
                logger.info(
                    f"[{step_id}] Trying selector {i}/{len(all_selectors)}: "
                    f"{selector} ({reason})"
                )
                
                # 根据action类型执行不同操作
                if action == 'click':
                    await page.click(selector, timeout=timeout, **action_kwargs)
                    result = True
                elif action == 'fill':
                    value = action_kwargs.get('value', '')
                    await page.fill(selector, value, timeout=timeout)
                    result = True
                elif action == 'wait':
                    state = action_kwargs.get('state', 'visible')
                    await page.wait_for_selector(
                        selector, 
                        timeout=timeout, 
                        state=state
                    )
                    result = True
                else:
                    # 其他action（扩展）
                    result = None
                
                # 成功
                if i > 1:
                    logger.info(
                        f"[{step_id}] Succeeded with fallback selector {i}: "
                        f"{selector}"
                    )
                
                return result
            
            except Exception as e:
                last_error = e
                logger.warning(
                    f"[{step_id}] Selector {i} failed: {selector} - "
                    f"{type(e).__name__}: {str(e)}"
                )
                
                # 最后一个选择器也失败
                if i >= len(all_selectors):
                    logger.error(
                        f"[{step_id}] All selectors failed "
                        f"(tried {len(all_selectors)} selectors)"
                    )
                    raise
        
        # 理论上不会到达这里
        raise last_error
    
    def _record_retry(
        self, 
        step_id: str, 
        attempts: int, 
        success: bool, 
        error: str = None
    ):
        """记录重试历史"""
        record = {
            'step_id': step_id,
            'attempts': attempts,
            'success': success,
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
        self.retry_history.append(record)
        
        # 限制历史记录数量
        if len(self.retry_history) > 100:
            self.retry_history = self.retry_history[-100:]
    
    def get_retry_statistics(self) -> Dict[str, Any]:
        """获取重试统计信息"""
        if not self.retry_history:
            return {
                'total_retries': 0,
                'success_rate': 0.0,
                'avg_attempts': 0.0
            }
        
        total = len(self.retry_history)
        successes = sum(1 for r in self.retry_history if r['success'])
        total_attempts = sum(r['attempts'] for r in self.retry_history)
        
        return {
            'total_retries': total,
            'success_rate': successes / total if total > 0 else 0.0,
            'avg_attempts': total_attempts / total if total > 0 else 0.0,
            'recent_retries': self.retry_history[-10:]  # 最近10次
        }


class ComponentFallbackStrategy:
    """组件级降级策略"""
    
    def __init__(self, component_loader):
        self.component_loader = component_loader
        self.fallback_history = []
    
    async def execute_with_fallback_components(
        self,
        executor,
        page,
        main_component: Dict[str, Any],
        fallback_components: List[Dict[str, Any]],
        params: Dict[str, Any],
        step_popup_handler,
        download_dir: Path
    ) -> Any:
        """
        执行组件，支持降级到备用组件
        
        Args:
            executor: CollectionExecutorV2实例
            page: Playwright Page对象
            main_component: 主组件配置
            fallback_components: 备用组件列表
            params: 参数
            step_popup_handler: 弹窗处理器
            download_dir: 下载目录
            
        Returns:
            执行结果
        """
        all_components = [
            {'component': main_component, 'reason': 'Primary component'}
        ] + [
            {
                'component': self.component_loader.load(fc['component'], params),
                'reason': fc.get('reason', 'Fallback component')
            }
            for fc in fallback_components
        ]
        
        last_error = None
        
        for i, comp_config in enumerate(all_components, 1):
            component = comp_config['component']
            reason = comp_config['reason']
            comp_name = component.get('name', 'unknown')
            
            try:
                logger.info(
                    f"Trying component {i}/{len(all_components)}: "
                    f"{comp_name} ({reason})"
                )
                
                # 执行组件
                result = await executor._execute_export_component(
                    page=page,
                    component=component,
                    step_popup_handler=step_popup_handler,
                    download_dir=download_dir
                )
                
                # 成功
                if i > 1:
                    logger.info(
                        f"Succeeded with fallback component {i}: {comp_name}"
                    )
                    self._record_fallback(comp_name, i, success=True)
                
                return result
            
            except Exception as e:
                last_error = e
                logger.warning(
                    f"Component {i} failed: {comp_name} - "
                    f"{type(e).__name__}: {str(e)}"
                )
                
                self._record_fallback(comp_name, i, success=False, error=str(e))
                
                # 最后一个组件也失败
                if i >= len(all_components):
                    logger.error(
                        f"All components failed (tried {len(all_components)} components)"
                    )
                    raise
        
        # 理论上不会到达这里
        raise last_error
    
    def _record_fallback(
        self, 
        component_name: str, 
        index: int, 
        success: bool, 
        error: str = None
    ):
        """记录降级历史"""
        record = {
            'component_name': component_name,
            'index': index,
            'success': success,
            'error': error,
            'timestamp': datetime.now().isoformat()
        }
        self.fallback_history.append(record)
        
        # 限制历史记录数量
        if len(self.fallback_history) > 100:
            self.fallback_history = self.fallback_history[-100:]

