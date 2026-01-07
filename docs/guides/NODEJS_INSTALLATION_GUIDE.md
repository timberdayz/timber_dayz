# 📦 Node.js 安装指南（Windows）

## 🎯 快速安装（推荐）

### 方法1: 使用官方安装包（最简单）

1. **下载Node.js**
   - 访问官网: https://nodejs.org/zh-cn/
   - 选择"长期支持版（LTS）"，目前推荐版本 18.x 或 20.x
   - 下载Windows安装包（.msi文件）

2. **安装Node.js**
   - 双击下载的.msi文件
   - 点击"Next"按照默认设置安装
   - **重要**: 确保勾选"Add to PATH"选项
   - 完成安装

3. **验证安装**
   ```powershell
   # 打开新的PowerShell窗口（重要！）
   node --version
   npm --version
   ```
   
   应该看到类似输出:
   ```
   v20.10.0
   10.2.3
   ```

### 方法2: 使用Chocolatey包管理器（开发者推荐）

如果您已安装Chocolatey，可以用一行命令安装：

```powershell
# 以管理员身份运行PowerShell
choco install nodejs-lts -y
```

### 方法3: 使用Scoop包管理器

如果您使用Scoop：

```powershell
scoop install nodejs-lts
```

## 🚀 安装后配置

### 1. 验证安装
```powershell
node --version
npm --version
```

### 2. 配置npm国内镜像（可选，提升下载速度）
```powershell
# 使用淘宝镜像
npm config set registry https://registry.npmmirror.com
```

### 3. 安装Vue.js前端依赖
```powershell
# 进入Vue.js前端目录
cd modules/apps/vue_field_mapping/frontend

# 安装依赖（首次需要）
npm install

# 验证安装
npm list --depth=0
```

## 🎯 完整流程（从零开始）

```powershell
# 1. 安装Node.js（使用官方安装包或包管理器）

# 2. 重新打开PowerShell（确保环境变量生效）

# 3. 验证Node.js安装
node --version
npm --version

# 4. 配置npm镜像（可选）
npm config set registry https://registry.npmmirror.com

# 5. 安装Vue.js前端依赖
cd F:\Vscode\python_programme\AI_code\xihong_erp\modules\apps\vue_field_mapping\frontend
npm install

# 6. 安装Python后端依赖（如果尚未安装）
cd F:\Vscode\python_programme\AI_code\xihong_erp
pip install fastapi uvicorn python-multipart

# 7. 测试启动
python run_new.py
# 选择 4. Vue字段映射审核
```

## 🔧 常见问题排查

### 问题1: "node"命令未识别

**原因**: PATH环境变量未更新

**解决方案**:
1. 重新打开PowerShell窗口
2. 或者手动添加到PATH:
   - 默认安装路径: `C:\Program Files\nodejs\`
   - 添加到系统PATH环境变量
   - 重启PowerShell

### 问题2: npm install 很慢

**解决方案**: 使用国内镜像
```powershell
npm config set registry https://registry.npmmirror.com
npm install
```

### 问题3: npm install 报错权限问题

**解决方案**: 以管理员身份运行PowerShell
```powershell
# 右键PowerShell图标 → "以管理员身份运行"
cd modules/apps/vue_field_mapping/frontend
npm install
```

### 问题4: 端口被占用

**解决方案**: 更改默认端口
```powershell
# 前端端口修改（vite.config.js）
# 后端端口修改（backend/main.py）
```

## 📊 依赖包说明

### Vue.js前端依赖（package.json）
```json
{
  "dependencies": {
    "vue": "^3.3.4",              // Vue.js核心框架
    "vue-router": "^4.2.4",       // 路由管理
    "pinia": "^2.1.6",            // 状态管理
    "element-plus": "^2.3.8",     // UI组件库
    "axios": "^1.4.0",            // HTTP客户端
    "dayjs": "^1.11.9"            // 日期处理
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^4.2.3",        // Vite Vue插件
    "vite": "^4.4.5",                      // 构建工具
    "unplugin-vue-components": "^0.25.1",  // 自动导入组件
    "unplugin-auto-import": "^0.16.6"      // 自动导入API
  }
}
```

### Python后端依赖（requirements.txt补充）
```txt
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
python-multipart>=0.0.6
pydantic>=2.4.0
```

## ✅ 验证安装成功

运行以下命令，如果都成功则表示安装完成：

```powershell
# 1. Node.js验证
node --version
# 输出: v20.x.x

# 2. npm验证
npm --version
# 输出: 10.x.x

# 3. Vue.js依赖验证
cd modules/apps/vue_field_mapping/frontend
npm list vue
# 输出: vue@3.3.4

# 4. 启动测试
cd ../../../../
python run_new.py
# 选择 4，应该正常启动
```

## 🎉 下一步

安装完成后，您可以：

1. **启动Vue字段映射系统**
   ```powershell
   python run_new.py
   # 选择 4. Vue字段映射审核
   ```

2. **访问系统**
   - 前端界面: http://localhost:5173
   - 后端API: http://localhost:8000
   - API文档: http://localhost:8000/docs

3. **开发调试**
   ```powershell
   # 后端开发模式（支持热重载）
   cd modules/apps/vue_field_mapping/backend
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

   # 前端开发模式（支持热重载）
   cd ../frontend
   npm run dev
   ```

## 📞 需要帮助？

如果遇到问题，请检查：
1. Node.js版本 >= 16.x
2. npm版本 >= 8.x
3. Python版本 >= 3.9
4. 网络连接正常
5. 防火墙允许端口8000和5173

祝您使用愉快！🎊
