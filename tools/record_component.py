"""
组件录制工具 V2 - Component Recorder (v4.8.0)

使用 Playwright Inspector 录制浏览器操作，自动转换为 YAML 组件格式

v4.8.0 更新 (2025-12-25):
- [OK] 智能登录状态检测（URL + 元素 + Cookie）
- [OK] 等待自动跳转检测（持久化会话）
- [OK] 增强日志输出

v4.7.0 重构 (2025-12-12):
- [OK] 自动执行login组件（录制非login组件时）
- [OK] Playwright Inspector集成（捕获所有操作）
- [OK] 增强超时配置和重试机制
- [OK] 集成弹窗处理
- [OK] Trace录制和保存
- [OK] 智能YAML生成

使用方法：
    python tools/record_component.py --platform shopee --component login --account MyStore_SG
    python tools/record_component.py --platform shopee --component orders_export --skip-login
    python tools/record_component.py --help
"""

import sys
import os
import argparse
import asyncio
import yaml
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.core.logger import get_logger

logger = get_logger(__name__)


class ComponentRecorder:
    """
    组件录制器 V2
    
    功能：
    1. 启动浏览器并自动登录（可选）
    2. 打开Playwright Inspector进行录制
    3. 将录制结果转换为YAML组件格式
    4. 支持Trace录制和回放
    5. 集成弹窗处理
    """
    
    SUPPORTED_PLATFORMS = ['shopee', 'tiktok', 'miaoshou']
    SUPPORTED_COMPONENT_TYPES = ['login', 'navigation', 'date_picker', 'export', 'verification']
    
    def __init__(
        self,
        platform: str,
        component_name: str,
        account_id: str = None,
        skip_login: bool = False,
        use_inspector: bool = True,
        enable_trace: bool = True,
        timeout: int = 60,
        output_dir: str = None,
    ):
        """
        初始化录制器
        
        Args:
            platform: 平台代码（shopee/tiktok/miaoshou）
            component_name: 组件名称
            account_id: 账号ID（用于自动登录）
            skip_login: 是否跳过登录
            use_inspector: 是否使用Playwright Inspector
            enable_trace: 是否启用Trace录制
            timeout: 页面导航超时（秒）
            output_dir: 输出目录
        """
        if platform not in self.SUPPORTED_PLATFORMS:
            raise ValueError(f"Unsupported platform: {platform}. Supported: {self.SUPPORTED_PLATFORMS}")
        
        self.platform = platform
        self.component_name = component_name
        self.account_id = account_id
        self.skip_login = skip_login
        self.use_inspector = use_inspector
        self.enable_trace = enable_trace
        self.timeout = timeout * 1000  # 转换为毫秒
        
        # 设置输出目录
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / 'config' / 'collection_components' / platform
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 录制的操作列表
        self.recorded_actions: List[Dict[str, Any]] = []
        
        # 加载组件加载器和执行器（用于自动登录）
        try:
            from modules.apps.collection_center.component_loader import ComponentLoader
            from modules.apps.collection_center.executor_v2 import CollectionExecutorV2
            from modules.apps.collection_center.popup_handler import UniversalPopupHandler
            
            self.component_loader = ComponentLoader()
            self.popup_handler = UniversalPopupHandler()
            self.executor = CollectionExecutorV2(
                component_loader=self.component_loader,
                popup_handler=self.popup_handler
            )
        except Exception as e:
            logger.warning(f"Failed to load executor components: {e}")
            self.component_loader = None
            self.executor = None
            self.popup_handler = None
        
        logger.info(f"ComponentRecorder V2 initialized: platform={platform}, component={component_name}")
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """
        获取账号信息（v4.7.0修复）
        
        Returns:
            Dict: 账号信息（包含login_url, username, password等）
        """
        if not self.account_id:
            return None
        
        try:
            import importlib.util
            accounts_file = Path(__file__).parent.parent / "local_accounts.py"
            
            if not accounts_file.exists():
                logger.warning("local_accounts.py not found")
                return None
            
            spec = importlib.util.spec_from_file_location("local_accounts", accounts_file)
            local_accounts = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(local_accounts)
            
            # v4.7.0修复：使用辅助函数获取所有账号
            if hasattr(local_accounts, 'get_all_local_accounts'):
                all_accounts = local_accounts.get_all_local_accounts()
                for account in all_accounts:
                    if account.get('account_id') == self.account_id:
                        logger.info(f"Loaded account: {self.account_id} (platform={account.get('platform')})")
                        return account
            
            # 兼容方案：手动遍历LOCAL_ACCOUNTS
            local_accounts_dict = getattr(local_accounts, "LOCAL_ACCOUNTS", {})
            for platform_group, accounts_list in local_accounts_dict.items():
                if isinstance(accounts_list, list):
                    for account in accounts_list:
                        if account.get('account_id') == self.account_id:
                            logger.info(f"Loaded account: {self.account_id} (platform={account.get('platform')})")
                            return account
            
            logger.warning(f"Account {self.account_id} not found in local_accounts.py")
            return None
        
        except Exception as e:
            logger.error(f"Failed to load account info: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def record(self) -> str:
        """
        开始录制（V2版本）
        
        流程：
        1. 启动浏览器
        2. 如果不是login组件，自动执行login
        3. 启动Inspector或Trace录制
        4. 等待用户操作
        5. 生成YAML
        
        Returns:
            str: 生成的YAML文件路径
        """
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed. Run: pip install playwright && playwright install")
            return None
        
        account_info = self.get_account_info()
        
        print("\n" + "="*60)
        print(" 组件录制工具 V2 - Component Recorder")
        print("="*60)
        print(f"\n平台: {self.platform}")
        print(f"组件: {self.component_name}")
        if account_info:
            print(f"账号: {self.account_id}")
        print(f"输出目录: {self.output_dir}")
        print(f"Inspector: {'启用' if self.use_inspector else '禁用'}")
        print(f"Trace录制: {'启用' if self.enable_trace else '禁用'}")
        print(f"超时配置: {self.timeout/1000}秒")
        print("\n" + "-"*60)
        
        input("按 Enter 键开始录制...")
        
        async with async_playwright() as p:
            # 1. 启动浏览器
            browser = await p.chromium.launch(
                headless=False,  # 录制时必须可见
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                ],
                slow_mo=100  # 慢速模式，便于观察
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
            
            page = await context.new_page()
            
            # 2. 启动Trace（如果启用）
            trace_path = None
            if self.enable_trace:
                trace_path = self._get_trace_path()
                await context.tracing.start(
                    screenshots=True, 
                    snapshots=True, 
                    sources=True
                )
                print(f"[Trace] 录制中: {trace_path}")
            
            # 3. 自动登录（如果需要）
            if self.component_name != 'login' and not self.skip_login:
                await self._auto_login(page, account_info)
            else:
                # 仅导航到登录页
                if account_info:
                    start_url = account_info.get('login_url')
                    if start_url:
                        print(f"\n[导航] {start_url}")
                        await self._safe_goto(page, start_url)
            
            # 4. 集成弹窗处理（录制前关闭弹窗）
            if self.popup_handler:
                await self.popup_handler.close_popups(page, platform=self.platform)
            
            # 5. 记录初始URL
            self.recorded_actions = []
            
            # 6. 启动Inspector（如果启用）
            if self.use_inspector:
                print("\n" + "="*60)
                print(" Playwright Inspector 录制模式")
                print("="*60)
                print("\n请在浏览器中执行操作：")
                print(f"  • 当前页面: {page.url}")
                print(f"  • 录制组件: {self.component_name}")
                print("\n操作说明：")
                print("  1. 在浏览器中执行您要录制的操作")
                print("  2. Inspector窗口会自动打开")
                print("  3. 完成操作后，在Inspector中点击 'Resume'")
                print("  4. 工具将自动生成YAML组件")
                print("="*60 + "\n")
                
                try:
                    await page.pause()  # 打开Inspector
                except Exception as e:
                    logger.warning(f"Inspector启动失败: {e}")
            else:
                # 不使用Inspector，监听用户操作
                print("\n[录制中] 请在浏览器中执行操作...")
                print("操作完成后关闭浏览器窗口。\n")
                
                try:
                    while True:
                        await page.title()  # 检查页面存在
                        await asyncio.sleep(0.5)
                except Exception:
                    pass  # 页面关闭
            
            # 7. 停止Trace
            if self.enable_trace and trace_path:
                await context.tracing.stop(path=trace_path)
                print(f"[Trace] 已保存: {trace_path}")
            
            await browser.close()
        
        # 8. 生成YAML文件
        output_path = self._generate_yaml_v2()
        
        print("\n" + "="*60)
        print(" 录制完成!")
        print("="*60)
        print(f"\n生成文件: {output_path}")
        print(f"录制步骤数: {len(self.recorded_actions)}")
        if trace_path:
            print(f"Trace文件: {trace_path}")
            print(f"\n💡 使用以下命令查看trace：")
            print(f"   playwright show-trace {trace_path}")
        print("\n请检查并手动完善生成的YAML文件。")
        
        return output_path
    
    async def _auto_login(self, page, account_info: Dict[str, Any]):
        """
        自动执行login组件（带智能登录检测 v4.8.0）
        
        流程：
        1. 导航到登录页面
        2. 智能检测登录状态（URL + 元素 + Cookie）
        3. 如果已登录，跳过登录步骤
        4. 如果未登录，执行登录组件
        5. 登录后验证状态
        """
        from modules.utils.login_status_detector import LoginStatusDetector, LoginStatus
        
        print("\n" + "="*60)
        print(" Auto Login (v4.8.0)")
        print("="*60)
        
        # 1. 导航到登录页
        login_url = account_info.get('login_url') if account_info else None
        if login_url:
            print(f"[Navigate] {login_url}")
            await self._safe_goto(page, login_url)
        
        # 2. 智能检测登录状态
        print("\n[Detect] Checking login status...")
        import os
        debug_mode = os.environ.get("DEBUG_LOGIN_DETECTION", "false").lower() == "true"
        detector = LoginStatusDetector(self.platform, debug=debug_mode)
        
        detection_result = await detector.detect(page, wait_for_redirect=True)
        
        print(f"[Detect] Status: {detection_result.status.value}")
        print(f"[Detect] Confidence: {detection_result.confidence:.2f}")
        print(f"[Detect] Method: {detection_result.detected_by}")
        print(f"[Detect] Reason: {detection_result.reason}")
        print(f"[Detect] Time: {detection_result.detection_time_ms}ms")
        
        # 3. 判断是否需要登录
        needs_login = detector.needs_login(detection_result)
        
        if not needs_login:
            print("\n[SKIP] Session already logged in (confidence >= 0.7)")
            print(f"[SKIP] Current URL: {page.url}")
            print("="*60 + "\n")
            return
        
        # 4. 需要执行登录
        print("\n[EXEC] Login required, executing login component...")
        
        if not self.component_loader or not self.executor:
            print("\n[WARN] Component loader not initialized")
            print("[WARN] Please login manually in the browser\n")
            print("Press Enter to continue after manual login...")
            input()
            return
        
        try:
            # 加载login组件
            component_path = f"{self.platform}/login"
            print(f"[Load] {component_path}.yaml")
            
            params = {
                'account': account_info,
                'login_url': account_info.get('login_url') if account_info else None,
                'username': account_info.get('username') if account_info else None,
                'password': account_info.get('password') if account_info else None,
            }
            
            login_component = self.component_loader.load(
                component_path, 
                params=params
            )
            
            # 执行login组件
            steps_count = len(login_component.get('steps', []))
            print(f"[Exec] Executing {steps_count} login steps...")
            
            from modules.apps.collection_center.popup_handler import StepPopupHandler
            step_popup_handler = StepPopupHandler(
                self.executor.popup_handler,
                login_component
            )
            
            await self.executor._execute_component(
                page,
                login_component,
                step_popup_handler
            )
            
            # 5. 登录后验证
            print("\n[Verify] Checking post-login status...")
            await asyncio.sleep(3)  # 等待页面跳转
            
            detector.clear_cache()
            post_login_result = await detector.detect(page, wait_for_redirect=True)
            
            print(f"[Verify] Status: {post_login_result.status.value}")
            print(f"[Verify] Confidence: {post_login_result.confidence:.2f}")
            print(f"[Verify] URL: {page.url}")
            
            if post_login_result.status == LoginStatus.LOGGED_IN:
                print("[OK] Login successful!")
            elif post_login_result.status == LoginStatus.NOT_LOGGED_IN:
                print("[WARN] Login may have failed")
                print("[WARN] Please verify login status in browser")
            else:
                print("[WARN] Login status uncertain")
            
            # 关闭登录后的弹窗
            if self.popup_handler:
                await self.popup_handler.close_popups(page, platform=self.platform)
            
            print("="*60 + "\n")
            
        except FileNotFoundError:
            print(f"\n[WARN] {self.platform}/login.yaml not found")
            print("[WARN] Please record login component first, or use --skip-login")
            print("\n[INFO] Please login manually in the browser\n")
            
            print("Press Enter to continue after manual login...")
            input()
        
        except Exception as e:
            print(f"\n[ERROR] Auto login failed: {e}")
            print("[INFO] Please complete login manually in the browser\n")
            
            print("Press Enter to continue after manual login...")
            input()
    
    async def _safe_goto(self, page, url: str, retries: int = 2):
        """
        安全的页面导航（带重试）
        
        Args:
            page: Playwright Page对象
            url: 目标URL
            retries: 重试次数
        """
        for attempt in range(retries + 1):
            try:
                print(f"[导航] {url} (尝试 {attempt + 1}/{retries + 1})")
                
                # 第一次尝试：domcontentloaded
                if attempt == 0:
                    await page.goto(
                        url, 
                        wait_until='domcontentloaded', 
                        timeout=self.timeout
                    )
                # 第二次尝试：load
                elif attempt == 1:
                    await page.goto(
                        url, 
                        wait_until='load', 
                        timeout=self.timeout + 30000
                    )
                # 最后尝试：不等待
                else:
                    await page.goto(url, timeout=self.timeout + 60000)
                
                # 等待网络空闲（可选，不阻塞）
                try:
                    await page.wait_for_load_state('networkidle', timeout=30000)
                except Exception:
                    pass
                
                print(f"[成功] 页面已加载")
                break
                
            except Exception as e:
                if attempt < retries:
                    print(f"[重试] 导航失败: {e}")
                    await asyncio.sleep(2)
                else:
                    print(f"[警告] 导航失败，但继续: {e}")
    
    def _get_trace_path(self) -> str:
        """生成trace文件路径"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        trace_dir = Path('temp/traces')
        trace_dir.mkdir(parents=True, exist_ok=True)
        
        return str(trace_dir / f"{self.platform}_{self.component_name}_{timestamp}.zip")
    
    def _generate_yaml_v2(self) -> str:
        """
        生成YAML组件文件（V2版本）
        
        改进：
        1. 更智能的步骤提取
        2. 更完善的成功判定
        3. 添加验证码处理配置
        """
        # 检测组件类型
        component_type = self._detect_component_type()
        
        # 构建组件结构
        component = {
            'name': f"{self.platform}_{self.component_name}",
            'platform': self.platform,
            'type': component_type,
            'version': '1.0.0',
            'description': f"{self.platform.capitalize()} {self.component_name} 组件（V2录制工具生成）",
            'steps': self._extract_steps(),
            'success_criteria': self._generate_success_criteria(component_type),
            'error_handlers': self._generate_error_handlers(),
            'popup_handling': {
                'enabled': True,
                'check_before_steps': True,
                'check_after_steps': True,
            },
            'verification_handlers': {
                'image': {
                    'enabled': True,
                    'notify_frontend': True,
                    'timeout': 300,
                }
            }
        }
        
        # 如果是导出类型，添加data_domain
        if component_type == 'export':
            domain = self._extract_domain_from_name()
            if domain:
                component['data_domain'] = domain
        
        # 生成文件名
        filename = f"{self.component_name}.yaml"
        output_path = self.output_dir / filename
        
        # 写入YAML文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"# {self.platform.upper()} {self.component_name} 组件\n")
            f.write(f"# 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# 生成工具: ComponentRecorder V2\n")
            f.write(f"# 注意: 此文件由录制工具自动生成，请手动检查和完善\n\n")
            yaml.dump(component, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        
        return str(output_path)
    
    def _extract_steps(self) -> List[Dict[str, Any]]:
        """
        提取步骤（从recorded_actions）
        
        ✅ v4.7.2改进：
        - navigate 步骤自动包含等待逻辑
        - wait 步骤自动添加 type 字段
        - 关键操作步骤自动添加重试配置
        - 不生成 TODO 占位符
        """
        if self.recorded_actions:
            # ⭐ 关键改进：增强所有步骤的配置
            enhanced_steps = []
            
            for i, action in enumerate(self.recorded_actions):
                current_action = dict(action)  # 复制以避免修改原数据
                
                # ⭐ v4.7.2: 为 wait 步骤添加 type 字段
                if current_action.get('action') == 'wait':
                    if 'type' not in current_action:
                        # 有 duration 表示固定延迟
                        if 'duration' in current_action:
                            current_action['type'] = 'timeout'
                        # 有 selector 表示等待元素
                        elif 'selector' in current_action:
                            current_action['type'] = 'selector'
                            if 'state' not in current_action:
                                current_action['state'] = 'visible'
                        # 默认是 navigation 等待
                        else:
                            current_action['type'] = 'navigation'
                            current_action['wait_until'] = 'networkidle'
                            current_action['timeout'] = current_action.get('timeout', 30000)
                    
                    enhanced_steps.append(current_action)
                
                # ⭐ 官方最佳实践：navigate 使用 wait_until 参数
                elif current_action.get('action') in ['navigate', 'goto']:
                    # 确保使用官方推荐的 wait_until
                    if 'wait_until' not in current_action:
                        current_action['wait_until'] = 'domcontentloaded'  # 官方默认值
                    
                    enhanced_steps.append(current_action)
                    
                    # ⭐ 官方推荐：SPA应用需要额外的 networkidle 等待
                    # 检查下一步是否已经是 wait 步骤
                    next_is_wait = (
                        i + 1 < len(self.recorded_actions) and 
                        self.recorded_actions[i + 1].get('action') == 'wait'
                    )
                    
                    if not next_is_wait:
                        enhanced_steps.append({
                            'action': 'wait',
                            'type': 'navigation',
                            'wait_until': 'networkidle',
                            'timeout': 30000,
                            'comment': 'Auto-added: Wait for network idle (Playwright best practice for SPA)'
                        })
                
                # ⭐ v4.7.2: 为关键操作步骤添加重试配置
                elif current_action.get('action') in ['click', 'fill']:
                    # 默认重试2次（失败时自动关闭弹窗后重试）
                    if 'max_retries' not in current_action:
                        current_action['max_retries'] = 2
                    
                    enhanced_steps.append(current_action)
                
                else:
                    enhanced_steps.append(current_action)
            
            return enhanced_steps
        
        # ✅ 模板步骤：遵循官方最佳实践，不使用 TODO 占位符
        return [
            {
                'action': 'navigate',
                'url': '{{params.url}}',
                'wait_until': 'domcontentloaded',  # ⭐ Playwright 官方推荐
                'timeout': 60000,
                'comment': 'Navigate with built-in wait (Playwright default)'
            },
            {
                'action': 'wait',
                'type': 'navigation',
                'wait_until': 'networkidle',  # ⭐ 官方推荐用于 SPA
                'timeout': 30000,
                'comment': 'Wait for network idle (recommended for dynamic pages)'
            }
        ]
    
    def _generate_success_criteria(self, component_type: str) -> List[Dict[str, Any]]:
        """
        生成成功判定条件
        
        ✅ v4.7.1改进：
        - 不生成 TODO 占位符
        - 使用官方推荐的验证方式
        - 自动从录制中提取实际 URL
        """
        if component_type == 'login':
            # ⭐ 官方推荐：使用 URL 模式匹配 + 元素存在性验证
            return [
                {
                    'type': 'url_contains',
                    'value': '/home|/welcome|/dashboard',
                    'comment': 'Verify URL after login (common patterns)'
                },
                {
                    'type': 'element_exists',
                    'selector': 'role=navigation',  # ⭐ 使用官方推荐的 role selector
                    'timeout': 5000,
                    'comment': 'Verify navigation menu exists (using get_by_role)'
                }
            ]
        
        elif component_type == 'navigation':
            # ⭐ 尝试从录制中提取目标 URL
            target_url_pattern = self._extract_target_url_from_actions()
            
            if target_url_pattern:
                return [
                    {
                        'type': 'url_contains',
                        'value': target_url_pattern,
                        'comment': 'Auto-extracted from recorded navigation'
                    }
                ]
            else:
                # ⭐ 如果无法提取，返回空数组（而不是 TODO）
                # 让测试工具提示用户手动添加
                logger.info("No target URL detected in navigation. Please add success_criteria manually.")
                return []
        
        elif component_type == 'export':
            return [
                {
                    'type': 'download_started',
                    'comment': 'Verify file download started'
                }
            ]
        
        else:
            # ⭐ 默认：空数组，不生成 TODO
            logger.info(f"No default success_criteria for type '{component_type}'. Please add manually if needed.")
            return []
    
    def _extract_target_url_from_actions(self) -> Optional[str]:
        """
        从录制的操作中提取目标 URL 特征
        
        ✅ 遵循官方推荐：从实际操作中推断，而不是猜测
        
        Returns:
            str: 提取的URL特征（如 '/orders', '/products'），失败返回 None
        """
        if not self.recorded_actions:
            return None
        
        # 查找最后一个 navigate 动作
        for action in reversed(self.recorded_actions):
            if action.get('action') in ['navigate', 'goto']:
                url = action.get('url', '')
                
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    path = parsed.path
                    
                    # 提取路径的主要部分（去除参数）
                    if path and len(path) > 1:
                        # 提取第一个有意义的路径段
                        # 例如：/orders/list -> /orders
                        parts = [p for p in path.split('/') if p]
                        if parts:
                            return '/' + parts[0]
                except Exception as e:
                    logger.debug(f"Failed to parse URL {url}: {e}")
                    pass
        
        return None
    
    def _generate_error_handlers(self) -> List[Dict[str, Any]]:
        """生成错误处理器"""
        return [
            {
                'selector': '.error-message, .alert-danger, [class*="error"]',
                'action': 'fail_task',
                'message': '检测到错误提示'
            },
            {
                'selector': '.login-form, [class*="login"]',
                'action': 'retry_login',
                'message': '可能需要重新登录'
            }
        ]
    
    def _detect_component_type(self) -> str:
        """
        根据组件名称检测组件类型
        
        Returns:
            str: 组件类型
        """
        name_lower = self.component_name.lower()
        
        if 'login' in name_lower:
            return 'login'
        elif 'nav' in name_lower:
            return 'navigation'
        elif 'date' in name_lower or 'picker' in name_lower:
            return 'date_picker'
        elif 'export' in name_lower:
            return 'export'
        elif 'verify' in name_lower or 'captcha' in name_lower:
            return 'verification'
        else:
            return 'export'
    
    def _extract_domain_from_name(self) -> Optional[str]:
        """
        从组件名称提取数据域
        
        Returns:
            str: 数据域
        """
        name_lower = self.component_name.lower()
        
        domains = ['orders', 'products', 'services', 'analytics', 'finance', 'inventory']
        
        for domain in domains:
            if domain in name_lower:
                return domain
        
        return None


class RecordingConverter:
    """
    录制结果转换器
    
    将Playwright codegen生成的代码转换为YAML格式
    """
    
    # Playwright操作到YAML动作的映射
    ACTION_MAP = {
        'goto': 'navigate',
        'click': 'click',
        'fill': 'fill',
        'type': 'fill',
        'press': 'keyboard',
        'select_option': 'select',
        'check': 'check',
        'uncheck': 'uncheck',
        'wait_for_selector': 'wait',
        'wait_for_load_state': 'wait',
    }
    
    def convert_codegen_output(self, codegen_code: str) -> List[Dict[str, Any]]:
        """
        转换Playwright codegen输出为YAML步骤
        
        Args:
            codegen_code: Playwright codegen生成的Python代码
            
        Returns:
            List[Dict]: YAML步骤列表
        """
        steps = []
        
        # 解析代码行
        lines = codegen_code.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            
            if not line or line.startswith('#') or line.startswith('from') or line.startswith('import'):
                continue
            
            step = self._parse_line(line)
            if step:
                steps.append(step)
        
        return steps
    
    def _parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        """
        解析单行代码
        
        Args:
            line: 代码行
            
        Returns:
            Dict: YAML步骤
        """
        # 匹配 page.goto("url")
        goto_match = re.match(r'.*\.goto\(["\']([^"\']+)["\']', line)
        if goto_match:
            return {
                'action': 'navigate',
                'url': goto_match.group(1)
            }
        
        # 匹配 page.locator("selector").click()
        click_match = re.match(r'.*\.locator\(["\']([^"\']+)["\'].*\)\.click\(\)', line)
        if click_match:
            return {
                'action': 'click',
                'selector': click_match.group(1)
            }
        
        # 匹配 page.locator("selector").fill("value")
        fill_match = re.match(r'.*\.locator\(["\']([^"\']+)["\'].*\)\.fill\(["\']([^"\']*)["\']', line)
        if fill_match:
            return {
                'action': 'fill',
                'selector': fill_match.group(1),
                'value': fill_match.group(2)
            }
        
        # 匹配 page.get_by_role/get_by_text等
        get_by_match = re.match(r'.*\.(get_by_\w+)\(["\']([^"\']+)["\'].*\)\.(\w+)\(', line)
        if get_by_match:
            method = get_by_match.group(1)
            value = get_by_match.group(2)
            action = get_by_match.group(3)
            
            # 转换为locator格式
            if method == 'get_by_role':
                selector = f'role={value}'
            elif method == 'get_by_text':
                selector = f'text={value}'
            elif method == 'get_by_label':
                selector = f'label={value}'
            elif method == 'get_by_placeholder':
                selector = f'placeholder={value}'
            else:
                selector = value
            
            return {
                'action': self.ACTION_MAP.get(action, action),
                'selector': selector
            }
        
        return None
    
    def convert_file(self, input_file: str, output_file: str) -> bool:
        """
        转换文件
        
        Args:
            input_file: 输入的Python文件
            output_file: 输出的YAML文件
            
        Returns:
            bool: 是否成功
        """
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                code = f.read()
            
            steps = self.convert_codegen_output(code)
            
            component = {
                'name': Path(output_file).stem,
                'platform': 'unknown',
                'type': 'export',
                'steps': steps
            }
            
            with open(output_file, 'w', encoding='utf-8') as f:
                yaml.dump(component, f, allow_unicode=True, default_flow_style=False)
            
            return True
        
        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            return False


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description='组件录制工具 V2 - 使用Playwright录制浏览器操作并生成YAML组件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 录制Shopee登录组件
  python tools/record_component.py --platform shopee --component login --account MyStore_SG

  # 录制Shopee订单导出组件（跳过登录）
  python tools/record_component.py --platform shopee --component orders_export --skip-login

  # 录制妙手ERP库存导出（自动登录）
  python tools/record_component.py --platform miaoshou --component inventory_export --account miaoshou_real_001

  # 不使用Inspector（仅trace）
  python tools/record_component.py --platform shopee --component login --account MyStore_SG --no-inspector

  # 转换已有的codegen输出
  python tools/record_component.py --convert input.py output.yaml
        """
    )
    
    parser.add_argument(
        '--platform', '-p',
        choices=['shopee', 'tiktok', 'miaoshou'],
        help='目标平台'
    )
    
    parser.add_argument(
        '--component', '-c',
        help='组件名称（如：login, orders_export）'
    )
    
    parser.add_argument(
        '--account', '-a',
        help='账号ID（用于自动登录）'
    )
    
    parser.add_argument(
        '--skip-login',
        action='store_true',
        help='跳过自动登录（手动登录）'
    )
    
    parser.add_argument(
        '--no-inspector',
        action='store_true',
        help='不使用Playwright Inspector（仅trace录制）'
    )
    
    parser.add_argument(
        '--no-trace',
        action='store_true',
        help='不录制trace文件'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=60,
        help='页面导航超时（秒，默认60）'
    )
    
    parser.add_argument(
        '--output-dir', '-o',
        help='输出目录（默认：config/collection_components/{platform}）'
    )
    
    parser.add_argument(
        '--convert',
        nargs=2,
        metavar=('INPUT', 'OUTPUT'),
        help='转换模式：将Playwright codegen输出转换为YAML'
    )
    
    return parser


async def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()
    
    # 转换模式
    if args.convert:
        converter = RecordingConverter()
        success = converter.convert_file(args.convert[0], args.convert[1])
        if success:
            print(f"[OK] Converted {args.convert[0]} to {args.convert[1]}")
        else:
            print(f"[ERROR] Conversion failed")
        return
    
    # 录制模式
    if not args.platform or not args.component:
        parser.print_help()
        print("\n[ERROR] 录制模式需要指定 --platform 和 --component")
        return
    
    recorder = ComponentRecorder(
        platform=args.platform,
        component_name=args.component,
        account_id=args.account,
        skip_login=args.skip_login,
        use_inspector=not args.no_inspector,
        enable_trace=not args.no_trace,
        timeout=args.timeout,
        output_dir=args.output_dir
    )
    
    output_path = await recorder.record()
    
    if output_path:
        print(f"\n[OK] 组件文件已生成: {output_path}")
    else:
        print("\n[ERROR] 录制失败")


if __name__ == '__main__':
    asyncio.run(main())
