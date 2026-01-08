#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Vue.js字段映射审核应用

现代化的Vue.js前端 + FastAPI后端架构
解决Streamlit死循环问题
"""

import os
import sys
import subprocess
import threading
import time
import webbrowser
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

from modules.core.base_app import BaseApplication


class VueFieldMappingApp(BaseApplication):
    """Vue.js字段映射审核应用"""
    
    def __init__(self):
        super().__init__()
        self.app_id = "vue_field_mapping"
        self.name = "Vue字段映射审核"
        self.version = "1.0.0"
        self.description = "基于Vue.js的现代化字段映射审核系统，解决Streamlit死循环问题"
        
        # 服务状态
        self.backend_process = None
        self.frontend_process = None
        self.backend_port = 8000
        self.frontend_port = 5173
        
        # 路径配置
        self.frontend_dir = Path("modules/apps/vue_field_mapping/frontend")
        self.backend_file = Path("modules/apps/vue_field_mapping/backend/main.py")
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            # 检查前端目录
            frontend_exists = self.frontend_dir.exists()
            
            # 检查后端文件
            backend_exists = self.backend_file.exists()
            
            # 检查依赖
            dependencies = self._check_dependencies()
            
            return {
                "status": "healthy" if frontend_exists and backend_exists else "degraded",
                "frontend_dir": str(self.frontend_dir),
                "frontend_exists": frontend_exists,
                "backend_file": str(self.backend_file),
                "backend_exists": backend_exists,
                "dependencies": dependencies,
                "backend_port": self.backend_port,
                "frontend_port": self.frontend_port
            }
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    def _check_dependencies(self) -> Dict[str, bool]:
        """检查依赖"""
        dependencies = {}
        
        # 检查Python依赖
        try:
            import fastapi
            import uvicorn
            dependencies["fastapi"] = True
            dependencies["uvicorn"] = True
        except ImportError:
            dependencies["fastapi"] = False
            dependencies["uvicorn"] = False
        
        # 检查Node.js (多种方式尝试)
        nodejs_found = False
        npm_found = False
        
        # 方法1: 直接运行命令
        try:
            result = subprocess.run('node --version', capture_output=True, text=True, shell=True, timeout=5)
            if result.returncode == 0:
                nodejs_found = True
        except:
            pass
        
        # 方法2: 检查常见安装路径
        if not nodejs_found:
            common_paths = [
                r"C:\Program Files\nodejs\node.exe",
                r"C:\Program Files (x86)\nodejs\node.exe",
                os.path.expanduser(r"~\AppData\Local\Programs\nodejs\node.exe"),
                os.path.expanduser(r"~\scoop\apps\nodejs\current\node.exe"),
            ]
            for path in common_paths:
                if os.path.exists(path):
                    nodejs_found = True
                    break
        
        dependencies["nodejs"] = nodejs_found
        
        # 检查npm (多种方式尝试)
        try:
            result = subprocess.run('npm --version', capture_output=True, text=True, shell=True, timeout=5)
            if result.returncode == 0:
                npm_found = True
        except:
            pass
        
        # 方法2: 检查常见npm路径
        if not npm_found:
            common_npm_paths = [
                r"C:\Program Files\nodejs\npm.cmd",
                r"C:\Program Files (x86)\nodejs\npm.cmd",
                os.path.expanduser(r"~\AppData\Roaming\npm\npm.cmd"),
                os.path.expanduser(r"~\scoop\apps\nodejs\current\npm.cmd"),
            ]
            for path in common_npm_paths:
                if os.path.exists(path):
                    npm_found = True
                    break
        
        dependencies["npm"] = npm_found
        
        return dependencies
    
    def run(self) -> None:
        """运行应用"""
        logger.info(f"[START] 启动 {self.name} v{self.version}")
        
        # 健康检查
        health = self.health_check()
        if health["status"] == "unhealthy":
            logger.error(f"[FAIL] 应用不健康: {health.get('error', '未知错误')}")
            return
        
        # 显示依赖状态
        dependencies = health["dependencies"]
        logger.info("[LIST] 依赖检查:")
        for dep, status in dependencies.items():
            status_icon = "[OK]" if status else "[FAIL]"
            logger.info(f"   {status_icon} {dep}")
        
        # 检查关键依赖
        if not dependencies.get("fastapi") or not dependencies.get("uvicorn"):
            logger.error("[FAIL] 缺少Python依赖，请运行: pip install fastapi uvicorn")
            return
        
        if not dependencies.get("nodejs") or not dependencies.get("npm"):
            logger.error("[FAIL] 无法检测到Node.js依赖")
            logger.info("请尝试以下解决方案:")
            logger.info("  1. 如果刚安装Node.js，请重启VSCode/终端")
            logger.info("  2. 在新的PowerShell窗口中运行: node --version")
            logger.info("  3. 如果命令有效，请关闭VSCode并重新打开")
            logger.info("  4. 或者使用独立终端运行此程序")
            logger.info("")
            logger.info("[TIP] 快速验证: 打开新的PowerShell窗口，运行:")
            logger.info("   node --version")
            logger.info("   npm --version")
            return
        
        # 显示菜单
        self._show_menu()
        
        # 等待用户选择
        while True:
            try:
                choice = input("\n请选择操作 (0-5): ").strip()
                
                if choice == "0":
                    self._stop_services()
                    logger.info("[HI] 退出Vue字段映射审核系统")
                    break
                elif choice == "1":
                    self._start_backend()
                elif choice == "2":
                    self._start_frontend()
                elif choice == "3":
                    self._start_full_system()
                elif choice == "4":
                    self._show_status()
                elif choice == "5":
                    self._show_menu()
                else:
                    logger.warning("[FAIL] 无效选择，请重新输入")
                    
            except KeyboardInterrupt:
                logger.info("\n[STOP] 用户中断，正在停止服务...")
                self._stop_services()
                break
            except Exception as e:
                logger.error(f"[FAIL] 操作失败: {e}")
    
    def _show_menu(self) -> None:
        """显示菜单"""
        print("\n" + "="*60)
        print(f"[TARGET] {self.name} v{self.version}")
        print("="*60)
        print("[LIST] 功能:")
        print("   [OK] Vue.js现代化界面（无死循环问题）")
        print("   [OK] FastAPI高性能后端")
        print("   [OK] 智能字段映射")
        print("   [OK] 数据预览和入库")
        print("="*60)
        print("[TOOL] 操作选项:")
        print("  1. [START] 启动后端API服务")
        print("  2. [ART] 启动前端界面")
        print("  3. [STAR] 启动完整系统")
        print("  4. [DATA] 查看服务状态")
        print("  5. [LIST] 显示菜单")
        print("  0. [FAIL] 退出")
        print("="*60)
    
    def _start_backend(self) -> None:
        """启动后端服务"""
        if self.backend_process and self.backend_process.poll() is None:
            logger.info("[OK] 后端服务已在运行")
            return
        
        try:
            logger.info(f"[START] 启动后端API服务 (端口 {self.backend_port})...")
            
            # 启动FastAPI服务
            self.backend_process = subprocess.Popen([
                sys.executable, '-m', 'uvicorn',
                f'modules.apps.vue_field_mapping.backend.main:app',
                '--host', '0.0.0.0',
                '--port', str(self.backend_port),
                '--reload'
            ])
            
            # 等待服务启动
            time.sleep(3)
            
            if self.backend_process.poll() is None:
                logger.info("[OK] 后端服务启动成功")
                logger.info(f"[SIGNAL] API地址: http://localhost:{self.backend_port}")
                logger.info(f"[DOCS] API文档: http://localhost:{self.backend_port}/docs")
            else:
                logger.error("[FAIL] 后端服务启动失败")
                
        except Exception as e:
            logger.error(f"[FAIL] 启动后端服务失败: {e}")
    
    def _start_frontend(self) -> None:
        """启动前端服务"""
        try:
            # 统一入口：不再启动模块内置前端，直接跳转到主前端的字段映射页面
            target_url = 'http://localhost:5173/#/field-mapping'
            logger.info("[LINK] 统一入口已启用：优先检测并打开主前端的字段映射页面")

            # 检测5173端口是否有服务在跑
            import socket
            s = socket.socket()
            s.settimeout(0.5)
            running = False
            try:
                s.connect(('127.0.0.1', 5173))
                running = True
            except Exception:
                running = False
            finally:
                try:
                    s.close()
                except Exception:
                    pass

            if not running:
                logger.info("[GEAR] 检测到主前端未运行，尝试在 frontend/ 下启动 npm run dev ...")
                try:
                    subprocess.Popen('npm run dev', cwd=Path('frontend'), shell=True)
                    time.sleep(3)
                except Exception as ee:
                    logger.warning(f"[WARN] 启动主前端失败: {ee}")

            webbrowser.open(target_url)
            logger.info(f"[WEB] 已打开: {target_url}")
            logger.info("[i] 如需独立调试模块前端，可手动进入 modules/apps/vue_field_mapping/frontend 运行 npm run dev")
        except Exception as e:
            logger.warning(f"[WARN] 无法打开主前端: {e}")
            # 兜底：如果主前端未运行，仍尝试启动模块内置前端
            try:
                if not self.frontend_dir.exists():
                    logger.error("[FAIL] 前端目录不存在，请先初始化前端")
                    return
                node_modules = self.frontend_dir / "node_modules"
                if not node_modules.exists():
                    subprocess.run('npm install', cwd=self.frontend_dir, shell=True, timeout=300)
                self.frontend_process = subprocess.Popen('npm run dev', cwd=self.frontend_dir, shell=True)
                time.sleep(5)
                if self.frontend_process.poll() is None:
                    webbrowser.open(f'http://localhost:{self.frontend_port}')
                    logger.info(f"[WEB] 已启动模块内置前端: http://localhost:{self.frontend_port}")
            except Exception as ee:
                logger.error(f"[FAIL] 启动模块内置前端失败: {ee}")
    
    def _start_full_system(self) -> None:
        """启动完整系统"""
        logger.info("[STAR] 启动完整系统...")
        
        # 启动后端
        self._start_backend()
        
        # 等待后端启动
        time.sleep(2)
        
        # 启动前端
        self._start_frontend()
        
        logger.info("[DONE] 完整系统启动完成！")
        logger.info("[NOTE] 使用说明:")
        logger.info(f"   - 前端界面: http://localhost:{self.frontend_port}")
        logger.info(f"   - 后端API: http://localhost:{self.backend_port}")
        logger.info(f"   - API文档: http://localhost:{self.backend_port}/docs")
        logger.info("   - 按 Ctrl+C 停止服务")
    
    def _show_status(self) -> None:
        """显示服务状态"""
        print("\n[DATA] 服务状态:")
        print("-" * 40)
        
        # 后端状态
        if self.backend_process and self.backend_process.poll() is None:
            print(f"[OK] 后端服务: 运行中 (端口 {self.backend_port})")
        else:
            print(f"[FAIL] 后端服务: 未运行")
        
        # 前端状态
        if self.frontend_process and self.frontend_process.poll() is None:
            print(f"[OK] 前端服务: 运行中 (端口 {self.frontend_port})")
        else:
            print(f"[FAIL] 前端服务: 未运行")
        
        # 健康检查
        health = self.health_check()
        print(f"[LIST] 健康状态: {health['status']}")
        
        # 依赖状态
        dependencies = health["dependencies"]
        print("[PKG] 依赖状态:")
        for dep, status in dependencies.items():
            status_icon = "[OK]" if status else "[FAIL]"
            print(f"   {status_icon} {dep}")
    
    def _stop_services(self) -> None:
        """停止服务"""
        logger.info("[STOP] 正在停止服务...")
        
        if self.frontend_process and self.frontend_process.poll() is None:
            self.frontend_process.terminate()
            logger.info("[OK] 前端服务已停止")
        
        if self.backend_process and self.backend_process.poll() is None:
            self.backend_process.terminate()
            logger.info("[OK] 后端服务已停止")
    
    def get_app_info(self) -> Dict[str, Any]:
        """获取应用信息"""
        return {
            "app_id": self.app_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "health": self.health_check()
        }

