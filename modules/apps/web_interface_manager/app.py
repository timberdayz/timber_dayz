#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Web界面管理应用

提供统一管理界面、店铺管理界面、采集管理界面的启动和管理功能
"""

import os
import sys
import subprocess
import socket
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from modules.core.base_app import BaseApplication
from modules.core.logger import get_logger
from modules.core.exceptions import ConfigurationError, ValidationError

logger = get_logger(__name__)

class WebInterfaceManagerApp(BaseApplication):
    """Web界面管理应用"""

    # 类级元数据 - 供注册器读取，避免实例化副作用
    NAME = "Web界面管理"
    VERSION = "1.0.0"
    DESCRIPTION = "集成所有Web界面功能，支持统一管理、店铺管理、采集管理界面"

    def __init__(self):
        """初始化Web界面管理应用"""
        super().__init__()  # 调用父类初始化
        
        self.name = "Web界面管理"
        self.version = "1.0.0"
        self.description = "集成所有Web界面功能，支持统一管理、店铺管理、采集管理界面"
        self.author = "跨境电商ERP团队"
        
        # 界面配置
        self.interfaces = {
            "unified": {
                "name": "统一管理界面",
                "file": "unified_dashboard.py",
                "port": 8503,
                "description": "企业级统一管理界面，集成所有功能"
            },
            "store": {
                "name": "店铺管理界面", 
                "file": "store_management.py",
                "port": 8504,
                "description": "专注多平台店铺管理"
            },
            "collection": {
                "name": "采集管理界面",
                "file": "collection_management.py", 
                "port": 8505,
                "description": "数据采集任务管理"
            }
        }
        
        self.running_processes = {}
        logger.debug(f"初始化 {self.name} v{self.version}")
    
    def get_info(self) -> Dict[str, Any]:
        """获取应用信息"""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "interfaces": list(self.interfaces.keys()),
            "running_interfaces": list(self.running_processes.keys())
        }
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            # 检查frontend_streamlit目录是否存在
            frontend_dir = project_root / "frontend_streamlit"
            if not frontend_dir.exists():
                logger.warning(f"前端目录不存在: {frontend_dir}")
                return False
            
            # 检查必要的界面文件
            missing_files = []
            for interface_key, interface_info in self.interfaces.items():
                interface_file = frontend_dir / interface_info["file"]
                if not interface_file.exists():
                    missing_files.append(interface_info["file"])
            
            if missing_files:
                logger.warning(f"缺少界面文件: {missing_files}")
                # 不将此作为健康检查失败，因为可能需要创建这些文件
            
            return True
            
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return False
    
    def run(self):
        """运行Web界面管理应用"""
        logger.info(f"启动 {self.name}")
        
        try:
            self._show_interface_menu()
        except Exception as e:
            logger.error(f"应用运行异常: {e}")
            raise
    
    def _show_interface_menu(self):
        """显示界面选择菜单"""
        while True:
            print(f"\n{'='*50}")
            print(f"🌐 {self.name} v{self.version}")
            print(f"{'='*50}")
            print(f"📋 {self.description}")
            print(f"🟢 状态: 运行中")
            print(f"⏱️  运行时长: {time.time() - getattr(self, '_start_time', time.time()):.1f}秒")
            print(f"{'='*50}")
            
            print("\n🌐 Web界面管理 - 功能菜单")
            print("-" * 40)
            
            # 显示可用界面
            for i, (key, info) in enumerate(self.interfaces.items(), 1):
                status = "🟢 运行中" if key in self.running_processes else "⚪ 未启动"
                print(f"{i}. {status} {info['name']} - {info['description']}")
            
            print(f"\n🔧 管理功能:")
            print(f"{len(self.interfaces) + 1}. 📊 查看运行状态")
            print(f"{len(self.interfaces) + 2}. 🔄 重启所有界面") 
            print(f"{len(self.interfaces) + 3}. ⏹️  停止所有界面")
            print(f"0. 🔙 返回主菜单")
            
            try:
                choice = input(f"\n请选择操作 (0-{len(self.interfaces) + 3}): ").strip()
                
                if choice == "0":
                    break
                elif choice == "1":
                    self._start_interface("unified")
                elif choice == "2":
                    self._start_interface("store") 
                elif choice == "3":
                    self._start_interface("collection")
                elif choice == str(len(self.interfaces) + 1):
                    self._show_status()
                elif choice == str(len(self.interfaces) + 2):
                    self._restart_all_interfaces()
                elif choice == str(len(self.interfaces) + 3):
                    self._stop_all_interfaces()
                else:
                    print("❌ 无效选项，请重新选择")
                    input("按回车键继续...")
                    
            except KeyboardInterrupt:
                print("\n\n🔙 返回主菜单")
                break
            except Exception as e:
                print(f"❌ 操作异常: {e}")
                input("按回车键继续...")
    
    def _start_interface(self, interface_key: str):
        """启动指定界面"""
        if interface_key not in self.interfaces:
            print(f"❌ 无效的界面: {interface_key}")
            return
        
        interface_info = self.interfaces[interface_key]
        
        # 检查是否已经运行
        if interface_key in self.running_processes:
            print(f"⚠️  {interface_info['name']} 已经在运行")
            input("按回车键继续...")
            return
        
        try:
            # 检查文件是否存在
            frontend_dir = project_root / "frontend_streamlit"
            interface_file = frontend_dir / interface_info["file"]
            
            if not interface_file.exists():
                print(f"❌ 界面文件不存在: {interface_file}")
                print(f"💡 建议: 请确保 {interface_info['file']} 文件存在于 frontend_streamlit 目录")
                input("按回车键继续...")
                return
            
            # 选择可用端口
            port = self._choose_available_port(interface_info["port"])
            
            print(f"\n🌐 启动 {interface_info['name']}")
            print("=" * 40)
            print(f"📁 文件: {interface_info['file']}")
            print(f"🌐 端口: {port}")
            print(f"📋 描述: {interface_info['description']}")
            print("\n💡 提示: 按 Ctrl+C 停止服务")
            print("🔗 访问地址: http://localhost:{port}")
            
            # 启动Streamlit服务
            cmd = [
                sys.executable, "-m", "streamlit", "run",
                str(interface_file),
                "--server.port", str(port),
                "--server.address", "0.0.0.0",
                "--server.headless", "true",
                "--browser.gatherUsageStats", "false"
            ]
            
            process = subprocess.Popen(
                cmd,
                cwd=str(project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 记录运行进程
            self.running_processes[interface_key] = {
                "process": process,
                "port": port,
                "start_time": time.time()
            }
            
            print(f"✅ {interface_info['name']} 启动成功")
            print(f"🔗 访问地址: http://localhost:{port}")
            
            # 询问是否在浏览器中打开
            try:
                open_browser = input("\n是否在浏览器中打开? (y/n): ").strip().lower()
                if open_browser in ['y', 'yes', '是']:
                    import webbrowser
                    webbrowser.open(f"http://localhost:{port}")
            except:
                pass
            
            input("按回车键继续...")
            
        except Exception as e:
            logger.error(f"启动界面失败 {interface_key}: {e}")
            print(f"❌ 启动失败: {e}")
            input("按回车键继续...")
    
    def _choose_available_port(self, default_port: int) -> int:
        """选择可用端口"""
        port = default_port
        
        while self._is_port_in_use(port):
            port += 1
            
        if port != default_port:
            logger.info(f"端口 {default_port} 被占用，改用 {port}")
            
        return port
    
    def _is_port_in_use(self, port: int) -> bool:
        """检查端口是否被占用"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("127.0.0.1", port)) == 0
    
    def _show_status(self):
        """显示运行状态"""
        print("\n📊 Web界面运行状态")
        print("-" * 40)
        
        if not self.running_processes:
            print("📋 当前没有运行的界面")
        else:
            for interface_key, process_info in self.running_processes.items():
                interface_info = self.interfaces[interface_key]
                runtime = time.time() - process_info["start_time"]
                
                # 检查进程是否还在运行
                if process_info["process"].poll() is None:
                    status = "🟢 运行中"
                else:
                    status = "🔴 已停止"
                
                print(f"  • {interface_info['name']}: {status}")
                print(f"    📍 端口: {process_info['port']}")
                print(f"    ⏱️  运行时长: {runtime:.1f}秒")
                print(f"    🔗 访问地址: http://localhost:{process_info['port']}")
                print()
        
        input("按回车键继续...")
    
    def _restart_all_interfaces(self):
        """重启所有界面"""
        print("\n🔄 重启所有界面...")
        
        # 先停止所有
        self._stop_all_interfaces()
        
        # 等待一下
        time.sleep(2)
        
        # 重新启动
        for interface_key in self.interfaces.keys():
            print(f"🔄 重启 {self.interfaces[interface_key]['name']}...")
            self._start_interface(interface_key)
        
        print("✅ 所有界面重启完成")
        input("按回车键继续...")
    
    def _stop_all_interfaces(self):
        """停止所有界面"""
        print("\n⏹️  停止所有界面...")
        
        for interface_key, process_info in list(self.running_processes.items()):
            interface_info = self.interfaces[interface_key]
            
            try:
                process_info["process"].terminate()
                process_info["process"].wait(timeout=5)
                print(f"✅ 停止 {interface_info['name']}")
            except subprocess.TimeoutExpired:
                process_info["process"].kill()
                print(f"🔴 强制停止 {interface_info['name']}")
            except Exception as e:
                print(f"❌ 停止失败 {interface_info['name']}: {e}")
        
        self.running_processes.clear()
        print("✅ 所有界面已停止")
        input("按回车键继续...")
    
    def cleanup(self):
        """清理资源"""
        try:
            self._stop_all_interfaces()
            logger.info("Web界面管理应用清理完成")
        except Exception as e:
            logger.error(f"清理失败: {e}")

# 模块导出
__all__ = ["WebInterfaceManagerApp"] 