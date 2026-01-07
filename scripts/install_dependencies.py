#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Vue.js字段映射系统 - 依赖自动安装脚本
支持Windows/Linux/macOS
"""

import os
import sys
import subprocess
import platform
from pathlib import Path

def print_header(text):
    """打印标题"""
    print("\n" + "="*60)
    print(f"🎯 {text}")
    print("="*60)

def print_step(text):
    """打印步骤"""
    print(f"\n📋 {text}")

def print_success(text):
    """打印成功信息"""
    print(f"✅ {text}")

def print_error(text):
    """打印错误信息"""
    print(f"❌ {text}")

def print_warning(text):
    """打印警告信息"""
    print(f"⚠️  {text}")

def run_command(cmd, check=True, shell=False):
    """运行命令"""
    try:
        result = subprocess.run(
            cmd,
            check=check,
            shell=shell,
            capture_output=True,
            text=True
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        return False, e.stdout, e.stderr
    except FileNotFoundError:
        return False, "", "命令未找到"

def check_nodejs():
    """检查Node.js是否安装"""
    print_step("步骤1: 检查Node.js安装状态")
    
    # 检查node
    success, stdout, _ = run_command(["node", "--version"], check=False)
    if success:
        node_version = stdout.strip()
        print_success(f"Node.js已安装: {node_version}")
        
        # 检查版本
        version_num = node_version.replace('v', '').split('.')[0]
        if int(version_num) < 16:
            print_warning(f"Node.js版本过低（{node_version}），建议升级到 >= 16.x")
    else:
        print_error("Node.js未安装")
        return False
    
    # 检查npm
    success, stdout, _ = run_command(["npm", "--version"], check=False)
    if success:
        npm_version = stdout.strip()
        print_success(f"npm已安装: {npm_version}")
    else:
        print_error("npm未安装")
        return False
    
    return True

def install_nodejs_guide():
    """显示Node.js安装指南"""
    print_warning("请先安装Node.js:")
    print("\n推荐安装方法:")
    
    system = platform.system()
    
    if system == "Windows":
        print("  1. 访问 https://nodejs.org/zh-cn/")
        print("  2. 下载'长期支持版'（LTS）")
        print("  3. 运行安装包，按默认设置安装")
        print("  4. 重新打开终端/PowerShell")
        print("  5. 再次运行此脚本")
        
        # 尝试打开浏览器
        try:
            import webbrowser
            print("\n是否立即打开Node.js下载页？(y/n): ", end="")
            choice = input().strip().lower()
            if choice == 'y':
                webbrowser.open("https://nodejs.org/zh-cn/download/")
                print_success("已在浏览器中打开")
        except:
            pass
    
    elif system == "Darwin":  # macOS
        print("  方法1 - Homebrew（推荐）:")
        print("    brew install node")
        print("\n  方法2 - 官方安装包:")
        print("    访问 https://nodejs.org/")
    
    else:  # Linux
        print("  Ubuntu/Debian:")
        print("    curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -")
        print("    sudo apt-get install -y nodejs")
        print("\n  CentOS/RHEL:")
        print("    curl -fsSL https://rpm.nodesource.com/setup_lts.x | sudo bash -")
        print("    sudo yum install -y nodejs")

def configure_npm_mirror():
    """配置npm镜像"""
    print_step("步骤2: 配置npm镜像")
    
    print("是否配置淘宝npm镜像（提升下载速度）？(y/n): ", end="")
    choice = input().strip().lower()
    
    if choice == 'y':
        print("正在配置淘宝镜像...")
        success, _, stderr = run_command(
            ["npm", "config", "set", "registry", "https://registry.npmmirror.com"]
        )
        if success:
            print_success("镜像配置完成")
        else:
            print_error(f"镜像配置失败: {stderr}")
    else:
        print("⏭️  跳过镜像配置")

def install_vue_dependencies():
    """安装Vue.js前端依赖"""
    print_step("步骤3: 安装Vue.js前端依赖")
    
    # 切换到前端目录
    frontend_dir = Path("modules/apps/vue_field_mapping/frontend")
    
    if not frontend_dir.exists():
        print_error(f"找不到前端目录: {frontend_dir}")
        return False
    
    original_dir = Path.cwd()
    os.chdir(frontend_dir)
    
    try:
        print("📦 正在安装npm依赖（可能需要几分钟）...")
        
        # 运行npm install
        success, stdout, stderr = run_command(["npm", "install"])
        
        if success:
            print_success("Vue.js前端依赖安装成功")
            
            # 显示安装的包
            print("\n已安装的主要依赖:")
            success, stdout, _ = run_command(["npm", "list", "--depth=0"], check=False)
            if success:
                for line in stdout.split('\n')[1:6]:  # 只显示前5个
                    if line.strip():
                        print(f"  {line}")
            
            return True
        else:
            print_error("依赖安装失败")
            print(f"错误信息: {stderr}")
            return False
    
    finally:
        os.chdir(original_dir)

def check_python_dependencies():
    """检查并安装Python依赖"""
    print_step("步骤4: 检查Python后端依赖")
    
    required_packages = {
        "fastapi": "fastapi",
        "uvicorn": "uvicorn[standard]",
        "pydantic": "pydantic",
    }
    
    missing_packages = []
    
    for module_name, package_name in required_packages.items():
        try:
            __import__(module_name)
            print_success(f"{module_name}")
        except ImportError:
            print_error(f"{module_name}")
            missing_packages.append(package_name)
    
    if missing_packages:
        print(f"\n是否立即安装缺少的Python依赖？(y/n): ", end="")
        choice = input().strip().lower()
        
        if choice == 'y':
            print("正在安装Python依赖...")
            packages = " ".join(missing_packages)
            success, _, stderr = run_command(
                [sys.executable, "-m", "pip", "install"] + missing_packages
            )
            
            if success:
                print_success("Python依赖安装成功")
            else:
                print_error(f"Python依赖安装失败: {stderr}")
    else:
        print_success("所有Python依赖已安装")

def main():
    """主函数"""
    print_header("Vue.js字段映射系统 - 依赖安装向导")
    
    # 检查Node.js
    if not check_nodejs():
        install_nodejs_guide()
        print("\n请安装Node.js后重新运行此脚本")
        return 1
    
    # 配置npm镜像
    configure_npm_mirror()
    
    # 安装Vue.js依赖
    if not install_vue_dependencies():
        return 1
    
    # 检查Python依赖
    check_python_dependencies()
    
    # 完成
    print_header("🎉 安装完成！")
    print("\n下一步操作:")
    print("  1. 启动系统: python run_new.py")
    print("  2. 选择: 4. Vue字段映射审核")
    print("  3. 访问前端: http://localhost:5173")
    print("  4. 访问API文档: http://localhost:8000/docs")
    print("\n祝您使用愉快！🎊\n")
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n操作已取消")
        sys.exit(1)
    except Exception as e:
        print_error(f"发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
