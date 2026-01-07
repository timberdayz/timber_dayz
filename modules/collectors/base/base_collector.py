#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
统一基础采集器接口
定义所有平台采集器必须实现的标准方法
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import json


class CollectionStatus(Enum):
    """采集状态"""
    IDLE = "idle"                  # 空闲
    LOGGING_IN = "logging_in"      # 登录中
    LOGGED_IN = "logged_in"        # 已登录
    COLLECTING = "collecting"      # 采集中
    COMPLETED = "completed"        # 完成
    FAILED = "failed"              # 失败
    RETRYING = "retrying"          # 重试中


class DataType(Enum):
    """数据类型"""
    ORDERS = "orders"              # 订单数据
    PRODUCTS = "products"          # 商品数据
    SALES = "sales"                # 销售数据
    CUSTOMERS = "customers"        # 客户数据
    INVENTORY = "inventory"        # 库存数据
    FINANCE = "finance"            # 财务数据
    ANALYTICS = "analytics"        # 分析数据


@dataclass
class CollectionConfig:
    """采集配置"""
    platform: str
    account_id: str
    data_types: List[DataType] = field(default_factory=list)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    max_retries: int = 3
    retry_delay: int = 30
    timeout: int = 300
    headless: bool = True
    use_proxy: bool = False
    proxy_config: Optional[Dict[str, Any]] = None
    custom_headers: Optional[Dict[str, str]] = None
    screenshot_on_error: bool = True
    save_raw_data: bool = True
    data_format: str = "json"  # json, csv, excel


@dataclass
class CollectionResult:
    """采集结果"""
    success: bool
    platform: str
    account_id: str
    data_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration: Optional[float] = None
    data_count: int = 0
    raw_data: Optional[Dict[str, Any]] = None
    processed_data: Optional[Dict[str, Any]] = None
    downloaded_files: List[str] = field(default_factory=list)
    screenshots: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LoginResult:
    """登录结果"""
    success: bool
    platform: str
    account_id: str
    login_time: datetime
    session_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    requires_2fa: bool = False
    captcha_required: bool = False


class BaseCollector(ABC):
    """基础采集器抽象类"""
    
    # 类属性
    PLATFORM_NAME: str = "unknown"
    SUPPORTED_DATA_TYPES: List[DataType] = []
    REQUIRES_LOGIN: bool = True
    SUPPORTS_SESSION_PERSISTENCE: bool = False
    MAX_CONCURRENT_REQUESTS: int = 1
    
    def __init__(self, platform: str, account_id: str, config: Optional[CollectionConfig] = None):
        """
        初始化基础采集器
        
        Args:
            platform: 平台名称
            account_id: 账号ID
            config: 采集配置
        """
        self.platform = platform
        self.account_id = account_id
        self.config = config or self._create_default_config()
        
        # 设置日志
        self.logger = self._setup_logger()
        
        # 状态管理
        self.status = CollectionStatus.IDLE
        self.is_logged_in = False
        self.session_data = {}
        self.login_time = None
        
        # 文件管理
        self.downloads_path = Path(f"temp/outputs/{platform}_{account_id}")
        self.screenshot_dir = Path(f"temp/media/screenshots/{platform}_{account_id}")
        self.session_dir = Path(f"temp/sessions/{platform}_{account_id}")
        
        # 创建必要目录
        for path in [self.downloads_path, self.screenshot_dir, self.session_dir]:
            path.mkdir(parents=True, exist_ok=True)
        
        # 统计信息
        self.stats = {
            'total_collections': 0,
            'successful_collections': 0,
            'failed_collections': 0,
            'total_data_count': 0,
            'last_collection_time': None
        }
        
        # 初始化采集器
        self._initialize_collector()
    
    def _setup_logger(self) -> logging.Logger:
        """设置日志记录器"""
        logger = logging.getLogger(f"{self.__class__.__name__}_{self.account_id}")
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            # 控制台处理器
            console_handler = logging.StreamHandler()
            console_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
            
            # 文件处理器
            log_file = self.session_dir / f"collection_{datetime.now().strftime('%Y%m%d')}.log"
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setFormatter(console_formatter)
            logger.addHandler(file_handler)
        
        return logger
    
    def _create_default_config(self) -> CollectionConfig:
        """创建默认配置"""
        return CollectionConfig(
            platform=self.platform,
            account_id=self.account_id,
            data_types=self.SUPPORTED_DATA_TYPES,
            start_date=datetime.now() - timedelta(days=30),
            end_date=datetime.now()
        )
    
    def _initialize_collector(self):
        """初始化采集器"""
        try:
            self.logger.info(f"初始化采集器: {self.platform} - {self.account_id}")
            
            # 加载会话数据
            if self.SUPPORTS_SESSION_PERSISTENCE:
                self._load_session()
            
            # 子类特定的初始化
            self._custom_initialization()
            
            self.logger.info("采集器初始化完成")
            
        except Exception as e:
            self.logger.error(f"采集器初始化失败: {e}")
            raise
    
    def _custom_initialization(self):
        """子类特定的初始化（可选实现）"""
        pass
    
    @abstractmethod
    def login(self, username: str, password: str, **kwargs) -> LoginResult:
        """
        登录平台
        
        Args:
            username: 用户名
            password: 密码
            **kwargs: 其他登录参数
            
        Returns:
            LoginResult: 登录结果
        """
        pass
    
    @abstractmethod
    def collect_data(self, data_type: str, **kwargs) -> CollectionResult:
        """
        采集数据
        
        Args:
            data_type: 数据类型
            **kwargs: 其他采集参数
            
        Returns:
            CollectionResult: 采集结果
        """
        pass
    
    @abstractmethod
    def check_login_status(self) -> bool:
        """
        检查登录状态
        
        Returns:
            bool: 是否已登录
        """
        pass
    
    def logout(self) -> bool:
        """
        登出平台
        
        Returns:
            bool: 是否成功登出
        """
        try:
            self.logger.info("登出平台")
            
            # 子类特定的登出逻辑
            logout_success = self._custom_logout()
            
            if logout_success:
                self.is_logged_in = False
                self.session_data = {}
                self.login_time = None
                self.status = CollectionStatus.IDLE
                
                # 保存会话数据
                if self.SUPPORTS_SESSION_PERSISTENCE:
                    self._save_session()
                
                self.logger.info("登出成功")
                return True
            else:
                self.logger.warning("登出失败")
                return False
                
        except Exception as e:
            self.logger.error(f"登出异常: {e}")
            return False
    
    def _custom_logout(self) -> bool:
        """子类特定的登出逻辑（可选实现）"""
        return True
    
    def collect_all_data(self, data_types: Optional[List[str]] = None) -> List[CollectionResult]:
        """
        采集所有支持的数据类型
        
        Args:
            data_types: 指定要采集的数据类型，如果为None则采集所有支持的类型
            
        Returns:
            List[CollectionResult]: 采集结果列表
        """
        if data_types is None:
            data_types = [dt.value for dt in self.SUPPORTED_DATA_TYPES]
        
        results = []
        
        for data_type in data_types:
            try:
                self.logger.info(f"开始采集数据类型: {data_type}")
                
                result = self.collect_data(data_type)
                results.append(result)
                
                # 更新统计信息
                self._update_stats(result)
                
                if result.success:
                    self.logger.info(f"数据类型 {data_type} 采集成功，共 {result.data_count} 条数据")
                else:
                    self.logger.error(f"数据类型 {data_type} 采集失败: {result.error_message}")
                
            except Exception as e:
                self.logger.error(f"采集数据类型 {data_type} 时发生异常: {e}")
                
                # 创建失败结果
                failed_result = CollectionResult(
                    success=False,
                    platform=self.platform,
                    account_id=self.account_id,
                    data_type=data_type,
                    start_time=datetime.now(),
                    error_message=str(e)
                )
                results.append(failed_result)
        
        return results
    
    def _update_stats(self, result: CollectionResult):
        """更新统计信息"""
        self.stats['total_collections'] += 1
        
        if result.success:
            self.stats['successful_collections'] += 1
            self.stats['total_data_count'] += result.data_count
        else:
            self.stats['failed_collections'] += 1
        
        self.stats['last_collection_time'] = datetime.now()
    
    def take_screenshot(self, name: str = None) -> Optional[str]:
        """
        截图
        
        Args:
            name: 截图名称
            
        Returns:
            Optional[str]: 截图文件路径
        """
        try:
            if name is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                name = f"screenshot_{timestamp}"
            
            screenshot_path = self.screenshot_dir / f"{name}.png"
            
            # 子类实现具体的截图逻辑
            if self._take_screenshot_impl(screenshot_path):
                self.logger.info(f"截图已保存: {screenshot_path}")
                return str(screenshot_path)
            else:
                self.logger.warning("截图失败")
                return None
                
        except Exception as e:
            self.logger.error(f"截图异常: {e}")
            return None
    
    def _take_screenshot_impl(self, file_path: Path) -> bool:
        """
        实现截图逻辑（子类必须实现）
        
        Args:
            file_path: 截图文件路径
            
        Returns:
            bool: 是否成功截图
        """
        raise NotImplementedError("子类必须实现截图逻辑")
    
    def save_raw_data(self, data: Dict[str, Any], data_type: str) -> str:
        """
        保存原始数据
        
        Args:
            data: 要保存的数据
            data_type: 数据类型
            
        Returns:
            str: 保存的文件路径
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{data_type}_{timestamp}.json"
            file_path = self.downloads_path / filename
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            
            self.logger.info(f"原始数据已保存: {file_path}")
            return str(file_path)
            
        except Exception as e:
            self.logger.error(f"保存原始数据失败: {e}")
            return ""
    
    def _load_session(self):
        """加载会话数据"""
        try:
            session_file = self.session_dir / "session.json"
            if session_file.exists():
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                
                # 检查会话是否过期
                if self._is_session_valid(session_data):
                    self.session_data = session_data
                    self.is_logged_in = True
                    self.login_time = datetime.fromisoformat(session_data.get('login_time', ''))
                    self.logger.info("会话数据加载成功")
                else:
                    self.logger.info("会话数据已过期")
                    
        except Exception as e:
            self.logger.warning(f"加载会话数据失败: {e}")
    
    def _save_session(self):
        """保存会话数据"""
        try:
            session_file = self.session_dir / "session.json"
            
            session_data = {
                'platform': self.platform,
                'account_id': self.account_id,
                'login_time': self.login_time.isoformat() if self.login_time else None,
                'session_data': self.session_data,
                'save_time': datetime.now().isoformat()
            }
            
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2, default=str)
            
            self.logger.info("会话数据已保存")
            
        except Exception as e:
            self.logger.error(f"保存会话数据失败: {e}")
    
    def _is_session_valid(self, session_data: Dict[str, Any]) -> bool:
        """
        检查会话是否有效
        
        Args:
            session_data: 会话数据
            
        Returns:
            bool: 会话是否有效
        """
        try:
            # 检查登录时间
            login_time_str = session_data.get('login_time')
            if not login_time_str:
                return False
            
            login_time = datetime.fromisoformat(login_time_str)
            session_age = datetime.now() - login_time
            
            # 默认会话有效期为24小时
            max_session_age = timedelta(hours=24)
            
            return session_age < max_session_age
            
        except Exception as e:
            self.logger.warning(f"检查会话有效性失败: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """获取采集器状态"""
        return {
            'platform': self.platform,
            'account_id': self.account_id,
            'status': self.status.value,
            'is_logged_in': self.is_logged_in,
            'login_time': self.login_time.isoformat() if self.login_time else None,
            'stats': self.stats,
            'supported_data_types': [dt.value for dt in self.SUPPORTED_DATA_TYPES],
            'session_persistence': self.SUPPORTS_SESSION_PERSISTENCE
        }
    
    def get_collection_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """获取采集历史"""
        try:
            history_file = self.session_dir / "collection_history.json"
            if not history_file.exists():
                return []
            
            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
            
            # 过滤指定天数内的记录
            cutoff_time = datetime.now() - timedelta(days=days)
            filtered_history = []
            
            for record in history:
                try:
                    record_time = datetime.fromisoformat(record.get('timestamp', ''))
                    if record_time >= cutoff_time:
                        filtered_history.append(record)
                except:
                    continue
            
            return filtered_history
            
        except Exception as e:
            self.logger.error(f"获取采集历史失败: {e}")
            return []
    
    def add_collection_record(self, result: CollectionResult):
        """添加采集记录到历史"""
        try:
            history_file = self.session_dir / "collection_history.json"
            
            # 读取现有历史
            history = []
            if history_file.exists():
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            
            # 添加新记录
            record = {
                'timestamp': datetime.now().isoformat(),
                'data_type': result.data_type,
                'success': result.success,
                'data_count': result.data_count,
                'duration': result.duration,
                'error_message': result.error_message
            }
            
            history.append(record)
            
            # 保持历史记录数量在合理范围内
            if len(history) > 1000:
                history = history[-1000:]
            
            # 保存历史
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2, default=str)
            
        except Exception as e:
            self.logger.error(f"添加采集记录失败: {e}")
    
    def cleanup_old_files(self, days: int = 7):
        """清理旧文件"""
        try:
            cutoff_time = datetime.now() - timedelta(days=days)
            
            # 清理截图
            for screenshot_file in self.screenshot_dir.glob("*.png"):
                if screenshot_file.stat().st_mtime < cutoff_time.timestamp():
                    screenshot_file.unlink()
            
            # 清理下载文件
            for download_file in self.downloads_path.glob("*"):
                if download_file.stat().st_mtime < cutoff_time.timestamp():
                    download_file.unlink()
            
            self.logger.info(f"清理了 {days} 天前的旧文件")
            
        except Exception as e:
            self.logger.error(f"清理旧文件失败: {e}")
    
    def export_collection_report(self, output_path: str = None) -> str:
        """导出采集报告"""
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"temp/outputs/collection_report_{self.platform}_{self.account_id}_{timestamp}.json"
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        report = {
            'export_time': datetime.now().isoformat(),
            'collector_status': self.get_status(),
            'collection_history': self.get_collection_history(30),
            'statistics': self.stats
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        
        self.logger.info(f"采集报告已导出到: {output_file}")
        return str(output_file)
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        try:
            self.logout()
        except:
            pass 