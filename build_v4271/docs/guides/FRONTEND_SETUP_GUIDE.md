# 🌐 前端服务设置指南

## 📦 前端依赖安装

### 问题说明
前端服务需要安装Vue.js、Vite等npm依赖包才能运行。

### 解决方案

#### 方案1: 通过前端管理模块安装（推荐）

```bash
# 1. 启动主入口
python run_new.py

# 2. 选择 "5" - 前端页面管理

# 3. 选择 "1" - 启动前端服务

# 4. 系统检测到依赖缺失后，会提示:
⚠️  检测到依赖缺失!
选项:
1. 现在安装依赖（推荐）  # 选择1
2. 手动安装
0. 取消

# 5. 选择 "1"，等待安装完成（约2-5分钟）

# 6. 安装完成后，服务会自动启动
```

#### 方案2: 手动安装依赖

```bash
# 打开新的终端窗口
cd F:\Vscode\python_programme\AI_code\xihong_erp\frontend
npm install

# 等待安装完成后，返回主程序启动前端服务
```

#### 方案3: 使用独立启动脚本

```bash
python start_frontend.py
# 会自动安装依赖并启动服务
```

## 🚀 启动流程

### 完整流程（首次运行）

```
1. python run_new.py
   ↓
2. 选择 5 (前端页面管理)
   ↓
3. 选择 1 (启动前端服务)
   ↓
4. 检测到依赖缺失
   ↓
5. 选择 1 (现在安装依赖)
   ↓
6. 等待2-5分钟安装完成
   ↓
7. 自动启动Vite开发服务器
   ↓
8. 选择 5 (在浏览器中打开)
   ↓
9. 访问 http://localhost:5173
```

### 后续启动（依赖已安装）

```
1. python run_new.py
   ↓
2. 选择 5 (前端页面管理)
   ↓
3. 选择 1 (启动前端服务)
   ↓
4. 等待3秒服务启动
   ↓
5. 选择 5 (在浏览器中打开)
```

## 🔧 依赖安装详情

### 安装的主要依赖
```json
{
  "vue": "^3.3.4",
  "vue-router": "^4.2.5",
  "pinia": "^2.1.7",
  "element-plus": "^2.4.4",
  "axios": "^1.6.2",
  "echarts": "^5.4.3",
  "dayjs": "^1.11.10"
}
```

### 开发依赖
```json
{
  "vite": "^5.0.0",
  "typescript": "^5.2.2",
  "eslint": "^8.54.0",
  "@vitejs/plugin-vue": "^4.5.0"
}
```

### 安装时间估算
- 正常网络: 2-3分钟
- 慢速网络: 5-10分钟
- 首次安装: 可能更长

## 📊 验证安装

### 检查依赖是否安装成功

```bash
cd frontend

# Windows
dir node_modules\vite

# 检查package.json
type package.json

# 查看已安装的包
npm list --depth=0
```

### 验证结果

成功安装后，`frontend/node_modules`目录应包含:
- ✅ vite/
- ✅ vue/
- ✅ element-plus/
- ✅ echarts/
- ✅ 其他依赖...

## 🐛 常见问题

### Q1: 安装超时
**症状**: 依赖安装超过10分钟

**解决**:
```bash
# 切换npm镜像源
npm config set registry https://registry.npmmirror.com

# 或使用cnpm
npm install -g cnpm --registry=https://registry.npmmirror.com
cnpm install
```

### Q2: 安装失败
**症状**: 提示依赖安装失败

**解决**:
```bash
# 清除缓存
npm cache clean --force

# 删除node_modules和package-lock.json
cd frontend
Remove-Item -Recurse -Force node_modules
Remove-Item package-lock.json

# 重新安装
npm install
```

### Q3: 权限错误
**症状**: EACCES权限错误

**解决**:
```bash
# 以管理员身份运行终端
# 或修改npm全局目录权限
```

## 💡 最佳实践

### 推荐方式
1. **首次使用**: 手动安装依赖（可以看到进度）
   ```bash
   cd frontend
   npm install
   ```

2. **后续使用**: 通过主入口启动
   ```bash
   python run_new.py
   # 选择5 → 1
   ```

### 开发建议
- 保持npm和Node.js为最新版本
- 使用淘宝镜像源加速安装
- 定期清理npm缓存
- 使用package-lock.json锁定版本

## 📞 获取帮助

如果遇到问题:
1. 查看错误信息
2. 参考本文档的常见问题
3. 提交Issue: https://github.com/xihong-erp/xihong-erp/issues

---

**最后更新**: 2025-01-16
