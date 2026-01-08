"""
批量数据导入测试工具
"""

import asyncio
import aiohttp
import time
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any
from dataclasses import dataclass
import statistics
import os

@dataclass
class ImportTestResult:
    """导入测试结果数据类"""
    test_name: str
    total_records: int
    successful_records: int
    failed_records: int
    total_time: float
    records_per_second: float
    average_response_time: float
    min_response_time: float
    max_response_time: float
    error_rate: float
    errors: List[str]
    memory_usage_mb: float

class BatchImportTester:
    """批量导入测试器"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = None
        self.results = []
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=300),  # 5分钟超时
            connector=aiohttp.TCPConnector(limit=50, limit_per_host=20)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    def generate_test_data(self, num_records: int, data_type: str = "orders") -> List[Dict]:
        """生成测试数据"""
        print(f"生成 {num_records} 条 {data_type} 测试数据...")
        
        if data_type == "orders":
            return self._generate_order_data(num_records)
        elif data_type == "products":
            return self._generate_product_data(num_records)
        elif data_type == "inventory":
            return self._generate_inventory_data(num_records)
        else:
            return self._generate_generic_data(num_records)
    
    def _generate_order_data(self, num_records: int) -> List[Dict]:
        """生成订单测试数据"""
        platforms = ["shopee", "tiktok", "amazon", "miaoshou"]
        statuses = ["pending", "paid", "shipped", "delivered", "cancelled"]
        
        data = []
        base_date = datetime.now() - timedelta(days=365)
        
        for i in range(num_records):
            order_date = base_date + timedelta(days=np.random.randint(0, 365))
            
            data.append({
                "order_id": f"ORD_{i+1:08d}",
                "platform": np.random.choice(platforms),
                "shop_id": f"shop_{np.random.randint(1, 100):03d}",
                "order_date": order_date.strftime("%Y-%m-%d"),
                "total_amount": round(np.random.uniform(10, 1000), 2),
                "currency": "USD",
                "status": np.random.choice(statuses),
                "customer_name": f"Customer_{i+1}",
                "customer_email": f"customer_{i+1}@example.com",
                "shipping_address": f"Address_{i+1}",
                "payment_method": np.random.choice(["credit_card", "paypal", "bank_transfer"]),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            })
        
        return data
    
    def _generate_product_data(self, num_records: int) -> List[Dict]:
        """生成产品测试数据"""
        categories = ["Electronics", "Clothing", "Home", "Sports", "Books"]
        brands = ["BrandA", "BrandB", "BrandC", "BrandD", "BrandE"]
        
        data = []
        
        for i in range(num_records):
            data.append({
                "sku": f"SKU_{i+1:08d}",
                "product_name": f"Product_{i+1}",
                "category": np.random.choice(categories),
                "brand": np.random.choice(brands),
                "price": round(np.random.uniform(5, 500), 2),
                "cost": round(np.random.uniform(2, 250), 2),
                "weight": round(np.random.uniform(0.1, 10), 2),
                "dimensions": f"{np.random.randint(5, 50)}x{np.random.randint(5, 50)}x{np.random.randint(1, 20)}",
                "description": f"Description for product {i+1}",
                "is_active": np.random.choice([True, False]),
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            })
        
        return data
    
    def _generate_inventory_data(self, num_records: int) -> List[Dict]:
        """生成库存测试数据"""
        warehouses = ["WH_001", "WH_002", "WH_003", "WH_004", "WH_005"]
        
        data = []
        
        for i in range(num_records):
            data.append({
                "sku": f"SKU_{i+1:08d}",
                "warehouse": np.random.choice(warehouses),
                "quantity_on_hand": np.random.randint(0, 1000),
                "quantity_reserved": np.random.randint(0, 100),
                "quantity_available": np.random.randint(0, 900),
                "reorder_point": np.random.randint(10, 100),
                "max_stock": np.random.randint(500, 2000),
                "location": f"Location_{np.random.randint(1, 50)}",
                "last_updated": datetime.now().isoformat()
            })
        
        return data
    
    def _generate_generic_data(self, num_records: int) -> List[Dict]:
        """生成通用测试数据"""
        data = []
        
        for i in range(num_records):
            data.append({
                "id": i + 1,
                "name": f"Record_{i+1}",
                "value": round(np.random.uniform(0, 1000), 2),
                "category": f"Category_{np.random.randint(1, 10)}",
                "status": np.random.choice(["active", "inactive", "pending"]),
                "created_at": datetime.now().isoformat()
            })
        
        return data
    
    async def test_batch_import(self, data: List[Dict], batch_size: int = 100, endpoint: str = "/api/test/batch-import") -> ImportTestResult:
        """测试批量导入"""
        print(f"开始批量导入测试: {len(data)} 条记录, 批次大小: {batch_size}")
        
        start_time = time.time()
        successful_records = 0
        failed_records = 0
        response_times = []
        errors = []
        
        # 分批处理数据
        for i in range(0, len(data), batch_size):
            batch = data[i:i + batch_size]
            batch_start = time.time()
            
            try:
                # 发送批量导入请求
                url = f"{self.base_url}{endpoint}"
                payload = {"data": batch, "batch_id": i // batch_size + 1}
                
                async with self.session.post(url, json=payload) as response:
                    response_time = time.time() - batch_start
                    response_times.append(response_time)
                    
                    if response.status < 400:
                        result = await response.json()
                        successful_records += result.get("successful_count", len(batch))
                        failed_records += result.get("failed_count", 0)
                    else:
                        failed_records += len(batch)
                        errors.append(f"HTTP {response.status}: {await response.text()}")
                
            except Exception as e:
                response_time = time.time() - batch_start
                response_times.append(response_time)
                failed_records += len(batch)
                errors.append(str(e))
            
            # 显示进度
            if (i // batch_size + 1) % 10 == 0:
                progress = (i + len(batch)) / len(data) * 100
                print(f"进度: {progress:.1f}% ({i + len(batch)}/{len(data)})")
        
        total_time = time.time() - start_time
        
        return ImportTestResult(
            test_name="Batch Import",
            total_records=len(data),
            successful_records=successful_records,
            failed_records=failed_records,
            total_time=total_time,
            records_per_second=len(data) / total_time if total_time > 0 else 0,
            average_response_time=statistics.mean(response_times) if response_times else 0,
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            error_rate=failed_records / len(data) * 100 if data else 0,
            errors=errors[:10],
            memory_usage_mb=0  # 这里可以添加内存监控
        )
    
    async def test_individual_imports(self, data: List[Dict], max_concurrent: int = 10) -> ImportTestResult:
        """测试单个记录导入（并发）"""
        print(f"开始单个记录导入测试: {len(data)} 条记录, 最大并发: {max_concurrent}")
        
        start_time = time.time()
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def import_single_record(record, index):
            async with semaphore:
                record_start = time.time()
                try:
                    url = f"{self.base_url}/api/test/single-import"
                    async with self.session.post(url, json=record) as response:
                        response_time = time.time() - record_start
                        if response.status < 400:
                            return {"success": True, "response_time": response_time, "error": None}
                        else:
                            return {"success": False, "response_time": response_time, "error": f"HTTP {response.status}"}
                except Exception as e:
                    response_time = time.time() - record_start
                    return {"success": False, "response_time": response_time, "error": str(e)}
        
        # 创建所有任务
        tasks = [import_single_record(record, i) for i, record in enumerate(data)]
        
        # 执行所有任务
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_time = time.time() - start_time
        
        # 处理结果
        successful = [r for r in results if isinstance(r, dict) and r.get("success", False)]
        failed = [r for r in results if isinstance(r, dict) and not r.get("success", False)]
        exceptions = [r for r in results if isinstance(r, Exception)]
        
        response_times = [r["response_time"] for r in successful + failed]
        errors = [r.get("error", "Unknown error") for r in failed] + [str(e) for e in exceptions]
        
        return ImportTestResult(
            test_name="Individual Imports",
            total_records=len(data),
            successful_records=len(successful),
            failed_records=len(failed) + len(exceptions),
            total_time=total_time,
            records_per_second=len(data) / total_time if total_time > 0 else 0,
            average_response_time=statistics.mean(response_times) if response_times else 0,
            min_response_time=min(response_times) if response_times else 0,
            max_response_time=max(response_times) if response_times else 0,
            error_rate=(len(failed) + len(exceptions)) / len(data) * 100 if data else 0,
            errors=errors[:10],
            memory_usage_mb=0
        )
    
    def print_test_result(self, result: ImportTestResult):
        """打印测试结果"""
        print(f"\n{'='*60}")
        print(f"测试名称: {result.test_name}")
        print(f"{'='*60}")
        print(f"总记录数: {result.total_records}")
        print(f"成功记录: {result.successful_records}")
        print(f"失败记录: {result.failed_records}")
        print(f"总耗时: {result.total_time:.2f}秒")
        print(f"每秒处理记录数: {result.records_per_second:.2f}")
        print(f"平均响应时间: {result.average_response_time:.3f}秒")
        print(f"最小响应时间: {result.min_response_time:.3f}秒")
        print(f"最大响应时间: {result.max_response_time:.3f}秒")
        print(f"错误率: {result.error_rate:.2f}%")
        
        if result.errors:
            print(f"\n错误示例:")
            for error in result.errors[:5]:
                print(f"  - {error}")
    
    def save_test_results(self, results: List[ImportTestResult], filename: str):
        """保存测试结果到文件"""
        try:
            data = {
                "test_time": datetime.now().isoformat(),
                "results": [
                    {
                        "test_name": r.test_name,
                        "total_records": r.total_records,
                        "successful_records": r.successful_records,
                        "failed_records": r.failed_records,
                        "total_time": r.total_time,
                        "records_per_second": r.records_per_second,
                        "average_response_time": r.average_response_time,
                        "min_response_time": r.min_response_time,
                        "max_response_time": r.max_response_time,
                        "error_rate": r.error_rate,
                        "errors": r.errors,
                        "memory_usage_mb": r.memory_usage_mb
                    }
                    for r in results
                ]
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            print(f"\n测试结果已保存到: {filename}")
        except Exception as e:
            print(f"保存测试结果失败: {e}")

async def run_batch_import_tests():
    """运行批量导入测试"""
    print("[START] 开始批量数据导入测试")
    print("="*60)
    
    # 测试配置
    test_configs = [
        {"records": 1000, "batch_size": 100, "name": "小批量测试"},
        {"records": 10000, "batch_size": 500, "name": "中批量测试"},
        {"records": 50000, "batch_size": 1000, "name": "大批量测试"},
        {"records": 100000, "batch_size": 2000, "name": "超大批量测试"}
    ]
    
    all_results = []
    
    async with BatchImportTester() as tester:
        for config in test_configs:
            print(f"\n[TEST] {config['name']}: {config['records']} 条记录, 批次大小: {config['batch_size']}")
            print("-" * 60)
            
            # 生成测试数据
            test_data = tester.generate_test_data(config["records"], "orders")
            
            # 批量导入测试
            batch_result = await tester.test_batch_import(test_data, config["batch_size"])
            tester.print_test_result(batch_result)
            all_results.append(batch_result)
            
            # 单个导入测试（使用较小的数据集）
            if config["records"] <= 10000:
                individual_data = test_data[:1000]  # 限制为1000条记录
                individual_result = await tester.test_individual_imports(individual_data, max_concurrent=20)
                tester.print_test_result(individual_result)
                all_results.append(individual_result)
            
            # 等待一段时间再进行下一轮测试
            print(f"\n[WAIT] 等待10秒后进行下一轮测试...")
            await asyncio.sleep(10)
    
    # 保存所有测试结果
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"temp/outputs/batch_import_test_results_{timestamp}.json"
    tester.save_test_results(all_results, filename)
    
    print(f"\n[DONE] 批量数据导入测试完成！")
    print(f"总共执行了 {len(all_results)} 个测试")
    print(f"结果已保存到: {filename}")

if __name__ == "__main__":
    asyncio.run(run_batch_import_tests())
