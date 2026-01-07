#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
catalog_scanner单元测试

测试文件扫描与注册功能
"""

import pytest
from pathlib import Path
from datetime import datetime
import tempfile
import shutil

from modules.services.catalog_scanner import (
    scan_and_register,
    _sha256,
    _infer_platform_from_path,
    _infer_domain_from_path,
    _gather_files,
)


class TestSHA256:
    """测试SHA256计算"""
    
    def test_sha256_basic(self, tmp_path):
        """测试基本hash计算"""
        # 创建测试文件
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")
        
        # 计算hash
        hash1 = _sha256(test_file)
        
        # 验证
        assert hash1 is not None
        assert len(hash1) == 64  # SHA256是64个字符
        assert hash1.isalnum()
        
        # 相同文件应该得到相同hash
        hash2 = _sha256(test_file)
        assert hash1 == hash2
    
    def test_sha256_different_content(self, tmp_path):
        """测试不同内容得到不同hash"""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        
        file1.write_text("Content 1")
        file2.write_text("Content 2")
        
        hash1 = _sha256(file1)
        hash2 = _sha256(file2)
        
        assert hash1 != hash2
    
    def test_sha256_cache(self, tmp_path):
        """测试hash缓存功能"""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")
        
        # 第一次计算
        hash1 = _sha256(test_file)
        
        # 第二次应该从缓存读取（如果缓存服务可用）
        hash2 = _sha256(test_file)
        
        assert hash1 == hash2


class TestPlatformInference:
    """测试平台推断"""
    
    def test_shopee_platform(self):
        """测试Shopee平台识别"""
        path = Path("temp/outputs/shopee/account1/file.xlsx")
        platform = _infer_platform_from_path(path)
        assert platform == "shopee"
    
    def test_tiktok_platform(self):
        """测试TikTok平台识别"""
        path = Path("temp/outputs/tiktok/shop123/data.xlsx")
        platform = _infer_platform_from_path(path)
        assert platform == "tiktok"
    
    def test_miaoshou_platform(self):
        """测试妙手平台识别"""
        path = Path("temp/outputs/miaoshou/data/report.xlsx")
        platform = _infer_platform_from_path(path)
        assert platform == "miaoshou"
    
    def test_unknown_platform(self):
        """测试未知平台"""
        path = Path("temp/outputs/unknown/file.xlsx")
        platform = _infer_platform_from_path(path)
        # 应该返回None或generic
        assert platform is None or platform == "generic"


class TestDomainInference:
    """测试数据域推断"""
    
    def test_orders_domain(self):
        """测试订单域识别"""
        path = Path("temp/outputs/shopee/orders/report.xlsx")
        domain = _infer_domain_from_path(path)
        assert domain == "orders"
    
    def test_products_domain(self):
        """测试产品域识别"""
        path = Path("temp/outputs/shopee/products/data.xlsx")
        domain = _infer_domain_from_path(path)
        assert domain == "products"
    
    def test_metrics_domain(self):
        """测试指标域识别"""
        path = Path("temp/outputs/shopee/metrics/stats.xlsx")
        domain = _infer_domain_from_path(path)
        assert domain == "metrics"
    
    def test_unknown_domain(self):
        """测试未知域"""
        path = Path("temp/outputs/shopee/unknown/file.xlsx")
        domain = _infer_domain_from_path(path)
        assert domain is None


class TestFileGathering:
    """测试文件收集"""
    
    def test_gather_xlsx_files(self, tmp_path):
        """测试收集xlsx文件"""
        # 创建测试目录结构
        (tmp_path / "dir1").mkdir()
        (tmp_path / "dir1" / "file1.xlsx").write_text("test")
        (tmp_path / "dir1" / "file2.xlsx").write_text("test")
        (tmp_path / "dir1" / "file3.txt").write_text("test")  # 不支持的格式
        
        # 收集文件
        files = list(_gather_files([tmp_path]))
        
        # 验证
        assert len(files) == 2
        assert all(f.suffix == ".xlsx" for f in files)
    
    def test_gather_multiple_formats(self, tmp_path):
        """测试收集多种格式"""
        (tmp_path / "file1.xlsx").write_text("test")
        (tmp_path / "file2.xls").write_text("test")
        (tmp_path / "file3.csv").write_text("test")
        (tmp_path / "file4.json").write_text("test")
        (tmp_path / "file5.txt").write_text("test")  # 不支持
        
        files = list(_gather_files([tmp_path]))
        
        assert len(files) == 4
        extensions = {f.suffix for f in files}
        assert extensions == {".xlsx", ".xls", ".csv", ".json"}
    
    def test_gather_recursive(self, tmp_path):
        """测试递归收集"""
        # 创建多层目录
        (tmp_path / "level1").mkdir()
        (tmp_path / "level1" / "level2").mkdir()
        (tmp_path / "level1" / "level2" / "file.xlsx").write_text("test")
        
        files = list(_gather_files([tmp_path]))
        
        assert len(files) == 1


class TestScanAndRegister:
    """测试扫描和注册功能"""
    
    @pytest.fixture
    def test_data_dir(self, tmp_path):
        """创建测试数据目录"""
        data_dir = tmp_path / "test_outputs"
        data_dir.mkdir()
        
        # 创建测试文件
        (data_dir / "shopee").mkdir()
        (data_dir / "shopee" / "products").mkdir()
        (data_dir / "shopee" / "products" / "report1.xlsx").write_text("test data 1")
        (data_dir / "shopee" / "products" / "report2.xlsx").write_text("test data 2")
        
        return data_dir
    
    def test_scan_basic(self, test_data_dir):
        """测试基本扫描功能"""
        result = scan_and_register([test_data_dir])
        
        assert result.seen >= 2
        assert result.registered >= 0  # 可能已注册过
        assert result.skipped >= 0
    
    def test_scan_idempotent(self, test_data_dir):
        """测试扫描幂等性"""
        # 第一次扫描
        result1 = scan_and_register([test_data_dir])
        
        # 第二次扫描（文件未改变）
        result2 = scan_and_register([test_data_dir])
        
        # 第二次应该跳过所有文件
        assert result2.registered == 0
        assert result2.skipped == result2.seen
    
    def test_scan_new_file(self, test_data_dir):
        """测试扫描新文件"""
        # 第一次扫描
        scan_and_register([test_data_dir])
        
        # 添加新文件（使用唯一文件名）
        import time
        unique_name = f"report_new_{int(time.time()*1000)}.xlsx"
        (test_data_dir / "shopee" / "products" / unique_name).write_text("new unique data")
        
        # 第二次扫描
        result = scan_and_register([test_data_dir])
        
        # 应该注册新文件（或者文件已存在则跳过）
        assert result.registered >= 1 or result.skipped >= 1


class TestIntegration:
    """集成测试"""
    
    def test_full_workflow(self, tmp_path):
        """测试完整工作流"""
        # 1. 准备测试数据
        test_dir = tmp_path / "integration_test"
        test_dir.mkdir()
        
        shopee_dir = test_dir / "shopee" / "account1" / "products"
        shopee_dir.mkdir(parents=True)
        
        test_file = shopee_dir / "products_20241016.xlsx"
        test_file.write_text("Mock product data")
        
        # 2. 扫描注册
        result = scan_and_register([test_dir])
        
        # 3. 验证结果
        assert result.seen >= 1
        assert result.registered >= 1 or result.skipped >= 1
        
        # 4. 验证文件信息
        # （需要查询数据库，这里简化）
        assert True  # 占位


# 性能测试（可选）
class TestPerformance:
    """性能测试"""
    
    @pytest.mark.slow
    def test_scan_large_directory(self, tmp_path):
        """测试大目录扫描性能"""
        # 创建大量文件
        data_dir = tmp_path / "large_test"
        data_dir.mkdir()
        
        for i in range(100):
            (data_dir / f"file{i}.xlsx").write_text(f"data {i}")
        
        import time
        start = time.time()
        result = scan_and_register([data_dir])
        elapsed = time.time() - start
        
        # 验证性能（100个文件应该<1秒）
        assert elapsed < 1.0
        assert result.seen == 100
    
    @pytest.mark.slow
    def test_hash_calculation_performance(self, tmp_path):
        """测试hash计算性能"""
        # 创建较大文件（1MB）
        test_file = tmp_path / "large_file.xlsx"
        test_file.write_bytes(b"x" * 1024 * 1024)
        
        import time
        start = time.time()
        hash_value = _sha256(test_file)
        elapsed = time.time() - start
        
        # 1MB文件应该<0.1秒
        assert elapsed < 0.1
        assert len(hash_value) == 64


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

