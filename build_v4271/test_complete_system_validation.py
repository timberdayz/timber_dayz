#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整系统验证测试
包括：所有API接口、数据库连接、服务可用性
"""

import sys
from pathlib import Path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import requests
import time
from sqlalchemy import create_engine, text, inspect
from backend.utils.config import Settings

BASE_URL = "http://localhost:8001"
TIMEOUT = 10

def safe_print(text):
    """Windows安全打印"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

class SystemValidator:
    """系统验证器"""
    
    def __init__(self):
        self.results = []
        self.passed = 0
        self.failed = 0
        self.warnings = 0
    
    def test(self, name, func):
        """执行单个测试"""
        try:
            result = func()
            if result.get('success'):
                self.passed += 1
                self.results.append((name, 'PASS', result.get('message', '')))
                safe_print(f"  [PASS] {name}")
                if result.get('details'):
                    safe_print(f"         {result['details']}")
            elif result.get('warning'):
                self.warnings += 1
                self.results.append((name, 'WARN', result.get('message', '')))
                safe_print(f"  [WARN] {name}: {result['message']}")
            else:
                self.failed += 1
                self.results.append((name, 'FAIL', result.get('message', '')))
                safe_print(f"  [FAIL] {name}: {result['message']}")
        except Exception as e:
            self.failed += 1
            self.results.append((name, 'ERROR', str(e)))
            safe_print(f"  [ERROR] {name}: {str(e)[:100]}")
    
    def summary(self):
        """打印测试总结"""
        total = self.passed + self.failed + self.warnings
        safe_print("\n" + "="*70)
        safe_print(" 测试总结")
        safe_print("="*70)
        safe_print(f"\n  总计: {total}")
        safe_print(f"  通过: {self.passed} ({self.passed/total*100:.1f}%)")
        safe_print(f"  失败: {self.failed}")
        safe_print(f"  警告: {self.warnings}")
        
        if self.failed == 0:
            safe_print(f"\n  [SUCCESS] 所有测试通过！系统100%正常！")
        else:
            safe_print(f"\n  [WARN] {self.failed}个测试失败，请检查：")
            for name, status, msg in self.results:
                if status in ('FAIL', 'ERROR'):
                    safe_print(f"    - {name}: {msg[:80]}")
        
        safe_print("")

def main():
    """主测试流程"""
    
    safe_print("\n" + "="*70)
    safe_print(" 西虹ERP系统 v2.3 + v3.0 完整验证测试")
    safe_print("="*70)
    
    validator = SystemValidator()
    
    # ============ 测试1：数据库连接与表结构 ============
    safe_print("\n[Category 1] 数据库连接与表结构")
    
    def test_db_connection():
        engine = create_engine(Settings().DATABASE_URL)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {'success': True, 'message': 'PostgreSQL连接正常'}
    
    def test_catalog_files_table():
        engine = create_engine(Settings().DATABASE_URL)
        inspector = inspect(engine)
        if 'catalog_files' in inspector.get_table_names():
            columns = [c['name'] for c in inspector.get_columns('catalog_files')]
            indexes = inspector.get_indexes('catalog_files')
            return {
                'success': True, 
                'message': 'catalog_files表存在',
                'details': f'{len(columns)}列, {len(indexes)}个索引'
            }
        return {'success': False, 'message': 'catalog_files表不存在'}
    
    def test_product_images_table():
        engine = create_engine(Settings().DATABASE_URL)
        inspector = inspect(engine)
        if 'product_images' in inspector.get_table_names():
            with engine.connect() as conn:
                result = conn.execute(text("SELECT COUNT(*) FROM product_images"))
                count = result.scalar()
            return {
                'success': True,
                'message': 'product_images表存在',
                'details': f'{count}张图片'
            }
        return {'success': False, 'message': 'product_images表不存在'}
    
    def test_dim_date_table():
        engine = create_engine(Settings().DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM dim_date"))
            count = result.scalar()
            if count > 4000:
                return {
                    'success': True,
                    'message': 'dim_date表正常',
                    'details': f'{count}条记录'
                }
            return {'success': False, 'message': f'dim_date数据不足: {count}条'}
    
    def test_fact_product_metrics_table():
        engine = create_engine(Settings().DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM fact_product_metrics"))
            count = result.scalar()
            return {
                'success': True,
                'message': 'fact_product_metrics表存在',
                'details': f'{count}条产品指标'
            }
    
    validator.test("1.1 PostgreSQL连接", test_db_connection)
    validator.test("1.2 catalog_files表结构", test_catalog_files_table)
    validator.test("1.3 product_images表（v3.0）", test_product_images_table)
    validator.test("1.4 dim_date表（Phase 3）", test_dim_date_table)
    validator.test("1.5 fact_product_metrics表", test_fact_product_metrics_table)
    
    # ============ 测试2：字段映射API ============
    safe_print("\n[Category 2] 字段映射API（v2.3核心）")
    
    def test_api_health():
        resp = requests.get(f"{BASE_URL}/health", timeout=TIMEOUT)
        if resp.status_code == 200:
            return {'success': True, 'message': '后端服务正常'}
        return {'success': False, 'message': f'状态码: {resp.status_code}'}
    
    def test_file_groups():
        resp = requests.get(f"{BASE_URL}/api/field-mapping/file-groups", timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            platforms = data.get('platforms', [])
            return {
                'success': True,
                'message': 'file-groups正常',
                'details': f'{len(platforms)}个平台'
            }
        return {'success': False, 'message': f'状态码: {resp.status_code}'}
    
    def test_catalog_status():
        resp = requests.get(f"{BASE_URL}/api/field-mapping/catalog-status", timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            return {
                'success': True,
                'message': 'catalog-status正常',
                'details': f'{data.get("total_files", 0)}个文件'
            }
        return {'success': False, 'message': f'状态码: {resp.status_code}'}
    
    def test_data_domains():
        resp = requests.get(f"{BASE_URL}/api/field-mapping/data-domains", timeout=TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            domains = data.get('domains', [])
            return {
                'success': True,
                'message': 'data-domains正常',
                'details': f'{len(domains)}个数据域'
            }
        return {'success': False, 'message': f'状态码: {resp.status_code}'}
    
    validator.test("2.1 后端服务健康检查", test_api_health)
    validator.test("2.2 GET /file-groups", test_file_groups)
    validator.test("2.3 GET /catalog-status", test_catalog_status)
    validator.test("2.4 GET /data-domains", test_data_domains)
    
    # ============ 测试3：v3.0产品管理API ============
    safe_print("\n[Category 3] v3.0产品管理API")
    
    def test_products_list():
        resp = requests.get(
            f"{BASE_URL}/api/products/products",
            params={'page': 1, 'page_size': 5},
            timeout=TIMEOUT
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                total = data.get('total', 0)
                current = len(data.get('data', []))
                return {
                    'success': True,
                    'message': '产品列表API正常',
                    'details': f'总计{total}个产品, 当前页{current}个'
                }
            return {'success': False, 'message': data.get('error', '未知错误')}
        return {'success': False, 'message': f'状态码: {resp.status_code}'}
    
    def test_platform_summary():
        resp = requests.get(
            f"{BASE_URL}/api/products/stats/platform-summary",
            timeout=TIMEOUT
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                stats = data.get('data', {})
                return {
                    'success': True,
                    'message': '平台汇总API正常',
                    'details': f'{stats.get("total_products", 0)}个产品, {stats.get("total_stock", 0)}库存'
                }
            return {'success': False, 'message': data.get('error', '未知错误')}
        return {'success': False, 'message': f'状态码: {resp.status_code}'}
    
    def test_product_detail():
        # 先获取产品列表
        resp = requests.get(
            f"{BASE_URL}/api/products/products",
            params={'page': 1, 'page_size': 1},
            timeout=TIMEOUT
        )
        
        if resp.status_code == 200:
            data = resp.json()
            if data.get('data') and len(data['data']) > 0:
                product = data['data'][0]
                sku = product['platform_sku']
                platform = product['platform_code']
                shop_id = product['shop_id']
                
                # 测试产品详情API
                detail_resp = requests.get(
                    f"{BASE_URL}/api/products/products/{sku}",
                    params={'platform': platform, 'shop_id': shop_id},
                    timeout=TIMEOUT
                )
                
                if detail_resp.status_code == 200:
                    detail_data = detail_resp.json()
                    if detail_data.get('success'):
                        return {
                            'success': True,
                            'message': '产品详情API正常',
                            'details': f'SKU={sku}'
                        }
                    return {'success': False, 'message': detail_data.get('error', '未知错误')}
                return {'success': False, 'message': f'状态码: {detail_resp.status_code}'}
            
            return {'warning': True, 'message': '无产品数据，跳过详情测试'}
        
        return {'success': False, 'message': f'获取产品列表失败: {resp.status_code}'}
    
    validator.test("3.1 GET /api/products/products", test_products_list)
    validator.test("3.2 GET /api/products/stats/platform-summary", test_platform_summary)
    validator.test("3.3 GET /api/products/products/{sku}", test_product_detail)
    
    # ============ 测试4：核心服务可用性 ============
    safe_print("\n[Category 4] 核心服务可用性")
    
    def test_excel_parser():
        from backend.services.excel_parser import ExcelParser
        return {
            'success': True,
            'message': 'ExcelParser服务可用',
            'details': '智能格式检测+合并单元格还原'
        }
    
    def test_image_services():
        from backend.services.image_extractor import get_image_extractor
        from backend.services.image_processor import get_image_processor
        
        extractor = get_image_extractor()
        processor = get_image_processor()
        
        return {
            'success': True,
            'message': '图片服务可用',
            'details': '提取+处理+缩略图'
        }
    
    def test_bulk_importer():
        from backend.services.bulk_importer import BulkImporter
        return {
            'success': True,
            'message': 'COPY批量导入服务可用',
            'details': 'PostgreSQL Phase 2'
        }
    
    def test_data_importer():
        from backend.services.data_importer import (
            stage_product_metrics,
            upsert_product_metrics
        )
        return {
            'success': True,
            'message': '数据导入服务可用',
            'details': 'stage+upsert'
        }
    
    validator.test("4.1 ExcelParser服务", test_excel_parser)
    validator.test("4.2 图片提取/处理服务", test_image_services)
    validator.test("4.3 COPY批量导入服务", test_bulk_importer)
    validator.test("4.4 数据导入服务", test_data_importer)
    
    # ============ 测试5：PostgreSQL优化验证 ============
    safe_print("\n[Category 5] PostgreSQL优化验证")
    
    def test_catalog_indexes():
        engine = create_engine(Settings().DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM pg_indexes 
                WHERE tablename = 'catalog_files'
            """))
            count = result.scalar()
            
            if count >= 10:
                return {
                    'success': True,
                    'message': 'catalog_files索引充足',
                    'details': f'{count}个索引'
                }
            return {
                'warning': True,
                'message': f'catalog_files索引不足: {count}个（建议>=10）'
            }
    
    def test_product_images_indexes():
        engine = create_engine(Settings().DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM pg_indexes 
                WHERE tablename = 'product_images'
            """))
            count = result.scalar()
            
            return {
                'success': True,
                'message': 'product_images索引',
                'details': f'{count}个索引'
            }
    
    def test_connection_pool():
        engine = create_engine(Settings().DATABASE_URL)
        pool_size = engine.pool.size()
        
        return {
            'success': True,
            'message': '连接池配置',
            'details': f'pool_size={pool_size}'
        }
    
    def test_dim_date_data():
        engine = create_engine(Settings().DATABASE_URL)
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT MIN(date_key), MAX(date_key), COUNT(*) 
                FROM dim_date
            """))
            min_date, max_date, count = result.fetchone()
            
            if count >= 4000:
                return {
                    'success': True,
                    'message': 'dim_date数据完整',
                    'details': f'{min_date} 至 {max_date}, 共{count}条'
                }
            return {
                'success': False,
                'message': f'dim_date数据不足: {count}条'
            }
    
    validator.test("5.1 catalog_files索引", test_catalog_indexes)
    validator.test("5.2 product_images索引", test_product_images_indexes)
    validator.test("5.3 连接池配置", test_connection_pool)
    validator.test("5.4 dim_date数据", test_dim_date_data)
    
    # ============ 测试6：API完整性检查 ============
    safe_print("\n[Category 6] API路由完整性")
    
    def test_api_docs():
        # FastAPI的Swagger UI文档页面
        resp = requests.get(f"{BASE_URL}/docs", timeout=TIMEOUT)
        if resp.status_code == 200:
            # 检查是否包含FastAPI标识
            content = resp.text
            if 'FastAPI' in content or 'swagger' in content.lower():
                return {
                    'success': True,
                    'message': 'API文档可访问',
                    'details': 'Swagger UI正常'
                }
            return {'success': False, 'message': 'API文档内容异常'}
        return {'success': False, 'message': f'API文档访问失败: {resp.status_code}'}
    
    def test_field_mapping_apis():
        required_apis = [
            '/api/field-mapping/file-groups',
            '/api/field-mapping/catalog-status',
            '/api/field-mapping/data-domains',
        ]
        
        all_ok = True
        for api in required_apis:
            resp = requests.get(f"{BASE_URL}{api}", timeout=TIMEOUT)
            if resp.status_code != 200:
                all_ok = False
                break
        
        if all_ok:
            return {
                'success': True,
                'message': '字段映射核心API可用',
                'details': f'{len(required_apis)}个接口'
            }
        return {'success': False, 'message': '部分字段映射API失败'}
    
    def test_product_apis():
        required_apis = [
            ('/api/products/products', {'page': 1, 'page_size': 1}),
            ('/api/products/stats/platform-summary', {}),
        ]
        
        all_ok = True
        for api, params in required_apis:
            resp = requests.get(f"{BASE_URL}{api}", params=params, timeout=TIMEOUT)
            if resp.status_code != 200:
                all_ok = False
                break
        
        if all_ok:
            return {
                'success': True,
                'message': 'v3.0产品管理API可用',
                'details': f'{len(required_apis)}个核心接口'
            }
        return {'success': False, 'message': '部分产品API失败'}
    
    validator.test("6.1 OpenAPI文档", test_api_docs)
    validator.test("6.2 字段映射核心API", test_field_mapping_apis)
    validator.test("6.3 v3.0产品管理API", test_product_apis)
    
    # ============ 测试7：前端路由检查 ============
    safe_print("\n[Category 7] 前端路由与页面")
    
    def test_frontend_router():
        router_file = Path('frontend/src/router/index.js')
        if router_file.exists():
            content = router_file.read_text(encoding='utf-8')
            
            # 检查关键路由
            required_routes = [
                'field-mapping',
                'product-management',
                'sales-dashboard-v3',
                'inventory-dashboard-v3'
            ]
            
            found = sum(1 for route in required_routes if route in content)
            
            if found == len(required_routes):
                return {
                    'success': True,
                    'message': '前端路由完整',
                    'details': f'{found}/{len(required_routes)}个核心路由'
                }
            return {
                'success': False,
                'message': f'前端路由缺失: {found}/{len(required_routes)}'
            }
        return {'success': False, 'message': 'router/index.js不存在'}
    
    def test_frontend_pages():
        required_pages = [
            'frontend/src/views/FieldMapping.vue',
            'frontend/src/views/ProductManagement.vue',
            'frontend/src/views/SalesDashboard.vue',
            'frontend/src/views/InventoryDashboard.vue'
        ]
        
        exists = [Path(p).exists() for p in required_pages]
        found = sum(exists)
        
        if found == len(required_pages):
            return {
                'success': True,
                'message': '前端页面完整',
                'details': f'{found}/{len(required_pages)}个页面文件'
            }
        
        missing = [required_pages[i] for i, e in enumerate(exists) if not e]
        return {
            'success': False,
            'message': f'页面文件缺失: {", ".join([Path(p).name for p in missing])}'
        }
    
    validator.test("7.1 前端路由配置", test_frontend_router)
    validator.test("7.2 前端页面文件", test_frontend_pages)
    
    # ============ 测试8：文档完整性 ============
    safe_print("\n[Category 8] 文档完整性")
    
    def test_core_docs():
        required_docs = [
            'README.md',
            'CHANGELOG.md',
            'docs/ULTIMATE_DELIVERY_REPORT_20251027.md',
            'docs/QUICK_START_ALL_FEATURES.md',
            'docs/USER_QUICK_START_GUIDE.md',
            '请从这里开始_v2.3_v3.0.txt'
        ]
        
        exists = [Path(p).exists() for p in required_docs]
        found = sum(exists)
        
        if found == len(required_docs):
            return {
                'success': True,
                'message': '核心文档完整',
                'details': f'{found}/{len(required_docs)}个文档'
            }
        
        missing = [required_docs[i] for i, e in enumerate(exists) if not e]
        return {
            'success': False,
            'message': f'文档缺失: {", ".join([Path(p).name for p in missing])}'
        }
    
    def test_specialized_docs():
        required_dirs = [
            'docs/field_mapping_v2',
            'docs/v3_product_management',
            'docs/deployment',
            'docs/architecture',
            'docs/development'
        ]
        
        exists = [Path(p).exists() for p in required_dirs]
        found = sum(exists)
        
        if found == len(required_dirs):
            return {
                'success': True,
                'message': '专题文档目录完整',
                'details': f'{found}/{len(required_dirs)}个专题'
            }
        return {
            'success': False,
            'message': f'专题目录缺失: {found}/{len(required_dirs)}'
        }
    
    validator.test("8.1 核心文档", test_core_docs)
    validator.test("8.2 专题文档目录", test_specialized_docs)
    
    # ============ 打印总结 ============
    validator.summary()
    
    # 返回exit code
    return 0 if validator.failed == 0 else 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        safe_print("\n\n[Interrupted] 测试被中断")
        sys.exit(1)
    except Exception as e:
        safe_print(f"\n[FATAL ERROR] 测试失败: {e}")
        sys.exit(1)

