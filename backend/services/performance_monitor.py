"""
性能监控服务
"""

import psutil
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
from collections import deque
import json

@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_available_mb: float
    disk_usage_percent: float
    network_sent_mb: float
    network_recv_mb: float
    active_connections: int
    load_average: float

class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.metrics_history = deque(maxlen=max_history)
        self.is_monitoring = False
        self.monitor_thread = None
        self.start_time = None
        
        # 网络统计基准
        self._network_baseline = None
        self._set_network_baseline()
    
    def _set_network_baseline(self):
        """设置网络统计基准"""
        try:
            net_io = psutil.net_io_counters()
            self._network_baseline = {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'timestamp': time.time()
            }
        except Exception as e:
            print(f"设置网络基准失败: {e}")
            self._network_baseline = None
    
    def get_current_metrics(self) -> PerformanceMetrics:
        """获取当前性能指标"""
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            # 内存使用情况
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used_mb = memory.used / (1024 * 1024)
            memory_available_mb = memory.available / (1024 * 1024)
            
            # 磁盘使用情况
            disk = psutil.disk_usage('/')
            disk_usage_percent = (disk.used / disk.total) * 100
            
            # 网络使用情况
            network_sent_mb = 0
            network_recv_mb = 0
            if self._network_baseline:
                try:
                    net_io = psutil.net_io_counters()
                    current_time = time.time()
                    time_diff = current_time - self._network_baseline['timestamp']
                    
                    if time_diff > 0:
                        bytes_sent_diff = net_io.bytes_sent - self._network_baseline['bytes_sent']
                        bytes_recv_diff = net_io.bytes_recv - self._network_baseline['bytes_recv']
                        
                        network_sent_mb = (bytes_sent_diff / (1024 * 1024)) / time_diff
                        network_recv_mb = (bytes_recv_diff / (1024 * 1024)) / time_diff
                        
                        # 更新基准
                        self._network_baseline = {
                            'bytes_sent': net_io.bytes_sent,
                            'bytes_recv': net_io.bytes_recv,
                            'timestamp': current_time
                        }
                except Exception as e:
                    print(f"网络统计失败: {e}")
            
            # 活跃连接数
            try:
                connections = psutil.net_connections()
                active_connections = len([conn for conn in connections if conn.status == 'ESTABLISHED'])
            except Exception:
                active_connections = 0
            
            # 系统负载（Linux/Unix）
            try:
                load_avg = psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else 0.0
            except Exception:
                load_avg = 0.0
            
            return PerformanceMetrics(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory_percent,
                memory_used_mb=memory_used_mb,
                memory_available_mb=memory_available_mb,
                disk_usage_percent=disk_usage_percent,
                network_sent_mb=network_sent_mb,
                network_recv_mb=network_recv_mb,
                active_connections=active_connections,
                load_average=load_avg
            )
            
        except Exception as e:
            print(f"获取性能指标失败: {e}")
            return PerformanceMetrics(
                timestamp=datetime.now(),
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_used_mb=0.0,
                memory_available_mb=0.0,
                disk_usage_percent=0.0,
                network_sent_mb=0.0,
                network_recv_mb=0.0,
                active_connections=0,
                load_average=0.0
            )
    
    def start_monitoring(self, interval: float = 1.0):
        """开始性能监控"""
        if self.is_monitoring:
            return
        
        self.is_monitoring = True
        self.start_time = datetime.now()
        self.monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(interval,),
            daemon=True
        )
        self.monitor_thread.start()
        print(f"性能监控已启动，监控间隔: {interval}秒")
    
    def stop_monitoring(self):
        """停止性能监控"""
        self.is_monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        print("性能监控已停止")
    
    def _monitor_loop(self, interval: float):
        """监控循环"""
        while self.is_monitoring:
            try:
                metrics = self.get_current_metrics()
                self.metrics_history.append(metrics)
                time.sleep(interval)
            except Exception as e:
                print(f"监控循环错误: {e}")
                time.sleep(interval)
    
    def get_metrics_summary(self, duration_minutes: int = 5) -> Dict:
        """获取性能指标摘要"""
        if not self.metrics_history:
            return {"error": "没有监控数据"}
        
        # 计算时间范围
        cutoff_time = datetime.now() - timedelta(minutes=duration_minutes)
        recent_metrics = [m for m in self.metrics_history if m.timestamp >= cutoff_time]
        
        if not recent_metrics:
            return {"error": "指定时间范围内没有数据"}
        
        # 计算统计信息
        cpu_values = [m.cpu_percent for m in recent_metrics]
        memory_values = [m.memory_percent for m in recent_metrics]
        
        return {
            "duration_minutes": duration_minutes,
            "sample_count": len(recent_metrics),
            "cpu": {
                "current": recent_metrics[-1].cpu_percent,
                "average": sum(cpu_values) / len(cpu_values),
                "max": max(cpu_values),
                "min": min(cpu_values)
            },
            "memory": {
                "current_percent": recent_metrics[-1].memory_percent,
                "current_used_mb": recent_metrics[-1].memory_used_mb,
                "current_available_mb": recent_metrics[-1].memory_available_mb,
                "average_percent": sum(memory_values) / len(memory_values),
                "max_percent": max(memory_values),
                "min_percent": min(memory_values)
            },
            "disk": {
                "current_percent": recent_metrics[-1].disk_usage_percent
            },
            "network": {
                "current_sent_mb_s": recent_metrics[-1].network_sent_mb,
                "current_recv_mb_s": recent_metrics[-1].network_recv_mb
            },
            "connections": {
                "current": recent_metrics[-1].active_connections
            },
            "load": {
                "current": recent_metrics[-1].load_average
            }
        }
    
    def get_metrics_history(self, limit: int = 100) -> List[Dict]:
        """获取历史性能指标"""
        history = list(self.metrics_history)[-limit:]
        return [
            {
                "timestamp": m.timestamp.isoformat(),
                "cpu_percent": m.cpu_percent,
                "memory_percent": m.memory_percent,
                "memory_used_mb": m.memory_used_mb,
                "memory_available_mb": m.memory_available_mb,
                "disk_usage_percent": m.disk_usage_percent,
                "network_sent_mb": m.network_sent_mb,
                "network_recv_mb": m.network_recv_mb,
                "active_connections": m.active_connections,
                "load_average": m.load_average
            }
            for m in history
        ]
    
    def export_metrics(self, filepath: str):
        """导出性能指标到文件"""
        try:
            data = {
                "export_time": datetime.now().isoformat(),
                "monitoring_duration": (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
                "metrics_count": len(self.metrics_history),
                "metrics": self.get_metrics_history()
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"性能指标已导出到: {filepath}")
            return True
        except Exception as e:
            print(f"导出性能指标失败: {e}")
            return False

# 全局性能监控器实例
performance_monitor = PerformanceMonitor()
