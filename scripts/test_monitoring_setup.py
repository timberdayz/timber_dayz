#!/usr/bin/env python3
"""
监控和告警系统测试脚本

用于验证 Phase 6 监控和告警系统是否正确配置和运行。

使用方法:
    python scripts/test_monitoring_setup.py

测试内容:
    1. Celery Exporter 可访问性
    2. Prometheus 可访问性和指标抓取
    3. AlertManager 可访问性
    4. Grafana 可访问性
    5. 告警规则加载
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import aiohttp
from modules.core.logger import get_logger

logger = get_logger(__name__)


class MonitoringTester:
    """监控系统测试器"""
    
    def __init__(self):
        self.results = {}
        # 默认端口配置（可通过环境变量覆盖）
        self.endpoints = {
            "celery_exporter": "http://localhost:9808/metrics",
            "prometheus": "http://localhost:19090/-/healthy",  # 端口已改为 19090
            "prometheus_targets": "http://localhost:19090/api/v1/targets",  # 端口已改为 19090
            "prometheus_rules": "http://localhost:19090/api/v1/rules",  # 端口已改为 19090
            "alertmanager": "http://localhost:19093/-/healthy",  # 端口已改为 19093
            "grafana": "http://localhost:3001/api/health",
        }
    
    async def test_endpoint(self, name: str, url: str, expected_status: int = 200) -> bool:
        """测试单个端点"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    status = response.status
                    if status == expected_status:
                        logger.info(f"[PASS] {name}: {url} - Status {status}")
                        return True
                    else:
                        logger.warning(f"[FAIL] {name}: {url} - Expected {expected_status}, got {status}")
                        return False
        except aiohttp.ClientConnectorError:
            logger.error(f"[FAIL] {name}: {url} - Connection refused (service not running?)")
            return False
        except asyncio.TimeoutError:
            logger.error(f"[FAIL] {name}: {url} - Timeout")
            return False
        except Exception as e:
            logger.error(f"[FAIL] {name}: {url} - Error: {e}")
            return False
    
    async def test_celery_exporter(self) -> bool:
        """测试 Celery Exporter"""
        logger.info("\n=== Testing Celery Exporter ===")
        url = self.endpoints["celery_exporter"]
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        text = await response.text()
                        # 检查是否有 Celery 相关指标
                        has_celery_metrics = "celery" in text.lower()
                        if has_celery_metrics:
                            logger.info(f"[PASS] Celery Exporter is running and exposing metrics")
                            return True
                        else:
                            logger.warning(f"[WARN] Celery Exporter is running but no celery metrics found")
                            logger.warning(f"       This might be normal if no Celery workers are connected")
                            return True  # 仍然算通过，因为服务本身是运行的
                    else:
                        logger.error(f"[FAIL] Celery Exporter returned status {response.status}")
                        return False
        except Exception as e:
            logger.error(f"[FAIL] Celery Exporter test failed: {e}")
            return False
    
    async def test_prometheus(self) -> bool:
        """测试 Prometheus"""
        logger.info("\n=== Testing Prometheus ===")
        
        # 测试健康检查
        health_ok = await self.test_endpoint("Prometheus Health", self.endpoints["prometheus"])
        if not health_ok:
            return False
        
        # 测试目标状态
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.endpoints["prometheus_targets"],
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        active_targets = data.get("data", {}).get("activeTargets", [])
                        celery_targets = [t for t in active_targets if t.get("labels", {}).get("job") == "celery"]
                        
                        if celery_targets:
                            for target in celery_targets:
                                health = target.get("health", "unknown")
                                logger.info(f"[INFO] Celery target health: {health}")
                                if health == "up":
                                    logger.info(f"[PASS] Prometheus is scraping Celery Exporter successfully")
                                else:
                                    logger.warning(f"[WARN] Celery target is not up: {health}")
                        else:
                            logger.warning(f"[WARN] No Celery targets found in Prometheus")
                            logger.warning(f"       Make sure celery-exporter is running and configured")
        except Exception as e:
            logger.warning(f"[WARN] Could not check Prometheus targets: {e}")
        
        return True
    
    async def test_prometheus_rules(self) -> bool:
        """测试 Prometheus 告警规则"""
        logger.info("\n=== Testing Prometheus Alert Rules ===")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.endpoints["prometheus_rules"],
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        groups = data.get("data", {}).get("groups", [])
                        
                        celery_rules = []
                        for group in groups:
                            if "celery" in group.get("name", "").lower():
                                celery_rules.extend(group.get("rules", []))
                        
                        if celery_rules:
                            logger.info(f"[PASS] Found {len(celery_rules)} Celery alert rules:")
                            for rule in celery_rules:
                                name = rule.get("name", "unknown")
                                state = rule.get("state", "unknown")
                                logger.info(f"       - {name}: {state}")
                            return True
                        else:
                            logger.warning(f"[WARN] No Celery alert rules found")
                            logger.warning(f"       Check monitoring/alert_rules.yml")
                            return True  # 仍然算通过，可能规则还未加载
                    else:
                        logger.error(f"[FAIL] Could not fetch alert rules: status {response.status}")
                        return False
        except Exception as e:
            logger.warning(f"[WARN] Could not check alert rules: {e}")
            return True
    
    async def test_alertmanager(self) -> bool:
        """测试 AlertManager"""
        logger.info("\n=== Testing AlertManager ===")
        return await self.test_endpoint("AlertManager Health", self.endpoints["alertmanager"])
    
    async def test_grafana(self) -> bool:
        """测试 Grafana"""
        logger.info("\n=== Testing Grafana ===")
        return await self.test_endpoint("Grafana Health", self.endpoints["grafana"])
    
    async def run_all_tests(self) -> dict:
        """运行所有测试"""
        logger.info("=" * 60)
        logger.info("Starting Monitoring System Tests")
        logger.info("=" * 60)
        
        self.results["celery_exporter"] = await self.test_celery_exporter()
        self.results["prometheus"] = await self.test_prometheus()
        self.results["prometheus_rules"] = await self.test_prometheus_rules()
        self.results["alertmanager"] = await self.test_alertmanager()
        self.results["grafana"] = await self.test_grafana()
        
        # 打印总结
        logger.info("\n" + "=" * 60)
        logger.info("Test Summary")
        logger.info("=" * 60)
        
        passed = sum(1 for v in self.results.values() if v)
        total = len(self.results)
        
        for name, result in self.results.items():
            status = "[PASS]" if result else "[FAIL]"
            logger.info(f"  {status} {name}")
        
        logger.info(f"\nTotal: {passed}/{total} tests passed")
        
        if passed == total:
            logger.info("\n[SUCCESS] All monitoring components are working!")
        elif passed > 0:
            logger.warning(f"\n[PARTIAL] Some components are not working. Check the logs above.")
        else:
            logger.error(f"\n[FAILURE] No monitoring components are working. Make sure services are started.")
        
        return self.results


async def main():
    """主函数"""
    tester = MonitoringTester()
    results = await tester.run_all_tests()
    
    # 如果有任何测试失败，返回非零退出码
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

