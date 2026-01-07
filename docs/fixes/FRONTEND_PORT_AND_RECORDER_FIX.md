# 前端端口和组件录制器修复报告

**日期**: 2025-12-20  
**问题**: 前端端口自动跳过5173，测试功能失败  
**优先级**: P0（阻塞性）

## 问题描述

### 问题1：前端端口跳过5173

**现象**：
- 启动系统时，前端服务运行在5174端口而不是默认的5173
- `run.py`显示"前端界面启动超时"警告

**诊断结果**：
```
前端服务实际运行在 5174 端口
后端服务正常运行在 8001 端口
```

**根本原因**：
- `vite.config.js`配置了`strictPort: false`
- 允许端口被占用时自动切换到下一个可用端口（5174/5175...）

### 问题2：测试功能失败  

**现象**：
- 用户报告"测试现在连启动都会失败"
- 前端显示错误弹窗

**诊断结果**：
```
✅ 录制器状态API正常 (200)
✅ 账号列表API正常 (200) - 返回正确数据
✅ 启动录制API正常 (200)
```

后端API实际上是正常工作的，问题可能是：
1. 前端缓存了旧的API端点
2. 浏览器使用了错误的端口（5174而不是5173）
3. WebSocket连接失败

## 修复内容

### 修复1：强制使用5173端口

**文件**：`frontend/vite.config.js`

**修改前**：
```javascript
server: {
    port: 5173,
    host: '0.0.0.0',
    strictPort: false,  // 如果端口被占用，自动尝试下一个
    open: false,
}
```

**修改后**：
```javascript
server: {
    port: 5173,
    host: '0.0.0.0',
    strictPort: true,  // ✅ 强制使用5173端口，如果被占用则报错
    open: false,
}
```

**影响**：
- ✅ 前端服务必须运行在5173端口
- ✅ 如果端口被占用，Vite会报错而不是自动切换
- ✅ 避免端口不一致导致的问题

### 修复2：API端点验证  

后端API端点已正确配置：
- ✅ `/api/accounts` - 获取账号列表
- ✅ `/api/collection/recorder/status` - 录制器状态
- ✅ `/api/collection/recorder/start` - 启动录制
- ✅ `/api/collection/recorder/test` - 测试组件

前端API调用已修复（`frontend/src/api/accounts.js`）：
```javascript
// ✅ 正确：使用 /accounts 而不是 /accounts/list
async listAccounts(params = {}) {
    const response = await api.get('/accounts', { params })
    return response
}
```

## 验证步骤

### 1. 重启前端服务

```bash
# 停止当前的前端服务（如果正在运行）
# 在前端服务的PowerShell窗口按 Ctrl+C

# 重新启动前端
cd frontend
npm run dev
```

**期望结果**：
```
VITE v4.4.5  ready in XXX ms
➜  Local:   http://localhost:5173/
➜  Network: http://0.0.0.0:5173/
```

如果5173端口被占用，Vite会报错：
```
Error: Port 5173 is in use
```

### 2. 清除浏览器缓存

- 打开 http://localhost:5173
- 按 `Ctrl + Shift + Delete`
- 清除缓存和Cookie
- 刷新页面

### 3. 测试组件录制功能

1. 登录系统
2. 进入"组件录制工具"页面
3. 选择平台（如：妙手ERP）
4. 选择测试账号
5. 点击"开始录制"

**期望结果**：
- ✅ 账号列表正常加载
- ✅ 录制器正常启动
- ✅ Playwright Inspector窗口打开

### 4. 测试组件测试功能

1. 录制一些步骤
2. 点击"停止录制"
3. 选择测试账号
4. 点击"开始测试"

**期望结果**：
- ✅ 测试正常执行
- ✅ 显示步骤执行结果
- ✅ 测试完成后显示成功/失败统计

## 诊断工具

创建了两个诊断脚本：

### 1. `temp/diagnose_frontend_issue.py`
检查前端和后端服务状态，以及端口占用情况。

```bash
python temp/diagnose_frontend_issue.py
```

### 2. `temp/test_recorder_api.py`  
测试组件录制器的所有API端点。

```bash
python temp/test_recorder_api.py
```

## 常见问题排查

### Q1: 5173端口被占用怎么办？

**检查占用进程**：
```bash
netstat -ano | findstr :5173
```

**终止占用进程**（谨慎使用）：
```bash
taskkill /PID <进程ID> /F
```

### Q2: 前端启动后无法访问？

**检查防火墙**：
- Windows Defender防火墙可能阻止了端口访问
- 尝试临时关闭防火墙测试

**检查hosts文件**：
- 确保localhost正确解析
- 文件位置：`C:\Windows\System32\drivers\etc\hosts`
- 应该包含：`127.0.0.1 localhost`

### Q3: API调用失败？

**检查网络请求**：
1. 打开浏览器开发者工具（F12）
2. 切换到"Network"标签页
3. 刷新页面
4. 查看失败的请求

**检查API响应**：
- 点击失败的请求
- 查看"Response"标签页
- 检查错误消息

### Q4: WebSocket连接失败？

**检查WebSocket端点**：
```javascript
// 应该使用当前页面的host
const ws = new WebSocket(`ws://${window.location.host}/api/ws/collection`)
```

**检查后端日志**：
- 查看后端PowerShell窗口
- 搜索"WebSocket"相关日志

## 相关文档

- Wait步骤修复报告：`docs/fixes/WAIT_STEP_FIX_REPORT.md`
- 组件录制工具文档：`docs/guides/component_recording.md`
- 提案：`openspec/changes/verify-collection-and-sync-e2e/`

## 总结

**已修复**：
1. ✅ 前端端口配置（强制使用5173）
2. ✅ 验证后端API正常工作
3. ✅ 创建诊断工具

**需要用户操作**：
1. 重启前端服务
2. 清除浏览器缓存
3. 测试组件录制功能
4. 如果仍有问题，运行诊断脚本并提供日志

**下一步**：
- 继续提案Phase 2（录制妙手ERP核心组件）
- 验证完整的录制-测试-保存流程

