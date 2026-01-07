#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
密钥生成工具

生成系统所需的所有密钥，支持：
- SECRET_KEY
- JWT_SECRET_KEY
- ACCOUNT_ENCRYPTION_KEY
- 输出到文件或终端打印

使用方法：
    python scripts/generate-secrets.py                    # 终端打印
    python scripts/generate-secrets.py --output .env.dev  # 输出到文件
    python scripts/generate-secrets.py --print           # 仅打印（不写入文件）
"""

import os
import sys
import secrets
import argparse
from pathlib import Path
from cryptography.fernet import Fernet

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent


def generate_secret_key(length: int = 32) -> str:
    """生成 SECRET_KEY 或 JWT_SECRET_KEY"""
    return secrets.token_urlsafe(length)


def generate_encryption_key() -> str:
    """生成 ACCOUNT_ENCRYPTION_KEY (Fernet 格式)"""
    return Fernet.generate_key().decode()


def generate_all_secrets() -> dict:
    """生成所有密钥"""
    return {
        "SECRET_KEY": generate_secret_key(32),
        "JWT_SECRET_KEY": generate_secret_key(32),
        "ACCOUNT_ENCRYPTION_KEY": generate_encryption_key(),
    }


def print_secrets(secrets_dict: dict, output_file: Path = None) -> None:
    """打印或写入密钥"""
    lines = []
    lines.append("# =====================================================")
    lines.append("# 生成的密钥（请妥善保管，不要提交到版本库）")
    lines.append("# =====================================================")
    lines.append("")
    
    for key, value in secrets_dict.items():
        lines.append(f"{key}={value}")
    
    lines.append("")
    lines.append("# =====================================================")
    lines.append("# 使用说明：")
    lines.append("# 1. 复制上述密钥到 .env 文件")
    lines.append("# 2. 生产环境：复制到服务器 .env 或云 Secret 管理")
    lines.append("# 3. 开发环境：可写入 .env.development（仅本地）")
    lines.append("# =====================================================")
    
    content = "\n".join(lines)
    
    if output_file:
        # 写入文件
        output_file.write_text(content, encoding='utf-8')
        # 设置文件权限（仅所有者可读）
        try:
            os.chmod(output_file, 0o600)
        except Exception:
            pass  # Windows 可能不支持
        print(f"[OK] 密钥已写入: {output_file}")
        print(f"[提示] 文件权限已设置为 600（仅所有者可读）")
    else:
        # 仅打印
        print(content)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="生成系统密钥")
    parser.add_argument(
        "--output",
        type=str,
        help="输出文件路径（如 .env.dev），如果未指定则仅打印"
    )
    parser.add_argument(
        "--print",
        action="store_true",
        help="仅打印到终端（不写入文件）"
    )
    args = parser.parse_args()
    
    print("=" * 60)
    print("密钥生成工具")
    print("=" * 60)
    print("")
    
    # 生成密钥
    print("[1/2] 生成密钥...")
    secrets_dict = generate_all_secrets()
    print("[OK] 密钥生成完成")
    print("")
    
    # 输出密钥
    print("[2/2] 输出密钥...")
    if args.print or not args.output:
        # 仅打印
        print_secrets(secrets_dict)
    else:
        # 写入文件
        output_file = Path(args.output)
        if not output_file.is_absolute():
            output_file = PROJECT_ROOT / output_file
        
        # 确认文件不存在或用户确认覆盖
        if output_file.exists():
            response = input(f"文件已存在: {output_file}\n是否覆盖？(y/N): ")
            if response.lower() != 'y':
                print("[取消] 用户取消操作")
                sys.exit(0)
        
        print_secrets(secrets_dict, output_file)
    
    print("")
    print("=" * 60)
    print("[完成] 密钥生成完成")
    print("=" * 60)
    print("")
    print("安全提示：")
    print("  - 生产环境：请将密钥复制到服务器 .env 或云 Secret 管理")
    print("  - 开发环境：可写入 .env.development（仅本地，不要提交到版本库）")
    print("  - 不要将密钥提交到 Git 仓库")


if __name__ == "__main__":
    main()

