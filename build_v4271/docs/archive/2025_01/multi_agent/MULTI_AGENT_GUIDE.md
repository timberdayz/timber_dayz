# 多Agent协作开发指南（总纲）

## 🎯 文档概述

本文档是多Agent协作开发的**总入口**，提供完整的开发框架和指引。

**适用场景**: 个人开发者使用Cursor和Augment两个AI工具串行开发  
**开发周期**: 7天（每天12小时）  
**目标**: 完成生产就绪的跨境电商ERP系统  

## 📚 文档体系

### 必读文档（开发前）
1. **本文档** - `MULTI_AGENT_GUIDE.md`（总纲，你正在阅读）
2. **开发规范** - `.cursorrules`（Cursor AI编程规范）
3. **项目状态** - `PROJECT_STATUS.md`（了解当前进度）
4. **开发计划** - Plan文档（7天详细计划）

### Agent专用手册（开发时）
- **Agent A手册** - `AGENT_A_HANDBOOK.md`（后端/数据库专家）
- **Agent B手册** - `AGENT_B_HANDBOOK.md`（前端/工具专家）

### 协作规范文档（避免冲突）
- **接口契约** - `API_CONTRACT.md`（接口定义，双方协调）
- **文件隔离规则** - `FILE_ISOLATION_RULES.md`（修改权限矩阵）

### 技术文档（参考）
- **数据库设计** - `DATABASE_SCHEMA_V3.md`（Day 1创建）
- **ETL架构** - `ETL_ARCHITECTURE.md`（Day 3创建）
- **部署指南** - `DEPLOYMENT_GUIDE.md`（Day 6创建）

---

## 🏗️ 系统架构概览（插件化视角）

### 分层架构
```
┌─────────────────────────────────────────┐
│  前端层 (Streamlit)                      │  ← Agent B负责
│  - pages/20_数据管理中心.py              │
│  - pages/40_字段映射审核.py              │
│  - unified_dashboard.py                 │
└─────────────────────────────────────────┘
              ↓ 调用
┌─────────────────────────────────────────┐
│  服务层 (Services)                       │  ← 共享接口层
│  - data_query_service.py (Agent B实现)  │
│  - currency_service.py (Agent B实现)    │
│  - etl_pipeline.py (Agent A实现)        │
│  - field_mapping/ (Agent A实现)         │
└─────────────────────────────────────────┘
              ↓ 调用
┌─────────────────────────────────────────┐
│  数据访问层 (Models)                     │  ← Agent A负责
│  - models/dimensions.py                 │
│  - models/facts.py                      │
│  - models/management.py                 │
└─────────────────────────────────────────┘
              ↓ ORM
┌─────────────────────────────────────────┐
│  数据库 (SQLite/PostgreSQL)              │
└─────────────────────────────────────────┘
```

### 插件化设计
- **数据采集插件**：modules/apps/collection_center/（已完成，冻结）
- **账号管理插件**：modules/apps/account_manager/（已完成）
- **数据处理插件**：services/etl_pipeline.py（本周开发）
- **前端页面插件**：frontend_streamlit/pages/（本周优化）

---

## 📅 7天开发时间表

### Week 1总览

| Day | 时间段 | Agent | 主要任务 | 验收标准 |
|-----|--------|-------|----------|----------|
| **Day 1** | 全天 | Cursor (A) | 诊断+数据库架构+Alembic | 数据库迁移可用 |
| **Day 2** | 全天 | Cursor (A) | 智能字段映射系统重构 | 映射性能提升10倍+ |
| **Day 3** | 全天 | Cursor (A) | ETL流程实现 | 文件能入库 |
| **Day 4** | 全天 | Cursor (A) | 性能优化+测试+工具 | 核心测试覆盖80%+ |
| **Day 5** | 上午 | Cursor (A) | 数据查询服务 | 接口定义完成 |
| **Day 5** | 下午+晚上 | Augment (B) | 前端页面修复 | 页面无白屏 |
| **Day 6** | 上午 | Augment (B) | 前端优化+图表 | 性能优化完成 |
| **Day 6** | 下午+晚上 | Cursor (A) | PostgreSQL+文档 | 双数据库支持 |
| **Day 7** | 全天 | Cursor + Augment | 集成测试+生产准备 | 系统生产就绪 |

### 工具切换时机
```
Day 1-4: 全部使用Cursor（后端开发）
Day 5上午: Cursor（完成数据查询服务）
Day 5下午: ⚠️ 切换到Augment（前端开发）
Day 6上午: 继续使用Augment（前端优化）
Day 6下午: ⚠️ 切换回Cursor（PostgreSQL）
Day 7: 根据任务灵活切换
```

---

## 🔒 防冲突机制（核心保障）

### 1. 文件级严格隔离
**原则**：Agent A和B各自负责完全不同的目录

**检查方法**：
```bash
# 修改前检查
# 查看 docs/FILE_ISOLATION_RULES.md 的权限矩阵

# 修改后检查
git status
# 如果看到不属于你的目录，立即撤销
```

### 2. 接口契约优先
**原则**：先定义接口，再实现代码

**流程**：
```
1. Agent B在docs/API_CONTRACT.md中提出接口需求
   → 定义方法签名、参数、返回值

2. Agent A确认接口可行
   → 评估实现难度和时间

3. 双方达成一致
   → 更新API_CONTRACT.md，标记状态为"📋 待实现"

4. Agent A实现接口
   → 完成后标记为"✅ 已实现"

5. Agent B调用测试
   → 确认接口工作正常
```

### 3. Git分支策略
**简化策略**（个人开发者）：
```bash
# 主分支
main/dev

# 功能分支（可选）
feature/agent-a-database
feature/agent-a-etl
feature/agent-b-frontend

# 推荐做法（简单）
直接在dev分支上开发，每天提交即可
```

### 4. 每日同步机制
```
早上9:00
├─ 拉取最新代码：git pull
├─ 查看今日任务清单
└─ 选择使用Cursor或Augment

每2-3小时
├─ 提交代码：git add . && git commit -m "..."
└─ 推送代码：git push

晚上11:00
├─ 最后一次提交
├─ 更新进度文档
└─ 准备明天任务清单
```

---

## 🚦 开发流程规范

### Step 1: 开发前准备
```markdown
□ 阅读今日任务（Plan中的Day X）
□ 查看API_CONTRACT.md有无接口更新
□ 拉取最新代码：git pull
□ 确认使用哪个Agent工具
```

### Step 2: 开发中
```markdown
□ 严格遵守文件隔离规则
□ 添加类型注解和docstring
□ 每完成一个模块就测试
□ 每2-3小时提交一次代码
```

### Step 3: 开发后
```markdown
□ 运行相关测试确保通过
□ 检查git status（确认没改错文件）
□ Git提交（使用规范格式）
□ 更新相关文档
```

### Git提交格式
```bash
# 格式
git commit -m "[Agent A/B] Day X: 完成XXX功能

- 具体改动1
- 具体改动2
- 影响范围: XXX模块
- 验收: XXX测试通过
"

# 示例1 - Agent A
git commit -m "[Agent A] Day 1: 完成数据库Schema设计

- 创建维度表模型（dim_platforms, dim_shops, dim_products）
- 创建事实表模型（fact_orders, fact_order_items）
- 实现Alembic初始迁移
- 添加索引和约束
- 影响范围: models/, migrations/
- 验收: alembic upgrade head 成功
"

# 示例2 - Agent B
git commit -m "[Agent B] Day 5: 修复数据管理中心白屏问题

- 移除导入阶段的数据库连接
- 使用@st.cache_resource缓存连接
- 接入data_query_service获取数据
- 添加统计卡片和图表
- 影响范围: frontend_streamlit/pages/20_数据管理中心.py
- 验收: 页面正常加载，无白屏
"
```

---

## 🚨 风险管理

### 识别的风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| 接口不一致 | 高 | 严格使用API_CONTRACT.md定义接口 |
| 误改对方文件 | 中 | 提交前检查git status |
| 接口变更未通知 | 高 | Git提交中标注"⚠️ 接口变更" |
| 代码冲突 | 低 | 串行开发，每日同步 |
| 性能不达标 | 中 | Day 4专项性能优化 |
| 时间不够 | 中 | 每天复盘，及时调整优先级 |

### 每日复盘（晚上11:00）
```markdown
今日完成情况：
□ 计划任务完成X/Y个
□ 遇到的主要问题：XXX
□ 解决方案：XXX
□ 明日重点：XXX

进度风险评估：
□ 是否按计划进行？
□ 是否需要调整优先级？
□ 是否需要砍功能？
```

---

## 📊 成功指标（验收标准）

### 功能完整性
- [ ] 数据库架构完整（10+张表）
- [ ] Alembic迁移可用
- [ ] 智能字段映射系统重构完成
- [ ] ETL流程打通（文件→数据库）
- [ ] 前端页面能展示数据库数据
- [ ] 支持3个平台数据（Shopee/TikTok/妙手）

### 性能指标
- [ ] 文件扫描：≥500文件/秒
- [ ] ETL处理：≥1000行/秒
- [ ] 数据库查询：<5秒
- [ ] 前端首屏：<2秒
- [ ] 内存使用：单文件处理≤500MB

### 质量保证
- [ ] 核心模块测试覆盖率≥80%
- [ ] 整体测试覆盖率≥60%
- [ ] 错误处理完善（try-except覆盖）
- [ ] 失败数据正确隔离到quarantine

### 文档完整性
- [ ] 部署指南完整
- [ ] API文档完整
- [ ] 快速开始指南完整
- [ ] 故障排查手册完整

### 生产就绪
- [ ] 支持SQLite和PostgreSQL双数据库
- [ ] 数据迁移脚本可用
- [ ] 生产环境配置完成
- [ ] 端到端测试通过

---

## 🎓 新手开发者指南

### 第一次使用Agent工具？

#### Cursor使用技巧
1. **告诉它具体要做什么**
   ```
   好的描述：
   "帮我创建一个Excel解析器类，支持.xlsx和.xls格式，
    返回pandas DataFrame，要有错误处理"
   
   不好的描述：
   "写个解析Excel的东西"
   ```

2. **给它看类似的代码**
   ```
   "参考models/product.py的写法，帮我创建models/order.py"
   ```

3. **让它解释代码**
   ```
   "这段代码是做什么的？有什么潜在问题？"
   ```

4. **让它帮你调试**
   ```
   "运行这段代码报错了：[粘贴错误信息]，帮我修复"
   ```

#### Augment使用技巧
1. **前端问题描述要具体**
   ```
   好的描述：
   "这个Streamlit页面打开是白屏，没有显示任何内容，
    浏览器控制台显示XXX错误"
   
   不好的描述：
   "页面有问题"
   ```

2. **要求优化性能**
   ```
   "这个页面加载很慢，帮我优化性能，目标是2秒内加载完成"
   ```

3. **要求改进UI**
   ```
   "添加一个GMV趋势图，使用Plotly，要有双Y轴（GMV和订单数）"
   ```

### 遇到问题怎么办？

#### 问题分类与处理

**1. 代码运行错误**
```
解决步骤：
1. 复制完整的错误信息（包括Traceback）
2. 粘贴给当前使用的Agent
3. 说明："运行XXX功能时报这个错误，帮我修复"
4. Agent会分析错误原因并提供修复代码
```

**2. 不知道怎么实现某个功能**
```
解决步骤：
1. 在项目中搜索类似的代码
2. 告诉Agent："参考XXX的实现，帮我实现YYY"
3. 或者直接问："如何在Streamlit中实现XXX功能？"
```

**3. 性能问题（慢）**
```
解决步骤：
1. 告诉Agent具体哪里慢（如"文件扫描很慢"）
2. 让Agent分析瓶颈："帮我分析这段代码的性能瓶颈"
3. 要求优化："使用缓存优化这段代码"
```

**4. Agent理解错误了你的需求**
```
解决步骤：
1. 重新描述需求，用更简单的话
2. 提供示例代码或截图
3. 分步骤说明："先做A，再做B，最后做C"
```

**5. 卡住超过30分钟**
```
解决步骤：
1. 换个思路或简化需求
2. 跳过当前任务，先做后面的
3. 记录到"待解决问题清单"，Day 7统一处理
```

### 调试技巧

#### Python调试
```python
# 1. 使用print调试
print(f"变量x的值: {x}")
print(f"DataFrame形状: {df.shape}")

# 2. 使用try-except捕获错误
try:
    result = some_function()
except Exception as e:
    print(f"错误: {str(e)}")
    import traceback
    traceback.print_exc()

# 3. 使用pdb调试器（高级）
import pdb; pdb.set_trace()  # 在这里暂停
```

#### Streamlit调试
```python
# 1. 显示变量值
st.write("变量x:", x)
st.json({"key": "value"})

# 2. 显示DataFrame
st.dataframe(df)

# 3. 显示错误信息
try:
    result = query_data()
except Exception as e:
    st.error(f"错误: {str(e)}")
```

---

## 🎯 每日开发节奏

### 标准工作日（9:00-23:00，12小时）

#### 上午（9:00-13:00，4小时）
```
09:00-09:30  准备工作
             - 拉取代码
             - 查看任务清单
             - 准备开发环境

09:30-12:30  专注开发
             - 完成上午的2-3个任务
             - 每完成一个就测试
             - 每1小时休息5分钟

12:30-13:00  上午总结
             - 提交代码
             - 记录进度
```

#### 下午（14:00-18:00，4小时）
```
14:00-14:30  准备工作
             - 查看下午任务
             - 如果需要切换Agent，切换工具

14:30-17:30  专注开发
             - 完成下午的2-3个任务
             - 每完成一个就测试

17:30-18:00  下午总结
             - 提交代码
```

#### 晚上（19:00-23:00，4小时）
```
19:00-19:30  准备工作
             - 查看晚上任务

19:30-22:30  专注开发
             - 完成晚上的2-3个任务

22:30-23:00  每日总结
             - 最后提交
             - 更新文档
             - 复盘当日工作
             - 准备明日任务
```

---

## 📝 每日检查清单

### 早上开始前
- [ ] 拉取最新代码
- [ ] 查看Plan中今日任务
- [ ] 查看API_CONTRACT.md接口更新
- [ ] 确认使用Cursor或Augment

### 开发过程中
- [ ] 遵守文件隔离规则
- [ ] 每完成一个模块就测试
- [ ] 添加必要的注释和类型注解
- [ ] 每2-3小时提交代码

### 晚上结束前
- [ ] 运行相关测试
- [ ] 检查git status
- [ ] 提交代码（规范格式）
- [ ] 更新进度文档
- [ ] 准备明日任务清单

---

## 📞 问题与支持

### 常见问题速查

#### Q1: 我是Agent A，需要Agent B提供的接口，但Agent B还没实现怎么办？
**答**：
1. 在`docs/API_CONTRACT.md`中定义接口签名
2. 先写一个mock实现（返回假数据）
3. 等Agent B实现后再替换

#### Q2: 我是Agent B，发现Agent A的接口有bug怎么办？
**答**：
1. 记录bug详情（错误信息、复现步骤）
2. 在docs/中创建`BUGS.md`记录
3. 下次切换到Cursor时修复

#### Q3: 一天的任务完成不了怎么办？
**答**：
1. 立即调整优先级，砍掉非核心功能
2. 保证核心流程能跑通
3. 延后的任务记录到文档，Week 2再做

#### Q4: 不确定某个文件应该谁改怎么办？
**答**：
1. 查看`docs/FILE_ISOLATION_RULES.md`权限矩阵
2. 如果是新文件，按照职责分工决定
   - 数据库、ETL相关 → Agent A
   - 前端、UI相关 → Agent B

#### Q5: Agent理解错我的需求怎么办？
**答**：
1. 重新描述，用更简单的话
2. 提供示例代码或截图
3. 分步骤说明具体流程

---

## 🎯 快速开始

### 今天就开始（Day 0准备）

**1. 环境检查**（30分钟）
```bash
# 检查Python版本
python --version  # 应该≥3.8

# 检查依赖
pip list | grep -E "streamlit|pandas|sqlalchemy|playwright"

# 如果缺少，安装
pip install -r requirements.txt
```

**2. 阅读文档**（1小时）
```
必读：
□ 本文档（MULTI_AGENT_GUIDE.md）
□ .cursorrules（开发规范）
□ AGENT_A_HANDBOOK.md（如果你明天用Cursor）
□ FILE_ISOLATION_RULES.md（权限矩阵）
```

**3. 准备工作区**（30分钟）
```bash
# 创建分支（可选）
git checkout -b feature/agent-a-database

# 或直接在dev分支工作
git checkout dev
git pull

# 准备笔记本记录每日进度
```

### 明天开始（Day 1）

**上午9:00准时开始**
1. 打开Cursor
2. 阅读`AGENT_A_HANDBOOK.md`的Day 1任务
3. 开始系统诊断！

---

## 🚀 加油！

**你能做到的！**

- 每天12小时投入 = 84小时有效开发时间
- 有清晰的Plan和完整的文档
- 有强大的AI工具辅助
- 有详细的代码示例参考

**7天后，你将拥有一个生产就绪的ERP系统！**

**相信自己，开始行动！💪**

---

**版本**: v1.0  
**创建日期**: 2025-10-16  
**适用人群**: 个人开发者（编程新手+重度依赖Agent）  
**核心理念**: 高效协作、零冲突、快速交付

