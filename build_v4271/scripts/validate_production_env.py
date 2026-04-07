#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证生产环境.env配置文件
检查配置完整性和安全性
"""

import os
import sys
from pathlib import Path

def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)

def check_env_file(env_file_path):
    """检查.env文件"""
    safe_print("\n" + "="*60)
    safe_print("验证生产环境配置")
    safe_print("="*60)
    
    if not env_file_path.exists():
        safe_print(f"[FAIL] 配置文件不存在: {env_file_path}")
        return False
    
    # 读取配置文件
    try:
        env_content = env_file_path.read_text(encoding='utf-8')
    except Exception as e:
        safe_print(f"[FAIL] 无法读取配置文件: {e}")
        return False
    
    # 解析配置
    config = {}
    for line in env_content.split('\n'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip()
    
    # 检查必需配置
    required_configs = {
        'ENVIRONMENT': 'production',
        'APP_ENV': 'production',
        'HOST': '0.0.0.0',
        'POSTGRES_PASSWORD': None,  # 必须存在且不为默认值
        'SECRET_KEY': None,  # 必须存在且不为默认值
        'JWT_SECRET_KEY': None,  # 必须存在且不为默认值
        'REDIS_PASSWORD': None,  # 必须存在
    }
    
    safe_print("\n[检查必需配置]")
    all_ok = True
    
    for key, expected_value in required_configs.items():
        if key not in config:
            safe_print(f"  [FAIL] {key}: 未配置")
            all_ok = False
        elif expected_value and config[key] != expected_value:
            safe_print(f"  [FAIL] {key}: 值不正确 (期望: {expected_value}, 实际: {config[key]})")
            all_ok = False
        elif not expected_value:
            # 检查是否为默认值
            value = config[key]
            if key == 'POSTGRES_PASSWORD' and ('erp_pass' in value.lower() or len(value) < 16):
                safe_print(f"  [FAIL] {key}: 密码太弱或使用默认值")
                all_ok = False
            elif key == 'SECRET_KEY' and ('xihong-erp-secret' in value.lower() or len(value) < 24):
                safe_print(f"  [FAIL] {key}: 密钥太弱或使用默认值")
                all_ok = False
            elif key == 'JWT_SECRET_KEY' and ('xihong-erp-jwt' in value.lower() or len(value) < 24):
                safe_print(f"  [FAIL] {key}: JWT密钥太弱或使用默认值")
                all_ok = False
            elif key == 'REDIS_PASSWORD' and (not value or len(value) < 8):
                safe_print(f"  [FAIL] {key}: Redis密码太弱")
                all_ok = False
            else:
                safe_print(f"  [OK] {key}: 已配置（已掩码显示）")
        else:
            safe_print(f"  [OK] {key}: {config[key]}")
    
    # 检查性能优化配置
    safe_print("\n[检查性能优化配置]")
    performance_configs = {
        'DB_POOL_SIZE': '10',
        'DB_MAX_OVERFLOW': '20',
        'MAX_CONCURRENT_TASKS': '2',
    }
    
    for key, expected_value in performance_configs.items():
        if key in config:
            if config[key] == expected_value:
                safe_print(f"  [OK] {key}: {config[key]} (已优化)")
            else:
                safe_print(f"  [WARN] {key}: {config[key]} (建议: {expected_value})")
        else:
            safe_print(f"  [WARN] {key}: 未配置 (建议: {expected_value})")
    
    # 检查服务器配置
    safe_print("\n[检查服务器配置]")
    server_configs = {
        'ALLOWED_ORIGINS': None,
        'ALLOWED_HOSTS': None,
        'VITE_API_BASE_URL': None,  # 使用 VITE_API_BASE_URL（不是 VITE_API_URL）
    }
    
    for key in server_configs:
        if key in config:
            value = config[key]
            if 'YOUR_SERVER_IP' in value or 'your-server-ip' in value or 'your-domain.com' in value:
                safe_print(f"  [WARN] {key}: 包含占位符，需要修改为实际值")
            elif key == 'VITE_API_BASE_URL' and value == '/api':
                safe_print(f"  [OK] {key}: {value} (Nginx反向代理模式)")
            else:
                safe_print(f"  [OK] {key}: {value}")
        else:
            # 检查是否有旧的 VITE_API_URL
            if key == 'VITE_API_BASE_URL' and 'VITE_API_URL' in config:
                safe_print(f"  [WARN] {key}: 未配置，但发现 VITE_API_URL（请改为 VITE_API_BASE_URL）")
            else:
                safe_print(f"  [WARN] {key}: 未配置")
    
    # 检查功能配置
    safe_print("\n[检查功能配置]")
    feature_configs = {
        'PLAYWRIGHT_HEADLESS': 'true',
        'VITE_MODE': 'production',
        'DATABASE_ECHO': 'false',
        'LOG_LEVEL': 'INFO',
    }
    
    for key, expected_value in feature_configs.items():
        if key in config:
            if config[key] == expected_value:
                safe_print(f"  [OK] {key}: {config[key]}")
            else:
                safe_print(f"  [WARN] {key}: {config[key]} (建议: {expected_value})")
        else:
            safe_print(f"  [WARN] {key}: 未配置 (建议: {expected_value})")
    
    # 总结
    safe_print("\n" + "="*60)
    if all_ok:
        safe_print("[OK] 配置验证通过")
        safe_print("\n[建议]")
        safe_print("  1. 确认服务器IP地址配置正确")
        safe_print("  2. 确认所有密码和密钥已妥善保管")
        safe_print("  3. 在服务器上测试配置: docker-compose config")
        return True
    else:
        safe_print("[FAIL] 配置验证失败，请检查上述错误")
        safe_print("\n[建议]")
        safe_print("  1. 修复所有[FAIL]项")
        safe_print("  2. 重新运行验证脚本")
        return False

def main():
    """主函数"""
    # 查找.env文件（优先检查生产环境配置）
    project_root = Path(__file__).parent.parent
    env_files = [
        project_root / ".env.production",  # 优先检查生产环境配置
        project_root / ".env",
        project_root / "env.production",
    ]
    
    env_file = None
    for file_path in env_files:
        if file_path.exists():
            env_file = file_path
            break
    
    if not env_file:
        safe_print("[ERROR] 未找到.env配置文件")
        safe_print("\n[建议]")
        safe_print("  1. 运行生成脚本: python scripts/generate_production_env.py")
        safe_print("  2. 或手动创建.env.production文件")
        return 1
    
    safe_print(f"[INFO] 检查配置文件: {env_file}")
    
    # 验证配置
    is_valid = check_env_file(env_file)
    
    return 0 if is_valid else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        safe_print("\n\n[退出] 用户取消操作")
        sys.exit(1)
    except Exception as e:
        safe_print(f"\n[ERROR] 验证失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
