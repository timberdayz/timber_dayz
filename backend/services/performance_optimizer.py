"""
性能优化建议服务
"""

import psutil
import time
from typing import Dict, List, Any
from dataclasses import dataclass
from backend.services.performance_monitor import performance_monitor

@dataclass
class OptimizationSuggestion:
    """优化建议数据类"""
    category: str
    priority: str  # high, medium, low
    title: str
    description: str
    impact: str
    effort: str
    implementation: str

class PerformanceOptimizer:
    """性能优化器"""
    
    def __init__(self):
        self.suggestions = []
    
    def analyze_system_performance(self) -> Dict[str, Any]:
        """分析系统性能"""
        try:
            # 获取当前系统指标
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # 获取网络统计
            net_io = psutil.net_io_counters()
            
            # 分析性能问题
            issues = []
            suggestions = []
            
            # CPU分析
            if cpu_percent > 80:
                issues.append("CPU使用率过高")
                suggestions.append(OptimizationSuggestion(
                    category="CPU",
                    priority="high",
                    title="优化CPU使用率",
                    description=f"当前CPU使用率为{cpu_percent:.1f}%，建议优化代码逻辑或增加CPU资源",
                    impact="高",
                    effort="中等",
                    implementation="1. 优化数据库查询\n2. 使用缓存机制\n3. 异步处理耗时操作\n4. 升级硬件配置"
                ))
            elif cpu_percent > 60:
                issues.append("CPU使用率偏高")
                suggestions.append(OptimizationSuggestion(
                    category="CPU",
                    priority="medium",
                    title="监控CPU使用率",
                    description=f"当前CPU使用率为{cpu_percent:.1f}%，建议持续监控",
                    impact="中等",
                    effort="低",
                    implementation="1. 设置CPU使用率告警\n2. 定期检查性能指标\n3. 优化热点代码"
                ))
            
            # 内存分析
            if memory.percent > 85:
                issues.append("内存使用率过高")
                suggestions.append(OptimizationSuggestion(
                    category="Memory",
                    priority="high",
                    title="优化内存使用",
                    description=f"当前内存使用率为{memory.percent:.1f}%，建议优化内存使用",
                    impact="高",
                    effort="高",
                    implementation="1. 检查内存泄漏\n2. 优化数据结构\n3. 使用内存池\n4. 增加内存容量"
                ))
            elif memory.percent > 70:
                issues.append("内存使用率偏高")
                suggestions.append(OptimizationSuggestion(
                    category="Memory",
                    priority="medium",
                    title="监控内存使用",
                    description=f"当前内存使用率为{memory.percent:.1f}%，建议监控内存使用情况",
                    impact="中等",
                    effort="低",
                    implementation="1. 设置内存使用率告警\n2. 定期检查内存使用\n3. 优化大数据处理"
                ))
            
            # 磁盘分析
            if disk.percent > 90:
                issues.append("磁盘空间不足")
                suggestions.append(OptimizationSuggestion(
                    category="Disk",
                    priority="high",
                    title="清理磁盘空间",
                    description=f"当前磁盘使用率为{disk.percent:.1f}%，建议清理磁盘空间",
                    impact="高",
                    effort="低",
                    implementation="1. 清理临时文件\n2. 删除过期日志\n3. 压缩历史数据\n4. 增加磁盘容量"
                ))
            elif disk.percent > 80:
                issues.append("磁盘空间紧张")
                suggestions.append(OptimizationSuggestion(
                    category="Disk",
                    priority="medium",
                    title="监控磁盘使用",
                    description=f"当前磁盘使用率为{disk.percent:.1f}%，建议监控磁盘使用情况",
                    impact="中等",
                    effort="低",
                    implementation="1. 设置磁盘使用率告警\n2. 定期清理临时文件\n3. 优化日志轮转"
                ))
            
            # 网络分析
            if net_io.packets_sent > 1000000 or net_io.packets_recv > 1000000:
                issues.append("网络流量较高")
                suggestions.append(OptimizationSuggestion(
                    category="Network",
                    priority="medium",
                    title="优化网络使用",
                    description="网络流量较高，建议优化网络使用",
                    impact="中等",
                    effort="中等",
                    implementation="1. 使用连接池\n2. 压缩数据传输\n3. 优化API调用\n4. 使用CDN"
                ))
            
            return {
                "analysis_time": time.time(),
                "system_metrics": {
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory.percent,
                    "memory_used_gb": memory.used / (1024**3),
                    "memory_available_gb": memory.available / (1024**3),
                    "disk_percent": disk.percent,
                    "disk_free_gb": disk.free / (1024**3),
                    "network_packets_sent": net_io.packets_sent,
                    "network_packets_recv": net_io.packets_recv
                },
                "issues": issues,
                "suggestions": [
                    {
                        "category": s.category,
                        "priority": s.priority,
                        "title": s.title,
                        "description": s.description,
                        "impact": s.impact,
                        "effort": s.effort,
                        "implementation": s.implementation
                    }
                    for s in suggestions
                ],
                "summary": {
                    "total_issues": len(issues),
                    "high_priority_suggestions": len([s for s in suggestions if s.priority == "high"]),
                    "medium_priority_suggestions": len([s for s in suggestions if s.priority == "medium"]),
                    "low_priority_suggestions": len([s for s in suggestions if s.priority == "low"])
                }
            }
            
        except Exception as e:
            return {
                "error": f"性能分析失败: {str(e)}",
                "analysis_time": time.time()
            }
    
    def analyze_database_performance(self) -> Dict[str, Any]:
        """分析数据库性能"""
        suggestions = []
        
        # 数据库连接池建议
        suggestions.append(OptimizationSuggestion(
            category="Database",
            priority="medium",
            title="优化数据库连接池",
            description="建议优化数据库连接池配置以提高并发性能",
            impact="高",
            effort="低",
            implementation="1. 调整连接池大小\n2. 设置连接超时\n3. 使用连接池监控\n4. 配置连接回收"
        ))
        
        # 查询优化建议
        suggestions.append(OptimizationSuggestion(
            category="Database",
            priority="high",
            title="优化数据库查询",
            description="建议优化慢查询和复杂查询以提高响应速度",
            impact="高",
            effort="中等",
            implementation="1. 添加数据库索引\n2. 优化SQL查询\n3. 使用查询缓存\n4. 分页处理大数据"
        ))
        
        # 数据分区建议
        suggestions.append(OptimizationSuggestion(
            category="Database",
            priority="medium",
            title="实施数据分区",
            description="建议对大表进行分区以提高查询性能",
            impact="高",
            effort="高",
            implementation="1. 按时间分区\n2. 按业务分区\n3. 使用分区索引\n4. 定期维护分区"
        ))
        
        return {
            "analysis_time": time.time(),
            "suggestions": [
                {
                    "category": s.category,
                    "priority": s.priority,
                    "title": s.title,
                    "description": s.description,
                    "impact": s.impact,
                    "effort": s.effort,
                    "implementation": s.implementation
                }
                for s in suggestions
            ]
        }
    
    def analyze_application_performance(self) -> Dict[str, Any]:
        """分析应用性能"""
        suggestions = []
        
        # 缓存建议
        suggestions.append(OptimizationSuggestion(
            category="Application",
            priority="high",
            title="实施缓存策略",
            description="建议实施多层缓存策略以提高响应速度",
            impact="高",
            effort="中等",
            implementation="1. 使用Redis缓存\n2. 实施查询缓存\n3. 使用CDN缓存\n4. 配置缓存过期"
        ))
        
        # 异步处理建议
        suggestions.append(OptimizationSuggestion(
            category="Application",
            priority="medium",
            title="异步处理优化",
            description="建议使用异步处理提高系统吞吐量",
            impact="高",
            effort="高",
            implementation="1. 使用Celery异步任务\n2. 异步文件处理\n3. 异步数据库操作\n4. 消息队列处理"
        ))
        
        # API优化建议
        suggestions.append(OptimizationSuggestion(
            category="Application",
            priority="medium",
            title="API性能优化",
            description="建议优化API响应时间和并发处理能力",
            impact="中等",
            effort="中等",
            implementation="1. 使用API缓存\n2. 实施请求限流\n3. 优化响应格式\n4. 使用API版本控制"
        ))
        
        return {
            "analysis_time": time.time(),
            "suggestions": [
                {
                    "category": s.category,
                    "priority": s.priority,
                    "title": s.title,
                    "description": s.description,
                    "impact": s.impact,
                    "effort": s.effort,
                    "implementation": s.implementation
                }
                for s in suggestions
            ]
        }
    
    def generate_optimization_report(self) -> Dict[str, Any]:
        """生成优化报告"""
        try:
            # 系统性能分析
            system_analysis = self.analyze_system_performance()
            
            # 数据库性能分析
            database_analysis = self.analyze_database_performance()
            
            # 应用性能分析
            application_analysis = self.analyze_application_performance()
            
            # 合并所有建议
            all_suggestions = []
            all_suggestions.extend(system_analysis.get("suggestions", []))
            all_suggestions.extend(database_analysis.get("suggestions", []))
            all_suggestions.extend(application_analysis.get("suggestions", []))
            
            # 按优先级排序
            priority_order = {"high": 0, "medium": 1, "low": 2}
            all_suggestions.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 2))
            
            return {
                "report_time": time.time(),
                "system_analysis": system_analysis,
                "database_analysis": database_analysis,
                "application_analysis": application_analysis,
                "optimization_suggestions": all_suggestions,
                "summary": {
                    "total_suggestions": len(all_suggestions),
                    "high_priority": len([s for s in all_suggestions if s.get("priority") == "high"]),
                    "medium_priority": len([s for s in all_suggestions if s.get("priority") == "medium"]),
                    "low_priority": len([s for s in all_suggestions if s.get("priority") == "low"])
                }
            }
            
        except Exception as e:
            return {
                "error": f"生成优化报告失败: {str(e)}",
                "report_time": time.time()
            }

# 全局性能优化器实例
performance_optimizer = PerformanceOptimizer()
