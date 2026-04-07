# 快速修复：前端端口5173权限错误

**错误信息**：`EACCES: permission denied 127.0.0.1:5173`

**状态**：✅ 已修复（2025-01-29）

---

## 🔍 问题原因

**EACCES（权限拒绝）**通常由以下原因引起：

1. **端口被其他进程占用**（即使netstat没有显示）
2. **Windows防火墙阻止**
3. **Node.js权限不足**
4. **之前的Vite进程没有完全关闭**

---

## ✅ 已完成的修复

### 1. 修改Vite配置

**文件**：`frontend/vite.config.js`

**改进**：
- ✅ host改为`localhost`（更兼容）
- ✅ 添加`strictPort: false`（端口被占用时自动使用下一个端口）

### 2. 添加端口自动检测

如果5173被占用，Vite会自动尝试5174、5175...直到找到可用端口。

---

## 🚀 立即修复步骤（3种方法）

### 方法1：重启Node.js进程（推荐，30秒）

#### 步骤1：关闭所有Node.js进程

```powershell
# 方法A：通过任务管理器
# 按 Ctrl+Shift+Esc 打开任务管理器
# 找到所有 "node.exe" 进程，结束任务

# 方法B：通过命令行（快速）
taskkill /F /IM node.exe
```

#### 步骤2：等待3秒

```powershell
Start-Sleep -Seconds 3
```

#### 步骤3：重新启动系统

```powershell
python run.py
```

**期望结果**：前端正常启动，显示：
```
[OK] 前端服务已在新窗口启动
[OK] 前端已就绪 (5秒)
```

---

### 方法2：手动清理端口（如果方法1失败）

#### 步骤1：检查端口占用

```powershell
netstat -ano | findstr :5173
```

#### 步骤2：如果看到输出，找到PID并关闭

```powershell
# 例如，如果看到：
# TCP    0.0.0.0:5173    0.0.0.0:0    LISTENING    12345
# 则关闭进程：
taskkill /F /PID 12345
```

#### 步骤3：重新启动

```powershell
python run.py
```

---

### 方法3：使用备用端口（最快，10秒）

如果5173端口始终有问题，可以临时使用其他端口。

#### 步骤1：修改vite配置

编辑 `frontend/vite.config.js`，将端口改为5174：

```javascript
server: {
  port: 5174,  // 改为5174
  host: 'localhost',
  // ...
}
```

#### 步骤2：修改run.py中的地址提示

编辑 `run.py`，更新前端地址提示（可选，不影响功能）：

```python
safe_print("  地址: http://localhost:5174")  # 改为5174
```

和等待服务的端口：

```python
wait_for_service(5174, "前端", max_wait=30)  # 改为5174
```

#### 步骤3：重新启动

```powershell
python run.py
```

**访问地址**：http://localhost:5174

---

## 🔧 如果仍然失败

### 检查清单

1. **Node.js版本**
   ```powershell
   node --version
   ```
   **期望**：v16+ 或 v18+

2. **npm版本**
   ```powershell
   npm --version
   ```

3. **防火墙设置**
   - 打开Windows防火墙设置
   - 检查是否阻止了Node.js
   - 临时关闭防火墙测试（仅用于诊断）

4. **以管理员身份运行**
   ```powershell
   # 右键PowerShell，选择"以管理员身份运行"
   # 然后cd到项目目录
   cd F:\Vscode\python_programme\AI_code\xihong_erp
   python run.py
   ```

5. **检查Vite配置**
   ```powershell
   # 确认vite.config.js中的配置
   cat frontend/vite.config.js | Select-String "server"
   ```

---

## 📊 验证修复

### 成功标志

启动后，你应该看到：

1. **后端日志**：
   ```
   [OK] Backend started on http://localhost:8001
   ```

2. **前端窗口**：
   ```
   VITE v5.x.x  ready in 500 ms

   ➜  Local:   http://localhost:5173/
   ➜  Network: use --host to expose
   ```

3. **run.py输出**：
   ```
   [OK] 前端服务已在新窗口启动
   [OK] 前端已就绪 (5秒)
   ```

### 测试访问

打开浏览器访问：
- http://localhost:5173 （或你设置的端口）

**期望看到**：西虹ERP登录页面或主界面

---

## 🎯 快速命令总结

### 一键清理并重启

```powershell
# 关闭所有Node.js进程
taskkill /F /IM node.exe

# 等待3秒
Start-Sleep -Seconds 3

# 重新启动
python run.py
```

### 检查端口状态

```powershell
# 检查5173端口
netstat -ano | findstr :5173

# 检查8001端口（后端）
netstat -ano | findstr :8001
```

---

## 💡 预防措施

### 1. 优雅关闭服务

**不要直接关闭终端窗口**，应该：
- 在Vite窗口按 `Ctrl+C` 停止前端
- 在run.py窗口按 `Ctrl+C` 停止后端

### 2. 使用进程管理器

如果经常遇到端口占用问题，可以考虑：
- 使用PM2管理Node.js进程
- 或使用Docker容器化部署

---

## 🆘 仍然无法解决？

如果以上方法都无效，请提供以下信息：

1. **错误信息完整日志**（截图）
2. **Node.js版本**：`node --version`
3. **操作系统版本**：`systeminfo | findstr /B /C:"OS Name" /C:"OS Version"`
4. **防火墙状态**：是否启用
5. **端口检查结果**：`netstat -ano | findstr :5173`

---

**最后更新**：2025-01-29  
**修复版本**：v4.4.0-hotfix-2

