# 🔧 Node.js识别问题解决方案

## 问题现象

运行 `python run_new.py` 并选择"Vue字段映射审核"时，提示:
```
❌ 无法检测到Node.js依赖
```

但在PowerShell中运行 `node --version` 可以正常显示版本号。

## 🎯 根本原因

**环境变量未同步**: VSCode启动时加载的环境变量，不会自动更新Node.js安装后添加的PATH。

## ✅ 解决方案（按推荐顺序）

### 方案1: 重启VSCode（最简单，推荐）⭐

1. **完全关闭VSCode**
   - 不是关闭窗口，而是完全退出
   - Windows: 关闭所有VSCode窗口
   - 或按 `Ctrl+Shift+P` → "退出"

2. **重新打开VSCode**
   - 打开项目目录
   - 打开终端（Terminal）

3. **验证**
   ```powershell
   node --version
   npm --version
   ```

4. **运行系统**
   ```powershell
   python run_new.py
   # 选择: 4. Vue字段映射审核
   ```

---

### 方案2: 使用独立的PowerShell窗口

1. **打开新的PowerShell窗口**
   - 按 `Win+X` → 选择"Windows PowerShell"
   - 或搜索"PowerShell"并打开

2. **导航到项目目录**
   ```powershell
   cd F:\Vscode\python_programme\AI_code\xihong_erp
   ```

3. **验证Node.js**
   ```powershell
   node --version
   npm --version
   ```

4. **运行系统**
   ```powershell
   python run_new.py
   # 选择: 4. Vue字段映射审核
   ```

---

### 方案3: 直接启动服务（开发者模式）

如果上述方案仍有问题，可以手动启动前后端服务：

**终端1 - 启动后端**:
```powershell
cd modules/apps/vue_field_mapping/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**终端2 - 启动前端**:
```powershell
cd modules/apps/vue_field_mapping/frontend
npm run dev
```

然后直接访问: http://localhost:5173

---

### 方案4: 刷新VSCode终端环境变量

在VSCode的终端中运行：

```powershell
# 刷新环境变量
$env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")

# 验证
node --version
npm --version

# 运行
python run_new.py
```

**注意**: 这个方法只对当前终端会话有效。

---

## 🧪 快速验证脚本

创建一个测试脚本来诊断问题：

```powershell
# 保存为 test_nodejs.ps1
Write-Host "🔍 Node.js环境诊断" -ForegroundColor Cyan
Write-Host ""

# 测试1: 直接命令
Write-Host "测试1: 直接运行命令" -ForegroundColor Yellow
try {
    $nodeVer = node --version 2>&1
    Write-Host "  ✅ Node.js: $nodeVer" -ForegroundColor Green
} catch {
    Write-Host "  ❌ Node.js命令失败" -ForegroundColor Red
}

try {
    $npmVer = npm --version 2>&1
    Write-Host "  ✅ npm: $npmVer" -ForegroundColor Green
} catch {
    Write-Host "  ❌ npm命令失败" -ForegroundColor Red
}

# 测试2: 检查PATH
Write-Host ""
Write-Host "测试2: 检查PATH环境变量" -ForegroundColor Yellow
$paths = $env:Path -split ';'
$nodejsPath = $paths | Where-Object { $_ -like "*nodejs*" }
if ($nodejsPath) {
    Write-Host "  ✅ 找到Node.js路径: $nodejsPath" -ForegroundColor Green
} else {
    Write-Host "  ❌ PATH中未找到Node.js" -ForegroundColor Red
}

# 测试3: 检查常见安装位置
Write-Host ""
Write-Host "测试3: 检查常见安装位置" -ForegroundColor Yellow
$commonPaths = @(
    "C:\Program Files\nodejs\node.exe",
    "C:\Program Files (x86)\nodejs\node.exe",
    "$env:LOCALAPPDATA\Programs\nodejs\node.exe",
    "$env:USERPROFILE\scoop\apps\nodejs\current\node.exe"
)

foreach ($path in $commonPaths) {
    if (Test-Path $path) {
        Write-Host "  ✅ 找到: $path" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host "💡 建议:" -ForegroundColor Cyan
Write-Host "  1. 如果以上测试都失败，请重新安装Node.js"
Write-Host "  2. 如果在VSCode外可以运行，请重启VSCode"
Write-Host "  3. 确保安装时勾选了 'Add to PATH' 选项"
```

运行:
```powershell
powershell -ExecutionPolicy Bypass -File test_nodejs.ps1
```

---

## 📋 检查清单

运行前请确认：

- [ ] Node.js已安装（从 https://nodejs.org 下载LTS版本）
- [ ] 安装时勾选了"Add to PATH"选项
- [ ] 已重启终端/VSCode
- [ ] 在新的PowerShell窗口中 `node --version` 有效
- [ ] 在新的PowerShell窗口中 `npm --version` 有效
- [ ] npm依赖已安装（运行过 `npm install`）

---

## 🎯 终极解决方案

如果所有方法都不行，可以：

### 选项A: 完全重装Node.js

1. **卸载Node.js**
   - 控制面板 → 程序和功能
   - 找到Node.js → 卸载

2. **清理残留**
   ```powershell
   Remove-Item -Recurse -Force "$env:APPDATA\npm"
   Remove-Item -Recurse -Force "$env:APPDATA\npm-cache"
   ```

3. **重新安装**
   - 下载最新LTS版本
   - 安装时确保勾选"Add to PATH"
   - 重启电脑

4. **验证**
   ```powershell
   node --version
   npm --version
   ```

### 选项B: 使用独立启动脚本

我们已经创建了 `start_vue_system.ps1` 脚本：

```powershell
# 运行此脚本会自动启动前后端
powershell -ExecutionPolicy Bypass -File start_vue_system.ps1
```

---

## 💡 为什么会出现这个问题？

1. **环境变量加载时机**: VSCode在启动时读取系统环境变量
2. **PATH未更新**: 安装Node.js后，新的PATH只对新启动的进程有效
3. **子进程继承**: Python从VSCode启动，继承了旧的环境变量

## 🎊 确认成功

当看到以下输出时，表示成功：

```
📋 依赖检查:
   ✅ fastapi
   ✅ uvicorn
   ✅ nodejs
   ✅ npm

🎯 Vue字段映射审核系统
```

---

**需要帮助？** 查看完整文档: `docs/NODEJS_INSTALLATION_GUIDE.md`
