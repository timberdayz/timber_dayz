"""
通用弹窗处理器 - Universal Popup Handler

负责检测和关闭各平台的弹窗、通知、对话框等
支持三层处理机制：通用 + 平台特定 + 组件级
"""

import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
import yaml

from modules.core.logger import get_logger

logger = get_logger(__name__)


class UniversalPopupHandler:
    """
    通用弹窗处理器
    
    三层处理机制：
    1. 通用选择器 - 处理常见弹窗（30+选择器）
    2. 平台特定配置 - popup_config.yaml定义的平台选择器
    3. 组件级配置 - 组件YAML中的popup_handling配置
    """
    
    # 通用关闭按钮选择器（30+种常见模式）
    UNIVERSAL_CLOSE_SELECTORS = [
        # aria标签
        '[aria-label="Close"]',
        '[aria-label="close"]',
        '[aria-label="关闭"]',
        '[aria-label="取消"]',
        '[aria-label="Dismiss"]',
        
        # 类名模式
        '.modal-close',
        '.close-btn',
        '.close-button',
        '.btn-close',
        '.dialog-close',
        '.popup-close',
        '.icon-close',
        '.dismiss',
        
        # 图标模式
        'button.close',
        'button[class*="close"]',
        'i.close',
        '[class*="modal"] button[class*="close"]',
        '[class*="dialog"] button[class*="close"]',
        
        # 文本模式
        'button:has-text("关闭")',
        'button:has-text("Close")',
        'button:has-text("取消")',
        'button:has-text("Cancel")',
        'button:has-text("稍后再说")',
        'button:has-text("Later")',
        'button:has-text("我知道了")',
        'button:has-text("Got it")',
        'button:has-text("确定")',
        'button:has-text("OK")',
        'button:has-text("No thanks")',
        'button:has-text("不，谢谢")',
        'button:has-text("跳过")',
        'button:has-text("Skip")',
        
        # X按钮模式
        '[class*="close"] svg',
        '[class*="close"] i',
        'button svg[class*="close"]',
    ]
    
    # 通用遮罩层选择器
    UNIVERSAL_OVERLAY_SELECTORS = [
        '.modal-backdrop',
        '.modal-overlay',
        '.overlay',
        '[class*="mask"]',
        '[class*="backdrop"]',
    ]
    
    def __init__(self, platform_config_dir: str = None):
        """
        初始化弹窗处理器
        
        Args:
            platform_config_dir: 平台配置目录（默认：config/collection_components）
        """
        if platform_config_dir is None:
            platform_config_dir = Path(__file__).parent.parent.parent.parent / 'config' / 'collection_components'
        
        self.platform_config_dir = Path(platform_config_dir)
        self._platform_configs: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"UniversalPopupHandler initialized: config_dir={self.platform_config_dir}")
    
    def _load_platform_config(self, platform: str) -> Dict[str, Any]:
        """
        加载平台弹窗配置
        
        Args:
            platform: 平台代码（shopee/tiktok/miaoshou）
            
        Returns:
            Dict: 平台配置字典
        """
        if platform in self._platform_configs:
            return self._platform_configs[platform]
        
        config_path = self.platform_config_dir / platform / 'popup_config.yaml'
        
        if not config_path.exists():
            logger.debug(f"Platform popup config not found: {config_path}")
            self._platform_configs[platform] = {}
            return {}
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            
            self._platform_configs[platform] = config
            logger.info(f"Loaded platform popup config: {platform}")
            return config
        
        except Exception as e:
            logger.error(f"Failed to load popup config for {platform}: {e}")
            self._platform_configs[platform] = {}
            return {}
    
    def get_close_selectors(self, platform: str = None) -> List[str]:
        """
        获取关闭选择器列表（通用 + 平台特定）
        
        Args:
            platform: 平台代码（可选）
            
        Returns:
            List[str]: 选择器列表
        """
        selectors = list(self.UNIVERSAL_CLOSE_SELECTORS)
        
        if platform:
            platform_config = self._load_platform_config(platform)
            platform_selectors = platform_config.get('close_selectors', [])
            # 平台特定选择器优先（插入到列表前面）
            selectors = platform_selectors + selectors
        
        return selectors
    
    def get_overlay_selectors(self, platform: str = None) -> List[str]:
        """
        获取遮罩层选择器列表
        
        Args:
            platform: 平台代码（可选）
            
        Returns:
            List[str]: 选择器列表
        """
        selectors = list(self.UNIVERSAL_OVERLAY_SELECTORS)
        
        if platform:
            platform_config = self._load_platform_config(platform)
            platform_selectors = platform_config.get('overlay_selectors', [])
            selectors = platform_selectors + selectors
        
        return selectors
    
    def get_poll_strategy(self, platform: str = None) -> Dict[str, int]:
        """
        获取轮询策略
        
        Args:
            platform: 平台代码（可选）
            
        Returns:
            Dict: 轮询策略配置
        """
        default_strategy = {
            'max_rounds': 20,
            'interval_ms': 300,
            'watch_ms': 8000,
        }
        
        if platform:
            platform_config = self._load_platform_config(platform)
            platform_strategy = platform_config.get('poll_strategy', {})
            default_strategy.update(platform_strategy)
        
        return default_strategy
    
    async def close_popups(
        self, 
        page, 
        platform: str = None,
        max_rounds: int = None,
        interval_ms: int = None,
        watch_ms: int = None
    ) -> int:
        """
        关闭所有弹窗（主方法）
        
        Args:
            page: Playwright Page对象
            platform: 平台代码（用于加载平台特定配置）
            max_rounds: 最大轮询次数（覆盖默认值）
            interval_ms: 轮询间隔毫秒（覆盖默认值）
            watch_ms: 总观察时间毫秒（覆盖默认值）
            
        Returns:
            int: 关闭的弹窗数量
        """
        # 获取轮询策略
        strategy = self.get_poll_strategy(platform)
        max_rounds = max_rounds or strategy['max_rounds']
        interval_ms = interval_ms or strategy['interval_ms']
        watch_ms = watch_ms or strategy['watch_ms']
        
        # 获取选择器列表
        close_selectors = self.get_close_selectors(platform)
        
        closed_count = 0
        start_time = asyncio.get_event_loop().time()
        
        for round_num in range(max_rounds):
            # 检查是否超过总观察时间
            elapsed = (asyncio.get_event_loop().time() - start_time) * 1000
            if elapsed > watch_ms:
                break
            
            # 尝试关闭弹窗
            closed_this_round = await self._try_close_popups(page, close_selectors)
            
            if closed_this_round > 0:
                closed_count += closed_this_round
                logger.debug(f"Round {round_num + 1}: closed {closed_this_round} popup(s)")
            else:
                # 没有找到弹窗，尝试ESC键
                await self._try_esc_key(page)
            
            # 等待下一轮
            await asyncio.sleep(interval_ms / 1000)
        
        if closed_count > 0:
            logger.info(f"Total popups closed: {closed_count}")
        
        return closed_count
    
    async def _try_close_popups(self, page, selectors: List[str]) -> int:
        """
        尝试关闭弹窗（遍历选择器）
        
        Args:
            page: Playwright Page对象
            selectors: 选择器列表
            
        Returns:
            int: 关闭的弹窗数量
        """
        closed = 0
        
        # 获取所有frame（主页面 + iframe）
        frames = [page] + list(page.frames)
        
        for frame in frames:
            for selector in selectors:
                try:
                    # 检查元素是否存在且可见
                    element = frame.locator(selector).first
                    
                    # 使用短超时快速检查
                    is_visible = await element.is_visible(timeout=100)
                    
                    if is_visible:
                        await element.click(timeout=1000)
                        closed += 1
                        logger.debug(f"Closed popup with selector: {selector}")
                        
                        # 关闭一个后等待一下，让页面更新
                        await asyncio.sleep(0.1)
                
                except Exception:
                    # 元素不存在或不可点击，继续下一个
                    pass
        
        return closed
    
    async def _try_esc_key(self, page) -> bool:
        """
        尝试使用ESC键关闭弹窗
        
        Args:
            page: Playwright Page对象
            
        Returns:
            bool: 是否按下ESC键
        """
        try:
            # 检查是否有遮罩层（表示有弹窗）
            overlay_selectors = self.get_overlay_selectors()
            
            for selector in overlay_selectors:
                try:
                    element = page.locator(selector).first
                    is_visible = await element.is_visible(timeout=100)
                    
                    if is_visible:
                        await page.keyboard.press('Escape')
                        logger.debug("Pressed ESC key to close popup")
                        return True
                
                except Exception:
                    pass
            
            return False
        
        except Exception as e:
            logger.debug(f"ESC key attempt failed: {e}")
            return False
    
    async def check_and_close(
        self, 
        page, 
        platform: str = None,
        component_config: Dict[str, Any] = None
    ) -> int:
        """
        检查并关闭弹窗（便捷方法）
        
        根据组件配置决定是否执行弹窗处理
        
        Args:
            page: Playwright Page对象
            platform: 平台代码
            component_config: 组件配置（包含popup_handling字段）
            
        Returns:
            int: 关闭的弹窗数量
        """
        # 检查是否启用弹窗处理
        if component_config:
            popup_handling = component_config.get('popup_handling', {})
            
            # 如果明确禁用，直接返回
            if popup_handling.get('enabled') is False:
                return 0
            
            # 如果没有明确禁用，默认启用
            if not popup_handling.get('auto_close', True):
                return 0
        
        return await self.close_popups(page, platform=platform)


class StepPopupHandler:
    """
    步骤级弹窗处理器
    
    在执行引擎中使用，处理步骤前后的弹窗
    """
    
    def __init__(self, popup_handler: UniversalPopupHandler, platform: str = None):
        """
        初始化步骤弹窗处理器
        
        Args:
            popup_handler: 通用弹窗处理器实例
            platform: 平台代码
        """
        self.popup_handler = popup_handler
        self.platform = platform
    
    async def before_step(self, page, step: Dict[str, Any], component_config: Dict[str, Any] = None) -> None:
        """
        步骤执行前的弹窗处理
        
        Args:
            page: Playwright Page对象
            step: 步骤配置
            component_config: 组件配置
        """
        # 检查组件级配置
        popup_handling = component_config.get('popup_handling', {}) if component_config else {}
        check_before = popup_handling.get('check_before_steps', True)
        
        # 检查步骤级配置
        step_popup = step.get('popup_handling', {})
        if step_popup.get('check_before') is False:
            check_before = False
        elif step_popup.get('check_before') is True:
            check_before = True
        
        if check_before:
            await self.popup_handler.close_popups(page, platform=self.platform)
    
    async def after_step(self, page, step: Dict[str, Any], component_config: Dict[str, Any] = None) -> None:
        """
        步骤执行后的弹窗处理
        
        Args:
            page: Playwright Page对象
            step: 步骤配置
            component_config: 组件配置
        """
        # 检查组件级配置
        popup_handling = component_config.get('popup_handling', {}) if component_config else {}
        check_after = popup_handling.get('check_after_steps', True)
        
        # 检查步骤级配置
        step_popup = step.get('popup_handling', {})
        if step_popup.get('check_after') is False:
            check_after = False
        elif step_popup.get('check_after') is True:
            check_after = True
        
        if check_after:
            await self.popup_handler.close_popups(page, platform=self.platform)
    
    async def on_error(self, page, step: Dict[str, Any], component_config: Dict[str, Any] = None) -> None:
        """
        步骤执行失败时的弹窗处理（v4.7.2增强）
        
        ⭐ 改进：
        1. 关闭弹窗
        2. 等待页面稳定（Playwright官方推荐）
        3. 短暂延迟，确保DOM更新完成
        
        Args:
            page: Playwright Page对象
            step: 步骤配置
            component_config: 组件配置
        """
        # 检查组件级配置
        popup_handling = component_config.get('popup_handling', {}) if component_config else {}
        check_on_error = popup_handling.get('check_on_error', True)
        
        if check_on_error:
            # 1️⃣ 关闭弹窗
            closed_count = await self.popup_handler.close_popups(page, platform=self.platform)
            
            if closed_count > 0:
                logger.info(f"Closed {closed_count} popup(s) after step failure")
                
                # 2️⃣ ⭐ 官方推荐：等待页面网络空闲（确保弹窗关闭完成）
                try:
                    await page.wait_for_load_state('networkidle', timeout=5000)
                except Exception as e:
                    logger.debug(f"Network idle wait timed out (may be normal): {e}")
                
                # 3️⃣ ⭐ 短暂延迟，确保DOM更新和动画完成
                await asyncio.sleep(0.5)
                
                logger.debug("Page stabilized after popup closure, ready to retry")
            else:
                # 没有弹窗，可能是其他原因导致失败
                logger.debug("No popups found, step may have failed for other reasons")

