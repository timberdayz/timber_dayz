"""
浏览器配置辅助函数（v4.7.0）

提供环境感知的浏览器配置，用于逐步替换硬编码的headless=False
"""

import os
from modules.core.logger import get_logger

logger = get_logger(__name__)


def get_browser_launch_args(debug_mode: bool = False) -> dict:
    """
    获取环境感知的浏览器启动参数（v4.7.0）
    
    自动根据环境返回合适的浏览器配置：
    - 开发环境：默认有头模式（headless=false, slow_mo=100）便于观察
    - 生产环境：自动无头模式（headless=true, slow_mo=0）适合Docker
    - 调试模式：强制有头模式（覆盖生产环境配置）
    
    Args:
        debug_mode: 调试模式（临时启用有头浏览器）
        
    Returns:
        dict: Playwright browser.launch() 参数
    """
    try:
        # 尝试从backend.utils.config导入
        from backend.utils.config import get_settings
        settings = get_settings()
        browser_config = settings.browser_config.copy()
        
        # 调试模式覆盖
        if debug_mode:
            browser_config['headless'] = False
            logger.info("Debug mode enabled: forcing headful browser")
        
        return browser_config
    
    except Exception as e:
        # 降级到默认配置
        logger.warning(f"Failed to load settings, using default browser config: {e}")
        
        environment = os.getenv("ENVIRONMENT", "development")
        headless = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"
        slow_mo = int(os.getenv("PLAYWRIGHT_SLOW_MO", "0"))
        
        if debug_mode:
            headless = False
        
        if environment == "production":
            return {
                'headless': headless or True,  # 生产环境强制无头（除非调试）
                'slow_mo': 0,
                'args': [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-blink-features=AutomationControlled',
                ]
            }
        else:
            return {
                'headless': headless,
                'slow_mo': slow_mo if slow_mo > 0 else 100,
                'args': []
            }


def get_browser_context_args() -> dict:
    """
    获取浏览器上下文参数（反检测指纹）
    
    Returns:
        dict: browser.new_context() 参数
    """
    return {
        'viewport': {'width': 1920, 'height': 1080},
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'locale': 'zh-CN',
        'timezone_id': 'Asia/Shanghai',
        'accept_downloads': True,
    }

