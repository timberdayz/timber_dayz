"""
PostgreSQL PATH管理器
处理本地开发和云端部署的PATH差异
"""
import os
import platform
from pathlib import Path
from typing import Optional


class PostgresPathManager:
    """PostgreSQL PATH智能管理器"""
    
    # 常见PostgreSQL安装路径
    COMMON_PATHS = {
        "windows": [
            r"C:\Program Files\PostgreSQL\18\bin",
            r"C:\Program Files\PostgreSQL\17\bin",
            r"C:\Program Files\PostgreSQL\16\bin",
            r"C:\Program Files\PostgreSQL\15\bin",
            r"C:\PostgreSQL\18\bin",
            r"C:\PostgreSQL\17\bin",
        ],
        "linux": [
            "/usr/pgsql-18/bin",
            "/usr/pgsql-17/bin",
            "/usr/pgsql-16/bin",
            "/usr/pgsql-15/bin",
            "/usr/lib/postgresql/18/bin",
            "/usr/lib/postgresql/17/bin",
            "/usr/lib/postgresql/16/bin",
            "/usr/lib/postgresql/15/bin",
        ],
        "darwin": [  # macOS
            "/Library/PostgreSQL/18/bin",
            "/Library/PostgreSQL/17/bin",
            "/usr/local/pgsql/bin",
            "/opt/homebrew/opt/postgresql@18/bin",
            "/opt/homebrew/opt/postgresql@17/bin",
        ]
    }
    
    @classmethod
    def detect_postgres_path(cls) -> Optional[Path]:
        """
        自动检测PostgreSQL安装路径
        
        优先级:
        1. 环境变量 POSTGRES_BIN_PATH
        2. PATH中已有的psql
        3. 常见安装路径
        
        Returns:
            PostgreSQL bin目录路径，如果未找到返回None
        """
        # 1. 检查环境变量
        custom_path = os.getenv("POSTGRES_BIN_PATH")
        if custom_path and Path(custom_path).exists():
            return Path(custom_path)
        
        # 2. 检查PATH中是否已有psql
        try:
            import shutil
            psql_path = shutil.which("psql")
            if psql_path:
                return Path(psql_path).parent
        except Exception:
            pass
        
        # 3. 检查常见安装路径
        system = platform.system().lower()
        if system == "darwin":
            system = "darwin"
        elif system not in ["windows", "linux"]:
            system = "linux"  # 默认使用Linux路径
        
        for path_str in cls.COMMON_PATHS.get(system, []):
            path = Path(path_str)
            if path.exists():
                # 验证psql是否存在
                psql_exe = path / ("psql.exe" if system == "windows" else "psql")
                if psql_exe.exists():
                    return path
        
        return None
    
    @classmethod
    def ensure_postgres_in_path(cls) -> bool:
        """
        确保PostgreSQL在PATH中
        
        Returns:
            True if PostgreSQL is accessible, False otherwise
        """
        # 检查是否已经在PATH中
        try:
            import shutil
            if shutil.which("psql"):
                return True
        except Exception:
            pass
        
        # 尝试检测并添加到当前进程的PATH
        postgres_path = cls.detect_postgres_path()
        if postgres_path:
            current_path = os.environ.get("PATH", "")
            postgres_path_str = str(postgres_path)
            
            if postgres_path_str not in current_path:
                separator = ";" if platform.system() == "Windows" else ":"
                os.environ["PATH"] = f"{current_path}{separator}{postgres_path_str}"
                print(f"[INFO] Added PostgreSQL to PATH: {postgres_path_str}")
            
            return True
        
        return False
    
    @classmethod
    def get_postgres_bin_path(cls) -> Optional[str]:
        """
        获取PostgreSQL bin目录路径（字符串格式）
        
        Returns:
            PostgreSQL bin目录路径字符串
        """
        path = cls.detect_postgres_path()
        return str(path) if path else None
    
    @classmethod
    def check_psql_available(cls) -> tuple[bool, Optional[str]]:
        """
        检查psql命令是否可用
        
        Returns:
            (is_available, version_info)
        """
        import subprocess
        
        # 确保PATH配置正确
        cls.ensure_postgres_in_path()
        
        try:
            result = subprocess.run(
                ["psql", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, None
        except Exception as e:
            return False, str(e)


def auto_configure_postgres_path():
    """
    自动配置PostgreSQL PATH（在应用启动时调用）
    
    Usage:
        from backend.utils.postgres_path import auto_configure_postgres_path
        auto_configure_postgres_path()
    """
    manager = PostgresPathManager()
    
    if manager.ensure_postgres_in_path():
        is_available, version = manager.check_psql_available()
        if is_available:
            print(f"PostgreSQL configured: {version}")
            return True
        else:
            print(f"PostgreSQL PATH configured but psql not working")
            return False
    else:
        print(f"PostgreSQL not found - database operations may fail")
        print(f"   Please set POSTGRES_BIN_PATH environment variable")
        return False


def safe_print(text):
    """安全打印（处理GBK编码问题）"""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('gbk', errors='ignore').decode('gbk'))


if __name__ == "__main__":
    # 测试脚本
    safe_print("=" * 60)
    safe_print("PostgreSQL PATH Manager - Test")
    safe_print("=" * 60)
    safe_print("")
    
    manager = PostgresPathManager()
    
    safe_print("[1/3] Detecting PostgreSQL installation...")
    postgres_path = manager.detect_postgres_path()
    if postgres_path:
        safe_print(f"[SUCCESS] Found: {postgres_path}")
    else:
        safe_print(f"[FAILED] Not found in common locations")
    
    safe_print("")
    safe_print("[2/3] Checking if psql is accessible...")
    is_available, version = manager.check_psql_available()
    if is_available:
        safe_print(f"[SUCCESS] psql available: {version}")
    else:
        safe_print(f"[FAILED] psql not accessible: {version}")
    
    safe_print("")
    safe_print("[3/3] Ensuring PostgreSQL in PATH...")
    if manager.ensure_postgres_in_path():
        safe_print(f"[SUCCESS] PostgreSQL PATH configured")
        safe_print(f"   Path: {manager.get_postgres_bin_path()}")
    else:
        safe_print(f"[FAILED] Failed to configure PostgreSQL PATH")
    
    safe_print("")
    safe_print("=" * 60)

