# 开发环境准备清单

## 🎯 目标

确保开发环境完整，所有依赖安装正确，能够顺利开始Day 1开发。

## ✅ 环境检查清单

### 1. Python环境
```bash
# 检查Python版本（需要≥3.8）
python --version
# 或
python3 --version

# 期望输出：Python 3.8.x 或更高版本
```

**如果Python版本不够**:
- Windows: 去https://www.python.org/downloads/ 下载最新版
- Mac: `brew install python3`
- Linux: `sudo apt install python3.8`

---

### 2. 核心依赖包

#### 检查已安装的包
```bash
pip list | grep -E "streamlit|pandas|sqlalchemy|playwright|alembic"

# 或Windows
pip list | findstr "streamlit pandas sqlalchemy playwright alembic"
```

#### 安装所有依赖
```bash
# 进入项目目录
cd F:\Vscode\python_programme\AI_code\xihong_erp

# 安装依赖
pip install -r requirements.txt

# 如果requirements.txt缺少某些包，手动安装
pip install streamlit pandas sqlalchemy alembic playwright plotly pyyaml
pip install openpyxl xlrd lxml beautifulsoup4 html5lib
pip install requests pydantic click pytest pytest-cov
```

#### 验证安装
```python
# 运行这个脚本验证
python -c "
import streamlit
import pandas
import sqlalchemy
import playwright
import alembic
import plotly
print('✅ 所有核心依赖安装成功')
"
```

---

### 3. Playwright浏览器

```bash
# 安装Playwright浏览器
playwright install chromium

# 验证安装
playwright --version
```

---

### 4. 数据库

#### SQLite（默认，无需安装）
```bash
# 检查SQLite
sqlite3 --version

# 期望输出：3.x.x
```

**SQLite已内置在Python中，无需额外安装**

#### PostgreSQL（可选，生产环境用）

**Windows安装**:
1. 下载：https://www.postgresql.org/download/windows/
2. 运行安装程序
3. 设置密码（记住！）
4. 默认端口5432

**验证安装**:
```bash
# 检查版本
psql --version

# 期望输出：psql (PostgreSQL) 14.x 或更高
```

**创建数据库**:
```bash
# 方法1: 使用psql命令行
psql -U postgres
CREATE DATABASE xihong_erp;
\q

# 方法2: 使用pgAdmin图形界面
# 打开pgAdmin → 右键数据库 → 创建数据库
```

---

### 5. Redis（可选，缓存用）

**Windows安装**:
1. 下载：https://github.com/microsoftarchive/redis/releases
2. 解压并运行redis-server.exe

**验证**:
```bash
redis-cli ping
# 期望输出：PONG
```

**如果不安装Redis**:
可以使用内存缓存（dict），Day 4会实现

---

### 6. Git

```bash
# 检查Git版本
git --version

# 期望输出：git version 2.x.x
```

**如果没有Git**:
- 下载：https://git-scm.com/downloads

**配置Git**（首次使用）:
```bash
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
```

---

### 7. IDE/编辑器

#### Cursor
- 下载：https://cursor.sh/
- 安装后配置Python解释器
- 安装Python插件

#### Augment（VS Code插件）
- 在VS Code中搜索"Augment"插件
- 安装并配置

---

## 🔧 项目初始化

### 1. 检查项目结构
```bash
cd F:\Vscode\python_programme\AI_code\xihong_erp

# 确认关键目录存在
ls -la
# 应该看到：
# - models/
# - services/
# - frontend_streamlit/
# - modules/
# - config/
# - docs/
# - temp/
```

### 2. 创建必要的目录
```bash
# 如果缺少，创建这些目录
mkdir -p temp/development
mkdir -p temp/outputs
mkdir -p temp/logs
mkdir -p data/input/manual_uploads
mkdir -p tests/performance
```

### 3. 初始化数据库
```bash
# 使用SQLite（开发环境）
python -c "
from models.database import get_engine
engine = get_engine()
print('✅ 数据库连接成功')
"
```

### 4. 运行现有系统测试
```bash
# 测试主入口
python run_new.py

# 测试Streamlit
streamlit run frontend_streamlit/main.py

# 如果能启动，说明基础环境OK
```

---

## 📝 环境变量配置

### 创建.env文件（可选）
```bash
# 在项目根目录创建.env文件
# 注意：.env文件不应提交到Git（已在.gitignore中）

# 数据库配置
DATABASE_URL=sqlite:///data/unified_erp_system.db
# 或PostgreSQL
# DATABASE_URL=postgresql://user:password@localhost:5432/xihong_erp

# Redis配置（可选）
REDIS_URL=redis://localhost:6379/0

# 其他配置
SALES_DATA_SOURCE=db
LOG_LEVEL=INFO
```

### 加载环境变量

#### 方法1: 使用python-dotenv
```bash
pip install python-dotenv
```

```python
# 在代码中加载
from dotenv import load_dotenv
load_dotenv()

import os
database_url = os.getenv('DATABASE_URL')
```

#### 方法2: 手动设置
```bash
# Windows PowerShell
$env:DATABASE_URL = "sqlite:///data/unified_erp_system.db"

# Windows CMD
set DATABASE_URL=sqlite:///data/unified_erp_system.db

# Linux/Mac
export DATABASE_URL=sqlite:///data/unified_erp_system.db
```

---

## 🧪 环境验证脚本

创建一个完整的环境检查脚本：

```python
# scripts/check_environment.py
"""环境检查脚本"""

def check_python_version():
    """检查Python版本"""
    import sys
    version = sys.version_info
    if version.major >= 3 and version.minor >= 8:
        print(f"✅ Python版本: {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"❌ Python版本过低: {version.major}.{version.minor}")
        print("   需要Python 3.8或更高版本")
        return False

def check_dependencies():
    """检查依赖包"""
    required = [
        'streamlit', 'pandas', 'sqlalchemy', 'alembic',
        'playwright', 'plotly', 'pyyaml', 'openpyxl',
        'requests', 'pydantic', 'click', 'pytest'
    ]
    
    missing = []
    for package in required:
        try:
            if package == 'pyyaml':
                __import__('yaml')
            else:
                __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package} - 未安装")
            missing.append(package)
    
    if missing:
        print(f"\n缺少{len(missing)}个依赖包")
        print(f"运行: pip install {' '.join(missing)}")
        return False
    
    print(f"\n✅ 所有依赖包已安装")
    return True

def check_database():
    """检查数据库连接"""
    try:
        from models.database import get_engine
        engine = get_engine()
        print(f"✅ 数据库连接成功: {engine.url}")
        return True
    except Exception as e:
        print(f"❌ 数据库连接失败: {str(e)}")
        return False

def check_directories():
    """检查必要目录"""
    from pathlib import Path
    
    required_dirs = [
        'models', 'services', 'frontend_streamlit',
        'modules', 'config', 'docs', 'temp',
        'temp/development', 'temp/outputs', 'temp/logs'
    ]
    
    missing = []
    for dir_name in required_dirs:
        dir_path = Path(dir_name)
        if dir_path.exists():
            print(f"✅ {dir_name}/")
        else:
            print(f"❌ {dir_name}/ - 不存在")
            missing.append(dir_name)
    
    if missing:
        print(f"\n缺少{len(missing)}个目录，正在创建...")
        for dir_name in missing:
            Path(dir_name).mkdir(parents=True, exist_ok=True)
        print("✅ 目录创建完成")
    
    return True

def main():
    """主函数"""
    print("="*60)
    print("🔍 跨境电商ERP系统 - 开发环境检查")
    print("="*60)
    
    checks = [
        ("Python版本", check_python_version),
        ("依赖包", check_dependencies),
        ("数据库", check_database),
        ("目录结构", check_directories),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n📋 检查{name}...")
        print("-"*60)
        result = check_func()
        results.append((name, result))
    
    print("\n" + "="*60)
    print("📊 检查结果汇总")
    print("="*60)
    
    all_passed = True
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")
        if not result:
            all_passed = False
    
    if all_passed:
        print("\n🎉 恭喜！环境检查全部通过，可以开始开发了！")
        print("\n下一步:")
        print("1. 阅读 docs/MULTI_AGENT_QUICKSTART.md")
        print("2. 阅读 docs/AGENT_A_HANDBOOK.md")
        print("3. 明天早上9:00开始Day 1")
    else:
        print("\n⚠️  环境检查未通过，请先解决上述问题")

if __name__ == "__main__":
    main()
```

### 运行环境检查
```bash
python scripts/check_environment.py
```

---

## 🎯 Day 0准备工作（今天晚上完成）

### 清单
- [ ] 检查Python版本（≥3.8）
- [ ] 安装所有依赖包
- [ ] 安装Playwright浏览器
- [ ] 验证数据库连接
- [ ] 创建必要目录
- [ ] 配置Git
- [ ] 运行环境检查脚本
- [ ] 阅读多Agent开发文档
- [ ] 准备明天的开发环境

### 预计时间
- 环境检查和安装：30分钟
- 阅读文档：1小时
- 总计：1.5小时

### 完成标志
```bash
# 运行这个命令，全部✅就可以了
python scripts/check_environment.py

# 期望看到：
# ✅ 通过 - Python版本
# ✅ 通过 - 依赖包
# ✅ 通过 - 数据库
# ✅ 通过 - 目录结构
# 🎉 恭喜！环境检查全部通过，可以开始开发了！
```

---

## 🚀 准备就绪！

**如果环境检查全部通过**:
1. ✅ 你已经准备好开始开发
2. ⏭️ 阅读 `docs/MULTI_AGENT_QUICKSTART.md`
3. ⏭️ 阅读 `docs/AGENT_A_HANDBOOK.md`
4. ⏭️ 明天早上9:00准时开始Day 1

**加油！期待你的7天开发之旅！🎊**

---

**版本**: v1.0  
**创建日期**: 2025-10-16  
**用途**: Day 0环境准备

