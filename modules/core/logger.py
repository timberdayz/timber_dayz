"""
统一日志管理模块。
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path


class ColoredFormatter(logging.Formatter):
    """支持按环境变量禁用颜色的控制台日志格式化器。"""

    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
        "RESET": "\033[0m",
    }

    @staticmethod
    def _color_enabled() -> bool:
        no_color = os.getenv("NO_COLOR", "").strip().lower()
        if no_color and no_color not in ("0", "false", "off", "no"):
            return False
        if os.getenv("CLICOLOR", "").strip() == "0":
            return False
        if os.getenv("FORCE_COLOR", "").strip() == "0":
            return False
        return True

    def format(self, record):
        if self._color_enabled():
            log_color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
            reset_color = self.COLORS["RESET"]
        else:
            log_color = ""
            reset_color = ""

        record.asctime = datetime.fromtimestamp(record.created).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        try:
            message = record.getMessage()
        except UnicodeEncodeError:
            message = str(record.msg).encode("gbk", errors="ignore").decode("gbk")
            if record.args:
                try:
                    message = message % tuple(
                        str(arg).encode("gbk", errors="ignore").decode("gbk")
                        for arg in record.args
                    )
                except Exception:
                    pass

        formatted_message = (
            f"{log_color}[{record.levelname}]{reset_color} "
            f"{record.asctime} - {record.name} - {message}"
        )

        if record.exc_info:
            try:
                formatted_message += f"\n{self.formatException(record.exc_info)}"
            except UnicodeEncodeError:
                formatted_message += "\n[异常信息包含无法编码的字符，已跳过]"

        return formatted_message


class ERPLogger:
    """ERP 系统日志管理器。"""

    def __init__(self):
        self.loggers = {}
        self.log_dir = Path("temp/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def get_logger(self, name: str, level: str = "INFO") -> logging.Logger:
        if name in self.loggers:
            return self.loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(getattr(logging, level.upper()))

        if not logger.handlers:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(ColoredFormatter())
            logger.addHandler(console_handler)

            log_file = self.log_dir / f"{name.replace('.', '_')}.log"
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(
                logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            )
            logger.addHandler(file_handler)

        logger.propagate = False
        self.loggers[name] = logger
        return logger

    def set_level(self, name: str, level: str):
        if name in self.loggers:
            self.loggers[name].setLevel(getattr(logging, level.upper()))

    def cleanup_logs(self, days: int = 7):
        import time

        cutoff_time = time.time() - (days * 24 * 60 * 60)
        for log_file in self.log_dir.glob("*.log"):
            if log_file.stat().st_mtime < cutoff_time:
                try:
                    log_file.unlink()
                    print(f"已删除旧日志文件: {log_file}")
                except Exception as exc:
                    print(f"删除日志文件失败 {log_file}: {exc}")


_logger_manager = ERPLogger()


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    return _logger_manager.get_logger(name, level)


def set_log_level(name: str, level: str):
    _logger_manager.set_level(name, level)


def cleanup_logs(days: int = 7):
    _logger_manager.cleanup_logs(days)
