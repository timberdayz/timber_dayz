#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
配置验证CLI脚本

验证项目配置文件的正确性，支持：
- 单个文件验证
- 批量验证
- 详细报告输出
- CI模式

用法:
    python scripts/validate_configs.py              # 验证所有配置
    python scripts/validate_configs.py --file accounts_config.yaml  # 验证单个文件
    python scripts/validate_configs.py --strict     # 严格模式，失败时退出
    python scripts/validate_configs.py --ci         # CI模式，简洁输出
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.core import ConfigValidator, ConfigValidationError, get_logger

logger = get_logger(__name__)


def validate_single_file(config_dir: str, filename: str, verbose: bool = False) -> bool:
    """
    验证单个配置文件
    
    Args:
        config_dir: 配置目录
        filename: 文件名
        verbose: 是否详细输出
        
    Returns:
        bool: 验证是否成功
    """
    validator = ConfigValidator(config_dir)
    config_path = Path(config_dir) / filename
    
    # 确定Schema类
    schema_class = validator.schemas.get(filename)
    if not schema_class:
        print(f"❌ 不支持的配置文件: {filename}")
        print(f"支持的文件: {list(validator.schemas.keys())}")
        return False
    
    try:
        result = validator.validate_config_file(config_path, schema_class)
        
        if result['valid']:
            print(f"✅ {filename} 验证通过")
            if verbose and result['warnings']:
                print("⚠️  警告:")
                for warning in result['warnings']:
                    print(f"  - {warning}")
        else:
            print(f"❌ {filename} 验证失败")
            print("错误:")
            for error in result['errors']:
                print(f"  - {error}")
            
            if result['warnings']:
                print("警告:")
                for warning in result['warnings']:
                    print(f"  - {warning}")
        
        return result['valid']
        
    except Exception as e:
        print(f"❌ 验证异常: {e}")
        return False


def validate_all_configs(config_dir: str, strict: bool = False, ci_mode: bool = False) -> bool:
    """
    验证所有配置文件
    
    Args:
        config_dir: 配置目录
        strict: 严格模式
        ci_mode: CI模式
        
    Returns:
        bool: 验证是否成功
    """
    try:
        validator = ConfigValidator(config_dir)
        
        if strict:
            results = validator.validate_and_raise()
        else:
            results = validator.validate_all_configs()
        
        if ci_mode:
            # CI模式简洁输出
            if results['success']:
                print(f"PASS: Config validation ({results['valid_files']}/{results['total_files']} files)")
            else:
                print(f"FAIL: Config validation ({results['valid_files']}/{results['total_files']} files)")
                for error in results['errors'][:3]:  # 只显示前3个错误
                    print(f"ERROR: {error}")
        else:
            # 详细输出
            report = validator.generate_validation_report(results)
            print(report)
        
        return results['success']
        
    except ConfigValidationError as e:
        if ci_mode:
            print(f"FAIL: {e}")
        else:
            print(f"❌ 配置验证失败: {e}")
        return False
    except Exception as e:
        if ci_mode:
            print(f"ERROR: {e}")
        else:
            print(f"💥 验证异常: {e}")
        return False


def fix_common_issues(config_dir: str) -> bool:
    """
    修复常见配置问题
    
    Args:
        config_dir: 配置目录
        
    Returns:
        bool: 是否有修复
    """
    print("🔧 检查并修复常见配置问题...")
    
    fixed = False
    config_path = Path(config_dir)
    
    # 检查配置目录是否存在
    if not config_path.exists():
        print(f"📁 创建配置目录: {config_path}")
        config_path.mkdir(parents=True, exist_ok=True)
        fixed = True
    
    # 检查关键配置文件是否存在
    required_files = {
        'accounts_config.yaml': 'accounts_config.yaml.template',
        'proxy_config.yaml': 'proxy_config.yaml.template'
    }
    
    for config_file, template_file in required_files.items():
        config_file_path = config_path / config_file
        template_path = config_path / template_file
        
        if not config_file_path.exists():
            if template_path.exists():
                print(f"📋 从模板创建配置文件: {config_file}")
                import shutil
                shutil.copy2(template_path, config_file_path)
                fixed = True
            else:
                print(f"⚠️  缺少配置文件: {config_file}")
                print(f"   请手动创建或提供模板文件: {template_file}")
    
    if not fixed:
        print("✅ 未发现需要修复的问题")
    
    return fixed


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="配置文件验证工具")
    parser.add_argument("--config-dir", default="config", help="配置文件目录")
    parser.add_argument("--file", help="验证单个文件")
    parser.add_argument("--strict", action="store_true", help="严格模式，失败时退出")
    parser.add_argument("--ci", action="store_true", help="CI模式，简洁输出")
    parser.add_argument("--fix", action="store_true", help="尝试修复常见问题")
    parser.add_argument("--verbose", action="store_true", help="详细输出")
    
    args = parser.parse_args()
    
    try:
        if args.fix:
            fix_common_issues(args.config_dir)
            print()
        
        if args.file:
            # 验证单个文件
            success = validate_single_file(args.config_dir, args.file, args.verbose)
        else:
            # 验证所有文件
            success = validate_all_configs(args.config_dir, args.strict, args.ci)
        
        sys.exit(0 if success else 1)
        
    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
        sys.exit(130)
    except Exception as e:
        if args.ci:
            print(f"FATAL: {e}")
        else:
            print(f"💥 致命错误: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
