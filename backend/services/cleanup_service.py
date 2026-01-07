"""
清理服务 - Cleanup Service

负责定期清理临时文件和孤儿进程
"""

import os
import shutil
import psutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List

from modules.core.logger import get_logger

logger = get_logger(__name__)


class CleanupService:
    """
    清理服务
    
    功能：
    1. 清理过期的下载文件
    2. 清理过期的截图文件
    3. 清理孤儿浏览器进程
    """
    
    # 默认保留天数
    DEFAULT_DOWNLOADS_RETENTION_DAYS = int(os.getenv('DOWNLOADS_RETENTION_DAYS', 7))
    DEFAULT_SCREENSHOTS_RETENTION_DAYS = int(os.getenv('SCREENSHOTS_RETENTION_DAYS', 30))
    
    # 浏览器进程名称列表
    BROWSER_PROCESS_NAMES = [
        'chrome', 'chromium', 'chromium-browser',
        'chrome.exe', 'chromium.exe',
        'msedge', 'msedge.exe',
        'firefox', 'firefox.exe'
    ]
    
    def __init__(self, temp_dir: str = None):
        """
        初始化清理服务
        
        Args:
            temp_dir: 临时文件目录（默认: temp/）
        """
        if temp_dir is None:
            temp_dir = os.getenv('TEMP_DIR', 'temp')
        
        self.temp_dir = Path(temp_dir)
        self.downloads_dir = self.temp_dir / 'downloads'
        self.screenshots_dir = self.temp_dir / 'screenshots'
        
        logger.info(f"CleanupService initialized: temp_dir={self.temp_dir}")
    
    def cleanup_downloads(self, retention_days: int = None) -> Dict[str, Any]:
        """
        清理过期的下载文件
        
        Args:
            retention_days: 保留天数（默认从环境变量读取）
            
        Returns:
            Dict: 清理结果统计
        """
        if retention_days is None:
            retention_days = self.DEFAULT_DOWNLOADS_RETENTION_DAYS
        
        result = {
            'type': 'downloads',
            'retention_days': retention_days,
            'files_deleted': 0,
            'dirs_deleted': 0,
            'bytes_freed': 0,
            'errors': []
        }
        
        if not self.downloads_dir.exists():
            logger.debug("Downloads directory does not exist, skipping cleanup")
            return result
        
        cutoff_time = datetime.now() - timedelta(days=retention_days)
        
        try:
            # 遍历下载目录（每个任务一个子目录）
            for task_dir in self.downloads_dir.iterdir():
                if not task_dir.is_dir():
                    continue
                
                # 检查目录修改时间
                mtime = datetime.fromtimestamp(task_dir.stat().st_mtime)
                
                if mtime < cutoff_time:
                    try:
                        # 统计大小
                        dir_size = sum(f.stat().st_size for f in task_dir.rglob('*') if f.is_file())
                        file_count = sum(1 for f in task_dir.rglob('*') if f.is_file())
                        
                        # 删除整个目录
                        shutil.rmtree(task_dir)
                        
                        result['dirs_deleted'] += 1
                        result['files_deleted'] += file_count
                        result['bytes_freed'] += dir_size
                        
                        logger.debug(f"Deleted expired download dir: {task_dir.name}")
                    
                    except Exception as e:
                        result['errors'].append(f"{task_dir.name}: {str(e)}")
                        logger.error(f"Failed to delete {task_dir}: {e}")
        
        except Exception as e:
            result['errors'].append(f"Scan error: {str(e)}")
            logger.error(f"Failed to scan downloads directory: {e}")
        
        logger.info(f"Downloads cleanup completed: {result['dirs_deleted']} dirs, {result['files_deleted']} files, {result['bytes_freed']} bytes")
        return result
    
    def cleanup_screenshots(self, retention_days: int = None) -> Dict[str, Any]:
        """
        清理过期的截图文件
        
        Args:
            retention_days: 保留天数（默认从环境变量读取）
            
        Returns:
            Dict: 清理结果统计
        """
        if retention_days is None:
            retention_days = self.DEFAULT_SCREENSHOTS_RETENTION_DAYS
        
        result = {
            'type': 'screenshots',
            'retention_days': retention_days,
            'files_deleted': 0,
            'bytes_freed': 0,
            'errors': []
        }
        
        if not self.screenshots_dir.exists():
            logger.debug("Screenshots directory does not exist, skipping cleanup")
            return result
        
        cutoff_time = datetime.now() - timedelta(days=retention_days)
        
        try:
            # 遍历截图目录
            for item in self.screenshots_dir.rglob('*'):
                if not item.is_file():
                    continue
                
                # 检查文件修改时间
                mtime = datetime.fromtimestamp(item.stat().st_mtime)
                
                if mtime < cutoff_time:
                    try:
                        file_size = item.stat().st_size
                        item.unlink()
                        
                        result['files_deleted'] += 1
                        result['bytes_freed'] += file_size
                        
                        logger.debug(f"Deleted expired screenshot: {item.name}")
                    
                    except Exception as e:
                        result['errors'].append(f"{item.name}: {str(e)}")
                        logger.error(f"Failed to delete {item}: {e}")
            
            # 清理空目录
            for dir_path in sorted(self.screenshots_dir.rglob('*'), reverse=True):
                if dir_path.is_dir() and not any(dir_path.iterdir()):
                    try:
                        dir_path.rmdir()
                        logger.debug(f"Deleted empty screenshot dir: {dir_path.name}")
                    except Exception:
                        pass
        
        except Exception as e:
            result['errors'].append(f"Scan error: {str(e)}")
            logger.error(f"Failed to scan screenshots directory: {e}")
        
        logger.info(f"Screenshots cleanup completed: {result['files_deleted']} files, {result['bytes_freed']} bytes")
        return result
    
    def cleanup_orphan_browsers(self) -> Dict[str, Any]:
        """
        清理孤儿浏览器进程
        
        检查并终止没有父进程的浏览器进程
        
        Returns:
            Dict: 清理结果统计
        """
        result = {
            'type': 'orphan_browsers',
            'processes_killed': 0,
            'processes_found': 0,
            'errors': []
        }
        
        try:
            current_pid = os.getpid()
            
            for proc in psutil.process_iter(['pid', 'name', 'ppid', 'cmdline']):
                try:
                    proc_info = proc.info
                    proc_name = proc_info.get('name', '').lower()
                    
                    # 检查是否是浏览器进程
                    is_browser = any(
                        browser_name in proc_name 
                        for browser_name in self.BROWSER_PROCESS_NAMES
                    )
                    
                    if not is_browser:
                        continue
                    
                    result['processes_found'] += 1
                    
                    # 检查命令行参数是否包含playwright相关
                    cmdline = proc_info.get('cmdline', []) or []
                    is_playwright = any(
                        'playwright' in arg.lower() or 'puppeteer' in arg.lower()
                        for arg in cmdline
                    )
                    
                    if not is_playwright:
                        continue
                    
                    # 检查父进程是否还存在
                    ppid = proc_info.get('ppid')
                    
                    if ppid and ppid != current_pid:
                        try:
                            parent = psutil.Process(ppid)
                            # 父进程存在，不是孤儿进程
                            continue
                        except psutil.NoSuchProcess:
                            # 父进程不存在，是孤儿进程
                            pass
                    
                    # 终止孤儿进程
                    logger.warning(f"Killing orphan browser process: PID={proc.pid}, name={proc_name}")
                    proc.terminate()
                    
                    # 等待进程终止
                    try:
                        proc.wait(timeout=5)
                    except psutil.TimeoutExpired:
                        proc.kill()
                    
                    result['processes_killed'] += 1
                
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
                except Exception as e:
                    result['errors'].append(str(e))
        
        except Exception as e:
            result['errors'].append(f"Scan error: {str(e)}")
            logger.error(f"Failed to scan for orphan browsers: {e}")
        
        if result['processes_killed'] > 0:
            logger.info(f"Orphan browser cleanup completed: {result['processes_killed']} processes killed")
        
        return result
    
    def run_full_cleanup(self) -> Dict[str, Any]:
        """
        执行完整清理（下载文件 + 截图 + 孤儿进程）
        
        Returns:
            Dict: 完整清理结果
        """
        logger.info("Starting full cleanup...")
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'downloads': self.cleanup_downloads(),
            'screenshots': self.cleanup_screenshots(),
            'orphan_browsers': self.cleanup_orphan_browsers(),
        }
        
        # 计算总计
        results['summary'] = {
            'total_files_deleted': (
                results['downloads']['files_deleted'] + 
                results['screenshots']['files_deleted']
            ),
            'total_bytes_freed': (
                results['downloads']['bytes_freed'] + 
                results['screenshots']['bytes_freed']
            ),
            'total_dirs_deleted': results['downloads']['dirs_deleted'],
            'total_processes_killed': results['orphan_browsers']['processes_killed'],
            'total_errors': (
                len(results['downloads']['errors']) +
                len(results['screenshots']['errors']) +
                len(results['orphan_browsers']['errors'])
            )
        }
        
        logger.info(f"Full cleanup completed: {results['summary']}")
        return results
    
    def get_temp_stats(self) -> Dict[str, Any]:
        """
        获取临时文件统计信息
        
        Returns:
            Dict: 临时文件统计
        """
        stats = {
            'downloads': {'count': 0, 'size_bytes': 0},
            'screenshots': {'count': 0, 'size_bytes': 0},
            'total_size_bytes': 0
        }
        
        try:
            if self.downloads_dir.exists():
                for f in self.downloads_dir.rglob('*'):
                    if f.is_file():
                        stats['downloads']['count'] += 1
                        stats['downloads']['size_bytes'] += f.stat().st_size
            
            if self.screenshots_dir.exists():
                for f in self.screenshots_dir.rglob('*'):
                    if f.is_file():
                        stats['screenshots']['count'] += 1
                        stats['screenshots']['size_bytes'] += f.stat().st_size
            
            stats['total_size_bytes'] = (
                stats['downloads']['size_bytes'] + 
                stats['screenshots']['size_bytes']
            )
        
        except Exception as e:
            logger.error(f"Failed to get temp stats: {e}")
        
        return stats


# 全局清理服务实例
cleanup_service = CleanupService()

