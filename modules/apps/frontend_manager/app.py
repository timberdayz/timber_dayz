"""
前端页面管理应用 - 管理Vue.js前端服务
"""

import os
import sys
import subprocess
import webbrowser
import time
import psutil
from pathlib import Path
from typing import Optional
import logging

from modules.core.base_app import BaseApplication

logger = logging.getLogger(__name__)


class FrontendManagerApp(BaseApplication):
    """前端页面管理应用"""
    
    # 类级元数据（避免实例化副作用）
    APP_ID = "frontend_manager"
    NAME = "前端页面管理"
    VERSION = "1.0.0"
    DESCRIPTION = "管理Vue.js前端服务，支持启动、停止、重启前端开发服务器"
    
    def __init__(self):
        """初始化前端管理应用"""
        super().__init__()
        self.process: Optional[subprocess.Popen] = None
        self.frontend_dir = Path(__file__).parent.parent.parent.parent / "frontend"
        self.port = 5173
        self.url = f"http://localhost:{self.port}"
        
    def get_metadata(self):
        """获取应用元数据"""
        return {
            "name": self.NAME,
            "version": self.VERSION,
            "description": self.DESCRIPTION,
            "app_id": self.APP_ID
        }
    
    def run(self):
        """运行前端管理应用"""
        logger.info(f"启动 {self.NAME}")
        
        while True:
            self._print_menu()
            choice = input("\n请选择操作 (0-5): ").strip()
            
            if choice == "1":
                self._start_frontend()
            elif choice == "2":
                self._stop_frontend()
            elif choice == "3":
                self._restart_frontend()
            elif choice == "4":
                self._check_status()
            elif choice == "5":
                self._open_browser()
            elif choice == "0":
                if self.process:
                    print("\n⚠️  前端服务正在运行，是否停止? (y/n): ", end="")
                    if input().strip().lower() == 'y':
                        self._stop_frontend()
                break
            else:
                print("❌ 无效选择，请重试")
            
            if choice != "0":
                input("\n按回车键继续...")
    
    def _print_menu(self):
        """打印菜单"""
        status = "🟢 运行中" if self._is_frontend_running() else "⚪ 未运行"
        
        print("\n" + "=" * 60)
        print(f"🌐 {self.NAME} v{self.VERSION}")
        print("=" * 60)
        print(f"📋 {self.DESCRIPTION}")
        print(f"🔗 访问地址: {self.url}")
        print(f"📁 前端目录: {self.frontend_dir}")
        print(f"🔘 状态: {status}")
        print("=" * 60)
        print("\n🌐 前端管理 - 功能菜单")
        print("-" * 40)
        print("1. 🚀 启动前端服务")
        print("2. ⏹️  停止前端服务")
        print("3. 🔄 重启前端服务")
        print("4. 📊 查看运行状态")
        print("5. 🌐 在浏览器中打开")
        print("0. 🔙 返回主菜单")
    
    def _check_npm(self) -> tuple:
        """检查npm是否可用，返回(是否可用, npm命令)"""
        try:
            # Windows系统下尝试多个npm路径
            npm_commands = ["npm.cmd", "npm"]
            
            for npm_cmd in npm_commands:
                try:
                    result = subprocess.run(
                        [npm_cmd, "--version"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        shell=True
                    )
                    if result.returncode == 0:
                        print(f"✅ npm版本: {result.stdout.strip()}")
                        print(f"✅ npm命令: {npm_cmd}")
                        return (True, npm_cmd)
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
            
            print("❌ npm未找到")
            print("\n💡 解决方案:")
            print("1. 确认已安装Node.js（包含npm）")
            print("2. 将npm添加到系统PATH环境变量")
            print("3. 重启终端/命令行窗口")
            return (False, None)
            
        except Exception as e:
            logger.error(f"检查npm失败: {e}")
            return (False, None)
    
    def _start_frontend(self):
        """启动前端服务"""
        if self._is_frontend_running():
            print("⚠️  前端服务已经在运行中")
            return
        
        print("\n🚀 启动Vue.js前端服务...")
        print("=" * 60)
        
        # 检查前端目录
        if not self.frontend_dir.exists():
            print(f"❌ 前端目录不存在: {self.frontend_dir}")
            return
        
        # 检查npm
        npm_available, npm_cmd = self._check_npm()
        if not npm_available:
            return
        
        # 检查是否需要安装依赖
        node_modules = self.frontend_dir / "node_modules"
        vite_path = self.frontend_dir / "node_modules" / "vite"
        
        if not node_modules.exists() or not vite_path.exists():
            print("\n⚠️  检测到依赖缺失!")
            print("=" * 60)
            print("前端服务需要安装npm依赖包（Vite、Vue.js等）")
            print("这可能需要几分钟时间...")
            print("\n选项:")
            print("1. 现在安装依赖（推荐）")
            print("2. 手动安装（在新终端运行: cd frontend && npm install）")
            print("0. 取消")
            
            choice = input("\n请选择 (0-2): ").strip()
            
            if choice == "1":
                print("\n📦 正在安装依赖...")
                print("⏳ 请耐心等待...")
                try:
                    # 不捕获输出，让用户看到安装进度
                    result = subprocess.run(
                        f"{npm_cmd} install",
                        cwd=self.frontend_dir,
                        shell=True,
                        timeout=600  # 10分钟超时
                    )
                    if result.returncode == 0:
                        print("\n✅ 依赖安装完成")
                    else:
                        print(f"\n❌ 依赖安装失败（退出码: {result.returncode}）")
                        return
                except subprocess.TimeoutExpired:
                    print("\n❌ 依赖安装超时")
                    return
                except Exception as e:
                    print(f"\n❌ 依赖安装失败: {e}")
                    return
            elif choice == "2":
                print("\n💡 请在新终端窗口运行以下命令:")
                print(f"   cd {self.frontend_dir}")
                print(f"   npm install")
                return
            else:
                print("\n❌ 已取消")
                return
        
        # 启动开发服务器
        try:
            print("\n🌟 启动开发服务器...")
            
            # 使用Popen以非阻塞方式启动
            self.process = subprocess.Popen(
                f"{npm_cmd} run dev",
                cwd=self.frontend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )
            
            # 等待服务启动
            print("⏳ 等待服务启动...")
            time.sleep(3)
            
            if self._is_frontend_running():
                print(f"✅ 前端服务启动成功")
                print(f"🔗 访问地址: {self.url}")
                print("\n💡 提示: 选择选项5在浏览器中打开")
            else:
                print("❌ 前端服务启动失败")
                if self.process:
                    stdout, stderr = self.process.communicate(timeout=1)
                    if stderr:
                        print(f"错误信息: {stderr}")
                
        except Exception as e:
            print(f"❌ 启动失败: {e}")
            logger.error(f"启动前端服务失败: {e}")
    
    def _stop_frontend(self):
        """停止前端服务"""
        if not self._is_frontend_running():
            print("⚠️  前端服务未运行")
            return
        
        print("\n⏹️  正在停止前端服务...")
        
        try:
            if self.process:
                # Windows下需要终止进程树
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                        capture_output=True
                    )
                else:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                
                self.process = None
                print("✅ 前端服务已停止")
            
            # 确保端口被释放
            self._kill_port_process(self.port)
            
        except Exception as e:
            print(f"❌ 停止失败: {e}")
            logger.error(f"停止前端服务失败: {e}")
    
    def _restart_frontend(self):
        """重启前端服务"""
        print("\n🔄 重启前端服务...")
        self._stop_frontend()
        time.sleep(2)
        self._start_frontend()
    
    def _is_frontend_running(self) -> bool:
        """检查前端服务是否运行"""
        # 检查进程是否存活
        if self.process and self.process.poll() is None:
            return True
        
        # 检查端口是否被占用
        for conn in psutil.net_connections():
            if conn.laddr.port == self.port and conn.status == 'LISTEN':
                return True
        
        return False
    
    def _check_status(self):
        """检查运行状态"""
        print("\n📊 前端服务状态")
        print("=" * 60)
        
        is_running = self._is_frontend_running()
        print(f"🔘 状态: {'🟢 运行中' if is_running else '⚪ 未运行'}")
        print(f"🔗 访问地址: {self.url}")
        print(f"📁 前端目录: {self.frontend_dir}")
        print(f"🔌 端口: {self.port}")
        
        if is_running:
            print(f"🆔 进程ID: {self.process.pid if self.process else '未知'}")
            
            # 检查端口连接
            connections = []
            for conn in psutil.net_connections():
                if conn.laddr.port == self.port:
                    connections.append(conn)
            
            print(f"🔗 连接数: {len(connections)}")
        
        # 检查node_modules
        node_modules = self.frontend_dir / "node_modules"
        print(f"📦 依赖状态: {'✅ 已安装' if node_modules.exists() else '❌ 未安装'}")
    
    def _open_browser(self):
        """在浏览器中打开"""
        if not self._is_frontend_running():
            print("⚠️  前端服务未运行，请先启动服务")
            return
        
        print(f"\n🌐 在浏览器中打开: {self.url}")
        try:
            webbrowser.open(self.url)
            print("✅ 浏览器已打开")
        except Exception as e:
            print(f"❌ 打开浏览器失败: {e}")
            print(f"💡 请手动访问: {self.url}")
    
    def _kill_port_process(self, port: int):
        """终止占用指定端口的进程"""
        try:
            for conn in psutil.net_connections():
                if conn.laddr.port == port and conn.status == 'LISTEN':
                    try:
                        process = psutil.Process(conn.pid)
                        process.terminate()
                        process.wait(timeout=3)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
        except Exception as e:
            logger.error(f"终止端口进程失败: {e}")
    
    def cleanup(self):
        """清理资源"""
        if self.process:
            try:
                self._stop_frontend()
            except Exception as e:
                logger.error(f"清理前端服务失败: {e}")


# 应用工厂函数
def create_app():
    """创建应用实例"""
    return FrontendManagerApp()
