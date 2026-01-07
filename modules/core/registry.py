"""
应用注册器

提供应用模块的注册、发现和管理功能，实现插件化架构。
"""

from typing import Dict, List, Type, Optional, Any
from pathlib import Path
import importlib
import inspect
from .base_app import BaseApplication
from .logger import get_logger
from .exceptions import ERPException
import sys

logger = get_logger(__name__)


class ApplicationRegistry:
    """应用注册器"""
    
    def __init__(self):
        """初始化注册器"""
        self._applications: Dict[str, Type[BaseApplication]] = {}
        self._instances: Dict[str, BaseApplication] = {}
        self._metadata: Dict[str, Dict[str, Any]] = {}
        
        logger.info("应用注册器初始化完成")
    
    def register_application(self, app_class: Type[BaseApplication], 
                           app_id: Optional[str] = None) -> str:
        """
        注册应用类
        
        Args:
            app_class: 应用类
            app_id: 应用ID，如果为None则使用类名
            
        Returns:
            str: 应用ID
            
        Raises:
            ERPException: 注册失败
        """
        if not issubclass(app_class, BaseApplication):
            raise ERPException(f"应用类必须继承BaseApplication: {app_class}")
        
        if app_id is None:
            app_id = app_class.__name__
        
        if app_id in self._applications:
            logger.warning(f"应用 {app_id} 已存在，将被覆盖")
        
        self._applications[app_id] = app_class
        
        # 获取应用元数据 - 优先读取类级元数据，避免实例化副作用
        try:
            # 方法1: 尝试读取类级 METADATA 字典
            if hasattr(app_class, 'METADATA') and isinstance(app_class.METADATA, dict):
                metadata = app_class.METADATA.copy()
                metadata.update({
                    "class_name": app_class.__name__,
                    "module": app_class.__module__
                })
                self._metadata[app_id] = metadata
                logger.debug(f"使用类级 METADATA 获取应用信息: {app_id}")

            # 方法2: 尝试读取类级常量 NAME/VERSION/DESCRIPTION
            elif (hasattr(app_class, 'NAME') and hasattr(app_class, 'VERSION')
                  and hasattr(app_class, 'DESCRIPTION')):
                self._metadata[app_id] = {
                    "name": app_class.NAME,
                    "version": app_class.VERSION,
                    "description": app_class.DESCRIPTION,
                    "class_name": app_class.__name__,
                    "module": app_class.__module__
                }
                logger.debug(f"使用类级常量获取应用信息: {app_id}")

            # 方法3: 降级 - 仅在前两种方法都不可用时才实例化
            else:
                logger.warning(f"应用 {app_id} 缺少类级元数据，降级为实例化获取")
                temp_instance = app_class()
                self._metadata[app_id] = temp_instance.get_info()
                del temp_instance

        except Exception as e:
            logger.warning(f"获取应用 {app_id} 元数据失败: {e}")
            # 安全降级：使用占位元数据，不影响其他模块加载
            self._metadata[app_id] = {
                "name": app_id,
                "version": "unknown",
                "description": "元数据获取失败",
                "class_name": app_class.__name__,
                "module": app_class.__module__,
                "error": str(e)
            }
        
        logger.info(f"注册应用: {app_id}")
        return app_id
    
    def unregister_application(self, app_id: str) -> bool:
        """
        取消注册应用
        
        Args:
            app_id: 应用ID
            
        Returns:
            bool: 是否成功
        """
        if app_id not in self._applications:
            logger.warning(f"应用 {app_id} 未注册")
            return False
        
        # 停止并移除实例
        if app_id in self._instances:
            try:
                self._instances[app_id].stop()
            except Exception as e:
                logger.error(f"停止应用实例失败 {app_id}: {e}")
            del self._instances[app_id]
        
        # 移除注册信息
        del self._applications[app_id]
        if app_id in self._metadata:
            del self._metadata[app_id]
        
        logger.info(f"取消注册应用: {app_id}")
        return True
    
    def get_application(self, app_id: str) -> Optional[BaseApplication]:
        """
        获取应用实例
        
        Args:
            app_id: 应用ID
            
        Returns:
            Optional[BaseApplication]: 应用实例，不存在返回None
        """
        if app_id not in self._applications:
            logger.error(f"应用 {app_id} 未注册")
            return None
        
        # 如果实例不存在，创建新实例
        if app_id not in self._instances:
            try:
                app_class = self._applications[app_id]
                self._instances[app_id] = app_class()
                logger.info(f"创建应用实例: {app_id}")
            except Exception as e:
                logger.error(f"创建应用实例失败 {app_id}: {e}")
                return None
        
        return self._instances[app_id]
    
    def list_applications(self) -> List[str]:
        """
        列出所有注册的应用
        
        Returns:
            List[str]: 应用ID列表
        """
        return list(self._applications.keys())
    
    def get_application_info(self, app_id: str) -> Optional[Dict[str, Any]]:
        """
        获取应用信息
        
        Args:
            app_id: 应用ID
            
        Returns:
            Optional[Dict[str, Any]]: 应用信息，不存在返回None
        """
        return self._metadata.get(app_id)
    
    def get_all_applications_info(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有应用信息
        
        Returns:
            Dict[str, Dict[str, Any]]: 所有应用信息
        """
        return self._metadata.copy()
    
    def discover_applications(self, module_path: str = "modules.apps") -> int:
        """
        自动发现并注册应用
        
        Args:
            module_path: 模块路径
            
        Returns:
            int: 发现的应用数量
        """
        discovered_count = 0
        
        try:
            # 获取应用模块目录
            apps_path = Path(__file__).parent.parent / "apps"
            
            if not apps_path.exists():
                logger.warning(f"应用目录不存在: {apps_path}")
                return 0
            
            # 遍历应用目录
            for app_dir in apps_path.iterdir():
                if not app_dir.is_dir() or app_dir.name.startswith('_'):
                    continue
                
                app_module_path = f"{module_path}.{app_dir.name}"
                
                try:
                    # 尝试导入应用模块
                    app_module = importlib.import_module(app_module_path)
                    
                    # 查找应用类
                    for name, obj in inspect.getmembers(app_module):
                        if (inspect.isclass(obj) and 
                            issubclass(obj, BaseApplication) and 
                            obj != BaseApplication):
                            
                            app_id = app_dir.name
                            self.register_application(obj, app_id)
                            discovered_count += 1
                            break
                    
                except Exception as e:
                    logger.warning(f"导入应用模块失败 {app_module_path}: {e}")
            
            logger.info(f"自动发现应用: {discovered_count} 个")
            
        except Exception as e:
            logger.error(f"应用发现失败: {e}")
        
        return discovered_count
    
    def start_application(self, app_id: str) -> bool:
        """
        启动应用
        
        Args:
            app_id: 应用ID
            
        Returns:
            bool: 启动是否成功
        """
        app = self.get_application(app_id)
        if app is None:
            return False
        
        try:
            return app.start()
        except Exception as e:
            logger.error(f"启动应用失败 {app_id}: {e}")
            return False
    
    def stop_application(self, app_id: str) -> bool:
        """
        停止应用
        
        Args:
            app_id: 应用ID
            
        Returns:
            bool: 停止是否成功
        """
        if app_id not in self._instances:
            logger.warning(f"应用实例不存在: {app_id}")
            return True
        
        try:
            return self._instances[app_id].stop()
        except Exception as e:
            logger.error(f"停止应用失败 {app_id}: {e}")
            return False
    
    def health_check_all(self) -> Dict[str, bool]:
        """
        检查所有应用的健康状态
        
        Returns:
            Dict[str, bool]: 应用健康状态映射
        """
        health_status = {}
        
        for app_id in self._applications:
            try:
                app = self.get_application(app_id)
                if app:
                    health_status[app_id] = app.health_check()
                else:
                    health_status[app_id] = False
            except Exception as e:
                logger.error(f"健康检查失败 {app_id}: {e}")
                health_status[app_id] = False
        
        return health_status
    
    def reload_application(self, app_id: str) -> bool:
        """
        重新加载应用
        
        Args:
            app_id: 应用ID
            
        Returns:
            bool: 重新加载是否成功
        """
        if app_id not in self._applications:
            logger.error(f"应用 {app_id} 未注册")
            return False
        
        try:
            # 停止现有实例
            if app_id in self._instances:
                self._instances[app_id].stop()
                del self._instances[app_id]
            
            # 重新导入模块
            app_class = self._applications[app_id]
            module_name = app_class.__module__
            
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
            
            # 重新创建实例
            self._instances[app_id] = app_class()
            
            logger.info(f"重新加载应用成功: {app_id}")
            return True
            
        except Exception as e:
            logger.error(f"重新加载应用失败 {app_id}: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取注册器统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        return {
            "total_applications": len(self._applications),
            "running_instances": len(self._instances),
            "applications": list(self._applications.keys()),
            "running_apps": [app_id for app_id, app in self._instances.items() if app.is_running()]
        }


# 全局应用注册器实例
_registry = ApplicationRegistry()


def get_registry() -> ApplicationRegistry:
    """获取全局应用注册器实例"""
    return _registry


def register_application(app_class: Type[BaseApplication], app_id: Optional[str] = None) -> str:
    """注册应用的便捷函数"""
    return _registry.register_application(app_class, app_id)


def get_application(app_id: str) -> Optional[BaseApplication]:
    """获取应用实例的便捷函数"""
    return _registry.get_application(app_id)


def discover_applications() -> int:
    """自动发现应用的便捷函数"""
    return _registry.discover_applications() 