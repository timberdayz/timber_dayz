"""
组件加载器 - Component Loader

负责加载、验证、缓存 YAML/Python 组件配置

v4.8.0: 添加 Python 组件加载支持,逐步废弃 YAML 组件
optimize-component-version-management: 添加 load_python_component_from_path
"""

import hashlib
import os
import re
import importlib
import importlib.util
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
    
    功能:
    1. 加载YAML组件配置
    2. 验证组件格式和安全性
    3. 缓存组件配置(生产模式)
    4. 参数模板替换
    """
    
    # 危险的selector模式(安全验证)
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
    
    # 支持的组件类型(Phase 7.2: 添加shop_switch, Phase 11: 添加filters)
    SUPPORTED_TYPES = ['login', 'shop_switch', 'navigation', 'date_picker', 'filters', 'export', 'verification']
    
    # Phase 11: 发现模式组件类型(使用 open_action + available_options 而非 steps)
    DISCOVERY_MODE_TYPES = ['date_picker', 'filters']
    
    # 支持的数据域
    SUPPORTED_DATA_DOMAINS = ['orders', 'products', 'services', 'analytics', 'finance', 'inventory']
    
    def __init__(self, components_dir: str = None, hot_reload: bool = None):
        """
        初始化组件加载器
        
        Args:
            components_dir: 组件目录路径(默认:config/collection_components)
            hot_reload: 是否热重载(默认:从环境变量COMPONENT_HOT_RELOAD读取)
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
        # load_python_component_from_path 缓存，key 为 file_path
        self._path_load_cache: Dict[str, Type] = {}
        
        logger.info(f"ComponentLoader initialized: dir={self.components_dir}, hot_reload={self.hot_reload}")
    
    def load(self, component_path: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        加载组件配置。迁离 YAML：仅从 Python 组件构建兼容 dict，不再读取 .yaml 文件。
        """
        # 规范化路径（去掉 .yaml 后缀若传入）
        path = component_path.replace(".yaml", "").replace(".yml", "").strip()
        parts = path.split("/", 1)
        platform = parts[0] if len(parts) >= 2 else ""
        comp_name = parts[1] if len(parts) >= 2 else path

        # 检查缓存
        if not self.hot_reload and path in self._cache:
            component = self._cache[path].copy()
            logger.debug(f"Component loaded from cache: {path}")
        else:
            component = self.build_component_dict_from_python(platform, comp_name, params or {})
            if component is None:
                raise FileNotFoundError(
                    f"Python component not found: {path} "
                    f"(expected modules/platforms/{platform}/components/{comp_name}.py)"
                )
            if not self.hot_reload:
                self._cache[path] = component.copy()
            logger.info(f"Component loaded: {path}")

        if params and "_python_component_class" not in component:
            component = self._replace_variables(component, params)
        return component
    
    def _load_from_file(self, component_path: str) -> Dict[str, Any]:
        """
        从文件加载组件
        
        Args:
            component_path: 组件路径(如 "shopee/login")
            
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
        
        Phase 11: 支持发现模式组件(date_picker, filters)
        - 发现模式:使用 open_action + available_options
        - 普通模式:使用 steps
        
        Args:
            component: 组件配置字典
            
        Raises:
            ComponentValidationError: 验证失败
        """
        component_type = component.get('type', '')
        is_discovery_mode = component_type in self.DISCOVERY_MODE_TYPES and 'open_action' in component
        
        # 1. 检查必填字段(发现模式和普通模式不同)
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
        验证发现模式组件结构(Phase 11)
        
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
        
        # Phase 12: 验证 test_config(可选但推荐)
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
            
            # 验证所有字符串字段的安全性(防止注入)
            for key, value in step.items():
                if isinstance(value, str):
                    self._validate_string_security(value, f"step {i}.{key}")
    
    def _validate_string_security(self, value: str, field_path: str) -> None:
        """
        验证字符串字段安全性(防止注入攻击)
        
        Args:
            value: 字符串值
            field_path: 字段路径(用于错误信息)
            
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
        
        支持的变量格式:{{xxx.yyy}}
        
        Args:
            component: 组件配置字典
            params: 参数字典(包含account, params, task等)
            
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
                    # 变量不存在,保持原样
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
        加载所有组件(用于预热缓存)。迁离 YAML：仅扫描 modules/platforms/*/components/*.py。
        """
        components = {}
        for platform in self.SUPPORTED_PLATFORMS:
            if platform not in PYTHON_COMPONENT_PLATFORMS:
                continue
            module_path = PYTHON_COMPONENT_PLATFORMS[platform]
            try:
                base_module = importlib.import_module(module_path)
                comp_dir = Path(base_module.__path__[0])
            except Exception as e:
                logger.debug(f"Skip platform {platform}: {e}")
                continue
            platform_components = []
            for py_file in comp_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue
                component_name = py_file.stem
                try:
                    self.load(f"{platform}/{component_name}")
                    platform_components.append(component_name)
                except Exception as e:
                    logger.error(f"Failed to load component {platform}/{component_name}: {e}")
            components[platform] = platform_components
        logger.info(f"Loaded {sum(len(v) for v in components.values())} components")
        return components
    
    def get_component_info(self, component_path: str) -> Dict[str, Any]:
        """
        获取组件元信息。迁离 YAML：基于 Python 组件类元数据。
        """
        component = self.load(component_path)
        steps = component.get("steps", [])
        return {
            "name": component.get("name"),
            "platform": component.get("platform"),
            "type": component.get("type"),
            "version": component.get("version", "1.0.0"),
            "description": component.get("description", ""),
            "author": component.get("author", ""),
            "data_domain": component.get("data_domain"),
            "step_count": len(steps) if isinstance(steps, list) else 0,
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
            platform: 平台代码(shopee/tiktok/miaoshou)
            component_name: 组件名称(login/navigation/orders_export 等)
        
        Returns:
            Type: 组件类,如果不存在则返回 None
        
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

    def _validate_component_file_path(
        self,
        abs_path: str,
        project_root: str,
        file_path: str,
        version_id: Any,
    ) -> None:
        """
        校验 file_path 解析后的绝对路径位于允许的组件目录内，拒绝路径穿越与越界。
        允许目录：modules/platforms/*/components/（相对于 PROJECT_ROOT）。
        """
        resolved = os.path.realpath(abs_path)
        root = (project_root or os.getenv("PROJECT_ROOT", "")).strip()
        if not root:
            raise ValueError(
                f"Component path security check failed: PROJECT_ROOT not set "
                f"(version_id={version_id}, file_path={file_path}). Set PROJECT_ROOT to allow loading."
            )
        allowed_base = os.path.realpath(os.path.join(root, "modules", "platforms"))
        if not resolved.startswith(allowed_base):
            raise ValueError(
                f"Component path outside allowed dir (version_id={version_id}, file_path={file_path}, "
                f"resolved={resolved}, allowed_base={allowed_base})"
            )
        if "components" not in resolved:
            raise ValueError(
                f"Component path must be under modules/platforms/*/components "
                f"(version_id={version_id}, file_path={file_path}, resolved={resolved})"
            )

    def load_python_component_from_path(
        self,
        file_path: str,
        version_id: Any = None,
        project_root: Optional[str] = None,
        platform: Optional[str] = None,
        component_type: Optional[str] = None,
    ) -> Type:
        """
        从 file_path 加载 Python 组件类。
        类发现：元数据优先（platform + component_type），再按 stem 命名兜底，兼容历史类名。

        Args:
            file_path: 相对路径(相对于 PROJECT_ROOT)或绝对路径
            version_id: 可选，用于唯一模块名，避免 sys.modules 缓存污染
            project_root: 项目根目录，若 file_path 为相对路径则拼接
            platform: 可选，用于元数据优先匹配（与 component_type 同时提供时生效）
            component_type: 可选，用于元数据优先匹配

        Returns:
            组件类

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 加载失败或安全校验失败
        """
        project_root = project_root or os.getenv("PROJECT_ROOT", "")
        if project_root and not os.path.isabs(file_path):
            abs_path = os.path.normpath(os.path.join(project_root, file_path))
        else:
            abs_path = os.path.normpath(file_path)

        if not os.path.exists(abs_path):
            raise FileNotFoundError(
                f"Component file not found: {file_path} (version_id={version_id}, "
                f"abs={abs_path})"
            )

        # P0: file_path 安全边界校验，拒绝路径穿越与越界
        self._validate_component_file_path(abs_path, project_root or "", file_path, version_id)

        cache_key = file_path
        if not self.hot_reload and cache_key in self._path_load_cache:
            return self._path_load_cache[cache_key]

        # 模块名须唯一，避免不同 file_path 使用相同模块名导致 sys.modules 污染
        unique_name = f"comp_{hashlib.sha256(abs_path.encode()).hexdigest()[:16]}"
        if version_id is not None:
            unique_name = f"{unique_name}_v{version_id}"

        spec = importlib.util.spec_from_file_location(unique_name, abs_path)
        if not spec or not spec.loader:
            raise ValueError(
                f"Failed to create spec for {file_path} (version_id={version_id})"
            )
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            raise ValueError(
                f"Failed to load component from {file_path}: {e} "
                f"(version_id={version_id})"
            ) from e

        stem = Path(abs_path).stem
        component_name_from_stem = self._stem_to_component_name(stem)
        component_class = None
        if platform is not None and component_type is not None:
            component_class = self._find_component_class_by_metadata(
                module, platform, component_type
            )
        if component_class is None:
            component_class = self._find_component_class(
                module, component_name_from_stem
            )
        if not component_class:
            candidates = [
                name
                for name, obj in inspect.getmembers(module, inspect.isclass)
                if obj.__module__ == module.__name__
            ]
            raise ValueError(
                f"No component class found in {file_path} (version_id={version_id}). "
                f"Match rule: metadata (platform={platform!r}, component_type={component_type!r}) first, "
                f"then naming fallback (stem={stem!r} -> component_name={component_name_from_stem!r}). "
                f"Candidate classes in module: {candidates!r}"
            )

        if not self.hot_reload:
            self._path_load_cache[cache_key] = component_class
        return component_class

    def _stem_to_component_name(self, stem: str) -> str:
        """从文件名 stem 推导 component_name，兼容 versioned 命名如 login_v1_0_0 -> login."""
        base = stem.replace("-", "_")
        match = re.match(r"^(.+)_v\d+_\d+_\d+$", base)
        if match:
            return match.group(1)
        return base

    def _find_component_class_by_metadata(
        self, module: Any, platform: str, component_type: str
    ) -> Optional[Type]:
        """在模块中按 platform + component_type 查找组件类（元数据优先）。"""
        module_path = getattr(module, "__name__", "")
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module_path:
                continue
            if getattr(obj, "platform", None) == platform and getattr(
                obj, "component_type", None
            ) == component_type:
                logger.debug(
                    "Found component class by metadata: %s (platform=%s, component_type=%s)",
                    name,
                    platform,
                    component_type,
                )
                return obj
        return None

    def _find_component_class_from_module(self, module, stem: str) -> Optional[Type]:
        """在模块中查找组件类（基于 stem 推断）"""
        component_name = self._stem_to_component_name(stem.replace("-", "_"))
        return self._find_component_class(module, component_name)

    def build_component_dict_from_python(
        self, platform: str, component_name: str, params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        为执行器构建兼容的组件字典：从 Python 类加载并返回含 _python_component_class 的 dict。
        供 executor_v2 在仅使用 Python 组件时使用，不再依赖 YAML 步骤。
        """
        Klass = self.load_python_component(platform, component_name)
        if not Klass:
            return None
        comp_type = getattr(
            Klass, "component_type", "export" if "export" in component_name else "login"
        )
        plat = getattr(Klass, "platform", platform)
        return {
            "name": component_name,
            "platform": plat,
            "type": comp_type,
            "data_domain": getattr(Klass, "data_domain", None),
            "_params": params or {},
            "_python_component_class": Klass,
        }

    def _find_component_class(self, module, component_name: str) -> Optional[Type]:
        """
        在模块中查找组件类
        
        命名约定(按优先级):
        1. 平台前缀:login.py -> ShopeeLogin(优先,因为这是实际的命名约定)
        2. 标准命名:login.py -> LoginComponent(仅在模块中定义的类)
        3. 后缀匹配:任何以 Component 或 Export 结尾的类(仅在模块中定义的类)
        
        Args:
            module: 导入的模块
            component_name: 组件名称(如 "login")
        
        Returns:
            Type: 组件类
        """
        module_path = module.__name__
        
        # 1. 平台前缀命名(优先,因为这是当前项目的实际命名约定)
        # 例如:modules.platforms.shopee.components.login -> ShopeeLogin
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
                    
                    # 尝试:ShopeeLogin
                    prefixed_name = f"{platform_prefix}{component_class_name}"
                    if hasattr(module, prefixed_name):
                        cls = getattr(module, prefixed_name)
                        if inspect.isclass(cls) and cls.__module__ == module_path:
                            logger.debug(f"Found component class by platform prefix: {prefixed_name}")
                            return cls
                    
                    # 尝试:ShopeeLoginComponent
                    prefixed_name_with_suffix = f"{platform_prefix}{component_class_name}Component"
                    if hasattr(module, prefixed_name_with_suffix):
                        cls = getattr(module, prefixed_name_with_suffix)
                        if inspect.isclass(cls) and cls.__module__ == module_path:
                            logger.debug(f"Found component class by platform prefix + suffix: {prefixed_name_with_suffix}")
                            return cls
            except (ValueError, IndexError, AttributeError):
                pass  # 降级到下一步
        
        # 2. 标准命名:snake_case -> PascalCase + Component(仅在模块中定义的类)
        class_name = ''.join(word.capitalize() for word in component_name.split('_')) + 'Component'
        if hasattr(module, class_name):
            cls = getattr(module, class_name)
            if inspect.isclass(cls) and cls.__module__ == module_path:
                logger.debug(f"Found component class by standard naming: {class_name}")
                return cls
        
        # 3. 降级:查找任何以 Component 或 Export 结尾的类(仅在模块中定义的类)
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (name.endswith('Component') or name.endswith('Export')) and obj.__module__ == module_path:
                logger.debug(f"Found component class by suffix: {name}")
                return obj
        
        return None
    
    def validate_python_component(self, component_class: Type) -> Dict[str, Any]:
        """
        v4.8.0: 验证 Python 组件类是否符合规范
        
        Python 组件必须:
        1. 有 run(page, account, params, **kwargs) 异步方法
        2. 有 platform 类属性
        3. 有 component_type 类属性
        
        Args:
            component_class: 组件类
        
        Returns:
            Dict: {
                'valid': bool,
                'errors': List[str],
                'metadata': Dict  # 如果有效,包含元数据
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
            platform: 可选,指定平台
        
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

