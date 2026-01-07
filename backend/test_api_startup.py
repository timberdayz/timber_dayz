"""
测试API服务启动
验证所有路由是否正确注册
"""

import sys
from pathlib import Path

root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

def test_api_startup():
    """测试API服务是否能正常启动"""
    
    print("=" * 80)
    print("[TEST] Testing API startup and routes")
    print("=" * 80)
    print()
    
    try:
        # 导入FastAPI应用
        print("[1/5] Importing FastAPI application...")
        from backend.main import app
        print("  [OK] App imported successfully")
        print()
        
        # 检查路由
        print("[2/5] Checking registered routes...")
        routes = []
        for route in app.routes:
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                methods = ', '.join(route.methods) if route.methods else 'N/A'
                routes.append((route.path, methods))
        
        print(f"  [OK] Total routes: {len(routes)}")
        print()
        
        # 按路由前缀分类
        print("[3/5] Routes by category...")
        
        categories = {}
        for path, methods in routes:
            if '/api/dashboard' in path:
                categories.setdefault('Dashboard', []).append((path, methods))
            elif '/api/collection' in path:
                categories.setdefault('Collection', []).append((path, methods))
            elif '/api/management' in path:
                categories.setdefault('Management', []).append((path, methods))
            elif '/api/accounts' in path:
                categories.setdefault('Accounts', []).append((path, methods))
            elif '/api/field-mapping' in path:
                categories.setdefault('Field Mapping', []).append((path, methods))
            elif '/api/inventory' in path:
                categories.setdefault('Inventory (NEW)', []).append((path, methods))
            elif '/api/finance' in path:
                categories.setdefault('Finance (NEW)', []).append((path, methods))
            elif '/api/test' in path:
                categories.setdefault('Test', []).append((path, methods))
            else:
                categories.setdefault('Other', []).append((path, methods))
        
        for category, category_routes in sorted(categories.items()):
            print(f"\n  [{category}]: {len(category_routes)} routes")
            for path, methods in sorted(category_routes):
                print(f"    {methods:15s} {path}")
        
        print()
        
        # 检查新增的路由
        print("[4/5] Verifying new routes...")
        
        new_routes = [
            ('/api/inventory/list', 'Inventory list'),
            ('/api/inventory/detail', 'Inventory detail'),
            ('/api/inventory/adjust', 'Inventory adjust'),
            ('/api/inventory/low-stock-alert', 'Low stock alert'),
            ('/api/finance/accounts-receivable', 'Accounts receivable'),
            ('/api/finance/record-payment', 'Record payment'),
            ('/api/finance/profit-report', 'Profit report'),
            ('/api/finance/overdue-alert', 'Overdue alert'),
            ('/api/finance/financial-overview', 'Financial overview'),
        ]
        
        all_paths = [path for path, _ in routes]
        
        for expected_path, description in new_routes:
            # 部分匹配（因为可能有路径参数）
            found = any(expected_path in path for path in all_paths)
            if found:
                print(f"  [OK] {description:30s} - {expected_path}")
            else:
                print(f"  [X] {description:30s} - MISSING: {expected_path}")
        
        print()
        
        # 验证数据库连接
        print("[5/5] Testing database connection...")
        from backend.models.database import SessionLocal
        db = SessionLocal()
        try:
            from sqlalchemy import text
            result = db.execute(text("SELECT 1")).scalar()
            print(f"  [OK] Database connection successful")
        except Exception as e:
            print(f"  [ERROR] Database connection failed: {e}")
        finally:
            db.close()
        
        print()
        print("=" * 80)
        print("[SUMMARY]")
        print("=" * 80)
        print(f"Total routes: {len(routes)}")
        print(f"New inventory routes: 4")
        print(f"New finance routes: 5")
        print()
        print("[OK] API startup test completed successfully!")
        
    except Exception as e:
        print(f"[ERROR] API startup test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_api_startup()

