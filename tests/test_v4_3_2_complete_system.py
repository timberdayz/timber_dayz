#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v4.3.2系统完整自动化测试

测试覆盖：
1. 数据库迁移验证
2. 产品层级入库（商品级+规格级）
3. 全域店铺解析
4. 智能日期解析
5. Services子类型分流
6. 查询服务统一出口
7. 质量告警系统
"""

import sys
from pathlib import Path
from datetime import date
import pandas as pd

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from modules.core.logger import get_logger

logger = get_logger(__name__)


class SystemTest:
    """系统测试主类"""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def test(self, name: str, func):
        """运行单个测试"""
        try:
            print(f"\n[测试] {name}...")
            func()
            print(f"[OK] {name}")
            self.passed += 1
        except Exception as e:
            print(f"[FAILED] {name}: {e}")
            self.errors.append(f"{name}: {e}")
            self.failed += 1
    
    def summary(self):
        """输出测试摘要"""
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"测试完成: {self.passed}/{total} 通过")
        if self.failed > 0:
            print(f"\n失败的测试:")
            for err in self.errors:
                print(f"  - {err}")
        print(f"{'='*60}\n")
        return self.failed == 0


def test_database_migration():
    """测试1：验证数据库迁移"""
    from modules.core.db.schema import FactProductMetric
    
    required_fields = ['sku_scope', 'parent_platform_sku', 'source_catalog_id', 
                      'period_start', 'metric_date_utc', 'order_count']
    
    for field in required_fields:
        assert hasattr(FactProductMetric, field), f"缺少字段: {field}"
    
    print("  - 所有新字段已创建")


def test_shop_resolver():
    """测试2：店铺解析器"""
    from modules.services.shop_resolver import get_shop_resolver
    
    resolver = get_shop_resolver()
    
    # 测试路径规则
    result = resolver.resolve(
        'profiles/shopee/account1/shop_sg_001/products/file.xlsx',
        'shopee'
    )
    assert result.shop_id is not None, "路径规则解析失败"
    assert result.confidence >= 0.85, f"置信度过低: {result.confidence}"
    print(f"  - 路径规则: shop_id={result.shop_id}, 置信度={result.confidence:.2f}")
    
    # 测试文件名正则
    result = resolver.resolve(
        'data/raw/shopee_shop123_products_daily.xlsx',
        'shopee'
    )
    print(f"  - 文件名正则: shop_id={result.shop_id}, 置信度={result.confidence:.2f}")


def test_smart_date_parser():
    """测试3：智能日期解析"""
    from modules.services.smart_date_parser import parse_date, detect_dayfirst
    
    # 测试dayfirst检测
    samples = ['23/09/2025', '24/09/2025', '25/09/2025']
    dayfirst = detect_dayfirst(samples)
    assert dayfirst is True, f"dayfirst检测错误: {dayfirst}"
    print(f"  - dayfirst检测: {dayfirst} [OK]")
    
    # 测试dd/MM/yyyy
    d = parse_date('23/09/2025 10:30', prefer_dayfirst=True)
    assert str(d) == '2025-09-23', f"日期解析错误: {d}"
    print(f"  - dd/MM/yyyy: {d} [OK]")
    
    # 测试yyyy-MM-dd
    d = parse_date('2025-09-23')
    assert str(d) == '2025-09-23', f"ISO日期解析错误: {d}"
    print(f"  - yyyy-MM-dd: {d} [OK]")
    
    # 测试Excel序列
    d = parse_date(44818)
    assert d is not None, "Excel序列解析失败"
    print(f"  - Excel序列: {d} [OK]")


def test_product_hierarchy_ingestion():
    """测试4：产品层级入库"""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from modules.core.db.schema import FactProductMetric
    from modules.core.secrets_manager import get_secrets_manager
    import os
    
    # 获取数据库连接
    url = os.getenv("DATABASE_URL")
    if not url:
        sm = get_secrets_manager()
        url = f"sqlite:///{sm.get_unified_database_path()}"
    
    engine = create_engine(url)
    session = Session(engine)
    
    try:
        # 查询测试数据（如果已入库）
        products = session.execute(
            select(FactProductMetric).where(
                FactProductMetric.platform_sku.in_(['PROD001', 'PROD002', 'PROD003']),
                FactProductMetric.sku_scope == 'product'
            )
        ).scalars().all()
        
        if products:
            print(f"  - 找到{len(products)}条商品级记录")
            for p in products:
                print(f"    SKU={p.platform_sku}, 销量={p.sales_volume}, GMV={p.sales_amount}")
        else:
            print("  - 未找到测试数据（请先运行契约样例）")
    
    finally:
        session.close()


def test_query_service():
    """测试5：查询服务统一出口"""
    from modules.services.data_query_service import DataQueryService
    
    service = DataQueryService()
    
    # 测试auto模式（商品级优先，规格级聚合兜底）
    df = service.get_product_metrics_unified(
        start_date=(date.today() - pd.Timedelta(days=30)).strftime('%Y-%m-%d'),
        end_date=date.today().strftime('%Y-%m-%d'),
        prefer_scope='auto'
    )
    
    print(f"  - auto模式查询: {len(df)}条记录")
    if not df.empty and 'metric_source' in df.columns:
        sources = df['metric_source'].value_counts().to_dict()
        print(f"    数据来源分布: {sources}")


def test_quality_monitor():
    """测试6：质量告警系统"""
    from modules.services.quality_monitor import detect_gmv_conflicts, generate_quality_report
    from sqlalchemy import create_engine
    from modules.core.secrets_manager import get_secrets_manager
    import os
    
    url = os.getenv("DATABASE_URL")
    if not url:
        sm = get_secrets_manager()
        url = f"sqlite:///{sm.get_unified_database_path()}"
    
    engine = create_engine(url)
    
    # 检测GMV冲突
    conflicts = detect_gmv_conflicts(engine, threshold=0.05)
    print(f"  - 检测到{len(conflicts)}个GMV冲突（偏差>5%）")
    
    # 生成质量报告
    report = generate_quality_report(engine)
    print(f"  - 质量报告: 高风险{report['high_risk']}个, 中风险{report['medium_risk']}个")


def test_catalog_scanner_integration():
    """测试7：扫描器集成测试"""
    from modules.services.catalog_scanner import scan_files
    
    # 扫描测试目录
    result = scan_files('temp/development')
    print(f"  - 扫描结果: 发现{result.seen}个, 注册{result.registered}个, 跳过{result.skipped}个")


def test_services_subdomain():
    """测试8：Services子类型支持检查"""
    from modules.services.ingestion_worker import _ingest_services_file
    
    # 简单检查函数存在
    assert callable(_ingest_services_file), "Services入库函数不存在"
    print("  - Services子类型入库函数已就绪")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("西虹ERP系统 v4.3.2 完整自动化测试")
    print("=" * 60)
    
    tester = SystemTest()
    
    # 运行所有测试
    tester.test("数据库迁移验证", test_database_migration)
    tester.test("店铺解析器", test_shop_resolver)
    tester.test("智能日期解析", test_smart_date_parser)
    tester.test("产品层级入库", test_product_hierarchy_ingestion)
    tester.test("查询服务统一出口", test_query_service)
    tester.test("质量告警系统", test_quality_monitor)
    tester.test("扫描器集成", test_catalog_scanner_integration)
    tester.test("Services子类型", test_services_subdomain)
    
    # 输出摘要
    success = tester.summary()
    
    # 返回退出码
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

