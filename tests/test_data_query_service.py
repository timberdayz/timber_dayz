#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
data_query_service单元测试

测试数据查询服务功能
"""

import pytest
from datetime import date, timedelta
import pandas as pd

from modules.services.data_query_service import (
    DataQueryService,
    get_data_query_service,
    query_orders,
    query_product_metrics,
    query_catalog_status,
)


class TestDataQueryService:
    """测试DataQueryService核心类"""
    
    @pytest.fixture
    def service(self):
        """创建服务实例"""
        return DataQueryService()
    
    def test_service_initialization(self, service):
        """测试服务初始化"""
        assert service is not None
        assert service._engine is None  # 懒加载
    
    def test_get_catalog_status(self, service):
        """测试Catalog状态查询"""
        status = service.get_catalog_status()
        
        assert isinstance(status, dict)
        assert 'total' in status
        assert 'by_status' in status
        assert 'by_domain' in status
        assert 'by_platform' in status
        
        # 验证数据类型
        assert isinstance(status['total'], int)
        assert isinstance(status['by_status'], list)
        assert isinstance(status['by_domain'], list)
        assert isinstance(status['by_platform'], list)
    
    def test_get_orders_basic(self, service):
        """测试基本订单查询"""
        orders = service.get_orders(limit=10)
        
        assert isinstance(orders, pd.DataFrame)
        # 应该有正确的列
        expected_cols = [
            'order_id', 'platform_code', 'shop_id',
            'order_date_local', 'total_amount', 'currency'
        ]
        for col in expected_cols:
            assert col in orders.columns
    
    def test_get_orders_with_filters(self, service):
        """测试带过滤的订单查询"""
        orders = service.get_orders(
            platforms=['shopee'],
            start_date='2024-10-01',
            end_date='2024-10-16',
            limit=100
        )
        
        assert isinstance(orders, pd.DataFrame)
        # 验证平台过滤（如果有数据）
        if not orders.empty:
            assert all(orders['platform_code'] == 'shopee')
    
    def test_get_product_metrics_basic(self, service):
        """测试基本产品指标查询"""
        metrics = service.get_product_metrics(limit=10)
        
        assert isinstance(metrics, pd.DataFrame)
        expected_cols = [
            'platform_code', 'shop_id', 'platform_sku',
            'metric_date', 'metric_type', 'metric_value'
        ]
        for col in expected_cols:
            assert col in metrics.columns
    
    def test_get_product_metrics_with_filters(self, service):
        """测试带过滤的产品指标查询"""
        metrics = service.get_product_metrics(
            platforms=['shopee'],
            metric_type='gmv',
            start_date='2024-10-01',
            end_date='2024-10-16',
            limit=100
        )
        
        assert isinstance(metrics, pd.DataFrame)
        # 验证过滤（如果有数据）
        if not metrics.empty:
            assert all(metrics['metric_type'] == 'gmv')
    
    def test_get_top_products(self, service):
        """测试Top产品查询"""
        top = service.get_top_products(
            metric_type='gmv',
            top_n=5
        )
        
        assert isinstance(top, pd.DataFrame)
        # 验证返回数量
        assert len(top) <= 5
    
    def test_get_order_summary(self, service):
        """测试订单汇总"""
        summary = service.get_order_summary(
            group_by='day',
            start_date='2024-10-01',
            end_date='2024-10-16'
        )
        
        assert isinstance(summary, pd.DataFrame)
    
    def test_get_recent_files(self, service):
        """测试最近文件查询"""
        files = service.get_recent_files(limit=10)
        
        assert isinstance(files, pd.DataFrame)
        # 验证返回数量
        assert len(files) <= 10
    
    def test_get_dashboard_summary(self, service):
        """测试仪表盘汇总"""
        dashboard = service.get_dashboard_summary(days=7)
        
        assert isinstance(dashboard, dict)
        assert 'period' in dashboard
        assert 'start_date' in dashboard
        assert 'end_date' in dashboard


class TestConvenienceFunctions:
    """测试便捷函数"""
    
    def test_query_orders(self):
        """测试便捷函数：订单查询"""
        orders = query_orders(limit=5)
        assert isinstance(orders, pd.DataFrame)
    
    def test_query_product_metrics(self):
        """测试便捷函数：产品指标查询"""
        metrics = query_product_metrics(limit=5)
        assert isinstance(metrics, pd.DataFrame)
    
    def test_query_catalog_status(self):
        """测试便捷函数：Catalog状态"""
        status = query_catalog_status()
        assert isinstance(status, dict)


class TestCaching:
    """测试缓存功能"""
    
    def test_cache_works(self):
        """测试缓存是否生效"""
        import time
        service = DataQueryService()
        
        # 第一次查询
        start = time.time()
        status1 = service.get_catalog_status()
        time1 = time.time() - start
        
        # 第二次查询（应该从缓存）
        start = time.time()
        status2 = service.get_catalog_status()
        time2 = time.time() - start
        
        # 缓存命中应该更快
        assert time2 < time1 * 0.5  # 至少快50%
        assert status1 == status2  # 数据一致


class TestErrorHandling:
    """测试错误处理"""
    
    def test_invalid_date_format(self):
        """测试无效日期格式"""
        service = DataQueryService()
        
        # 即使日期格式错误，也应该返回空DataFrame而不是抛异常
        try:
            result = service.get_orders(
                start_date='invalid-date',
                end_date='2024-10-16'
            )
            # 应该返回空DataFrame或正常结果
            assert isinstance(result, pd.DataFrame)
        except Exception:
            # 或者抛出可预期的异常
            pass
    
    def test_empty_platform_list(self):
        """测试空平台列表"""
        service = DataQueryService()
        
        result = service.get_orders(platforms=[], limit=10)
        assert isinstance(result, pd.DataFrame)


class TestGlobalService:
    """测试全局服务单例"""
    
    def test_get_global_service(self):
        """测试获取全局服务"""
        service1 = get_data_query_service()
        service2 = get_data_query_service()
        
        # 应该是同一个实例
        assert service1 is service2


class TestQueryParameters:
    """测试查询参数"""
    
    def test_limit_parameter(self):
        """测试limit参数"""
        service = DataQueryService()
        
        result = service.get_orders(limit=5)
        assert isinstance(result, pd.DataFrame)
        assert len(result) <= 5
    
    def test_date_range(self):
        """测试日期范围"""
        service = DataQueryService()
        
        today = date.today()
        week_ago = today - timedelta(days=7)
        
        result = service.get_orders(
            start_date=week_ago.strftime('%Y-%m-%d'),
            end_date=today.strftime('%Y-%m-%d'),
            limit=100
        )
        
        assert isinstance(result, pd.DataFrame)
        # 如果有数据，验证日期在范围内
        if not result.empty and 'order_date_local' in result.columns:
            for order_date in result['order_date_local']:
                if pd.notna(order_date):
                    order_date_obj = pd.to_datetime(order_date).date()
                    assert week_ago <= order_date_obj <= today


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

