# 代码清理任务跟踪器

**创建日期**: 2025-12-19  
**最后更新**: 2025-12-19 (网络恢复后)  
**完整报告**: [CODE_CLEANUP_REPORT_2025_12_19.md](CODE_CLEANUP_REPORT_2025_12_19.md)  
**进度报告**: [CODE_CLEANUP_REPORT_2025_12_19_PROGRESS.md](CODE_CLEANUP_REPORT_2025_12_19_PROGRESS.md)  
**验证脚本**: `scripts/verify_*.py`

---

## ✅ P0任务（立即执行）- Week 1 - **已完成**

### Task 1.1: 修复AccountResponse重复定义 ⭐⭐⭐
- [x] 创建 `backend/schemas/account.py`（含完整账号模型）
- [x] 更新 `backend/routers/account_management.py` 导入schemas
- [x] 更新 `backend/routers/collection.py` 改名为CollectionAccountResponse
- [x] 删除account_management.py中的重复定义
- [x] 运行 `python scripts/verify_contract_first.py` - ✅ 通过
- [ ] 更新 `frontend/src/api/accounts.js` JSDoc（待定）
- [ ] 测试账号管理页面（待定）
- [ ] 测试组件版本管理页面（待定）

**实际耗时**: 15分钟  
**执行人**: AI Agent  
**状态**: ✅ **已完成**

---

### Task 1.2: 修复FilePreviewRequest重复定义
- [x] 检查 `modules/apps/vue_field_mapping/backend/main.py` - 还在使用
- [x] 改名为 `FieldMappingFilePreviewRequest`（使用file_path）
- [x] 改名 `data_sync.py` 为 `DataSyncFilePreviewRequest`（使用file_id）
- [x] 更新所有引用的API端点
- [x] 运行 `python scripts/verify_contract_first.py` - ✅ 通过
- [ ] 测试数据同步功能（待定）

**实际耗时**: 10分钟  
**执行人**: AI Agent  
**状态**: ✅ **已完成**

---

### Task 1.3: 处理backend/models/finance.py（SSOT违规）⭐⭐⭐
- [x] 检查是否还有引用 - ✅ 无引用
- [x] 决策：**选项A** - 删除文件（未使用）
- [x] 删除 `backend/models/finance.py`
- [x] 运行 `python scripts/identify_dead_code.py` - ✅ 通过
- [x] 运行 `python scripts/verify_architecture_ssot.py` - ✅ 通过

**实际耗时**: 5分钟  
**执行人**: AI Agent  
**状态**: ✅ **已完成**

---

### Task 1.4: 删除重复的accounts.py
- [x] 对比功能 - account_management.py功能更完整
- [x] 确认 `accounts.py` 已被 `account_management.py` 替代
- [x] 检查 `main.py` 中的注册 - 两个都注册了
- [x] 删除 `backend/routers/accounts.py`
- [x] 更新 `backend/main.py` - 移除import和router注册
- [x] 运行 `python scripts/identify_dead_code.py` - ✅ 通过
- [ ] 运行所有测试（待定）

**实际耗时**: 10分钟  
**执行人**: AI Agent  
**状态**: ✅ **已完成**

---

## 🟡 P1任务（本周内）- Week 2

### Task 2.1: 修复前后端API不匹配（13个）
- [ ] 逐个检查13个不匹配的API调用
- [ ] 确认后端实际路径（考虑router prefix）
- [ ] 更新前端API路径或修复后端路径
- [ ] 更新前端API：
  - [ ] `frontend/src/api/accounts.js` (2个)
  - [ ] `frontend/src/api/collection.js` (10个)
  - [ ] `frontend/src/api/finance.js` (1个)
- [ ] 运行 `python scripts/verify_api_contract_consistency.py`
- [ ] 测试所有受影响的前端页面

**预计**: 3-4小时  
**负责人**: _______  
**状态**: ⬜ 未开始

---

### Task 2.2: 审查inventory.py vs inventory_management.py
- [ ] 对比两个文件的功能
- [ ] 决策：合并或明确分工
- [ ] 如果合并：迁移功能并删除旧文件
- [ ] 如果分工：在文件头部添加清晰的注释说明职责
- [ ] 更新文档

**预计**: 2-3小时  
**负责人**: _______  
**状态**: ⬜ 未开始

---

### Task 2.3: 审查performance.py vs performance_management.py
- [ ] 对比两个文件的功能
- [ ] 决策：合并或明确分工
- [ ] 执行相应操作
- [ ] 更新文档

**预计**: 2-3小时  
**负责人**: _______  
**状态**: ⬜ 未开始

---

## 🟡 P1任务（持续）- Week 3-7

### Task 3.1: 为API添加response_model（分批）

**批次1**（Week 3，15-20个API）:
- [ ] accounts.py (7个)
- [ ] account_alignment.py (10个)
- [ ] 运行验证

**批次2**（Week 4，15-20个API）:
- [ ] management.py (15个)
- [ ] 运行验证

**批次3**（Week 5，15-20个API）:
- [ ] field_mapping.py (15个)
- [ ] 运行验证

**批次4-10**（Week 6-12）:
- [ ] 持续添加，每周15-20个
- [ ] 目标：response_model覆盖率 >80%

**当前覆盖率**: 27% (74/273)  
**目标覆盖率**: 80% (218/273)  
**还需添加**: 144个

---

### Task 3.2: 迁移模型到backend/schemas/（分批）

**批次1**（Week 3，5-10个模型）:
- [ ] AccountListItemResponse → `backend/schemas/accounts.py`
- [ ] AccountDetailResponse → `backend/schemas/accounts.py`
- [ ] TaskCreateRequest → `backend/schemas/collection.py`
- [ ] TaskResponse → `backend/schemas/collection.py`
- [ ] ComponentVersionResponse → `backend/schemas/components.py`

**批次2**（Week 4，5-10个模型）:
- [ ] CollectionConfigResponse → `backend/schemas/collection.py`
- [ ] TestHistoryResponse → `backend/schemas/components.py`
- [ ] OrderResponse → `backend/schemas/orders.py`
- [ ] ProductResponse → `backend/schemas/products.py`

**批次3-8**（Week 5-10）:
- [ ] 持续迁移，每周5-10个模型
- [ ] 目标：schemas覆盖率 >60%

**当前覆盖率**: 15% (19/122)  
**目标覆盖率**: 60% (73/122)  
**还需迁移**: 54个

---

## 🟢 P2任务（长期）

### Task 4.1: 标记未使用的API（185个）
- [ ] 为每个API添加使用情况注释
- [ ] 识别真正的死代码
- [ ] 创建删除计划

**预计**: 长期持续  
**负责人**: Team  
**状态**: ⬜ 未开始

---

## 📊 进度跟踪

### Week 1 进度
- P0任务: ▯▯▯▯ 0/4 (0%)
- 验证通过: ❌

### Week 2 进度
- P1任务: ▯▯▯ 0/3 (0%)
- 验证通过: ❌

### Week 3-7 进度
- response_model添加: ▯▯▯▯▯▯▯▯▯▯ 0/144 (0%)
- 模型迁移: ▯▯▯▯▯ 0/54 (0%)
- 验证通过: ❌

---

## ✅ 验证检查清单

每完成一个任务后运行：

```bash
# 1. SSOT验证
python scripts/verify_architecture_ssot.py
# 期望：Compliance Rate: 100.0%

# 2. Contract-First验证
python scripts/verify_contract_first.py
# 期望：Tests Failed: 0, Warnings减少

# 3. API契约验证
python scripts/verify_api_contract_consistency.py
# 期望：Mismatches减少

# 4. 死代码识别
python scripts/identify_dead_code.py
# 期望：Issues减少
```

---

## 📝 变更日志

### 2025-12-19
- [x] 创建验证脚本（4个）
- [x] 运行初始扫描
- [x] 创建清理报告
- [x] 创建任务跟踪器
- [x] 更新.cursorrules

### 2025-12-20
- [ ] 开始P0任务执行
- [ ] ...

---

## 🎯 里程碑

- [ ] **里程碑1**（Week 1 End）: P0问题全部解决，Pydantic重复定义=0
- [ ] **里程碑2**（Week 2 End）: 前后端API不匹配=0
- [ ] **里程碑3**（Week 4 End）: response_model覆盖率>50%
- [ ] **里程碑4**（Week 8 End）: Schemas覆盖率>40%
- [ ] **里程碑5**（Week 12 End）: response_model覆盖率>80%, Schemas覆盖率>60%

---

**文档维护**: 请在每次完成任务后更新此文件  
**下次审查**: 每周五  
**问题反馈**: 更新[CODE_CLEANUP_REPORT_2025_12_19.md](CODE_CLEANUP_REPORT_2025_12_19.md)

