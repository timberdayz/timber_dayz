"""
组件加载器 - Component Loader

负责加载、验证、缓存 YAML/Python 组件配置

v4.8.0: 添加 Python 组件加载支持，逐步废弃 YAML 组件
"""

import os
import re
import importlib
import inspect
from pathlib import Path
from typing import Dict, Any, Optional, List, Type
import yaml

from modules.core.logger import get_logger

logger = get_logger(__name__)


# v4.8.0: Python 组件平台模块映射
PYTHON_COMPONENT_PLATFORMS = {
    'shopee': 'modules.platforms.shopee.components',
    'tiktok': 'modules.platforms.tiktok.components',
    'miaoshou': 'modules.platforms.miaoshou.components',
}


class ComponentValidationError(Exception):
    """组件验证错误"""
    pass


class ComponentLoader:
    """
    组件加载器
    
    功能：
    1. 加载YAML组件配置
    2. 验证组件格式和安全性
    3. 缓存组件配置（生产模式）
    4. 参数模板替换
    """
    
    # 危险的selector模式（安全验证）
    DANGEROUS_PATTERNS = [
        r'javascript:',
        r'data:',
        r'on\w+\s*=',  # onclick=, onload= 等
        r'<script',
        r'eval\(',
        r'Function\(',
    ]
    
    # 支持的平台
    SUPPORTED_PLATFORMS = ['shopee', 'tiktok', 'miaoshou']
    
    # 支持的组件类型（Phase 7.2: 添加shop_switch, Phase 11: 添加filters）
    SUPPORTED_TYPES = ['login', 'shop_switch', 'navigation', 'date_picker', 'filters', 'export', 'verification']
    
    # Phase 11: 发现模式组件类型（使用 open_action + available_options 而非 steps）
    DISCOVERY_MODE_TYPES = ['date_picker', 'filters']
    
    # 支持的数据域
    SUPPORTED_DATA_DOMAINS = ['orders', 'products', 'services', 'analytics', 'finance', 'inventory']
    
    def __init__(self, components_dir: str = None, hot_reload: bool = None):
        """
        初始化组件加载器
        
        Args:
            components_dir: 组件目录路径（默认：config/collection_components）
            hot_reload: 是否热重载（默认：从环境变量COMPONENT_HOT_RELOAD读取）
        """
        if components_dir is None:
            components_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                'config', 'collection_components'
            )
        
        self.components_dir = Path(components_dir)
        
        # 热重载配置
        if hot_reload is None:
            hot_reload = os.getenv('COMPONENT_HOT_RELOAD', 'false').lower() == 'true'
        self.hot_reload = hot_reload
        
        # 组件缓存
        self._cache: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"ComponentLoader initialized: dir={self.components_dir}, hot_reload={self.hot_reload}")
    
    def load(self, component_path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        加载组件配置
        
        Args:
            component_path: 组件路径（如 "shopee/login" 或 "shopee/orders_export"）
            params: 参数字典（用于变量替换）
            
        Returns:
            Dict: 组件配置字典
            
        Raises:
            ComponentValidationError: 组件验证失败
            FileNotFoundError: 组件文件不存在
        """
        # 检查缓存
        if not self.hot_reload and component_path in self._cache:
            component = self._cache[component_path].copy()
            logger.debug(f"Component loaded from cache: {component_path}")
        else:
            # 从文件加载
            component = self._load_from_file(component_path)
            
            # 验证组件
            self._validate_component(component)
            
            # 缓存组件（如果不是热重载模式）
            if not self.hot_reload:
                self._cache[component_path] = component.copy()
            
            logger.info(f"Component loaded: {component_path}")
        
        # 参数替换
        if params:
            component = self._replace_variables(component, params)
        
        return component
    
    def _load_from_file(self, component_path: str) -> Dict[str, Any]:
        """
        从文件加载组件
        
        Args:
            component_path: 组件路径（如 "shopee/login"）
            
        Returns:
            Dict: 组件配置字典
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        # 构建文件路径
        if not component_path.endswith('.yaml'):
            component_path = f"{component_path}.yaml"
        
        file_path = self.components_dir / component_path
        
        if not file_path.exists():
            raise FileNotFoundError(f"Component file not found: {file_path}")
        
        # 读取YAML文件
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                component = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ComponentValidationError(f"Invalid YAML format: {e}")
        
        if not isinstance(component, dict):
            raise ComponentValidationError("Component must be a dictionary")
        
        return component
    
    def _validate_component(self, component: Dict[str, Any]) -> None:
        """
        验证组件配置
        
        Phase 11: 支持发现模式组件（date_picker, filters）
        - 发现模式：使用 open_action + available_options
        - 普通模式：使用 steps
        
        Args:
            component: 组件配置字典
            
        Raises:
            ComponentValidationError: 验证失败
        """
        component_type = component.get('type', '')
        is_discovery_mode = component_type in self.DISCOVERY_MODE_TYPES and 'open_action' in component
        
        # 1. 检查必填字段（发现模式和普通模式不同）
        if is_discovery_mode:
            required_fields = ['name', 'platform', 'type', 'open_action', 'available_options']
        else:
            required_fields = ['name', 'platform', 'type', 'steps']
        
        for field in required_fields:
            if field not in component:
                raise ComponentValidationError(f"Missing required field: {field}")
        
        # 2. 验证平台
        if component['platform'] not in self.SUPPORTED_PLATFORMS:
            raise ComponentValidationError(
                f"Unsupported platform: {component['platform']}. "
                f"Supported: {', '.join(self.SUPPORTED_PLATFORMS)}"
            )
        
        # 3. 验证组件类型
        if component['type'] not in self.SUPPORTED_TYPES:
            raise ComponentValidationError(
                f"Unsupported type: {component['type']}. "
                f"Supported: {', '.join(self.SUPPORTED_TYPES)}"
            )
        
        # 4. export类型必须有data_domain
        if component['type'] == 'export' and 'data_domain' not in component:
            raise ComponentValidationError("Export component must have 'data_domain' field")
        
        # 5. 验证data_domain
        if 'data_domain' in component:
            if component['data_domain'] not in self.SUPPORTED_DATA_DOMAINS:
                raise ComponentValidationError(
                    f"Unsupported data_domain: {component['data_domain']}. "
                    f"Supported: {', '.join(self.SUPPORTED_DATA_DOMAINS)}"
                )
        
        # 6. 根据模式验证结构
        if is_discovery_mode:
            # Phase 11: 验证发现模式结构
            self._validate_discovery_mode(component)
        else:
            # 验证普通模式的步骤
            self._validate_steps(component)
    
    def _validate_discovery_mode(self, component: Dict[str, Any]) -> None:
        """
        验证发现模式组件结构（Phase 11）
        
        发现模式组件使用 open_action + available_options 结构
        
        Args:
            component: 组件配置字典
            
        Raises:
            ComponentValidationError: 验证失败
        """
        # 验证 open_action
        open_action = component.get('open_action')
        if not isinstance(open_action, dict):
            raise ComponentValidationError("Discovery component 'open_action' must be a dictionary")
        
        if 'action' not in open_action and 'selectors' not in open_action:
            raise ComponentValidationError("Discovery component 'open_action' must have 'action' or 'selectors'")
        
        # 验证 available_options
        available_options = component.get('available_options', [])
        if not isinstance(available_options, list) or len(available_options) == 0:
            raise ComponentValidationError("Discovery component must have at least one option in 'available_options'")
        
        for i, option in enumerate(available_options):
            if not isinstance(option, dict):
                raise ComponentValidationError(f"Option {i} must be a dictionary")
            
            if 'key' not in option:
                raise ComponentValidationError(f"Option {i} must have 'key' field")
            
            if 'text' not in option:
                raise ComponentValidationError(f"Option {i} must have 'text' field")
            
            # selectors 可选但如果存在必须是列表
            if 'selectors' in option and not isinstance(option['selectors'], list):
                raise ComponentValidationError(f"Option {i} 'selectors' must be a list")
            
            # 验证字符串安全性
            for key, value in option.items():
                if isinstance(value, str):
                    self._validate_string_security(value, f"option {i}.{key}")
        
        # Phase 12: 验证 test_config（可选但推荐）
        test_config = component.get('test_config', {})
        if test_config:
            if not isinstance(test_config, dict):
                raise ComponentValidationError("'test_config' must be a dictionary")
            
            has_test_url = 'test_url' in test_config
            has_test_data_domain = 'test_data_domain' in test_config
            
            if has_test_url and has_test_data_domain:
                logger.warning("test_config has both test_url and test_data_domain, test_url will be used")
            
            if has_test_data_domain:
                if test_config['test_data_domain'] not in self.SUPPORTED_DATA_DOMAINS:
                    raise ComponentValidationError(
                        f"Invalid test_data_domain: {test_config['test_data_domain']}. "
                        f"Supported: {', '.join(self.SUPPORTED_DATA_DOMAINS)}"
                    )
        else:
            logger.warning(f"Discovery component missing 'test_config'. Testing may require manual navigation.")
        
        logger.debug(f"Discovery mode component validated: {len(available_options)} options")
    
    def _validate_steps(self, component: Dict[str, Any]) -> None:
        """
        验证普通模式组件的步骤结构
        
        Args:
            component: 组件配置字典
            
        Raises:
            ComponentValidationError: 验证失败
        """
        steps = component.get('steps', [])
        
        if not isinstance(steps, list) or len(steps) == 0:
            raise ComponentValidationError("Component must have at least one step")
        
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                raise ComponentValidationError(f"Step {i} must be a dictionary")
            
            if 'action' not in step:
                raise ComponentValidationError(f"Step {i} missing 'action' field")
            
            # 验证所有字符串字段的安全性（防止注入）
            for key, value in step.items():
                if isinstance(value, str):
                    self._validate_string_security(value, f"step {i}.{key}")
    
    def _validate_string_security(self, value: str, field_path: str) -> None:
        """
        验证字符串字段安全性（防止注入攻击）
        
        Args:
            value: 字符串值
            field_path: 字段路径（用于错误信息）
            
        Raises:
            ComponentValidationError: 检测到危险模式
        """
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                raise ComponentValidationError(
                    f"Dangerous pattern detected in {field_path}: {pattern}"
                )
    
    def _replace_variables(self, component: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """
        替换组件中的变量
        
        支持的变量格式：{{xxx.yyy}}
        
        Args:
            component: 组件配置字典
            params: 参数字典（包含account, params, task等）
            
        Returns:
            Dict: 替换后的组件配置
        """
        import json
        
        # 将组件转为JSON字符串
        component_str = json.dumps(component, ensure_ascii=False)
        
        # 替换变量
        def replace_var(match):
            var_path = match.group(1)  # 如 "account.username"
            parts = var_path.split('.')
            
            # 从params中获取值
            value = params
            for part in parts:
                if isinstance(value, dict) and part in value:
                    value = value[part]
                else:
                    # 变量不存在，保持原样
                    return match.group(0)
            
            # 转换为字符串
            if isinstance(value, str):
                return value
            else:
                return json.dumps(value, ensure_ascii=False)
        
        # 正则替换
        component_str = re.sub(r'\{\{([^}]+)\}\}', replace_var, component_str)
        
        # 转回字典
        return json.loads(component_str)
    
    def clear_cache(self) -> None:
        """清空组件缓存"""
        self._cache.clear()
        logger.info("Component cache cleared")
    
    def load_all(self) -> Dict[str, List[str]]:
        """
        加载所有组件（用于预热缓存）
        
        Returns:
            Dict: 按平台分组的组件列表
        """
        components = {}
        
        for platform in self.SUPPORTED_PLATFORMS:
            platform_dir = self.components_dir / platform
            if not platform_dir.exists():
                continue
            
            platform_components = []
            for yaml_file in platform_dir.glob('*.yaml'):
                component_name = yaml_file.stem
                component_path = f"{platform}/{component_name}"
                
                try:
                    self.load(component_path)
                    platform_components.append(component_name)
                except Exception as e:
                    logger.error(f"Failed to load component {component_path}: {e}")
            
            components[platform] = platform_components
        
        logger.info(f"Loaded {sum(len(v) for v in components.values())} components")
        return components
    
    def get_component_info(self, component_path: str) -> Dict[str, Any]:
        """
        获取组件元信息（不加载完整配置）
        
        Args:
            component_path: 组件路径
            
        Returns:
            Dict: 组件元信息
        """
        component = self.load(component_path)
        
        return {
            'name': component.get('name'),
            'platform': component.get('platform'),
            'type': component.get('type'),
            'version': component.get('version', '1.0.0'),
            'description': component.get('description', ''),
            'author': component.get('author', ''),
            'data_domain': component.get('data_domain'),
            'step_count': len(component.get('steps', [])),
        }
    
    # ========== v4.8.0: Python 组件加载支持 ==========
    
    def load_python_component(
        self,
        platform: str,
        component_name: str
    ) -> Optional[Type]:
        """
        v4.8.0: 加载 Python 组件类
        
        Python 组件位于 modules/platforms/{platform}/components/{name}.py
        
        Args:
            platform: 平台代码（shopee/tiktok/miaoshou）
            component_name: 组件名称（login/navigation/orders_export 等）
        
        Returns:
            Type: 组件类，如果不存在则返回 None
        
        Example:
            loader = ComponentLoader()
            LoginComponent = loader.load_python_component('shopee', 'login')
            component = LoginComponent(ctx)
            await component.run(page, account, params)
        """
        if platform not in PYTHON_COMPONENT_PLATFORMS:
            logger.warning(f"Unknown platform: {platform}")
            return None
        
        module_path = PYTHON_COMPONENT_PLATFORMS[platform]
        
        try:
            # 动态导入组件模块
            module = importlib.import_module(f"{module_path}.{component_name}")
            
            # 查找组件类
            component_class = self._find_component_class(module, component_name)
            
            if component_class:
                logger.debug(f"Loaded Python component: {platform}/{component_name}")
                return component_class
            else:
                logger.warning(f"No component class found in {module_path}.{component_name}")
                return None
                
        except ModuleNotFoundError as e:
            logger.debug(f"Python component not found: {platform}/{component_name} - {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to load Python component {platform}/{component_name}: {e}")
            return None
    
    def _find_component_class(self, module, component_name: str) -> Optional[Type]:
        """
        在模块中查找组件类
        
        命名约定（按优先级）：
        1. 平台前缀：login.py -> ShopeeLogin（优先，因为这是实际的命名约定）
        2. 标准命名：login.py -> LoginComponent（仅在模块中定义的类）
        3. 后缀匹配：任何以 Component 或 Export 结尾的类（仅在模块中定义的类）
        
        Args:
            module: 导入的模块
            component_name: 组件名称（如 "login"）
        
        Returns:
            Type: 组件类
        """
        module_path = module.__name__
        
        # 1. 平台前缀命名（优先，因为这是当前项目的实际命名约定）
        # 例如：modules.platforms.shopee.components.login -> ShopeeLogin
        if 'platforms' in module_path:
            try:
                parts = module_path.split('.')
                platform_idx = parts.index('platforms') + 1
                if platform_idx < len(parts):
                    platform = parts[platform_idx]
                    platform_prefix = platform.capitalize()  # shopee -> Shopee
                    
                    # 从 component_name 生成可能的类名
                    # login -> Login, orders_export -> OrdersExport
                    component_class_name = ''.join(word.capitalize() for word in component_name.split('_'))
                    
                    # 尝试：ShopeeLogin
                    prefixed_name = f"{platform_prefix}{component_class_name}"
                    if hasattr(module, prefixed_name):
                        cls = getattr(module, prefixed_name)
                        if inspect.isclass(cls) and cls.__module__ == module_path:
                            logger.debug(f"Found component class by platform prefix: {prefixed_name}")
                            return cls
                    
                    # 尝试：ShopeeLoginComponent
                    prefixed_name_with_suffix = f"{platform_prefix}{component_class_name}Component"
                    if hasattr(module, prefixed_name_with_suffix):
                        cls = getattr(module, prefixed_name_with_suffix)
                        if inspect.isclass(cls) and cls.__module__ == module_path:
                            logger.debug(f"Found component class by platform prefix + suffix: {prefixed_name_with_suffix}")
                            return cls
            except (ValueError, IndexError, AttributeError):
                pass  # 降级到下一步
        
        # 2. 标准命名：snake_case -> PascalCase + Component（仅在模块中定义的类）
        class_name = ''.join(word.capitalize() for word in component_name.split('_')) + 'Component'
        if hasattr(module, class_name):
            cls = getattr(module, class_name)
            if inspect.isclass(cls) and cls.__module__ == module_path:
                logger.debug(f"Found component class by standard naming: {class_name}")
                return cls
        
        # 3. 降级：查找任何以 Component 或 Export 结尾的类（仅在模块中定义的类）
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (name.endswith('Component') or name.endswith('Export')) and obj.__module__ == module_path:
                logger.debug(f"Found component class by suffix: {name}")
                return obj
        
        return None
    
    def validate_python_component(self, component_class: Type) -> Dict[str, Any]:
        """
        v4.8.0: 验证 Python 组件类是否符合规范
        
        Python 组件必须：
        1. 有 run(page, account, params, **kwargs) 异步方法
        2. 有 platform 类属性
        3. 有 component_type 类属性
        
        Args:
            component_class: 组件类
        
        Returns:
            Dict: {
                'valid': bool,
                'errors': List[str],
                'metadata': Dict  # 如果有效，包含元数据
            }
        """
        errors = []
        metadata = {}
        
        # 检查 run 方法
        if not hasattr(component_class, 'run'):
            errors.append("Missing 'run' method")
        else:
            run_method = getattr(component_class, 'run')
            if not inspect.iscoroutinefunction(run_method):
                errors.append("'run' method must be async (async def run)")
        
        # 检查 platform 属性
        if hasattr(component_class, 'platform'):
            metadata['platform'] = getattr(component_class, 'platform')
        else:
            errors.append("Missing 'platform' class attribute")
        
        # 检查 component_type 属性
        if hasattr(component_class, 'component_type'):
            metadata['component_type'] = getattr(component_class, 'component_type')
        else:
            errors.append("Missing 'component_type' class attribute")
        
        # 可选属性
        if hasattr(component_class, 'data_domain'):
            metadata['data_domain'] = getattr(component_class, 'data_domain')
        
        if hasattr(component_class, 'description'):
            metadata['description'] = getattr(component_class, 'description')
        
        if hasattr(component_class, 'version'):
            metadata['version'] = getattr(component_class, 'version')
        else:
            metadata['version'] = '1.0.0'
        
        return {
            'valid': len(errors) == 0,
            'errors': errors,
            'metadata': metadata if len(errors) == 0 else {}
        }
    
    def list_python_components(self, platform: str = None) -> Dict[str, List[Dict[str, Any]]]:
        """
        v4.8.0: 列出所有 Python 组件
        
        Args:
            platform: 可选，指定平台
        
        Returns:
            Dict: 按平台分组的组件列表
        """
        result = {}
        
        platforms = [platform] if platform else PYTHON_COMPONENT_PLATFORMS.keys()
        
        for plat in platforms:
            if plat not in PYTHON_COMPONENT_PLATFORMS:
                continue
            
            module_path = PYTHON_COMPONENT_PLATFORMS[plat]
            components = []
            
            # 查找组件目录
            try:
                base_module = importlib.import_module(module_path)
                if hasattr(base_module, '__path__'):
                    components_dir = Path(base_module.__path__[0])
                else:
                    continue
            except Exception as e:
                logger.debug(f"Failed to import {module_path}: {e}")
                continue
            
            # 遍历目录中的 Python 文件
            for py_file in components_dir.glob('*.py'):
                if py_file.name.startswith('_'):
                    continue
                
                component_name = py_file.stem
                
                try:
                    component_class = self.load_python_component(plat, component_name)
                    if component_class:
                        validation = self.validate_python_component(component_class)
                        components.append({
                            'name': component_name,
                            'class_name': component_class.__name__,
                            'valid': validation['valid'],
                            'errors': validation['errors'],
                            'metadata': validation['metadata'],
                        })
                except Exception as e:
                    components.append({
                        'name': component_name,
                        'class_name': None,
                        'valid': False,
                        'errors': [str(e)],
                        'metadata': {},
                    })
            
            result[plat] = components
        
        return result

