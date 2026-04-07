"""
CollectionExecutorV2 单元测试
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
import tempfile

from backend.services.component_runtime_resolver import RuntimeComponentManifest
from modules.apps.collection_center.executor_v2 import (
    CollectionExecutorV2,
    CollectionResult,
    TaskContext,
    StepExecutionError,
    VerificationRequiredError,
    TaskCancelledError,
)
from modules.apps.collection_center.component_loader import ComponentLoader
from modules.apps.collection_center.popup_handler import UniversalPopupHandler
from modules.apps.collection_center.python_component_adapter import AdapterResult

# 配置pytest-asyncio
pytestmark = pytest.mark.anyio


@pytest.fixture
def mock_component_loader():
    """创建模拟的组件加载器"""
    loader = Mock(spec=ComponentLoader)
    
    # 模拟登录组件
    loader.load.return_value = {
        'name': 'test_login',
        'platform': 'shopee',
        'type': 'login',
        'popup_handling': {
            'enabled': True,
            'check_before_steps': True,
            'check_after_steps': True,
        },
        'steps': [
            {'action': 'navigate', 'url': 'https://example.com/login'},
            {'action': 'fill', 'selector': 'input[name="username"]', 'value': 'test_user'},
            {'action': 'click', 'selector': 'button[type="submit"]'},
        ]
    }
    
    return loader


@pytest.fixture
def mock_popup_handler():
    """创建模拟的弹窗处理器"""
    handler = Mock(spec=UniversalPopupHandler)
    handler.close_popups = AsyncMock(return_value=0)
    return handler


@pytest.fixture
def mock_page():
    """创建模拟的Playwright Page（含 context.browser 供执行器 new_context 使用）"""
    page = Mock()
    
    # 模拟locator（同步返回，但方法是异步的）
    mock_locator = Mock()
    mock_locator.first = mock_locator
    mock_locator.click = AsyncMock()
    mock_locator.fill = AsyncMock()
    mock_locator.clear = AsyncMock()
    mock_locator.is_visible = AsyncMock(return_value=False)
    mock_locator.wait_for = AsyncMock()
    mock_locator.select_option = AsyncMock()
    
    # page.locator()同步返回locator对象
    page.locator = Mock(return_value=mock_locator)
    
    # 页面级异步方法
    page.goto = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.screenshot = AsyncMock()
    
    # 键盘
    page.keyboard = Mock()
    page.keyboard.press = AsyncMock()
    
    page.frames = []
    page.context = Mock()
    page.context.storage_state = AsyncMock(return_value=None)

    # 执行器会从 page.context.browser 取 browser，再 await browser.new_context() / context.new_page()
    mock_ctx = Mock()
    mock_ctx.new_page = AsyncMock(return_value=page)
    page.context.browser = Mock()
    page.context.browser.new_context = AsyncMock(return_value=mock_ctx)
    
    return page


@pytest.fixture
def executor(mock_component_loader, mock_popup_handler):
    """创建执行引擎实例"""
    return CollectionExecutorV2(
        component_loader=mock_component_loader,
        popup_handler=mock_popup_handler,
    )


class TestCollectionExecutorV2:
    """CollectionExecutorV2测试类"""
    
    async def test_initialization(self):
        """测试初始化"""
        executor = CollectionExecutorV2()
        
        assert executor.component_loader is not None
        assert executor.popup_handler is not None
        assert executor._task_contexts == {}
    
    async def test_execute_basic_flow(self, executor, mock_page, mock_component_loader):
        """测试基本执行流程（Python 组件模式：mock adapter 避免真实登录/导出）"""
        # 返回带 _python_component_class 的 dict，走 Python 分支；adapter 由下方 patch 提供
        def mock_load(path, params=None):
            if "login" in path:
                return {
                    "name": "test_login",
                    "platform": "shopee",
                    "type": "login",
                    "_params": params or {},
                    "_python_component_class": True,
                }
            if "navigation" in path:
                raise FileNotFoundError("Navigation not found")
            return {
                "name": "test_export",
                "platform": "shopee",
                "type": "export",
                "data_domain": "orders",
                "_params": params or {},
                "_python_component_class": True,
            }

        mock_component_loader.load.side_effect = mock_load

        mock_adapter = Mock()
        mock_adapter.execute_component = AsyncMock(return_value=AdapterResult(success=True))
        mock_adapter.export = AsyncMock(return_value=AdapterResult(success=True))

        with patch(
            "modules.apps.collection_center.executor_v2.create_adapter",
            return_value=mock_adapter,
        ):
            result = await executor.execute(
                task_id="test-task-1",
                platform="shopee",
                account_id="account-1",
                account={"username": "test", "password": "pass"},
                data_domains=["orders"],
                date_range={"start": "2025-01-01", "end": "2025-01-31"},
                granularity="daily",
                page=mock_page,
            )

        assert result.task_id == "test-task-1"
        assert result.status == "completed"
        assert result.duration_seconds >= 0

    async def test_execute_uses_runtime_manifest_file_paths_for_login_and_export(
        self, executor, mock_page
    ):
        """正式运行应按 stable runtime manifest 的 file_path 加载组件。"""

        class _Result:
            def __init__(self, success=True, message="ok", file_path=None):
                self.success = success
                self.message = message
                self.file_path = file_path

        class _LoginComponent:
            platform = "shopee"
            component_type = "login"

            def __init__(self, ctx):
                self.ctx = ctx

            async def run(self, page):
                return _Result(success=True, message="login ok")

        class _OrdersExportComponent:
            platform = "shopee"
            component_type = "export"
            data_domain = "orders"

            def __init__(self, ctx):
                self.ctx = ctx

            async def run(self, page, *args, **kwargs):
                return _Result(success=True, message="export ok", file_path="temp/orders.xlsx")

        runtime_manifests = {
            "login": RuntimeComponentManifest(
                component_name="shopee/login",
                version="1.0.0",
                file_path="modules/platforms/shopee/components/login_v1_0_0.py",
                platform="shopee",
                component_type="login",
            ),
            "exports_by_domain": {
                "orders": RuntimeComponentManifest(
                    component_name="shopee/orders_export",
                    version="1.0.0",
                    file_path="modules/platforms/shopee/components/orders_export_v1_0_0.py",
                    platform="shopee",
                    component_type="export",
                    data_domain="orders",
                )
            },
        }

        executor.component_loader.load_python_component_from_path = Mock(
            side_effect=[_LoginComponent, _OrdersExportComponent]
        )

        result = await executor.execute(
            task_id="manifest-task-1",
            platform="shopee",
            account_id="account-1",
            account={"username": "test", "password": "pass"},
            data_domains=["orders"],
            date_range={"start": "2025-01-01", "end": "2025-01-31"},
            granularity="daily",
            page=mock_page,
            runtime_manifests=runtime_manifests,
        )

        assert result.status == "completed"
        assert executor.component_loader.load_python_component_from_path.call_count == 2
        login_call = executor.component_loader.load_python_component_from_path.call_args_list[0]
        export_call = executor.component_loader.load_python_component_from_path.call_args_list[1]
        assert login_call.args[0] == runtime_manifests["login"].file_path
        assert export_call.args[0] == runtime_manifests["exports_by_domain"]["orders"].file_path

    async def test_execute_with_runtime_manifests_does_not_use_adapter_loading(
        self, executor, mock_page
    ):
        """正式运行提供 manifest 时，不应再依赖 adapter 的模块名加载路径。"""

        class _Result:
            def __init__(self, success=True, message="ok", file_path=None):
                self.success = success
                self.message = message
                self.file_path = file_path

        class _LoginComponent:
            platform = "shopee"
            component_type = "login"

            def __init__(self, ctx):
                self.ctx = ctx

            async def run(self, page):
                return _Result(success=True)

        class _OrdersExportComponent:
            platform = "shopee"
            component_type = "export"
            data_domain = "orders"

            def __init__(self, ctx):
                self.ctx = ctx

            async def run(self, page, *args, **kwargs):
                return _Result(success=True, file_path="temp/orders.xlsx")

        runtime_manifests = {
            "login": RuntimeComponentManifest(
                component_name="shopee/login",
                version="1.0.0",
                file_path="modules/platforms/shopee/components/login_v1_0_0.py",
                platform="shopee",
                component_type="login",
            ),
            "exports_by_domain": {
                "orders": RuntimeComponentManifest(
                    component_name="shopee/orders_export",
                    version="1.0.0",
                    file_path="modules/platforms/shopee/components/orders_export_v1_0_0.py",
                    platform="shopee",
                    component_type="export",
                    data_domain="orders",
                )
            },
        }

        executor.component_loader.load_python_component_from_path = Mock(
            side_effect=[_LoginComponent, _OrdersExportComponent]
        )

        with patch(
            "modules.apps.collection_center.executor_v2.create_adapter",
            side_effect=AssertionError("formal runtime should not call create_adapter"),
        ):
            result = await executor.execute(
                task_id="manifest-task-2",
                platform="shopee",
                account_id="account-2",
                account={"username": "test", "password": "pass"},
                data_domains=["orders"],
                date_range={"start": "2025-01-01", "end": "2025-01-31"},
                granularity="daily",
                page=mock_page,
                runtime_manifests=runtime_manifests,
            )

        assert result.status == "completed"
    
    async def test_status_callback(self, mock_component_loader, mock_popup_handler, mock_page):
        """测试状态回调"""
        status_updates = []
        
        async def status_callback(task_id, progress, message):
            status_updates.append((task_id, progress, message))
        
        executor = CollectionExecutorV2(
            component_loader=mock_component_loader,
            popup_handler=mock_popup_handler,
            status_callback=status_callback,
        )
        
        # 简化组件
        mock_component_loader.load.side_effect = FileNotFoundError("Not found")
        
        try:
            await executor.execute(
                task_id='test-task-2',
                platform='shopee',
                account_id='account-1',
                account={'username': 'test', 'password': 'pass'},
                data_domains=['orders'],
                date_range={'start': '2025-01-01', 'end': '2025-01-31'},
                granularity='daily',
                page=mock_page,
            )
        except:
            pass
        
        # 验证有状态更新
        assert len(status_updates) > 0
        assert status_updates[0][0] == 'test-task-2'
    
    async def test_task_cancellation(self, mock_component_loader, mock_popup_handler, mock_page):
        """测试任务取消"""
        async def is_cancelled(task_id):
            return True  # 模拟任务被取消
        
        executor = CollectionExecutorV2(
            component_loader=mock_component_loader,
            popup_handler=mock_popup_handler,
            is_cancelled_callback=is_cancelled,
        )
        
        result = await executor.execute(
            task_id='test-task-3',
            platform='shopee',
            account_id='account-1',
            account={'username': 'test', 'password': 'pass'},
            data_domains=['orders'],
            date_range={'start': '2025-01-01', 'end': '2025-01-31'},
            granularity='daily',
            page=mock_page,
        )
        
        assert result.status == 'cancelled'
        assert '取消' in result.error_message
    
    async def test_task_context(self, executor):
        """测试任务上下文"""
        context = TaskContext(
            task_id='test-task-4',
            platform='shopee',
            account_id='account-1',
            data_domains=['orders', 'products'],
            date_range={'start': '2025-01-01', 'end': '2025-01-31'},
            granularity='daily',
        )
        
        executor._task_contexts['test-task-4'] = context
        
        retrieved = executor.get_task_context('test-task-4')
        
        assert retrieved is not None
        assert retrieved.task_id == 'test-task-4'
        assert retrieved.platform == 'shopee'
    
    async def test_step_execution_navigate(self, executor, mock_page):
        """测试navigate步骤执行"""
        step = {'action': 'navigate', 'url': 'https://example.com', 'timeout': 5000}
        component = {'platform': 'shopee'}
        
        await executor._execute_step(mock_page, step, component)
        
        mock_page.goto.assert_called_once()
    
    async def test_step_execution_click(self, executor, mock_page):
        """测试click步骤执行"""
        step = {'action': 'click', 'selector': 'button.submit', 'timeout': 5000}
        component = {'platform': 'shopee'}
        
        await executor._execute_step(mock_page, step, component)
        
        mock_page.locator.assert_called_with('button.submit')
    
    async def test_step_execution_fill(self, executor, mock_page):
        """测试fill步骤执行"""
        step = {'action': 'fill', 'selector': 'input.username', 'value': 'test', 'timeout': 5000}
        component = {'platform': 'shopee'}
        
        await executor._execute_step(mock_page, step, component)
        
        mock_page.locator.assert_called_with('input.username')


class TestPopupHandler:
    """弹窗处理器测试"""
    
    def test_get_close_selectors(self):
        """测试获取关闭选择器"""
        handler = UniversalPopupHandler()
        
        selectors = handler.get_close_selectors()
        
        assert len(selectors) > 0
        assert '[aria-label="Close"]' in selectors
    
    def test_get_close_selectors_with_platform(self):
        """测试获取平台特定选择器（平台可从 popup_config.py 返回空或更多）"""
        handler = UniversalPopupHandler()
        
        selectors = handler.get_close_selectors(platform='shopee')
        
        # 至少包含通用选择器；平台可追加 0 或多个
        assert len(selectors) >= len(handler.UNIVERSAL_CLOSE_SELECTORS)
    
    def test_get_poll_strategy(self):
        """测试获取轮询策略"""
        handler = UniversalPopupHandler()
        
        strategy = handler.get_poll_strategy()
        
        assert 'max_rounds' in strategy
        assert 'interval_ms' in strategy
        assert 'watch_ms' in strategy


class TestCollectionResult:
    """CollectionResult测试"""
    
    def test_completed_result(self):
        """测试完成结果"""
        result = CollectionResult(
            task_id='test-1',
            status='completed',
            files_collected=5,
            collected_files=['file1.xlsx', 'file2.xlsx'],
            duration_seconds=120.5,
        )
        
        assert result.status == 'completed'
        assert result.files_collected == 5
        assert len(result.collected_files) == 2
    
    def test_failed_result(self):
        """测试失败结果"""
        result = CollectionResult(
            task_id='test-2',
            status='failed',
            error_message='Connection timeout',
        )
        
        assert result.status == 'failed'
        assert result.error_message == 'Connection timeout'


class TestTaskContext:
    """TaskContext测试"""
    
    def test_context_creation(self):
        """测试上下文创建"""
        context = TaskContext(
            task_id='test-1',
            platform='shopee',
            account_id='acc-1',
            data_domains=['orders', 'products'],
            date_range={'start': '2025-01-01', 'end': '2025-01-31'},
            granularity='daily',
        )
        
        assert context.task_id == 'test-1'
        assert context.current_component_index == 0
        assert context.current_step_index == 0
        assert context.verification_required is False
    
    def test_context_update(self):
        """测试上下文更新"""
        context = TaskContext(
            task_id='test-1',
            platform='shopee',
            account_id='acc-1',
            data_domains=['orders'],
            date_range={'start': '2025-01-01', 'end': '2025-01-31'},
            granularity='daily',
        )
        
        context.current_component_index = 2
        context.collected_files.append('test.xlsx')
        
        assert context.current_component_index == 2
        assert len(context.collected_files) == 1
