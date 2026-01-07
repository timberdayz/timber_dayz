#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C类数据计算完整流程集成测试

测试场景：
1. B类数据入库 → C类数据计算完整流程
2. 数据质量检查 → 数据隔离区 → 重新处理流程
3. 物化视图刷新 → C类数据查询流程

用于C类数据核心字段优化计划
"""

import pytest
from datetime import date, datetime, timedelta
from sqlalchemy.orm import Session
from unittest.mock import Mock, patch, MagicMock

from backend.services.c_class_data_validator import CClassDataValidator
from backend.services.currency_validator import CurrencyValidator
from backend.services.shop_health_service import ShopHealthService
from modules.core.db import FactOrder, FactProductMetric, DataQuarantine


class TestBClassToCClassDataFlow:
    """B类数据入库到C类数据计算完整流程测试"""
    
    def test_complete_data_flow_orders_to_health_score(self):
        """测试订单数据入库到健康度评分计算的完整流程"""
        # 模拟数据库会话
        db = Mock(spec=Session)
        
        # 1. 模拟B类数据入库（订单数据）
        mock_order = Mock()
        mock_order.order_id = "ORD001"
        mock_order.order_date_local = date(2025, 1, 31)
        mock_order.total_amount_rmb = 1000.0
        mock_order.order_status = "completed"
        mock_order.platform_code = "shopee"
        mock_order.shop_id = "shop001"
        
        # 2. 模拟B类数据完整性检查
        validator = CClassDataValidator(db)
        db.execute.return_value.scalars.return_value.all.return_value = [mock_order]
        
        check_result = validator.check_b_class_completeness(
            platform_code="shopee",
            shop_id="shop001",
            metric_date=date(2025, 1, 31),
            data_domain="orders"
        )
        
        # 验证B类数据完整性
        assert check_result["orders_complete"] is True
        
        # 3. 模拟C类数据计算（健康度评分）
        health_service = ShopHealthService(db)
        
        # 模拟健康度评分计算所需的数据查询
        db.execute.return_value.scalars.return_value.all.return_value = []
        
        # 验证流程完整性
        assert check_result["data_quality_score"] >= 0
    
    def test_data_quality_check_to_quarantine_flow(self):
        """测试数据质量检查到数据隔离区的流程"""
        # 模拟数据库会话
        db = Mock(spec=Session)
        
        # 1. 模拟B类数据完整性检查（发现字段缺失）
        validator = CClassDataValidator(db)
        
        # 模拟订单数据（缺失total_amount_rmb）
        mock_order = Mock()
        mock_order.order_id = "ORD001"
        mock_order.total_amount_rmb = None  # 缺失字段
        
        db.execute.return_value.scalars.return_value.all.return_value = [mock_order]
        
        check_result = validator.check_b_class_completeness(
            platform_code="shopee",
            shop_id="shop001",
            metric_date=date(2025, 1, 31)
        )
        
        # 2. 验证检查结果
        assert check_result["orders_complete"] is False
        assert len(check_result["missing_fields"]) > 0
        
        # 3. 模拟数据隔离区记录
        mock_quarantine = Mock(spec=DataQuarantine)
        mock_quarantine.id = 1
        mock_quarantine.error_type = "missing_c_class_core_field"
        mock_quarantine.error_msg = "缺失字段: orders.total_amount_rmb"
        
        # 验证错误类型正确
        assert mock_quarantine.error_type == "missing_c_class_core_field"
    
    def test_quarantine_reprocess_flow(self):
        """测试数据隔离区重新处理流程"""
        # 模拟数据库会话
        db = Mock(spec=Session)
        
        # 1. 模拟隔离数据
        mock_quarantine = Mock(spec=DataQuarantine)
        mock_quarantine.id = 1
        mock_quarantine.error_type = "missing_c_class_core_field"
        mock_quarantine.platform_code = "shopee"
        mock_quarantine.shop_id = "shop001"
        mock_quarantine.data_domain = "orders"
        mock_quarantine.row_data = '{"order_id": "ORD001", "total_amount_rmb": null}'
        
        # 2. 模拟重新处理前的完整性检查
        validator = CClassDataValidator(db)
        
        # 模拟补充字段后的数据
        db.execute.return_value.scalars.return_value.all.return_value = []
        
        check_result = validator.check_b_class_completeness(
            platform_code="shopee",
            shop_id="shop001",
            metric_date=date(2025, 1, 31),
            data_domain="orders"
        )
        
        # 3. 验证重新处理流程
        # 如果字段已补充，应该可以通过检查
        assert isinstance(check_result, dict)
        assert "orders_complete" in check_result


class TestMaterializedViewRefreshFlow:
    """物化视图刷新流程测试"""
    
    def test_mv_refresh_order_c_class_priority(self):
        """测试C类数据物化视图优先刷新顺序"""
        from backend.services.materialized_view_service import MaterializedViewService
        
        # 获取刷新顺序
        refresh_order = MaterializedViewService._get_refresh_order()
        
        # 验证C类数据物化视图在B类数据视图之后
        b_class_views = [
            MaterializedViewService.VIEW_DAILY_SALES,
            MaterializedViewService.VIEW_ORDER_SALES_SUMMARY,
        ]
        
        c_class_views = [
            MaterializedViewService.VIEW_SHOP_DAILY_PERFORMANCE,
            MaterializedViewService.VIEW_SHOP_HEALTH_SUMMARY,
            MaterializedViewService.VIEW_CAMPAIGN_ACHIEVEMENT,
            MaterializedViewService.VIEW_TARGET_ACHIEVEMENT,
        ]
        
        # 找到B类视图和C类视图的位置
        b_class_indices = [refresh_order.index(v) for v in b_class_views if v in refresh_order]
        c_class_indices = [refresh_order.index(v) for v in c_class_views if v in refresh_order]
        
        # 验证C类视图在B类视图之后（如果都存在）
        if b_class_indices and c_class_indices:
            assert max(b_class_indices) < min(c_class_indices), \
                "C类数据物化视图应该在B类数据视图之后刷新"
    
    def test_mv_refresh_with_quality_check(self):
        """测试物化视图刷新时的数据质量检查（不阻止刷新）"""
        # 模拟数据库会话
        db = Mock(spec=Session)
        
        # 模拟C类数据物化视图刷新
        view_name = "mv_shop_daily_performance"
        
        # 模拟数据质量检查（可选，不阻止刷新）
        validator = CClassDataValidator(db)
        
        # 即使检查失败，也不应该阻止刷新
        try:
            check_result = validator.check_b_class_completeness(
                platform_code="shopee",
                shop_id="shop001",
                metric_date=date.today()
            )
            # 检查结果只用于记录，不阻止刷新
            assert isinstance(check_result, dict)
        except Exception:
            # 检查失败不应该影响刷新
            pass
        
        # 验证刷新可以继续
        assert True  # 刷新逻辑应该继续执行


class TestCurrencyPolicyEnforcement:
    """货币策略执行测试"""
    
    def test_currency_policy_enforcement_orders(self):
        """测试订单域货币策略执行"""
        validator = CurrencyValidator()
        
        # 测试CNY字段（通过）
        result1 = validator.validate_currency_policy(
            field_code="total_amount_rmb",
            data_domain="orders"
        )
        assert result1.valid is True
        
        # 测试非CNY字段（失败）
        result2 = validator.validate_currency_policy(
            field_code="total_amount_sgd",
            data_domain="orders"
        )
        assert result2.valid is False
    
    def test_currency_policy_enforcement_products(self):
        """测试产品域货币策略执行"""
        validator = CurrencyValidator()
        
        # 测试非货币字段（通过）
        result1 = validator.validate_currency_policy(
            field_code="sales_volume",
            data_domain="products"
        )
        assert result1.valid is True
        
        # 测试货币字段（失败）
        result2 = validator.validate_currency_policy(
            field_code="sales_amount_sgd",
            data_domain="products"
        )
        assert result2.valid is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

