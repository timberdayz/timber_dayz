# 🚀 Vue.js字段映射系统 - 快速安装指南

## 📦 第一步：安装Node.js

### Windows用户（推荐方法）

1. **下载Node.js LTS版本**
   - 访问: https://nodejs.org/zh-cn/
   - 点击"长期支持版"下载（推荐v20.x）
   - 双击安装包，按默认设置安装
   - **重要**: 安装时确保勾选"Add to PATH"

2. **验证安装**
   ```powershell
   # 重新打开PowerShell窗口
   node --version
   npm --version
   ```

## 🔧 第二步：安装项目依赖

### 方法A：自动安装（推荐）

```powershell
# 在项目根目录运行
python scripts/install_dependencies.py
```

### 方法B：手动安装

```powershell
# 1. 配置npm镜像（可选，加速下载）
npm config set registry https://registry.npmmirror.com

# 2. 安装Vue.js前端依赖
cd modules/apps/vue_field_mapping/frontend
npm install

# 3. 安装Python后端依赖
cd ../../../../
pip install fastapi uvicorn[standard] python-multipart pydantic
```

## ✅ 第三步：启动系统

```powershell
python run_new.py
# 选择 4. Vue字段映射审核
```

## 🌐 访问系统

- 前端界面: http://localhost:5173
- 后端API: http://localhost:8000
- API文档: http://localhost:8000/docs

## ⚡ 如果Node.js已安装但未识别

```powershell
# 刷新环境变量
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# 或者重新打开PowerShell窗口
```

## 🆘 遇到问题？

查看完整文档: `docs/NODEJS_INSTALLATION_GUIDE.md`

