"""
配置文件 - 西虹ERP系统后端配置管理
"""

from typing import List
import os

from backend.utils.project_env import TEST_ENV_GUARD_VAR, is_test_env_guarded


#: 测试期使用的隔离库(**兜底**地址)。
#:
#: 为什么不是 SQLite: 本项目的表分布在 PG 的 schema 命名空间里
#: (``core`` / ``a_class`` / ...), SQLite 没有 schema 概念,
#: ``CREATE TABLE core.xxx`` 直接报 "unknown database core"。
#: 详见 ``backend.utils.project_env.isolated_database_url`` 的说明。
#:
#: 真正的地址由 ``backend/tests/conftest.py`` 在 pytest 启动时起一个**一次性
#: PostgreSQL 容器**并写入 ``XIHONG_TEST_DATABASE_URL``;
#: 这个常量只是「环境变量缺失时的兜底」——
#: 它指向一个不存在的服务, 也就是说护栏一旦失效就是**连不上**,
#: 而不是**连上真实库**(fail-closed)。
_TEST_ISOLATED_DATABASE_URL = "postgresql://test:test@127.0.0.1:15445/test"


class Settings:
    """应用配置"""
    
    def __init__(self):
        """初始化配置并进行安全检查"""
        # 生产环境强制检查
        env_mode = os.getenv("ENVIRONMENT", "development")
        if env_mode == "production":
            # 生产环境必须设置自定义密钥
            if self.JWT_SECRET_KEY == "xihong-erp-jwt-secret-2025":
                raise RuntimeError(
                    "生产环境禁止使用默认JWT密钥！\n"
                    "请设置环境变量: export JWT_SECRET_KEY='your-secure-random-key'"
                )
            if self.SECRET_KEY == "xihong-erp-secret-key-2025":
                raise RuntimeError(
                    "生产环境禁止使用默认SECRET密钥！\n"
                    "请设置环境变量: export SECRET_KEY='your-secure-random-key'"
                )
    
    # 应用基本配置
    APP_NAME: str = "西虹ERP系统API"
    VERSION: str = "4.0.0"
    DEBUG: bool = False
    
    # 服务器配置
    HOST: str = os.getenv("HOST", "127.0.0.1")  # Windows开发环境使用127.0.0.1避免权限问题
    PORT: int = int(os.getenv("PORT", "8001"))  # 后端API端口
    
    # 数据库配置
    # 支持环境变量切换数据库
    # 开发环境: SQLite
    # 生产环境: PostgreSQL
    #
    # [*] 测试期护栏: 强制隔离库, 无视 .env / 环境变量里的 DATABASE_URL。
    # 详见本模块顶部 TEST_ENV_GUARD_VAR 的说明 ——
    # 测试连上真实业务库曾经把 21 个真实文件的入库状态改坏过。
    # 护栏开启时**只认** ``XIHONG_TEST_DATABASE_URL``(由 conftest 写入),
    # 连环境变量里的 ``DATABASE_URL`` 都不采信 —— 否则改一下环境变量
    # 就能把测试指回真实业务库。
    DATABASE_URL: str = (
        os.getenv(
            "XIHONG_TEST_DATABASE_URL",
            _TEST_ISOLATED_DATABASE_URL,
        )
        if is_test_env_guarded()
        else os.getenv(
            "DATABASE_URL",
            # 默认使用PostgreSQL(如果Docker运行)
            # 使用5433端口避免与本地PostgreSQL冲突
            "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp"
            # 回退到SQLite
            # "sqlite:///F:/Vscode/python_programme/AI_code/xihong_erp/data/erp_system.db"
        )
    )
    DATABASE_ECHO: bool = os.getenv("DATABASE_ECHO", "false").lower() == "true"
    
    # PostgreSQL专用配置
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "15432"))  # 使用15432避开Windows保留端口范围
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "erp_user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "erp_pass_2025")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "xihong_erp")
    
    # 数据库连接池配置(v4.1.0优化 - 企业级配置)
    # v4.19.0更新:环境感知的资源配置
    _cpu_cores = os.cpu_count() or 4
    _env = os.getenv("ENVIRONMENT", "development")
    
    # 执行器配置(v4.19.0新增)
    # CPU进程池:业界常用做法(CPU核心数 - 1,为主进程预留1核)
    # 环境变量优先,支持Docker容器手动设置
    _cpu_workers_env = os.getenv("CPU_EXECUTOR_WORKERS")
    if _cpu_workers_env is not None:
        try:
            _cpu_workers = int(_cpu_workers_env)
            CPU_EXECUTOR_WORKERS = _cpu_workers if _cpu_workers > 0 else max(1, min(4, _cpu_cores - 1))
        except ValueError:
            CPU_EXECUTOR_WORKERS = max(1, min(4, _cpu_cores - 1))
    else:
        CPU_EXECUTOR_WORKERS = max(1, min(4, _cpu_cores - 1))
    
    # I/O线程池:min(CPU核心数 * 5, 20)
    _io_workers_env = os.getenv("IO_EXECUTOR_WORKERS")
    if _io_workers_env is not None:
        try:
            _io_workers = int(_io_workers_env)
            IO_EXECUTOR_WORKERS = _io_workers if _io_workers > 0 else min(max(_cpu_cores * 2, 4), 8)
        except ValueError:
            IO_EXECUTOR_WORKERS = min(max(_cpu_cores * 2, 4), 8)
    else:
        IO_EXECUTOR_WORKERS = min(max(_cpu_cores * 2, 4), 8)
    
    # 数据库连接池:根据环境自动调整
    if _env == "production":
        # 生产环境:根据CPU核心数动态计算
        DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", str(min(30, _cpu_cores * 10))))
        DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", str(min(20, _cpu_cores * 5))))
        DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", str(min(max(_cpu_cores * 2, 4), 8))))
        DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", str(min(max(_cpu_cores * 2, 2), 8))))
    else:
        # 开发环境:使用较小值(节省数据库资源)
        DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
        DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "60"))  # 连接超时60秒
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "1800")) # 连接回收30分钟(避免长连接问题)

    # ── 超时预算对齐(2026-10-30)────────────────────────────────
    # 背景:前端 axios 超时(frontend/src/api/index.js 的 TIMEOUTS)必须**大于**后端
    # DB statement_timeout。否则前端先放弃(报"网络连接失败"),后端 SQL 还在跑,
    # 拖住事件循环与连接池 —— 这就是"超时预算倒置"。
    # 规则:DB statement_timeout < 前端 axios 超时,中间留出响应组装与序列化的余量。
    # 详见 docs/architecture/SYNC_MODULE_REFACTOR_PLAN.md 第 4 批。
    #
    # Dashboard 家族的 DB 预算(前端 /dashboard/* 是 70s,这里留 10s 余量)。
    DB_STATEMENT_TIMEOUT_MS: int = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "60000"))
    # 请求级 DB 超时预算(毫秒):按请求路径片段匹配。
    # 键顺序 = 前端 URL 匹配的判定顺序(frontend/src/api/index.js)。
    # 规则:每个值必须**严格小于**该路径在前端的 axios 超时。
    REQUEST_STATEMENT_TIMEOUT_MS: dict[str, int] = {
        # 前端 120s;耗时主要是 Excel 表头解析(纯 IO),DB 侧只有几次目录查询
        "/governance/detailed-coverage": int(os.getenv("DB_TIMEOUT_GOVERNANCE_MS", "60000")),
        # 前端 120s
        "/scan": int(os.getenv("DB_TIMEOUT_SCAN_MS", "60000")),
        # 前端 60s
        "/preview": int(os.getenv("DB_TIMEOUT_PREVIEW_MS", "50000")),
        # 前端 180s
        "/ingest": int(os.getenv("DB_TIMEOUT_INGEST_MS", "170000")),
        # 前端 70s
        "/dashboard": DB_STATEMENT_TIMEOUT_MS,
        # 前端 300s
        "/collection": int(os.getenv("DB_TIMEOUT_COLLECTION_MS", "290000")),
        # 前端 90s
        "/mapping": int(os.getenv("DB_TIMEOUT_MAPPING_MS", "80000")),
        # 前端 60s
        "/data-sync/batch": int(os.getenv("DB_TIMEOUT_DATA_SYNC_BATCH_MS", "50000")),
        # 前端 120s
        "/data-sync/single": int(os.getenv("DB_TIMEOUT_DATA_SYNC_SINGLE_MS", "110000")),
    }
    # 普通接口:前端 axios 默认 30s,DB 留 5s 余量
    DB_REQUEST_STATEMENT_TIMEOUT_MS: int = int(
        os.getenv("DB_REQUEST_STATEMENT_TIMEOUT_MS", "25000")
    )
    # 连接池级默认值:保持 120s。Celery/后台批量采集导入直接用 AsyncSessionLocal(),
    # 不经过请求级预算;把连接池默认值全局砍到 60s 会打断这些长事务与批量任务。
    DB_POOL_STATEMENT_TIMEOUT_MS: int = int(os.getenv("DB_POOL_STATEMENT_TIMEOUT_MS", "120000"))
    # 批量采集/导入长任务专用预算:0 = 不限制(显式保留/可按环境放宽)。
    DB_BATCH_STATEMENT_TIMEOUT_MS: int = int(os.getenv("DB_BATCH_STATEMENT_TIMEOUT_MS", "0"))
    # 事务空闲超时(沿用原值)
    DB_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS: int = int(
        os.getenv("DB_IDLE_IN_TRANSACTION_SESSION_TIMEOUT_MS", "120000")
    )

    # 安全配置
    SECRET_KEY: str = os.getenv("SECRET_KEY", "xihong-erp-secret-key-2025")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "xihong-erp-jwt-secret-2025")
    JWT_ALGORITHM: str = "HS256"
    # [*] v6.0.0更新:Access Token 过期时间(开发/生产统一为 1 小时，减少工作被打断)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    REFRESH_TOKEN_ROTATION_GRACE_SECONDS: int = int(os.getenv("REFRESH_TOKEN_ROTATION_GRACE_SECONDS", "30"))
    
    # CORS配置
    # [*] 从环境变量读取 ALLOWED_ORIGINS(支持逗号分隔的多个值)
    # 如果环境变量未设置,使用开发环境的默认值(兼容性)
    _allowed_origins_str = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8080,http://localhost:5173,http://localhost:5174,http://127.0.0.1:8080,http://127.0.0.1:5173,http://127.0.0.1:5174,http://localhost:8001,http://127.0.0.1:8001"
    )
    ALLOWED_ORIGINS: List[str] = [o.strip() for o in _allowed_origins_str.split(",") if o.strip()]
    
    # [*] 从环境变量读取 ALLOWED_HOSTS(支持逗号分隔的多个值)
    _allowed_hosts_str = os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1")
    ALLOWED_HOSTS: List[str] = [h.strip() for h in _allowed_hosts_str.split(",") if h.strip()]
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/backend.log"
    
    # 文件存储配置
    UPLOAD_DIR: str = "uploads"
    TEMP_DIR: str = "temp"
    
    # Redis配置(可选)
    # [*] v4.19.5 新增:支持 Redis 密码配置
    # 优先级:REDIS_URL > (REDIS_HOST + REDIS_PORT + REDIS_PASSWORD)
    _redis_url = os.getenv("REDIS_URL")
    if _redis_url:
        REDIS_URL: str = _redis_url
    else:
        # 从独立配置构建 Redis URL
        _redis_host = os.getenv("REDIS_HOST", "localhost")
        _redis_port = os.getenv("REDIS_PORT", "6379")
        _redis_password = os.getenv("REDIS_PASSWORD", "")
        _redis_db = os.getenv("REDIS_DB", "0")
        
        if _redis_password:
            # 带密码的 Redis URL 格式:redis://:password@host:port/db
            REDIS_URL: str = f"redis://:{_redis_password}@{_redis_host}:{_redis_port}/{_redis_db}"
        else:
            # 无密码的 Redis URL 格式:redis://host:port/db
            REDIS_URL: str = f"redis://{_redis_host}:{_redis_port}/{_redis_db}"
    
    REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "true").lower() == "true"
    
    # 外部服务配置
    PLAYWRIGHT_BROWSER_PATH: str = ""
    
    # v4.7.0: Playwright浏览器配置(环境感知)
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")  # development/production
    PLAYWRIGHT_HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"
    PLAYWRIGHT_SLOW_MO: int = int(os.getenv("PLAYWRIGHT_SLOW_MO", "0"))
    
    @property
    def rate_limit_storage_uri(self) -> str:
        """
        获取限流器存储URI(环境感知)
        
        [*] v4.19.5 新增:限流器存储配置
        
        策略:
        - 生产环境:强制使用 Redis(分布式、高性能)
        - 开发环境:优先使用 Redis,如果不可用则降级到内存存储
        
        Returns:
            str: 存储URI(redis://... 或 memory://)
        """
        if self.ENVIRONMENT == "production":
            # 生产环境强制使用 Redis
            if not self.REDIS_ENABLED:
                raise RuntimeError("生产环境必须启用 Redis 作为限流器存储(设置 REDIS_ENABLED=true)")
            return self.REDIS_URL
        
        # 开发环境:优先使用 Redis,降级到内存
        if self.REDIS_ENABLED:
            try:
                # 测试 Redis 连接(同步检查,避免阻塞)
                import redis
                r = redis.from_url(self.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
                r.ping()
                r.close()
                return self.REDIS_URL
            except Exception:
                # Redis 不可用,降级到内存存储
                # 注意:这里不记录日志,因为可能在 Settings 初始化时调用
                # 日志会在 rate_limiter.py 中记录
                return "memory://"
        
        return "memory://"
    
    @property
    def browser_config(self) -> dict:
        """
        环境感知的浏览器配置(v4.7.0)
        
        自动根据环境返回合适的浏览器配置:
        - 开发环境:默认有头模式(headless=false, slow_mo=100)便于观察
        - 生产环境:自动无头模式(headless=true, slow_mo=0)适合Docker
        
        Returns:
            dict: Playwright browser.launch() 参数
        """
        if self.ENVIRONMENT == "production":
            # 生产环境:无头模式 + 安全参数
            return {
                'headless': True,
                'slow_mo': 0,
                'args': [
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',  # Docker容器共享内存限制
                    '--disable-blink-features=AutomationControlled',  # 反检测
                ]
            }
        else:
            # 开发环境:根据环境变量或默认有头模式
            return {
                'headless': self.PLAYWRIGHT_HEADLESS,
                'slow_mo': self.PLAYWRIGHT_SLOW_MO if self.PLAYWRIGHT_SLOW_MO > 0 else 100,
                'args': []
            }

def get_settings() -> Settings:
    """获取配置实例"""
    return Settings()
