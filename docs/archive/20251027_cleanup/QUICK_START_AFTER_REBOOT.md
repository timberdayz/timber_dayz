# 重启电脑后快速启动指南

> **版本**: v4.1.1  
> **最后更新**: 2025-10-25

---

## ⚡ 30秒快速启动

```bash
# Step 1: 进入项目目录
cd F:\Vscode\python_programme\AI_code\xihong_erp

# Step 2: 运行诊断（可选）
python diagnose_simple.py

# Step 3: 一键启动
python run.py
```

**就这么简单！**

---

## 🌐 访问地址

启动后访问：

- **前端界面**: http://localhost:5173
- **API文档**: http://localhost:8001/api/docs
- **健康检查**: http://localhost:8001/health

---

## 📝 详细文档

- **[完整优化报告](v4.1.1_optimization/)** - v4.1.1所有文档
- **[使用手册](USER_MANUAL.md)** - 系统使用指南
- **[部署指南](DEPLOYMENT_GUIDE.md)** - 部署说明

---

**快速命令**:
```bash
# 启动
python run.py

# 诊断
python diagnose_simple.py

# 只启动后端
python run.py --backend-only
```

