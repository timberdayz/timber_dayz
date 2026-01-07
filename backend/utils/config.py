"""
配置文件 - 西虹ERP系统后端配置管理
"""

from typing import List
import os

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
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        # 默认使用PostgreSQL（如果Docker运行）
        # 使用5433端口避免与本地PostgreSQL冲突
        "postgresql://erp_user:erp_pass_2025@localhost:15432/xihong_erp"
        # 回退到SQLite
        # "sqlite:///F:/Vscode/python_programme/AI_code/xihong_erp/data/erp_system.db"
    )
    DATABASE_ECHO: bool = os.getenv("DATABASE_ECHO", "false").lower() == "true"
    
    # PostgreSQL专用配置
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: int = int(os.getenv("POSTGRES_PORT", "15432"))  # 使用15432避开Windows保留端口范围
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "erp_user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "erp_pass_2025")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "xihong_erp")
    
    # 数据库连接池配置（v4.1.0优化 - 企业级配置）
    # v4.19.0更新：环境感知的资源配置
    _cpu_cores = os.cpu_count() or 4
    _env = os.getenv("ENVIRONMENT", "development")
    
    # 执行器配置（v4.19.0新增）
    # CPU进程池：业界常用做法（CPU核心数 - 1，为主进程预留1核）
    # 环境变量优先，支持Docker容器手动设置
    _cpu_workers_env = os.getenv("CPU_EXECUTOR_WORKERS")
    if _cpu_workers_env is not None:
        try:
            _cpu_workers = int(_cpu_workers_env)
            CPU_EXECUTOR_WORKERS = _cpu_workers if _cpu_workers > 0 else max(1, _cpu_cores - 1)
        except ValueError:
            CPU_EXECUTOR_WORKERS = max(1, _cpu_cores - 1)
    else:
        CPU_EXECUTOR_WORKERS = max(1, _cpu_cores - 1)
    
    # I/O线程池：min(CPU核心数 * 5, 20)
    _io_workers_env = os.getenv("IO_EXECUTOR_WORKERS")
    if _io_workers_env is not None:
        try:
            _io_workers = int(_io_workers_env)
            IO_EXECUTOR_WORKERS = _io_workers if _io_workers > 0 else min(_cpu_cores * 5, 20)
        except ValueError:
            IO_EXECUTOR_WORKERS = min(_cpu_cores * 5, 20)
    else:
        IO_EXECUTOR_WORKERS = min(_cpu_cores * 5, 20)
    
    # 数据库连接池：根据环境自动调整
    if _env == "production":
        # 生产环境：根据CPU核心数动态计算
        DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", str(min(30, _cpu_cores * 10))))
        DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", str(min(20, _cpu_cores * 5))))
    else:
        # 开发环境：使用较小值（节省数据库资源）
        DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
        DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "60"))  # 连接超时60秒
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "1800")) # 连接回收30分钟（避免长连接问题）
    
    # 安全配置
    SECRET_KEY: str = os.getenv("SECRET_KEY", "xihong-erp-secret-key-2025")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "xihong-erp-jwt-secret-2025")
    JWT_ALGORITHM: str = "HS256"
    # ⭐ v6.0.0更新：缩短 Access Token 过期时间（Phase 4: 优化 Token 过期时间）
    # 从 30 分钟缩短到 15 分钟，提升安全性（token 泄露后有效期更短）
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
    
    # CORS配置
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:8080",  # Metabase端口（从3000改为8080，避免Windows端口权限问题）
        "http://localhost:5173",
        "http://localhost:5174",  # 前端端口
        "http://127.0.0.1:8080",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost:8001",  # 后端端口（用于Swagger UI）
        "http://127.0.0.1:8001"
    ]
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1"]
    
    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/backend.log"
    
    # 文件存储配置
    UPLOAD_DIR: str = "uploads"
    TEMP_DIR: str = "temp"
    
    # Redis配置（可选）
    # ⭐ v4.19.5 新增：支持 Redis 密码配置
    # 优先级：REDIS_URL > (REDIS_HOST + REDIS_PORT + REDIS_PASSWORD)
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
            # 带密码的 Redis URL 格式：redis://:password@host:port/db
            REDIS_URL: str = f"redis://:{_redis_password}@{_redis_host}:{_redis_port}/{_redis_db}"
        else:
            # 无密码的 Redis URL 格式：redis://host:port/db
            REDIS_URL: str = f"redis://{_redis_host}:{_redis_port}/{_redis_db}"
    
    REDIS_ENABLED: bool = os.getenv("REDIS_ENABLED", "true").lower() == "true"
    
    # 外部服务配置
    PLAYWRIGHT_BROWSER_PATH: str = ""
    
    # v4.7.0: Playwright浏览器配置（环境感知）
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")  # development/production
    PLAYWRIGHT_HEADLESS: bool = os.getenv("PLAYWRIGHT_HEADLESS", "false").lower() == "true"
    PLAYWRIGHT_SLOW_MO: int = int(os.getenv("PLAYWRIGHT_SLOW_MO", "0"))
    
    @property
    def rate_limit_storage_uri(self) -> str:
        """
        获取限流器存储URI（环境感知）
        
        ⭐ v4.19.5 新增：限流器存储配置
        
        策略：
        - 生产环境：强制使用 Redis（分布式、高性能）
        - 开发环境：优先使用 Redis，如果不可用则降级到内存存储
        
        Returns:
            str: 存储URI（redis://... 或 memory://）
        """
        if self.ENVIRONMENT == "production":
            # 生产环境强制使用 Redis
            if not self.REDIS_ENABLED:
                raise RuntimeError("生产环境必须启用 Redis 作为限流器存储（设置 REDIS_ENABLED=true）")
            return self.REDIS_URL
        
        # 开发环境：优先使用 Redis，降级到内存
        if self.REDIS_ENABLED:
            try:
                # 测试 Redis 连接（同步检查，避免阻塞）
                import redis
                r = redis.from_url(self.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
                r.ping()
                r.close()
                return self.REDIS_URL
            except Exception:
                # Redis 不可用，降级到内存存储
                # 注意：这里不记录日志，因为可能在 Settings 初始化时调用
                # 日志会在 rate_limiter.py 中记录
                return "memory://"
        
        return "memory://"
    
    @property
    def browser_config(self) -> dict:
        """
        环境感知的浏览器配置（v4.7.0）
        
        自动根据环境返回合适的浏览器配置：
        - 开发环境：默认有头模式（headless=false, slow_mo=100）便于观察
        - 生产环境：自动无头模式（headless=true, slow_mo=0）适合Docker
        
        Returns:
            dict: Playwright browser.launch() 参数
        """
        if self.ENVIRONMENT == "production":
            # 生产环境：无头模式 + 安全参数
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
            # 开发环境：根据环境变量或默认有头模式
            return {
                'headless': self.PLAYWRIGHT_HEADLESS,
                'slow_mo': self.PLAYWRIGHT_SLOW_MO if self.PLAYWRIGHT_SLOW_MO > 0 else 100,
                'args': []
            }

def get_settings() -> Settings:
    """获取配置实例"""
    return Settings()
