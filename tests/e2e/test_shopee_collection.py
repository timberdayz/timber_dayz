"""
Shopee 采集端到端测试

测试完整的采集流程：登录 → 导航 → 日期选择 → 导出 → 文件处理

使用方法：
    # 运行所有端到端测试
    pytest tests/e2e/test_shopee_collection.py -v
    
    # 运行单个测试（带账号参数）
    pytest tests/e2e/test_shopee_collection.py::TestShopeeE2E::test_single_component -v --account MyStore_SG
    
    # 跳过需要真实浏览器的测试
    pytest tests/e2e/test_shopee_collection.py -v -m "not requires_browser"
"""

import os
import sys
import pytest
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from modules.apps.collection_center.component_loader import ComponentLoader
from modules.apps.collection_center.popup_handler import UniversalPopupHandler


class TestShopeeComponentLoading:
    """测试Shopee组件加载"""
    
    @pytest.fixture
    def loader(self):
        return ComponentLoader()
    
    def test_load_login_component(self, loader):
        """测试加载登录组件"""
        component = loader.load("shopee/login")
        
        assert component is not None
        assert component["name"] == "shopee_login"
        assert component["platform"] == "shopee"
        assert component["type"] == "login"
        assert "steps" in component
        assert len(component["steps"]) > 0
    
    def test_load_navigation_component(self, loader):
        """测试加载导航组件"""
        component = loader.load("shopee/navigation")
        
        assert component is not None
        assert component["name"] == "shopee_navigation"
        assert "data_domain_urls" in component
    
    def test_load_date_picker_component(self, loader):
        """测试加载日期选择组件"""
        component = loader.load("shopee/date_picker")
        
        assert component is not None
        assert component["type"] == "date_picker"
    
    def test_load_orders_export_component(self, loader):
        """测试加载订单导出组件"""
        component = loader.load("shopee/orders_export")
        
        assert component is not None
        assert component["data_domain"] == "orders"
        assert "dependencies" in component
    
    def test_load_all_export_components(self, loader):
        """测试加载所有导出组件"""
        export_components = [
            "shopee/orders_export",
            "shopee/products_export",
            "shopee/analytics_export",
        ]
        
        for comp_name in export_components:
            component = loader.load(comp_name)
            assert component is not None
            assert component["type"] == "export"
    
    def test_component_variable_rendering(self, loader):
        """测试组件变量渲染"""
        component = loader.load("shopee/login")
        
        # 验证组件已加载
        assert component is not None
        assert "steps" in component
        
        # 验证步骤中包含变量模板
        steps = component.get("steps", [])
        has_variable = False
        for step in steps:
            value = step.get("value", "")
            url = step.get("url", "")
            if "{{" in str(value) or "{{" in str(url):
                has_variable = True
                break
        
        assert has_variable, "组件应包含变量模板"


class TestShopeePopupConfig:
    """测试Shopee弹窗配置"""
    
    @pytest.fixture
    def loader(self):
        return ComponentLoader()
    
    def test_load_popup_config(self, loader):
        """测试加载弹窗配置"""
        # popup_config不是标准组件，直接读取yaml
        import yaml
        
        config_path = Path(__file__).parent.parent.parent / "config" / "collection_components" / "shopee" / "popup_config.yaml"
        
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        assert config is not None
        assert config["platform"] == "shopee"
        assert "close_selectors" in config
        assert "poll_strategy" in config
    
    def test_popup_handler_initialization(self):
        """测试弹窗处理器初始化"""
        handler = UniversalPopupHandler()
        
        # 验证处理器已初始化
        assert handler.platform_config_dir is not None
        assert len(handler.UNIVERSAL_CLOSE_SELECTORS) > 0
        assert len(handler.UNIVERSAL_OVERLAY_SELECTORS) > 0


class TestCollectionAPIIntegration:
    """测试采集API集成"""
    
    @pytest.fixture
    def mock_db(self):
        """模拟数据库会话"""
        db = Mock()
        db.query.return_value.filter.return_value.count.return_value = 0
        db.execute.return_value.rowcount = 1
        return db
    
    def test_task_service_creation(self, mock_db):
        """测试任务服务创建"""
        from backend.services.task_service import TaskService
        
        service = TaskService(mock_db)
        
        assert service.db == mock_db
        assert service.MAX_CONCURRENT_TASKS >= 1
    
    def test_cleanup_service_creation(self):
        """测试清理服务创建"""
        from backend.services.cleanup_service import CleanupService
        
        service = CleanupService()
        
        assert service.downloads_dir is not None
        assert service.screenshots_dir is not None


class TestShopeeE2E:
    """
    Shopee端到端测试
    
    注意：这些测试需要真实的浏览器和账号
    在CI环境中会被跳过
    """
    
    @pytest.fixture
    def account_id(self, request):
        """获取账号ID（从命令行参数或环境变量）"""
        # 尝试从命令行参数获取
        account = request.config.getoption("--account", default=None)
        
        if not account:
            # 尝试从环境变量获取
            account = os.getenv("TEST_SHOPEE_ACCOUNT")
        
        return account
    
    @pytest.mark.requires_browser
    @pytest.mark.asyncio
    async def test_single_component_execution(self, account_id):
        """
        测试单个组件执行
        
        需要真实浏览器环境
        """
        if not account_id:
            pytest.skip("No account specified. Use --account or TEST_SHOPEE_ACCOUNT env var.")
        
        from tools.test_component import ComponentTester
        
        tester = ComponentTester(
            platform="shopee",
            account_id=account_id,
            headless=False
        )
        
        # 测试登录组件结构验证
        components = tester.list_components()
        assert "login" in components
        
        # 注意：实际浏览器执行需要在本地环境手动验证
        # result = await tester.test_component("login")
        # assert result.status == TestStatus.PASSED
    
    @pytest.mark.requires_browser
    @pytest.mark.asyncio
    async def test_full_collection_flow(self, account_id):
        """
        测试完整采集流程
        
        登录 → 导航 → 日期选择 → 导出 → 文件处理
        
        注意：此测试需要真实环境手动执行
        """
        if not account_id:
            pytest.skip("No account specified")
        
        # 这是一个框架性测试，实际执行需要手动验证
        # 完整流程测试步骤：
        #
        # 1. 启动浏览器
        # 2. 执行登录组件
        # 3. 验证登录成功
        # 4. 执行导航组件（到订单页面）
        # 5. 执行日期选择组件
        # 6. 执行订单导出组件
        # 7. 验证文件下载
        # 8. 验证文件命名和注册
        
        print(f"""
=============================================================
 Shopee 完整采集流程手动测试指南
=============================================================

请使用以下命令进行手动测试：

1. 测试单个组件：
   python tools/test_component.py -p shopee -c login -a {account_id}
   python tools/test_component.py -p shopee -c navigation -a {account_id}
   python tools/test_component.py -p shopee -c orders_export -a {account_id}

2. 测试所有组件：
   python tools/test_component.py --all -p shopee -a {account_id}

3. 使用录制工具完善组件：
   python tools/record_component.py -p shopee -c login -a {account_id}

4. 验证文件注册：
   检查 data/raw/{datetime.now().year}/ 目录
   检查 catalog_files 表

=============================================================
        """)
        
        # 标记为跳过，因为需要手动验证
        pytest.skip("Manual verification required")


class TestFileNamingAndRegistration:
    """测试文件命名和注册"""
    
    def test_standard_filename_generation(self):
        """测试标准文件名生成"""
        # 这需要StandardFileName工具类
        # 验证文件名格式：{platform}_{domain}_{granularity}_{date}_{timestamp}.xlsx
        
        expected_pattern = r"shopee_orders_daily_\d{8}_\d{6}\.xlsx"
        
        # 实际实现后取消注释
        # from modules.utils.file_naming import StandardFileName
        # generator = StandardFileName(
        #     platform="shopee",
        #     data_domain="orders",
        #     granularity="daily",
        #     timestamp=datetime.now()
        # )
        # filename = generator.generate_filename(".xlsx")
        # assert re.match(expected_pattern, filename)
        
        pass  # 占位


def pytest_addoption(parser):
    """添加命令行参数"""
    parser.addoption(
        "--account",
        action="store",
        default=None,
        help="Test account ID for E2E tests"
    )


def pytest_configure(config):
    """配置pytest标记"""
    config.addinivalue_line(
        "markers", "requires_browser: marks tests that require a real browser"
    )


# 运行测试
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "not requires_browser"])

