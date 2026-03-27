"""
Python Component Adapter - 异步 Python 组件统一适配层

职责:
- 为 executor_v2 提供统一的 Python 组件执行接口
- 集中处理账号预处理(密码解密)
- 替代 YAML 组件的 component_call 机制
- 提供组件调用方法供子组件间调用

用法:
    adapter = PythonComponentAdapter(platform="shopee", account=account_dict, config=config_dict)
    result = await adapter.login(page)
    result = await adapter.navigate(page, target_page="orders")
    result = await adapter.export(page, data_domain="orders")
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Type

from modules.components.base import ExecutionContext, ResultBase
from modules.core.logger import get_logger
from backend.services.collection_component_topology import is_canonical_component_filename


logger = get_logger("python_component_adapter")


# 数据域到导出组件的映射
DATA_DOMAIN_EXPORT_MAP = {
    "shopee": {
        "orders": "ShopeeOrdersExport",
        "products": "ShopeeProductsExport",
        "finance": "ShopeeFinanceExport",
        "services": "ShopeeServicesExport",
        "analytics": "ShopeeAnalyticsExport",
        "traffic": "ShopeeAnalyticsExport",  # 别名
    },
    "tiktok": {
        "orders": "TiktokExport",  # TikTok 使用通用导出
        "products": "TiktokExport",
        "finance": "TiktokExport",
        "analytics": "TiktokExport",
        "services": "TiktokExport",
    },
    "miaoshou": {
        "orders": "MiaoshouOrdersExport",
        "products": "MiaoshouExport",
        "warehouse": "MiaoshouExport",
        "inventory": "MiaoshouExport",
        "analytics": "MiaoshouExport",
    },
}

# 平台到组件模块的映射
PLATFORM_MODULE_MAP = {
    "shopee": "modules.platforms.shopee.components",
    "tiktok": "modules.platforms.tiktok.components",
    "miaoshou": "modules.platforms.miaoshou.components",
    "amazon": "modules.platforms.amazon.components",
}


@dataclass
class AdapterResult:
    """适配层执行结果"""
    success: bool
    message: str = ""
    data: Optional[Dict[str, Any]] = None
    file_path: Optional[str] = None


class PythonComponentAdapter:
    """Python 组件统一适配层
    
    提供异步的组件执行接口,替代 YAML 组件的执行逻辑。
    v4.8.0: 支持步骤回调和步骤ID命名空间

    注意:
    - 正式采集运行路径必须优先使用 stable runtime manifest + file_path 解析组件
    - 本适配层保留给录制测试、组件测试和调试路径
    - 不应再作为正式任务的最终组件选择器
    """
    
    def __init__(
        self,
        platform: str,
        account: Dict[str, Any],
        config: Optional[Dict[str, Any]] = None,
        logger: Optional[Any] = None,
        step_callback: Optional[Any] = None,  # v4.8.0: 步骤回调
        step_prefix: str = "",  # v4.8.0: 步骤ID前缀
        is_test_mode: bool = False,  # v4.8.0: 测试模式
        override_login_class: Optional[Type] = None,
        override_navigation_class: Optional[Type] = None,
        override_export_class: Optional[Type] = None,
        override_date_picker_class: Optional[Type] = None,
        override_shop_switch_class: Optional[Type] = None,
        override_filters_class: Optional[Type] = None,
    ):
        """初始化适配器"""
        self.platform = platform
        self.account = self._prepare_account(account)
        self.config = config or {}
        self._logger = logger
        self._step_callback = step_callback
        self._step_prefix = step_prefix
        self._is_test_mode = is_test_mode
        self._override_login_class = override_login_class
        self._override_navigation_class = override_navigation_class
        self._override_export_class = override_export_class
        self._override_date_picker_class = override_date_picker_class
        self._override_shop_switch_class = override_shop_switch_class
        self._override_filters_class = override_filters_class
        
        # 创建执行上下文
        self.ctx = ExecutionContext(
            platform=platform,
            account=self.account,
            logger=self._logger,
            config=self.config,
            step_callback=step_callback,
            step_prefix=step_prefix,
            is_test_mode=is_test_mode,
        )
        
        # 组件缓存
        self._component_cache: Dict[str, Any] = {}
    
    def _prepare_account(self, account: Dict[str, Any]) -> Dict[str, Any]:
        """准备账号信息(含密码解密)
        
        Args:
            account: 原始账号信息
            
        Returns:
            Dict: 处理后的账号信息(密码已解密)
        """
        prepared = account.copy()
        
        # 解密密码
        if "password_encrypted" in prepared:
            try:
                from backend.services.encryption_service import get_encryption_service
                svc = get_encryption_service()
                decrypted = svc.decrypt_password(prepared["password_encrypted"])
                prepared["password"] = decrypted
                logger.info("[Adapter] Password decrypted successfully")
            except Exception as e:
                # 降级:使用原值(可能是明文或空)
                logger.warning(f"[Adapter] Password decryption failed, using original: {e}")
                if "password" not in prepared:
                    prepared["password"] = prepared.get("password_encrypted", "")
        
        return prepared
    
    def _load_component_class(self, component_name: str) -> Optional[Type]:
        """加载组件类
        
        Args:
            component_name: 组件名(如 "login"、"navigation"、"orders_export")
            
        Returns:
            Type: 组件类,或 None(加载失败)
        """
        # 检查缓存
        cache_key = f"{self.platform}/{component_name}"
        if cache_key in self._component_cache:
            return self._component_cache[cache_key]
        
        # 确定模块路径
        base_module = PLATFORM_MODULE_MAP.get(self.platform)
        if not base_module:
            logger.error(f"[Adapter] Unknown platform: {self.platform}")
            return None
        
        try:
            module = importlib.import_module(f"{base_module}.{component_name}")
            
            # 查找组件类(优先匹配平台前缀)
            platform_prefix = self.platform.capitalize()
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if name.startswith(platform_prefix):
                    self._component_cache[cache_key] = obj
                    return obj
            
            # 备选:查找任何以 Component 结尾的类
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if name.endswith("Component") or name.endswith("Export"):
                    self._component_cache[cache_key] = obj
                    return obj
                    
            logger.warning(f"[Adapter] No component class found in {base_module}.{component_name}")
            return None
            
        except ImportError as e:
            logger.error(f"[Adapter] Failed to import component: {e}")
            return None
    
    async def login(self, page: Any) -> AdapterResult:
        """执行登录组件。override 存在时使用注入类，不得再按模块名加载。"""
        try:
            component_class = self._override_login_class or self._load_component_class("login")
            if not component_class:
                return AdapterResult(success=False, message="Failed to load login component")
            
            component = component_class(self.ctx)
            result = await component.run(page)
            
            return AdapterResult(
                success=result.success,
                message=result.message,
                data={"details": getattr(result, "details", None)},
            )
        except Exception as e:
            # 验证码/OTP 需由执行器统一处理：暂停、持久化、阻塞等待回传、同一 page 继续
            from modules.apps.collection_center.executor_v2 import VerificationRequiredError
            if isinstance(e, VerificationRequiredError):
                raise
            logger.error(f"[Adapter] Login failed: {e}")
            return AdapterResult(success=False, message=str(e))
    
    async def navigate(self, page: Any, target_page: str) -> AdapterResult:
        """执行导航组件。override 存在时使用注入类。"""
        try:
            component_class = self._override_navigation_class or self._load_component_class("navigation")
            if not component_class:
                return AdapterResult(success=False, message="Failed to load navigation component")
            
            component = component_class(self.ctx)
            result = await component.run(page, target_page)
            
            return AdapterResult(
                success=result.success,
                message=result.message,
                data={"url": getattr(result, "url", None)},
            )
        except Exception as e:
            logger.error(f"[Adapter] Navigation failed: {e}")
            return AdapterResult(success=False, message=str(e))
    
    async def export(self, page: Any, data_domain: str) -> AdapterResult:
        """执行导出组件
        
        Args:
            page: Playwright Page 对象
            data_domain: 数据域(如 "orders"、"products"、"finance")
            
        Returns:
            AdapterResult: 执行结果
        """
        try:
            # 获取对应的导出组件类名
            domain_map = DATA_DOMAIN_EXPORT_MAP.get(self.platform, {})
            export_class_name = domain_map.get(data_domain)
            
            if not export_class_name:
                return AdapterResult(
                    success=False,
                    message=f"Unknown data domain: {data_domain} for platform {self.platform}"
                )
            
            module_name = f"{data_domain}_export"
            canonical_filename = f"{module_name}.py"
            if not is_canonical_component_filename(canonical_filename):
                return AdapterResult(
                    success=False,
                    message=f"Invalid canonical export component filename: {canonical_filename}",
                )
            component_class = (
                self._override_export_class
                or self._load_component_class(module_name)
            )
            
            if not component_class:
                return AdapterResult(
                    success=False,
                    message=f"Failed to load canonical export component for {data_domain}",
                )
            
            component = component_class(self.ctx)
            result = await component.run(page)
            
            return AdapterResult(
                success=result.success,
                message=result.message,
                file_path=getattr(result, "file_path", None),
            )
        except Exception as e:
            # 导出阶段验证码同样由执行器统一处理：暂停、持久化、阻塞等待回传、同一 page 继续
            from modules.apps.collection_center.executor_v2 import VerificationRequiredError
            if isinstance(e, VerificationRequiredError):
                raise
            logger.error(f"[Adapter] Export failed: {e}")
            return AdapterResult(success=False, message=str(e))
    
    async def date_picker(self, page: Any, option: Any) -> AdapterResult:
        """执行日期选择组件。override 存在时使用注入类。"""
        try:
            component_class = self._override_date_picker_class or self._load_component_class("date_picker")
            if not component_class:
                return AdapterResult(success=False, message="Failed to load date_picker component")
            
            component = component_class(self.ctx)
            result = await component.run(page, option)
            
            return AdapterResult(
                success=result.success,
                message=result.message,
            )
        except Exception as e:
            logger.error(f"[Adapter] DatePicker failed: {e}")
            return AdapterResult(success=False, message=str(e))
    
    async def call_component(
        self,
        component_name: str,
        page: Any,
        *args: Any,
        **kwargs: Any
    ) -> AdapterResult:
        """通用组件调用方法(替代 YAML 的 component_call)
        
        v4.8.0: 子组件继承步骤回调,并添加步骤ID前缀
        
        Args:
            component_name: 组件名(如 "date_picker"、"shop_selector")
            page: Playwright Page 对象
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            AdapterResult: 执行结果
        """
        try:
            override_map = {
                "date_picker": self._override_date_picker_class,
                "shop_switch": self._override_shop_switch_class,
                "filters": self._override_filters_class,
            }
            component_class = override_map.get(component_name) or self._load_component_class(component_name)
            if not component_class:
                return AdapterResult(
                    success=False,
                    message=f"Failed to load component: {component_name}"
                )
            
            # v4.8.0: 为子组件创建新的上下文,添加步骤ID前缀
            child_step_prefix = f"{self._step_prefix}{component_name}."
            child_ctx = ExecutionContext(
                platform=self.platform,
                account=self.account,
                logger=self._logger,
                config=self.config,
                step_callback=self._step_callback,  # 继承步骤回调
                step_prefix=child_step_prefix,  # 添加前缀
                is_test_mode=self._is_test_mode,
            )
            
            component = component_class(child_ctx)
            result = await component.run(page, *args, **kwargs)
            
            return AdapterResult(
                success=result.success,
                message=getattr(result, "message", ""),
                data=getattr(result, "details", None),
                file_path=getattr(result, "file_path", None),
            )
        except Exception as e:
            logger.error(f"[Adapter] Component {component_name} failed: {e}")
            return AdapterResult(success=False, message=str(e))
    
    async def execute_component(
        self,
        component_name: str,
        page: Any,
        params: Optional[Dict[str, Any]] = None,
    ) -> AdapterResult:
        """执行指定组件(供 executor_v2 调用)
        
        Args:
            component_name: 组件名(如 "login"、"navigation"、"orders_export")
            page: Playwright Page 对象
            params: 组件参数
            
        Returns:
            AdapterResult: 执行结果
        """
        params = params or {}
        
        # 根据组件名分发到对应方法
        if component_name == "login":
            return await self.login(page)
        elif component_name == "navigation":
            target = params.get("target") or params.get("target_page")
            return await self.navigate(page, target)
        elif component_name.endswith("_export"):
            data_domain = component_name.replace("_export", "")
            return await self.export(page, data_domain)
        elif component_name == "date_picker":
            option = params.get("option") or params.get("date_option")
            return await self.date_picker(page, option)
        else:
            return await self.call_component(component_name, page, **params)


def create_adapter(
    platform: str,
    account: Dict[str, Any],
    config: Optional[Dict[str, Any]] = None,
    logger: Optional[Any] = None,
    step_callback: Optional[Any] = None,
    step_prefix: str = "",
    is_test_mode: bool = False,
    override_login_class: Optional[Type] = None,
    override_navigation_class: Optional[Type] = None,
    override_export_class: Optional[Type] = None,
    override_date_picker_class: Optional[Type] = None,
    override_shop_switch_class: Optional[Type] = None,
    override_filters_class: Optional[Type] = None,
) -> PythonComponentAdapter:
    """创建 Python 组件适配器的工厂函数。支持 override 注入指定组件类。"""
    return PythonComponentAdapter(
        platform=platform,
        account=account,
        config=config,
        logger=logger,
        step_callback=step_callback,
        step_prefix=step_prefix,
        is_test_mode=is_test_mode,
        override_login_class=override_login_class,
        override_navigation_class=override_navigation_class,
        override_export_class=override_export_class,
        override_date_picker_class=override_date_picker_class,
        override_shop_switch_class=override_shop_switch_class,
        override_filters_class=override_filters_class,
    )
