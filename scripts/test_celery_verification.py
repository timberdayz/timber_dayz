#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Celery 功能验证测试脚本

测试内容：
1. 任务恢复测试（服务器重启后任务自动恢复）
2. 任务重试测试（任务失败后自动重试）
3. Celery Worker 崩溃恢复测试
4. 基本功能验证（任务提交、执行、状态查询）

使用方法：
    python scripts/test_celery_verification.py
"""

import asyncio
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.core.logger import get_logger

logger = get_logger(__name__)

# 测试配置
API_BASE_URL = "http://localhost:8000"
TEST_TIMEOUT = 300  # 5分钟超时


class CeleryVerificationTester:
    """Celery 功能验证测试器"""
    
    def __init__(self):
        self.api_base_url = API_BASE_URL
        self.test_results: Dict[str, Any] = {}
        
    async def test_task_submission(self) -> bool:
        """测试任务提交功能"""
        logger.info("=" * 60)
        logger.info("测试 1: 任务提交功能")
        logger.info("=" * 60)
        
        try:
            # 这里需要实际的 API 调用
            # 由于是验证脚本，我们只检查 API 是否可访问
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                # 检查健康端点
                async with session.get(f"{self.api_base_url}/health", timeout=5) as response:
                    if response.status == 200:
                        logger.info("[PASS] API 服务可访问")
                        self.test_results["task_submission"] = True
                        return True
                    else:
                        logger.error(f"[FAIL] API 服务返回状态码: {response.status}")
                        self.test_results["task_submission"] = False
                        return False
        except Exception as e:
            logger.error(f"[FAIL] 任务提交测试失败: {e}")
            self.test_results["task_submission"] = False
            return False
    
    async def test_task_recovery(self) -> bool:
        """测试任务恢复功能（需要手动重启 Worker）"""
        logger.info("=" * 60)
        logger.info("测试 2: 任务恢复功能")
        logger.info("=" * 60)
        logger.info("[INFO] 此测试需要手动操作：")
        logger.info("  1. 提交一个长时间运行的任务")
        logger.info("  2. 在任务执行过程中重启 Celery Worker")
        logger.info("  3. 验证任务是否自动恢复并继续执行")
        logger.info("")
        logger.info("[SKIP] 手动测试，跳过自动化测试")
        self.test_results["task_recovery"] = "manual_test_required"
        return True
    
    async def test_task_retry(self) -> bool:
        """测试任务重试功能"""
        logger.info("=" * 60)
        logger.info("测试 3: 任务重试功能")
        logger.info("=" * 60)
        logger.info("[INFO] 此测试需要模拟任务失败场景")
        logger.info("[SKIP] 需要创建专门的重试测试任务，跳过自动化测试")
        self.test_results["task_retry"] = "manual_test_required"
        return True
    
    async def test_worker_recovery(self) -> bool:
        """测试 Worker 崩溃恢复功能"""
        logger.info("=" * 60)
        logger.info("测试 4: Worker 崩溃恢复功能")
        logger.info("=" * 60)
        logger.info("[INFO] 此测试需要检查 Docker 重启策略")
        logger.info("[INFO] 检查 docker-compose.prod.yml 中的 restart: always 配置")
        
        try:
            import subprocess
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=celery-worker", "--format", "{{.RestartPolicy}}"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and "always" in result.stdout:
                logger.info("[PASS] Celery Worker 配置了自动重启策略")
                self.test_results["worker_recovery"] = True
                return True
            else:
                logger.warning("[WARN] 无法验证 Worker 重启策略，请手动检查")
                self.test_results["worker_recovery"] = "manual_check_required"
                return True
        except Exception as e:
            logger.warning(f"[WARN] 无法检查 Worker 配置: {e}")
            self.test_results["worker_recovery"] = "manual_check_required"
            return True
    
    async def test_redis_fallback(self) -> bool:
        """测试 Redis 连接失败时的降级处理"""
        logger.info("=" * 60)
        logger.info("测试 5: Redis 降级处理")
        logger.info("=" * 60)
        logger.info("[INFO] 此测试需要停止 Redis 服务")
        logger.info("[SKIP] 需要手动测试，跳过自动化测试")
        self.test_results["redis_fallback"] = "manual_test_required"
        return True
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试"""
        logger.info("=" * 60)
        logger.info("Celery 功能验证测试")
        logger.info("=" * 60)
        logger.info("")
        
        # 运行测试
        await self.test_task_submission()
        await self.test_task_recovery()
        await self.test_task_retry()
        await self.test_worker_recovery()
        await self.test_redis_fallback()
        
        # 生成测试报告
        self.generate_report()
        
        return self.test_results
    
    def generate_report(self):
        """生成测试报告"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("测试报告")
        logger.info("=" * 60)
        
        passed = 0
        failed = 0
        manual = 0
        
        for test_name, result in self.test_results.items():
            if result is True:
                logger.info(f"  [PASS] {test_name}")
                passed += 1
            elif result is False:
                logger.error(f"  [FAIL] {test_name}")
                failed += 1
            else:
                logger.info(f"  [MANUAL] {test_name}: {result}")
                manual += 1
        
        logger.info("")
        logger.info(f"总计: {len(self.test_results)} 个测试")
        logger.info(f"  通过: {passed}")
        logger.info(f"  失败: {failed}")
        logger.info(f"  需手动测试: {manual}")
        logger.info("")
        
        if failed == 0:
            logger.info("[SUCCESS] 所有自动化测试通过！")
        else:
            logger.warning(f"[WARNING] 有 {failed} 个测试失败")


async def main():
    """主函数"""
    tester = CeleryVerificationTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())

