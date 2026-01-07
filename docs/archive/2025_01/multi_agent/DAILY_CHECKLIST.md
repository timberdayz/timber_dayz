# 每日开发检查清单（打印版）

## 📋 每日3次检查

### ✅ 早上开始前（9:00）
```
□ git pull（拉取最新代码）
□ 查看今日任务（Agent手册中的Day X）
□ 确认使用Cursor还是Augment
□ 查看API_CONTRACT.md有无更新
```

### ✅ 开发过程中（每2-3小时）
```
□ 完成一个模块就测试
□ 确认没有改错文件（查FILE_ISOLATION_RULES.md）
□ 添加类型注解和docstring
□ 提交代码：git add . && git commit
```

### ✅ 晚上结束前（23:00）
```
□ 运行相关测试
□ 检查git status（没有改错文件）
□ 最后提交：git commit && git push
□ 填写DAILY_PROGRESS_TRACKER.md
□ 准备明天任务清单
```

---

## 🚨 3个最重要的规则

### 规则1: 文件隔离
```
Agent A（Cursor）只改:
  ✅ models/
  ✅ migrations/
  ✅ services/etl*
  ✅ services/field_mapping/

Agent B（Augment）只改:
  ✅ frontend_streamlit/pages/
  ✅ utils/
  ✅ services/currency*
  ✅ services/data_query*

都不能改:
  ❌ modules/apps/collection_center/
  ❌ pages/10_数据采集中心.py
```

### 规则2: 接口优先
```
修改共享文件前:
1. 在docs/API_CONTRACT.md中定义接口
2. 双方确认接口签名
3. 实现接口
4. Git提交注明"⚠️ 接口变更"
```

### 规则3: 频繁测试
```
每完成一个功能:
□ 立即测试能不能运行
□ 测试通过才提交
□ 不要积累问题
```

---

## 🎯 7天验收标准

### Day 1 ✅
```
□ 诊断报告完成
□ 数据库Schema设计完成
□ ORM模型可用
□ Alembic迁移测试通过
```

### Day 2 ✅
```
□ 字段映射性能提升10倍+
□ 映射准确率≥90%
□ 刷新按钮正常工作
□ 无白屏问题
```

### Day 3 ✅
```
□ 支持所有格式（.xlsx/.xls/.csv）
□ 字段映射准确
□ 数据能成功入库
□ 失败数据正确隔离
```

### Day 4 ✅
```
□ 核心测试覆盖≥80%
□ ETL性能≥1000行/秒
□ 汇率服务可用
```

### Day 5 ✅
```
□ 数据查询服务完成
□ 前端页面无白屏
□ 能展示数据库数据
□ 统计卡片正确
```

### Day 6 ✅
```
□ 前端首屏<2秒
□ PostgreSQL支持完成
□ 部署文档齐全
```

### Day 7 ✅
```
□ 端到端测试通过
□ 测试覆盖率达标
□ 生产环境就绪
□ 代码已提交
```

---

## 🔧 快速命令参考

### Git命令
```bash
git status              # 查看状态
git add .               # 添加所有修改
git commit -m "..."     # 提交
git push                # 推送
git pull                # 拉取
git checkout -- <file>  # 撤销修改
```

### 测试命令
```bash
# 运行测试
pytest tests/ -v

# 查看覆盖率
pytest --cov=services --cov=models
```

### 环境检查
```bash
# 检查环境
python scripts/check_environment.py

# 运行系统
python run_new.py
streamlit run frontend_streamlit/main.py
```

---

## 📞 遇到问题？

### 代码问题
```
→ 截图给当前Agent
→ "这段代码报错了：[错误信息]，帮我修复"
```

### 不知道做什么
```
→ 查看对应Agent手册的Day X任务
→ 告诉Agent："帮我完成Day X的第一个任务"
```

### 改错文件了
```
→ git checkout -- <文件>
→ 查看FILE_ISOLATION_RULES.md确认权限
```

### 任务完成不了
```
→ 立即调整优先级
→ 砍掉非核心功能
→ 记录到DAILY_PROGRESS_TRACKER.md
```

---

**打印这份文档，贴在墙上，随时查看！**

**版本**: v1.0  
**创建日期**: 2025-10-16  
**用途**: 每日快速参考

