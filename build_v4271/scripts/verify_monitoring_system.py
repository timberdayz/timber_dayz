#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
监控系统功能验证脚本

验证内容：
1. Grafana 仪表板访问
2. Prometheus 指标收集
3. 告警规则状态
4. AlertManager 配置

使用方法：
    python scripts/verify_monitoring_system.py
"""

import sys
import asyncio
from pathlib import Path
from typing import Dict, Any, List
import aiohttp

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.core.logger import get_logger

logger = get_logger(__name__)

# 监控服务配置
PROMETHEUS_URL = "http://localhost:19090"
ALERTMANAGER_URL = "http://localhost:19093"
GRAFANA_URL = "http://localhost:3001"
CELERY_EXPORTER_URL = "http://localhost:9808"


class MonitoringSystemVerifier:
    """监控系统验证器"""
    
    def __init__(self):
        self.test_results: Dict[str, Any] = {}
        
    async def verify_prometheus(self) -> bool:
        """验证 Prometheus 功能"""
        logger.info("=" * 60)
        logger.info("验证 1: Prometheus")
        logger.info("=" * 60)
        
        try:
            async with aiohttp.ClientSession() as session:
                # 检查健康状态
                async with session.get(f"{PROMETHEUS_URL}/-/healthy", timeout=5) as response:
                    if response.status == 200:
                        logger.info("[PASS] Prometheus 健康检查通过")
                    else:
                        logger.error(f"[FAIL] Prometheus 健康检查失败: {response.status}")
                        self.test_results["prometheus_health"] = False
                        return False
                
                # 检查 targets
                async with session.get(f"{PROMETHEUS_URL}/api/v1/targets", timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        targets = data.get("data", {}).get("activeTargets", [])
                        
                        logger.info(f"[INFO] 发现 {len(targets)} 个监控目标:")
                        for target in targets:
                            job = target.get("labels", {}).get("job", "unknown")
                            health = target.get("health", "unknown")
                            logger.info(f"  - {job}: {health}")
                        
                        # 检查 Celery Exporter
                        celery_targets = [t for t in targets if t.get("labels", {}).get("job") == "celery"]
                        if celery_targets:
                            celery_health = celery_targets[0].get("health", "unknown")
                            if celery_health == "up":
                                logger.info("[PASS] Celery Exporter target 状态正常")
                                self.test_results["prometheus_celery"] = True
                            else:
                                logger.warning(f"[WARN] Celery Exporter target 状态: {celery_health}")
                                self.test_results["prometheus_celery"] = False
                        else:
                            logger.warning("[WARN] 未找到 Celery Exporter target")
                            self.test_results["prometheus_celery"] = False
                        
                        self.test_results["prometheus_health"] = True
                        return True
                    else:
                        logger.error(f"[FAIL] 无法获取 Prometheus targets: {response.status}")
                        self.test_results["prometheus_health"] = False
                        return False
                        
        except Exception as e:
            logger.error(f"[FAIL] Prometheus 验证失败: {e}")
            self.test_results["prometheus_health"] = False
            return False
    
    async def verify_alertmanager(self) -> bool:
        """验证 AlertManager 功能"""
        logger.info("=" * 60)
        logger.info("验证 2: AlertManager")
        logger.info("=" * 60)
        
        try:
            async with aiohttp.ClientSession() as session:
                # 检查健康状态
                async with session.get(f"{ALERTMANAGER_URL}/-/healthy", timeout=5) as response:
                    if response.status == 200:
                        logger.info("[PASS] AlertManager 健康检查通过")
                        self.test_results["alertmanager_health"] = True
                        return True
                    else:
                        logger.error(f"[FAIL] AlertManager 健康检查失败: {response.status}")
                        self.test_results["alertmanager_health"] = False
                        return False
                        
        except Exception as e:
            logger.error(f"[FAIL] AlertManager 验证失败: {e}")
            self.test_results["alertmanager_health"] = False
            return False
    
    async def verify_grafana(self) -> bool:
        """验证 Grafana 功能"""
        logger.info("=" * 60)
        logger.info("验证 3: Grafana")
        logger.info("=" * 60)
        
        try:
            async with aiohttp.ClientSession() as session:
                # 检查健康状态
                async with session.get(f"{GRAFANA_URL}/api/health", timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        status = data.get("database", "unknown")
                        logger.info(f"[PASS] Grafana 健康检查通过 (数据库: {status})")
                        self.test_results["grafana_health"] = True
                        return True
                    else:
                        logger.error(f"[FAIL] Grafana 健康检查失败: {response.status}")
                        self.test_results["grafana_health"] = False
                        return False
                        
        except Exception as e:
            logger.error(f"[FAIL] Grafana 验证失败: {e}")
            self.test_results["grafana_health"] = False
            return False
    
    async def verify_celery_exporter(self) -> bool:
        """验证 Celery Exporter 功能"""
        logger.info("=" * 60)
        logger.info("验证 4: Celery Exporter")
        logger.info("=" * 60)
        
        try:
            async with aiohttp.ClientSession() as session:
                # 检查 metrics 端点
                async with session.get(f"{CELERY_EXPORTER_URL}/metrics", timeout=5) as response:
                    if response.status == 200:
                        content = await response.text()
                        if "celery_tasks_total" in content:
                            logger.info("[PASS] Celery Exporter metrics 端点正常")
                            self.test_results["celery_exporter"] = True
                            return True
                        else:
                            logger.warning("[WARN] Celery Exporter metrics 端点可访问，但未找到 celery_tasks_total 指标")
                            self.test_results["celery_exporter"] = False
                            return False
                    else:
                        logger.error(f"[FAIL] Celery Exporter metrics 端点失败: {response.status}")
                        self.test_results["celery_exporter"] = False
                        return False
                        
        except Exception as e:
            logger.error(f"[FAIL] Celery Exporter 验证失败: {e}")
            self.test_results["celery_exporter"] = False
            return False
    
    async def verify_alert_rules(self) -> bool:
        """验证告警规则"""
        logger.info("=" * 60)
        logger.info("验证 5: Prometheus 告警规则")
        logger.info("=" * 60)
        
        try:
            async with aiohttp.ClientSession() as session:
                # 检查告警规则
                async with session.get(f"{PROMETHEUS_URL}/api/v1/rules", timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        groups = data.get("data", {}).get("groups", [])
                        
                        celery_rules = []
                        for group in groups:
                            if group.get("name") == "celery_alerts":
                                celery_rules = group.get("rules", [])
                                break
                        
                        if celery_rules:
                            logger.info(f"[PASS] 找到 {len(celery_rules)} 条 Celery 告警规则:")
                            for rule in celery_rules:
                                name = rule.get("name", "unknown")
                                state = rule.get("state", "unknown")
                                logger.info(f"  - {name}: {state}")
                            
                            self.test_results["alert_rules"] = True
                            return True
                        else:
                            logger.warning("[WARN] 未找到 Celery 告警规则")
                            self.test_results["alert_rules"] = False
                            return False
                    else:
                        logger.error(f"[FAIL] 无法获取告警规则: {response.status}")
                        self.test_results["alert_rules"] = False
                        return False
                        
        except Exception as e:
            logger.error(f"[FAIL] 告警规则验证失败: {e}")
            self.test_results["alert_rules"] = False
            return False
    
    async def run_all_verifications(self) -> Dict[str, Any]:
        """运行所有验证"""
        logger.info("=" * 60)
        logger.info("监控系统功能验证")
        logger.info("=" * 60)
        logger.info("")
        
        # 运行验证
        await self.verify_prometheus()
        await self.verify_alertmanager()
        await self.verify_grafana()
        await self.verify_celery_exporter()
        await self.verify_alert_rules()
        
        # 生成报告
        self.generate_report()
        
        return self.test_results
    
    def generate_report(self):
        """生成验证报告"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("验证报告")
        logger.info("=" * 60)
        
        passed = sum(1 for v in self.test_results.values() if v is True)
        failed = sum(1 for v in self.test_results.values() if v is False)
        
        for test_name, result in self.test_results.items():
            if result is True:
                logger.info(f"  [PASS] {test_name}")
            else:
                logger.error(f"  [FAIL] {test_name}")
        
        logger.info("")
        logger.info(f"总计: {len(self.test_results)} 个验证")
        logger.info(f"  通过: {passed}")
        logger.info(f"  失败: {failed}")
        logger.info("")
        
        if failed == 0:
            logger.info("[SUCCESS] 所有监控系统验证通过！")
        else:
            logger.warning(f"[WARNING] 有 {failed} 个验证失败")
        
        logger.info("")
        logger.info("访问地址:")
        logger.info(f"  - Prometheus: {PROMETHEUS_URL}")
        logger.info(f"  - AlertManager: {ALERTMANAGER_URL}")
        logger.info(f"  - Grafana: {GRAFANA_URL}")
        logger.info(f"  - Celery Exporter: {CELERY_EXPORTER_URL}/metrics")


async def main():
    """主函数"""
    verifier = MonitoringSystemVerifier()
    await verifier.run_all_verifications()


if __name__ == "__main__":
    asyncio.run(main())

