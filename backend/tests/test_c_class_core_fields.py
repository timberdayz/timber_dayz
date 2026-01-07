#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C类数据核心字段验证和数据质量检查单元测试

测试内容：
1. 核心字段验证逻辑
2. 数据质量检查服务
3. 货币策略验证
4. 物化视图查询性能

用于C类数据核心字段优化计划
"""

import pytest
from datetime import date, datetime
from sqlalchemy.orm import Session
from unittest.mock import Mock, patch

from backend.services.c_class_data_validator import CClassDataValidator, get_c_class_data_validator
from backend.services.currency_validator import CurrencyValidator, get_currency_validator
from modules.core.db import FactOrder, FactProductMetric, FieldMappingDictionary


class TestCClassDataValidator:
    """C类数据完整性检查服务测试"""
    
    def test_check_b_class_completeness_orders_complete(self):
        """测试订单数据完整性检查（完整数据）"""
        # 模拟数据库会话
        db = Mock(spec=Session)
        
        # 模拟订单数据查询结果
        mock_order = Mock()
        mock_order.order_id = "ORD001"
        mock_order.order_date_local = date(2025, 1, 31)
        mock_order.total_amount_rmb = 1000.0
        mock_order.order_status = "completed"
        mock_order.platform_code = "shopee"
        mock_order.shop_id = "shop001"
        mock_order.buyer_id = "buyer001"
        
        mock_orders = [mock_order]
        
        # 模拟查询执行
        db.execute.return_value.scalars.return_value.all.return_value = mock_orders
        
        # 创建验证器
        validator = CClassDataValidator(db)
        
        # 执行检查
        result = validator.check_b_class_completeness(
            platform_code="shopee",
            shop_id="shop001",
            metric_date=date(2025, 1, 31),
            data_domain="orders"
        )
        
        # 验证结果
        assert result["orders_complete"] is True
        assert len(result["missing_fields"]) == 0
        assert result["data_quality_score"] > 0
    
    def test_check_b_class_completeness_orders_missing_fields(self):
        """测试订单数据完整性检查（缺失字段）"""
        # 模拟数据库会话
        db = Mock(spec=Session)
        
        # 模拟订单数据（缺失total_amount_rmb字段）
        mock_order = Mock()
        mock_order.order_id = "ORD001"
        mock_order.order_date_local = date(2025, 1, 31)
        mock_order.total_amount_rmb = None  # 缺失字段
        mock_order.order_status = "completed"
        mock_order.platform_code = "shopee"
        mock_order.shop_id = "shop001"
        
        mock_orders = [mock_order]
        
        # 模拟查询执行
        db.execute.return_value.scalars.return_value.all.return_value = mock_orders
        
        # 创建验证器
        validator = CClassDataValidator(db)
        
        # 执行检查
        result = validator.check_b_class_completeness(
            platform_code="shopee",
            shop_id="shop001",
            metric_date=date(2025, 1, 31),
            data_domain="orders"
        )
        
        # 验证结果
        assert result["orders_complete"] is False
        assert "orders.total_amount_rmb" in result["missing_fields"]
        assert len(result["warnings"]) > 0
    
    def test_check_b_class_completeness_products_complete(self):
        """测试产品数据完整性检查（完整数据）"""
        # 模拟数据库会话
        db = Mock(spec=Session)
        
        # 模拟产品数据查询结果
        mock_product = Mock()
        mock_product.unique_visitors = 1000
        mock_product.order_count = 50
        mock_product.rating = 4.5
        mock_product.metric_date = date(2025, 1, 31)
        mock_product.data_domain = "products"
        mock_product.sales_volume = 100
        mock_product.sales_amount_rmb = 5000.0
        mock_product.conversion_rate = 5.0
        
        mock_products = [mock_product]
        
        # 模拟查询执行
        db.execute.return_value.scalars.return_value.all.return_value = mock_products
        
        # 创建验证器
        validator = CClassDataValidator(db)
        
        # 执行检查
        result = validator.check_b_class_completeness(
            platform_code="shopee",
            shop_id="shop001",
            metric_date=date(2025, 1, 31),
            data_domain="products"
        )
        
        # 验证结果
        assert result["products_complete"] is True
        assert len(result["missing_fields"]) == 0
    
    def test_check_b_class_completeness_products_missing_visitors(self):
        """测试产品数据完整性检查（缺失访客数）"""
        # 模拟数据库会话
        db = Mock(spec=Session)
        
        # 模拟产品数据（缺失unique_visitors字段）
        mock_product = Mock()
        mock_product.unique_visitors = None  # 缺失字段
        mock_product.order_count = 50
        mock_product.rating = 4.5
        
        mock_products = [mock_product]
        
        # 模拟查询执行
        db.execute.return_value.scalars.return_value.all.return_value = mock_products
        
        # 创建验证器
        validator = CClassDataValidator(db)
        
        # 执行检查
        result = validator.check_b_class_completeness(
            platform_code="shopee",
            shop_id="shop001",
            metric_date=date(2025, 1, 31),
            data_domain="products"
        )
        
        # 验证结果
        assert result["products_complete"] is False
        assert "products.unique_visitors" in result["missing_fields"]
        assert len(result["warnings"]) > 0
    
    def test_generate_quality_report(self):
        """测试生成数据质量报告"""
        # 模拟数据库会话
        db = Mock(spec=Session)
        
        # 模拟数据查询（简化版）
        db.execute.return_value.scalars.return_value.all.return_value = []
        
        # 创建验证器
        validator = CClassDataValidator(db)
        
        # 执行报告生成
        report = validator.generate_quality_report(
            platform_code="shopee",
            shop_id="shop001",
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 31)
        )
        
        # 验证报告结构
        assert "platform_code" in report
        assert "shop_id" in report
        assert "date_range" in report
        assert "daily_checks" in report
        assert "summary" in report
        assert report["summary"]["total_days"] == 31


class TestCurrencyValidator:
    """货币字段验证服务测试"""
    
    def test_validate_currency_policy_orders_cny(self):
        """测试订单域CNY货币策略验证（通过）"""
        validator = CurrencyValidator()
        
        result = validator.validate_currency_policy(
            field_code="total_amount_rmb",
            data_domain="orders",
            value=1000.0
        )
        
        assert result.valid is True
        assert result.error is None
    
    def test_validate_currency_policy_orders_non_cny(self):
        """测试订单域非CNY货币策略验证（失败）"""
        validator = CurrencyValidator()
        
        # 模拟检测到SGD货币符号
        with patch.object(validator, '_detect_currency_symbol', return_value='SGD'):
            result = validator.validate_currency_policy(
                field_code="total_amount_sgd",
                data_domain="orders",
                value="S$1000.00"
            )
        
        assert result.valid is False
        assert "非CNY货币" in result.error or "SGD" in result.error
    
    def test_validate_currency_policy_products_no_currency(self):
        """测试产品域无货币策略验证（通过）"""
        validator = CurrencyValidator()
        
        result = validator.validate_currency_policy(
            field_code="sales_volume",
            data_domain="products",
            value=100
        )
        
        assert result.valid is True
    
    def test_validate_currency_policy_products_currency_field(self):
        """测试产品域货币字段验证（失败）"""
        validator = CurrencyValidator()
        
        result = validator.validate_currency_policy(
            field_code="sales_amount_sgd",
            data_domain="products",
            value=1000.0
        )
        
        assert result.valid is False
        assert "禁止货币字段" in result.error
    
    def test_is_currency_field(self):
        """测试货币字段识别"""
        validator = CurrencyValidator()
        
        # 测试货币字段
        assert validator._is_currency_field("total_amount_rmb") is True
        assert validator._is_currency_field("sales_amount") is True
        assert validator._is_currency_field("price") is True
        
        # 测试非货币字段
        assert validator._is_currency_field("sales_volume") is False
        assert validator._is_currency_field("order_count") is False
        assert validator._is_currency_field("rating") is False
    
    def test_is_cny_field(self):
        """测试CNY字段识别"""
        validator = CurrencyValidator()
        
        # 测试CNY字段
        assert validator._is_cny_field("total_amount_rmb") is True
        assert validator._is_cny_field("sales_amount_cny") is True
        assert validator._is_cny_field("price_rmb") is True
        
        # 测试非CNY字段
        assert validator._is_cny_field("total_amount_sgd") is False
        assert validator._is_cny_field("sales_amount") is False
    
    def test_detect_currency_symbol(self):
        """测试货币符号检测"""
        validator = CurrencyValidator()
        
        # 测试CNY符号
        assert validator._detect_currency_symbol("¥1000") == "CNY"
        assert validator._detect_currency_symbol("CNY1000") == "CNY"
        assert validator._detect_currency_symbol("人民币1000") == "CNY"
        
        # 测试SGD符号
        assert validator._detect_currency_symbol("S$1000") == "SGD"
        assert validator._detect_currency_symbol("SGD1000") == "SGD"
        
        # 测试无货币符号
        assert validator._detect_currency_symbol("1000") is None
        assert validator._detect_currency_symbol(1000) is None
    
    def test_validate_batch_fields(self):
        """测试批量字段验证"""
        validator = CurrencyValidator()
        
        fields = {
            "total_amount_rmb": 1000.0,
            "sales_volume": 100,
            "sales_amount_sgd": 500.0
        }
        
        results = validator.validate_batch_fields(fields, "orders")
        
        assert "total_amount_rmb" in results
        assert "sales_volume" in results
        assert "sales_amount_sgd" in results
        assert results["total_amount_rmb"].valid is True
        assert results["sales_amount_sgd"].valid is False
    
    def test_detect_multi_currency(self):
        """测试多币种检测"""
        validator = CurrencyValidator()
        
        fields = {
            "total_amount_rmb": 1000.0,
            "sales_amount_sgd": 500.0,
            "sales_volume": 100
        }
        
        violations = validator.detect_multi_currency(fields, "orders")
        
        # 应该检测到SGD货币违规
        assert len(violations) > 0
        assert any("SGD" in v["error"] for v in violations)


class TestCoreFieldsVerification:
    """核心字段验证测试"""
    
    def test_c_class_core_fields_definition(self):
        """测试C类数据核心字段定义完整性"""
        from scripts.verify_c_class_core_fields import C_CLASS_CORE_FIELDS
        
        # 验证字段定义
        assert "orders" in C_CLASS_CORE_FIELDS
        assert "products" in C_CLASS_CORE_FIELDS
        assert "inventory" in C_CLASS_CORE_FIELDS
        
        # 验证订单域字段数量
        assert len(C_CLASS_CORE_FIELDS["orders"]) == 6
        
        # 验证产品域字段数量
        assert len(C_CLASS_CORE_FIELDS["products"]) == 8
        
        # 验证库存域字段数量
        assert len(C_CLASS_CORE_FIELDS["inventory"]) == 2
        
        # 验证关键字段存在
        assert "order_id" in C_CLASS_CORE_FIELDS["orders"]
        assert "total_amount_rmb" in C_CLASS_CORE_FIELDS["orders"]
        assert "unique_visitors" in C_CLASS_CORE_FIELDS["products"]
        assert "conversion_rate" in C_CLASS_CORE_FIELDS["products"]
        assert "available_stock" in C_CLASS_CORE_FIELDS["inventory"]


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

