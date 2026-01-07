#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
西虹ERP系统 - 统一启动脚本 (v4.19.7)

版本历史:
- v4.19.7: 改进Docker健康检查等待逻辑，添加数据库连接预检查，主动检测启动错误
- v4.19.6: 添加Celery worker自动启动功能 + Docker Compose模式支持
- v4.18.0: 统一使用相对路径，提升云端迁移兼容性
- v4.1.1: 改进Windows下的进程启动方式

使用方法:
    python run.py                      # 传统模式（本地启动）
    python run.py --use-docker         # Docker Compose模式（推荐，统一管理）
    python run.py --backend-only       # 仅启动后端
    python run.py --frontend-only      # 仅启动前端
    python run.py --no-celery          # 不启动Celery worker
"""

import subprocess
import sys
import time
import webbrowser
import argparse
from pathlib import Path
import platform as sys_platform
import os

def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))

def print_banner():
    """打印系统横幅"""
    safe_print("\n" + "="*80)
    safe_print("西虹ERP系统 v4.19.7")
    safe_print("="*80)
    safe_print("现代化跨境电商管理平台")
    safe_print("FastAPI + Vue.js 3 + PostgreSQL + Celery")
    safe_print("="*80)

def check_postgresql():
    """检查PostgreSQL是否运行"""
    safe_print("\n[检查] PostgreSQL数据库状态...")
    
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=xihong_erp_postgres"],
            capture_output=True,
            text=True,
            timeout=5,
            encoding='utf-8',  # 明确指定UTF-8编码
            errors='ignore'     # 忽略无法解码的字符
        )
        
        # 安全检查stdout是否为None
        stdout = result.stdout or ""
        
        if "xihong_erp_postgres" in stdout and "healthy" in stdout:
            safe_print("  [OK] PostgreSQL容器正常运行")
            return True
        elif "xihong_erp_postgres" in stdout:
            safe_print("  [WARNING] PostgreSQL容器正在运行但可能不健康")
            return True  # 仍然尝试继续
        else:
            safe_print("  [WARNING] PostgreSQL容器未检测到")
            safe_print("  提示: 如果使用本地PostgreSQL，可以忽略此警告")
            return True  # 不阻止启动，让后端自己检查数据库连接
    except FileNotFoundError:
        safe_print("  [WARNING] Docker未安装或不在PATH中")
        safe_print("  提示: 如果使用本地PostgreSQL，可以忽略此警告")
        return True  # 不阻止启动
    except Exception as e:
        safe_print(f"  [WARNING] Docker检查跳过: {type(e).__name__}")
        return True  # 继续尝试，不阻止启动

def check_redis():
    """检查Redis是否运行（Celery需要Redis）"""
    safe_print("\n[检查] Redis服务状态...")
    
    try:
        import redis
        # ⭐ 修复：从环境变量读取REDIS_URL（支持密码）
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        
        # 如果REDIS_URL中没有密码，尝试从REDIS_PASSWORD读取
        if "@" not in redis_url.split("://")[1] and os.getenv("REDIS_PASSWORD"):
            # 解析URL并构建带密码的URL
            from urllib.parse import urlparse
            parsed = urlparse(redis_url)
            password = os.getenv("REDIS_PASSWORD")
            # 构建带密码的URL: redis://:password@host:port/db
            if parsed.port:
                redis_url = f"redis://:{password}@{parsed.hostname}:{parsed.port}{parsed.path}"
            else:
                redis_url = f"redis://:{password}@{parsed.hostname}:6379{parsed.path}"
        
        r = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        r.ping()
        r.close()
        safe_print("  [OK] Redis服务正常运行")
        return True
    except ImportError:
        safe_print("  [WARNING] redis库未安装，无法检查Redis")
        safe_print("  提示: Celery worker需要Redis，请安装: pip install redis")
        return False
    except Exception as e:
        # 检查Docker容器
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=redis"],
                capture_output=True,
                text=True,
                timeout=5,
                encoding='utf-8',
                errors='ignore'
            )
            stdout = result.stdout or ""
            if "redis" in stdout.lower():
                safe_print("  [WARNING] Redis容器存在但连接失败")
                error_type = type(e).__name__
                safe_print(f"  错误: {error_type}")
                if "AuthenticationError" in error_type or "auth" in str(e).lower():
                    safe_print("  提示: Redis需要密码认证，请检查.env中的REDIS_URL或REDIS_PASSWORD配置")
                    current_redis_url = os.getenv("REDIS_URL", "未设置")
                    # 隐藏密码显示
                    if "@" in current_redis_url:
                        safe_print(f"  当前REDIS_URL: redis://:***@{current_redis_url.split('@')[1]}")
                    else:
                        safe_print(f"  当前REDIS_URL: {current_redis_url}")
                else:
                safe_print("  提示: 请检查Redis是否正常启动")
                return False
        except:
            pass
        
        safe_print("  [WARNING] Redis服务不可用")
        safe_print("  提示: Celery worker需要Redis，请启动Redis服务")
        safe_print("  方式1: docker-compose -f docker-compose.prod.yml up -d redis")
        safe_print("  方式2: 确保.env中配置了正确的REDIS_URL或REDIS_PASSWORD")
        return False

def check_metabase():
    """检查Metabase是否运行（v4.6.0 DSS架构：已迁移到Metabase）"""
    safe_print("\n[检查] Metabase BI服务状态...")
    
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=metabase"],
            capture_output=True,
            text=True,
            timeout=5,
            encoding='utf-8',
            errors='ignore'
        )
        
        stdout = result.stdout or ""
        
        if "metabase" in stdout or "xihong_erp_metabase" in stdout:
            safe_print("  [OK] Metabase容器正在运行")
            safe_print("  地址: http://localhost:8080")
            return True
        else:
            safe_print("  [INFO] Metabase未运行（可选服务）")
            safe_print("  提示: 如需使用BI功能，请运行: docker-compose -f docker-compose.metabase.yml up -d")
            return False
    except FileNotFoundError:
        safe_print("  [WARNING] Docker未安装或不在PATH中")
        safe_print("  提示: Metabase是可选服务，不影响主系统运行")
        return False
    except Exception as e:
        safe_print(f"  [WARNING] Metabase检查跳过: {type(e).__name__}")
        safe_print("  提示: Metabase是可选服务，不影响主系统运行")
        return False

def start_backend():
    """启动后端服务（改进版）"""
    safe_print("\n[启动] 后端服务...")
    safe_print("  地址: http://localhost:8001")
    safe_print("  文档: http://localhost:8001/api/docs")
    
    backend_dir = Path(__file__).parent / "backend"
    
    if sys_platform.system() == "Windows":
        # Windows: 使用Start-Process在新窗口启动
        # 先构建路径字符串，避免f-string转义问题
        backend_path = str(backend_dir)
        cmd = f'Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd {backend_path}; python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload"'
        
        process = subprocess.Popen(
            ["powershell", "-Command", cmd],
            shell=True
        )
        
        safe_print("  [OK] 后端服务已在新窗口启动")
        safe_print("  提示: 查看新打开的PowerShell窗口获取详细日志")
    else:
        # Unix: 直接启动
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "main:app",
             "--host", "0.0.0.0", "--port", "8001", "--reload"],
            cwd=backend_dir
        )
        safe_print("  [OK] 后端服务已启动")
    
    return process

def start_frontend():
    """启动前端服务（改进版，含端口检查）"""
    safe_print("\n[启动] 前端服务...")
    safe_print("  地址: http://localhost:5173")
    
    frontend_dir = Path(__file__).parent / "frontend"
    
    # Windows: 尝试清理可能残留的Node.js进程（仅提示，不强制）
    if sys_platform.system() == "Windows":
        try:
            # 静默检查端口占用，如果被占用给出提示
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            result = sock.connect_ex(('localhost', 5173))
            sock.close()
            if result == 0:
                safe_print("  [WARN] 端口5173可能被占用，尝试关闭残留进程...")
                # 不强制kill，避免误杀其他重要进程
                # 用户可以通过任务管理器手动关闭node.exe
        except:
            pass
    
    if sys_platform.system() == "Windows":
        # Windows: 使用Start-Process在新窗口启动
        # 先构建路径字符串，避免f-string转义问题
        frontend_path = str(frontend_dir)
        cmd = f'Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd {frontend_path}; npm run dev"'
        
        process = subprocess.Popen(
            ["powershell", "-Command", cmd],
            shell=True
        )
        
        safe_print("  [OK] 前端服务已在新窗口启动")
        safe_print("  [INFO] 如果端口被占用，Vite会自动使用下一个端口（5174/5175...）")
    else:
        # Unix: 直接启动
        process = subprocess.Popen(
            ["npm", "run", "dev"],
            cwd=frontend_dir
        )
        safe_print("  [OK] 前端服务已启动")
    
    return process

def start_celery_worker():
    """启动Celery worker（v4.19.6新增）"""
    safe_print("\n[启动] Celery Worker服务...")
    safe_print("  队列: data_sync, scheduled, data_processing")
    
    backend_dir = Path(__file__).parent / "backend"
    project_root = Path(__file__).parent
    
    if sys_platform.system() == "Windows":
        # Windows: 使用Start-Process在新窗口启动
        backend_path = str(backend_dir)
        # Windows必须使用--pool=solo
        cmd = f'Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd {backend_path}; python -m celery -A backend.celery_app worker --loglevel=info --queues=data_sync,scheduled,data_processing --pool=solo --concurrency=4"'
        
        process = subprocess.Popen(
            ["powershell", "-Command", cmd],
            shell=True,
            cwd=project_root
        )
        
        safe_print("  [OK] Celery Worker已在新窗口启动")
        safe_print("  提示: 查看新打开的PowerShell窗口获取Celery日志")
    else:
        # Unix: 直接启动
        process = subprocess.Popen(
            [sys.executable, "-m", "celery", "-A", "backend.celery_app", "worker",
             "--loglevel=info", "--queues=data_sync,scheduled,data_processing", "--concurrency=4"],
            cwd=project_root
        )
        safe_print("  [OK] Celery Worker已启动")
    
    return process

def check_docker_container_running(container_name):
    """检查Docker容器是否在运行（返回True/False）"""
    try:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"name={container_name}", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=5,
            encoding='utf-8',
            errors='ignore'
        )
        return container_name in (result.stdout or "")
    except:
        return False

def get_docker_container_status(container_name):
    """获取Docker容器状态（返回状态字符串）"""
    try:
        result = subprocess.run(
            ["docker", "ps", "-a", "--filter", f"name={container_name}", "--format", "{{.Status}}"],
            capture_output=True,
            text=True,
            timeout=5,
            encoding='utf-8',
            errors='ignore'
        )
        return (result.stdout or "").strip()
    except:
        return "unknown"

def show_docker_container_logs(container_name, lines=50):
    """显示Docker容器日志（最后N行）"""
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(lines), container_name],
            capture_output=True,
            text=True,
            timeout=10,
            encoding='utf-8',
            errors='ignore'
        )
        return result.stdout or result.stderr or ""
    except:
        return "无法获取日志"

def start_services_with_docker_compose():
    """使用Docker Compose启动服务（v4.19.6新增，生产模式：确保所有服务在容器中运行）"""
    safe_print("\n[启动] 使用Docker Compose启动服务...")
    
    project_root = Path(__file__).parent
    
    # ⭐ Phase 1.3: 环境变量验证（开发环境可跳过）
    env_file = project_root / ".env"
    skip_validation = os.getenv("SKIP_ENV_VALIDATION", "false").lower() == "true"
    
    if not skip_validation and env_file.exists():
        safe_print("  [检查] 验证环境变量配置...")
        validate_script = project_root / "scripts" / "validate-env.py"
        if validate_script.exists():
            try:
                result = subprocess.run(
                    [sys.executable, str(validate_script), "--env-file", str(env_file), "--skip-p1"],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    encoding='utf-8',
                    errors='ignore'
                )
                if result.returncode != 0:
                    safe_print("  [WARNING] 环境变量验证失败（开发环境仅检查P0变量）")
                    safe_print(f"  错误: {result.stderr[:200] if result.stderr else result.stdout[:200]}")
                    safe_print("  提示: 可以设置 SKIP_ENV_VALIDATION=true 跳过验证")
                    # 开发环境不阻止启动，仅警告
                else:
                    safe_print("  [OK] 环境变量验证通过")
            except Exception as e:
                safe_print(f"  [WARNING] 环境变量验证脚本执行失败: {type(e).__name__}")
                safe_print("  提示: 可以设置 SKIP_ENV_VALIDATION=true 跳过验证")
        else:
            safe_print("  [INFO] 环境变量验证脚本不存在，跳过验证")
    elif not env_file.exists():
        safe_print("  [INFO] .env 文件不存在，跳过验证")
    
    # 检查docker-compose文件
    compose_base = project_root / "docker-compose.yml"
    compose_dev = project_root / "docker-compose.dev.yml"
    
    if not compose_base.exists():
        safe_print("  [ERROR] docker-compose.yml 不存在")
        return False
    
    compose_files = ["-f", str(compose_base)]
    profile_name = "dev-full"
    
    if compose_dev.exists():
        compose_files.extend(["-f", str(compose_dev)])
    
    try:
        # 启动Redis和PostgreSQL
        safe_print("  [启动] Redis和PostgreSQL...")
        cmd = ["docker-compose"] + compose_files + ["--profile", "dev", "up", "-d", "redis", "postgres"]
        result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, timeout=120, encoding='utf-8', errors='ignore')
        if result.returncode != 0:
            error_msg = result.stderr or result.stdout or "未知错误"
            safe_print(f"  [WARNING] Docker Compose启动失败: {error_msg[:200]}")
            return False
        safe_print("  [OK] Redis和PostgreSQL已启动")
        
        # 等待服务就绪（给服务时间完全启动）
        safe_print("  [等待] 服务启动中...")
        time.sleep(8)  # 增加等待时间，确保Redis和PostgreSQL完全就绪
        
        # ⭐ 新增：检查PostgreSQL数据库连接（诊断数据库用户问题）
        safe_print("  [检查] PostgreSQL数据库连接...")
        try:
            result = subprocess.run(
                ["docker", "exec", "xihong_erp_postgres", "psql", "-U", "erp_user", "-d", "xihong_erp", "-c", "SELECT 1"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding='utf-8',
                errors='ignore'
            )
            if result.returncode == 0:
                safe_print("  [OK] PostgreSQL数据库连接正常")
            else:
                safe_print("  [WARNING] PostgreSQL数据库连接测试失败")
                safe_print(f"  错误输出: {result.stderr[:200]}")
                safe_print("  提示: 数据库用户可能不存在，需要重新创建数据库容器")
                safe_print("  解决方案:")
                safe_print("    1. 停止并删除数据库容器和数据卷:")
                safe_print("       docker-compose -f docker-compose.yml -f docker-compose.dev.yml down -v")
                safe_print("    2. 重新启动服务:")
                safe_print("       python run.py --use-docker")
        except Exception as e:
            safe_print(f"  [WARNING] 无法检查数据库连接: {e}")
        
        # 启动后端API（生产模式：必须在Docker中运行）
        safe_print("  [启动] 后端API服务...")
        safe_print("  提示: 首次构建可能需要几分钟，请耐心等待...")
        backend_container = "xihong_erp_backend"
        try:
            cmd = ["docker-compose"] + compose_files + ["--profile", profile_name, "up", "-d", "backend"]
            # ⭐ 增加超时到300秒（5分钟），首次构建需要更长时间
            result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, timeout=300, encoding='utf-8', errors='ignore')
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "未知错误"
                safe_print(f"  [ERROR] 后端API启动命令失败: {error_msg[:200]}")
                safe_print(f"  容器状态: {get_docker_container_status(backend_container)}")
                safe_print("  容器日志:")
                logs = show_docker_container_logs(backend_container, 30)
                for line in logs.split('\n')[-20:]:  # 只显示最后20行
                    if line.strip():
                        safe_print(f"    {line}")
                return False
            
            # ⭐ 验证容器是否真的在运行
            safe_print("  [验证] 检查后端容器状态...")
            time.sleep(3)  # 给容器一些启动时间
            
            max_retries = 10
            for i in range(max_retries):
                if check_docker_container_running(backend_container):
                    safe_print(f"  [OK] 后端容器正在运行（尝试 {i+1}/{max_retries}）")
                    break
                else:
                    status = get_docker_container_status(backend_container)
                    safe_print(f"  [等待] 容器状态: {status} (尝试 {i+1}/{max_retries})")
                    if i < max_retries - 1:
                        time.sleep(2)
            else:
                # 容器未运行
                status = get_docker_container_status(backend_container)
                safe_print(f"  [ERROR] 后端容器启动失败")
                safe_print(f"  容器状态: {status}")
                safe_print("  容器日志（最后30行）:")
                logs = show_docker_container_logs(backend_container, 30)
                for line in logs.split('\n')[-30:]:
                    if line.strip():
                        safe_print(f"    {line}")
                safe_print("\n  诊断建议:")
                safe_print("    1. 查看完整日志: docker logs xihong_erp_backend")
                safe_print("    2. 检查容器状态: docker ps -a | grep backend")
                safe_print("    3. 手动启动: docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full up -d backend")
                return False
            
            # ⭐ 现代化Docker最佳实践：等待后端服务健康检查通过（容器运行 ≠ 服务就绪）
            safe_print("  [等待] 后端服务健康检查...")
            max_health_retries = 30  # 最多等待5分钟（30 * 10秒）
            backend_healthy = False
            log_check_interval = 10  # 每10次重试（100秒）显示一次容器日志
            
            for i in range(max_health_retries):
                # ⭐ 改进：定期检查容器日志，及早发现启动失败
                if i > 0 and i % log_check_interval == 0:
                    safe_print(f"  [诊断] 检查容器状态（尝试 {i}/{max_health_retries}）...")
                    # 检查容器是否仍在运行
                    if not check_docker_container_running(backend_container):
                        status = get_docker_container_status(backend_container)
                        safe_print(f"  [ERROR] 后端容器已停止，状态: {status}")
                        safe_print("  容器日志（最后50行）:")
                        logs = show_docker_container_logs(backend_container, 50)
                        for line in logs.split('\n')[-50:]:
                            if line.strip():
                                safe_print(f"    {line}")
                        safe_print("\n  诊断建议:")
                        safe_print("    1. 查看完整日志: docker logs xihong_erp_backend -f")
                        safe_print("    2. 检查数据库连接配置")
                        safe_print("    3. 检查容器环境变量: docker exec xihong_erp_backend env | grep DATABASE")
                        return False
                    # 检查容器日志中是否有错误
                    logs = show_docker_container_logs(backend_container, 30)
                    # 检查常见错误
                    if "Application startup failed" in logs or "ERROR" in logs.upper():
                        safe_print("  [WARNING] 检测到容器启动错误，显示日志:")
                        for line in logs.split('\n')[-20:]:
                            if line.strip() and ("ERROR" in line.upper() or "Exception" in line or "Failed" in line):
                                safe_print(f"    {line}")
                
                try:
                    import urllib.request
                    import urllib.error
                    response = urllib.request.urlopen("http://localhost:8001/health", timeout=5)
                    if response.status == 200:
                        safe_print(f"  [OK] 后端服务健康检查通过（尝试 {i+1}/{max_health_retries}）")
                        backend_healthy = True
                        break
                except urllib.error.URLError as e:
                    if i < max_health_retries - 1:
                        # 每3次重试（30秒）显示一次等待提示
                        if (i + 1) % 3 == 0:
                            safe_print(f"  [等待] 后端服务启动中... (尝试 {i+1}/{max_health_retries})")
                            # 如果等待时间超过60秒，显示容器状态
                            if i >= 6:
                                safe_print("  提示: 如果长时间等待，请查看容器日志: docker logs xihong_erp_backend -f")
                        time.sleep(10)  # 等待10秒后重试
                    else:
                        # 最后一次重试失败，显示完整错误信息
                        safe_print(f"  [ERROR] 后端服务健康检查失败（超过5分钟）")
                        safe_print(f"  错误: {e}")
                        safe_print("  容器日志（最后50行）:")
                        logs = show_docker_container_logs(backend_container, 50)
                        for line in logs.split('\n')[-50:]:
                            if line.strip():
                                safe_print(f"    {line}")
                        safe_print("\n  诊断建议:")
                        safe_print("    1. 查看完整日志: docker logs xihong_erp_backend -f")
                        safe_print("    2. 测试健康检查: curl http://localhost:8001/health")
                        safe_print("    3. 检查数据库连接: docker exec xihong_erp_backend env | grep DATABASE_URL")
                        safe_print("    4. 检查容器状态: docker ps -a | grep backend")
                        return False
                except Exception as e:
                    if i < max_health_retries - 1:
                        time.sleep(10)
                    else:
                        safe_print(f"  [ERROR] 后端服务健康检查异常: {e}")
                        safe_print("  容器日志（最后30行）:")
                        logs = show_docker_container_logs(backend_container, 30)
                        for line in logs.split('\n')[-30:]:
                            if line.strip():
                                safe_print(f"    {line}")
                        return False
            
            if not backend_healthy:
                safe_print("  [ERROR] 后端服务健康检查超时")
                safe_print("  容器日志（最后50行）:")
                logs = show_docker_container_logs(backend_container, 50)
                for line in logs.split('\n')[-50:]:
                    if line.strip():
                        safe_print(f"    {line}")
                return False
                
        except subprocess.TimeoutExpired:
            safe_print("  [ERROR] 后端API构建超时（超过5分钟）")
            safe_print("  提示: 请手动构建和启动:")
            safe_print("    docker-compose -f docker-compose.yml -f docker-compose.dev.yml build backend")
            safe_print("    docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full up -d backend")
            return False
        
        # 启动Celery Worker（生产模式：必须在Docker中运行）
        safe_print("  [启动] Celery Worker...")
        safe_print("  提示: 首次构建可能需要几分钟，请耐心等待...")
        celery_container = "xihong_erp_celery_worker"
        try:
            cmd = ["docker-compose"] + compose_files + ["--profile", profile_name, "up", "-d", "celery-worker"]
            # ⭐ 增加超时到300秒（5分钟）
            result = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, timeout=300, encoding='utf-8', errors='ignore')
            
            if result.returncode != 0:
                error_msg = result.stderr or result.stdout or "未知错误"
                safe_print(f"  [ERROR] Celery Worker启动失败: {error_msg[:200]}")
                safe_print(f"  容器状态: {get_docker_container_status(celery_container)}")
                safe_print("  容器日志:")
                logs = show_docker_container_logs(celery_container, 30)
                for line in logs.split('\n')[-20:]:
                    if line.strip():
                        safe_print(f"    {line}")
                return False
            
            # ⭐ 验证Celery Worker容器是否真的在运行
            safe_print("  [验证] 检查Celery Worker容器状态...")
            time.sleep(3)
            
            max_retries = 10
            for i in range(max_retries):
                if check_docker_container_running(celery_container):
                    safe_print(f"  [OK] Celery Worker容器正在运行（尝试 {i+1}/{max_retries}）")
                    break
                else:
                    status = get_docker_container_status(celery_container)
                    safe_print(f"  [等待] 容器状态: {status} (尝试 {i+1}/{max_retries})")
                    if i < max_retries - 1:
                        time.sleep(2)
            else:
                status = get_docker_container_status(celery_container)
                safe_print(f"  [ERROR] Celery Worker容器启动失败")
                safe_print(f"  容器状态: {status}")
                safe_print("  容器日志（最后30行）:")
                logs = show_docker_container_logs(celery_container, 30)
                for line in logs.split('\n')[-30:]:
                    if line.strip():
                        safe_print(f"    {line}")
                safe_print("\n  诊断建议:")
                safe_print("    1. 查看完整日志: docker logs xihong_erp_celery_worker")
                safe_print("    2. 检查容器状态: docker ps -a | grep celery")
                safe_print("    3. 手动启动: docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full up -d celery-worker")
                return False
                
        except subprocess.TimeoutExpired:
            safe_print("  [ERROR] Celery Worker构建超时")
            safe_print("  提示: 请手动构建和启动:")
            safe_print("    docker-compose -f docker-compose.yml -f docker-compose.dev.yml build celery-worker")
            safe_print("    docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full up -d celery-worker")
            return False
        
        return True
    except FileNotFoundError:
        safe_print("  [ERROR] docker-compose 命令未找到")
        safe_print("  提示: 请安装Docker Compose或确保其在PATH中")
        return False
    except Exception as e:
        safe_print(f"  [ERROR] Docker Compose启动失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def wait_for_service(port, name, max_wait=30):
    """等待服务启动"""
    import socket
    
    safe_print(f"\n[等待] {name}服务启动中...")
    
    for i in range(max_wait):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            result = sock.connect_ex(('127.0.0.1', port))
            if result == 0:
                safe_print(f"  [OK] {name}已就绪 ({i+1}秒)")
                return True
        finally:
            sock.close()
        
        if (i + 1) % 5 == 0:
            safe_print(f"  等待中... {i+1}/{max_wait}秒")
        
        time.sleep(1)
    
    safe_print(f"  [WARNING] {name}启动超时")
    return False

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="西虹ERP系统启动脚本（修复版）")
    parser.add_argument("--backend-only", action="store_true", help="仅启动后端")
    parser.add_argument("--frontend-only", action="store_true", help="仅启动前端")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--with-metabase", action="store_true", help="同时启动Metabase（如果未运行）")
    parser.add_argument("--no-celery", action="store_true", help="不启动Celery worker（v4.19.6新增）")
    parser.add_argument("--use-docker", action="store_true", help="使用Docker Compose启动服务（推荐，统一管理）")
    args = parser.parse_args()
    
    print_banner()
    
    # ⭐ v4.19.6新增：Docker Compose模式
    if args.use_docker:
        safe_print("\n[模式] Docker Compose模式（统一管理服务）")
        if not args.frontend_only:
            # 启动Docker服务（Redis、PostgreSQL、Celery Worker）
            docker_success = start_services_with_docker_compose()
            if not docker_success:
                safe_print("\n[ERROR] Docker Compose启动失败")
                safe_print("  提示: 可以尝试手动运行: docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full up -d")
                input("\n按回车键退出...")
                sys.exit(1)
            
            # Docker模式下，不启动本地后端和Celery worker（已经在Docker中运行）
            args.no_celery = True  # 标记为不需要本地启动Celery worker
            safe_print("\n[提示] 后端API和Celery Worker已在Docker容器中运行")
            safe_print("  提示: 如需查看日志: docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f celery-worker")
        # 继续启动前端（如果需要）
    
    # 检查PostgreSQL（非Docker模式下）
    if not args.use_docker and not check_postgresql():
        safe_print("\n[ERROR] 请先启动PostgreSQL")
        input("\n按回车键退出...")
        sys.exit(1)
    
    # 检查Redis（如果启动本地Celery worker需要Redis）
    redis_available = False
    if not args.use_docker and not args.no_celery and not args.frontend_only:
        redis_available = check_redis()
        if not redis_available:
            safe_print("\n[WARNING] Redis不可用，Celery worker无法启动")
            safe_print("  选项1: 启动Redis后重新运行脚本")
            safe_print("  选项2: 使用 --use-docker 参数使用Docker Compose模式（推荐）")
            safe_print("  选项3: 使用 --no-celery 参数跳过Celery worker（数据同步会使用降级模式）")
            choice = input("\n是否继续启动（不启动Celery worker）? (y/n): ").strip().lower()
            if choice != 'y':
                safe_print("[退出] 用户取消启动")
                sys.exit(0)
            args.no_celery = True  # 强制禁用Celery
    
    # 检查Metabase（v4.6.0 DSS架构：已迁移到Metabase）
    metabase_running = check_metabase()
    if args.with_metabase and not metabase_running:
        safe_print("\n[启动] Metabase服务...")
        try:
            compose_file = Path(__file__).parent / "docker-compose.metabase.yml"
            if compose_file.exists():
                result = subprocess.run(
                    ["docker-compose", "-f", str(compose_file), "up", "-d"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode == 0:
                    safe_print("  [OK] Metabase服务已启动")
                    safe_print("  等待30秒让Metabase完全启动...")
                    time.sleep(30)
                    metabase_running = True
                else:
                    safe_print("  [WARNING] Metabase启动失败，请手动检查")
            else:
                safe_print("  [WARNING] docker-compose.metabase.yml 文件不存在")
        except Exception as e:
            safe_print(f"  [WARNING] Metabase启动失败: {e}")
    
    processes = []
    
    try:
        # 启动后端（非Docker模式下）
        if not args.frontend_only and not args.use_docker:
            backend_process = start_backend()
            processes.append(("backend", backend_process))
            
            # 等待后端就绪
            if wait_for_service(8001, "后端API", 20):
                safe_print("  [OK] 后端API就绪")
            else:
                safe_print("  [WARNING] 后端启动可能失败，请查看后端窗口")
        elif args.use_docker and not args.frontend_only:
            # Docker模式下，等待后端容器就绪
            safe_print("\n[等待] 后端API容器启动中...")
            if wait_for_service(8001, "后端API容器", 30):
                safe_print("  [OK] 后端API容器已就绪")
            else:
                safe_print("  [WARNING] 后端容器可能未启动，请检查Docker容器状态")
        
        # 启动Celery worker（v4.19.6新增，仅非Docker模式）
        celery_process = None
        if not args.use_docker and not args.no_celery and not args.frontend_only:
            if redis_available:
                celery_process = start_celery_worker()
                processes.append(("celery", celery_process))
                # 给Celery一些启动时间
                time.sleep(3)
            else:
                safe_print("\n[SKIP] 跳过Celery Worker（Redis不可用）")
                safe_print("  提示: 数据同步将使用降级模式（asyncio.create_task）")
        
        # 启动前端
        if not args.backend_only:
            frontend_process = start_frontend()
            processes.append(("frontend", frontend_process))
            
            # 等待前端就绪
            if wait_for_service(5173, "前端界面", 15):
                safe_print("  [OK] 前端界面就绪")
        
        # 打印访问信息
        safe_print("\n" + "="*80)
        safe_print("[成功] 系统启动成功！")
        safe_print("="*80)
        
        if not args.frontend_only:
            safe_print("[后端] API文档:  http://localhost:8001/api/docs")
            safe_print("[后端] 健康检查: http://localhost:8001/health")
        
        if args.use_docker:
            safe_print("[任务] Celery Worker已启动（Docker容器，处理数据同步任务）")
            safe_print("       查看日志: docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f celery-worker")
        elif celery_process:
            safe_print("[任务] Celery Worker已启动（处理数据同步任务）")
        
        if not args.backend_only:
            safe_print("[前端] 主界面:   http://localhost:5173")
        
        if metabase_running:
            safe_print("[BI]   Metabase:  http://localhost:8080")
            safe_print("       账号: admin@xihong.com / admin")
        
        safe_print("="*80)
        if args.use_docker:
            safe_print("\n[提示] Docker Compose模式：服务在容器中运行")
            safe_print("[提示] 停止服务: docker-compose -f docker-compose.yml -f docker-compose.dev.yml --profile dev-full down")
            safe_print("[提示] 查看日志: docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f")
        else:
        safe_print("\n[提示] 服务已在独立窗口运行，关闭窗口即可停止服务")
        safe_print("[提示] 按 Ctrl+C 退出此脚本（服务继续运行）")
            if celery_process:
                safe_print("[提示] Celery Worker处理数据同步任务，请保持运行")
        safe_print("="*80)
        
        # 自动打开浏览器
        if not args.no_browser and not args.backend_only:
            safe_print("\n[浏览器] 5秒后自动打开...")
            time.sleep(5)
            try:
                webbrowser.open("http://localhost:5173")
                safe_print("[OK] 浏览器已打开")
            except Exception as e:
                safe_print(f"[WARNING] 无法自动打开浏览器: {e}")
        
        # 保持运行（监控模式）
        safe_print("\n[监控] 系统监控中... (按Ctrl+C退出监控)\n")
        
        while True:
            time.sleep(10)
            # 简单的心跳检查
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                result = sock.connect_ex(('127.0.0.1', 8001))
                if result != 0 and not args.frontend_only:
                    safe_print("[WARNING] 后端服务似乎已停止")
                    break
            finally:
                sock.close()
        
    except KeyboardInterrupt:
        safe_print("\n\n[退出] 监控脚本已退出")
        safe_print("[提示] 后端、前端和Celery Worker服务仍在独立窗口运行")
        safe_print("[提示] 关闭对应窗口可停止服务")
    
    except Exception as e:
        safe_print(f"\n[ERROR] 启动失败: {e}")
        import traceback
        traceback.print_exc()
        input("\n按回车键退出...")
        sys.exit(1)

if __name__ == "__main__":
    main()

