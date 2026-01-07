#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
配置验证器

提供YAML配置文件的验证功能，支持：
- Schema验证
- 业务逻辑验证
- 配置文件完整性检查
- 验证报告生成
"""

import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from pydantic import ValidationError

from .config_schemas import AccountsConfigSchema, ProxyConfigSchema
from .logger import get_logger
from .exceptions import ERPException

logger = get_logger(__name__)


class ConfigValidationError(ERPException):
    """配置验证错误"""
    pass


class ConfigValidator:
    """配置验证器"""
    
    def __init__(self, config_dir: str = "config"):
        """
        初始化配置验证器
        
        Args:
            config_dir: 配置文件目录
        """
        self.config_dir = Path(config_dir)
        self.schemas = {
            'accounts_config.yaml': AccountsConfigSchema,
            'proxy_config.yaml': ProxyConfigSchema,
        }
        
    def validate_all_configs(self) -> Dict[str, Any]:
        """
        验证所有配置文件
        
        Returns:
            Dict[str, Any]: 验证结果
        """
        results = {
            'success': True,
            'total_files': 0,
            'valid_files': 0,
            'invalid_files': 0,
            'errors': [],
            'warnings': [],
            'details': {}
        }
        
        logger.info("开始验证配置文件...")
        
        for config_file, schema_class in self.schemas.items():
            config_path = self.config_dir / config_file
            results['total_files'] += 1
            
            try:
                validation_result = self.validate_config_file(config_path, schema_class)
                results['details'][config_file] = validation_result
                
                if validation_result['valid']:
                    results['valid_files'] += 1
                    logger.info(f"✅ {config_file} 验证通过")
                else:
                    results['invalid_files'] += 1
                    results['success'] = False
                    results['errors'].extend(validation_result['errors'])
                    logger.error(f"❌ {config_file} 验证失败")
                    
            except Exception as e:
                results['invalid_files'] += 1
                results['success'] = False
                error_msg = f"{config_file}: {str(e)}"
                results['errors'].append(error_msg)
                logger.error(f"❌ {config_file} 验证异常: {e}")
        
        # 检查配置文件完整性
        self._check_config_completeness(results)
        
        logger.info(f"配置验证完成: {results['valid_files']}/{results['total_files']} 通过")
        return results
    
    def validate_config_file(self, config_path: Path, schema_class) -> Dict[str, Any]:
        """
        验证单个配置文件
        
        Args:
            config_path: 配置文件路径
            schema_class: Schema类
            
        Returns:
            Dict[str, Any]: 验证结果
        """
        result = {
            'valid': False,
            'file_path': str(config_path),
            'errors': [],
            'warnings': [],
            'data': None
        }
        
        # 检查文件是否存在
        if not config_path.exists():
            result['errors'].append(f"配置文件不存在: {config_path}")
            return result
        
        try:
            # 加载YAML文件
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            if config_data is None:
                result['errors'].append("配置文件为空")
                return result
            
            # Schema验证
            validated_data = schema_class(**config_data)
            result['data'] = validated_data.dict()
            result['valid'] = True
            
            # 业务逻辑验证
            business_warnings = self._validate_business_logic(config_path.name, result['data'])
            result['warnings'].extend(business_warnings)
            
        except yaml.YAMLError as e:
            result['errors'].append(f"YAML格式错误: {e}")
        except ValidationError as e:
            for error in e.errors():
                field_path = " -> ".join(str(loc) for loc in error['loc'])
                error_msg = f"{field_path}: {error['msg']}"
                result['errors'].append(error_msg)
        except Exception as e:
            result['errors'].append(f"未知错误: {e}")
        
        return result
    
    def _validate_business_logic(self, filename: str, config_data: Dict[str, Any]) -> List[str]:
        """
        业务逻辑验证
        
        Args:
            filename: 配置文件名
            config_data: 配置数据
            
        Returns:
            List[str]: 警告信息列表
        """
        warnings = []
        
        if filename == 'accounts_config.yaml':
            warnings.extend(self._validate_accounts_business_logic(config_data))
        elif filename == 'proxy_config.yaml':
            warnings.extend(self._validate_proxy_business_logic(config_data))
        
        return warnings
    
    def _validate_accounts_business_logic(self, config_data: Dict[str, Any]) -> List[str]:
        """验证账号配置的业务逻辑"""
        warnings = []
        
        accounts = config_data.get('accounts', {})
        
        # 检查是否有启用的账号
        enabled_accounts = []
        for group_name, account_list in accounts.items():
            for account in account_list:
                if account.get('enabled', True):
                    enabled_accounts.append(account['account_id'])
        
        if not enabled_accounts:
            warnings.append("没有启用的账号，系统可能无法正常工作")
        
        # 检查代理配置一致性
        proxy_required_accounts = []
        for group_name, account_list in accounts.items():
            for account in account_list:
                if account.get('proxy_required', False):
                    proxy_required_accounts.append(account['account_id'])
        
        if proxy_required_accounts:
            warnings.append(f"以下账号需要代理配置: {', '.join(proxy_required_accounts)}")
        
        # 检查密码安全性
        weak_passwords = []
        for group_name, account_list in accounts.items():
            for account in account_list:
                password = account.get('password', '')
                if len(password) < 8:
                    weak_passwords.append(account['account_id'])
        
        if weak_passwords:
            warnings.append(f"以下账号密码强度较弱: {', '.join(weak_passwords)}")
        
        return warnings
    
    def _validate_proxy_business_logic(self, config_data: Dict[str, Any]) -> List[str]:
        """验证代理配置的业务逻辑"""
        warnings = []
        
        direct_domains = config_data.get('direct_domains', [])
        vpn_domains = config_data.get('vpn_domains', [])
        
        # 检查域名重复
        common_domains = set(direct_domains) & set(vpn_domains)
        if common_domains:
            warnings.append(f"以下域名同时在直连和VPN列表中: {', '.join(common_domains)}")
        
        # 检查代理设置
        proxy_settings = config_data.get('proxy_settings', {})
        custom_proxies = [name for name, settings in proxy_settings.items() 
                         if settings.get('type') == 'custom']
        
        if custom_proxies:
            for proxy_name in custom_proxies:
                proxy_config = proxy_settings[proxy_name]
                if not proxy_config.get('server'):
                    warnings.append(f"自定义代理 {proxy_name} 缺少服务器配置")
        
        return warnings
    
    def _check_config_completeness(self, results: Dict[str, Any]):
        """检查配置文件完整性"""
        required_configs = ['accounts_config.yaml', 'proxy_config.yaml']
        missing_configs = []
        
        for config_file in required_configs:
            if config_file not in results['details']:
                missing_configs.append(config_file)
            elif not results['details'][config_file]['valid']:
                missing_configs.append(f"{config_file} (无效)")
        
        if missing_configs:
            warning_msg = f"缺少或无效的关键配置文件: {', '.join(missing_configs)}"
            results['warnings'].append(warning_msg)
    
    def generate_validation_report(self, results: Dict[str, Any]) -> str:
        """
        生成验证报告
        
        Args:
            results: 验证结果
            
        Returns:
            str: 格式化的验证报告
        """
        report_lines = [
            "📋 配置文件验证报告",
            "=" * 50,
            f"总文件数: {results['total_files']}",
            f"有效文件: {results['valid_files']}",
            f"无效文件: {results['invalid_files']}",
            f"整体状态: {'✅ 通过' if results['success'] else '❌ 失败'}",
            ""
        ]
        
        # 详细结果
        for config_file, detail in results['details'].items():
            status = "✅ 有效" if detail['valid'] else "❌ 无效"
            report_lines.append(f"📄 {config_file}: {status}")
            
            if detail['errors']:
                report_lines.append("  错误:")
                for error in detail['errors']:
                    report_lines.append(f"    - {error}")
            
            if detail['warnings']:
                report_lines.append("  警告:")
                for warning in detail['warnings']:
                    report_lines.append(f"    - {warning}")
            
            report_lines.append("")
        
        # 全局警告
        if results['warnings']:
            report_lines.append("⚠️ 全局警告:")
            for warning in results['warnings']:
                report_lines.append(f"  - {warning}")
            report_lines.append("")
        
        # 全局错误
        if results['errors']:
            report_lines.append("❌ 全局错误:")
            for error in results['errors']:
                report_lines.append(f"  - {error}")
        
        return "\n".join(report_lines)
    
    def validate_and_raise(self):
        """验证配置并在失败时抛出异常"""
        results = self.validate_all_configs()
        
        if not results['success']:
            report = self.generate_validation_report(results)
            logger.error("配置验证失败")
            logger.error(report)
            raise ConfigValidationError(f"配置验证失败: {len(results['errors'])} 个错误")
        
        if results['warnings']:
            report = self.generate_validation_report(results)
            logger.warning("配置验证通过但有警告")
            logger.warning(report)
        
        return results


def validate_configs(config_dir: str = "config") -> Dict[str, Any]:
    """
    验证配置文件的便捷函数
    
    Args:
        config_dir: 配置目录
        
    Returns:
        Dict[str, Any]: 验证结果
    """
    validator = ConfigValidator(config_dir)
    return validator.validate_all_configs()


def validate_configs_strict(config_dir: str = "config") -> Dict[str, Any]:
    """
    严格验证配置文件，失败时抛出异常
    
    Args:
        config_dir: 配置目录
        
    Returns:
        Dict[str, Any]: 验证结果
    """
    validator = ConfigValidator(config_dir)
    return validator.validate_and_raise()
