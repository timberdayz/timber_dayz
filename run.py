#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
西虹ERP系统 - 统一启动脚本 (v4.24.2)

版本历史:
- v4.24.2: --local 时强制 ENVIRONMENT=development，保证本地采集默认有头（fix-local-collection-headed-mode）
- v4.24.1: 版本号同步；修复 Windows 下 Start-Process -Command 中 $env:PYTHONPATH 被父进程展开导致子窗口报错
- v4.19.8: 新增 --local 一键本地开发（Docker 起 Postgres/Redis，本机起后端/Celery/前端）
- v4.19.7: 改进Docker健康检查等待逻辑，添加数据库连接预检查，主动检测启动错误
- v4.19.6: 添加Celery worker自动启动功能 + Docker Compose模式支持
- v4.18.0: 统一使用相对路径，提升云端迁移兼容性
- v4.1.1: 改进Windows下的进程启动方式

使用方法:
    python run.py                      # 传统模式（需先启动 Postgres/Redis）
    python run.py --local              # 一键本地：Docker 起 Postgres/Redis，本机起后端+Celery+前端
    python run.py --use-docker         # Docker Compose模式（推荐，统一管理）
    python run.py --backend-only       # 仅启动后端
    python run.py --frontend-only      # 仅启动前端
    python run.py --no-celery          # 不启动Celery worker
    python run.py --use-docker --collection
"""

import subprocess
import sys
import time
import webbrowser
import argparse
import shutil
from pathlib import Path
import platform as sys_platform
import os

BACKEND_PORT = 8001
FRONTEND_PORT = 5173
ACTIVE_BACKEND_PORT = BACKEND_PORT

# 本地启动时加载项目根目录 .env，使 check_redis/check_postgresql 及后端能读取 REDIS_URL、DATABASE_URL 等
_project_root = Path(__file__).resolve().parent
_env_file = _project_root / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        pass

def safe_print(text):
    """安全打印（处理Windows GBK编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            # 尝试GBK编码
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            # 降级到ASCII
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)

def print_banner():
    """打印系统横幅"""
    safe_print("\n" + "="*80)
    safe_print("西虹ERP系统 v4.24.1")
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
        # [FIX] 修复：从环境变量读取REDIS_URL（支持密码）
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

def ensure_postgresql_dashboard_assets(project_root):
    """Ensure PostgreSQL Dashboard assets exist before runtime starts."""
    use_postgresql_dashboard = os.getenv("USE_POSTGRESQL_DASHBOARD_ROUTER", "true").lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if not use_postgresql_dashboard:
        return True

    script_path = project_root / "scripts" / "bootstrap_postgresql_dashboard.py"
    if not script_path.exists():
        safe_print("  [ERROR] 缺少 PostgreSQL Dashboard bootstrap 脚本")
        safe_print(f"  路径: {script_path}")
        return False

    safe_print("  [检查] PostgreSQL Dashboard 资产...")
    check_result = subprocess.run(
        [sys.executable, str(script_path), "--check"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=120,
        encoding="utf-8",
        errors="ignore",
    )
    if check_result.returncode == 0:
        safe_print("  [OK] PostgreSQL Dashboard 资产完整")
        return True

    safe_print("  [修复] 检测到 PostgreSQL Dashboard 资产缺失，开始初始化...")
    apply_result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=300,
        encoding="utf-8",
        errors="ignore",
    )
    if apply_result.returncode != 0:
        safe_print("  [ERROR] PostgreSQL Dashboard 资产初始化失败")
        output = (apply_result.stdout or apply_result.stderr or "").splitlines()[-20:]
        for line in output:
            if line.strip():
                safe_print(f"    {line}")
        return False

    safe_print("  [OK] PostgreSQL Dashboard 资产初始化完成")
    return True


def warn_legacy_shop_session_artifacts(project_root):
    """启动期告警：提醒当前磁盘上仍有店铺级会话残留。"""
    try:
        from backend.utils.config import get_settings
        from modules.utils.sessions.legacy_shop_artifact_cleanup import (
            collect_legacy_shop_artifacts_for_active_shops,
        )

        artifacts = collect_legacy_shop_artifacts_for_active_shops(
            Path(project_root),
            get_settings().DATABASE_URL,
        )
    except Exception as e:
        safe_print(f"  [WARNING] 遗留店铺会话残留检查失败: {e}")
        return True

    if not artifacts:
        return True

    safe_print("  [WARNING] 检测到店铺级会话历史残留，当前运行不会使用它们，但建议及时清理:")
    for artifact in artifacts[:10]:
        safe_print(f"    {artifact}")
    if len(artifacts) > 10:
        safe_print(f"    ... 其余 {len(artifacts) - 10} 个路径已省略")
    safe_print("  提示: 可执行 `python tools/cleanup_legacy_shop_session_artifacts.py --delete` 清理")
    return True


def _is_port_in_use(port, host="127.0.0.1"):
    """检查本地端口是否已被占用。"""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def _require_local_port_available(port, service_name):
    """启动本地服务前确认端口可用，避免误把其他服务当成本项目。"""
    if _is_port_in_use(port):
        safe_print(f"  [ERROR] {service_name} 所需端口 {port} 已被占用")
        safe_print(f"  鎻愮ず: 璇峰厛閲婃斁 localhost:{port}锛屽啀閲嶈瘯 python run.py --local")
        return False
    return True


def _docker_container_health(container_name):
    """返回 Docker 容器健康状态（healthy/running/unhealthy/...）。"""
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{if .State.Running}}running{{else}}stopped{{end}}{{end}}",
                container_name,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
            errors="ignore",
        )
        if result.returncode != 0:
            return "missing"
        return (result.stdout or "").strip() or "unknown"
    except Exception:
        return "unknown"


def _wait_for_local_docker_infra(container_names, max_wait=60):
    """等待本地模式所需的 Docker 依赖容器进入健康状态。"""
    safe_print("  [等待] Docker 基础服务健康检查...")
    for second in range(max_wait):
        statuses = {name: _docker_container_health(name) for name in container_names}
        if all(status in ("healthy", "running") for status in statuses.values()):
            status_text = ", ".join(f"{name}={status}" for name, status in statuses.items())
            safe_print(f"  [OK] Docker 基础服务已就绪: {status_text}")
            return True
        if (second + 1) % 5 == 0:
            status_text = ", ".join(f"{name}={status}" for name, status in statuses.items())
            safe_print(f"  等待中... {second + 1}/{max_wait}秒 ({status_text})")
        time.sleep(1)

    status_text = ", ".join(
        f"{name}={_docker_container_health(name)}" for name in container_names
    )
    safe_print(f"  [ERROR] Docker 基础服务等待超时: {status_text}")
    return False


def _read_nvmrc_version(project_root):
    """读取 .nvmrc 中的 Node 主版本号（如 24），用于优先选择对应版本。"""
    nvmrc = project_root / ".nvmrc"
    if not nvmrc.exists():
        return None
    try:
        ver = nvmrc.read_text(encoding="utf-8", errors="ignore").strip().strip("v")
        if ver:
            return ver.split(".")[0]
    except Exception:
        pass
    return None


def start_celery_worker():
    """启动Celery worker（v4.19.6新增）"""
    safe_print("\n[启动] Celery Worker服务...")
    safe_print("  队列: data_sync, scheduled, data_processing")
    
    backend_dir = Path(__file__).parent / "backend"
    project_root = Path(__file__).parent
    
    if sys_platform.system() == "Windows":
        # Windows: 设置 PYTHONPATH 并指定 -WorkingDirectory，保证子进程能 import backend
        # 反引号转义 $ 避免父 PowerShell 展开 $env:PYTHONPATH 导致子窗口收到 "=路径" 报 CommandNotFoundException
        work_dir = str(project_root.resolve())
        work_dir_ps = work_dir.replace("'", "''")
        celery_cmd = "`$env:PYTHONPATH='{}'; python -m celery -A backend.celery_app worker --loglevel=info --queues=data_sync,scheduled,data_processing --pool=solo --concurrency=4".format(work_dir_ps)
        cmd = (
            'Start-Process powershell -ArgumentList "-NoExit", "-Command", "{}" -WorkingDirectory "{}"'
        ).format(celery_cmd.replace('"', '`"'), work_dir.replace('"', '`"'))
        
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

def _load_env_vars(env_path):
    """从 .env 文件加载键值对（简单解析，用于启动前检查）"""
    vars_map = {}
    if not env_path or not env_path.exists():
        return vars_map
    try:
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            key = k.strip()
            val = v.strip().strip("'\"").split("#")[0].strip()
            if key:
                vars_map[key] = val
    except Exception:
        pass
    return vars_map


def validate_environment_for_docker(project_root):
    """
    启动前环境检查：Docker 模式下校验关键环境变量，避免部署后失败。
    仅警告不阻断，返回是否通过。
    """
    env_file = project_root / ".env"
    if not env_file.exists():
        safe_print("  [WARNING] .env 不存在，Docker Compose 将使用各 compose 文件内默认值")
        safe_print("  建议: cp env.example .env 并修改必要项（如 REDIS_PASSWORD）")
        return True
    vars_map = _load_env_vars(env_file)
    required = ["DATABASE_URL", "SECRET_KEY"]
    optional_docker = ["REDIS_PASSWORD", "POSTGRES_PASSWORD"]
    missing = [k for k in required if not (vars_map.get(k) or os.getenv(k))]
    missing_opt = [k for k in optional_docker if not (vars_map.get(k) or os.getenv(k))]
    if missing:
        safe_print(f"  [WARNING] 建议在 .env 中配置: {', '.join(missing)}")
        safe_print("  否则可能导致容器无法连接数据库或认证失败")
    if missing_opt and not os.getenv("SKIP_ENV_VALIDATION"):
        safe_print(f"  [INFO] 可选变量未设置将使用默认值: {', '.join(missing_opt)}")
    return True


def pre_flight_check_docker(project_root):
    """启动前检查：Docker 是否可用、.env 是否存在。仅提示，不阻断。"""
    try:
        r = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
            errors="ignore",
            cwd=project_root,
        )
        if r.returncode != 0:
            safe_print("  [FAIL] Docker 未运行或不可用，请先启动 Docker Desktop / Docker Engine")
            return False
        safe_print("  [OK] Docker 运行正常")
    except FileNotFoundError:
        safe_print("  [FAIL] 未找到 docker 命令，请安装 Docker 并加入 PATH")
        return False
    except Exception as e:
        safe_print(f"  [FAIL] Docker 检查异常: {e}")
        return False
    return True


def start_services_with_docker_compose(use_collection=False):
    """使用Docker Compose启动服务（v4.19.6新增，生产模式：确保所有服务在容器中运行）
    use_collection: 若为 True，加载 docker-compose.collection-dev.yml，使 backend 使用 Dockerfile.collection（带 Playwright）
    """
    safe_print("\n[启动] 使用Docker Compose启动服务...")
    
    project_root = Path(__file__).parent
    
    # [Phase 3.3] 启动前检查：Docker 可用性
    safe_print("  [检查] 本地开发启动清单...")
    if not pre_flight_check_docker(project_root):
        return False
    
    # [Phase 2.3] 启动前环境检查（Docker 关键变量）
    validate_environment_for_docker(project_root)
    
    # [PHASE 1.3] 环境变量验证（开发环境可跳过）
    env_file = project_root / ".env"
    skip_validation = os.getenv("SKIP_ENV_VALIDATION", "false").lower() == "true"
    
    if not skip_validation and env_file.exists():
        safe_print("  [检查] 验证环境变量配置...")
        validate_script = project_root / "scripts" / "validate-env.py"
        if validate_script.exists():
            try:
                # [FIX] 设置Python IO编码环境变量，确保subprocess输出UTF-8
                env = os.environ.copy()
                env['PYTHONIOENCODING'] = 'utf-8'
                
                result = subprocess.run(
                    [sys.executable, str(validate_script), "--env-file", str(env_file), "--skip-p1"],
                    cwd=project_root,
                    capture_output=True,
                    text=True,
                    timeout=10,
                    encoding='utf-8',
                    errors='replace',
                    env=env
                )
                if result.returncode != 0:
                    safe_print("  [WARNING] 环境变量验证失败（开发环境仅检查P0变量）")
                    error_msg = result.stderr if result.stderr else result.stdout
                    if error_msg:
                        # [FIX] 改进错误消息处理：subprocess输出已经是UTF-8字符串，直接显示
                        # 但需要确保在Windows控制台正确显示
                        try:
                            # 错误消息已经是UTF-8编码的字符串（通过subprocess的encoding='utf-8'）
                            # 直接使用safe_print，它会处理GBK编码问题
                            error_lines = error_msg.split('\n')[:5]  # 只显示前5行
                            for line in error_lines:
                                if line.strip():
                                    safe_print(f"    {line}")
                        except Exception as e:
                            safe_print(f"  错误: [无法显示错误详情: {type(e).__name__}]")
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
    
    # [Phase 3.1] 显示当前使用的 Profile，便于排查本地/云端差异
    safe_print(f"  [INFO] Docker Compose Profile: {profile_name}")
    
    
    # [v4.19.x] 采集模式：使 backend 使用 Dockerfile.collection（带 Playwright）
    compose_collection_dev = project_root / "docker-compose.collection-dev.yml"
    if use_collection and compose_collection_dev.exists():
        compose_files.extend(["-f", str(compose_collection_dev)])
        safe_print("  [INFO] 已加载采集开发配置（backend 使用 Dockerfile.collection，端口 8001）")
    
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
        
        # [NEW] 新增：检查PostgreSQL数据库连接（诊断数据库用户问题）
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
            # [FIX] 增加超时到300秒（5分钟），首次构建需要更长时间
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
            
            # [CHECK] 验证容器是否真的在运行
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
            
            # [BEST PRACTICE] 现代化Docker最佳实践：等待后端服务健康检查通过（容器运行 != 服务就绪）
            safe_print("  [等待] 后端服务健康检查...")
            max_health_retries = 30  # 最多等待5分钟（30 * 10秒）
            backend_healthy = False
            log_check_interval = 10  # 每10次重试（100秒）显示一次容器日志
            
            for i in range(max_health_retries):
                # [IMPROVE] 改进：定期检查容器日志，及早发现启动失败
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
            # [FIX] 增加超时到300秒（5分钟）
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
            
            # [CHECK] 验证Celery Worker容器是否真的在运行
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

def _can_bind_local_port(port, host="127.0.0.1"):
    """检查当前用户是否能在本机绑定指定端口。"""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _choose_local_backend_port(preferred_port=BACKEND_PORT, fallback_ports=None):
    """为本地后端选择可绑定端口，优先默认端口，失败时回退。"""
    candidates = [preferred_port]
    if fallback_ports is None:
        candidates.extend([18001, 18011, 18021, 18031, 18041])
    else:
        candidates.extend(fallback_ports)

    for port in candidates:
        if _can_bind_local_port(port):
            return port
    return None


def _select_preferred_nvm_npm(preferred_major):
    """优先从 nvm 目录中选择与 .nvmrc 匹配的 npm。"""
    if not preferred_major or sys_platform.system() != "Windows":
        return None

    search_roots = []
    nvm_home = os.environ.get("NVM_HOME", "").rstrip("\\")
    if nvm_home:
        search_roots.append(nvm_home)

    appdata = os.path.expandvars(r"%APPDATA%")
    if appdata:
        default_root = os.path.join(appdata, "nvm")
        if default_root not in search_roots:
            search_roots.append(default_root)

    for root in search_roots:
        if not root or not os.path.isdir(root):
            continue
        versions = [
            name
            for name in os.listdir(root)
            if name.startswith("v") and os.path.isdir(os.path.join(root, name))
        ]
        matching = [
            name for name in versions if name.lstrip("v").split(".")[0] == preferred_major
        ]
        for version_name in sorted(matching, reverse=True):
            npm_cmd = os.path.join(root, version_name, "npm.cmd")
            if os.path.isfile(npm_cmd):
                return os.path.normpath(npm_cmd)
    return None


def _resolve_npm_path():
    """解析 npm 路径，Windows 下优先遵循 .nvmrc 指定主版本。"""
    project_root = Path(__file__).resolve().parent
    preferred_major = _read_nvmrc_version(project_root)

    preferred_npm = _select_preferred_nvm_npm(preferred_major)
    if preferred_npm:
        return preferred_npm

    npm_exe = shutil.which("npm")
    if sys_platform.system() == "Windows" and not npm_exe:
        npm_exe = shutil.which("npm.cmd")
    if npm_exe:
        return npm_exe

    if sys_platform.system() == "Windows":
        if os.environ.get("NVM_SYMLINK"):
            symlink = os.environ.get("NVM_SYMLINK", "").rstrip("\\")
            npm_cmd = os.path.join(symlink, "npm.cmd")
            if os.path.isfile(npm_cmd):
                return os.path.normpath(npm_cmd)

        for candidate_dir in [
            os.path.expandvars(r"%ProgramFiles%\nodejs"),
            os.path.expandvars(r"%ProgramFiles(x86)%\nodejs"),
            os.path.expandvars(r"%APPDATA%\npm"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\node"),
        ]:
            if not candidate_dir:
                continue
            npm_cmd = os.path.join(candidate_dir, "npm.cmd")
            if os.path.isfile(npm_cmd):
                return os.path.normpath(npm_cmd)

    return None


def _frontend_has_cli_dependency(frontend_dir, package_name):
    """检查前端关键 CLI 依赖是否已正确安装，避免空 node_modules 误判为可启动。"""
    package_dir = frontend_dir / "node_modules" / package_name
    if package_dir.is_dir():
        return True

    bin_dir = frontend_dir / "node_modules" / ".bin"
    candidates = [package_name, f"{package_name}.cmd", f"{package_name}.ps1"]
    return any((bin_dir / candidate).exists() for candidate in candidates)


def start_backend():
    """启动本地后端服务。"""
    safe_print("\n[启动] 后端服务...")
    safe_print(f"  地址: http://localhost:{ACTIVE_BACKEND_PORT}")
    safe_print(f"  文档: http://localhost:{ACTIVE_BACKEND_PORT}/api/docs")

    project_root = Path(__file__).parent
    if not _require_local_port_available(ACTIVE_BACKEND_PORT, "后端服务"):
        return None

    if sys_platform.system() == "Windows":
        work_dir = str(project_root.resolve())
        work_dir_ps = work_dir.replace("'", "''")
        inner_cmd = (
            "`$env:PYTHONPATH='{}'; python -m uvicorn backend.main:app "
            "--host 127.0.0.1 --port {} --loop asyncio"
        ).format(work_dir_ps, ACTIVE_BACKEND_PORT)
        cmd = (
            'Start-Process powershell -ArgumentList "-NoExit", "-Command", "{}" '
            '-WorkingDirectory "{}"'
        ).format(inner_cmd.replace('"', '`"'), work_dir.replace('"', '`"'))

        process = subprocess.Popen(
            ["powershell", "-Command", cmd],
            shell=True,
            cwd=project_root,
        )
        safe_print("  [OK] 后端服务已在新窗口启动")
        safe_print("  提示: 查看新打开的 PowerShell 窗口获取详细日志")
        return process

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            str(ACTIVE_BACKEND_PORT),
            "--reload",
        ],
        cwd=project_root,
    )
    safe_print("  [OK] 后端服务已启动")
    return process


def start_frontend():
    """启动本地前端服务。"""
    safe_print("\n[启动] 前端服务...")
    safe_print(f"  地址: http://localhost:{FRONTEND_PORT}")

    frontend_dir = Path(__file__).parent / "frontend"
    if not (frontend_dir / "package.json").exists():
        safe_print("  [ERROR] 未找到 frontend/package.json，请确认项目结构完整")
        return None
    if not (frontend_dir / "node_modules").is_dir():
        safe_print("  [ERROR] frontend/node_modules 不存在，请先在 frontend 目录执行: npm install")
        return None
    if not _frontend_has_cli_dependency(frontend_dir, "vite"):
        safe_print("  [ERROR] frontend/node_modules 不完整，缺少 vite 依赖")
        safe_print("  提示: 请在 frontend 目录重新执行: npm install")
        return None
    if not _require_local_port_available(FRONTEND_PORT, "前端服务"):
        safe_print("  提示: 当前前端使用 strictPort=true，不会自动切换到 5174/5175")
        return None

    npm_exe = _resolve_npm_path()
    if not npm_exe:
        safe_print("  [ERROR] 未找到 npm。请确保已安装 Node.js 并加入 PATH")
        safe_print("  提示: 仓库要求 Node >= 24，且优先匹配 .nvmrc")
        return None

    safe_print("  [INFO] 使用 npm: " + npm_exe)

    if sys_platform.system() == "Windows":
        frontend_path = str(frontend_dir.resolve())
        node_bin_dir = os.path.dirname(npm_exe)
        env = os.environ.copy()
        env["Path"] = node_bin_dir + os.pathsep + env.get("Path", env.get("PATH", ""))
        env["VITE_DEV_PROXY_TARGET"] = f"http://127.0.0.1:{ACTIVE_BACKEND_PORT}"
        create_new_console = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        process = subprocess.Popen(
            [npm_exe, "run", "dev"],
            cwd=frontend_path,
            env=env,
            shell=False,
            creationflags=create_new_console,
        )
        safe_print("  [OK] 前端服务已在新窗口启动")
        safe_print("  [INFO] Vite 使用 strictPort=true，固定监听 5173")
        return process

    env = os.environ.copy()
    env["VITE_DEV_PROXY_TARGET"] = f"http://127.0.0.1:{ACTIVE_BACKEND_PORT}"
    process = subprocess.Popen([npm_exe, "run", "dev"], cwd=frontend_dir, env=env)
    safe_print("  [OK] 前端服务已启动")
    return process


def ensure_postgres_redis_docker(project_root, with_celery=True):
    """本地模式下启动并等待 Postgres/Redis/Celery Docker 基础设施就绪。"""
    safe_print(
        "\n[本地模式] 使用 Docker 启动 Postgres、Redis"
        + (" 与 Celery Worker" if with_celery else "")
        + "..."
    )
    if not pre_flight_check_docker(project_root):
        return False

    compose_base = project_root / "docker-compose.yml"
    compose_dev = project_root / "docker-compose.dev.yml"
    if not compose_base.exists():
        safe_print("  [ERROR] docker-compose.yml 不存在")
        return False

    compose_files = ["-f", str(compose_base)]
    if compose_dev.exists():
        compose_files.extend(["-f", str(compose_dev)])

    profiles = ["--profile", "dev"]
    if with_celery:
        profiles.extend(["--profile", "dev-full"])

    services = ["redis", "postgres"]
    required_names = ["xihong_erp_postgres", "xihong_erp_redis"]
    if with_celery:
        services.append("celery-worker")
        required_names.append("xihong_erp_celery_worker")

    try:
        ps_result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="ignore",
            cwd=project_root,
        )
        if ps_result.returncode == 0:
            running_names = {
                line.strip()
                for line in (ps_result.stdout or "").splitlines()
                if line.strip()
            }
            if set(required_names).issubset(running_names):
                if _wait_for_local_docker_infra(required_names, max_wait=5):
                    safe_print("  [OK] 复用已运行且健康的本地 Docker 基础服务")
                    return True
                safe_print("  [WARNING] 已有容器存在但未就绪，将尝试重新拉起并等待健康检查")
    except Exception as exc:
        safe_print(f"  [WARNING] 检查已有 Docker 基础服务失败，将尝试直接启动: {exc}")

    try:
        safe_print("  [启动] " + ", ".join(services) + "...")
        cmd = ["docker-compose"] + compose_files + profiles + ["up", "-d"] + services
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
            errors="ignore",
        )
        if result.returncode != 0:
            error_msg = (result.stderr or result.stdout or "未知错误")[:300]
            safe_print(f"  [ERROR] 启动失败: {error_msg}")
            return False

        if not _wait_for_local_docker_infra(required_names, max_wait=60):
            return False

        postgres_user = os.getenv("POSTGRES_USER", "erp_user")
        postgres_db = os.getenv("POSTGRES_DB", "xihong_erp")
        safe_print("  [检查] PostgreSQL 连接...")
        probe = subprocess.run(
            [
                "docker",
                "exec",
                "xihong_erp_postgres",
                "psql",
                "-U",
                postgres_user,
                "-d",
                postgres_db,
                "-c",
                "SELECT 1",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="ignore",
        )
        if probe.returncode != 0:
            safe_print("  [ERROR] PostgreSQL 连接测试失败，本机后端无法继续启动")
            return False

        safe_print("  [OK] PostgreSQL 连接正常")
        if with_celery:
            safe_print("  [OK] Celery Worker 使用 Docker 容器，与本机无时钟漂移")
        return True
    except Exception as exc:
        safe_print(f"  [ERROR] 启动本地 Docker 基础服务异常: {exc}")
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


def wait_for_frontend_port(port=FRONTEND_PORT, max_wait=15):
    """等待前端 Vite 在固定端口就绪。"""
    import socket

    safe_print("\n[等待] 前端界面服务启动中...")
    for i in range(max_wait):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                safe_print(f"  [OK] 前端界面已就绪 (端口 {port}, {i + 1}秒)")
                return port
        finally:
            sock.close()

        if (i + 1) % 5 == 0:
            safe_print(f"  等待中... {i + 1}/{max_wait}秒")
        time.sleep(1)

    safe_print("  [ERROR] 前端界面启动超时")
    return None


def _prompt_continue_without_celery():
    """Redis 不可用时，交互式确认是否继续。非交互环境默认继续并禁用 Celery。"""
    if not getattr(sys.stdin, "isatty", lambda: False)():
        safe_print("  [INFO] 非交互环境，自动以 --no-celery 继续")
        return True

    choice = input("\n是否继续启动（不启动Celery worker）? (y/n): ").strip().lower()
    return choice == "y"


def main():
    """主函数。"""
    global ACTIVE_BACKEND_PORT

    parser = argparse.ArgumentParser(description="西虹ERP系统启动脚本（修复版）")
    parser.add_argument("--backend-only", action="store_true", help="仅启动后端")
    parser.add_argument("--frontend-only", action="store_true", help="仅启动前端")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--no-celery", action="store_true", help="不启动Celery worker")
    parser.add_argument("--use-docker", action="store_true", help="使用Docker Compose启动服务")
    parser.add_argument(
        "--collection",
        action="store_true",
        help="采集模式：与 --use-docker 同时使用时，backend 使用带 Playwright 的镜像",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="一键本地开发：Docker 启动 Postgres/Redis/Celery，本机启动后端与前端",
    )
    args = parser.parse_args()

    print_banner()
    project_root = Path(__file__).resolve().parent
    warn_legacy_shop_session_artifacts(project_root)

    if args.local and not args.use_docker and not args.frontend_only:
        safe_print("\n[模式] 一键本地开发（Docker Postgres/Redis/Celery + 本机后端/前端）")
        if not ensure_postgres_redis_docker(project_root, with_celery=True):
            safe_print("\n[ERROR] Docker 基础服务启动失败，请检查 Docker 与 compose 配置")
            raise SystemExit(1)
        args.no_celery = True
        safe_print("  [OK] 数据库、Redis 与 Celery 已就绪，接下来启动本机后端与前端...\n")

    if args.use_docker:
        safe_print("\n[模式] Docker Compose 模式（统一管理服务）")
        if not args.frontend_only:
            docker_success = start_services_with_docker_compose(
                use_collection=args.collection,
            )
            if not docker_success:
                safe_print("\n[ERROR] Docker Compose 启动失败")
                raise SystemExit(1)

            if not ensure_postgresql_dashboard_assets(project_root):
                safe_print("\n[ERROR] PostgreSQL Dashboard 资产检查失败")
                raise SystemExit(1)

            args.no_celery = True
            safe_print("\n[提示] 后端 API 和 Celery Worker 已在 Docker 容器中运行")

    if not args.use_docker and not args.frontend_only and not check_postgresql():
        safe_print("\n[ERROR] 请先启动 PostgreSQL")
        raise SystemExit(1)

    redis_available = False
    if not args.use_docker and not args.no_celery and not args.frontend_only:
        redis_available = check_redis()
        if not redis_available:
            safe_print("\n[WARNING] Redis 不可用，Celery worker 无法启动")
            safe_print("  选项1: 启动 Redis 后重新运行脚本")
            safe_print("  选项2: 使用 --use-docker")
            safe_print("  选项3: 使用 --no-celery")
            if not _prompt_continue_without_celery():
                safe_print("[退出] 用户取消启动")
                raise SystemExit(0)
            args.no_celery = True

    if args.local:
        os.environ["ENVIRONMENT"] = "development"

    backend_port = BACKEND_PORT
    if not args.frontend_only and not args.use_docker:
        chosen_backend_port = _choose_local_backend_port(BACKEND_PORT)
        if chosen_backend_port is None:
            safe_print("\n[ERROR] 未找到可用于本地后端的可绑定端口")
            raise SystemExit(1)
        backend_port = chosen_backend_port
        ACTIVE_BACKEND_PORT = chosen_backend_port
        if backend_port != BACKEND_PORT:
            safe_print(
                f"\n[提示] 默认后端端口 {BACKEND_PORT} 在当前 Windows 环境不可绑定，"
                f"已回退到 {backend_port}"
            )
    else:
        ACTIVE_BACKEND_PORT = BACKEND_PORT

    processes = []

    try:
        if not args.frontend_only and not args.use_docker:
            if not ensure_postgresql_dashboard_assets(project_root):
                safe_print("\n[ERROR] PostgreSQL Dashboard 资产检查失败")
                raise SystemExit(1)

            backend_process = start_backend()
            if backend_process is None:
                safe_print("\n[ERROR] 后端服务未启动")
                raise SystemExit(1)
            processes.append(("backend", backend_process))

            time.sleep(2)
            if wait_for_service(backend_port, "后端API", 20):
                safe_print("  [OK] 后端API就绪")
            else:
                safe_print("  [ERROR] 后端启动失败，请查看后端窗口日志")
                raise SystemExit(1)
        elif args.use_docker and not args.frontend_only:
            safe_print("\n[等待] 后端 API 容器启动中...")
            if wait_for_service(backend_port, "后端API容器", 30):
                safe_print("  [OK] 后端 API 容器已就绪")
            else:
                safe_print("  [ERROR] 后端容器未就绪，请检查 Docker 日志")
                raise SystemExit(1)

        celery_process = None
        if not args.use_docker and not args.no_celery and not args.frontend_only:
            if redis_available:
                celery_process = start_celery_worker()
                processes.append(("celery", celery_process))
                time.sleep(3)
            else:
                safe_print("\n[SKIP] 跳过 Celery Worker（Redis 不可用）")

        frontend_port = None
        if not args.backend_only:
            frontend_process = start_frontend()
            if frontend_process is None:
                safe_print("  [ERROR] 前端服务未启动")
                raise SystemExit(1)
            processes.append(("frontend", frontend_process))
            frontend_port = wait_for_frontend_port()
            if frontend_port is None:
                safe_print("  [ERROR] 前端服务启动失败，请查看前端窗口日志")
                raise SystemExit(1)

        safe_print("\n" + "=" * 80)
        safe_print("[成功] 系统启动成功")
        safe_print("=" * 80)

        if not args.frontend_only:
            safe_print(f"[后端] API文档:  http://localhost:{backend_port}/api/docs")
            safe_print(f"[后端] 健康检查: http://localhost:{backend_port}/health")

        if args.use_docker or args.local:
            safe_print("[任务] Celery Worker已启动（Docker容器，处理数据同步任务）")
            safe_print("       查看日志: docker-compose -f docker-compose.yml -f docker-compose.dev.yml logs -f celery-worker")
        elif celery_process:
            safe_print("[任务] Celery Worker已启动（处理数据同步任务）")

        if not args.backend_only:
            safe_print(f"[前端] 主界面:   http://localhost:{frontend_port}")

        safe_print("=" * 80)

        if not args.no_browser and not args.backend_only:
            safe_print("\n[浏览器] 5秒后自动打开...")
            time.sleep(5)
            webbrowser.open(f"http://localhost:{frontend_port}")
            safe_print("[OK] 浏览器已打开")

        safe_print("\n[监控] 系统监控中... (按 Ctrl+C 退出监控)\n")
        while True:
            time.sleep(10)
            if not args.frontend_only and not _is_port_in_use(backend_port):
                safe_print("[WARNING] 后端服务似乎已停止")
                break

    except KeyboardInterrupt:
        safe_print("\n\n[退出] 监控脚本已退出")
        safe_print("[提示] 后端、前端和 Celery Worker 服务仍在独立窗口运行")
    except SystemExit:
        raise
    except Exception as exc:
        safe_print(f"\n[ERROR] 启动失败: {exc}")
        import traceback

        traceback.print_exc()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
