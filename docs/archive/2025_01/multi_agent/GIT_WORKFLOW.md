# Git工作流指南（个人开发者版）

## 🎯 简化策略

个人开发者使用Git，不需要复杂的分支策略。保持简单高效即可。

## 📋 基础工作流

### 每日标准流程

#### 早上开始工作（9:00）
```bash
# 1. 切换到开发分支
git checkout dev

# 2. 拉取最新代码（如果有多台电脑或协作者）
git pull origin dev

# 3. 开始开发
```

#### 开发过程中（每2-3小时）
```bash
# 1. 查看修改了哪些文件
git status

# 2. 添加修改的文件
git add .
# 或指定文件
git add models/dimensions.py services/etl_pipeline.py

# 3. 提交（使用规范格式）
git commit -m "[Agent A] Day 1上午: 完成数据库Schema设计

- 创建dim_platforms, dim_shops模型
- 添加索引和约束
- 影响范围: models/dimensions.py
"

# 4. 推送（可选，建议每天至少推一次）
git push origin dev
```

#### 晚上结束工作（23:00）
```bash
# 最后一次提交
git add .
git commit -m "[Agent A] Day 1完成: 数据库架构+Alembic迁移

Day 1总结:
- ✅ 完成系统诊断
- ✅ 创建数据库Schema文档
- ✅ 实现ORM模型
- ✅ 配置Alembic迁移
- 验收: 迁移测试通过

明日计划:
- Day 2重构字段映射系统
"

# 推送到远程
git push origin dev
```

---

## ✏️ 提交信息规范

### 标准格式
```
[Agent A/B] Day X阶段: 简短描述（50字内）

详细说明:
- 改动点1
- 改动点2
- 改动点3

影响范围: 模块名称
验收: 测试结果
```

### 好的提交信息示例

#### 示例1: 功能完成
```
[Agent A] Day 3下午: 实现数据入库引擎

- 创建DataImporter类，支持订单/产品/指标入库
- 实现幂等性upsert（SQLite: INSERT OR REPLACE）
- 实现失败数据隔离到quarantine表
- 添加批量处理（1000行/批次）

影响范围: services/data_importer.py
验收: 测试入库1000条订单成功
```

#### 示例2: Bug修复
```
[Agent B] Day 5: 修复数据管理中心白屏问题

问题: 页面打开显示白屏
原因: 导入阶段创建数据库连接导致阻塞
修复: 移动到@st.cache_resource装饰的函数内

影响范围: frontend_streamlit/pages/20_数据管理中心.py
验收: 页面正常加载，2秒内完成首屏渲染
```

#### 示例3: 接口变更
```
⚠️ [Agent A] Day 5: 数据查询服务接口变更

变更: 统一使用dict过滤器替代多个参数
旧接口: get_orders(platform, start_date, end_date)
新接口: get_orders(filters: dict)

影响范围: services/data_query_service.py
兼容性: 旧接口标记废弃但保留
通知: Agent B需要更新前端调用代码
```

### 不好的提交信息
```
❌ "更新代码"
❌ "修复bug"
❌ "Day 1"
❌ "完成任务"

原因: 太模糊，看不出改了什么
```

---

## 🔧 常用Git命令

### 查看状态
```bash
# 查看当前修改状态
git status

# 查看详细的修改内容
git diff

# 查看某个文件的修改
git diff models/order.py
```

### 提交代码
```bash
# 添加所有修改
git add .

# 添加指定文件
git add models/order.py services/etl.py

# 添加某个目录
git add models/

# 提交
git commit -m "提交信息"

# 修改上一次提交信息
git commit --amend
```

### 撤销操作
```bash
# 撤销未暂存的修改（还没git add）
git checkout -- <file>
git checkout -- .  # 撤销所有

# 撤销已暂存的修改（已git add但未commit）
git reset HEAD <file>
git reset HEAD .  # 撤销所有

# 撤销上一次commit（保留修改）
git reset --soft HEAD~1

# 撤销上一次commit（丢弃修改）⚠️ 慎用
git reset --hard HEAD~1
```

### 查看历史
```bash
# 简洁版（推荐）
git log --oneline -10

# 详细版
git log -5

# 查看某个文件的历史
git log -- models/order.py

# 查看某次提交的详细内容
git show <commit-hash>
```

---

## 🌿 分支管理（简化版）

### 推荐策略：单分支开发
```
对于个人开发者，建议就用一个dev分支:

main (生产分支，保护)
  └─ dev (开发分支，你在这工作)
```

### 操作命令
```bash
# 切换到dev分支
git checkout dev

# 每天在dev分支上开发和提交
git add .
git commit -m "..."
git push origin dev

# 每周或重要milestone合并到main
git checkout main
git merge dev
git push origin main
```

### 如果要使用功能分支（可选）
```
只在遇到以下情况时使用:
1. 需要尝试一个不确定的重构
2. 需要回滚的可能性很大
3. 想保留多个版本对比

创建功能分支:
git checkout -b feature/agent-a-database
开发...
git checkout dev
git merge feature/agent-a-database
git branch -d feature/agent-a-database
```

---

## 🆘 紧急情况处理

### 情况1: 改错了文件
```bash
# 立即撤销（还没commit）
git checkout -- <错误文件>

# 已经commit了
git reset --soft HEAD~1  # 撤销commit保留修改
git checkout -- <错误文件>  # 撤销修改
git commit -m "..."  # 重新提交正确的修改
```

### 情况2: 代码丢失
```bash
# 查看最近的提交
git log --oneline -20

# 恢复到某个提交
git checkout <commit-hash>

# 创建新分支保存
git checkout -b recovery
```

### 情况3: 提交了敏感信息
```bash
# 如果还没push
git reset --soft HEAD~1  # 撤销commit
# 删除敏感信息
git commit -m "..."  # 重新提交

# 如果已经push（需要强制推送）⚠️
git reset --hard HEAD~1
git push origin dev --force  # 慎用！
```

---

## 📊 提交频率建议

### 什么时候应该提交？

**必须提交的时机**:
- [ ] 完成一个功能模块（如完成Excel解析器）
- [ ] 代码能正常运行且测试通过
- [ ] 每天晚上11:00（无论是否完成）
- [ ] 切换Agent工具前（如Cursor→Augment）

**建议提交的时机**:
- [ ] 每2-3小时（防止代码丢失）
- [ ] 完成一个小功能（如添加一个方法）
- [ ] 修复一个bug

**不要提交的时机**:
- ❌ 代码无法运行（报错）
- ❌ 还没有测试过
- ❌ 只改了一行就提交（太频繁）

### 提交粒度建议
```
太小: 每改一行就提交（浪费时间）
太大: 一天只提交一次（风险高）
合适: 每2-3小时或完成一个模块提交
```

---

## 🔍 Git检查清单

### 提交前自检
```bash
# 1. 查看修改了哪些文件
git status

# 检查清单:
□ 是否改了不该改的文件？（查看FILE_ISOLATION_RULES.md）
□ 是否有临时文件需要排除？（.pyc, __pycache__等）
□ 是否有敏感信息？（密码、密钥等）

# 2. 查看具体修改内容
git diff

# 检查清单:
□ 修改是否符合预期？
□ 是否有误删的代码？
□ 是否有调试用的print忘记删？

# 3. 确认后提交
git add .
git commit -m "..."
```

### 推送前自检
```bash
# 检查清单:
□ 代码能正常运行？
□ 相关测试通过？
□ 提交信息清晰？
□ 没有敏感信息？

# 确认后推送
git push origin dev
```

---

## 💡 Git技巧

### 技巧1: 查看美化的日志
```bash
# 创建别名（只需设置一次）
git config --global alias.lg "log --graph --pretty=format:'%Cred%h%Creset -%C(yellow)%d%Creset %s %Cgreen(%cr) %C(bold blue)<%an>%Creset' --abbrev-commit"

# 使用
git lg -10  # 显示最近10次提交
```

### 技巧2: 暂存当前工作
```bash
# 临时保存当前修改（不提交）
git stash

# 切换到其他分支或其他工作
git checkout other-branch

# 恢复之前的修改
git checkout dev
git stash pop
```

### 技巧3: 比较不同提交
```bash
# 比较两个提交的差异
git diff commit1 commit2

# 比较当前代码与上一次提交
git diff HEAD

# 比较某个文件的变化
git diff HEAD~1 HEAD -- models/order.py
```

---

## 🎓 Git学习资源

### 基础教程
- **交互式学习**: https://learngitbranching.js.org/（强烈推荐）
- **官方文档**: https://git-scm.com/doc
- **简明指南**: https://rogerdudler.github.io/git-guide/index.zh.html

### 只需要掌握的命令（够用了）
```bash
git status          # 查看状态
git add .           # 添加所有修改
git commit -m ""    # 提交
git push            # 推送
git pull            # 拉取
git log --oneline   # 查看历史
git checkout --     # 撤销修改
git diff            # 查看差异
```

### 不需要学的（暂时）
- 复杂的分支策略（git flow）
- rebase操作
- cherry-pick
- submodule

---

## 📝 .gitignore配置

确保以下文件不被提交：

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/

# 敏感信息
local_accounts.py
*.enc
*.key
.env

# 数据库
*.db
*.sqlite

# 临时文件
temp/development/*
temp/logs/*
*.tmp
*.bak

# IDE
.vscode/
.idea/
*.swp

# 系统文件
.DS_Store
Thumbs.db
```

---

## 🚨 紧急救援命令

### 救援1: 我不小心删除了文件
```bash
# 还没commit
git checkout -- <删除的文件>

# 已经commit了
git checkout HEAD~1 -- <删除的文件>
```

### 救援2: 我想回到之前的某个版本
```bash
# 查看历史
git log --oneline

# 回到指定版本（不删除之后的提交）
git checkout <commit-hash>

# 如果确认要恢复到这个版本
git checkout -b recovery
git checkout dev
git merge recovery
```

### 救援3: 代码冲突了
```bash
# 如果是个人开发，不应该有冲突
# 如果真的有冲突：

# 1. 查看冲突文件
git status

# 2. 打开文件，找到冲突标记
<<<<<<< HEAD
你的修改
=======
对方的修改
>>>>>>> branch

# 3. 手动解决冲突（删除标记，保留正确代码）

# 4. 标记为已解决
git add <冲突文件>
git commit -m "解决冲突"
```

---

## 🎯 实战示例

### Day 1完整Git操作记录

```bash
# 早上9:00 - 开始工作
git checkout dev
git pull origin dev

# 10:30 - 完成诊断
git add docs/DIAGNOSTIC_REPORT_DAY1.md
git commit -m "[Agent A] Day 1上午: 完成系统诊断

- 诊断字段映射系统性能问题
- 评估数据库现状
- 定位前端白屏原因
- 输出诊断报告

影响范围: docs/
验收: 诊断报告完整
"

# 15:00 - 完成Schema设计
git add docs/DATABASE_SCHEMA_V3.md
git commit -m "[Agent A] Day 1下午: 完成数据库Schema设计

- 设计维度表（platforms, shops, products）
- 设计事实表（orders, order_items, metrics）  
- 设计管理表（catalog_files, quarantine）
- 定义索引和约束

影响范围: docs/
验收: Schema文档完整，ER图清晰
"

# 16:30 - 完成ORM模型
git add models/dimensions.py models/facts.py models/management.py
git commit -m "[Agent A] Day 1下午: 创建ORM模型

- 创建dimensions.py（维度表模型）
- 创建facts.py（事实表模型）
- 创建management.py（管理表模型）

影响范围: models/
验收: python -c 'from models.dimensions import DimPlatform' 无报错
"

# 20:00 - 配置Alembic
git add migrations/ alembic.ini
git commit -m "[Agent A] Day 1晚上: 配置Alembic迁移系统

- 初始化Alembic
- 配置alembic.ini支持SQLite和PostgreSQL
- 修改env.py从DATABASE_URL读取配置

影响范围: migrations/, alembic.ini
验收: alembic current 命令可用
"

# 22:30 - 创建初始迁移
git add migrations/versions/001_initial_schema.py
git commit -m "[Agent A] Day 1晚上: 创建初始数据库迁移

- 创建001_initial_schema.py
- 实现upgrade()创建所有表
- 实现downgrade()删除所有表
- 测试迁移通过

影响范围: migrations/versions/
验收: alembic upgrade head 成功，数据库表创建完成
"

# 23:00 - 每日总结提交
git add docs/DAILY_PROGRESS_TRACKER.md
git commit -m "[Agent A] Day 1完成: 总结与收尾

Day 1完成情况:
- ✅ 系统诊断完成
- ✅ 数据库Schema设计完成
- ✅ ORM模型创建完成  
- ✅ Alembic迁移配置完成
- ✅ 初始迁移测试通过

完成度: 100%（所有验收标准达成）
工作时长: 12小时

明日计划:
- Day 2重构智能字段映射系统
"

# 推送所有提交
git push origin dev
```

---

## 📊 提交统计

### 每日提交目标
- 最少提交次数：3次（上午、下午、晚上各一次）
- 推荐提交次数：5-8次（每2-3小时）
- 最多提交次数：不限（但不要太碎片化）

### 每周提交统计（参考）
```bash
# 查看本周提交次数
git log --oneline --since="1 week ago" | wc -l

# 查看本周修改的文件数
git diff --name-only HEAD~7 HEAD | wc -l

# 查看本周代码增删行数
git diff --stat HEAD~7 HEAD
```

---

## 🎯 最佳实践

### Do（推荐做法）
- ✅ 频繁提交（每2-3小时）
- ✅ 提交信息清晰（使用规范格式）
- ✅ 提交前测试代码能运行
- ✅ 每天晚上推送到远程
- ✅ 提交前检查git status

### Don't（不推荐）
- ❌ 一天只提交一次（风险高）
- ❌ 提交信息随便写
- ❌ 提交不能运行的代码
- ❌ 几天不推送到远程
- ❌ 提交前不检查改了什么

---

## 🔄 Day 5工具切换示例

### 从Cursor切换到Augment

```bash
# 上午最后（13:00），在Cursor中:

# 1. 提交所有代码
git add .
git commit -m "[Agent A] Day 5上午: 完成数据查询服务

- 实现DataQueryService类
- 实现get_orders, get_products, get_metrics方法
- 添加缓存和超时保护
- 更新API_CONTRACT.md接口文档

影响范围: services/data_query_service.py, docs/API_CONTRACT.md
验收: 接口测试通过
"

git push origin dev

# 2. 关闭Cursor

# 下午开始（14:00），打开Augment:

# 3. 拉取最新代码（可选，如果只在一台电脑上开发）
git pull origin dev

# 4. 查看Agent B手册，开始前端开发
# 阅读 docs/AGENT_B_HANDBOOK.md 的 Day 5任务
```

---

**版本**: v1.0  
**创建日期**: 2025-10-16  
**适用人群**: 个人开发者  
**复杂度**: 简化版（不需要复杂的Git技巧）

