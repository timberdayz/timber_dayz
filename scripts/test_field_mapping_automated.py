#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字段映射系统自动化测试 - 企业级ERP标准
覆盖：字典API、智能映射、数据入库
"""

import sys
import time
import requests
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def safe_print(text):
    """安全打印（Windows编码兼容）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

class FieldMappingTests:
    """字段映射自动化测试套件"""
    
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.passed = 0
        self.failed = 0
        self.warnings = 0
    
    def test_dictionary_api(self):
        """测试1: 字典API加载"""
        safe_print("\n[Test 1] Dictionary API Loading")
        safe_print("-" * 60)
        
        domains = ['services', 'orders', 'products', 'traffic', 'finance']
        results = {}
        
        for domain in domains:
            try:
                url = f"{self.base_url}/api/field-mapping/dictionary?data_domain={domain}"
                response = requests.get(url, timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    count = data.get('total', 0)
                    results[domain] = count
                    
                    if count > 0:
                        safe_print(f"  [PASS] {domain:12} -> {count:2} fields")
                        self.passed += 1
                    else:
                        safe_print(f"  [WARN] {domain:12} -> 0 fields (empty dictionary)")
                        self.warnings += 1
                else:
                    safe_print(f"  [FAIL] {domain:12} -> HTTP {response.status_code}")
                    self.failed += 1
                    results[domain] = 0
                    
            except Exception as e:
                safe_print(f"  [FAIL] {domain:12} -> {str(e)[:50]}")
                self.failed += 1
                results[domain] = 0
        
        total_fields = sum(results.values())
        safe_print(f"\n  Total fields loaded: {total_fields}")
        
        return results
    
    def test_file_groups_api(self):
        """测试2: 文件分组API"""
        safe_print("\n[Test 2] File Groups API")
        safe_print("-" * 60)
        
        try:
            url = f"{self.base_url}/api/field-mapping/file-groups"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                groups = data.get('file_groups', [])
                total_files = data.get('total_files', 0)
                
                safe_print(f"  [PASS] Loaded {len(groups)} file groups, {total_files} files")
                self.passed += 1
                return len(groups) > 0
            else:
                safe_print(f"  [FAIL] HTTP {response.status_code}")
                self.failed += 1
                return False
                
        except Exception as e:
            safe_print(f"  [FAIL] {str(e)[:50]}")
            self.failed += 1
            return False
    
    def test_health_check(self):
        """测试3: 健康检查"""
        safe_print("\n[Test 3] Backend Health Check")
        safe_print("-" * 60)
        
        try:
            url = f"{self.base_url}/health"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                status = data.get('status', '')
                
                if status == 'healthy':
                    safe_print(f"  [PASS] Backend is healthy")
                    safe_print(f"    Database: {data.get('database', 'unknown')}")
                    safe_print(f"    Version: {data.get('version', 'unknown')}")
                    self.passed += 1
                    return True
                else:
                    safe_print(f"  [WARN] Backend status: {status}")
                    self.warnings += 1
                    return False
            else:
                safe_print(f"  [FAIL] HTTP {response.status_code}")
                self.failed += 1
                return False
                
        except Exception as e:
            safe_print(f"  [FAIL] {str(e)[:50]}")
            self.failed += 1
            return False
    
    def test_database_consistency(self):
        """测试4: 数据库一致性"""
        safe_print("\n[Test 4] Database Consistency")
        safe_print("-" * 60)
        
        from sqlalchemy import create_engine, text
        from backend.utils.config import get_settings
        
        settings = get_settings()
        engine = create_engine(settings.DATABASE_URL)
        
        try:
            with engine.connect() as conn:
                # 检查字典表
                result = conn.execute(text("""
                    SELECT data_domain, COUNT(*) as cnt
                    FROM field_mapping_dictionary
                    WHERE active = true
                    GROUP BY data_domain
                    ORDER BY data_domain
                """))
                
                db_counts = dict(result.fetchall())
                total_db = sum(db_counts.values())
                
                safe_print(f"  Database has {total_db} active fields:")
                for domain, count in db_counts.items():
                    safe_print(f"    {domain:12} -> {count:2} fields")
                
                self.passed += 1
                return db_counts
                
        except Exception as e:
            safe_print(f"  [FAIL] {str(e)[:50]}")
            self.failed += 1
            return {}
    
    def test_api_db_consistency(self, api_results, db_results):
        """测试5: API与数据库一致性"""
        safe_print("\n[Test 5] API-Database Consistency")
        safe_print("-" * 60)
        
        api_total = sum(api_results.values())
        db_total = sum(db_results.values())
        
        if api_total == db_total:
            safe_print(f"  [PASS] API and DB are consistent: {api_total} fields")
            self.passed += 1
            return True
        else:
            safe_print(f"  [FAIL] Inconsistency detected:")
            safe_print(f"    API total: {api_total}")
            safe_print(f"    DB total: {db_total}")
            safe_print(f"    Difference: {abs(api_total - db_total)}")
            
            for domain in set(api_results.keys()) | set(db_results.keys()):
                api_count = api_results.get(domain, 0)
                db_count = db_results.get(domain, 0)
                if api_count != db_count:
                    safe_print(f"    {domain:12}: API={api_count}, DB={db_count}")
            
            self.failed += 1
            return False
    
    def run_all_tests(self):
        """运行所有测试"""
        safe_print("\n" + "="*80)
        safe_print("Field Mapping System - Automated Test Suite")
        safe_print("Enterprise ERP Standard")
        safe_print("="*80)
        safe_print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Test 1: Dictionary API
        api_results = self.test_dictionary_api()
        
        # Test 2: File Groups API
        self.test_file_groups_api()
        
        # Test 3: Health Check
        self.test_health_check()
        
        # Test 4: Database Consistency
        db_results = self.test_database_consistency()
        
        # Test 5: API-DB Consistency
        if api_results and db_results:
            self.test_api_db_consistency(api_results, db_results)
        
        # Final Report
        safe_print("\n" + "="*80)
        safe_print("Test Results Summary")
        safe_print("="*80)
        safe_print(f"  PASSED:   {self.passed}")
        safe_print(f"  FAILED:   {self.failed}")
        safe_print(f"  WARNINGS: {self.warnings}")
        safe_print(f"  TOTAL:    {self.passed + self.failed + self.warnings}")
        
        success_rate = self.passed / (self.passed + self.failed) * 100 if (self.passed + self.failed) > 0 else 0
        safe_print(f"\n  Success Rate: {success_rate:.1f}%")
        
        safe_print(f"\n  End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        safe_print("="*80)
        
        if self.failed == 0:
            safe_print("\n[OK] All tests passed! System is ready for production.")
            return 0
        else:
            safe_print(f"\n[ERROR] {self.failed} test(s) failed. Please review and fix.")
            return 1

def main():
    """主函数"""
    tests = FieldMappingTests()
    exit_code = tests.run_all_tests()
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()

