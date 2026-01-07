"""
日志管理模块

提供统一的日志管理功能，支持不同级别的日志记录和格式化输出。
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime


class ColoredFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    # 定义颜色代码
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[35m',   # 紫色
        'RESET': '\033[0m'        # 重置
    }
    
    def format(self, record):
        """格式化日志记录（Windows兼容：处理UnicodeEncodeError）"""
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset_color = self.COLORS['RESET']
        
        # 格式化时间
        record.asctime = datetime.fromtimestamp(record.created).strftime('%Y-%m-%d %H:%M:%S')
        
        # 获取消息（安全处理Unicode）
        try:
            message = record.getMessage()
        except UnicodeEncodeError:
            # Windows GBK编码兼容：移除无法编码的字符
            message = str(record.msg).encode('gbk', errors='ignore').decode('gbk')
            if record.args:
                try:
                    message = message % tuple(
                        str(arg).encode('gbk', errors='ignore').decode('gbk') 
                        for arg in record.args
                    )
                except:
                    pass
        
        # 创建格式化的消息
        formatted_message = f"{log_color}[{record.levelname}]{reset_color} {record.asctime} - {record.name} - {message}"
        
        # 如果有异常信息，添加异常堆栈
        if record.exc_info:
            try:
                formatted_message += f"\n{self.formatException(record.exc_info)}"
            except UnicodeEncodeError:
                formatted_message += "\n[异常信息包含无法编码的字符，已跳过]"
        
        return formatted_message


class ERPLogger:
    """ERP系统日志管理器"""
    
    def __init__(self):
        self.loggers = {}
        self.log_dir = Path("temp/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def get_logger(self, name: str, level: str = "INFO") -> logging.Logger:
        """
        获取日志记录器
        
        Args:
            name: 日志记录器名称
            level: 日志级别
            
        Returns:
            logging.Logger: 配置好的日志记录器
        """
        if name in self.loggers:
            return self.loggers[name]
        
        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level.upper()))
        
        # 避免重复添加处理器
        if not logger.handlers:
            # 控制台处理器
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(ColoredFormatter())
            logger.addHandler(console_handler)
            
            # 文件处理器
            log_file = self.log_dir / f"{name.replace('.', '_')}.log"
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        
        # 防止日志向上传播
        logger.propagate = False
        
        self.loggers[name] = logger
        return logger
    
    def set_level(self, name: str, level: str):
        """
        设置日志级别
        
        Args:
            name: 日志记录器名称
            level: 日志级别
        """
        if name in self.loggers:
            self.loggers[name].setLevel(getattr(logging, level.upper()))
    
    def cleanup_logs(self, days: int = 7):
        """
        清理旧日志文件
        
        Args:
            days: 保留天数
        """
        import time
        current_time = time.time()
        cutoff_time = current_time - (days * 24 * 60 * 60)
        
        for log_file in self.log_dir.glob("*.log"):
            if log_file.stat().st_mtime < cutoff_time:
                try:
                    log_file.unlink()
                    print(f"已删除旧日志文件: {log_file}")
                except Exception as e:
                    print(f"删除日志文件失败 {log_file}: {e}")


# 全局日志管理器实例
_logger_manager = ERPLogger()


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """
    获取日志记录器的便捷函数
    
    Args:
        name: 日志记录器名称
        level: 日志级别
        
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    return _logger_manager.get_logger(name, level)


def set_log_level(name: str, level: str):
    """
    设置日志级别的便捷函数
    
    Args:
        name: 日志记录器名称
        level: 日志级别
    """
    _logger_manager.set_level(name, level)


def cleanup_logs(days: int = 7):
    """
    清理旧日志文件的便捷函数
    
    Args:
        days: 保留天数
    """
    _logger_manager.cleanup_logs(days) 