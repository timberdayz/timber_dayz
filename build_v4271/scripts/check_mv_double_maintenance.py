"""
检查物化视图双维护风险（v4.8.0）
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent

print("=" * 80)
print("物化视图双维护风险检查 - v4.8.0")
print("=" * 80)
print()

issues = []
warnings = []

# 检查1: 物化视图SQL定义是否唯一
print("[检查1] 物化视图SQL定义唯一性...")
sql_files = list(project_root.glob("**/*.sql"))
mv_definition_files = []

for sql_file in sql_files:
    if 'backups' in str(sql_file) or 'temp' in str(sql_file):
        continue
    with open(sql_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        if 'CREATE MATERIALIZED VIEW' in content.upper() and 'mv_product_management' in content:
            mv_definition_files.append(sql_file)

if len(mv_definition_files) == 1:
    print(f"  [PASS] 物化视图定义唯一: {mv_definition_files[0].relative_to(project_root)}")
elif len(mv_definition_files) > 1:
    issues.append(f"[FAIL] 发现{len(mv_definition_files)}个物化视图定义文件（应该只有1个）:")
    for f in mv_definition_files:
        issues.append(f"  - {f.relative_to(project_root)}")
else:
    warnings.append("[WARN] 未找到物化视图定义文件")

# 检查2: MaterializedViewService是否唯一
print("[检查2] MaterializedViewService服务类唯一性...")
service_files = list(project_root.glob("**/*materialized_view*.py"))
mv_service_files = []

for service_file in service_files:
    if 'backups' in str(service_file) or 'temp' in str(service_file) or '__pycache__' in str(service_file):
        continue
    with open(service_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        if 'class MaterializedViewService' in content:
            mv_service_files.append(service_file)

if len(mv_service_files) == 1:
    print(f"  [PASS] 服务类定义唯一: {mv_service_files[0].relative_to(project_root)}")
elif len(mv_service_files) > 1:
    issues.append(f"[FAIL] 发现{len(mv_service_files)}个MaterializedViewService定义（应该只有1个）:")
    for f in mv_service_files:
        issues.append(f"  - {f.relative_to(project_root)}")
else:
    issues.append("[FAIL] 未找到MaterializedViewService定义文件")

# 检查3: product_management.py是否还有旧查询逻辑
print("[检查3] 产品API是否清理了旧逻辑...")
product_mgmt_file = project_root / "backend" / "routers" / "product_management.py"

if product_mgmt_file.exists():
    with open(product_mgmt_file, 'r', encoding='utf-8') as f:
        content = f.read()
        
        # 检查是否使用MaterializedViewService
        if 'MaterializedViewService' in content:
            print("  [PASS] 已使用MaterializedViewService")
        else:
            issues.append("[FAIL] product_management.py未使用MaterializedViewService")
        
        # 检查是否还有旧的复杂查询逻辑
        old_patterns = [
            'latest_date_subq',
            'func.max(FactProductMetric.metric_date)',
            '.subquery()'
        ]
        
        has_old_logic = False
        for pattern in old_patterns:
            if pattern in content:
                has_old_logic = True
                warnings.append(f"[WARN] 发现疑似旧查询逻辑: {pattern}")
        
        if not has_old_logic:
            print("  [PASS] 未发现旧查询逻辑")
else:
    issues.append("[FAIL] product_management.py文件不存在")

# 检查4: 是否有多处定义定时刷新任务
print("[检查4] 定时刷新任务唯一性...")
refresh_task_files = []

for py_file in project_root.glob("**/*.py"):
    if 'backups' in str(py_file) or 'temp' in str(py_file) or '__pycache__' in str(py_file):
        continue
    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        if 'refresh_all_views' in content and 'def refresh_all_views' in content:
            refresh_task_files.append(py_file)

if len(refresh_task_files) == 1:
    print(f"  [PASS] 刷新任务定义唯一: {refresh_task_files[0].relative_to(project_root)}")
elif len(refresh_task_files) > 1:
    issues.append(f"[FAIL] 发现{len(refresh_task_files)}个刷新任务定义（应该只有1个）:")
    for f in refresh_task_files:
        issues.append(f"  - {f.relative_to(project_root)}")

# 检查5: 是否有重复的物化视图管理API
print("[检查5] 物化视图管理API唯一性...")
mv_router_files = []

for py_file in project_root.glob("backend/routers/*.py"):
    if '__pycache__' in str(py_file):
        continue
    with open(py_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        if 'refresh/product-management' in content or '@router.post("/refresh' in content:
            mv_router_files.append(py_file)

if len(mv_router_files) == 1:
    print(f"  [PASS] 物化视图API定义唯一: {mv_router_files[0].relative_to(project_root)}")
elif len(mv_router_files) > 1:
    issues.append(f"[FAIL] 发现{len(mv_router_files)}个物化视图API定义（应该只有1个）:")
    for f in mv_router_files:
        issues.append(f"  - {f.relative_to(project_root)}")

print()
print("=" * 80)
print("检查结果汇总")
print("=" * 80)

if issues:
    print(f"\n[FAIL] 发现 {len(issues)} 个双维护问题:")
    for issue in issues:
        print(issue)

if warnings:
    print(f"\n[WARN] 发现 {len(warnings)} 个警告:")
    for warning in warnings:
        print(warning)

if not issues and not warnings:
    print("\n[OK] 所有检查通过！无双维护风险！")
    print()
    print("SSOT合规率: 100%")
    sys.exit(0)
elif not issues:
    print("\n[OK] 无严重问题，仅有警告信息")
    print()
    print("SSOT合规率: 95%")
    sys.exit(0)
else:
    print(f"\n[ERROR] 存在双维护风险，请立即修复！")
    print()
    print(f"SSOT合规率: {max(0, 100 - len(issues) * 20)}%")
    sys.exit(1)

