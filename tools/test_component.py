"""
组件测试工具 - Component Tester

测试YAML组件配置是否正确执行

使用方法：
    python tools/test_component.py --platform shopee --component login --account MyStore_SG
    python tools/test_component.py --platform shopee --component orders_export --skip-login
    python tools/test_component.py --all --platform shopee
    python tools/test_component.py --help
"""

import sys
import os
import argparse
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum

# [*] 注意（2025-12-21）：
# Windows 上 Playwright 需要 ProactorEventLoop（默认），因为需要 create_subprocess_exec
# SelectorEventLoop 不支持 subprocess，会导致 NotImplementedError
# 所以不要设置 WindowsSelectorEventLoopPolicy

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.core.logger import get_logger
from modules.apps.collection_center.component_loader import ComponentLoader

logger = get_logger(__name__)


class TestStatus(Enum):
    """测试状态"""
    PENDING = 'pending'
    RUNNING = 'running'
    PASSED = 'passed'
    FAILED = 'failed'
    SKIPPED = 'skipped'


@dataclass
class StepResult:
    """步骤测试结果"""
    step_id: str
    action: str
    status: TestStatus
    duration_ms: float = 0
    error: str = None
    screenshot: str = None


@dataclass
class ComponentTestResult:
    """组件测试结果"""
    component_name: str
    platform: str
    status: TestStatus
    start_time: str = None
    end_time: str = None
    duration_ms: float = 0
    steps_total: int = 0
    steps_passed: int = 0
    steps_failed: int = 0
    step_results: List[StepResult] = field(default_factory=list)
    error: str = None


class ComponentTester:
    """
    组件测试器
    
    功能：
    1. 加载并验证组件配置
    2. 在浏览器中执行组件步骤
    3. 记录测试结果和截图
    4. 生成测试报告
    """
    
    def __init__(
        self,
        platform: str,
        account_id: str = None,
        skip_login: bool = False,
        headless: bool = False,
        screenshot_on_error: bool = True,
        output_dir: str = None,
        account_info: Dict[str, Any] = None,  # 新增：直接传入账号信息
        progress_callback: Callable[[str, dict], None] = None,  # [*] v4.7.3: 进度回调
    ):
        """
        初始化测试器（v4.7.3增强：支持实时进度回调）
        
        Args:
            platform: 平台代码
            account_id: 账号ID
            skip_login: 跳过登录
            headless: 无头模式
            screenshot_on_error: 错误时截图
            output_dir: 输出目录
            account_info: 账号信息字典（优先使用，避免从文件加载）
            progress_callback: 进度回调函数 (event_type: str, data: dict) -> None
        """
        self.platform = platform
        self.account_id = account_id
        self.skip_login = skip_login
        self.headless = headless
        self.screenshot_on_error = screenshot_on_error
        self._account_info = account_info  # 缓存传入的账号信息
        self.progress_callback = progress_callback  # [*] v4.7.3: 进度回调
        
        # 组件加载器
        self.component_loader = ComponentLoader()
        
        # 输出目录
        if output_dir is None:
            output_dir = Path(__file__).parent.parent / 'temp' / 'test_results'
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # 测试结果
        self.results: List[ComponentTestResult] = []
        
        logger.info(f"ComponentTester initialized: platform={platform}")
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        """获取账号信息（优先使用传入的account_info）"""
        # 优先使用传入的账号信息
        if self._account_info:
            return self._account_info
        
        if not self.account_id:
            return None
        
        # 降级：尝试从local_accounts.py加载（向后兼容）
        try:
            import importlib.util
            accounts_file = Path(__file__).parent.parent / "local_accounts.py"
            
            if not accounts_file.exists():
                return None
            
            spec = importlib.util.spec_from_file_location("local_accounts", accounts_file)
            local_accounts = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(local_accounts)
            
            return getattr(local_accounts, "ACCOUNTS", {}).get(self.account_id)
        except Exception as e:
            logger.error(f"Failed to load account: {e}")
            return None
    
    def list_components(self) -> List[str]:
        """
        列出平台的所有组件
        
        Returns:
            List[str]: 组件名称列表
        """
        components_dir = Path(__file__).parent.parent / 'config' / 'collection_components' / self.platform
        
        if not components_dir.exists():
            return []
        
        components = []
        for f in components_dir.glob('*.yaml'):
            if not f.name.startswith('popup_'):
                components.append(f.stem)
        
        return sorted(components)
    
    async def test_component(self, component_name: str) -> ComponentTestResult:
        """
        测试单个组件
        
        Args:
            component_name: 组件名称
            
        Returns:
            ComponentTestResult: 测试结果
        """
        result = ComponentTestResult(
            component_name=component_name,
            platform=self.platform,
            status=TestStatus.PENDING,
            start_time=datetime.now().isoformat()
        )
        
        try:
            # 加载组件
            component = self.component_loader.load(f"{self.platform}/{component_name}")
            
            # Phase 12: 判断是否为发现模式
            component_type = component.get('type', '')
            is_discovery_mode = component_type in ['date_picker', 'filters'] and 'open_action' in component
            
            if is_discovery_mode:
                available_options = component.get('available_options', [])
                result.steps_total = len(available_options) + 1  # open_action + options
            else:
                steps = component.get('steps', [])
                result.steps_total = len(steps)
            
            # #region agent log
            import json
            with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({'location':'test_component.py:180','message':'test_component: component loaded','data':{'steps_count':len(steps),'has_steps':len(steps)>0},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'F_I'})+'\n')
            # #endregion
            
            print(f"\n[TEST] {self.platform}/{component_name} ({len(steps)} steps)")
            
            # 验证组件结构
            validation_passed = self._validate_component_structure(component)
            # #region agent log
            with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({'location':'test_component.py:191','message':'test_component: validation result','data':{'validation_passed':validation_passed},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'I'})+'\n')
            # #endregion
            if not validation_passed:
                result.status = TestStatus.FAILED
                result.error = "Component structure validation failed"
                return result
            
            # 如果有Playwright，执行实际测试
            # #region agent log
            with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({'location':'test_component.py:202','message':'test_component: before _test_with_browser','data':{},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'F_G'})+'\n')
            # #endregion
            browser_test_passed = await self._test_with_browser(component, result)
            # #region agent log
            with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({'location':'test_component.py:209','message':'test_component: after _test_with_browser','data':{'browser_test_passed':browser_test_passed,'step_results_count':len(result.step_results)},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'F_G'})+'\n')
            # #endregion
            if browser_test_passed:
                result.status = TestStatus.PASSED
            else:
                result.status = TestStatus.FAILED
        
        except Exception as e:
            result.status = TestStatus.FAILED
            result.error = str(e)
            logger.error(f"Test failed for {component_name}: {e}")
        
        finally:
            result.end_time = datetime.now().isoformat()
            if result.start_time and result.end_time:
                start = datetime.fromisoformat(result.start_time)
                end = datetime.fromisoformat(result.end_time)
                result.duration_ms = (end - start).total_seconds() * 1000
        
        return result
    
    async def test_python_component(
        self, 
        component_path: str, 
        component_name: str
    ) -> ComponentTestResult:
        """
        测试 Python 组件（v4.8.0新增）
        
        Args:
            component_path: Python 组件文件路径
            component_name: 组件名称
            
        Returns:
            ComponentTestResult: 测试结果
        """
        result = ComponentTestResult(
            component_name=component_name,
            platform=self.platform,
            status=TestStatus.PENDING,
            start_time=datetime.now().isoformat()
        )
        
        try:
            from modules.apps.collection_center.component_loader import ComponentLoader
            from modules.apps.collection_center.python_component_adapter import PythonComponentAdapter, create_adapter
            
            # 1. 加载 Python 组件类
            loader = ComponentLoader()
            component_class = loader.load_python_component(self.platform, component_name)
            
            if not component_class:
                result.status = TestStatus.FAILED
                result.error = f"Failed to load Python component: {component_name}"
                return result
            
            # 2. 验证组件元数据（v4.8.0: 修复方法名和返回值处理）
            validation_result = loader.validate_python_component(component_class)
            if not validation_result.get('valid', False):
                result.status = TestStatus.FAILED
                errors = validation_result.get('errors', [])
                result.error = f"Python component validation failed: {', '.join(errors)}"
                return result
            
            # 3. 获取账号信息
            account_info = self.get_account_info()
            if not account_info:
                result.status = TestStatus.FAILED
                result.error = "Account info not available"
                return result
            
            # 4. 执行 Python 组件测试
            result.steps_total = 1  # Python 组件作为一个整体步骤
            
            test_passed = await self._test_python_component_with_browser(
                component_class=component_class,
                component_name=component_name,
                account_info=account_info,
                result=result
            )
            
            # v4.8.0: 综合判断 - 如果有 error，即使 test_passed 为 True 也应标记失败
            if test_passed and not result.error:
                result.status = TestStatus.PASSED
                result.steps_passed = 1
            else:
                result.status = TestStatus.FAILED
                result.steps_failed = 1
                if not result.error:
                    result.error = "Test execution failed"
        
        except Exception as e:
            result.status = TestStatus.FAILED
            result.error = str(e)
            logger.error(f"Python component test failed for {component_name}: {e}")
        
        finally:
            result.end_time = datetime.now().isoformat()
            if result.start_time and result.end_time:
                start = datetime.fromisoformat(result.start_time)
                end = datetime.fromisoformat(result.end_time)
                result.duration_ms = (end - start).total_seconds() * 1000
        
        return result
    
    async def _test_python_component_with_browser(
        self,
        component_class,
        component_name: str,
        account_info: Dict[str, Any],
        result: ComponentTestResult
    ) -> bool:
        """
        在浏览器中测试 Python 组件（v4.8.0新增 + 增强）
        
        Args:
            component_class: Python 组件类
            component_name: 组件名称
            account_info: 账号信息
            result: 测试结果对象
            
        Returns:
            bool: 是否测试通过
            
        v4.8.0 增强:
            - 支持 success_criteria 验证
            - 支持步骤回调传递给适配器
        """
        from playwright.async_api import async_playwright
        from modules.apps.collection_center.python_component_adapter import create_adapter
        
        browser = None
        
        try:
            async with async_playwright() as p:
                # 启动浏览器
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=['--start-maximized']
                )
                
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    locale='zh-CN'
                )
                
                page = await context.new_page()
                
                # v4.8.0: 创建适配器时传递步骤回调
                adapter = create_adapter(
                    platform=self.platform,
                    account=account_info,
                    config={'output_dir': str(self.output_dir)},
                    step_callback=self.progress_callback,  # v4.8.0: 传递回调
                    is_test_mode=True,  # v4.8.0: 标记为测试模式
                )
                
                # 获取组件类型
                component_type = getattr(component_class, 'component_type', 'export')
                
                # 发送进度回调
                if self.progress_callback:
                    try:
                        import asyncio
                        if asyncio.iscoroutinefunction(self.progress_callback):
                            await self.progress_callback('step_start', {
                                'step_index': 1,
                                'step_total': 1,
                                'action': f'Execute Python component: {component_name}'
                            })
                        else:
                            self.progress_callback('step_start', {
                                'step_index': 1,
                                'step_total': 1,
                                'action': f'Execute Python component: {component_name}'
                            })
                    except Exception as cb_err:
                        logger.warning(f"Progress callback error (ignored): {cb_err}")
                
                start_time = datetime.now()
                
                # 根据组件类型执行
                if component_type == 'login':
                    exec_result = await adapter.login(page)
                elif component_type == 'navigation':
                    exec_result = await adapter.navigate(page, target_page=component_name)
                elif component_type == 'export':
                    data_domain = getattr(component_class, 'data_domain', 'orders')
                    exec_result = await adapter.export(page=page, data_domain=data_domain)
                elif component_type == 'date_picker':
                    exec_result = await adapter.date_picker(page, None)
                else:
                    # 直接执行组件
                    exec_result = await adapter.execute_component(
                        component_name=component_name,
                        page=page,
                        params={}
                    )
                
                duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                
                # v4.8.0: 验证 success_criteria（如果组件定义了）
                success_criteria_passed = True
                if exec_result.success:
                    success_criteria = getattr(component_class, 'success_criteria', [])
                    if success_criteria:
                        logger.info(f"Verifying {len(success_criteria)} success criteria for Python component...")
                        success_criteria_passed = await self._verify_success_criteria(page, success_criteria)
                        
                        if not success_criteria_passed:
                            logger.warning("Python component success criteria verification failed")
                            result.error = "Success criteria verification failed"
                
                # 综合判断：步骤成功 + success_criteria 通过
                test_passed = exec_result.success and success_criteria_passed
                
                # 记录步骤结果
                step_result = StepResult(
                    step_id='python_component_1',
                    action=f'Execute {component_name}',
                    status=TestStatus.PASSED if test_passed else TestStatus.FAILED,
                    duration_ms=duration_ms,
                    error=result.error if not test_passed else None
                )
                result.step_results.append(step_result)
                
                # 发送进度回调
                if self.progress_callback:
                    try:
                        event_type = 'step_success' if test_passed else 'step_failed'
                        import asyncio
                        if asyncio.iscoroutinefunction(self.progress_callback):
                            await self.progress_callback(event_type, {
                                'step_index': 1,
                                'step_total': 1,
                                'action': f'Execute Python component: {component_name}',
                                'duration_ms': duration_ms
                            })
                        else:
                            self.progress_callback(event_type, {
                                'step_index': 1,
                                'step_total': 1,
                                'action': f'Execute Python component: {component_name}',
                                'duration_ms': duration_ms
                            })
                    except Exception as cb_err:
                        logger.warning(f"Progress callback error (ignored): {cb_err}")
                
                # 截图保存
                if self.screenshot_on_error and not test_passed:
                    screenshot_path = self.output_dir / f"{component_name}_error_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                    await page.screenshot(path=str(screenshot_path))
                    step_result.screenshot = str(screenshot_path)
                
                await context.close()
                await browser.close()
                
                return test_passed
        
        except Exception as e:
            logger.error(f"Python component browser test failed: {e}")
            result.error = str(e)
            
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            
            return False
    
    def _validate_component_structure(self, component: Dict[str, Any]) -> bool:
        """
        验证组件结构
        
        Phase 12: 支持发现模式组件（date_picker, filters）
        
        Args:
            component: 组件配置
            
        Returns:
            bool: 是否有效
        """
        # 检查必填字段
        if 'name' not in component:
            logger.error(f"Missing required field: name")
            return False
        
        # Phase 12: 判断是否为发现模式组件
        component_type = component.get('type', '')
        is_discovery_mode = component_type in ['date_picker', 'filters'] and 'open_action' in component
        
        if is_discovery_mode:
            # 发现模式组件验证
            return self._validate_discovery_component(component)
        
        # 普通模式组件需要 steps
        if 'steps' not in component:
            logger.error(f"Missing required field: steps")
            return False
        
        steps = component.get('steps', [])
        
        for i, step in enumerate(steps):
            if 'action' not in step:
                logger.error(f"Step {i+1} missing 'action' field")
                return False
            
            action = step['action']
            
            # 验证特定动作的必填字段
            if action == 'navigate' and 'url' not in step:
                logger.error(f"Step {i+1}: 'navigate' requires 'url'")
                return False
            
            # [OK] v4.7.0修复：wait步骤验证逻辑（与executor_v2.py对齐）
            if action == 'wait':
                wait_type = step.get('type', 'timeout')
                
                if wait_type == 'timeout':
                    # 固定延迟必须有duration字段
                    if 'duration' not in step:
                        logger.error(f"Step {i+1}: wait步骤type='timeout'时必须提供'duration'字段")
                        return False
                
                elif wait_type == 'selector':
                    # 等待元素必须有selector字段
                    if 'selector' not in step:
                        logger.error(f"Step {i+1}: wait步骤type='selector'时必须提供'selector'字段")
                        return False
                    
                    # 检测TODO占位符
                    selector_val = step.get('selector', '')
                    if 'TODO' in str(selector_val).upper():
                        logger.error(f"Step {i+1}: wait步骤包含TODO占位符，请手动完善或标记为optional")
                        logger.error(f"  当前selector: {selector_val}")
                        return False
                
                elif wait_type == 'navigation':
                    # 页面加载等待，可选的wait_until字段
                    pass
                
                else:
                    logger.error(f"Step {i+1}: wait步骤不支持的type: {wait_type}，支持: timeout/selector/navigation")
                    return False
            
            if action in ['click', 'fill'] and 'selector' not in step:
                logger.error(f"Step {i+1}: '{action}' requires 'selector'")
                return False
            
            if action == 'fill' and 'value' not in step:
                logger.error(f"Step {i+1}: 'fill' requires 'value'")
                return False
        
        # [*] v4.7.1新增：检查 success_criteria 的有效性
        success_criteria = component.get('success_criteria', [])
        
        if not success_criteria:
            logger.warning("No success_criteria defined. Test will only check if steps complete without errors.")
            logger.info("Tip: Add success_criteria to verify the component achieved its goal")
        
        for i, criterion in enumerate(success_criteria):
            criterion_type = criterion.get('type')
            value = criterion.get('value', '')
            
            # 检查 TODO 占位符
            if 'TODO' in str(value).upper():
                if criterion.get('optional', False):
                    logger.warning(f"Criterion {i+1}: Contains TODO placeholder (optional, will be skipped)")
                else:
                    logger.error(f"Criterion {i+1}: Contains TODO placeholder but is not marked as optional")
                    logger.error(f"  Current value: {value}")
                    logger.info(f"  Fix: Either fill in the actual value OR set 'optional: true'")
                    return False
            
            # 检查空值
            if not value and criterion_type in ['url_contains', 'element_exists', 'element_visible']:
                if not criterion.get('optional', False):
                    logger.warning(f"Criterion {i+1}: '{criterion_type}' has empty value (not optional, may cause test to fail)")
                    logger.info(f"  Tip: Use Playwright Inspector to find the right selector or URL pattern")
            
            # [*] 推荐使用官方 role-based selector
            if criterion_type in ['element_exists', 'element_visible']:
                selector = criterion.get('selector', '')
                if selector and not any(prefix in selector for prefix in ['role=', 'text=', 'label=', 'placeholder=']):
                    logger.info(f"Tip for criterion {i+1}: Consider using Playwright's role-based selectors:")
                    logger.info(f"     role=button[name='Login']  (recommended)")
                    logger.info(f"     text='Welcome'")
                    logger.info(f"     label='Email'")
        
        return True
    
    async def _test_with_browser(self, component: Dict[str, Any], result: ComponentTestResult) -> bool:
        """
        使用浏览器执行测试（异步版本，符合Playwright官方建议）
        
        Phase 12.5增强：
        1. 导出/日期/筛选器组件使用持久化浏览器上下文
        2. 登录后立即清理弹窗和通知
        3. 增强错误诊断信息
        
        Args:
            component: 组件配置
            result: 测试结果对象
            
        Returns:
            bool: 是否成功
        """
        try:
            from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
        except ImportError:
            logger.warning("Playwright not installed, skipping browser test")
            result.status = TestStatus.SKIPPED
            result.error = "Playwright not installed"
            return True  # 标记为跳过但不失败
        
        account_info = self.get_account_info()
        
        # #region agent log
        import json
        with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
            f.write(json.dumps({'location':'test_component.py:293','message':'_test_with_browser: got account_info','data':{'has_account':account_info is not None,'account_id':self.account_id},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'H'})+'\n')
        # #endregion
        
        # Phase 12.5: 判断是否需要使用持久化上下文
        component_type = component.get('type', '')
        use_persistent_context = component_type in ['export', 'date_picker', 'filters'] and not self.skip_login
        
        browser = None  # 持久化上下文不直接管理浏览器
        
        try:
            async with async_playwright() as p:
                # #region agent log
                with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({'location':'test_component.py:301','message':'_test_with_browser: launching browser','data':{'headless':self.headless,'use_persistent':use_persistent_context},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'G'})+'\n')
                # #endregion
                
                # Phase 12.5: 根据组件类型选择浏览器上下文
                if use_persistent_context:
                    # 使用持久化浏览器上下文（复用登录状态）
                    try:
                        from modules.utils.sessions.session_manager import SessionManager
                        from modules.utils.sessions.device_fingerprint import DeviceFingerprintManager
                        
                        session_manager = SessionManager()
                        fingerprint_manager = DeviceFingerprintManager()
                        
                        # 获取 profile 路径
                        account_id = self.account_id or account_info.get('account_id', 'default')
                        profile_path = session_manager.get_persistent_profile_path(self.platform, account_id)
                        
                        # 获取指纹配置
                        fingerprint = fingerprint_manager.get_or_create_fingerprint(
                            self.platform, account_id, account_info
                        )
                        
                        logger.info(f"[PERSISTENT] Using persistent context: {profile_path}")
                        print(f"  [PERSISTENT] Using persistent session for {self.platform}/{account_id}")
                        
                        # 构建上下文选项
                        context_options = {
                            'viewport': fingerprint.get('viewport', {'width': 1920, 'height': 1080}),
                            'user_agent': fingerprint.get('user_agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'),
                            'locale': fingerprint.get('locale', 'zh-CN'),
                            'timezone_id': fingerprint.get('timezone', 'Asia/Shanghai'),
                        }
                        
                        # 使用 launch_persistent_context
                        context = await p.chromium.launch_persistent_context(
                            user_data_dir=str(profile_path),
                            headless=self.headless,
                            args=[
                                '--no-sandbox',
                                '--disable-blink-features=AutomationControlled',
                                '--disable-dev-shm-usage',
                            ],
                            slow_mo=50,
                            **context_options
                        )
                        
                        # 持久化上下文可能已有页面
                        if context.pages:
                            page = context.pages[0]
                            # 关闭多余页面
                            for extra_page in context.pages[1:]:
                                await extra_page.close()
                        else:
                            page = await context.new_page()
                            
                    except Exception as e:
                        logger.warning(f"Failed to create persistent context: {e}, falling back to normal context")
                        print(f"  [WARN] Persistent context failed, using normal context")
                        # 降级到普通上下文
                        browser = await p.chromium.launch(
                            headless=self.headless,
                            args=['--disable-blink-features=AutomationControlled']
                        )
                        context = await browser.new_context(
                            viewport={'width': 1920, 'height': 1080}
                        )
                        page = await context.new_page()
                else:
                    # 普通模式：创建新的浏览器上下文
                    browser = await p.chromium.launch(
                        headless=self.headless,
                        args=['--disable-blink-features=AutomationControlled']
                    )
                    context = await browser.new_context(
                        viewport={'width': 1920, 'height': 1080}
                    )
                    page = await context.new_page()
                
                # #region agent log
                with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({'location':'test_component.py:315','message':'_test_with_browser: browser ready','data':{'use_persistent':use_persistent_context},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'G'})+'\n')
                # #endregion
                
                # Phase 12: 判断是否为发现模式组件
                is_discovery_mode = component_type in ['date_picker', 'filters'] and 'open_action' in component
                
                if is_discovery_mode:
                    # 发现模式组件测试
                    discovery_result = await self._test_discovery_component(page, component, result, account_info)
                    if browser:
                        await browser.close()
                    else:
                        await context.close()
                    return discovery_result
                
                steps = component.get('steps', [])
                
                # Phase 12.5: 导出组件自动登录和弹窗清理
                if component_type == 'export' and not self.skip_login:
                    print(f"\n  [LOGIN] Starting auto login for export component...")
                    login_success = await self._execute_auto_login(page, account_info)
                    if not login_success:
                        result.error = "Auto login failed for export component"
                        print(f"  [FAIL] Auto login failed")
                        if browser:
                            await browser.close()
                        else:
                            await context.close()
                        return False
                    print(f"  [OK] Auto login completed")
                    
                    # Phase 12.5: 登录后立即清理弹窗和通知
                    print(f"  [POPUP] Cleaning up popups and notifications...")
                    await self._handle_popups_and_notifications(page)
                    await page.wait_for_timeout(1000)  # 等待页面稳定
                    print(f"  [OK] Popup cleanup completed\n")
            
                # #region agent log
                with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({'location':'test_component.py:320','message':'_test_with_browser: starting step loop','data':{'steps_count':len(steps),'steps_summary':[{'action':s.get('action'),'selector':s.get('selector')} for s in steps]},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'H5,H6'})+'\n')
                # #endregion
                
                for i, step in enumerate(steps):
                    step_id = step.get('id', f'step_{i+1}')
                    action = step.get('action', 'unknown')
                    is_optional = step.get('optional', False)  # [OK] 读取optional标记
                    
                    # [*] v4.7.3: 步骤开始回调（异步）
                    if self.progress_callback:
                        try:
                            if asyncio.iscoroutinefunction(self.progress_callback):
                                await self.progress_callback('step_start', {
                                    'step_index': i + 1,
                                    'step_total': len(steps),
                                    'step_id': step_id,
                                    'action': action,
                                    'optional': is_optional,
                                    'selector': step.get('selector', ''),
                                    'comment': step.get('comment', '')
                                })
                            else:
                                self.progress_callback('step_start', {
                                    'step_index': i + 1,
                                    'step_total': len(steps),
                                    'step_id': step_id,
                                    'action': action,
                                    'optional': is_optional,
                                    'selector': step.get('selector', ''),
                                    'comment': step.get('comment', '')
                                })
                        except Exception as cb_err:
                            logger.warning(f"Progress callback error (step_start): {cb_err}")
                    
                    # #region agent log
                    with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                        f.write(json.dumps({'location':'test_component.py:330','message':f'_test_with_browser: executing step {i+1}','data':{'step_id':step_id,'action':action,'has_selector':step.get('selector') is not None,'is_optional':is_optional},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'I'})+'\n')
                    # #endregion
                    
                    step_result = StepResult(
                        step_id=step_id,
                        action=action,
                        status=TestStatus.RUNNING
                    )
                    
                    start_time = datetime.now()
                    max_retries = step.get('max_retries', 2)  # 默认重试2次
                    last_error = None
                    step_succeeded = False
                    
                    # [*] v4.7.4: 带弹窗处理的重试机制
                    for retry_count in range(max_retries + 1):
                        try:
                            await self._execute_step(page, step, account_info)
                            step_succeeded = True
                            step_result.status = TestStatus.PASSED
                            result.steps_passed += 1
                            if retry_count > 0:
                                print(f"  [OK] Step {i+1}: {action} (retry {retry_count} succeeded)")
                            else:
                                print(f"  [OK] Step {i+1}: {action}")
                            
                            # [*] v4.7.3: 步骤成功回调（异步）
                            if self.progress_callback:
                                try:
                                    if asyncio.iscoroutinefunction(self.progress_callback):
                                        await self.progress_callback('step_success', {
                                            'step_index': i + 1,
                                            'step_id': step_id,
                                            'action': action,
                                            'duration_ms': (datetime.now() - start_time).total_seconds() * 1000,
                                            'retry_count': retry_count
                                        })
                                    else:
                                        self.progress_callback('step_success', {
                                            'step_index': i + 1,
                                            'step_id': step_id,
                                            'action': action,
                                            'duration_ms': (datetime.now() - start_time).total_seconds() * 1000,
                                            'retry_count': retry_count
                                        })
                                except Exception as cb_err:
                                    logger.warning(f"Progress callback error (step_success): {cb_err}")
                            break  # 成功，退出重试循环
                            
                        except Exception as e:
                            last_error = e
                            # 如果不是最后一次重试，尝试处理弹窗后重试
                            if retry_count < max_retries:
                                logger.info(f"[RETRY] Step {i+1} failed ({type(e).__name__}), attempting popup handling before retry {retry_count + 1}...")
                                print(f"  [RETRY] Step {i+1}: {action} - Attempting popup handling...")
                                
                                # [*] v4.7.4: 弹窗处理 - 尝试关闭弹窗/通知
                                popup_handled = await self._handle_popups_and_notifications(page)
                                if popup_handled:
                                    logger.info(f"[POPUP] Popups handled, retrying step {i+1}")
                                    print(f"  [POPUP] Cleared popups, retrying...")
                                    await page.wait_for_timeout(500)  # 等待页面稳定
                                else:
                                    logger.info(f"[POPUP] No popups found, retrying anyway...")
                                    await page.wait_for_timeout(300)
                                continue  # 重试
                    
                    # 如果步骤没有成功，处理失败
                    if not step_succeeded and last_error:
                        e = last_error
                        if isinstance(e, PlaywrightTimeout):
                            # #region agent log
                            with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                                f.write(json.dumps({'location':'test_component.py:357','message':f'_test_with_browser: step {i+1} timeout','data':{'step_id':step_id,'action':action,'is_optional':is_optional,'error':str(e)},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'I'})+'\n')
                            # #endregion
                            
                            # [OK] 检查是否为可选步骤
                            if is_optional:
                                step_result.status = TestStatus.SKIPPED
                                step_result.error = f"Optional step skipped (timeout): {e}"
                                print(f"  [SKIP] Step {i+1}: {action} - Optional, skipped")
                            else:
                                step_result.status = TestStatus.FAILED
                                step_result.error = f"Timeout: {e}"
                                result.steps_failed += 1
                                print(f"  [FAIL] Step {i+1}: {action} - Timeout (after {max_retries} retries)")
                                
                                # Phase 12.4: 打印诊断建议
                                diagnosis = self._diagnose_failure(step, e)
                                if diagnosis:
                                    print(diagnosis)
                                
                                if self.screenshot_on_error:
                                    screenshot_path = await self._save_screenshot(page, component['name'], step_id)
                                    step_result.screenshot = screenshot_path
                        else:
                            # #region agent log
                            with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                                f.write(json.dumps({'location':'test_component.py:371','message':f'_test_with_browser: step {i+1} exception','data':{'step_id':step_id,'action':action,'is_optional':is_optional,'error_type':type(e).__name__,'error':str(e)},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'I'})+'\n')
                            # #endregion
                            
                            # [OK] 检查是否为可选步骤
                            if is_optional:
                                step_result.status = TestStatus.SKIPPED
                                step_result.error = f"Optional step skipped: {str(e)[:100]}"
                                print(f"  [SKIP] Step {i+1}: {action} - Optional, skipped")
                            else:
                                step_result.status = TestStatus.FAILED
                                step_result.error = str(e)
                                result.steps_failed += 1
                                print(f"  [FAIL] Step {i+1}: {action} - {e} (after {max_retries} retries)")
                                
                                # Phase 12.4: 打印诊断建议
                                diagnosis = self._diagnose_failure(step, e)
                                if diagnosis:
                                    print(diagnosis)
                                
                                # [*] v4.7.3: 步骤失败回调（异步）
                                if self.progress_callback:
                                    try:
                                        if asyncio.iscoroutinefunction(self.progress_callback):
                                            await self.progress_callback('step_failed', {
                                                'step_index': i + 1,
                                                'step_id': step_id,
                                                'action': action,
                                                'error': str(e)[:200],
                                                'optional': is_optional
                                            })
                                        else:
                                            self.progress_callback('step_failed', {
                                                'step_index': i + 1,
                                                'step_id': step_id,
                                                'action': action,
                                                'error': str(e)[:200],
                                                'optional': is_optional
                                            })
                                    except Exception as cb_err:
                                        logger.warning(f"Progress callback error (step_failed): {cb_err}")
                                
                                if self.screenshot_on_error:
                                    screenshot_path = await self._save_screenshot(page, component['name'], step_id)
                                    step_result.screenshot = screenshot_path
                    
                    # 记录步骤结果
                    end_time = datetime.now()
                    step_result.duration_ms = (end_time - start_time).total_seconds() * 1000
                    result.step_results.append(step_result)
                    
                    # [OK] 只有非可选步骤失败才停止测试
                    if step_result.status == TestStatus.FAILED and not is_optional:
                        logger.warning(f"Stopping test due to failed required step {i+1}")
                        break
                
                # #region agent log
                with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                    f.write(json.dumps({'location':'test_component.py:396','message':'_test_with_browser: all steps completed, closing browser','data':{'steps_total':len(steps),'steps_passed':result.steps_passed,'steps_failed':result.steps_failed,'current_url':page.url if page else None},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'H5,H7,H8'})+'\n')
                # #endregion
                
                # [OK] 新增：验证success_criteria（如果有）
                success_criteria_passed = True
                if result.steps_failed == 0:  # 只有步骤全部成功才验证
                    success_criteria = component.get('success_criteria', [])
                    if success_criteria:
                        logger.info(f"Verifying {len(success_criteria)} success criteria...")
                        success_criteria_passed = await self._verify_success_criteria(page, success_criteria)
                        
                        if not success_criteria_passed:
                            logger.warning("Success criteria verification failed")
                            # 标记为失败，但不增加steps_failed（这不是步骤失败）
                            result.error = "Success criteria verification failed"
                
                # Phase 12.5: 正确关闭浏览器/上下文
                if browser:
                    await browser.close()
                else:
                    await context.close()
                
                return result.steps_failed == 0 and success_criteria_passed
        
        except Exception as e:
            # #region agent log
            import traceback
            with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({'location':'test_component.py:401','message':'_test_with_browser: EXCEPTION in async with','data':{'error_type':type(e).__name__,'error':str(e),'error_repr':repr(e),'traceback':''.join(traceback.format_tb(e.__traceback__))},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'G'})+'\n')
            # #endregion
            logger.error(f"Browser test failed: {e}", exc_info=True)
            result.error = str(e) if str(e) else type(e).__name__
            return False
    
    async def _verify_success_criteria(self, page, success_criteria: list) -> bool:
        """
        验证成功标准（登录后的检查点）
        
        Args:
            page: Playwright页面对象
            success_criteria: 成功标准列表
            
        Returns:
            bool: 是否所有必需的标准都满足
        """
        import re
        
        for i, criterion in enumerate(success_criteria):
            criterion_type = criterion.get('type')
            value = criterion.get('value', '')
            optional = criterion.get('optional', False)
            timeout = criterion.get('timeout', 10000)
            comment = criterion.get('comment', '')
            
            logger.info(f"  Checking criterion {i+1}: {criterion_type} - {comment}")
            
            try:
                if criterion_type == 'url_contains':
                    # URL包含特定文本
                    current_url = page.url
                    if value not in current_url:
                        if optional:
                            logger.warning(f"    [SKIP] Optional criterion failed: URL does not contain '{value}' (current: {current_url})")
                            continue
                        else:
                            logger.error(f"    [FAIL] URL does not contain '{value}' (current: {current_url})")
                            return False
                    logger.info(f"    [OK] URL contains '{value}'")
                
                elif criterion_type == 'url_not_contains':
                    # URL不包含特定文本（如：已离开登录页）
                    current_url = page.url
                    if value in current_url:
                        if optional:
                            logger.warning(f"    [SKIP] Optional criterion failed: URL still contains '{value}' (current: {current_url})")
                            continue
                        else:
                            logger.error(f"    [FAIL] URL still contains '{value}' (current: {current_url})")
                            return False
                    logger.info(f"    [OK] URL does not contain '{value}' (left {value} page)")
                
                elif criterion_type == 'url_matches_pattern':
                    # URL匹配正则表达式
                    current_url = page.url
                    if not re.search(value, current_url):
                        if optional:
                            logger.warning(f"    [SKIP] Optional criterion failed: URL does not match pattern '{value}' (current: {current_url})")
                            continue
                        else:
                            logger.error(f"    [FAIL] URL does not match pattern '{value}' (current: {current_url})")
                            return False
                    logger.info(f"    [OK] URL matches pattern '{value}'")
                
                elif criterion_type == 'element_exists':
                    # 元素存在
                    selector = criterion.get('selector', value)
                    try:
                        await page.wait_for_selector(selector, timeout=timeout, state='visible')
                        logger.info(f"    [OK] Element exists: {selector}")
                    except Exception as e:
                        if optional:
                            logger.warning(f"    [SKIP] Optional criterion failed: Element not found: {selector}")
                            continue
                        else:
                            logger.error(f"    [FAIL] Element not found: {selector}")
                            return False
                
                elif criterion_type == 'element_not_exists':
                    # 元素不存在（如：无错误提示）
                    selector = criterion.get('selector', value)
                    try:
                        await page.wait_for_selector(selector, timeout=timeout, state='visible')
                        # 如果找到了元素，说明条件不满足
                        if optional:
                            logger.warning(f"    [SKIP] Optional criterion failed: Element should not exist but found: {selector}")
                            continue
                        else:
                            logger.error(f"    [FAIL] Element should not exist but found: {selector}")
                            return False
                    except:
                        # 超时未找到元素，说明条件满足
                        logger.info(f"    [OK] Element does not exist: {selector}")
                
                elif criterion_type == 'page_contains_text':
                    # 页面包含文本
                    try:
                        await page.wait_for_selector(f"text={value}", timeout=timeout)
                        logger.info(f"    [OK] Page contains text: '{value}'")
                    except Exception as e:
                        if optional:
                            logger.warning(f"    [SKIP] Optional criterion failed: Page does not contain text: '{value}'")
                            continue
                        else:
                            logger.error(f"    [FAIL] Page does not contain text: '{value}'")
                            return False
                
                else:
                    logger.warning(f"    [WARN] Unknown criterion type: {criterion_type}")
            
            except Exception as e:
                if optional:
                    logger.warning(f"    [SKIP] Optional criterion error: {e}")
                    continue
                else:
                    logger.error(f"    [FAIL] Criterion check error: {e}")
                    return False
        
        logger.info(f"[OK] All required success criteria passed")
        return True
    
    def _validate_discovery_component(self, component: Dict[str, Any]) -> bool:
        """
        验证发现模式组件结构（Phase 12）
        
        Args:
            component: 组件配置
            
        Returns:
            bool: 是否有效
        """
        # 验证 open_action
        open_action = component.get('open_action')
        if not open_action or not isinstance(open_action, dict):
            logger.error("Discovery component missing 'open_action' or not a dictionary")
            return False
        
        if 'selectors' not in open_action and 'action' not in open_action:
            logger.error("Discovery component 'open_action' must have 'selectors' or 'action'")
            return False
        
        # 验证 available_options
        available_options = component.get('available_options', [])
        if not available_options or not isinstance(available_options, list):
            logger.error("Discovery component missing 'available_options' or not a list")
            return False
        
        if len(available_options) == 0:
            logger.error("Discovery component must have at least one option")
            return False
        
        for i, option in enumerate(available_options):
            if 'key' not in option:
                logger.error(f"Option {i} missing 'key' field")
                return False
            if 'text' not in option:
                logger.error(f"Option {i} missing 'text' field")
                return False
        
        # 验证 test_config（推荐但可选）
        test_config = component.get('test_config', {})
        if not test_config:
            logger.warning("Discovery component missing 'test_config'. Testing may require manual navigation.")
        else:
            test_url = test_config.get('test_url', '')
            test_data_domain = test_config.get('test_data_domain', '')
            if not test_url and not test_data_domain:
                logger.warning("test_config has neither 'test_url' nor 'test_data_domain'")
        
        logger.info(f"[OK] Discovery component structure valid: {len(available_options)} options")
        return True
    
    async def _test_discovery_component(
        self, 
        page, 
        component: Dict[str, Any], 
        result: ComponentTestResult,
        account_info: Dict[str, Any]
    ) -> bool:
        """
        测试发现模式组件（Phase 12）
        
        流程：
        1. 导航到测试页面（使用 test_config）
        2. 执行 open_action（打开选择器）
        3. 循环测试每个 available_option
        
        Args:
            page: Playwright页面对象
            component: 组件配置
            result: 测试结果对象
            account_info: 账号信息
            
        Returns:
            bool: 是否成功
        """
        from playwright.async_api import TimeoutError as PlaywrightTimeout
        
        component_type = component.get('type', 'unknown')
        open_action = component.get('open_action', {})
        available_options = component.get('available_options', [])
        test_config = component.get('test_config', {})
        
        result.steps_total = len(available_options) + 1  # open_action + options
        
        print(f"\n[TEST] Discovery Mode: {self.platform}/{component.get('name')} ({len(available_options)} options)")
        
        try:
            # Phase 12.1: 自动登录（如果未跳过）
            if not self.skip_login:
                print(f"\n  [LOGIN] Starting auto login...")
                login_success = await self._execute_auto_login(page, account_info)
                if not login_success:
                    result.error = "Auto login failed"
                    print(f"  [FAIL] Auto login failed")
                    return False
                print(f"  [OK] Auto login completed")
                
                # Phase 12.5: 登录后立即清理弹窗和通知
                print(f"  [POPUP] Cleaning up popups and notifications...")
                await self._handle_popups_and_notifications(page)
                await page.wait_for_timeout(1000)  # 等待页面稳定
                print(f"  [OK] Popup cleanup completed\n")
            
            # 步骤1: 导航到测试页面
            nav_success = await self._navigate_to_test_page(page, test_config, account_info)
            if not nav_success:
                result.error = "Failed to navigate to test page"
                return False
            
            print(f"  [OK] Navigated to test page")
            
            # 等待页面稳定
            await page.wait_for_timeout(2000)
            
            # 步骤2: 测试 open_action
            open_action_result = StepResult(
                step_id='open_action',
                action='click',
                status=TestStatus.RUNNING
            )
            start_time = datetime.now()
            
            try:
                await self._execute_open_action(page, open_action)
                open_action_result.status = TestStatus.PASSED
                result.steps_passed += 1
                print(f"  [OK] Open action executed successfully")
                
                # 等待选择器面板出现
                await page.wait_for_timeout(500)
                
            except Exception as e:
                open_action_result.status = TestStatus.FAILED
                open_action_result.error = str(e)
                result.steps_failed += 1
                result.error = f"Open action failed: {e}"
                print(f"  [FAIL] Open action failed: {e}")
                
                if self.screenshot_on_error:
                    screenshot_path = await self._save_screenshot(page, component['name'], 'open_action')
                    open_action_result.screenshot = screenshot_path
                
                return False
            finally:
                open_action_result.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                result.step_results.append(open_action_result)
            
            # 步骤3: 测试每个选项
            options_tested = 0
            options_passed = 0
            
            for i, option in enumerate(available_options):
                option_key = option.get('key', f'option_{i}')
                option_text = option.get('text', option_key)
                
                option_result = StepResult(
                    step_id=f'option_{option_key}',
                    action='select_option',
                    status=TestStatus.RUNNING
                )
                option_start = datetime.now()
                
                try:
                    # 如果不是第一个选项，需要重新打开选择器
                    if i > 0:
                        await self._execute_open_action(page, open_action)
                        await page.wait_for_timeout(500)
                    
                    # 点击选项
                    await self._click_option(page, option)
                    
                    options_tested += 1
                    options_passed += 1
                    option_result.status = TestStatus.PASSED
                    result.steps_passed += 1
                    print(f"  [OK] Option '{option_key}' ({option_text}) - success")
                    
                    # 等待选择器关闭
                    await page.wait_for_timeout(800)
                    
                except Exception as e:
                    options_tested += 1
                    option_result.status = TestStatus.FAILED
                    option_result.error = str(e)
                    result.steps_failed += 1
                    print(f"  [FAIL] Option '{option_key}' ({option_text}) - {e}")
                    
                    if self.screenshot_on_error:
                        screenshot_path = await self._save_screenshot(page, component['name'], f'option_{option_key}')
                        option_result.screenshot = screenshot_path
                    
                finally:
                    option_result.duration_ms = (datetime.now() - option_start).total_seconds() * 1000
                    result.step_results.append(option_result)
            
            # 汇总结果
            print(f"\n  [SUMMARY] {options_passed}/{options_tested} options passed")
            
            return result.steps_failed == 0
            
        except Exception as e:
            logger.error(f"Discovery component test failed: {e}", exc_info=True)
            result.error = str(e)
            return False
    
    async def _navigate_to_test_page(
        self, 
        page, 
        test_config: Dict[str, Any],
        account_info: Dict[str, Any]
    ) -> bool:
        """
        导航到测试页面（Phase 12）
        
        Args:
            page: Playwright页面对象
            test_config: 测试配置
            account_info: 账号信息
            
        Returns:
            bool: 是否成功
        """
        try:
            test_url = test_config.get('test_url', '')
            test_data_domain = test_config.get('test_data_domain', '')
            
            if test_url:
                # 使用 test_url 直接导航
                if account_info:
                    test_url = self._replace_variables(test_url, account_info)
                
                logger.info(f"[NAV] Navigating to test URL: {test_url}")
                await page.goto(test_url, wait_until='domcontentloaded', timeout=30000)
                
                # 等待页面加载
                try:
                    await page.wait_for_load_state('networkidle', timeout=10000)
                except:
                    pass
                
                return True
                
            elif test_data_domain:
                # 使用 navigation 组件导航
                logger.info(f"[NAV] Using navigation component for data_domain: {test_data_domain}")
                
                # 尝试加载 navigation 组件
                try:
                    nav_component = self.component_loader.load(f"{self.platform}/navigation")
                    nav_steps = nav_component.get('steps', [])
                    
                    # 替换 data_domain 参数
                    params = {'data_domain': test_data_domain}
                    if account_info:
                        params.update({'account': account_info})
                    
                    # 执行导航步骤
                    for step in nav_steps:
                        await self._execute_step(page, step, account_info)
                    
                    return True
                    
                except FileNotFoundError:
                    logger.warning(f"Navigation component not found for {self.platform}, using default URL")
                    # 降级：使用默认URL
                    if account_info and 'login_url' in account_info:
                        default_url = f"{account_info['login_url']}/portal/sale/order"
                        logger.info(f"[NAV] Falling back to default URL: {default_url}")
                        await page.goto(default_url, wait_until='domcontentloaded', timeout=30000)
                        return True
                    return False
            else:
                # 没有配置，使用默认URL
                logger.warning("No test_config provided, using default URL")
                if account_info and 'login_url' in account_info:
                    default_url = f"{account_info['login_url']}/portal/sale/order"
                    logger.info(f"[NAV] Using default URL: {default_url}")
                    await page.goto(default_url, wait_until='domcontentloaded', timeout=30000)
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Navigation failed: {e}")
            return False
    
    async def _execute_open_action(self, page, open_action: Dict[str, Any]) -> None:
        """
        执行打开动作（Phase 12）
        
        Args:
            page: Playwright页面对象
            open_action: 打开动作配置
        """
        selectors = open_action.get('selectors', [])
        
        for selector_info in selectors:
            selector_type = selector_info.get('type', 'css')
            selector_value = selector_info.get('value', '')
            
            try:
                if selector_type == 'text':
                    locator = page.get_by_text(selector_value)
                elif selector_type == 'role':
                    # 解析 role 选择器
                    if '[name=' in selector_value:
                        import re
                        match = re.match(r'(\w+)\[name=([^\]]+)\]', selector_value)
                        if match:
                            role, name = match.groups()
                            locator = page.get_by_role(role, name=name)
                        else:
                            locator = page.locator(f'[role="{selector_value}"]')
                    else:
                        locator = page.locator(f'[role="{selector_value}"]')
                else:
                    # css 或其他
                    locator = page.locator(selector_value)
                
                count = await locator.count()
                if count > 0:
                    await locator.first.wait_for(state='visible', timeout=5000)
                    await locator.first.click(timeout=5000)
                    logger.info(f"[OK] Open action clicked: {selector_type}={selector_value}")
                    return
                    
            except Exception as e:
                logger.debug(f"Selector failed: {selector_type}={selector_value}, error: {e}")
                continue
        
        # 如果所有选择器都失败
        raise Exception(f"Failed to execute open_action: no valid selector found")
    
    async def _click_option(self, page, option: Dict[str, Any]) -> None:
        """
        点击选项（Phase 12）
        
        Args:
            page: Playwright页面对象
            option: 选项配置
        """
        selectors = option.get('selectors', [])
        option_text = option.get('text', '')
        
        # 优先尝试配置的选择器
        for selector_info in selectors:
            selector_type = selector_info.get('type', 'css')
            selector_value = selector_info.get('value', '')
            
            try:
                if selector_type == 'text':
                    locator = page.get_by_text(selector_value, exact=True)
                elif selector_type == 'role':
                    locator = page.get_by_role('option', name=selector_value)
                else:
                    locator = page.locator(selector_value)
                
                count = await locator.count()
                if count > 0:
                    await locator.first.wait_for(state='visible', timeout=5000)
                    await locator.first.click(timeout=5000)
                    logger.info(f"[OK] Option clicked: {selector_type}={selector_value}")
                    return
                    
            except Exception as e:
                logger.debug(f"Option selector failed: {selector_type}={selector_value}, error: {e}")
                continue
        
        # 降级：使用文本定位
        if option_text:
            try:
                locator = page.get_by_text(option_text, exact=True)
                count = await locator.count()
                if count > 0:
                    await locator.first.click(timeout=5000)
                    logger.info(f"[OK] Option clicked by text: {option_text}")
                    return
            except Exception as e:
                logger.debug(f"Text fallback failed: {option_text}, error: {e}")
        
        raise Exception(f"Failed to click option '{option.get('key')}': no valid selector found")
    
    async def _execute_auto_login(self, page, account_info: Dict[str, Any]) -> bool:
        """
        执行自动登录（Phase 12.1 修复）
        
        Args:
            page: Playwright页面对象
            account_info: 账号信息
            
        Returns:
            bool: 是否成功
        """
        try:
            # 加载登录组件
            login_component = self.component_loader.load(f"{self.platform}/login")
            login_steps = login_component.get('steps', [])
            
            logger.info(f"[LOGIN] Executing login component ({len(login_steps)} steps)")
            
            # 执行登录步骤
            for i, step in enumerate(login_steps):
                try:
                    await self._execute_step(page, step, account_info)
                    print(f"    [OK] Login step {i+1}: {step.get('action')}")
                except Exception as e:
                    # 检查是否可选步骤
                    if step.get('optional', False):
                        print(f"    [SKIP] Login step {i+1}: {step.get('action')} (optional)")
                        continue
                    else:
                        logger.error(f"Login step {i+1} failed: {e}")
                        print(f"    [FAIL] Login step {i+1}: {step.get('action')} - {e}")
                        return False
            
            # 等待登录完成
            await page.wait_for_timeout(2000)
            
            return True
            
        except FileNotFoundError:
            logger.error(f"Login component not found for {self.platform}")
            print(f"    [FAIL] Login component not found: {self.platform}/login")
            return False
        except Exception as e:
            logger.error(f"Auto login failed: {e}")
            print(f"    [FAIL] Auto login exception: {e}")
            return False
    
    async def _execute_step(self, page, step: Dict[str, Any], account_info: Dict[str, Any]):
        """
        执行单个步骤（使用Playwright官方API + 完整等待机制）
        
        Args:
            page: Playwright页面对象
            step: 步骤配置
            account_info: 账号信息
        """
        action = step['action']
        selector = step.get('selector')
        value = step.get('value', '')
        timeout = step.get('timeout', 30000)
        
        # 替换变量
        if account_info and value:
            value = self._replace_variables(value, account_info)
        
        if action == 'navigate' or action == 'goto':
            url = step.get('url', '')
            if account_info:
                url = self._replace_variables(url, account_info)
            
            # #region agent log
            import json
            with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({'location':'test_component.py:_execute_step:navigate','message':'Starting navigation','data':{'url':url,'action':action},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'H8'})+'\n')
            # #endregion
            
            # 修复1：完整的页面加载等待
            await page.goto(url, wait_until='domcontentloaded', timeout=timeout)
            
            # 等待网络空闲（确保所有资源加载完成）
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
            except:
                pass  # 如果超时也继续，某些页面可能一直有网络请求
            
            # 额外等待1秒确保JavaScript渲染完成
            await page.wait_for_timeout(1000)
            
            # #region agent log
            with open(r'f:\Vscode\python_programme\AI_code\xihong_erp\.cursor\debug.log', 'a', encoding='utf-8') as f:
                f.write(json.dumps({'location':'test_component.py:_execute_step:navigate_done','message':'Navigation completed','data':{'final_url':page.url},'timestamp':datetime.now().timestamp()*1000,'sessionId':'debug-session','hypothesisId':'H8'})+'\n')
            # #endregion
            
            logger.info(f"[OK] Page loaded and ready: {url}")
        
        elif action == 'click':
            # 修复2：使用Playwright官方API
            locator = await self._get_playwright_locator(page, selector)
            
            # 等待元素可见且可交互
            await locator.wait_for(state='visible', timeout=timeout)
            await locator.scroll_into_view_if_needed(timeout=timeout)
            
            await locator.click(timeout=timeout)
        
        elif action == 'fill':
            # 修复2：使用Playwright官方API
            locator = await self._get_playwright_locator(page, selector)
            
            # 等待元素可见且可交互
            await locator.wait_for(state='visible', timeout=timeout)
            await locator.scroll_into_view_if_needed(timeout=timeout)
            
            # 先点击聚焦，再清空，再填充
            await locator.click(timeout=timeout)
            await locator.fill('', timeout=timeout)  # 清空
            await locator.fill(value, timeout=timeout)
        
        elif action == 'wait':
            # [OK] v4.7.0修复：与executor_v2.py对齐，使用Playwright官方API
            # 支持三种等待类型：
            # 1. type='timeout': 固定时间延迟（毫秒）
            # 2. type='selector': 等待元素出现
            # 3. type='navigation': 等待页面加载完成
            wait_type = step.get('type', 'timeout')
            
            if wait_type == 'timeout':
                duration = step.get('duration', 1000)
                logger.info(f"[WAIT] 等待 {duration}ms（固定延迟）")
                await page.wait_for_timeout(duration)
            
            elif wait_type == 'selector':
                selector = step.get('selector')
                if not selector:
                    raise ValueError("wait步骤type='selector'时必须提供selector字段")
                
                state = step.get('state', 'visible')
                logger.info(f"[WAIT] 等待元素出现: {selector} (state={state})")
                await page.wait_for_selector(selector, state=state, timeout=timeout)
            
            elif wait_type == 'navigation':
                wait_until = step.get('wait_until', 'load')
                logger.info(f"[WAIT] 等待页面加载完成 (wait_until={wait_until})")
                await page.wait_for_load_state(wait_until, timeout=timeout)
            
            else:
                raise ValueError(f"wait步骤不支持的type: {wait_type}，支持: timeout/selector/navigation")
        
        elif action == 'wait_for_navigation':
            await page.wait_for_load_state('domcontentloaded', timeout=timeout)
        
        elif action == 'screenshot':
            await page.screenshot(path=step.get('path', 'screenshot.png'))
        
        else:
            logger.warning(f"Unknown action: {action}")
    
    async def _get_playwright_locator(self, page, selector: str):
        """
        使用Playwright官方API定位元素（推荐方式）
        
        优先级：
        1. get_by_role() - 官方推荐，最稳定
        2. get_by_label() - 表单元素
        3. get_by_text() - 文本定位
        4. locator() - 通用定位
        
        Args:
            page: Playwright页面对象
            selector: 选择器字符串
            
        Returns:
            Locator对象
            
        Note:
            [*] v4.7.3修复：使用 await locator.count() 正确检查元素存在
        """
        import re
        
        # 策略1: Playwright官方 get_by_role API
        # 格式: role=textbox[name=手机号/子账号/邮箱]
        if 'role=' in selector and '[name=' in selector:
            match = re.match(r'role=(\w+)\[name=([^\]]+)\]', selector)
            if match:
                role, name = match.groups()
                try:
                    logger.debug(f"[Playwright Official] get_by_role('{role}', name='{name}')")
                    locator = page.get_by_role(role, name=name)
                    
                    # [*] 修复：异步API需要await
                    count = await locator.count()
                    if count > 0:
                        logger.info(f"[OK] Official API found element: get_by_role('{role}', name='{name}')")
                        return locator
                    else:
                        logger.warning(f"[WARN] Element not found with get_by_role('{role}', name='{name}')")
                except Exception as e:
                    logger.warning(f"[WARN] get_by_role failed: {str(e)[:100]}")
        
        # 策略2: Playwright get_by_label API
        # 格式: label=密码
        if selector.startswith('label='):
            label_text = selector[6:]
            try:
                logger.debug(f"[Playwright Official] get_by_label('{label_text}')")
                locator = page.get_by_label(label_text)
                count = await locator.count()
                if count > 0:
                    logger.info(f"[OK] Official API found element: get_by_label('{label_text}')")
                    return locator
            except Exception as e:
                logger.warning(f"[WARN] get_by_label failed: {str(e)[:100]}")
        
        # 策略3: Playwright get_by_text API
        # 格式: text=立即登录
        if selector.startswith('text='):
            text = selector[5:]
            try:
                logger.debug(f"[Playwright Official] get_by_text('{text}')")
                locator = page.get_by_text(text)
                count = await locator.count()
                if count > 0:
                    logger.info(f"[OK] Official API found element: get_by_text('{text}')")
                    return locator
            except Exception as e:
                logger.warning(f"[WARN] get_by_text failed: {str(e)[:100]}")
        
        # 策略4: 通用 locator() API（降级方案）
        # 支持CSS selector、XPath等
        try:
            logger.debug(f"[Playwright] locator('{selector}')")
            locator = page.locator(selector).first
            count = await locator.count()
            if count > 0:
                logger.info(f"[OK] Generic locator found element: {selector}")
                return locator
        except Exception as e:
            logger.warning(f"[WARN] Generic locator failed: {str(e)[:100]}")
        
        # 策略5: 最后尝试 - CSS selector with name attribute
        if 'name=' in selector:
            name_match = re.search(r'\[name=([^\]]+)\]', selector)
            if name_match:
                name = name_match.group(1)
                css_selector = f'[name="{name}"]'
                try:
                    logger.debug(f"[CSS Fallback] locator('{css_selector}')")
                    locator = page.locator(css_selector).first
                    count = await locator.count()
                    if count > 0:
                        logger.info(f"[OK] CSS fallback found element: {css_selector}")
                        return locator
                except Exception as e:
                    logger.warning(f"[WARN] CSS fallback failed: {str(e)[:100]}")
        
        # 所有策略都失败
        error_msg = (
            f"[ERROR] Cannot locate element with selector: {selector}\n"
            f"[TIP] The element might not exist yet, or the selector format is incorrect.\n"
            f"[TIP] Supported formats:\n"
            f"  - role=button[name=\u767b\u5f55]\n"
            f"  - label=\u5bc6\u7801\n"
            f"  - text=\u7acb\u5373\u767b\u5f55\n"
            f"  - CSS selector: .class-name\n"
            f"  - XPath: xpath=//button[@name='login']"
        )
        raise Exception(error_msg)
    
    
    async def _handle_popups_and_notifications(self, page, max_attempts: int = 3) -> bool:
        """
        处理弹窗和通知（v4.7.5增强）
        
        Phase 12.5增强：
        1. 多轮清理弹窗（最多3轮）
        2. 增加更多弹窗选择器（新用户引导等）
        3. 打印清理日志
        
        尝试关闭常见的弹窗、通知、遮罩层：
        1. 按 ESC 键
        2. 点击常见关闭按钮
        3. 点击遮罩层外部
        
        Args:
            page: Playwright页面对象
            max_attempts: 最大清理轮数
            
        Returns:
            bool: 是否成功处理了弹窗
        """
        total_handled = 0
        
        # Phase 12.5: 多轮清理
        for attempt in range(max_attempts):
            handled_this_round = False
            
            try:
                # 策略1: 按 ESC 键关闭弹窗
                await page.keyboard.press('Escape')
                await page.wait_for_timeout(200)
                
                # 策略2: 尝试点击常见的关闭按钮
                close_selectors = [
                    # 通用关闭按钮
                    '[class*="close"]',
                    '[class*="dismiss"]',
                    '[aria-label*="关闭"]',
                    '[aria-label*="Close"]',
                    'button:has-text("关闭")',
                    'button:has-text("取消")',
                    'button:has-text("我知道了")',
                    'button:has-text("确定")',
                    'button:has-text("OK")',
                    'button:has-text("知道了")',
                    'button:has-text("跳过")',
                    'button:has-text("下次再说")',
                    'button:has-text("不再提示")',
                    # 新用户引导弹窗
                    '[class*="guide"] [class*="close"]',
                    '[class*="tour"] [class*="close"]',
                    '[class*="intro"] [class*="close"]',
                    '[class*="welcome"] [class*="close"]',
                    # Ant Design / Element UI 关闭按钮
                    '.ant-modal-close',
                    '.el-dialog__close',
                    '.el-message-box__close',
                    '.el-notification__closeBtn',
                    # Toast 通知
                    '.ant-notification-close-x',
                    '.el-message__closeBtn',
                    '.ant-message-notice-close',
                    # 遮罩层点击关闭（谨慎使用）
                    # '.ant-modal-mask',
                    # '.el-overlay',
                    # 妙手ERP特定弹窗
                    '[class*="modal"] [class*="btn-close"]',
                    '[class*="dialog"] [class*="btn-close"]',
                    '.close-btn',
                    '.icon-close',
                    'i[class*="close"]',
                    'span[class*="close"]',
                ]
                
                for selector in close_selectors:
                    try:
                        locator = page.locator(selector).first
                        if await locator.count() > 0:
                            is_visible = await locator.is_visible()
                            if is_visible:
                                await locator.click(timeout=1000)
                                await page.wait_for_timeout(300)
                                handled_this_round = True
                                total_handled += 1
                                logger.debug(f"[POPUP] Closed popup with selector: {selector}")
                                break  # 一次只关闭一个，然后重新检测
                    except Exception:
                        continue
                
                # 如果这轮没有处理任何弹窗，退出循环
                if not handled_this_round:
                    break
                    
            except Exception as e:
                logger.debug(f"[POPUP] Error during popup handling attempt {attempt+1}: {e}")
                break
        
        if total_handled > 0:
            logger.info(f"[POPUP] Cleared {total_handled} popup(s) in {attempt+1} attempt(s)")
            print(f"    [POPUP] Cleared {total_handled} popup(s)")
        
        return total_handled > 0
    
    
    def _replace_variables(self, text: str, account_info: Dict[str, Any]) -> str:
        """替换变量"""
        if not text or not account_info:
            return text
        
        # 替换 {{account.xxx}} 格式的变量
        import re
        
        def replace_match(match):
            path = match.group(1)
            if path.startswith('account.'):
                key = path[8:]
                return str(account_info.get(key, match.group(0)))
            return match.group(0)
        
        return re.sub(r'\{\{(\w+(?:\.\w+)*)\}\}', replace_match, text)
    
    async def _save_screenshot(self, page, component_name: str, step_id: str) -> str:
        """保存截图（异步版本）"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{component_name}_{step_id}_{timestamp}.png"
            filepath = self.output_dir / 'screenshots' / filename
            filepath.parent.mkdir(parents=True, exist_ok=True)
            
            # 保存截图（异步API）
            await page.screenshot(path=str(filepath))
            
            return str(filepath)
        except Exception as e:
            logger.error(f"Failed to save screenshot: {e}")
            return None
    
    def _diagnose_failure(self, step: Dict[str, Any], error: Exception) -> str:
        """
        诊断步骤失败原因并给出建议（Phase 12.4）
        
        Args:
            step: 失败的步骤
            error: 异常对象
            
        Returns:
            str: 诊断建议
        """
        error_msg = str(error).lower()
        action = step.get('action', '')
        selector = step.get('selector', '')
        
        suggestions = []
        
        # 选择器相关错误
        if 'selector' in error_msg or 'locator' in error_msg or 'resolved to' in error_msg:
            suggestions.append("[DIAG] Selector issue detected:")
            suggestions.append("  1. Use Playwright Inspector to re-locate the element")
            suggestions.append("  2. Try role-based selector: role=button[name='...']")
            suggestions.append("  3. Check if element is inside an iframe")
        
        # 超时错误
        if 'timeout' in error_msg or 'timeouterror' in error_msg:
            suggestions.append("[DIAG] Timeout detected:")
            suggestions.append("  1. Increase timeout value in step config")
            suggestions.append("  2. Add wait step before this action")
            suggestions.append("  3. Check network connectivity")
        
        # 元素不可见
        if 'not visible' in error_msg or 'hidden' in error_msg or 'outside' in error_msg:
            suggestions.append("[DIAG] Element visibility issue:")
            suggestions.append("  1. Element may need scrolling - try scroll_into_view")
            suggestions.append("  2. Wait for animation to complete")
            suggestions.append("  3. Check if element is blocked by another element")
        
        # 点击相关错误
        if action == 'click' and ('click' in error_msg or 'intercept' in error_msg):
            suggestions.append("[DIAG] Click failed:")
            suggestions.append("  1. Element may be non-clickable")
            suggestions.append("  2. Try adding force: true to step")
            suggestions.append("  3. Wait for element to become interactive")
        
        # 填写相关错误
        if action == 'fill' and ('fill' in error_msg or 'editable' in error_msg):
            suggestions.append("[DIAG] Fill failed:")
            suggestions.append("  1. Element may be readonly or disabled")
            suggestions.append("  2. Try clicking the element first")
            suggestions.append("  3. Check if element is an input/textarea")
        
        # 导航相关错误
        if 'navigation' in error_msg or 'goto' in error_msg:
            suggestions.append("[DIAG] Navigation issue:")
            suggestions.append("  1. Check URL format and protocol")
            suggestions.append("  2. Increase navigation timeout")
            suggestions.append("  3. Check for redirects or authentication")
        
        if not suggestions:
            suggestions.append("[DIAG] Unknown error - check step configuration")
        
        return "\n".join(suggestions)
    
    async def test_all_components(self) -> List[ComponentTestResult]:
        """
        测试所有组件
        
        Returns:
            List[ComponentTestResult]: 所有测试结果
        """
        components = self.list_components()
        
        print(f"\n{'='*60}")
        print(f" Testing all {self.platform} components ({len(components)} total)")
        print('='*60)
        
        self.results = []
        
        for component_name in components:
            result = await self.test_component(component_name)
            self.results.append(result)
        
        return self.results
    
    def generate_report(self, format: str = 'json') -> str:
        """
        生成测试报告
        
        Args:
            format: 报告格式（json/html）
            
        Returns:
            str: 报告文件路径
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        if format == 'json':
            report_path = self.output_dir / f"test_report_{self.platform}_{timestamp}.json"
            
            report = {
                'platform': self.platform,
                'timestamp': timestamp,
                'summary': {
                    'total': len(self.results),
                    'passed': sum(1 for r in self.results if r.status == TestStatus.PASSED),
                    'failed': sum(1 for r in self.results if r.status == TestStatus.FAILED),
                    'skipped': sum(1 for r in self.results if r.status == TestStatus.SKIPPED),
                },
                'results': [
                    {
                        'component': r.component_name,
                        'status': r.status.value,
                        'duration_ms': r.duration_ms,
                        'steps_total': r.steps_total,
                        'steps_passed': r.steps_passed,
                        'steps_failed': r.steps_failed,
                        'error': r.error,
                    }
                    for r in self.results
                ]
            }
            
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
        
        elif format == 'html':
            report_path = self.output_dir / f"test_report_{self.platform}_{timestamp}.html"
            
            html = self._generate_html_report()
            
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(html)
        
        else:
            raise ValueError(f"Unknown format: {format}")
        
        print(f"\n[OK] Report saved: {report_path}")
        return str(report_path)
    
    def _generate_html_report(self) -> str:
        """生成HTML报告"""
        passed = sum(1 for r in self.results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in self.results if r.status == TestStatus.FAILED)
        total = len(self.results)
        
        rows = ""
        for r in self.results:
            status_class = {
                TestStatus.PASSED: 'success',
                TestStatus.FAILED: 'danger',
                TestStatus.SKIPPED: 'warning',
            }.get(r.status, 'secondary')
            
            rows += f"""
            <tr>
                <td>{r.component_name}</td>
                <td><span class="badge bg-{status_class}">{r.status.value}</span></td>
                <td>{r.duration_ms:.0f}ms</td>
                <td>{r.steps_passed}/{r.steps_total}</td>
                <td>{r.error or '-'}</td>
            </tr>
            """
        
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Component Test Report - {self.platform}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="p-4">
    <div class="container">
        <h1>Component Test Report</h1>
        <p class="lead">Platform: {self.platform}</p>
        
        <div class="row mb-4">
            <div class="col-md-4">
                <div class="card bg-light">
                    <div class="card-body text-center">
                        <h2>{total}</h2>
                        <p>Total Tests</p>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card bg-success text-white">
                    <div class="card-body text-center">
                        <h2>{passed}</h2>
                        <p>Passed</p>
                    </div>
                </div>
            </div>
            <div class="col-md-4">
                <div class="card bg-danger text-white">
                    <div class="card-body text-center">
                        <h2>{failed}</h2>
                        <p>Failed</p>
                    </div>
                </div>
            </div>
        </div>
        
        <table class="table table-striped">
            <thead>
                <tr>
                    <th>Component</th>
                    <th>Status</th>
                    <th>Duration</th>
                    <th>Steps</th>
                    <th>Error</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
        
        <p class="text-muted">Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
</body>
</html>
        """


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description='组件测试工具 - 测试YAML组件配置',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 测试单个组件
  python tools/test_component.py --platform shopee --component login --account MyStore_SG

  # 测试所有组件
  python tools/test_component.py --all --platform shopee

  # 无头模式测试
  python tools/test_component.py --platform shopee --component login --headless
        """
    )
    
    parser.add_argument(
        '--platform', '-p',
        choices=['shopee', 'tiktok', 'miaoshou'],
        required=True,
        help='目标平台'
    )
    
    parser.add_argument(
        '--component', '-c',
        help='组件名称'
    )
    
    parser.add_argument(
        '--all',
        action='store_true',
        help='测试所有组件'
    )
    
    parser.add_argument(
        '--account', '-a',
        help='账号ID'
    )
    
    parser.add_argument(
        '--skip-login',
        action='store_true',
        help='跳过登录'
    )
    
    parser.add_argument(
        '--headless',
        action='store_true',
        help='无头模式'
    )
    
    parser.add_argument(
        '--report',
        choices=['json', 'html'],
        default='json',
        help='报告格式'
    )
    
    parser.add_argument(
        '--output-dir', '-o',
        help='输出目录'
    )
    
    parser.add_argument(
        '--list',
        action='store_true',
        help='列出所有组件'
    )
    
    return parser


async def main():
    """主函数"""
    parser = create_parser()
    args = parser.parse_args()
    
    tester = ComponentTester(
        platform=args.platform,
        account_id=args.account,
        skip_login=args.skip_login,
        headless=args.headless,
        output_dir=args.output_dir
    )
    
    # 列出组件
    if args.list:
        components = tester.list_components()
        print(f"\n{args.platform} components:")
        for c in components:
            print(f"  - {c}")
        return
    
    # 测试所有组件
    if args.all:
        results = await tester.test_all_components()
    
    # 测试单个组件
    elif args.component:
        result = await tester.test_component(args.component)
        tester.results = [result]
    
    else:
        parser.print_help()
        return
    
    # 打印摘要
    print("\n" + "="*60)
    print(" Test Summary")
    print("="*60)
    
    passed = sum(1 for r in tester.results if r.status == TestStatus.PASSED)
    failed = sum(1 for r in tester.results if r.status == TestStatus.FAILED)
    
    print(f"\nTotal: {len(tester.results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    # 生成报告
    tester.generate_report(format=args.report)


if __name__ == '__main__':
    asyncio.run(main())

