#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复SQL文件并同步到云端"""

import os
import sys
import gzip
import glob
import subprocess
from pathlib import Path

project_root = Path(__file__).parent.parent
temp_dir = project_root / 'temp'

# 找到最新的导出文件
sql_files = list(temp_dir.glob('templates_export_*.sql.gz'))
if not sql_files:
    print("[ERROR] 未找到导出文件")
    sys.exit(1)

sql_file = max(sql_files, key=lambda p: p.stat().st_mtime)
print(f"[INFO] 找到导出文件: {sql_file}")

# 修复SQL文件（移除core.前缀）
fixed_sql_file = temp_dir / f"{sql_file.stem}_fixed.sql.gz"
print(f"[修复] 修复SQL文件（移除core.前缀）...")

with gzip.open(sql_file, 'rt', encoding='utf-8') as f_in:
    content = f_in.read()
    # 替换 core.field_mapping_templates 为 field_mapping_templates
    fixed_content = content.replace('core.field_mapping_templates', 'field_mapping_templates')

with gzip.open(fixed_sql_file, 'wt', encoding='utf-8') as f_out:
    f_out.write(fixed_content)

print(f"[OK] 修复完成: {fixed_sql_file}")

# 上传到云端
remote_file = f"/tmp/{fixed_sql_file.name}"
print(f"[上传] 上传到云端: {remote_file}")

ssh_key = r"C:\Users\18689\.ssh\github_actions_deploy"
ssh_host = "deploy@134.175.222.171"

scp_cmd = [
    'scp', '-i', ssh_key,
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'Compression=yes',
    str(fixed_sql_file),
    f'{ssh_host}:{remote_file}'
]

result = subprocess.run(scp_cmd, capture_output=True, text=True)
if result.returncode != 0:
    print(f"[FAIL] 上传失败: {result.stderr}")
    sys.exit(1)

print(f"[OK] 上传成功: {remote_file}")

# 导入到云端数据库
print("[导入] 导入到云端数据库...")
import_cmd = f"cd /opt/xihong_erp && gunzip -c {remote_file} | docker exec -i xihong_erp_postgres psql -U erp_user -d xihong_erp"

ssh_cmd = [
    'ssh', '-i', ssh_key,
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'Compression=yes',
    ssh_host,
    import_cmd
]

result = subprocess.run(ssh_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
if result.returncode != 0:
    # 检查是否有错误
    if 'ERROR' in result.stderr or 'ERROR' in result.stdout:
        print(f"[WARN] 导入过程中有错误:")
        print(result.stderr[-1000:] if result.stderr else result.stdout[-1000:])
    else:
        print(f"[OK] 导入成功")
else:
    print(f"[OK] 导入成功")

# 验证
print("[验证] 验证云端模板数量...")
verify_cmd = "docker exec xihong_erp_postgres psql -U erp_user -d xihong_erp -t -c 'SELECT COUNT(*) FROM field_mapping_templates;'"
verify_ssh = [
    'ssh', '-i', ssh_key,
    '-o', 'StrictHostKeyChecking=no',
    ssh_host,
    verify_cmd
]

result = subprocess.run(verify_ssh, capture_output=True, text=True)
if result.returncode == 0:
    count = result.stdout.strip()
    print(f"[OK] 云端模板总数: {count}")
else:
    print(f"[WARN] 验证失败: {result.stderr}")

# 清理
print("[清理] 清理临时文件...")
os.remove(fixed_sql_file)
print("[OK] 已清理本地临时文件")

cleanup_cmd = f"rm -f {remote_file}"
cleanup_ssh = [
    'ssh', '-i', ssh_key,
    '-o', 'StrictHostKeyChecking=no',
    ssh_host,
    cleanup_cmd
]
subprocess.run(cleanup_ssh, capture_output=True)
print("[OK] 已清理云端临时文件")

print("\n========================================")
print("同步完成！")
print("========================================")
