#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
持久化浏览器管理器

提供每账号独立的持久化浏览器Profile和固定指纹功能：
- 每账号一个独立的user_data_dir
- 固定的设备指纹（UA、viewport、locale、timezone）
- 自动复用storage_state，减少验证码频率
- 支持Playwright的launch_persistent_context
"""

import json
import time
from pathlib import Path
from typing import Dict, Optional, Any, Union
from datetime import datetime
from loguru import logger

from playwright.sync_api import Browser, BrowserContext, Page, Playwright
from .sessions.session_manager import SessionManager
from .sessions.device_fingerprint import DeviceFingerprintManager


class PersistentBrowserManager:
    """持久化浏览器管理器"""

    def __init__(self, playwright: Playwright):
        """
        初始化持久化浏览器管理器

        Args:
            playwright: Playwright实例
        """
        self.playwright = playwright
        self.session_manager = SessionManager()
        self.fingerprint_manager = DeviceFingerprintManager()

        # 活跃的持久化上下文缓存
        self.active_contexts: Dict[str, BrowserContext] = {}
        # 回退模式下创建的 Browser 实例（需要在关闭上下文时一并关闭）
        self._fallback_browsers: Dict[str, Browser] = {}

        logger.info("持久化浏览器管理器初始化完成")

    def get_or_create_persistent_context(
        self,
        platform: str,
        account_id: str,
        account_config: Optional[Dict[str, Any]] = None,
        **context_overrides: Any,
    ) -> BrowserContext:
        """
        获取或创建账号的持久化浏览器上下文

        Args:
            platform: 平台名称
            account_id: 账号ID
            account_config: 账号配置（用于生成指纹）

        Returns:
            持久化浏览器上下文
        """
        context_key = f"{platform}_{account_id}"

        # 检查是否已有活跃上下文
        if context_key in self.active_contexts:
            try:
                # 验证上下文是否仍然有效
                context = self.active_contexts[context_key]
                # 简单测试上下文是否可用
                pages = context.pages
                logger.debug(f"复用现有持久化上下文: {context_key}")
                return context
            except Exception as e:
                logger.warning(f"现有上下文已失效，将重新创建: {e}")
                del self.active_contexts[context_key]

        # 创建新的持久化上下文
        context = self._create_persistent_context(platform, account_id, account_config, **context_overrides)
        self.active_contexts[context_key] = context

        return context

    def _create_persistent_context(
        self,
        platform: str,
        account_id: str,
        account_config: Optional[Dict[str, Any]] = None,
        **context_overrides: Any,
    ) -> BrowserContext:
        """创建持久化浏览器上下文"""
        try:
            # 获取持久化Profile路径
            profile_path = self.session_manager.get_persistent_profile_path(platform, account_id)

            # 获取或生成设备指纹
            fingerprint = self.fingerprint_manager.get_or_create_fingerprint(
                platform, account_id, account_config
            )

            # 构建启动参数
            launch_options = {
                'headless': False,
                'args': [
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-web-security',
                    '--disable-features=VizDisplayCompositor',
                    '--disable-dev-shm-usage',
                    '--no-first-run',
                    '--disable-default-apps',
                    # 移除 --disable-extensions-except（需要参数路径，空值会导致崩溃）
                    # '--disable-plugins-discovery' 保留为可选，通常不需要
                    f'--user-agent={fingerprint["user_agent"]}'
                ],
                'slow_mo': 100  # 稍微减慢操作速度，更像真实用户
            }

            # 构建上下文参数
            context_options = {
                'viewport': fingerprint['viewport'],
                'user_agent': fingerprint['user_agent'],
                'locale': fingerprint['locale'],
                'timezone_id': fingerprint['timezone'],
                'permissions': ['geolocation', 'notifications'],
                'geolocation': fingerprint.get('geolocation'),
                'color_scheme': 'light',
                'reduced_motion': 'no-preference',
                'forced_colors': 'none',
                'accept_downloads': True,
                'ignore_https_errors': True,
                'java_script_enabled': True,
                'bypass_csp': False,
                'extra_http_headers': {
                    'Accept-Language': f"{fingerprint['locale']},en;q=0.9",
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Sec-Fetch-User': '?1',
                    'Upgrade-Insecure-Requests': '1'
                }
            }

            # 创建持久化上下文
            logger.info(f"创建持久化上下文: {platform}/{account_id}")
            logger.debug(f"Profile路径: {profile_path}")
            logger.debug(f"设备指纹: UA={fingerprint['user_agent'][:50]}...")

            # 合并外部覆盖参数（例如 downloads_path/accept_downloads 等）
            if context_overrides:
                logger.debug(f"持久化上下文外部覆盖参数: {context_overrides}")
                # 允许覆盖 context_options 与 launch_options
                # 常见覆盖: accept_downloads, downloads_path, viewport, user_agent, locale
                # 注意: downloads_path 仅在持久化上下文下生效
                for k, v in context_overrides.items():
                    if k in ('viewport','user_agent','locale','timezone_id','permissions','geolocation','color_scheme','reduced_motion','forced_colors','accept_downloads','ignore_https_errors','java_script_enabled','bypass_csp','extra_http_headers','downloads_path'):
                        context_options[k] = v
                    else:
                        launch_options[k] = v

            # 默认下载目录（未外部覆盖时）：downloads/<platform>
            try:
                if not context_options.get('downloads_path'):
                    droot = Path.cwd() / 'downloads' / str(platform).lower()
                    droot.mkdir(parents=True, exist_ok=True)
                    context_options['downloads_path'] = str(droot)
                    logger.debug(f"设置默认downloads_path: {context_options['downloads_path']}")
            except Exception as e:
                logger.warning(f"设置默认downloads_path失败: {e}")

            # 尝试创建（带小重试，处理偶发的 "Target ... has been closed"）
            last_err = None
            for attempt in range(2):
                try:
                    # 第一次使用主Profile；第二次使用旁路Profile，避免主Profile被系统锁定/损坏
                    if attempt == 0:
                        user_dir = profile_path
                    else:
                        user_dir = profile_path.with_name(profile_path.name + "_alt")
                        user_dir.mkdir(parents=True, exist_ok=True)
                    context = self.playwright.chromium.launch_persistent_context(
                        user_data_dir=str(user_dir),
                        **context_options,
                        **launch_options
                    )
                    # 设置额外的反检测措施
                    self._setup_anti_detection(context)
                    logger.success(f"持久化上下文创建成功: {platform}/{account_id}")
                    return context
                except Exception as e:
                    last_err = e
                    msg = str(e)
                    logger.warning(f"持久化上下文创建失败(第{attempt+1}次): {msg}")
                    if "Target page, context or browser has been closed" in msg or "profile" in msg.lower():
                        time.sleep(0.8)
                        continue
                    else:
                        break
            # 最终回退到普通上下文
            logger.error(f"创建持久化上下文失败: {last_err}")
            return self._create_fallback_context(fingerprint, context_key=context_key)
        except Exception as e:
            logger.error(f"创建持久化上下文异常: {e}")
            try:
                fp = self.fingerprint_manager.get_or_create_fingerprint(platform, account_id, account_config)
            except Exception:
                fp = {
                    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                    'viewport': {'width': 1920, 'height': 1080},
                    'locale': 'zh-CN',
                    'timezone': 'Asia/Shanghai',
                }
            return self._create_fallback_context(fp, context_key=context_key)


    def _setup_anti_detection(self, context: BrowserContext):
        """设置反检测措施"""
        try:
            # 注入反检测脚本到所有页面
            context.add_init_script("""
                // 移除webdriver标识
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });

                // 伪造chrome对象
                window.chrome = {
                    runtime: {},
                    loadTimes: function() {},
                    csi: function() {},
                    app: {}
                };

                // 伪造plugins
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5],
                });

                // 伪造languages
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['zh-CN', 'zh', 'en'],
                });

                // 移除自动化相关属性
                delete navigator.__proto__.webdriver;
            """)

            logger.debug("反检测脚本注入成功")

        except Exception as e:
            logger.warning(f"反检测脚本注入失败: {e}")

    def _create_fallback_context(self, fingerprint: Dict[str, Any], context_key: Optional[str] = None) -> BrowserContext:
        """创建回退上下文（普通模式）"""
        try:
            logger.warning("使用回退模式创建普通浏览器上下文")

            browser = self.playwright.chromium.launch(
                headless=False,
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    f'--user-agent={fingerprint["user_agent"]}'
                ]
            )

            context = browser.new_context(
                viewport=fingerprint['viewport'],
                user_agent=fingerprint['user_agent'],
                locale=fingerprint['locale'],
                timezone_id=fingerprint['timezone']
            )

            self._setup_anti_detection(context)
            # 记录回退浏览器，便于后续关闭释放资源
            if context_key:
                try:
                    self._fallback_browsers[context_key] = browser
                except Exception:
                    pass
            return context

        except Exception as e:
            logger.error(f"创建回退上下文失败: {e}")
            raise

    def save_context_state(
        self,
        context: BrowserContext,
        platform: str,
        account_id: str
    ) -> bool:
        """
        保存上下文状态（稳健版）

        - 在某些环境下，context.storage_state() 可能触发 Protocol error (Target.createTarget)
          通常发生在所有页面被关闭、或上下文即将关闭时。
        - 此方法通过“必要时临时打开一页 + 重试”来规避，同时将失败降级为 warning，避免噪音。
        """
        # 1) 快速判定上下文可用
        try:
            _ = context.pages  # 触发一次访问，若已关闭会抛错
        except Exception as e:
            logger.warning(f"保存上下文状态跳过（上下文可能已关闭）: {platform}/{account_id} - {e}")
            return False

        # 2) 尝试直接获取；失败则在短暂重试中创建临时页
        for attempt in range(2):
            temp_page: Optional[Page] = None
            try:
                try:
                    storage_state = context.storage_state()
                except Exception:
                    # 如果第一页失败且没有可用页面，尝试创建临时页后再试一次
                    if attempt == 0:
                        try:
                            temp_page = context.new_page()
                        except Exception as ne:
                            logger.debug(f"创建临时页失败: {ne}")
                    storage_state = context.storage_state()

                success = self.session_manager.save_session(
                    platform,
                    account_id,
                    storage_state,
                    metadata={
                        'saved_at': time.time(),
                        'persistent_profile': True,
                        'context_type': 'persistent',
                    },
                )
                if success:
                    logger.info(f"上下文状态已保存: {platform}/{account_id}")
                return success
            except Exception as e:
                msg = str(e)
                # 对已关闭上下文的典型报错不再告警，直接信息级跳过
                if "has been closed" in msg or "Target.createTarget" in msg or "Target page, context or browser has been closed" in msg:
                    logger.info(f"跳过保存（上下文已结束）: {platform}/{account_id}")
                    return False
                logger.warning(f"保存上下文状态失败(第{attempt+1}次): {msg}")
                time.sleep(0.2)
            finally:
                if temp_page is not None:
                    try:
                        temp_page.close()
                    except Exception:
                        pass
        return False

    def close_context(self, platform: str, account_id: str):
        """关闭指定账号的上下文"""
        context_key = f"{platform}_{account_id}"

        if context_key in self.active_contexts:
            try:
                context = self.active_contexts[context_key]

                # 保存状态
                self.save_context_state(context, platform, account_id)

                # 关闭上下文
                context.close()

                del self.active_contexts[context_key]
                logger.info(f"上下文已关闭: {context_key}")

            except Exception as e:
                logger.error(f"关闭上下文失败: {e}")

        # 如存在回退浏览器，也一并关闭，避免残留进程/窗口
        if context_key in self._fallback_browsers:
            try:
                fb = self._fallback_browsers.pop(context_key, None)
                if fb:
                    fb.close()
                    logger.info(f"回退浏览器已关闭: {context_key}")
            except Exception as e:
                logger.warning(f"关闭回退浏览器失败: {e}")

    def close_all_contexts(self):
        """关闭所有活跃上下文"""
        for context_key in list(self.active_contexts.keys()):
            platform, account_id = context_key.split('_', 1)
            self.close_context(platform, account_id)
        # 关闭仍然残留的回退浏览器
        for context_key, fb in list(self._fallback_browsers.items()):
            try:
                fb.close()
            except Exception:
                pass
            finally:
                self._fallback_browsers.pop(context_key, None)
        logger.info("所有持久化上下文已关闭")

    def get_context_info(self, platform: str, account_id: str) -> Dict[str, Any]:
        """获取上下文信息"""
        context_key = f"{platform}_{account_id}"
        profile_path = self.session_manager.get_persistent_profile_path(platform, account_id)

        return {
            'platform': platform,
            'account_id': account_id,
            'context_key': context_key,
            'profile_path': str(profile_path),
            'is_active': context_key in self.active_contexts,
            'profile_exists': profile_path.exists(),
            'session_exists': self.session_manager.is_session_valid(platform, account_id)
        }
