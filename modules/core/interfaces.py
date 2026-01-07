"""
标准接口定义

定义系统中所有模块必须遵循的标准接口，确保模块间的一致性和可互换性。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional


class ApplicationInterface(ABC):
    """应用接口标准"""
    
    @abstractmethod
    def run(self) -> bool:
        """
        运行应用
        
        Returns:
            bool: 运行是否成功
        """
        pass
    
    @abstractmethod
    def get_info(self) -> Dict[str, Any]:
        """
        获取应用信息
        
        Returns:
            Dict[str, Any]: 包含name, version, description等信息的字典
        """
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """
        健康检查
        
        Returns:
            bool: 健康状态
        """
        pass


class HandlerInterface(ABC):
    """处理器接口标准"""
    
    @abstractmethod
    def process(self, data: Any) -> Any:
        """
        处理数据
        
        Args:
            data: 输入数据
            
        Returns:
            Any: 处理结果
        """
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """
        处理器健康检查
        
        Returns:
            bool: 健康状态
        """
        pass


class ValidatorInterface(ABC):
    """验证器接口标准"""
    
    @abstractmethod
    def validate(self, data: Any) -> bool:
        """
        验证数据
        
        Args:
            data: 待验证数据
            
        Returns:
            bool: 验证是否通过
        """
        pass


class CollectorInterface(ABC):
    """采集器接口标准"""
    
    @abstractmethod
    def collect(self, **kwargs) -> Dict[str, Any]:
        """
        执行数据采集
        
        Returns:
            Dict[str, Any]: 采集结果
        """
        pass
    
    @abstractmethod
    def test_connection(self) -> bool:
        """
        测试连接
        
        Returns:
            bool: 连接是否成功
        """
        pass


class ConfigInterface(ABC):
    """配置接口标准"""
    
    @abstractmethod
    def load_config(self, config_path: str) -> Dict[str, Any]:
        """
        加载配置
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            Dict[str, Any]: 配置数据
        """
        pass
    
    @abstractmethod
    def save_config(self, config_data: Dict[str, Any], config_path: str) -> bool:
        """
        保存配置
        
        Args:
            config_data: 配置数据
            config_path: 配置文件路径
            
        Returns:
            bool: 保存是否成功
        """
        pass 