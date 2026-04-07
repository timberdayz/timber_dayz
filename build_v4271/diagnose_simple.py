"""
简化启动诊断 - Windows GBK兼容版
"""

import subprocess
import sys
from pathlib import Path
import socket

def check_port(port):
    """检查端口是否开放"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        result = sock.connect_ex(('127.0.0.1', port))
        return result == 0
    finally:
        sock.close()

print("\n" + "="*60)
print("  System Diagnosis - XiHong ERP v4.1.0")
print("="*60)

# 1. Check Docker/PostgreSQL
print("\n[1/5] Checking Docker PostgreSQL...")
try:
    result = subprocess.run(
        ["docker", "ps", "--filter", "name=postgres"],
        capture_output=True,
        text=True,
        timeout=5,
        encoding='utf-8',
        errors='ignore'
    )
    
    if "xihong_erp_postgres" in result.stdout and "healthy" in result.stdout:
        print("  [OK] PostgreSQL container is running and healthy")
        docker_ok = True
    else:
        print("  [ERROR] PostgreSQL container not running")
        print("  Fix: docker-compose up -d postgres")
        docker_ok = False
except Exception as e:
    print(f"  [ERROR] Docker check failed: {e}")
    docker_ok = False

# 2. Check Python dependencies
print("\n[2/5] Checking Python dependencies...")
try:
    import fastapi
    import uvicorn
    import sqlalchemy
    print("  [OK] Required Python packages installed")
    python_ok = True
except ImportError as e:
    print(f"  [ERROR] Missing packages: {e}")
    print("  Fix: pip install -r requirements.txt")
    python_ok = False

# 3. Check database connection
print("\n[3/5] Checking database connection...")
if docker_ok and python_ok:
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from backend.models.database import engine
        from sqlalchemy import text
        
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        print("  [OK] Database connection successful")
        db_ok = True
    except Exception as e:
        print(f"  [ERROR] Database connection failed: {e}")
        db_ok = False
else:
    print("  [SKIP] Prerequisites not met")
    db_ok = False

# 4. Check backend code
print("\n[4/5] Checking backend code...")
if python_ok:
    try:
        import backend.main
        print("  [OK] backend.main imports successfully")
        code_ok = True
    except Exception as e:
        print(f"  [ERROR] backend.main import failed:")
        print(f"  {e}")
        code_ok = False
else:
    print("  [SKIP] Prerequisites not met")
    code_ok = False

# 5. Check ports
print("\n[5/5] Checking service ports...")
port_5432 = check_port(5432)
port_8001 = check_port(8001)
port_5173 = check_port(5173)

print(f"  Port 5432 (PostgreSQL): {'OPEN' if port_5432 else 'CLOSED'}")
print(f"  Port 8001 (Backend API): {'OPEN' if port_8001 else 'CLOSED'}")
print(f"  Port 5173 (Frontend):    {'OPEN' if port_5173 else 'CLOSED'}")

# Summary
print("\n" + "="*60)
print("  Summary")
print("="*60)

all_checks = {
    "Docker/PostgreSQL": docker_ok,
    "Python Dependencies": python_ok,
    "Database Connection": db_ok,
    "Backend Code": code_ok,
    "Backend Running": port_8001
}

for name, status in all_checks.items():
    symbol = "[OK]" if status else "[ERROR]"
    print(f"  {symbol} {name}")

passed = sum(1 for v in all_checks.values() if v)
total = len(all_checks)

print(f"\n  Result: {passed}/{total} checks passed")

# Recommendations
print("\n" + "="*60)
print("  Recommendations")
print("="*60)

if not port_8001 and docker_ok and python_ok and db_ok and code_ok:
    print("\n  All prerequisites OK but backend not running.")
    print("  Manual start to see detailed error:")
    print("    cd backend")
    print("    python -m uvicorn main:app --host 0.0.0.0 --port 8001")
elif not all([docker_ok, python_ok, db_ok, code_ok]):
    print("\n  Please fix the errors above first.")
else:
    print("\n  System is ready! Run: python run.py")

print("\n" + "="*60 + "\n")

sys.exit(0 if all(all_checks.values()) else 1)



