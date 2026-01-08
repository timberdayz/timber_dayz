"""
后端API管理应用 - 管理FastAPI后端服务
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


class BackendManagerApp(BaseApplication):
    """后端API管理应用"""
    
    # 类级元数据（避免实例化副作用）
    APP_ID = "backend_manager"
    NAME = "后端API管理"
    VERSION = "1.0.0"
    DESCRIPTION = "管理FastAPI后端服务，支持启动、停止、重启API服务器"
    
    def __init__(self):
        """初始化后端管理应用"""
        super().__init__()
        self.process: Optional[subprocess.Popen] = None
        self.backend_dir = Path(__file__).parent.parent.parent.parent / "backend"
        self.port = 8000
        self.url = f"http://localhost:{self.port}"
        self.api_docs_url = f"{self.url}/api/docs"
        
    def get_metadata(self):
        """获取应用元数据"""
        return {
            "name": self.NAME,
            "version": self.VERSION,
            "description": self.DESCRIPTION,
            "app_id": self.APP_ID
        }
    
    def run(self):
        """运行后端管理应用"""
        logger.info(f"启动 {self.NAME}")
        
        while True:
            self._print_menu()
            choice = input("\n请选择操作 (0-6): ").strip()
            
            if choice == "1":
                self._start_backend()
            elif choice == "2":
                self._stop_backend()
            elif choice == "3":
                self._restart_backend()
            elif choice == "4":
                self._check_status()
            elif choice == "5":
                self._open_api_docs()
            elif choice == "6":
                self._test_api()
            elif choice == "0":
                if self.process:
                    print("\n[WARN]  后端服务正在运行，是否停止? (y/n): ", end="")
                    if input().strip().lower() == 'y':
                        self._stop_backend()
                break
            else:
                print("[FAIL] 无效选择，请重试")
            
            if choice != "0":
                input("\n按回车键继续...")
    
    def _print_menu(self):
        """打印菜单"""
        status = "[GREEN] 运行中" if self._is_backend_running() else "[WHITE] 未运行"
        
        print("\n" + "=" * 60)
        print(f"[GEAR] {self.NAME} v{self.VERSION}")
        print("=" * 60)
        print(f"[LIST] {self.DESCRIPTION}")
        print(f"[LINK] API地址: {self.url}")
        print(f"[DOCS] API文档: {self.api_docs_url}")
        print(f"[DIR] 后端目录: {self.backend_dir}")
        print(f"[o] 状态: {status}")
        print("=" * 60)
        print("\n[GEAR] 后端管理 - 功能菜单")
        print("-" * 40)
        print("1. [START] 启动后端服务")
        print("2. [STOP]  停止后端服务")
        print("3. [RETRY] 重启后端服务")
        print("4. [DATA] 查看运行状态")
        print("5. [DOCS] 打开API文档")
        print("6. [TEST] 测试API连接")
        print("0. [BACK] 返回主菜单")
    
    def _check_python(self) -> bool:
        """检查Python环境"""
        try:
            result = subprocess.run(
                [sys.executable, "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                print(f"[OK] Python版本: {result.stdout.strip()}")
                return True
            return False
        except Exception as e:
            logger.error(f"检查Python失败: {e}")
            return False
    
    def _start_backend(self):
        """启动后端服务"""
        if self._is_backend_running():
            print("[WARN]  后端服务已经在运行中")
            return
        
        print("\n[START] 启动FastAPI后端服务...")
        print("=" * 60)
        
        # 检查后端目录
        if not self.backend_dir.exists():
            print(f"[FAIL] 后端目录不存在: {self.backend_dir}")
            return
        
        # 检查Python
        if not self._check_python():
            return
        
        # 检查依赖
        requirements_file = self.backend_dir / "requirements.txt"
        if not requirements_file.exists():
            print("[FAIL] requirements.txt文件不存在")
            return
        
        # 检查是否需要安装依赖
        print("[PKG] 检查依赖...")
        try:
            # 尝试导入fastapi，如果失败则需要安装依赖
            result = subprocess.run(
                [sys.executable, "-c", "import fastapi"],
                capture_output=True,
                timeout=5
            )
            
            if result.returncode != 0:
                print("[PKG] 首次运行，正在安装依赖...")
                print("[WAIT] 这可能需要几分钟，请耐心等待...")
                
                install_result = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
                    cwd=self.backend_dir,
                    capture_output=True,
                    text=True,
                    timeout=600  # 10分钟超时
                )
                
                if install_result.returncode == 0:
                    print("[OK] 依赖安装完成")
                else:
                    print(f"[FAIL] 依赖安装失败")
                    print(f"错误信息: {install_result.stderr[:500]}")  # 只显示前500字符
                    return
        except subprocess.TimeoutExpired:
            print("[FAIL] 依赖安装超时")
            return
        except Exception as e:
            print(f"[FAIL] 检查依赖失败: {e}")
            return
        
        # 启动FastAPI服务
        try:
            print("\n[STAR] 启动FastAPI服务器...")
            
            # 构建启动命令
            cmd = f'"{sys.executable}" -m uvicorn main:app --host 0.0.0.0 --port {self.port} --reload'
            
            # 使用Popen以非阻塞方式启动
            self.process = subprocess.Popen(
                cmd,
                cwd=self.backend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=True,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0
            )
            
            # 等待服务启动
            print("[WAIT] 等待服务启动...")
            time.sleep(3)
            
            if self._is_backend_running():
                print(f"[OK] 后端服务启动成功")
                print(f"[LINK] API地址: {self.url}")
                print(f"[DOCS] API文档: {self.api_docs_url}")
                print("\n[TIP] 提示: 选择选项5查看API文档")
            else:
                print("[FAIL] 后端服务启动失败")
                if self.process:
                    # 尝试获取错误信息
                    try:
                        stdout, stderr = self.process.communicate(timeout=1)
                        if stderr:
                            print(f"错误信息: {stderr[:500]}")
                    except subprocess.TimeoutExpired:
                        pass
                
        except Exception as e:
            print(f"[FAIL] 启动失败: {e}")
            logger.error(f"启动后端服务失败: {e}")
    
    def _stop_backend(self):
        """停止后端服务"""
        if not self._is_backend_running():
            print("[WARN]  后端服务未运行")
            return
        
        print("\n[STOP]  正在停止后端服务...")
        
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
                print("[OK] 后端服务已停止")
            
            # 确保端口被释放
            self._kill_port_process(self.port)
            
        except Exception as e:
            print(f"[FAIL] 停止失败: {e}")
            logger.error(f"停止后端服务失败: {e}")
    
    def _restart_backend(self):
        """重启后端服务"""
        print("\n[RETRY] 重启后端服务...")
        self._stop_backend()
        time.sleep(2)
        self._start_backend()
    
    def _is_backend_running(self) -> bool:
        """检查后端服务是否运行"""
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
        print("\n[DATA] 后端服务状态")
        print("=" * 60)
        
        is_running = self._is_backend_running()
        print(f"[o] 状态: {'[GREEN] 运行中' if is_running else '[WHITE] 未运行'}")
        print(f"[LINK] API地址: {self.url}")
        print(f"[DOCS] API文档: {self.api_docs_url}")
        print(f"[DIR] 后端目录: {self.backend_dir}")
        print(f"[PLUG] 端口: {self.port}")
        
        if is_running:
            print(f"[ID] 进程ID: {self.process.pid if self.process else '未知'}")
            
            # 检查端口连接
            connections = []
            for conn in psutil.net_connections():
                if conn.laddr.port == self.port:
                    connections.append(conn)
            
            print(f"[LINK] 连接数: {len(connections)}")
            
            # 测试API健康检查
            try:
                import urllib.request
                with urllib.request.urlopen(f"{self.url}/health", timeout=2) as response:
                    if response.status == 200:
                        print("[OK] API健康检查: 正常")
                    else:
                        print(f"[WARN]  API健康检查: HTTP {response.status}")
            except Exception as e:
                print(f"[FAIL] API健康检查: 失败 - {e}")
    
    def _open_api_docs(self):
        """打开API文档"""
        if not self._is_backend_running():
            print("[WARN]  后端服务未运行，请先启动服务")
            return
        
        print(f"\n[DOCS] 在浏览器中打开API文档: {self.api_docs_url}")
        try:
            webbrowser.open(self.api_docs_url)
            print("[OK] 浏览器已打开")
        except Exception as e:
            print(f"[FAIL] 打开浏览器失败: {e}")
            print(f"[TIP] 请手动访问: {self.api_docs_url}")
    
    def _test_api(self):
        """测试API连接"""
        print("\n[TEST] 测试API连接...")
        print("=" * 60)
        
        if not self._is_backend_running():
            print("[FAIL] 后端服务未运行")
            return
        
        # 测试健康检查端点
        try:
            import urllib.request
            import json
            
            print(f"[LINK] 测试: {self.url}/health")
            with urllib.request.urlopen(f"{self.url}/health", timeout=5) as response:
                data = json.loads(response.read())
                print(f"[OK] 健康检查成功")
                print(f"[DATA] 响应数据: {json.dumps(data, indent=2, ensure_ascii=False)}")
        except Exception as e:
            print(f"[FAIL] 测试失败: {e}")
    
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
                self._stop_backend()
            except Exception as e:
                logger.error(f"清理后端服务失败: {e}")


# 应用工厂函数
def create_app():
    """创建应用实例"""
    return BackendManagerApp()
