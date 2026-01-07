#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C类数据计算性能测试

测试指标：
1. C类数据计算响应时间（目标：<500ms P95）
2. 物化视图刷新时间（目标：<60s）
3. 数据质量检查性能（目标：<100ms/店铺）

用于C类数据核心字段优化计划
"""

import sys
import time
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import List, Dict, Any
import statistics

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.models.database import get_db, SessionLocal
from backend.services.c_class_data_validator import get_c_class_data_validator
from backend.services.shop_health_service import ShopHealthService
from backend.services.materialized_view_service import MaterializedViewService
from modules.core.logger import get_logger
from sqlalchemy import text

logger = get_logger(__name__)


class PerformanceTestResults:
    """性能测试结果"""
    
    def __init__(self):
        self.results = {
            "c_class_calculation": [],
            "mv_refresh": [],
            "data_quality_check": []
        }
    
    def add_result(self, category: str, duration_ms: float, metadata: Dict[str, Any] = None):
        """添加测试结果"""
        self.results[category].append({
            "duration_ms": duration_ms,
            "metadata": metadata or {},
            "timestamp": datetime.now().isoformat()
        })
    
    def get_statistics(self, category: str) -> Dict[str, float]:
        """获取统计信息"""
        durations = [r["duration_ms"] for r in self.results[category]]
        
        if not durations:
            return {}
        
        return {
            "count": len(durations),
            "min": min(durations),
            "max": max(durations),
            "mean": statistics.mean(durations),
            "median": statistics.median(durations),
            "p95": self._percentile(durations, 95),
            "p99": self._percentile(durations, 99)
        }
    
    def _percentile(self, data: List[float], percentile: float) -> float:
        """计算百分位数"""
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile / 100)
        return sorted_data[min(index, len(sorted_data) - 1)]
    
    def print_report(self):
        """打印测试报告"""
        logger.info("=" * 70)
        logger.info("C类数据计算性能测试报告")
        logger.info("=" * 70)
        
        # C类数据计算性能
        calc_stats = self.get_statistics("c_class_calculation")
        if calc_stats:
            logger.info("\n1. C类数据计算响应时间:")
            logger.info(f"   测试次数: {calc_stats['count']}")
            logger.info(f"   平均响应时间: {calc_stats['mean']:.2f}ms")
            logger.info(f"   P95响应时间: {calc_stats['p95']:.2f}ms")
            logger.info(f"   目标: <500ms P95")
            logger.info(f"   结果: {'[OK]' if calc_stats['p95'] < 500 else '[FAIL]'}")
        
        # 物化视图刷新性能
        mv_stats = self.get_statistics("mv_refresh")
        if mv_stats:
            logger.info("\n2. 物化视图刷新时间:")
            logger.info(f"   测试次数: {mv_stats['count']}")
            logger.info(f"   平均刷新时间: {mv_stats['mean']:.2f}ms ({mv_stats['mean']/1000:.2f}s)")
            logger.info(f"   P95刷新时间: {mv_stats['p95']:.2f}ms ({mv_stats['p95']/1000:.2f}s)")
            logger.info(f"   目标: <60s")
            logger.info(f"   结果: {'[OK]' if mv_stats['p95'] < 60000 else '[FAIL]'}")
        
        # 数据质量检查性能
        dq_stats = self.get_statistics("data_quality_check")
        if dq_stats:
            logger.info("\n3. 数据质量检查性能:")
            logger.info(f"   测试次数: {dq_stats['count']}")
            logger.info(f"   平均检查时间: {dq_stats['mean']:.2f}ms/店铺")
            logger.info(f"   P95检查时间: {dq_stats['p95']:.2f}ms/店铺")
            logger.info(f"   目标: <100ms/店铺")
            logger.info(f"   结果: {'[OK]' if dq_stats['p95'] < 100 else '[FAIL]'}")
        
        logger.info("\n" + "=" * 70)


def test_c_class_calculation_performance(db: SessionLocal, results: PerformanceTestResults):
    """测试C类数据计算性能"""
    logger.info("\n测试C类数据计算响应时间...")
    
    # 获取所有店铺列表（简化版：使用固定店铺）
    test_shops = [
        ("shopee", "shop001"),
        ("shopee", "shop002"),
        ("tiktok", "shop001"),
    ]
    
    health_service = ShopHealthService(db)
    
    for platform_code, shop_id in test_shops:
        for i in range(5):  # 每个店铺测试5次
            start_time = time.time()
            
            try:
                # 执行健康度评分计算
                result = health_service.calculate_health_score(
                    platform_code=platform_code,
                    shop_id=shop_id,
                    metric_date=date.today() - timedelta(days=i),
                    granularity="daily"
                )
                
                duration_ms = (time.time() - start_time) * 1000
                results.add_result("c_class_calculation", duration_ms, {
                    "platform_code": platform_code,
                    "shop_id": shop_id,
                    "health_score": result.get("health_score", 0)
                })
                
            except Exception as e:
                logger.warning(f"计算失败 {platform_code}/{shop_id}: {e}")
                duration_ms = (time.time() - start_time) * 1000
                results.add_result("c_class_calculation", duration_ms, {
                    "error": str(e)
                })


def test_mv_refresh_performance(db: SessionLocal, results: PerformanceTestResults):
    """测试物化视图刷新性能"""
    logger.info("\n测试物化视图刷新时间...")
    
    # C类数据物化视图列表
    c_class_views = [
        "mv_shop_daily_performance",
        "mv_shop_health_summary",
        "mv_campaign_achievement",
        "mv_target_achievement",
    ]
    
    for view_name in c_class_views:
        # 检查视图是否存在
        check_query = text("""
            SELECT COUNT(*) 
            FROM pg_matviews 
            WHERE matviewname = :view_name AND schemaname = 'public'
        """)
        
        view_exists = db.execute(check_query, {"view_name": view_name}).scalar() > 0
        
        if not view_exists:
            logger.warning(f"跳过不存在的视图: {view_name}")
            continue
        
        # 测试刷新性能（3次）
        for i in range(3):
            start_time = time.time()
            
            try:
                # 尝试CONCURRENTLY刷新
                try:
                    db.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}"))
                    db.commit()
                except Exception:
                    # 如果不支持CONCURRENTLY，使用普通刷新
                    db.rollback()
                    db.execute(text(f"REFRESH MATERIALIZED VIEW {view_name}"))
                    db.commit()
                
                duration_ms = (time.time() - start_time) * 1000
                results.add_result("mv_refresh", duration_ms, {
                    "view_name": view_name,
                    "refresh_type": "concurrent" if i == 0 else "normal"
                })
                
            except Exception as e:
                logger.warning(f"刷新失败 {view_name}: {e}")
                duration_ms = (time.time() - start_time) * 1000
                results.add_result("mv_refresh", duration_ms, {
                    "view_name": view_name,
                    "error": str(e)
                })


def test_data_quality_check_performance(db: SessionLocal, results: PerformanceTestResults):
    """测试数据质量检查性能"""
    logger.info("\n测试数据质量检查性能...")
    
    # 获取所有店铺列表（简化版：查询前10个店铺）
    shops_query = text("""
        SELECT DISTINCT platform_code, shop_id 
        FROM fact_orders 
        LIMIT 10
    """)
    
    shops = db.execute(shops_query).fetchall()
    
    validator = get_c_class_data_validator(db)
    
    for platform_code, shop_id in shops:
        start_time = time.time()
        
        try:
            # 执行数据质量检查
            check_result = validator.check_b_class_completeness(
                platform_code=platform_code,
                shop_id=shop_id,
                metric_date=date.today()
            )
            
            duration_ms = (time.time() - start_time) * 1000
            results.add_result("data_quality_check", duration_ms, {
                "platform_code": platform_code,
                "shop_id": shop_id,
                "quality_score": check_result.get("data_quality_score", 0)
            })
            
        except Exception as e:
            logger.warning(f"检查失败 {platform_code}/{shop_id}: {e}")
            duration_ms = (time.time() - start_time) * 1000
            results.add_result("data_quality_check", duration_ms, {
                "error": str(e)
            })


def main():
    """主测试函数"""
    logger.info("=" * 70)
    logger.info("C类数据计算性能测试")
    logger.info("=" * 70)
    
    db = SessionLocal()
    results = PerformanceTestResults()
    
    try:
        # 1. 测试C类数据计算性能
        test_c_class_calculation_performance(db, results)
        
        # 2. 测试物化视图刷新性能
        test_mv_refresh_performance(db, results)
        
        # 3. 测试数据质量检查性能
        test_data_quality_check_performance(db, results)
        
        # 4. 打印测试报告
        results.print_report()
        
        # 5. 判断是否通过
        calc_stats = results.get_statistics("c_class_calculation")
        mv_stats = results.get_statistics("mv_refresh")
        dq_stats = results.get_statistics("data_quality_check")
        
        all_passed = True
        
        if calc_stats and calc_stats.get("p95", 0) >= 500:
            logger.error("[FAIL] C类数据计算P95响应时间 >= 500ms")
            all_passed = False
        
        if mv_stats and mv_stats.get("p95", 0) >= 60000:
            logger.error("[FAIL] 物化视图刷新P95时间 >= 60s")
            all_passed = False
        
        if dq_stats and dq_stats.get("p95", 0) >= 100:
            logger.error("[FAIL] 数据质量检查P95时间 >= 100ms/店铺")
            all_passed = False
        
        if all_passed:
            logger.info("\n[OK] 所有性能测试通过")
            return 0
        else:
            logger.error("\n[FAIL] 部分性能测试未通过")
            return 1
        
    except Exception as e:
        logger.error(f"性能测试失败: {e}", exc_info=True)
        return 1
    finally:
        db.close()


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)

