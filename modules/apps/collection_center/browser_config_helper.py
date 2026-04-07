"""
浏览器配置辅助函数(v4.7.0)

提供环境感知的浏览器配置,用于逐步替换硬编码的headless=False
"""

import os
from typing import Any, Dict
from modules.core.logger import get_logger

logger = get_logger(__name__)


def enforce_official_playwright_browser(launch_args: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    强制使用 Playwright 官方默认浏览器。

    活跃采集/测试路径一律不允许通过 channel 或 executable_path
    切到系统安装的 Chrome / Edge，避免运行时落到 branded channel。
    """
    normalized = dict(launch_args or {})
    removed = {}

    for key in ("channel", "executable_path", "executablePath", "browser"):
        if key in normalized:
            removed[key] = normalized.pop(key)

    if removed:
        logger.info(
            f"Removed branded browser overrides from Playwright launch args: {', '.join(sorted(removed.keys()))}"
        )

    return normalized


def get_browser_launch_args(
    debug_mode: bool = False,
    execution_mode: str | None = None,
) -> dict:
    """
    获取环境感知的浏览器启动参数(v4.7.0)
    
    自动根据环境返回合适的浏览器配置:
    - 开发环境:默认有头模式(headless=false, slow_mo=100)便于观察
    - 生产环境:自动无头模式(headless=true, slow_mo=0)适合Docker
    - 调试模式:强制有头模式(覆盖生产环境配置)
    
    Args:
        debug_mode: 调试模式(临时启用有头浏览器)
        
    Returns:
        dict: Playwright browser.launch() 参数
    """
    try:
        # 尝试从backend.utils.config导入
        from backend.utils.config import get_settings
        settings = get_settings()
        browser_config = settings.browser_config.copy()
        normalized_mode = str(execution_mode or "").strip().lower()

        if normalized_mode == "headless":
            browser_config["headless"] = True
            browser_config["slow_mo"] = 0
        elif normalized_mode == "headed":
            browser_config["headless"] = False
        
        # 调试模式覆盖
        if debug_mode:
            browser_config['headless'] = False
            logger.info("Debug mode enabled: forcing headful browser")
        
        return enforce_official_playwright_browser(browser_config)
    
    except Exception as e:
        # 降级到默认配置
        logger.warning(f"Failed to load settings, using default browser config: {e}")
        
        environment = os.getenv("ENVIRONMENT", "development")
        headless = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"
        slow_mo = int(os.getenv("PLAYWRIGHT_SLOW_MO", "0"))
        normalized_mode = str(execution_mode or "").strip().lower()

        if normalized_mode == "headless":
            headless = True
            slow_mo = 0
        elif normalized_mode == "headed":
            headless = False
        
        if debug_mode:
            headless = False
        
        if environment == "production":
            return enforce_official_playwright_browser({
                'headless': headless or True,  # 生产环境强制无头(除非调试)
                'slow_mo': 0,
                'args': [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                ]
            })
        else:
            return enforce_official_playwright_browser({
                'headless': headless,
                'slow_mo': slow_mo if slow_mo > 0 else 100,
                'args': []
            })


def get_browser_context_args() -> dict:
    """
    获取浏览器上下文参数(全局默认反检测指纹)。
    主采集执行器已按账号使用 DeviceFingerprintManager 生成指纹，此处仅作回退/兼容。

    代理为预留能力：当前采集在住宅 IP 下无需启用；若未来需要多 IP/代理，
    可在执行器创建 context 时从 account 读取 proxy_required/proxy 并注入 context 的 proxy。
    """
    return {
        'viewport': {'width': 1920, 'height': 1080},
        'locale': 'zh-CN',
        'timezone_id': 'Asia/Shanghai',
        'accept_downloads': True,
    }
