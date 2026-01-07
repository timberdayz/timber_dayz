"""
配置管理模块

提供统一的配置管理功能，支持YAML格式配置文件的加载、保存和验证。
"""

import yaml
import json
from pathlib import Path
from typing import Dict, Any, Optional, Union
from .exceptions import ConfigurationError
from .logger import get_logger

logger = get_logger(__name__)


def get_export_settings(platform: str = "shopee", granularity: str = "daily") -> Dict[str, bool]:
    """
    获取导出行为配置

    Args:
        platform: 平台名称（如 shopee）
        granularity: 数据粒度（daily/weekly/monthly）

    Returns:
        Dict包含 auto_regenerate 和 api_fallback 布尔值
    """
    try:
        config_manager = ConfigManager()
        config = config_manager.load_config("simple_config")

        # 默认值
        defaults = {
            "auto_regenerate": True,
            "api_fallback": False
        }

        # 平台级配置
        platform_config = config.get("platforms", {}).get(platform, {})
        export_config = platform_config.get("export", {})

        # 基础配置
        result = {
            "auto_regenerate": export_config.get("auto_regenerate", defaults["auto_regenerate"]),
            "api_fallback": export_config.get("api_fallback", defaults["api_fallback"])
        }

        # 粒度级覆盖
        granularity_overrides = export_config.get("granularity_overrides", {})
        if granularity in granularity_overrides:
            override = granularity_overrides[granularity]
            result.update({
                "auto_regenerate": override.get("auto_regenerate", result["auto_regenerate"]),
                "api_fallback": override.get("api_fallback", result["api_fallback"])
            })

        logger.debug(f"导出配置 {platform}/{granularity}: {result}")
        return result

    except Exception as e:
        logger.warning(f"读取导出配置失败，使用默认值: {e}")
        return {"auto_regenerate": True, "api_fallback": False}


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_dir: str = "config"):
        """
        初始化配置管理器
        
        Args:
            config_dir: 配置文件目录
        """
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self._configs = {}
        
        logger.info(f"配置管理器初始化，配置目录: {self.config_dir}")
    
    def load_config(self, config_name: str, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        加载配置文件
        
        Args:
            config_name: 配置名称
            config_path: 配置文件路径，如果为None则使用默认路径
            
        Returns:
            Dict[str, Any]: 配置数据
            
        Raises:
            ConfigurationError: 配置加载失败
        """
        if config_path is None:
            config_path = self.config_dir / f"{config_name}.yaml"
        else:
            config_path = Path(config_path)
        
        try:
            if not config_path.exists():
                logger.warning(f"配置文件不存在: {config_path}")
                return {}
            
            with open(config_path, 'r', encoding='utf-8') as f:
                if config_path.suffix.lower() == '.json':
                    config_data = json.load(f)
                else:
                    config_data = yaml.safe_load(f) or {}
            
            self._configs[config_name] = config_data
            logger.info(f"成功加载配置: {config_name}")
            return config_data
            
        except Exception as e:
            error_msg = f"加载配置文件失败: {e}"
            logger.error(error_msg)
            raise ConfigurationError(error_msg, config_name)
    
    def save_config(self, config_name: str, config_data: Dict[str, Any], 
                   config_path: Optional[str] = None) -> bool:
        """
        保存配置文件
        
        Args:
            config_name: 配置名称
            config_data: 配置数据
            config_path: 配置文件路径，如果为None则使用默认路径
            
        Returns:
            bool: 保存是否成功
            
        Raises:
            ConfigurationError: 配置保存失败
        """
        if config_path is None:
            config_path = self.config_dir / f"{config_name}.yaml"
        else:
            config_path = Path(config_path)
        
        try:
            # 确保目录存在
            config_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                if config_path.suffix.lower() == '.json':
                    json.dump(config_data, f, ensure_ascii=False, indent=2)
                else:
                    yaml.dump(config_data, f, default_flow_style=False, 
                             allow_unicode=True, indent=2)
            
            self._configs[config_name] = config_data
            logger.info(f"成功保存配置: {config_name}")
            return True
            
        except Exception as e:
            error_msg = f"保存配置文件失败: {e}"
            logger.error(error_msg)
            raise ConfigurationError(error_msg, config_name)
    
    def get_config(self, config_name: str) -> Dict[str, Any]:
        """
        获取配置数据
        
        Args:
            config_name: 配置名称
            
        Returns:
            Dict[str, Any]: 配置数据
        """
        if config_name not in self._configs:
            self.load_config(config_name)
        
        return self._configs.get(config_name, {})
    
    def get_config_value(self, config_name: str, key: str, default: Any = None) -> Any:
        """
        获取配置项的值
        
        Args:
            config_name: 配置名称
            key: 配置键，支持点号分隔的嵌套键
            default: 默认值
            
        Returns:
            Any: 配置值
        """
        config = self.get_config(config_name)
        
        # 支持嵌套键，如 "database.host"
        keys = key.split('.')
        value = config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            logger.debug(f"配置项不存在: {config_name}.{key}，使用默认值: {default}")
            return default
    
    def set_config_value(self, config_name: str, key: str, value: Any) -> bool:
        """
        设置配置项的值
        
        Args:
            config_name: 配置名称
            key: 配置键，支持点号分隔的嵌套键
            value: 配置值
            
        Returns:
            bool: 设置是否成功
        """
        config = self.get_config(config_name)
        
        # 支持嵌套键设置
        keys = key.split('.')
        current = config
        
        # 创建嵌套结构
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        # 设置最终值
        current[keys[-1]] = value
        
        # 保存配置
        return self.save_config(config_name, config)
    
    def validate_config(self, config_name: str, schema: Dict[str, Any]) -> bool:
        """
        验证配置数据
        
        Args:
            config_name: 配置名称
            schema: 配置模式
            
        Returns:
            bool: 验证是否通过
            
        Raises:
            ConfigurationError: 配置验证失败
        """
        config = self.get_config(config_name)
        
        try:
            self._validate_schema(config, schema)
            logger.info(f"配置验证通过: {config_name}")
            return True
        except Exception as e:
            error_msg = f"配置验证失败: {e}"
            logger.error(error_msg)
            raise ConfigurationError(error_msg, config_name)
    
    def _validate_schema(self, config: Dict[str, Any], schema: Dict[str, Any]):
        """
        递归验证配置模式
        
        Args:
            config: 配置数据
            schema: 配置模式
        """
        for key, expected_type in schema.items():
            if key not in config:
                raise ValueError(f"缺少必需配置项: {key}")
            
            if isinstance(expected_type, dict):
                if not isinstance(config[key], dict):
                    raise ValueError(f"配置项 {key} 应该是字典类型")
                self._validate_schema(config[key], expected_type)
            elif isinstance(expected_type, type):
                if not isinstance(config[key], expected_type):
                    raise ValueError(f"配置项 {key} 应该是 {expected_type.__name__} 类型")
    
    def list_configs(self) -> list:
        """
        列出所有配置文件
        
        Returns:
            list: 配置文件列表
        """
        configs = []
        for config_file in self.config_dir.glob("*.yaml"):
            configs.append(config_file.stem)
        for config_file in self.config_dir.glob("*.json"):
            configs.append(config_file.stem)
        return sorted(configs)
    
    def reload_config(self, config_name: str) -> Dict[str, Any]:
        """
        重新加载配置
        
        Args:
            config_name: 配置名称
            
        Returns:
            Dict[str, Any]: 配置数据
        """
        if config_name in self._configs:
            del self._configs[config_name]
        return self.load_config(config_name)


# 全局配置管理器实例
_config_manager = ConfigManager()


def get_config_manager() -> ConfigManager:
    """获取全局配置管理器实例"""
    return _config_manager


def load_config(config_name: str) -> Dict[str, Any]:
    """加载配置的便捷函数"""
    return _config_manager.load_config(config_name)


def save_config(config_name: str, config_data: Dict[str, Any]) -> bool:
    """保存配置的便捷函数"""
    return _config_manager.save_config(config_name, config_data)


def get_config_value(config_name: str, key: str, default: Any = None) -> Any:
    """获取配置值的便捷函数"""
    return _config_manager.get_config_value(config_name, key, default) 