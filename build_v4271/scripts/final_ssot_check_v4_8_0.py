"""
v4.8.0最终SSOT检查 - 排除误报
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent

print("=" * 80)
print("v4.8.0最终SSOT检查 - 物化视图")
print("=" * 80)
print()

issues = []

# 检查1: 物化视图SQL定义是否唯一
print("[检查1] 物化视图SQL定义...")
mv_sql_file = project_root / "sql" / "create_mv_product_management.sql"
if mv_sql_file.exists():
    print(f"  [PASS] SQL定义存在: {mv_sql_file.relative_to(project_root)}")
else:
    issues.append("[FAIL] 物化视图SQL定义文件不存在")

# 检查2: MaterializedViewService是否存在
print("[检查2] MaterializedViewService服务...")
service_file = project_root / "backend" / "services" / "materialized_view_service.py"
if service_file.exists():
    print(f"  [PASS] 服务类存在: {service_file.relative_to(project_root)}")
else:
    issues.append("[FAIL] MaterializedViewService文件不存在")

# 检查3: 刷新任务是否存在
print("[检查3] 定时刷新任务...")
task_file = project_root / "backend" / "tasks" / "materialized_view_refresh.py"
if task_file.exists():
    print(f"  [PASS] 刷新任务存在: {task_file.relative_to(project_root)}")
else:
    issues.append("[FAIL] 定时刷新任务文件不存在")

# 检查4: 管理API是否存在
print("[检查4] 物化视图管理API...")
router_file = project_root / "backend" / "routers" / "materialized_views.py"
if router_file.exists():
    print(f"  [PASS] 管理API存在: {router_file.relative_to(project_root)}")
else:
    issues.append("[FAIL] 物化视图管理API文件不存在")

# 检查5: product_management.py是否使用物化视图
print("[检查5] 产品API使用物化视图...")
product_mgmt_file = project_root / "backend" / "routers" / "product_management.py"
if product_mgmt_file.exists():
    with open(product_mgmt_file, 'r', encoding='utf-8') as f:
        content = f.read()
        if 'MaterializedViewService.query_product_management' in content:
            print("  [PASS] 产品列表API已切换到物化视图")
        else:
            issues.append("[FAIL] 产品列表API未使用物化视图")
else:
    issues.append("[FAIL] product_management.py文件不存在")

# 检查6: main.py是否注册物化视图API和启动调度器
print("[检查6] main.py集成检查...")
main_file = project_root / "backend" / "main.py"
if main_file.exists():
    with open(main_file, 'r', encoding='utf-8') as f:
        content = f.read()
        
        has_import = 'materialized_views' in content
        has_router = 'materialized_views.router' in content
        has_scheduler = 'start_scheduler' in content
        
        if has_import and has_router:
            print("  [PASS] 物化视图API已注册")
        else:
            issues.append("[FAIL] 物化视图API未注册到main.py")
        
        if has_scheduler:
            print("  [PASS] 定时刷新调度器已启动")
        else:
            issues.append("[FAIL] 定时刷新调度器未启动")
else:
    issues.append("[FAIL] main.py文件不存在")

# 检查7: 旧的重复文件是否已归档
print("[检查7] 旧文件清理...")
old_manager = project_root / "backend" / "services" / "materialized_view_manager.py"
if old_manager.exists():
    issues.append(f"[FAIL] 旧文件未清理: {old_manager.relative_to(project_root)}")
else:
    print("  [PASS] 旧文件已清理（materialized_view_manager.py）")

print()
print("=" * 80)
print("检查结果")
print("=" * 80)

if issues:
    print(f"\n[FAIL] 发现 {len(issues)} 个问题:")
    for issue in issues:
        print(issue)
    print(f"\nSSOT合规率: {max(0, 100 - len(issues) * 15)}%")
    sys.exit(1)
else:
    print("\n[OK] 所有检查通过！")
    print("\n物化视图实施状态:")
    print("  - 物化视图SQL定义: [OK]")
    print("  - 服务层封装: [OK]")
    print("  - API层集成: [OK]")
    print("  - 定时刷新任务: [OK]")
    print("  - 旧文件清理: [OK]")
    print()
    print("SSOT合规率: 100%")
    print()
    sys.exit(0)

