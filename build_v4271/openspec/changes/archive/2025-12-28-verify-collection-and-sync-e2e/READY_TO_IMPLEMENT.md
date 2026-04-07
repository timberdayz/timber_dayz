# 🎯 数据采集模块优化 - 准备实施

**时间**: 2025-12-19 22:15  
**提案状态**: ✅ 已验证，等待用户执行

---

## ✨ 工作完成情况

### ✅ Agent已完成（2小时工作）

1. **📋 OpenSpec提案创建**
   - ✅ proposal.md - 变更原因和范围
   - ✅ tasks.md - 69个详细任务（7个Phase）
   - ✅ spec deltas - 数据采集+数据同步规格变更
   - ✅ 提案验证通过 (`openspec validate --strict`)

2. **🔍 系统全面分析**
   - ✅ 录制工具代码审查（902行，功能完整）
   - ✅ 执行引擎审查（2212行，功能完整）
   - ✅ 组件YAML状态分析（发现阻塞项）
   - ✅ 定时任务配置检查（发现MV刷新缺失）
   - ✅ 服务运行状态确认（全部正常）

3. **🛠️ 代码修复**
   - ✅ 修复Contract-First重复模型定义（`ImportResponse`）
   - ✅ 清理4个测试YAML文件
   - ✅ 修复合规性问题（SSOT: 100%）

4. **🧪 测试脚本编写**
   - ✅ E2E测试脚本（368行，14个测试）
   - ✅ 13/14测试通过（基础功能验证）
   - ✅ 2个手动测试标记（需要真实账号）

5. **📚 文档创建**
   - ✅ 系统状态分析报告
   - ✅ 实施指南（分步骤执行）
   - ✅ 云端部署环境变量清单（20+变量）
   - ✅ 提案总览和README

---

## 🎯 关键发现

### 🔴 阻塞项：组件YAML需要实际录制

**问题**:
```yaml
# 当前状态（模板）
miaoshou/login.yaml:
  - selector: 'TODO: 填写等待的选择器'  ❌

miaoshou/navigation.yaml:
  - value: 'TODO: 填写成功URL特征'  ❌

miaoshou/orders_export.yaml:
  - selector: "button:has-text('导出')"  ⚠️ 通用选择器
```

**影响**: 无法执行实际采集任务

**解决**: 需要用户提供妙手ERP账号，使用录制工具更新YAML

---

### ⚠️ 改进项：物化视图无定时刷新

**问题**: APScheduler未注册物化视图刷新任务

**建议**: 在 `backend/main.py` 添加定时任务（每天凌晨2点）

**影响**: 物化视图数据需要手动刷新，不会自动更新

---

## 🚀 下一步：用户执行（2-3小时）

### Phase 1: 录制组件（1-1.5小时）⭐ **必须完成**

**前置条件**:
- ✅ 系统已启动（PostgreSQL/后端/前端全部运行）
- 需要: 妙手ERP账号信息

**执行步骤**:

```bash
# Step 1: 查看可用账号
curl "http://localhost:8001/api/collection/accounts?platform=miaoshou"
# 或前端查看: http://localhost:5173/account-management

# Step 2: 录制登录组件（15分钟）
python tools/record_component.py \
  --platform miaoshou \
  --component login \
  --account {YOUR_ACCOUNT_ID}

# 录制过程：
# 1. 浏览器窗口自动打开
# 2. Playwright Inspector启动
# 3. 在浏览器中执行登录操作
# 4. 点击Inspector的"Resume"按钮
# 5. YAML自动生成并保存

# 验证生成的YAML
cat config/collection_components/miaoshou/login.yaml | grep -i "TODO"
# 期望: 无输出（无TODO占位符）

# 测试组件
python tools/test_component.py -p miaoshou -c login -a {YOUR_ACCOUNT_ID}
# 期望: 测试通过

# Step 3: 录制导航组件（15分钟）
python tools/record_component.py \
  --platform miaoshou \
  --component navigation \
  --account {YOUR_ACCOUNT_ID}

# Step 4: 录制订单导出组件（30分钟）
python tools/record_component.py \
  --platform miaoshou \
  --component export \
  --account {YOUR_ACCOUNT_ID}
# 在录制过程中：
# - 导航到订单页面
# - 选择日期范围（昨天）
# - 点击导出按钮
# - 等待文件下载完成

# 验证组件
python tools/test_component.py -p miaoshou -c orders_export -a {YOUR_ACCOUNT_ID}
```

---

### Phase 2: 端到端测试（30分钟）

**通过前端界面**:

1. 访问采集任务页面
   ```
   http://localhost:5173/collection-tasks
   ```

2. 点击"快速采集"，填写：
   - 平台: 妙手ERP
   - 账号: ✓ 选择测试账号
   - 数据域: ✓ orders
   - 日期: 昨天

3. 点击"开始采集"

4. 观察执行过程（5-10分钟）：
   - 进度条: 0% → 100%
   - 当前步骤: "正在登录..." → "正在下载..." → "处理完成"
   - WebSocket日志: 实时输出

5. 验证结果：
   - 任务状态: completed ✅
   - 文件数: 1
   - 查看文件:
     ```bash
     ls data/raw/2025/miaoshou_orders_*
     ```

6. 验证catalog注册：
   ```sql
   SELECT file_name, platform_code, status 
   FROM catalog_files 
   ORDER BY created_at DESC 
   LIMIT 5;
   ```
   期望: 新文件记录，status='pending'

---

### Phase 3: 数据同步测试（30分钟）

1. 获取待同步文件ID：
   ```bash
   curl "http://localhost:8001/api/data-sync/pending-files?limit=5"
   ```

2. 触发单文件同步：
   ```bash
   curl -X POST "http://localhost:8001/api/data-sync/sync-file/{FILE_ID}"
   ```

3. 验证文件状态：
   ```sql
   SELECT id, file_name, status, ingested_at 
   FROM catalog_files 
   WHERE id={FILE_ID};
   ```
   期望: status='ingested' ✅

4. 验证数据入库：
   ```sql
   SELECT COUNT(*) FROM b_class.fact_miaoshou_orders_daily;
   ```
   期望: 行数>0 ✅

5. 查看数据内容：
   ```sql
   SELECT 
     raw_data->>'订单号' AS order_id,
     raw_data->>'金额' AS amount,
     platform_code,
     shop_id
   FROM b_class.fact_miaoshou_orders_daily
   LIMIT 5;
   ```
   期望: JSONB数据正确 ✅

---

## 📊 验证清单

### 基础验证（已完成）✅

- [x] OpenSpec提案创建并验证
- [x] 系统状态分析完成
- [x] 测试YAML文件清理
- [x] 服务运行状态确认
- [x] SSOT架构验证100%
- [x] Contract-First重复定义修复
- [x] 环境变量清单创建
- [x] E2E测试脚本编写（13/14通过）

### 功能验证（等待用户执行）

- [ ] ⏸️ 录制工具功能测试
- [ ] ⏸️ 组件YAML实际录制
- [ ] ⏸️ 组件可执行性验证
- [ ] ⏸️ 端到端采集流程测试
- [ ] ⏸️ 文件下载和注册验证
- [ ] ⏸️ 数据同步流程验证
- [ ] ⏸️ 数据完整性验证

### 可选验证（改进项）

- [ ] 📌 定时采集任务验证
- [ ] 📌 添加物化视图定时刷新
- [ ] 📌 无头浏览器模式测试
- [ ] 📌 Docker部署测试

---

## 🎬 立即开始

### 方式1: 提供账号信息（推荐）

**格式**:
```
账号ID: miaoshou_account_01
（或提供完整凭证）
```

我将指导您使用录制工具更新组件YAML。

---

### 方式2: 查看详细文档

```bash
# 查看实施指南
cat openspec/changes/verify-collection-and-sync-e2e/IMPLEMENTATION_GUIDE.md

# 查看系统状态
cat openspec/changes/verify-collection-and-sync-e2e/CURRENT_STATUS.md

# 查看任务清单
cat openspec/changes/verify-collection-and-sync-e2e/tasks.md
```

---

### 方式3: 先运行基础测试

```bash
# 验证系统基础功能
python -m pytest tests/e2e/test_complete_collection_to_sync.py -v -k "not manual"

# 期望结果
✅ 13 passed, 1 skipped
```

---

## 📞 联系和反馈

**准备好了吗？** 

提供妙手ERP账号信息，我们就可以开始执行录制和测试，让数据采集模块真正可用！ 🚀

**预计完成时间**: 2-3小时  
**预期成果**: MVP可用（orders域采集和同步）
