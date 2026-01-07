# 路径配置管理文档

**版本**: v4.12.0  
**更新时间**: 2025-02-01  
**维护者**: 系统架构组

---

## 📋 概述

统一路径配置管理工具（`modules/core/path_manager.py`）提供了项目路径的统一管理机制，解决了硬编码路径导致的工作目录依赖问题。

### 核心功能

1. **统一项目根目录获取** - `get_project_root()`
2. **统一数据目录路径管理** - `get_data_dir()`, `get_data_raw_dir()` 等
3. **环境变量覆盖支持** - 支持通过环境变量自定义路径
4. **路径缓存机制** - 避免重复计算，提升性能

---

## 🎯 设计原则

### 与 secrets_manager 的关系

- **path_manager.py**: 专注于路径管理（目录路径、文件路径）
- **secrets_manager.py**: 专注于密钥和环境变量管理（数据库连接、API密钥等）
- **互补关系**: 两者不冲突，各司其职

### 路径解析优先级

所有路径函数都遵循以下优先级：

1. **环境变量** - 最高优先级
2. **项目结构检测** - 自动检测backend和frontend目录
3. **当前工作目录** - 如果包含项目结构
4. **向上查找** - 从当前文件位置向上查找
5. **默认值** - 使用项目根目录的相对路径

---

## 📁 可用函数

### 项目根目录

```python
from modules.core.path_manager import get_project_root

# 获取项目根目录
root = get_project_root()
# 返回: Path对象，例如: F:\Vscode\python_programme\AI_code\xihong_erp
```

**优先级**:
1. `PROJECT_ROOT` 环境变量
2. 从当前文件位置向上查找（包含backend和frontend目录）
3. 当前工作目录（如果包含backend和frontend）
4. 向上查找当前工作目录的父目录

### 数据目录

```python
from modules.core.path_manager import get_data_dir, get_data_raw_dir, get_data_input_dir

# 获取数据目录（data/）
data_dir = get_data_dir()
# 返回: Path对象，例如: F:\Vscode\python_programme\AI_code\xihong_erp\data

# 获取原始数据目录（data/raw）
raw_dir = get_data_raw_dir()
# 返回: Path对象，例如: F:\Vscode\python_programme\AI_code\xihong_erp\data\raw

# 获取输入数据目录（data/input）
input_dir = get_data_input_dir()
# 返回: Path对象，例如: F:\Vscode\python_programme\AI_code\xihong_erp\data\input
```

**环境变量**:
- `DATA_DIR` - 覆盖数据目录路径
- `DATA_RAW_DIR` - 覆盖原始数据目录路径
- `DATA_INPUT_DIR` - 覆盖输入数据目录路径

### 输出目录

```python
from modules.core.path_manager import get_output_dir

# 获取输出目录（temp/outputs）
output_dir = get_output_dir()
# 返回: Path对象，例如: F:\Vscode\python_programme\AI_code\xihong_erp\temp\outputs
```

**环境变量**:
- `OUTPUT_DIR` - 覆盖输出目录路径

### 下载目录

```python
from modules.core.path_manager import get_downloads_dir

# 获取下载目录（downloads）
downloads_dir = get_downloads_dir()
# 返回: Path对象，例如: F:\Vscode\python_programme\AI_code\xihong_erp\downloads
```

**环境变量**:
- `DOWNLOADS_DIR` - 覆盖下载目录路径

---

## 🔧 环境变量配置

### Windows PowerShell

```powershell
# 设置项目根目录
$env:PROJECT_ROOT = "F:\Vscode\python_programme\AI_code\xihong_erp"

# 设置数据目录
$env:DATA_DIR = "D:\Data\xihong_erp\data"

# 设置原始数据目录
$env:DATA_RAW_DIR = "D:\Data\xihong_erp\data\raw"

# 设置输出目录
$env:OUTPUT_DIR = "D:\Data\xihong_erp\temp\outputs"

# 设置下载目录
$env:DOWNLOADS_DIR = "D:\Data\xihong_erp\downloads"
```

### Linux/Mac Bash

```bash
# 设置项目根目录
export PROJECT_ROOT="/path/to/xihong_erp"

# 设置数据目录
export DATA_DIR="/data/xihong_erp/data"

# 设置原始数据目录
export DATA_RAW_DIR="/data/xihong_erp/data/raw"

# 设置输出目录
export OUTPUT_DIR="/data/xihong_erp/temp/outputs"

# 设置下载目录
export DOWNLOADS_DIR="/data/xihong_erp/downloads"
```

### .env 文件（推荐）

在项目根目录创建 `.env` 文件：

```env
# 路径配置（可选）
PROJECT_ROOT=F:\Vscode\python_programme\AI_code\xihong_erp
DATA_DIR=F:\Vscode\python_programme\AI_code\xihong_erp\data
DATA_RAW_DIR=F:\Vscode\python_programme\AI_code\xihong_erp\data\raw
DATA_INPUT_DIR=F:\Vscode\python_programme\AI_code\xihong_erp\data\input
OUTPUT_DIR=F:\Vscode\python_programme\AI_code\xihong_erp\temp\outputs
DOWNLOADS_DIR=F:\Vscode\python_programme\AI_code\xihong_erp\downloads
```

**注意**: `.env` 文件需要被 `secrets_manager.py` 或 `python-dotenv` 加载才能生效。

---

## 📦 项目迁移步骤

### 步骤1: 备份现有数据

```bash
# 备份数据目录
cp -r data/ data_backup/

# 备份下载目录
cp -r downloads/ downloads_backup/
```

### 步骤2: 配置环境变量

根据新项目位置设置环境变量（见"环境变量配置"章节）。

### 步骤3: 验证路径配置

```python
from modules.core.path_manager import get_project_root, get_data_raw_dir

# 验证项目根目录
root = get_project_root()
print(f"项目根目录: {root}")
assert (root / "backend").exists(), "backend目录不存在"
assert (root / "frontend").exists(), "frontend目录不存在"

# 验证数据目录
raw_dir = get_data_raw_dir()
print(f"原始数据目录: {raw_dir}")
assert raw_dir.exists(), "原始数据目录不存在"
```

### 步骤4: 迁移数据

```bash
# 迁移数据目录（如果使用环境变量覆盖）
cp -r data_backup/* $DATA_DIR/

# 迁移下载目录（如果使用环境变量覆盖）
cp -r downloads_backup/* $DOWNLOADS_DIR/
```

### 步骤5: 测试路径解析

运行测试脚本验证路径配置：

```bash
python scripts/test_file_scanning.py
```

---

## 🔍 路径解析优先级详解

### get_project_root() 优先级

1. **环境变量 PROJECT_ROOT**
   - 如果设置了 `PROJECT_ROOT` 环境变量，直接使用
   - 验证：检查目录是否包含 `backend` 和 `frontend` 目录

2. **从当前文件位置向上查找**
   - 从 `modules/core/path_manager.py` 所在位置向上查找
   - 查找包含 `backend` 和 `frontend` 目录的父目录

3. **当前工作目录**
   - 如果当前工作目录包含 `backend` 和 `frontend` 目录，使用当前工作目录

4. **向上查找当前工作目录的父目录**
   - 从当前工作目录向上查找，直到找到包含 `backend` 和 `frontend` 的目录

5. **Fallback**
   - 如果都找不到，使用当前文件所在目录的父目录（不推荐）

### 其他路径函数优先级

所有其他路径函数（`get_data_dir()`, `get_data_raw_dir()` 等）都遵循以下优先级：

1. **环境变量** - 如果设置了对应的环境变量，直接使用
2. **项目根目录相对路径** - 使用 `get_project_root()` + 相对路径

---

## ⚡ 性能优化

### 路径缓存机制

所有路径函数都使用 `@lru_cache(maxsize=1)` 装饰器，确保：

1. **只计算一次** - 第一次调用时计算路径，后续调用直接返回缓存结果
2. **全局缓存** - 使用全局变量 `_project_root` 进一步优化
3. **零性能影响** - 启动时检测一次（<100ms），运行时0影响

### 使用建议

```python
# ✅ 正确：直接调用函数，自动缓存
from modules.core.path_manager import get_data_raw_dir

raw_dir = get_data_raw_dir()  # 第一次调用：计算路径
raw_dir2 = get_data_raw_dir()  # 第二次调用：直接返回缓存

# ❌ 错误：不要手动缓存或重复计算
# 不需要手动缓存，函数已经自动缓存
```

---

## 🐛 故障排查

### 问题1: 找不到项目根目录

**症状**: `get_project_root()` 返回错误的路径

**解决方案**:
1. 检查环境变量 `PROJECT_ROOT` 是否正确设置
2. 确认项目根目录包含 `backend` 和 `frontend` 目录
3. 检查当前工作目录是否正确

**验证命令**:
```python
from modules.core.path_manager import get_project_root
import os

print(f"PROJECT_ROOT环境变量: {os.getenv('PROJECT_ROOT')}")
print(f"检测到的项目根目录: {get_project_root()}")
print(f"backend目录存在: {(get_project_root() / 'backend').exists()}")
print(f"frontend目录存在: {(get_project_root() / 'frontend').exists()}")
```

### 问题2: 数据目录路径错误

**症状**: `get_data_raw_dir()` 返回错误的路径

**解决方案**:
1. 检查环境变量 `DATA_DIR` 或 `DATA_RAW_DIR` 是否正确设置
2. 确认数据目录是否存在
3. 检查路径权限（Windows需要读写权限）

**验证命令**:
```python
from modules.core.path_manager import get_data_raw_dir
import os

print(f"DATA_DIR环境变量: {os.getenv('DATA_DIR')}")
print(f"DATA_RAW_DIR环境变量: {os.getenv('DATA_RAW_DIR')}")
print(f"检测到的原始数据目录: {get_data_raw_dir()}")
print(f"目录存在: {get_data_raw_dir().exists()}")
```

### 问题3: 路径缓存问题

**症状**: 修改环境变量后路径没有更新

**解决方案**:
1. 重启Python进程（路径缓存是进程级别的）
2. 清除缓存（不推荐，重启进程更简单）

**清除缓存代码**（仅用于调试）:
```python
from modules.core.path_manager import get_project_root, get_data_raw_dir
import modules.core.path_manager as pm

# 清除缓存
pm._project_root = None
get_project_root.cache_clear()
get_data_raw_dir.cache_clear()
```

---

## 📝 代码示例

### 示例1: 替换硬编码路径

**修改前**:
```python
# ❌ 错误：硬编码路径
data_dir = Path(__file__).parent.parent.parent / "data" / "raw"
```

**修改后**:
```python
# ✅ 正确：使用路径管理函数
from modules.core.path_manager import get_data_raw_dir

data_dir = get_data_raw_dir()
```

### 示例2: 在不同工作目录下运行

**场景**: 从 `backend/` 目录运行脚本

**代码**:
```python
from modules.core.path_manager import get_data_raw_dir

# 无论从哪个目录运行，都能正确获取路径
raw_dir = get_data_raw_dir()
print(f"原始数据目录: {raw_dir}")
```

### 示例3: 使用环境变量覆盖

**场景**: 开发环境和生产环境使用不同的数据目录

**开发环境** (`.env`):
```env
DATA_RAW_DIR=F:\Vscode\python_programme\AI_code\xihong_erp\data\raw
```

**生产环境** (`.env`):
```env
DATA_RAW_DIR=/data/xihong_erp/data/raw
```

**代码**（无需修改）:
```python
from modules.core.path_manager import get_data_raw_dir

# 自动使用环境变量配置的路径
raw_dir = get_data_raw_dir()
```

---

## ✅ 验证清单

在项目迁移或配置更新后，请验证以下项目：

- [ ] `get_project_root()` 返回正确的项目根目录
- [ ] `get_data_raw_dir()` 返回正确的原始数据目录
- [ ] `get_data_input_dir()` 返回正确的输入数据目录
- [ ] `get_output_dir()` 返回正确的输出目录
- [ ] `get_downloads_dir()` 返回正确的下载目录
- [ ] 所有目录路径都存在且可访问
- [ ] 环境变量配置正确（如果使用）
- [ ] 路径缓存正常工作（多次调用返回相同结果）

---

## 📚 相关文档

- [数据同步管道验证文档](DATA_SYNC_PIPELINE_VALIDATION.md) - 包含路径配置验证步骤
- [开发规范文档](DEVELOPMENT_RULES/) - 包含路径使用规范
- [快速启动指南](QUICK_START_ALL_FEATURES.md) - 包含路径配置示例

---

## 🔄 更新历史

- **v4.12.0 (2025-02-01)**: 初始版本，实现统一路径配置管理工具
- **v4.12.1 (2025-02-01)**: 添加路径缓存机制，优化性能

---

## 📞 支持

如有问题或建议，请：

1. 查看故障排查章节
2. 检查相关文档
3. 联系系统架构组

