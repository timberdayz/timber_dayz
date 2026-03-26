#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inspector API 录制脚本（v4.8.0）

使用 Playwright Inspector 进行组件录制：
1. 使用 PersistentBrowserManager 创建持久化上下文
2. 应用固定指纹（DeviceFingerprintManager）
3. 智能登录检测 + 自动执行登录组件（如果不是 login 组件）
4. 启动 Trace 录制
5. 打开 Inspector（page.pause()）
6. 停止后保存步骤到 JSON 文件

v4.8.0 更新 (2025-12-25):
- 增强登录状态检测（支持Cookie、等待自动跳转）
- 优化自动登录流程（快速检测 + 完整检测）
- 增强错误处理和降级策略

用法:
    python tools/launch_inspector_recorder.py --config <config.json>

配置文件格式:
{
    "platform": "miaoshou",
    "component_type": "shop_switch",
    "account_info": {...},
    "trace_file": "path/to/trace.zip",
    "steps_file": "path/to/steps.json",
    "skip_login": false,
    "enable_trace": true,
    "use_persistent_context": true,
    "use_fingerprint": true
}
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.components.base import ExecutionContext
from modules.apps.collection_center.transition_gates import evaluate_login_ready
from modules.core.logger import get_logger

logger = get_logger(__name__)


class InspectorRecorder:
    """
    Inspector API 录制器
    
    功能：
    1. 持久化浏览器上下文（可选）
    2. 固定设备指纹（可选）
    3. 自动登录（可选）
    4. Trace 录制
    5. Inspector 交互式录制
    6. 步骤提取和保存
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化录制器
        
        Args:
            config: 录制配置
        """
        self.config = config
        self.platform = config.get('platform', '')
        self.component_type = config.get('component_type', '')
        self.account_info = config.get('account_info', {})
        self.trace_file = config.get('trace_file')
        self.steps_file = config.get('steps_file')
        self.status_file = config.get('status_file')
        self.response_file = config.get('response_file')
        self.skip_login = config.get('skip_login', False)
        self.enable_trace = config.get('enable_trace', True)
        self.use_persistent_context = config.get('use_persistent_context', True)
        self.use_fingerprint = config.get('use_fingerprint', True)
        self.login_runtime_params: Dict[str, Any] = {}
        
        # 录制结果
        self.recorded_steps: List[Dict[str, Any]] = []
        self.start_url: Optional[str] = None
        self.end_url: Optional[str] = None
        
        # Phase 11: 发现模式（用于 date_picker 和 filters 组件）
        self.discovery_mode = self.component_type in ['date_picker', 'filters']
        self.open_action: Optional[Dict[str, Any]] = None  # 打开动作
        self.available_options: List[Dict[str, Any]] = []  # 发现的选项
        self._last_click_selector: Optional[str] = None  # 上次点击的选择器（用于检测重复 open）
        
        if self.discovery_mode:
            logger.info(f"[Discovery Mode] Enabled for component type: {self.component_type}")
        
        logger.info(f"InspectorRecorder initialized: {self.platform}/{self.component_type}")

    def _write_status(
        self,
        *,
        state: str,
        gate_stage: str = "login_gate",
        ready_to_record: bool = False,
        error_message: Optional[str] = None,
        verification_type: Optional[str] = None,
        verification_screenshot: Optional[str] = None,
    ) -> None:
        if not self.status_file:
            return

        payload = {
            "state": state,
            "gate_stage": gate_stage,
            "ready_to_record": ready_to_record,
            "platform": self.platform,
            "component_type": self.component_type,
            "error_message": error_message,
            "verification_type": verification_type,
            "verification_screenshot": verification_screenshot,
            "updated_at": datetime.now().isoformat(),
        }
        path = Path(self.status_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    async def _wait_for_verification_input(self, verification_type: str) -> str:
        if not self.response_file:
            raise RuntimeError("verification response file is not configured")

        response_path = Path(self.response_file)
        timeout_seconds = 300
        poll_interval_seconds = 2
        for _ in range(timeout_seconds // poll_interval_seconds):
            await asyncio.sleep(poll_interval_seconds)
            if response_path.exists():
                try:
                    with open(response_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    value = data.get("captcha_code") or data.get("otp")
                    if value:
                        try:
                            response_path.unlink()
                        except Exception:
                            pass
                        return str(value).strip()
                except Exception:
                    pass
        raise RuntimeError("验证码输入超时")

    async def _handle_login_verification(self, page, verification_error) -> None:
        verification_type = (verification_error.verification_type or "graphical_captcha").strip().lower()
        screenshot_name = "verification_screenshot.png"
        screenshot_path = verification_error.screenshot_path
        target_path = None
        if self.status_file:
            target_path = Path(self.status_file).parent / screenshot_name

        if target_path:
            import shutil
            if screenshot_path and Path(screenshot_path).exists():
                try:
                    shutil.copy2(screenshot_path, target_path)
                except Exception:
                    target_path = None
            if target_path and not target_path.exists():
                try:
                    await page.screenshot(path=str(target_path), timeout=5000)
                except Exception:
                    target_path = None

        self._write_status(
            state="login_verification_pending",
            gate_stage="login_gate",
            ready_to_record=False,
            verification_type=verification_type,
            verification_screenshot=screenshot_name if target_path else None,
        )

        value = await self._wait_for_verification_input(verification_type)
        if verification_type in ("otp", "sms", "email_code"):
            self.login_runtime_params["otp"] = value
        else:
            self.login_runtime_params["captcha_code"] = value
        self._write_status(state="login_checking", gate_stage="login_gate", ready_to_record=False)
    
    async def record(self) -> bool:
        """
        开始录制
        
        Returns:
            bool: 是否成功
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install")
            return False
        
        print("\n" + "="*60)
        print(" Inspector API Recording - v4.7.5")
        print("="*60)
        print(f"\nPlatform: {self.platform}")
        print(f"Component: {self.component_type}")
        print(f"Account: {self.account_info.get('account_id', 'N/A')}")
        print(f"Persistent Context: {self.use_persistent_context}")
        print(f"Fixed Fingerprint: {self.use_fingerprint}")
        print(f"Trace Recording: {self.enable_trace}")
        print("\n" + "-"*60)
        
        async with async_playwright() as p:
            # 1. 创建浏览器上下文
            self._write_status(state="starting", gate_stage="login_gate", ready_to_record=False)
            context, browser = await self._create_context(p)
            
            # 标记 Trace 是否已保存（用于 finally 中判断）
            trace_started = False
            trace_saved = False
            
            try:
                # 检查是否已有页面（持久化上下文可能包含默认页面）
                existing_pages = context.pages
                if existing_pages:
                    page = existing_pages[0]
                    logger.info(f"Using existing page from persistent context (total: {len(existing_pages)})")
                    # 关闭多余的空白页面
                    for extra_page in existing_pages[1:]:
                        await extra_page.close()
                else:
                    page = await context.new_page()
                    logger.info("Created new page")
                
                # 2. 启动 Trace 录制
                if self.enable_trace and self.trace_file:
                    await context.tracing.start(
                        screenshots=True,
                        snapshots=True,
                        sources=True
                    )
                    trace_started = True
                    print(f"[Trace] Recording started: {self.trace_file}")
                
                # 3. 自动登录（如果不是 login 组件）
                if not self.skip_login and self.component_type != 'login':
                    await self._auto_login(page)
                else:
                    # 导航到登录页
                    login_url = self.account_info.get('login_url')
                    if login_url:
                        print(f"\n[Navigate] {login_url}")
                        await self._safe_goto(page, login_url)
                    self._write_status(state="login_ready", gate_stage="login_gate", ready_to_record=True)
                
                # 4. 处理弹窗
                await self._handle_popups(page)
                
                # 5. 记录初始 URL
                self.start_url = page.url
                self._write_status(state="inspector_recording", gate_stage="login_gate", ready_to_record=True)
                
                # 6. 启动 Inspector
                print("\n" + "="*60)
                print(" Playwright Inspector Mode")
                print("="*60)
                print(f"\nCurrent URL: {page.url}")
                print(f"Recording Component: {self.component_type}")
                print("\nInstructions:")
                print("  1. Perform the actions you want to record in the browser")
                print("  2. The Inspector window will open automatically")
                print("  3. When done, click 'Resume' OR close the browser")
                print("  4. The tool will save your recorded steps")
                print("="*60 + "\n")
                
                # 监听事件以捕获操作
                await self._setup_event_listeners(page)
                
                try:
                    await page.pause()  # 打开 Inspector
                except Exception as e:
                    logger.warning(f"Inspector closed (this is normal if browser was closed): {e}")
                
                # 7. 安全记录结束 URL（浏览器可能已关闭）
                try:
                    self.end_url = page.url
                except Exception:
                    self.end_url = self.start_url
                    logger.info("Could not get end URL, using start URL")
                
                # 8. 尝试停止 Trace 录制
                if trace_started and self.trace_file and not trace_saved:
                    try:
                        await context.tracing.stop(path=self.trace_file)
                        trace_saved = True
                        print(f"[Trace] Saved: {self.trace_file}")
                        # 验证文件
                        self._verify_trace_file()
                    except Exception as e:
                        logger.warning(f"Failed to save trace in try block: {e}")
                
            finally:
                # 确保 Trace 保存（如果还没保存）
                if trace_started and self.trace_file and not trace_saved:
                    try:
                        print("[Trace] Attempting to save trace in finally block...")
                        await context.tracing.stop(path=self.trace_file)
                        trace_saved = True
                        print(f"[Trace] Saved in finally: {self.trace_file}")
                        self._verify_trace_file()
                    except Exception as e:
                        logger.error(f"Failed to save trace in finally: {e}")
                        print(f"[Trace] ERROR: Could not save trace file: {e}")
                
                # 关闭上下文（在 Trace 保存后）
                try:
                    await context.close()
                except Exception as e:
                    logger.debug(f"Context close error (may be already closed): {e}")
                
                # 关闭浏览器
                if browser:
                    try:
                        await browser.close()
                    except Exception as e:
                        logger.debug(f"Browser close error (may be already closed): {e}")
        
        # 9. 保存步骤到 JSON 文件
        self._save_steps()
        
        print("\n" + "="*60)
        print(" Recording Complete!")
        print("="*60)
        print(f"\nRecorded Steps: {len(self.recorded_steps)}")
        if self.trace_file:
            print(f"Trace File: {self.trace_file}")
        if self.steps_file:
            print(f"Steps File: {self.steps_file}")
        print(f"\n[TIP] View trace: playwright show-trace {self.trace_file}")
        
        return True
    
    async def _create_context(self, playwright):
        """
        创建浏览器上下文
        
        根据配置决定是否使用持久化上下文和固定指纹
        """
        browser = None
        
        if self.use_persistent_context:
            try:
                from modules.utils.persistent_browser_manager import PersistentBrowserManager
                
                # 使用同步 API 创建 PersistentBrowserManager（它内部使用 sync_playwright）
                # 但我们在异步环境中，所以需要另一种方式
                # 这里改为手动创建持久化上下文
                
                from modules.utils.sessions.session_manager import SessionManager
                from modules.utils.sessions.device_fingerprint import DeviceFingerprintManager
                
                session_manager = SessionManager()
                fingerprint_manager = DeviceFingerprintManager()
                
                # 获取 profile 路径
                account_id = self.account_info.get('account_id', 'default')
                profile_path = session_manager.get_persistent_profile_path(self.platform, account_id)
                
                # 获取指纹配置
                fingerprint = fingerprint_manager.get_or_create_fingerprint(
                    self.platform, account_id, self.account_info
                ) if self.use_fingerprint else {}
                
                # 构建上下文选项
                context_options = {
                    'viewport': fingerprint.get('viewport', {'width': 1920, 'height': 1080}),
                    'user_agent': fingerprint.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
                    'locale': fingerprint.get('locale', 'zh-CN'),
                    'timezone_id': fingerprint.get('timezone', 'Asia/Shanghai'),
                }
                
                # 使用 launch_persistent_context
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(profile_path),
                    headless=False,
                    args=[
                        '--no-sandbox',
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                    ],
                    slow_mo=100,
                    **context_options
                )
                
                # 注入反检测脚本
                await context.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                """)
                
                logger.info(f"Persistent context created: {profile_path}")
                return context, browser
                
            except Exception as e:
                logger.warning(f"Failed to create persistent context, falling back: {e}")
        
        # 非持久化上下文
        browser = await playwright.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
            ],
            slow_mo=100
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        # 注入反检测脚本
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        return context, browser
    
    async def _auto_login(self, page):
        """
        Run recorder pre-login using the same canonical login component model as production runtime.
        """
        from modules.utils.login_status_detector import LoginStatusDetector, LoginStatus

        print()
        print(f"[Auto Login] ====== Starting login check for {self.platform} ======")
        self._write_status(state="login_checking", gate_stage="login_gate", ready_to_record=False)

        login_url = self.account_info.get("login_url")
        if login_url:
            print(f"[Auto Login] Navigating to: {login_url}")
            await self._safe_goto(page, login_url)

        import os

        debug_mode = os.environ.get("DEBUG_LOGIN_DETECTION", "false").lower() == "true"
        detector = LoginStatusDetector(self.platform, debug=debug_mode)

        print("[Auto Login] Detecting login status (wait_for_redirect=True)...")
        detection_result = await detector.detect(page, wait_for_redirect=True)

        print("[Auto Login] Detection Result:")
        print(f"  - Status: {detection_result.status.value}")
        print(f"  - Confidence: {detection_result.confidence:.2f}")
        print(f"  - Method: {detection_result.detected_by}")
        print(f"  - Reason: {detection_result.reason}")
        print(f"  - Time: {detection_result.detection_time_ms}ms")
        if detection_result.matched_pattern:
            print(f"  - Matched: {detection_result.matched_pattern}")

        if not detector.needs_login(detection_result):
            gate_result = evaluate_login_ready(
                status=detection_result.status.value,
                confidence=detection_result.confidence,
                current_url=page.url,
                matched_signal=detection_result.matched_pattern or detection_result.detected_by,
            )
            print()
            print("[Auto Login] [SKIP] Session already logged in (confidence >= 0.7)")
            print(f"[Auto Login] Current URL: {page.url}")
            logger.info(f"Session already logged in, skipping auto-login for {self.platform}")
            self._write_status(
                state="login_ready",
                gate_stage=gate_result.stage,
                ready_to_record=True,
            )
            print("[Auto Login] ====== Login check complete (skipped) ======")
            print()
            return

        print()
        print("[Auto Login] [EXEC] Login required, executing login component...")

        from modules.apps.collection_center.executor_v2 import VerificationRequiredError

        try:
            while True:
                try:
                    await self._run_login_component(page)
                    break
                except VerificationRequiredError as verification_error:
                    await self._handle_login_verification(page, verification_error)
            print("[Auto Login] Waiting for post-login navigation...")
            await page.wait_for_timeout(3000)

            detector.clear_cache()
            post_login_result = await detector.detect(page, wait_for_redirect=True)

            print()
            print("[Auto Login] Post-login verification:")
            print(f"  - Status: {post_login_result.status.value}")
            print(f"  - Confidence: {post_login_result.confidence:.2f}")
            print(f"  - URL: {page.url}")

            gate_result = evaluate_login_ready(
                status=post_login_result.status.value,
                confidence=post_login_result.confidence,
                current_url=page.url,
                matched_signal=post_login_result.matched_pattern or post_login_result.detected_by,
            )

            if gate_result.status == "ready":
                self._write_status(
                    state="login_ready",
                    gate_stage=gate_result.stage,
                    ready_to_record=True,
                )
                print("[Auto Login] [OK] Login successful!")
            else:
                self._write_status(
                    state="failed_before_recording",
                    gate_stage=gate_result.stage,
                    ready_to_record=False,
                    error_message=gate_result.reason,
                )
                raise RuntimeError(
                    f"Auto login was not confirmed for {self.platform}: "
                    f"status={post_login_result.status.value}, "
                    f"confidence={post_login_result.confidence:.2f}, url={page.url}"
                )
        except FileNotFoundError:
            logger.warning(f"Login component not found for {self.platform}")
            print("[Auto Login] [ERROR] Login component file not found")
            self._write_status(
                state="failed_before_recording",
                gate_stage="login_gate",
                ready_to_record=False,
                error_message="login component file not found",
            )
            raise RuntimeError(
                f"Auto login was not confirmed for {self.platform}: login component file not found"
            )
        except Exception as e:
            logger.error(f"Auto login failed: {e}")
            print(f"[Auto Login] [ERROR] Auto login failed: {e}")
            self._write_status(
                state="failed_before_recording",
                gate_stage="login_gate",
                ready_to_record=False,
                error_message=str(e),
            )
            raise RuntimeError(
                f"Auto login was not confirmed for {self.platform}: {e}"
            ) from e

        print("[Auto Login] ====== Login check complete ======")
        print()

    async def _run_login_component(self, page) -> None:
        """Execute the recorder's login component using Python components first."""
        from modules.apps.collection_center.component_loader import ComponentLoader
        from backend.models.database import SessionLocal
        from backend.services.component_version_service import ComponentVersionService

        loader = ComponentLoader()
        python_component_class = None

        db = SessionLocal()
        try:
            svc = ComponentVersionService(db)
            preferred_version = svc.select_version_for_use(
                f"{self.platform}/login",
                enable_ab_test=False,
            )
        finally:
            db.close()

        if (
            preferred_version
            and str(getattr(preferred_version, "file_path", "")).strip().endswith(".py")
            and hasattr(loader, "load_python_component_from_path")
        ):
            python_component_class = loader.load_python_component_from_path(
                preferred_version.file_path,
                version_id=getattr(preferred_version, "id", None),
                platform=self.platform,
                component_type="login",
            )
            print(
                "[Auto Login] Executing versioned Python login component "
                f"v{getattr(preferred_version, 'version', 'unknown')}"
            )
        else:
            login_component = loader.load(f"{self.platform}/login")

            if not login_component:
                raise FileNotFoundError(f"Login component not found for {self.platform}")

            python_component_class = login_component.get("_python_component_class")
            if not python_component_class:
                steps = login_component.get("steps", [])
                print(f"[Auto Login] Found {len(steps)} login steps")
                if not steps:
                    raise RuntimeError("legacy login component has no executable steps")

                for i, step in enumerate(steps, 1):
                    step_action = step.get("action", "unknown")
                    step_comment = step.get("comment", "")
                    print(f"[Auto Login] Step {i}/{len(steps)}: {step_action}")
                    if step_comment:
                        print(f"         Comment: {step_comment}")
                    await self._execute_step(page, step)
                return

        if python_component_class:
            ctx = ExecutionContext(
                platform=self.platform,
                account=self.account_info,
                logger=logger,
                config={
                    "reused_session": bool(self.use_persistent_context),
                    "params": dict(self.login_runtime_params),
                },
            )
            result = await python_component_class(ctx).run(page)
            if not getattr(result, "success", False):
                raise RuntimeError(
                    getattr(result, "message", "login component returned unsuccessful result")
                )
            return

    async def _execute_step(self, page, step: Dict[str, Any]):
        """
        执行单个步骤
        """
        action = step.get('action', '')
        
        if action == 'navigate' or action == 'goto':
            url = step.get('url', '')
            if url:
                await self._safe_goto(page, url)
        
        elif action == 'click':
            selector = step.get('selector', '')
            if selector:
                locator = self._get_locator(page, selector)
                await locator.click(timeout=30000)
        
        elif action == 'fill':
            selector = step.get('selector', '')
            value = step.get('value', '')
            
            # 替换模板变量
            if '{{' in value:
                value = self._replace_template(value)
            
            if selector:
                locator = self._get_locator(page, selector)
                await locator.fill(value, timeout=30000)
        
        elif action == 'wait':
            timeout = step.get('timeout', 1000)
            await page.wait_for_timeout(timeout)
    
    def _get_locator(self, page, selector: str):
        """
        根据选择器获取定位器（使用官方 API）
        """
        if selector.startswith('role='):
            import re
            match = re.match(r'role=(\w+)\[name=([^\]]+)\]', selector)
            if match:
                role = match.group(1)
                name = match.group(2)
                return page.get_by_role(role, name=name)
        
        if selector.startswith('text='):
            return page.get_by_text(selector[5:])
        
        if selector.startswith('placeholder='):
            return page.get_by_placeholder(selector[12:])
        
        if selector.startswith('label='):
            return page.get_by_label(selector[6:])
        
        # 默认 CSS 选择器
        return page.locator(selector)
    
    def _replace_template(self, value: str) -> str:
        """
        替换模板变量
        """
        if '{{account.username}}' in value:
            value = value.replace('{{account.username}}', self.account_info.get('username', ''))
        if '{{account.password}}' in value:
            # 解密密码
            password = self._decrypt_password(self.account_info.get('password', ''))
            value = value.replace('{{account.password}}', password)
        return value
    
    def _decrypt_password(self, encrypted_password: str) -> str:
        """
        解密密码
        
        使用 EncryptionService 解密密码（P0强制要求）
        """
        if not encrypted_password:
            return ""
        
        try:
            from backend.services.encryption_service import get_encryption_service
            encryption_service = get_encryption_service()
            decrypted = encryption_service.decrypt_password(encrypted_password)
            logger.debug("[Auto Login] Password decrypted successfully")
            return decrypted
        except Exception as e:
            # 如果解密失败，可能是明文密码或密钥问题
            logger.warning(f"[Auto Login] Password decryption failed, using as-is: {e}")
            return encrypted_password
    
    def _verify_trace_file(self):
        """
        验证 Trace 文件是否有效
        
        检查：
        1. 文件是否存在
        2. 文件大小是否 > 0
        3. 是否为有效的 ZIP 文件
        """
        import zipfile
        
        if not self.trace_file:
            return
        
        trace_path = Path(self.trace_file)
        
        # 检查文件是否存在
        if not trace_path.exists():
            logger.error(f"[Trace Verify] File does not exist: {trace_path}")
            print(f"[Trace] ERROR: File not created")
            return
        
        # 检查文件大小
        file_size = trace_path.stat().st_size
        if file_size == 0:
            logger.error(f"[Trace Verify] File is empty: {trace_path}")
            print(f"[Trace] ERROR: File is empty (0 bytes)")
            return
        
        # 检查是否为有效 ZIP 文件
        try:
            with zipfile.ZipFile(trace_path, 'r') as zf:
                # 尝试读取文件列表
                file_list = zf.namelist()
                logger.info(f"[Trace Verify] Valid ZIP with {len(file_list)} files, size: {file_size} bytes")
                print(f"[Trace] Verified: {len(file_list)} files, {file_size} bytes")
        except zipfile.BadZipFile:
            logger.error(f"[Trace Verify] Invalid ZIP file: {trace_path}")
            print(f"[Trace] ERROR: Invalid ZIP file (corrupted)")
        except Exception as e:
            logger.error(f"[Trace Verify] Error checking file: {e}")
            print(f"[Trace] WARNING: Could not verify file: {e}")
    
    async def _safe_goto(self, page, url: str):
        """
        安全导航（带重试）
        """
        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=60000)
            await page.wait_for_load_state('networkidle', timeout=30000)
        except Exception as e:
            logger.warning(f"Navigation warning: {e}")
    
    async def _handle_popups(self, page):
        """
        处理弹窗
        """
        try:
            from modules.apps.collection_center.popup_handler import UniversalPopupHandler
            
            handler = UniversalPopupHandler()
            await handler.close_popups(page, platform=self.platform)
        except Exception as e:
            logger.debug(f"Popup handling skipped: {e}")
    
    async def _setup_event_listeners(self, page):
        """
        设置事件监听器以捕获操作
        
        v4.8.0: 增强事件监听，捕获 click、fill、select 等用户交互
        - 注入 JavaScript 监听器捕获所有用户操作
        - 生成多重选择器（role, text, css）
        - 与 Trace 录制并行工作，互不干扰
        """
        step_counter = [0]  # 使用列表以便在闭包中修改
        
        # 注入 JavaScript 事件监听器
        await self._inject_event_capture_script(page)
        
        # 监听页面导航
        def on_navigation(frame):
            if frame == page.main_frame:
                step_counter[0] += 1
                self.recorded_steps.append({
                    'id': step_counter[0],
                    'action': 'navigate',
                    'url': frame.url,
                    'comment': f'Navigate to {frame.url[:50]}...' if len(frame.url) > 50 else f'Navigate to {frame.url}'
                })
                self._persist_live_steps()
                logger.info(f"[Event] Navigation: {frame.url[:80]}")
        
        page.on('framenavigated', on_navigation)
        
        # 监听控制台消息（用于调试和捕获事件）
        def on_console(msg):
            text = msg.text
            # 捕获我们注入脚本的事件日志
            if text.startswith('[RecorderEvent]'):
                try:
                    import json
                    # 格式: [RecorderEvent] {"action": "click", ...}
                    event_json = text[len('[RecorderEvent]'):].strip()
                    event_data = json.loads(event_json)
                    self._handle_captured_event(event_data, step_counter)
                except Exception as e:
                    logger.debug(f"Failed to parse recorder event: {e}")
            elif msg.type == 'error':
                logger.warning(f"[Console Error] {text[:200]}")
        
        page.on('console', on_console)
        
        # 监听对话框
        async def on_dialog(dialog):
            logger.info(f"[Event] Dialog: {dialog.type} - {dialog.message[:100]}")
            step_counter[0] += 1
            self.recorded_steps.append({
                'id': step_counter[0],
                'action': 'handle_dialog',
                'dialog_type': dialog.type,
                'message': dialog.message,
                'comment': f'Handle {dialog.type} dialog'
            })
            self._persist_live_steps()
            await dialog.dismiss()
        
        page.on('dialog', on_dialog)
        
        # 监听下载
        def on_download(download):
            logger.info(f"[Event] Download: {download.suggested_filename}")
            step_counter[0] += 1
            self.recorded_steps.append({
                'id': step_counter[0],
                'action': 'download',
                'filename': download.suggested_filename,
                'comment': f'Download file: {download.suggested_filename}'
            })
            self._persist_live_steps()
        
        page.on('download', on_download)
        
        logger.info("[Event Listeners] Setup complete - monitoring clicks, inputs, navigation, dialogs, downloads")
    
    async def _inject_event_capture_script(self, page):
        """
        注入 JavaScript 脚本以捕获用户交互事件
        
        选择器优先级: role > placeholder > label > text > css
        支持隐式 ARIA 角色检测、placeholder/label 捕获、唯一性验证
        """
        script = '''
        (function() {
            if (window.__recorderInjected) return;
            window.__recorderInjected = true;

            var IMPLICIT_ROLES = {
                'button': 'button', 'a': 'link', 'select': 'combobox',
                'textarea': 'textbox', 'nav': 'navigation', 'img': 'img',
                'h1': 'heading', 'h2': 'heading', 'h3': 'heading',
                'h4': 'heading', 'h5': 'heading', 'h6': 'heading'
            };
            var INPUT_TYPE_ROLES = {
                'text': 'textbox', 'email': 'textbox', 'search': 'textbox',
                'tel': 'textbox', 'url': 'textbox', 'password': 'textbox',
                'number': 'spinbutton',
                'checkbox': 'checkbox', 'radio': 'radio',
                'submit': 'button', 'button': 'button', 'reset': 'button'
            };

            function getImplicitRole(el) {
                var explicit = el.getAttribute('role');
                if (explicit) return explicit;
                var tag = el.tagName.toLowerCase();
                if (tag === 'input') {
                    var t = (el.getAttribute('type') || 'text').toLowerCase();
                    return INPUT_TYPE_ROLES[t] || 'textbox';
                }
                if (tag === 'a' && !el.hasAttribute('href')) return null;
                return IMPLICIT_ROLES[tag] || null;
            }

            function getAccessibleName(el, role) {
                var ariaLabel = el.getAttribute('aria-label');
                if (ariaLabel && ariaLabel.trim()) return ariaLabel.trim();
                var tag = el.tagName.toLowerCase();
                if (tag === 'img') return (el.getAttribute('alt') || '').trim();
                if (tag === 'input' && (el.type === 'submit' || el.type === 'button' || el.type === 'reset')) {
                    return (el.value || '').trim();
                }
                if (role === 'textbox' || role === 'combobox' || role === 'checkbox' || role === 'radio' || role === 'spinbutton') {
                    var label = findLabel(el);
                    if (label) return label;
                    var ph = el.getAttribute('placeholder');
                    if (ph && ph.trim()) return ph.trim();
                    return '';
                }
                var text = getDirectText(el);
                return text;
            }

            function getDirectText(el) {
                var t = '';
                for (var i = 0; i < el.childNodes.length; i++) {
                    if (el.childNodes[i].nodeType === 3) t += el.childNodes[i].textContent;
                }
                t = t.trim();
                if (!t) t = (el.textContent || '').trim();
                return t.length <= 80 ? t : t.slice(0, 80);
            }

            function findLabel(el) {
                var id = el.id;
                if (id) {
                    var lab = document.querySelector('label[for="' + CSS.escape(id) + '"]');
                    if (lab) return lab.textContent.trim();
                }
                var parent = el.closest('label');
                if (parent) return parent.textContent.trim();
                return '';
            }

            function checkUnique(type, el, role, name) {
                try {
                    if (type === 'css') return document.querySelectorAll(name).length === 1;
                    if (type === 'placeholder') {
                        return document.querySelectorAll('[placeholder="' + CSS.escape(name) + '"]').length === 1;
                    }
                    if (type === 'label') {
                        var labels = document.querySelectorAll('label');
                        var c = 0;
                        for (var i = 0; i < labels.length; i++) { if (labels[i].textContent.trim() === name) c++; }
                        return c === 1;
                    }
                    if (type === 'role') {
                        var tag = el.tagName.toLowerCase();
                        var cssTag = tag;
                        if (tag === 'input') cssTag = 'input[type="' + (el.getAttribute('type') || 'text') + '"]';
                        var explicitRole = '[role="' + role + '"]';
                        var candidates = document.querySelectorAll(cssTag + ', ' + explicitRole);
                        var matched = 0;
                        for (var j = 0; j < candidates.length; j++) {
                            var cRole = getImplicitRole(candidates[j]);
                            if (cRole === role) {
                                var cName = getAccessibleName(candidates[j], cRole);
                                if (cName === name) matched++;
                            }
                        }
                        return matched === 1;
                    }
                    if (type === 'text') {
                        var xp = document.evaluate(
                            '//*[normalize-space(text())="' + name.replace(/"/g, '\\\\"') + '"]',
                            document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
                        );
                        return xp.snapshotLength === 1;
                    }
                } catch(e) {}
                return false;
            }

            function generateSelectors(element) {
                var selectors = [];
                var tag = element.tagName.toLowerCase();
                var role = getImplicitRole(element);

                // 1. Role + accessible name
                if (role) {
                    var accName = getAccessibleName(element, role);
                    if (accName) {
                        var rv = role + '[name="' + accName.replace(/"/g, '\\\\"') + '"]';
                        selectors.push({ type: 'role', value: rv, priority: 1,
                            unique: checkUnique('role', element, role, accName) });
                    }
                }

                // 2. Placeholder (input/textarea)
                if (tag === 'input' || tag === 'textarea') {
                    var ph = element.getAttribute('placeholder');
                    if (ph && ph.trim()) {
                        selectors.push({ type: 'placeholder', value: ph.trim(), priority: 1.5,
                            unique: checkUnique('placeholder', element, null, ph.trim()) });
                    }
                }

                // 3. Label
                var labelText = findLabel(element);
                if (labelText && labelText.length < 60) {
                    selectors.push({ type: 'label', value: labelText, priority: 1.8,
                        unique: checkUnique('label', element, null, labelText) });
                }

                // 4. Text content
                var text = getDirectText(element);
                if (text && text.length > 0 && text.length < 50) {
                    selectors.push({ type: 'text', value: text, priority: 2,
                        unique: checkUnique('text', element, null, text) });
                }

                // 5. CSS class
                var classes = Array.from(element.classList || []);
                var meaningful = classes.filter(function(c) {
                    return !c.match(/^(el-|ant-|van-|arco-)/i) && c.length > 3 && !c.match(/^[a-f0-9]{8,}$/i);
                });
                if (meaningful.length > 0) {
                    var cssSel = tag + '.' + meaningful[0];
                    selectors.push({ type: 'css', value: cssSel, priority: 3,
                        unique: checkUnique('css', element, null, cssSel) });
                }

                // 6. Data/id attribute
                var dataAttrs = ['data-testid', 'data-id', 'data-key', 'name', 'id'];
                for (var i = 0; i < dataAttrs.length; i++) {
                    var av = element.getAttribute(dataAttrs[i]);
                    if (av && !av.match(/^[a-f0-9]{8,}$/i)) {
                        var attrSel = '[' + dataAttrs[i] + '="' + av + '"]';
                        selectors.push({ type: 'css', value: attrSel, priority: 4,
                            unique: checkUnique('css', element, null, attrSel) });
                        break;
                    }
                }

                // 7. Positional fallback
                var parent = element.parentElement;
                if (parent) {
                    var idx = Array.from(parent.children).indexOf(element) + 1;
                    selectors.push({ type: 'css', value: tag + ':nth-child(' + idx + ')', priority: 5, unique: false });
                }

                return selectors;
            }

            function getElementDescription(element) {
                var text = getDirectText(element).slice(0, 30);
                var tag = element.tagName.toLowerCase();
                var role = getImplicitRole(element) || '';
                return text || role || tag;
            }

            document.addEventListener('click', function(e) {
                var target = e.target;
                if (!target || target === document.body) return;
                if (target.closest('[class*="playwright"]')) return;
                console.log('[RecorderEvent]', JSON.stringify({
                    action: 'click',
                    selectors: generateSelectors(target),
                    description: getElementDescription(target),
                    timestamp: Date.now()
                }));
            }, true);

            document.addEventListener('input', function(e) {
                var target = e.target;
                if (!target || !['INPUT', 'TEXTAREA'].includes(target.tagName)) return;
                var value = target.type === 'password' ? '***' : target.value;
                var selectors = generateSelectors(target);
                var description = target.placeholder || target.name || 'input';
                clearTimeout(target.__inputTimer);
                target.__inputTimer = setTimeout(function() {
                    console.log('[RecorderEvent]', JSON.stringify({
                        action: 'fill', selectors: selectors, value: value,
                        description: description, timestamp: Date.now()
                    }));
                }, 500);
            }, true);

            document.addEventListener('change', function(e) {
                var target = e.target;
                if (!target || target.tagName !== 'SELECT') return;
                var opt = target.options[target.selectedIndex];
                console.log('[RecorderEvent]', JSON.stringify({
                    action: 'select', selectors: generateSelectors(target),
                    value: opt ? opt.text : target.value,
                    description: 'Select option', timestamp: Date.now()
                }));
            }, true);

            document.addEventListener('keydown', function(e) {
                var key = e.key;
                if (['Enter', 'Tab', 'Escape', 'Backspace', 'Delete', 'ArrowDown', 'ArrowUp', 'ArrowLeft', 'ArrowRight'].indexOf(key) === -1) return;
                var target = e.target;
                console.log('[RecorderEvent]', JSON.stringify({
                    action: 'press', selectors: target ? generateSelectors(target) : [],
                    value: key, description: 'Press ' + key, timestamp: Date.now()
                }));
            }, true);

            console.log('[Recorder] Event capture script injected (v2 - implicit roles + placeholder + label + uniqueness)');
        })();
        '''
        
        try:
            await page.add_init_script(script)
            # 也在当前页面执行一次（init_script 只对新页面生效）
            await page.evaluate(script)
            logger.info("[Inject] Event capture script injected successfully")
        except Exception as e:
            logger.warning(f"[Inject] Failed to inject event capture script: {e}")
    
    def _handle_captured_event(self, event_data: dict, step_counter: list):
        """
        处理从 JavaScript 捕获的事件
        
        Phase 11: 支持发现模式
        - 普通模式：记录为顺序步骤
        - 发现模式：识别 open_action 和 available_options
        """
        action = event_data.get('action')
        selectors = event_data.get('selectors', [])
        description = event_data.get('description', '')
        value = event_data.get('value', '')
        
        # 跳过空事件
        if not action or not selectors:
            return
        
        # Phase 11: 发现模式处理
        if self.discovery_mode and action == 'click':
            self._handle_discovery_click(selectors, description, step_counter)
            return
        
        # 普通模式：记录为顺序步骤
        self._handle_normal_event(action, selectors, description, value, step_counter)
    
    def _handle_discovery_click(self, selectors: list, description: str, step_counter: list):
        """
        处理发现模式下的点击事件
        
        逻辑：
        1. 第一次点击 -> 记录为 open_action
        2. 第二次点击（不同元素）-> 记录为选项
        3. 再次点击相同的 open 元素 -> 重置，准备记录下一个选项
        """
        # 获取主选择器（用于比较）
        primary_selector = self._get_primary_selector(selectors)
        
        # 检查是否是重复的 open 动作
        if self.open_action and primary_selector == self._last_click_selector:
            # 重复点击 open 元素，准备记录下一个选项
            logger.info(f"[Discovery] Repeated open action detected, ready for next option")
            return
        
        # 如果还没有 open_action，这是第一次点击
        if not self.open_action:
            self.open_action = {
                'action': 'click',
                'selectors': selectors,
                'description': description,
                'comment': f'Open {self.component_type}'
            }
            self._last_click_selector = primary_selector
            self._persist_live_steps()
            logger.info(f"[Discovery] Open action recorded: {description[:50]}")
            return
        
        # 否则，这是一个新选项
        # 检查是否已存在相同的选项（去重）
        for opt in self.available_options:
            if opt.get('text') == description:
                logger.debug(f"[Discovery] Option already exists: {description}")
                return
        
        # 生成选项 key
        option_key = self._generate_option_key(description)
        
        # 添加新选项
        option = {
            'key': option_key,
            'text': description,
            'selectors': selectors,
        }
        self.available_options.append(option)
        self._persist_live_steps()
        
        logger.info(f"[Discovery] New option discovered: {description} (key: {option_key})")
        print(f"[Discovery] Option {len(self.available_options)}: {description}")
    
    def _get_primary_selector(self, selectors: list) -> str:
        """获取主选择器（用于比较）"""
        if not selectors:
            return ''
        # 优先使用 CSS 选择器
        for sel in selectors:
            if sel.get('type') == 'css':
                return sel.get('value', '')
        # 降级使用第一个选择器
        return selectors[0].get('value', '')
    
    def _generate_option_key(self, text: str) -> str:
        """
        从文本生成选项 key
        
        例如：
        - "今天" -> "today"
        - "昨天" -> "yesterday"
        - "最近7天" -> "last_7_days"
        - "最近30天" -> "last_30_days"
        - "本月" -> "this_month"
        """
        # 常见日期选项映射
        date_mappings = {
            '今天': 'today',
            '昨天': 'yesterday',
            '前天': 'day_before_yesterday',
            '本周': 'this_week',
            '上周': 'last_week',
            '本月': 'this_month',
            '上月': 'last_month',
            '今年': 'this_year',
            '去年': 'last_year',
            'today': 'today',
            'yesterday': 'yesterday',
            'this week': 'this_week',
            'last week': 'last_week',
            'this month': 'this_month',
            'last month': 'last_month',
        }
        
        # 精确匹配
        text_lower = text.lower().strip()
        if text_lower in date_mappings:
            return date_mappings[text_lower]
        if text in date_mappings:
            return date_mappings[text]
        
        # 模式匹配：最近N天/天/days
        import re
        
        # 中文：最近7天、最近30天
        match = re.search(r'最近\s*(\d+)\s*天', text)
        if match:
            return f"last_{match.group(1)}_days"
        
        # 英文：Last 7 days, Last 30 days
        match = re.search(r'last\s*(\d+)\s*days?', text_lower)
        if match:
            return f"last_{match.group(1)}_days"
        
        # 降级：使用文本的拼音或简化形式
        # 移除特殊字符，转换为 snake_case
        key = re.sub(r'[^\w\u4e00-\u9fff]+', '_', text.lower())
        key = key.strip('_')
        
        return key or 'option'
    
    def _handle_normal_event(self, action: str, selectors: list, description: str, value: str, step_counter: list):
        """处理普通模式的事件（顺序步骤）"""
        primary = self._get_primary_selector(selectors)
        # 去重：与最近一步相同 action+description 则合并/跳过
        if self.recorded_steps:
            last_step = self.recorded_steps[-1]
            if (last_step.get('action') == action and
                    last_step.get('description') == description):
                if action == 'fill' and value:
                    last_step['value'] = value
                    return
                return
        # 加固去重：最近 2～3 步内相同 action + 主 selector 则合并/跳过
        recent = self.recorded_steps[-3:] if len(self.recorded_steps) >= 3 else self.recorded_steps
        for s in recent:
            if s.get('action') != action:
                continue
            s_primary = self._get_primary_selector(s.get('selectors') or [])
            if s_primary and primary and s_primary == primary:
                if action == 'fill' and value:
                    s['value'] = value
                return
        step_counter[0] += 1
        
        # 构建步骤
        step = {
            'id': step_counter[0],
            'action': action,
            'selectors': selectors,
            'description': description,
            'comment': f'{action.capitalize()}: {description[:40]}'
        }
        
        if action == 'fill' and value:
            step['value'] = value
        
        self.recorded_steps.append(step)
        self._persist_live_steps()
        logger.info(f"[Event] {action.capitalize()}: {description[:50]}")

    def _persist_live_steps(self):
        """Persist the latest recorder payload so the UI can poll during recording."""
        if not self.steps_file:
            return

        steps_data = self._build_discovery_output() if self.discovery_mode else self._build_steps_output()
        steps_path = Path(self.steps_file)
        steps_path.parent.mkdir(parents=True, exist_ok=True)
        with open(steps_path, 'w', encoding='utf-8') as f:
            json.dump(steps_data, f, ensure_ascii=False, indent=2)
    
    def _save_steps(self):
        """
        保存步骤到 JSON 文件
        """
        if not self.steps_file:
            logger.warning("No steps_file specified, skipping save")
            return
        
        print(f"\n[Save] Event-captured steps: {len(self.recorded_steps)}")
        
        # 如果没有手动记录的步骤，从 Trace 解析
        if not self.recorded_steps and self.trace_file:
            print(f"[Save] No event-captured steps, trying to parse Trace file...")
            try:
                import zipfile
                from backend.utils.trace_parser import TraceParser
                
                trace_path = Path(self.trace_file)
                print(f"[Save] Trace file path: {trace_path}")
                print(f"[Save] Trace file exists: {trace_path.exists()}")
                
                if trace_path.exists():
                    file_size = trace_path.stat().st_size
                    print(f"[Save] Trace file size: {file_size} bytes")
                    
                    # 验证 ZIP 文件
                    if file_size == 0:
                        print(f"[Save] ERROR: Trace file is empty (0 bytes)")
                    else:
                        try:
                            # 检查是否为有效 ZIP
                            with zipfile.ZipFile(trace_path, 'r') as zf:
                                file_list = zf.namelist()
                                print(f"[Save] Trace ZIP contains {len(file_list)} files")
                            
                            # 解析 Trace
                            parser = TraceParser()
                            result = parser.parse(str(trace_path))
                            
                            print(f"[Save] Trace parse success: {result.success}")
                            if result.success:
                                self.recorded_steps = result.steps
                                print(f"[Save] Parsed {len(result.steps)} steps from Trace")
                            else:
                                print(f"[Save] Trace parse error: {result.error}")
                        except zipfile.BadZipFile:
                            print(f"[Save] ERROR: Trace file is not a valid ZIP (corrupted)")
                            logger.error(f"Trace file is corrupted: {trace_path}")
                else:
                    print(f"[Save] Trace file does not exist!")
            except Exception as e:
                logger.warning(f"Failed to parse trace for steps: {e}")
                print(f"[Save] Exception: {e}")
        
        # Phase 11: 根据模式构建不同的输出结构
        if self.discovery_mode:
            steps_data = self._build_discovery_output()
        else:
            steps_data = self._build_steps_output()
        
        try:
            steps_path = Path(self.steps_file)
            steps_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(steps_path, 'w', encoding='utf-8') as f:
                json.dump(steps_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Steps saved to: {steps_path}")
            
            if self.discovery_mode:
                print(f"[Save] Discovery mode: {len(self.available_options)} options saved")
            else:
                print(f"[Save] Steps mode: {len(self.recorded_steps)} steps saved")
        except Exception as e:
            logger.error(f"Failed to save steps: {e}")
    
    def _build_steps_output(self) -> Dict[str, Any]:
        """构建普通步骤模式的输出"""
        return {
            'platform': self.platform,
            'component_type': self.component_type,
            'mode': 'steps',
            'recorded_at': datetime.now().isoformat(),
            'start_url': self.start_url,
            'end_url': self.end_url,
            'steps': self.recorded_steps,
            'metadata': {
                'use_persistent_context': self.use_persistent_context,
                'use_fingerprint': self.use_fingerprint,
                'enable_trace': self.enable_trace,
            }
        }
    
    def _build_discovery_output(self) -> Dict[str, Any]:
        """
        构建发现模式的输出
        
        结构：
        {
            "mode": "discovery",
            "open_action": {...},
            "available_options": [...],
            "default_option": "last_7_days",
            "test_config": {"test_url": "..."}  // Phase 12.2: 自动捕获
        }
        """
        # 确定默认选项（优先使用 last_7_days，否则用第一个）
        default_option = None
        for opt in self.available_options:
            if 'last_7_days' in opt.get('key', ''):
                default_option = opt['key']
                break
        if not default_option and self.available_options:
            default_option = self.available_options[0].get('key')
        
        # Phase 12.2: 自动捕获当前页面 URL 作为 test_config
        test_config = self._build_test_config()
        
        return {
            'platform': self.platform,
            'component_type': self.component_type,
            'mode': 'discovery',
            'recorded_at': datetime.now().isoformat(),
            'start_url': self.start_url,
            'end_url': self.end_url,
            'open_action': self.open_action,
            'available_options': self.available_options,
            'default_option': default_option,
            'test_config': test_config,
            'metadata': {
                'use_persistent_context': self.use_persistent_context,
                'use_fingerprint': self.use_fingerprint,
                'enable_trace': self.enable_trace,
                'options_count': len(self.available_options),
            }
        }
    
    def _build_test_config(self) -> Dict[str, str]:
        """
        构建测试配置（Phase 12.2）
        
        自动将当前页面 URL 转换为使用 {{account.login_url}} 变量的格式
        """
        current_url = self.end_url or ''
        
        if not current_url:
            return {}
        
        # 尝试将绝对 URL 转换为使用变量的格式
        # 例如: https://miaoshou.com/portal/sale/order -> {{account.login_url}}/portal/sale/order
        login_url = self.account_info.get('login_url', '') if self.account_info else ''
        
        if login_url and current_url.startswith(login_url):
            # 替换为变量格式
            test_url = current_url.replace(login_url, '{{account.login_url}}')
        else:
            # 无法替换，使用原始 URL
            test_url = current_url
        
        return {
            'test_url': test_url
        }


async def main_async(config_path: str):
    """
    异步主函数
    """
    # 读取配置
    config_path = Path(config_path)
    if not config_path.exists():
        print(f"[ERROR] Config file not found: {config_path}")
        return False
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 创建录制器并开始录制
    recorder = InspectorRecorder(config)
    return await recorder.record()


def main():
    """
    主函数
    """
    parser = argparse.ArgumentParser(description='Inspector API Recorder')
    parser.add_argument('--config', required=True, help='Path to config JSON file')
    
    args = parser.parse_args()
    
    # 运行异步主函数
    success = asyncio.run(main_async(args.config))
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
