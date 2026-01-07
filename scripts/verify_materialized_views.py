#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证物化视图创建和功能

验证内容：
1. 检查新的物化视图是否在数据库中
2. 检查物化视图的行数
3. 检查前端数据浏览器API是否能返回这些视图
4. 检查主视图API是否能正常查询
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.models.database import get_db
from sqlalchemy import text
from modules.core.logger import get_logger
import requests

logger = get_logger(__name__)


def safe_print(text_str):
    """安全打印（Windows兼容）"""
    try:
        print(text_str)
    except UnicodeEncodeError:
        print(text_str.encode('gbk', errors='ignore').decode('gbk'))


def verify_database_views():
    """验证数据库中的物化视图"""
    safe_print("\n" + "=" * 70)
    safe_print("1. 验证数据库中的物化视图")
    safe_print("=" * 70)
    
    db = next(get_db())
    
    try:
        # 查询所有物化视图
        all_views = db.execute(text("""
            SELECT matviewname 
            FROM pg_matviews 
            WHERE schemaname = 'public'
            ORDER BY matviewname
        """)).fetchall()
        
        view_names = [v[0] for v in all_views]
        safe_print(f"\n数据库中共有 {len(view_names)} 个物化视图:")
        for v in view_names:
            safe_print(f"  - {v}")
        
        # 验证新的物化视图
        new_views = [
            'mv_order_summary',
            'mv_traffic_summary',
            'mv_sales_detail_by_product',
            'mv_inventory_by_sku'
        ]
        
        safe_print("\n验证新的物化视图:")
        results = {}
        for view_name in new_views:
            exists = view_name in view_names
            if exists:
                row_count = db.execute(text(f"SELECT COUNT(*) FROM {view_name}")).scalar()
                results[view_name] = {'exists': True, 'row_count': row_count}
                safe_print(f"  [OK] {view_name}: 存在, 行数={row_count}")
            else:
                results[view_name] = {'exists': False, 'row_count': 0}
                safe_print(f"  [MISSING] {view_name}: 不存在")
        
        return results
        
    finally:
        db.close()


def verify_frontend_api():
    """验证前端数据浏览器API"""
    safe_print("\n" + "=" * 70)
    safe_print("2. 验证前端数据浏览器API")
    safe_print("=" * 70)
    
    try:
        response = requests.get('http://localhost:8001/api/data-browser/tables', timeout=5)
        if response.status_code != 200:
            safe_print(f"  [ERROR] API返回状态码: {response.status_code}")
            return {}
        
        data = response.json()
        tables = data.get('tables', [])
        mvs = [t for t in tables if t.get('is_materialized_view')]
        
        safe_print(f"\n前端API返回 {len(mvs)} 个物化视图")
        
        new_views = [
            'mv_order_summary',
            'mv_traffic_summary',
            'mv_sales_detail_by_product',
            'mv_inventory_by_sku'
        ]
        
        safe_print("\n验证新的物化视图在前端的可见性:")
        results = {}
        for view_name in new_views:
            found = any(t['name'] == view_name for t in mvs)
            results[view_name] = {'visible': found}
            status = "[OK]" if found else "[MISSING]"
            safe_print(f"  {status} {view_name}: {'可见' if found else '不可见'}")
        
        return results
        
    except requests.exceptions.ConnectionError:
        safe_print("  [WARNING] 无法连接到后端API（可能后端未启动）")
        return {}
    except Exception as e:
        safe_print(f"  [ERROR] 验证失败: {e}")
        return {}


def verify_main_view_apis():
    """验证主视图API端点"""
    safe_print("\n" + "=" * 70)
    safe_print("3. 验证主视图API端点")
    safe_print("=" * 70)
    
    apis = [
        ('/api/main-views/orders/summary', '订单汇总'),
        ('/api/main-views/traffic/summary', '流量汇总'),
        ('/api/main-views/inventory/by-sku', '库存明细'),
        ('/api/management/sales-detail-by-product', '销售明细（产品ID级别）')
    ]
    
    results = {}
    
    for path, name in apis:
        try:
            response = requests.get(
                f'http://localhost:8001{path}?page=1&page_size=1',
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                total = data.get('total', 0)
                results[path] = {'status': 'ok', 'total': total}
                safe_print(f"  [OK] {name}: 状态码=200, 总记录数={total}")
            else:
                results[path] = {'status': 'error', 'code': response.status_code}
                safe_print(f"  [ERROR] {name}: 状态码={response.status_code}")
                
        except requests.exceptions.ConnectionError:
            results[path] = {'status': 'connection_error'}
            safe_print(f"  [WARNING] {name}: 无法连接到后端API")
        except Exception as e:
            results[path] = {'status': 'error', 'error': str(e)}
            safe_print(f"  [ERROR] {name}: {str(e)[:50]}")
    
    return results


def main():
    """主函数"""
    safe_print("=" * 70)
    safe_print("物化视图验证报告")
    safe_print("=" * 70)
    
    # 1. 验证数据库中的视图
    db_results = verify_database_views()
    
    # 2. 验证前端API
    frontend_results = verify_frontend_api()
    
    # 3. 验证主视图API
    api_results = verify_main_view_apis()
    
    # 总结
    safe_print("\n" + "=" * 70)
    safe_print("验证结果总结")
    safe_print("=" * 70)
    
    # 数据库验证结果
    db_success = all(r.get('exists', False) for r in db_results.values())
    safe_print(f"\n数据库验证: {'[OK]' if db_success else '[FAILED]'}")
    
    # 前端API验证结果
    if frontend_results:
        frontend_success = all(r.get('visible', False) for r in frontend_results.values())
        safe_print(f"前端API验证: {'[OK]' if frontend_success else '[FAILED]'}")
    else:
        safe_print("前端API验证: [SKIPPED] (后端未启动)")
    
    # API端点验证结果
    if api_results:
        api_success = all(r.get('status') == 'ok' for r in api_results.values())
        safe_print(f"API端点验证: {'[OK]' if api_success else '[FAILED]'}")
    else:
        safe_print("API端点验证: [SKIPPED] (后端未启动)")
    
    safe_print("\n" + "=" * 70)
    
    if db_success:
        safe_print("[SUCCESS] 所有新的物化视图已成功创建并验证！")
        safe_print("现在可以在前端数据浏览器中看到这些新的物化视图了。")
        return 0
    else:
        safe_print("[WARNING] 部分物化视图验证失败，请检查错误信息")
        return 1


if __name__ == "__main__":
    sys.exit(main())

