#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
西虹ERP - 纯本机启动脚本（不启动 Docker）

注意：大多数情况下推荐使用 `python run.py --local`，它会自动用 Docker 拉起
Postgres/Redis/Celery，再本机起后端+前端——无需配置本机数据库。

本脚本仅适用于已在本机安装并配好 PostgreSQL 的场景（如离线开发或不方便用 Docker 时）。
不解析 --use-docker/--collection，不启动 Metabase。

配置要求：
- .env 中 DATABASE_URL 指向的 PostgreSQL 必须先可连接（端口、用户、库名、密码正确）。
- 本机 PostgreSQL 通常在 5432 端口，需在 .env 中设置
  POSTGRES_PORT=5432 且 DATABASE_URL 相应修改，并在本机创建用户 erp_user、数据库 xihong_erp。

启动前可先检查环境：
    python scripts/check_local_run_env.py

用法:
    python local_run.py          # 启动本机后端 + 前端，Redis 可用时询问是否启动 Celery
"""

import os
import subprocess
import sys
import time
from pathlib import Path
import platform as sys_platform

_project_root = Path(__file__).resolve().parent
_env_file = _project_root / ".env"

# 使用 UTF-8 加载 .env，避免 Windows 下编码问题
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        try:
            load_dotenv(_env_file, encoding="utf-8")
        except TypeError:
            load_dotenv(_env_file)
    except ImportError:
        pass


def safe_print(text):
    """安全打印（处理 Windows GBK 编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode("gbk", errors="ignore").decode("gbk")
            print(safe_text, flush=True)
        except Exception:
            safe_text = text.encode("ascii", errors="ignore").decode("ascii")
            print(safe_text, flush=True)


def check_redis():
    """检查 Redis 是否可用（Celery 需要）。返回 True/False。"""
    safe_print("\n[检查] Redis 服务状态...")
    try:
        import redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        if "@" not in redis_url.split("://")[1] and os.getenv("REDIS_PASSWORD"):
            from urllib.parse import urlparse
            parsed = urlparse(redis_url)
            pwd = os.getenv("REDIS_PASSWORD")
            redis_url = f"redis://:{pwd}@{parsed.hostname}:{parsed.port or 6379}{parsed.path}"
        r = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        r.ping()
        r.close()
        safe_print("  [OK] Redis 服务正常")
        return True
    except Exception:
        safe_print("  [WARNING] Redis 不可用，将跳过 Celery Worker")
        safe_print("  提示: 启动 Redis 后可再次运行并选择启动 Celery")
        return False


def start_backend():
    """启动本机后端（uvicorn）"""
    safe_print("\n[启动] 后端服务...")
    safe_print("  地址: http://localhost:8001  文档: http://localhost:8001/api/docs")
    backend_dir = _project_root / "backend"
    if sys_platform.system() == "Windows":
        work_dir = str(_project_root.resolve())
        work_dir_ps = work_dir.replace("'", "''")
        inner = "`$env:PYTHONPATH='{}'; python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 --loop asyncio".format(work_dir_ps)
        cmd = 'Start-Process powershell -ArgumentList "-NoExit", "-Command", "{}" -WorkingDirectory "{}"'.format(
            inner.replace('"', '`"'), work_dir.replace('"', '`"')
        )
        subprocess.Popen(["powershell", "-Command", cmd], shell=True, cwd=_project_root)
        safe_print("  [OK] 后端已在新窗口启动")
    else:
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"],
            cwd=_project_root,
        )
        safe_print("  [OK] 后端已启动")
    return None


def start_frontend():
    """启动本机前端（npm run dev）"""
    safe_print("\n[启动] 前端服务...")
    safe_print("  地址: http://localhost:5173")
    frontend_dir = _project_root / "frontend"
    if sys_platform.system() == "Windows":
        fp = str(frontend_dir.resolve())
        cmd = 'Start-Process powershell -ArgumentList "-NoExit", "-Command", "npm run dev" -WorkingDirectory "{}"'.format(
            fp.replace('"', '`"')
        )
        subprocess.Popen(["powershell", "-Command", cmd], shell=True, cwd=_project_root)
        safe_print("  [OK] 前端已在新窗口启动")
    else:
        subprocess.Popen(["npm", "run", "dev"], cwd=frontend_dir)
        safe_print("  [OK] 前端已启动")
    return None


def start_celery_worker():
    """启动本机 Celery Worker"""
    safe_print("\n[启动] Celery Worker...")
    work_dir = str(_project_root.resolve())
    if sys_platform.system() == "Windows":
        work_dir_ps = work_dir.replace("'", "''")
        celery_cmd = "`$env:PYTHONPATH='{}'; python -m celery -A backend.celery_app worker --loglevel=info --queues=data_sync,scheduled,data_processing --pool=solo --concurrency=4".format(work_dir_ps)
        cmd = 'Start-Process powershell -ArgumentList "-NoExit", "-Command", "{}" -WorkingDirectory "{}"'.format(
            celery_cmd.replace('"', '`"'), work_dir.replace('"', '`"')
        )
        subprocess.Popen(["powershell", "-Command", cmd], shell=True, cwd=_project_root)
        safe_print("  [OK] Celery 已在新窗口启动")
    else:
        subprocess.Popen(
            [sys.executable, "-m", "celery", "-A", "backend.celery_app", "worker",
             "--loglevel=info", "--queues=data_sync,scheduled,data_processing", "--concurrency=4"],
            cwd=_project_root,
        )
        safe_print("  [OK] Celery 已启动")
    return None


def wait_for_service(port, name, timeout_sec=20):
    """等待端口就绪"""
    import socket
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            if result == 0:
                return True
        except Exception:
            pass
        time.sleep(1)
    safe_print(f"  [WARNING] {name} 启动超时")
    return False


def main():
    safe_print("\n" + "=" * 60)
    safe_print("西虹ERP - 纯本机启动（local_run.py）")
    safe_print("=" * 60)
    safe_print("提示: 若不想配本机数据库，推荐使用 python run.py --local")
    safe_print("请确保本机 PostgreSQL 已运行且 .env 中 DATABASE_URL 可连")
    redis_ok = check_redis()
    start_celery = False
    if redis_ok:
        choice = input("\n是否启动 Celery Worker? (y/n，默认 n): ").strip().lower()
        start_celery = choice == "y"

    start_backend()
    time.sleep(2)
    if wait_for_service(8001, "后端API", 20):
        safe_print("  [OK] 后端 API 就绪")
    else:
        safe_print("  [WARNING] 请查看后端窗口日志")

    if start_celery:
        start_celery_worker()
        time.sleep(3)

    start_frontend()
    if wait_for_service(5173, "前端", 15):
        safe_print("  [OK] 前端就绪")

    safe_print("\n" + "=" * 60)
    safe_print("[成功] 本机服务已启动")
    safe_print("  后端: http://localhost:8001/api/docs  前端: http://localhost:5173")
    safe_print("  关闭各窗口即可停止服务；按 Ctrl+C 退出本脚本")
    safe_print("=" * 60)

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        safe_print("\n[退出] 监控已退出，后端/前端/Celery 仍在各自窗口运行")


if __name__ == "__main__":
    main()
