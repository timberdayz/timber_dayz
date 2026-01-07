#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Web界面管理器

统一管理Streamlit和Vue.js前端应用
"""

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger

class WebInterfaceManager:
    """Web界面管理器"""
    
    def __init__(self):
        """初始化Web界面管理器"""
        self.streamlit_apps = {}
        self.vue_apps = {}
        self.available_apps = {}
        self.running_processes = {}
        self._discover_streamlit_apps()
        self._discover_vue_apps()
    
    def _discover_streamlit_apps(self):
        """发现Streamlit应用"""
        try:
            streamlit_dir = Path("frontend_streamlit")
            if streamlit_dir.exists():
                for page_file in streamlit_dir.glob("pages/*.py"):
                    app_name = page_file.stem
                    self.streamlit_apps[app_name] = {
                        "type": "streamlit",
                        "path": str(page_file),
                        "name": app_name,
                        "description": f"Streamlit页面: {app_name}"
                    }
                    self.available_apps[app_name] = self.streamlit_apps[app_name]
            
            logger.info(f"发现 {len(self.streamlit_apps)} 个Streamlit应用")
        except Exception as e:
            logger.error(f"发现Streamlit应用失败: {e}")
    
    def _discover_vue_apps(self):
        """发现Vue.js应用"""
        try:
            # 查找modules/apps下的Vue.js应用
            apps_dir = Path("modules/apps")
            if apps_dir.exists():
                for app_dir in apps_dir.iterdir():
                    if app_dir.is_dir() and (app_dir / "frontend").exists():
                        frontend_dir = app_dir / "frontend"
                        package_json = frontend_dir / "package.json"
                        
                        if package_json.exists():
                            app_name = app_dir.name
                            self.vue_apps[app_name] = {
                                "type": "vue",
                                "path": str(frontend_dir),
                                "name": app_name,
                                "description": f"Vue.js应用: {app_name}",
                                "package_json": str(package_json)
                            }
                            self.available_apps[app_name] = self.vue_apps[app_name]
            
            logger.info(f"发现 {len(self.vue_apps)} 个Vue.js应用")
        except Exception as e:
            logger.error(f"发现Vue.js应用失败: {e}")
    
    def list_apps(self) -> Dict[str, Dict[str, Any]]:
        """列出所有可用应用"""
        return self.available_apps.copy()
    
    def start_streamlit_app(self, app_name: str, port: int = 8501) -> bool:
        """启动Streamlit应用"""
        try:
            if app_name not in self.streamlit_apps:
                logger.error(f"Streamlit应用不存在: {app_name}")
                return False
            
            app_info = self.streamlit_apps[app_name]
            
            # 检查是否已经在运行
            if app_name in self.running_processes:
                logger.warning(f"应用 {app_name} 已经在运行")
                return True
            
            # 启动Streamlit应用
            cmd = [
                "streamlit", "run", app_info["path"],
                "--server.port", str(port),
                "--server.address", "0.0.0.0",
                "--server.headless", "true"
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.running_processes[app_name] = {
                "process": process,
                "type": "streamlit",
                "port": port,
                "started_at": time.time()
            }
            
            logger.info(f"启动Streamlit应用 {app_name} 在端口 {port}")
            return True
            
        except Exception as e:
            logger.error(f"启动Streamlit应用失败 {app_name}: {e}")
            return False
    
    def start_vue_app(self, app_name: str, port: int = 5173) -> bool:
        """启动Vue.js应用"""
        try:
            if app_name not in self.vue_apps:
                logger.error(f"Vue.js应用不存在: {app_name}")
                return False
            
            app_info = self.vue_apps[app_name]
            frontend_dir = Path(app_info["path"])
            
            # 检查是否已经在运行
            if app_name in self.running_processes:
                logger.warning(f"应用 {app_name} 已经在运行")
                return True
            
            # 检查Node.js和npm
            try:
                subprocess.run(["node", "-v"], check=True, capture_output=True)
                subprocess.run(["npm", "-v"], check=True, capture_output=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.error("Node.js或npm未安装，无法启动Vue.js应用")
                return False
            
            # 检查并安装依赖
            node_modules = frontend_dir / "node_modules"
            if not node_modules.exists():
                logger.info(f"安装Vue.js应用 {app_name} 的依赖...")
                install_process = subprocess.run(
                    ["npm", "install"],
                    cwd=frontend_dir,
                    capture_output=True,
                    text=True
                )
                if install_process.returncode != 0:
                    logger.error(f"安装依赖失败: {install_process.stderr}")
                    return False
            
            # 启动Vue.js开发服务器
            cmd = ["npm", "run", "dev", "--", "--port", str(port), "--host", "0.0.0.0"]
            
            process = subprocess.Popen(
                cmd,
                cwd=frontend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.running_processes[app_name] = {
                "process": process,
                "type": "vue",
                "port": port,
                "started_at": time.time()
            }
            
            logger.info(f"启动Vue.js应用 {app_name} 在端口 {port}")
            return True
            
        except Exception as e:
            logger.error(f"启动Vue.js应用失败 {app_name}: {e}")
            return False
    
    def start_backend_api(self, app_name: str, port: int = 8000) -> bool:
        """启动后端API服务"""
        try:
            # 查找对应的后端API
            apps_dir = Path("modules/apps")
            backend_dir = apps_dir / app_name / "backend"
            
            if not backend_dir.exists():
                logger.error(f"后端API不存在: {backend_dir}")
                return False
            
            main_py = backend_dir / "main.py"
            if not main_py.exists():
                logger.error(f"后端主文件不存在: {main_py}")
                return False
            
            # 检查是否已经在运行
            backend_key = f"{app_name}_backend"
            if backend_key in self.running_processes:
                logger.warning(f"后端API {app_name} 已经在运行")
                return True
            
            # 启动FastAPI应用
            cmd = ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port)]
            
            process = subprocess.Popen(
                cmd,
                cwd=backend_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.running_processes[backend_key] = {
                "process": process,
                "type": "backend",
                "port": port,
                "started_at": time.time()
            }
            
            logger.info(f"启动后端API {app_name} 在端口 {port}")
            return True
            
        except Exception as e:
            logger.error(f"启动后端API失败 {app_name}: {e}")
            return False
    
    def stop_app(self, app_name: str) -> bool:
        """停止应用"""
        try:
            if app_name not in self.running_processes:
                logger.warning(f"应用 {app_name} 未在运行")
                return False
            
            process_info = self.running_processes[app_name]
            process = process_info["process"]
            
            # 终止进程
            process.terminate()
            
            # 等待进程结束
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            
            del self.running_processes[app_name]
            logger.info(f"停止应用 {app_name}")
            return True
            
        except Exception as e:
            logger.error(f"停止应用失败 {app_name}: {e}")
            return False
    
    def stop_all_apps(self):
        """停止所有应用"""
        for app_name in list(self.running_processes.keys()):
            self.stop_app(app_name)
    
    def get_app_status(self, app_name: str) -> Optional[Dict[str, Any]]:
        """获取应用状态"""
        if app_name not in self.running_processes:
            return None
        
        process_info = self.running_processes[app_name]
        process = process_info["process"]
        
        return {
            "name": app_name,
            "type": process_info["type"],
            "port": process_info["port"],
            "status": "running" if process.poll() is None else "stopped",
            "started_at": process_info["started_at"],
            "uptime": time.time() - process_info["started_at"]
        }
    
    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有应用状态"""
        status = {}
        for app_name in self.running_processes:
            status[app_name] = self.get_app_status(app_name)
        return status
    
    def start_vue_field_mapping_system(self) -> bool:
        """启动Vue字段映射系统（前端+后端）"""
        try:
            # 启动后端API
            if not self.start_backend_api("vue_field_mapping", 8000):
                return False
            
            # 等待后端启动
            time.sleep(2)
            
            # 启动Vue.js前端
            if not self.start_vue_app("vue_field_mapping", 5173):
                # 如果前端启动失败，停止后端
                self.stop_app("vue_field_mapping_backend")
                return False
            
            logger.info("Vue字段映射系统启动成功")
            logger.info("后端API: http://localhost:8000")
            logger.info("前端界面: http://localhost:5173")
            return True
            
        except Exception as e:
            logger.error(f"启动Vue字段映射系统失败: {e}")
            return False

# 全局实例
_web_manager = None

def get_web_interface_manager() -> WebInterfaceManager:
    """获取Web界面管理器实例"""
    global _web_manager
    if _web_manager is None:
        _web_manager = WebInterfaceManager()
    return _web_manager

def start_vue_field_mapping():
    """启动Vue字段映射系统的便捷函数"""
    manager = get_web_interface_manager()
    return manager.start_vue_field_mapping_system()

if __name__ == "__main__":
    # 测试Web界面管理器
    manager = get_web_interface_manager()
    
    print("可用应用:")
    for name, info in manager.list_apps().items():
        print(f"  - {name}: {info['description']}")
    
    print("\n启动Vue字段映射系统...")
    if manager.start_vue_field_mapping_system():
        print("✅ 系统启动成功")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n停止所有应用...")
            manager.stop_all_apps()
            print("✅ 所有应用已停止")
    else:
        print("❌ 系统启动失败")
