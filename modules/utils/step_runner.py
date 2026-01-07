#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
录制步骤执行框架
加载并执行用户录制的采集脚本，支持函数导入和codegen脚本适配
"""

import os
import sys
import time
import importlib.util
import subprocess
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path
from playwright.sync_api import Page, Browser, BrowserContext

from modules.core.logger import get_logger

logger = get_logger(__name__)


class StepRunner:
    """录制步骤执行器"""
    
    def __init__(self, browser: Browser):
        """
        初始化步骤执行器
        
        Args:
            browser: Playwright浏览器实例
        """
        self.browser = browser
        self.recordings_base_dir = Path("temp/recordings")
        
        # 确保录制目录存在
        self.recordings_base_dir.mkdir(parents=True, exist_ok=True)
        
    def execute_recorded_steps(self, platform: str, account: Dict[str, Any], 
                             page: Page, date_range: Dict[str, Any] = None,
                             step_type: str = "collection") -> Dict[str, Any]:
        """
        执行录制的步骤
        
        Args:
            platform: 平台名称 (miaoshou/shopee/tiktok)
            account: 账号信息
            page: 已登录的页面对象
            date_range: 日期范围 {"start_date": "2025-01-01", "end_date": "2025-01-31"}
            step_type: 步骤类型 (collection/navigation/export)
            
        Returns:
            Dict: 执行结果
        """
        result = {
            "success": False,
            "platform": platform,
            "step_type": step_type,
            "executed_steps": [],
            "downloaded_files": [],
            "error": None,
            "execution_time": 0
        }
        
        start_time = time.time()
        
        try:
            logger.info(f"🎬 开始执行{platform}平台的{step_type}录制步骤")
            
            # 1. 查找录制脚本
            script_files = self._find_recording_scripts(platform, step_type)
            if not script_files:
                result["error"] = f"未找到{platform}平台的{step_type}录制脚本"
                logger.warning(f"⚠️ {result['error']}")
                return result
            
            # 2. 执行找到的脚本
            for script_file in script_files:
                step_result = self._execute_single_script(
                    script_file, platform, account, page, date_range
                )
                
                result["executed_steps"].append({
                    "script": str(script_file),
                    "success": step_result["success"],
                    "error": step_result.get("error"),
                    "downloaded_files": step_result.get("downloaded_files", [])
                })
                
                # 合并下载文件列表
                result["downloaded_files"].extend(step_result.get("downloaded_files", []))
                
                # 如果某个步骤失败，记录但继续执行其他步骤
                if not step_result["success"]:
                    logger.warning(f"⚠️ 步骤执行失败: {script_file}")
            
            # 3. 判断整体成功状态
            successful_steps = [step for step in result["executed_steps"] if step["success"]]
            if successful_steps:
                result["success"] = True
                logger.info(f"✅ 录制步骤执行完成，成功{len(successful_steps)}/{len(result['executed_steps'])}个步骤")
            else:
                result["error"] = "所有录制步骤都执行失败"
                logger.error(f"❌ {result['error']}")
            
        except Exception as e:
            result["error"] = f"录制步骤执行异常: {e}"
            logger.error(f"❌ {result['error']}")
        
        finally:
            result["execution_time"] = time.time() - start_time
            
        return result
    
    def _find_recording_scripts(self, platform: str, step_type: str) -> List[Path]:
        """查找录制脚本文件"""
        try:
            platform_dir = self.recordings_base_dir / platform.lower()
            if not platform_dir.exists():
                logger.info(f"📁 创建录制目录: {platform_dir}")
                platform_dir.mkdir(parents=True, exist_ok=True)
                return []
            
            # 查找匹配的脚本文件
            script_patterns = [
                f"*{step_type}*.py",
                f"*collection*.py",
                f"*export*.py",
                f"*data*.py",
                "*.py"  # 兜底匹配所有Python文件
            ]
            
            found_scripts = []
            for pattern in script_patterns:
                scripts = list(platform_dir.glob(pattern))
                found_scripts.extend(scripts)
                if scripts:
                    break  # 找到匹配的就停止
            
            # 去重并排序
            unique_scripts = list(set(found_scripts))
            unique_scripts.sort(key=lambda x: x.stat().st_mtime, reverse=True)  # 按修改时间倒序
            
            logger.info(f"🔍 找到{len(unique_scripts)}个录制脚本: {[s.name for s in unique_scripts]}")
            return unique_scripts
            
        except Exception as e:
            logger.error(f"❌ 查找录制脚本失败: {e}")
            return []
    
    def _execute_single_script(self, script_file: Path, platform: str, 
                             account: Dict, page: Page, date_range: Dict = None) -> Dict[str, Any]:
        """执行单个录制脚本"""
        result = {
            "success": False,
            "downloaded_files": [],
            "error": None
        }
        
        try:
            logger.info(f"📜 执行录制脚本: {script_file.name}")
            
            # 尝试作为模块导入并执行
            if self._try_import_and_execute(script_file, account, page, date_range, result):
                return result
            
            # 如果导入失败，尝试作为独立脚本执行
            if self._try_subprocess_execute(script_file, account, page, result):
                return result
            
            result["error"] = "脚本执行失败：无法导入或运行"
            
        except Exception as e:
            result["error"] = f"脚本执行异常: {e}"
            logger.error(f"❌ {result['error']}")
        
        return result
    
    def _try_import_and_execute(self, script_file: Path, account: Dict, 
                              page: Page, date_range: Dict, result: Dict) -> bool:
        """尝试导入脚本并执行标准函数"""
        try:
            # 动态导入脚本模块
            spec = importlib.util.spec_from_file_location("recorded_script", str(script_file))
            if not spec or not spec.loader:
                return False
            
            module = importlib.util.module_from_spec(spec)
            sys.modules["recorded_script"] = module
            spec.loader.exec_module(module)
            
            # 查找可执行的函数
            executable_functions = [
                "run_step",           # 推荐的标准接口
                "execute_collection", # 采集函数
                "run_collection",     # 运行采集
                "main",              # 主函数
                "run"                # 运行函数
            ]
            
            executed = False
            for func_name in executable_functions:
                if hasattr(module, func_name):
                    func = getattr(module, func_name)
                    if callable(func):
                        logger.info(f"🎯 调用函数: {func_name}")
                        
                        # 尝试不同的参数组合
                        try:
                            # 标准接口：run_step(page, account, date_range, context)
                            if func_name == "run_step":
                                context = {"platform": account.get("platform"), "step_type": "collection"}
                                func_result = func(page, account, date_range or {}, context)
                            else:
                                # 其他函数尝试传入page参数
                                func_result = func(page)
                            
                            # 处理函数返回结果
                            if isinstance(func_result, dict):
                                result.update(func_result)
                            else:
                                result["success"] = bool(func_result)
                            
                            executed = True
                            logger.info(f"✅ 函数{func_name}执行完成")
                            break
                            
                        except TypeError:
                            # 参数不匹配，尝试无参数调用
                            try:
                                func_result = func()
                                result["success"] = bool(func_result)
                                executed = True
                                logger.info(f"✅ 函数{func_name}(无参数)执行完成")
                                break
                            except Exception as e:
                                logger.warning(f"⚠️ 函数{func_name}调用失败: {e}")
                                continue
                        
                        except Exception as e:
                            logger.warning(f"⚠️ 函数{func_name}执行失败: {e}")
                            continue
            
            if not executed:
                logger.warning("⚠️ 未找到可执行的函数")
                return False
            
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ 脚本导入失败: {e}")
            return False
    
    def _try_subprocess_execute(self, script_file: Path, account: Dict, 
                              page: Page, result: Dict) -> bool:
        """尝试作为独立脚本执行（适用于codegen生成的脚本）"""
        try:
            logger.info(f"🔄 尝试子进程执行脚本: {script_file.name}")
            
            # 注意：这种方式无法传递page对象，适用于完全独立的脚本
            # 主要用于codegen生成的完整脚本
            
            cmd = [sys.executable, str(script_file)]
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                cwd=str(script_file.parent)
            )
            
            if process.returncode == 0:
                result["success"] = True
                logger.info(f"✅ 子进程脚本执行成功")
                
                # 尝试从输出中提取信息
                if process.stdout:
                    logger.info(f"📄 脚本输出: {process.stdout[:500]}...")
                
                return True
            else:
                logger.warning(f"⚠️ 子进程脚本执行失败，返回码: {process.returncode}")
                if process.stderr:
                    logger.warning(f"错误输出: {process.stderr[:500]}...")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("❌ 脚本执行超时")
            return False
        except Exception as e:
            logger.warning(f"⚠️ 子进程执行失败: {e}")
            return False
    
    def list_available_scripts(self, platform: str = None) -> Dict[str, List[str]]:
        """列出可用的录制脚本"""
        try:
            scripts_info = {}
            
            if platform:
                platforms = [platform.lower()]
            else:
                # 列出所有平台
                platforms = [d.name for d in self.recordings_base_dir.iterdir() if d.is_dir()]
            
            for plat in platforms:
                platform_dir = self.recordings_base_dir / plat
                if platform_dir.exists():
                    scripts = [f.name for f in platform_dir.glob("*.py")]
                    scripts_info[plat] = scripts
                else:
                    scripts_info[plat] = []
            
            return scripts_info
            
        except Exception as e:
            logger.error(f"❌ 列出录制脚本失败: {e}")
            return {}
    
    def create_all_platform_templates(self) -> Dict[str, Path]:
        """为所有支持的平台创建录制脚本模板"""
        templates = {}
        platforms = ["miaoshou", "shopee", "tiktok"]

        for platform in platforms:
            try:
                template_path = self.create_script_template(platform, "collection")
                templates[platform] = template_path
                logger.info(f"✅ 创建{platform}平台模板: {template_path}")
            except Exception as e:
                logger.error(f"❌ 创建{platform}平台模板失败: {e}")

        return templates

    def create_script_template(self, platform: str, step_type: str = "collection") -> Path:
        """创建录制脚本模板"""
        try:
            platform_dir = self.recordings_base_dir / platform.lower()
            platform_dir.mkdir(parents=True, exist_ok=True)
            
            template_file = platform_dir / f"{step_type}_template.py"
            
            template_content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
{platform.upper()}平台{step_type}录制脚本模板
请使用Playwright Inspector录制后替换此模板内容
"""

def run_step(page, account, date_range, context):
    """
    标准录制步骤接口
    
    Args:
        page: Playwright页面对象（已登录）
        account: 账号信息字典
        date_range: 日期范围 {{"start_date": "2025-01-01", "end_date": "2025-01-31"}}
        context: 上下文信息 {{"platform": "{platform}", "step_type": "{step_type}"}}
        
    Returns:
        Dict: {{"success": bool, "notes": str, "downloaded_files": []}}
    """
    try:
        print(f"🎬 开始执行{platform}平台{step_type}步骤")
        
        # TODO: 在这里添加您录制的操作步骤
        # 示例：
        # page.click("button:has-text('导出')")
        # page.wait_for_download()
        
        return {{
            "success": True,
            "notes": f"{platform}平台{step_type}步骤执行完成",
            "downloaded_files": []
        }}
        
    except Exception as e:
        print(f"❌ 步骤执行失败: {{e}}")
        return {{
            "success": False,
            "error": str(e)
        }}


if __name__ == "__main__":
    print("这是一个录制脚本模板，请使用StepRunner调用run_step函数")
'''
            
            template_file.write_text(template_content, encoding='utf-8')
            logger.info(f"✅ 创建录制脚本模板: {template_file}")
            
            return template_file
            
        except Exception as e:
            logger.error(f"❌ 创建脚本模板失败: {e}")
            raise
