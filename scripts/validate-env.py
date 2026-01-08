#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
环境变量验证脚本

验证环境变量配置的完整性和正确性，支持：
- P0/P1 分级检查
- 变量格式验证（URL、端口、布尔值）
- 默认密钥检测
- 生产环境安全检查

使用方法：
    python scripts/validate-env.py --env-file .env
    python scripts/validate-env.py --env-file .env --strict  # 严格模式（P0+P1）
    python scripts/validate-env.py --env-file .env --skip-p1  # 仅检查 P0（开发环境）
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from urllib.parse import urlparse

# [FIX] Windows编码兼容：设置标准输出编码
if sys.platform == 'win32':
    try:
        # 尝试设置UTF-8编码
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def safe_print(text, file=None):
    """安全打印（处理Windows GBK编码）"""
    try:
        if file:
            print(text, file=file, flush=True)
        else:
            print(text, flush=True)
    except UnicodeEncodeError:
        # Windows GBK编码兼容：移除无法编码的字符
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
        if file:
            print(safe_text, file=file, flush=True)
        else:
            print(safe_text, flush=True)

# P0 级别变量（必须配置）
P0_VARIABLES = {
    "ENVIRONMENT": {
        "required": True,
        "values": ["development", "production"],
        "description": "运行环境"
    },
    "DATABASE_URL": {
        "required": True,
        "format": "url",
        "description": "数据库连接字符串"
    },
    "SECRET_KEY": {
        "required": True,
        "min_length": 32,
        "description": "应用密钥"
    },
    "JWT_SECRET_KEY": {
        "required": True,
        "min_length": 32,
        "description": "JWT 签名密钥"
    },
}

# P1 级别变量（建议配置）
P1_VARIABLES = {
    "HOST": {
        "required": False,
        "description": "服务器监听地址"
    },
    "PORT": {
        "required": False,
        "format": "port",
        "description": "服务器端口"
    },
    "POSTGRES_HOST": {
        "required": False,
        "description": "PostgreSQL 主机"
    },
    "POSTGRES_PORT": {
        "required": False,
        "format": "port",
        "description": "PostgreSQL 端口"
    },
    "POSTGRES_USER": {
        "required": False,
        "description": "PostgreSQL 用户名"
    },
    "POSTGRES_PASSWORD": {
        "required": False,
        "min_length": 8,
        "description": "PostgreSQL 密码"
    },
    "POSTGRES_DB": {
        "required": False,
        "description": "PostgreSQL 数据库名"
    },
    "REDIS_URL": {
        "required": False,
        "format": "url",
        "description": "Redis 连接 URL"
    },
}

# 默认密钥列表（生产环境禁止使用）
DEFAULT_SECRETS = {
    "SECRET_KEY": [
        "xihong-erp-secret-key-2025",
        "your-secret-key-change-this-in-production-please-use-strong-random-string",
        "docker-secret-key-change-in-production",
        "dev-secret-key-not-for-production",
    ],
    "JWT_SECRET_KEY": [
        "xihong-erp-jwt-secret-2025",
        "your-jwt-secret-key-here",
        "docker-jwt-secret-key-change-in-production",
        "dev-jwt-secret-not-for-production",
    ],
    "POSTGRES_PASSWORD": [
        "erp_pass_2025",
        "dev_pass_2025",
        "YOUR_SECURE_PASSWORD_HERE",
    ],
}


class ValidationError(Exception):
    """验证错误"""
    pass


class EnvValidator:
    """环境变量验证器"""
    
    def __init__(self, env_file: Path, strict: bool = False, skip_p1: bool = False):
        """
        初始化验证器
        
        Args:
            env_file: 环境变量文件路径
            strict: 严格模式（检查 P0 + P1）
            skip_p1: 跳过 P1 检查（仅开发环境）
        """
        self.env_file = env_file
        self.strict = strict
        self.skip_p1 = skip_p1
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.env_vars: Dict[str, str] = {}
        
    def load_env_file(self) -> None:
        """加载环境变量文件"""
        if not self.env_file.exists():
            raise ValidationError(f"环境变量文件不存在: {self.env_file}")
        
        # 读取文件
        content = self.env_file.read_text(encoding='utf-8')
        
        # 解析环境变量（简单解析，不处理复杂情况）
        for line in content.split('\n'):
            line = line.strip()
            
            # 跳过空行和注释
            if not line or line.startswith('#'):
                continue
            
            # 解析 KEY=VALUE
            if '=' in line:
                parts = line.split('=', 1)
                key = parts[0].strip()
                value = parts[1].strip()
                
                # 移除引号
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                self.env_vars[key] = value
    
    def validate_format(self, key: str, value: str, format_type: str) -> bool:
        """验证变量格式"""
        if format_type == "url":
            try:
                parsed = urlparse(value)
                return parsed.scheme in ["http", "https", "postgresql", "redis", "sqlite"]
            except Exception:
                return False
        
        elif format_type == "port":
            try:
                port = int(value)
                return 1 <= port <= 65535
            except ValueError:
                return False
        
        elif format_type == "boolean":
            return value.lower() in ["true", "false", "1", "0", "yes", "no"]
        
        return True
    
    def check_default_secrets(self) -> None:
        """检查是否使用默认密钥"""
        environment = self.env_vars.get("ENVIRONMENT", "development")
        
        if environment != "production":
            # 开发环境允许使用默认密钥
            return
        
        # 生产环境检查
        for key, default_values in DEFAULT_SECRETS.items():
            value = self.env_vars.get(key, "")
            
            if not value:
                continue
            
            for default_value in default_values:
                if value == default_value or default_value.lower() in value.lower():
                    self.errors.append(
                        f"[P0] 生产环境禁止使用默认密钥: {key}={value[:20]}..."
                    )
                    break
    
    def validate_variable(
        self,
        key: str,
        config: Dict,
        priority: str
    ) -> Tuple[bool, Optional[str]]:
        """
        验证单个变量
        
        Returns:
            (是否通过, 错误消息)
        """
        value = self.env_vars.get(key)
        
        # 检查必需变量
        if config.get("required", False) and not value:
            return False, f"[{priority}] 必需变量缺失: {key} - {config.get('description', '')}"
        
        if not value:
            # 可选变量未设置，跳过
            return True, None
        
        # 检查值范围
        if "values" in config:
            if value not in config["values"]:
                return False, (
                    f"[{priority}] 变量值无效: {key}={value} "
                    f"(允许值: {', '.join(config['values'])})"
                )
        
        # 检查最小长度
        if "min_length" in config:
            if len(value) < config["min_length"]:
                return False, (
                    f"[{priority}] 变量值太短: {key} "
                    f"(最小长度: {config['min_length']})"
                )
        
        # 检查格式
        if "format" in config:
            if not self.validate_format(key, value, config["format"]):
                return False, (
                    f"[{priority}] 变量格式无效: {key}={value} "
                    f"(格式: {config['format']})"
                )
        
        return True, None
    
    def validate(self) -> bool:
        """执行验证"""
        try:
            self.load_env_file()
        except ValidationError as e:
            self.errors.append(str(e))
            return False
        
        # 验证 P0 变量
        for key, config in P0_VARIABLES.items():
            passed, error = self.validate_variable(key, config, "P0")
            if not passed:
                self.errors.append(error)
        
        # 验证 P1 变量（如果启用）
        if self.strict and not self.skip_p1:
            for key, config in P1_VARIABLES.items():
                passed, error = self.validate_variable(key, config, "P1")
                if not passed:
                    self.warnings.append(error)
        
        # 检查默认密钥
        self.check_default_secrets()
        
        # 检查生产环境特定要求
        environment = self.env_vars.get("ENVIRONMENT", "development")
        if environment == "production":
            # 检查关键配置
            if self.env_vars.get("DEBUG", "false").lower() == "true":
                self.warnings.append("[P1] 生产环境建议设置 DEBUG=false")
            
            if self.env_vars.get("DATABASE_ECHO", "false").lower() == "true":
                self.warnings.append("[P1] 生产环境建议设置 DATABASE_ECHO=false")
            
            if self.env_vars.get("PLAYWRIGHT_HEADLESS", "false").lower() != "true":
                self.warnings.append("[P1] 生产环境建议设置 PLAYWRIGHT_HEADLESS=true")
        
        return len(self.errors) == 0
    
    def print_results(self, json_output: bool = False) -> None:
        """打印验证结果"""
        if json_output:
            result = {
                "valid": len(self.errors) == 0,
                "errors": self.errors,
                "warnings": self.warnings,
                "variables_checked": len(self.env_vars),
            }
            safe_print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            if self.errors:
                safe_print("[ERROR] 环境变量验证失败：\n", file=sys.stderr)
                for error in self.errors:
                    safe_print(f"  {error}", file=sys.stderr)
                safe_print("", file=sys.stderr)
            
            if self.warnings:
                safe_print("[WARNING] 环境变量警告：\n")
                for warning in self.warnings:
                    safe_print(f"  {warning}")
                safe_print("")
            
            if not self.errors and not self.warnings:
                safe_print("[OK] 环境变量验证通过")
            elif not self.errors:
                safe_print("[OK] 环境变量验证通过（有警告）")


def main():
    """主函数"""
    # [FIX] Windows编码兼容：确保输出编码正确
    if sys.platform == 'win32':
        import io
        try:
            # 重新配置标准输出流
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)
        except Exception:
            pass
    
    parser = argparse.ArgumentParser(description="环境变量验证工具")
    parser.add_argument(
        "--env-file",
        type=str,
        default=".env",
        help="环境变量文件路径（默认: .env）"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="严格模式（检查 P0 + P1）"
    )
    parser.add_argument(
        "--skip-p1",
        action="store_true",
        help="跳过 P1 检查（仅开发环境）"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON 输出格式（用于脚本消费）"
    )
    args = parser.parse_args()
    
    # 解析文件路径
    env_file = Path(args.env_file)
    if not env_file.is_absolute():
        # 相对路径：从项目根目录查找
        project_root = Path(__file__).parent.parent
        env_file = project_root / env_file
    
    # 创建验证器
    validator = EnvValidator(
        env_file=env_file,
        strict=args.strict,
        skip_p1=args.skip_p1
    )
    
    # 执行验证
    is_valid = validator.validate()
    
    # 打印结果
    validator.print_results(json_output=args.json)
    
    # 返回退出码
    sys.exit(0 if is_valid else 1)


if __name__ == "__main__":
    main()

