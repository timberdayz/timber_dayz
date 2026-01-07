"""
应用基类

定义所有应用模块的基础类，提供统一的接口和通用功能。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from .interfaces import ApplicationInterface
from .logger import get_logger
from .exceptions import ERPException


class BaseApplication(ApplicationInterface):
    """应用基类"""
    
    def __init__(self):
        """初始化基类"""
        self.name = "未命名应用"
        self.version = "1.0.0"
        self.description = "应用描述"
        self.logger = get_logger(self.__class__.__name__)
        self._is_running = False
        self._startup_time = None
        
        self.logger.debug(f"初始化应用: {self.name}")
    
    @abstractmethod
    def run(self) -> bool:
        """
        运行应用主逻辑
        
        子类必须实现此方法来定义具体的应用逻辑
        
        Returns:
            bool: 运行是否成功
        """
        pass
    
    def get_info(self) -> Dict[str, Any]:
        """
        获取应用信息
        
        Returns:
            Dict[str, Any]: 应用信息字典
        """
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "class_name": self.__class__.__name__,
            "module": self.__class__.__module__,
            "is_running": self._is_running,
            "startup_time": self._startup_time
        }
    
    def health_check(self) -> bool:
        """
        健康检查
        
        默认实现检查基本状态，子类可重写以添加特定检查
        
        Returns:
            bool: 健康状态
        """
        try:
            # 基础健康检查
            info = self.get_info()
            
            # 检查必要字段
            required_fields = ["name", "version", "description"]
            for field in required_fields:
                if not info.get(field):
                    self.logger.warning(f"健康检查失败: 缺少字段 {field}")
                    return False
            
            # 子类可以重写这个方法添加更多检查
            return self._custom_health_check()
            
        except Exception as e:
            self.logger.error(f"健康检查异常: {e}")
            return False
    
    def _custom_health_check(self) -> bool:
        """
        自定义健康检查
        
        子类可重写此方法实现特定的健康检查逻辑
        
        Returns:
            bool: 健康状态
        """
        return True
    
    def start(self) -> bool:
        """
        启动应用
        
        Returns:
            bool: 启动是否成功
        """
        try:
            if self._is_running:
                self.logger.warning(f"应用 {self.name} 已在运行中")
                return True
            
            self.logger.info(f"启动应用: {self.name}")
            
            # 执行启动前检查
            if not self._pre_start_check():
                self.logger.error("启动前检查失败")
                return False
            
            # 设置状态
            self._is_running = True
            import time
            self._startup_time = time.time()
            
            # 运行应用主逻辑
            result = self.run()
            
            if result:
                self.logger.info(f"应用 {self.name} 启动成功")
            else:
                self.logger.error(f"应用 {self.name} 启动失败")
                self._is_running = False
            
            return result
            
        except Exception as e:
            self.logger.error(f"应用启动异常: {e}")
            self._is_running = False
            return False
    
    def stop(self) -> bool:
        """
        停止应用
        
        Returns:
            bool: 停止是否成功
        """
        try:
            if not self._is_running:
                self.logger.warning(f"应用 {self.name} 未在运行")
                return True
            
            self.logger.info(f"停止应用: {self.name}")
            
            # 执行停止前清理
            self._pre_stop_cleanup()
            
            # 设置状态
            self._is_running = False
            self._startup_time = None
            
            self.logger.info(f"应用 {self.name} 已停止")
            return True
            
        except Exception as e:
            self.logger.error(f"应用停止异常: {e}")
            return False
    
    def restart(self) -> bool:
        """
        重启应用
        
        Returns:
            bool: 重启是否成功
        """
        self.logger.info(f"重启应用: {self.name}")
        
        if not self.stop():
            self.logger.error("应用停止失败，无法重启")
            return False
        
        return self.start()
    
    def _pre_start_check(self) -> bool:
        """
        启动前检查
        
        子类可重写此方法实现特定的启动前检查
        
        Returns:
            bool: 检查是否通过
        """
        return True
    
    def _pre_stop_cleanup(self):
        """
        停止前清理
        
        子类可重写此方法实现特定的清理逻辑
        """
        pass
    
    def is_running(self) -> bool:
        """
        检查应用是否在运行
        
        Returns:
            bool: 运行状态
        """
        return self._is_running
    
    def get_uptime(self) -> Optional[float]:
        """
        获取应用运行时长（秒）
        
        Returns:
            Optional[float]: 运行时长，未运行返回None
        """
        if self._startup_time and self._is_running:
            import time
            return time.time() - self._startup_time
        return None
    
    def show_menu(self):
        """
        显示应用菜单
        
        默认实现显示基本信息，子类可重写实现自定义菜单
        """
        print(f"\n{'='*50}")
        print(f"🎯 {self.name} v{self.version}")
        print(f"{'='*50}")
        print(f"📋 {self.description}")
        print(f"🟢 状态: {'运行中' if self._is_running else '未运行'}")
        
        if self._is_running and self._startup_time:
            uptime = self.get_uptime()
            if uptime:
                print(f"⏱️  运行时长: {uptime:.1f}秒")
        
        print(f"{'='*50}")
        
        # 子类可以重写_show_custom_menu来添加自定义菜单项
        self._show_custom_menu()
    
    def _show_custom_menu(self):
        """
        显示自定义菜单
        
        子类可重写此方法添加特定的菜单项
        """
        print("请选择操作:")
        print("1. 查看应用信息")
        print("2. 健康检查")
        print("0. 返回上级菜单")
        
        choice = input("\n请输入选择: ").strip()
        
        if choice == "1":
            self._show_app_info()
        elif choice == "2":
            self._show_health_status()
        elif choice == "0":
            return
        else:
            print("❌ 无效选择")
        
        input("\n按回车键继续...")
    
    def _show_app_info(self):
        """显示应用详细信息"""
        info = self.get_info()
        print(f"\n📋 应用详细信息:")
        print(f"   名称: {info['name']}")
        print(f"   版本: {info['version']}")
        print(f"   描述: {info['description']}")
        print(f"   类名: {info['class_name']}")
        print(f"   模块: {info['module']}")
        print(f"   状态: {'运行中' if info['is_running'] else '未运行'}")
        
        if info['startup_time']:
            import time
            startup_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(info['startup_time']))
            print(f"   启动时间: {startup_str}")
    
    def _show_health_status(self):
        """显示健康状态"""
        print(f"\n🔍 执行健康检查...")
        
        try:
            is_healthy = self.health_check()
            if is_healthy:
                print("✅ 应用状态健康")
            else:
                print("❌ 应用状态异常")
        except Exception as e:
            print(f"❌ 健康检查失败: {e}")
    
    def __str__(self) -> str:
        """字符串表示"""
        return f"{self.name} v{self.version}"
    
    def __repr__(self) -> str:
        """调试字符串表示"""
        return f"<{self.__class__.__name__}(name='{self.name}', version='{self.version}', running={self._is_running})>" 