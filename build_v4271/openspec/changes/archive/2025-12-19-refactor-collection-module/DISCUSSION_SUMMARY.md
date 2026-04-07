# 对话总结 - 数据采集模块重构提案审查

**日期**: 2025-01-08  
**审查人**: AI Agent  
**状态**: ✅ 已澄清所有疑问，提案可进入开发阶段

---

## 📋 审查问题与解决方案

### 1. 账号配置来源设计 ✅

**问题**: `local_accounts.py` 和 `accounts.json` 的关系不明确

**解决方案**:
- **数据源**: `local_accounts.py` 是唯一真实数据源（私密文件，不提交Git）
- **API读取**: 后端API直接从 `local_accounts.py` 读取（通过 `importlib` 动态导入）
- **脱敏处理**: API返回时移除敏感字段（username, password, Email account/password等）
- **缓存机制**: `accounts.json` 仅作为运行时缓存，不用于API读取

**实现位置**:
- `backend/routers/collection.py` - `GET /api/collection/accounts` 端点
- 采集执行时：`executor_v2.py` 中读取完整凭证（包含密码）

---

### 2. 组件YAML高级特性 ✅

**问题**: 条件判断、循环等高级特性何时实现？

**解决方案**:
- **Phase 1**: 不实现高级特性，仅支持基础actions（click, fill, wait, component_call）
- **Phase 2+**: 后续版本根据需求添加 `if` 条件判断和 `loop` 循环
- **当前策略**: 大多数场景可通过组件嵌套（`component_call`）解决

---

### 3. 验证码处理边界情况 ✅

**问题**: 滑块验证、拼图验证等无法输入验证码的情况如何处理？

**解决方案**:
- **验证码类型**: 支持 sms_code（输入）、slider/image（手动完成）、2fa（输入）
- **超时时间**: 5分钟（可配置 `VERIFICATION_TIMEOUT`）
- **超时策略**: 保持 `paused` 状态，不自动标记为 `failed`
- **用户选择**: 继续等待 / 跳过（标记失败）/ 取消任务
- **前端交互**: 根据 `verification_type` 显示输入框或"已手动完成"按钮

---

### 4. 任务恢复行为 ✅

**问题**: Resume 和 Retry 的精确行为是什么？

**解决方案**:
- **Resume（继续）**: 从暂停点继续执行（保存执行上下文：当前组件、步骤索引、浏览器状态）
- **Retry（重试）**: 创建新任务，重新开始整个流程（`parent_task_id` 关联原任务）
- **实现**: `executor_v2.py` 中保存 `TaskContext`，Resume 时恢复上下文

---

### 5. APScheduler任务持久化 ✅

**问题**: 是否需要手动定义 `apscheduler_jobs` 表？

**解决方案**:
- **使用**: SQLAlchemy Job Store（APScheduler自动创建表）
- **不手动定义**: 不在 `schema.py` 中定义表，避免与APScheduler内部结构冲突
- **实现**: `backend/services/collection_scheduler.py` 中使用 `SQLAlchemyJobStore`

---

### 6. tasks.md编号修复 ✅

**问题**: `1.5.6` 出现两次（任务截图API和验证基础API）

**解决方案**:
- 将第二个 `1.5.6` 改为 `1.5.8`
- 保持编号连续性

---

### 7. Amazon平台移除 ✅

**问题**: 提案说Non-Goal不支持Amazon，但代码中仍有Amazon

**解决方案**:
- **移除**: 从 `backend/routers/collection.py` 的 `get_collection_platforms()` 移除 `amazon`
- **保留**: `local_accounts.py` 中的Amazon账号配置保留（不影响，只是不显示在平台列表）
- **文档**: 在 `proposal.md` 和 `design.md` 中明确说明不支持Amazon

---

### 8. 数据域变更 ✅

**问题**: `traffic` → `analytics` 的向后兼容性

**解决方案**:
- **不考虑历史兼容**: 前端表单中已不存在 `traffic` 选项
- **统一使用**: `analytics` 作为标准数据域名称

---

### 9. 数据模块清理计划 ✅

**问题**: 旧版数据采集模块何时清理？

**解决方案**:
- **Phase 1**: Phase 2完成后（新系统上线后）
  - 归档旧版完整脚本录制文件到 `backups/2025XX_collection_legacy_scripts/`
  - 保留 `handlers.py` 的CLI功能（标记为deprecated）
- **Phase 2**: Phase 4完成后（稳定运行1个月后）
  - 评估CLI功能使用情况
  - 如果新系统稳定，移除CLI录制向导代码
  - 归档 `handlers.py` 中的legacy方法

**清理原则**:
- ✅ 保留兼容性：新系统上线后保留CLI功能1个月
- ✅ 渐进式清理：分阶段清理，确保不影响现有用户
- ✅ 完整归档：所有清理的代码必须归档到 `backups/` 目录
- ✅ 文档更新：清理后更新相关文档和CHANGELOG

---

### 10. 录制流程详细说明 ✅

**问题**: 如何从0开始录制新的数据域（如Shopee服务数据-人工服务子域）？

**解决方案**: 已提供完整的录制流程指南（见 `design.md` D3章节补充）

**关键步骤**:
1. 检查前置组件（login/navigation/date_picker）- 不存在则先录制
2. 录制目标组件（services_export.yaml）- 支持子域参数
3. 测试组件（使用 `tools/test_component.py`）
4. 端到端测试（通过API创建采集任务）

---

### 11. 弹窗处理方案 ✅（新增）

**问题**: 不同平台的意外弹窗或通知弹窗如何处理？

**解决方案**: 三层弹窗处理机制

**架构设计**:
1. **通用弹窗处理器** (`UniversalPopupHandler`)
   - 处理所有平台的常见弹窗
   - 通用选择器列表（30+选择器）
   - 支持iframe、ESC键兜底、轮询策略

2. **平台特定弹窗配置** (`popup_config.yaml`)
   - 每个平台一个配置文件
   - 平台特定选择器
   - 平台特定轮询策略

3. **组件级弹窗处理** (组件YAML配置)
   - `popup_handling` 配置段
   - 步骤级弹窗处理
   - 自动/手动控制

**实现位置**:
- `modules/apps/collection_center/popup_handler.py` - 通用处理器
- `config/collection_components/{platform}/popup_config.yaml` - 平台配置
- 组件YAML中的 `popup_handling` 配置段

---

### 12. 系统可靠性漏洞修复 ✅（安全审查后新增）

**问题**: 提案审查发现多个潜在漏洞

**发现的漏洞**:

| 风险等级 | 漏洞 | 解决方案 |
|---------|------|---------|
| 🔴 高 | WebSocket未认证 | JWT Token认证，连接时验证 |
| 🔴 高 | 浏览器进程泄漏 | 启动时+定期清理孤儿进程 |
| 🟡 中 | 任务状态竞态 | 使用乐观锁防止并发更新冲突 |
| 🟡 中 | 排队任务不启动 | 任务完成回调触发启动 |
| 🟡 中 | 组件YAML注入 | selector安全验证 |
| 🟡 中 | 文件注册失败 | 事务保证原子性，失败回滚 |
| 🟢 低 | 临时文件堆积 | 定时清理（下载7天、截图30天） |
| 🟢 低 | API端点不一致 | 统一使用查询参数 |
| 🟢 低 | 缺少健康检查 | 添加健康检查端点 |

**实现位置**:
- `backend/routers/collection_websocket.py` - WebSocket JWT认证
- `backend/services/cleanup_service.py` - 临时文件清理
- `backend/services/task_service.py` - 乐观锁更新
- `backend/services/task_queue_service.py` - 排队任务自动启动
- `backend/services/file_processing_service.py` - 文件注册原子性
- `modules/apps/collection_center/component_loader.py` - 组件安全验证

---

## 📊 提案评估结果

### ✅ 提案设计评估

| 评估项 | 结果 | 说明 |
|--------|------|------|
| **项目要求匹配度** | ✅ 100% | 满足所有核心要求，部分功能超出预期 |
| **技术可行性** | ✅ 高 | 基于现有技术栈，无技术风险 |
| **架构合理性** | ✅ 优秀 | 组件驱动架构清晰，可维护性强 |
| **实施计划** | ✅ 完整 | 5个Phase，15-17天，任务分解详细 |
| **风险评估** | ✅ 充分 | 识别7个风险，均有缓解措施 |

### 🎯 关键决策确认

1. ✅ **账号配置**: 从 `local_accounts.py` 读取，API脱敏返回
2. ✅ **组件架构**: Phase 1不实现高级特性，后续版本支持
3. ✅ **验证码处理**: 5分钟超时，保持paused状态，用户选择操作
4. ✅ **任务恢复**: Resume从暂停点继续，Retry重新开始
5. ✅ **弹窗处理**: 三层机制（通用+平台特定+组件级）
6. ✅ **数据清理**: 分两阶段渐进式清理
7. ✅ **WebSocket安全**: JWT Token认证
8. ✅ **资源管理**: 孤儿浏览器进程清理、临时文件定时清理
9. ✅ **并发安全**: 乐观锁、排队任务自动启动
10. ✅ **数据一致性**: 文件注册原子性、事务回滚

---

## 📝 需要更新的文件

### 必须更新
1. ✅ `proposal.md` - 添加澄清问题和解决方案、系统可靠性增强
2. ✅ `design.md` - 添加弹窗处理设计、账号配置设计、验证码处理细节、可靠性机制（D21-D25）
3. ✅ `tasks.md` - 修复编号错误，添加弹窗处理任务、可靠性增强任务（1.6节）
4. ✅ `specs/data-collection/spec.md` - 添加弹窗处理需求、系统可靠性需求（9个新Requirement）

### 可选更新
5. `docs/guides/component_recording.md` - 录制流程详细指南（如果不存在）
6. `docs/guides/popup_handling.md` - 弹窗处理使用指南（新增）

---

## 🚀 下一步行动

1. ✅ **更新提案文件** - 根据对话总结更新所有相关文件
2. ⏳ **开始开发** - Phase 1: 组件系统基础架构
3. ⏳ **录制工具开发** - 实现 `tools/record_component.py`
4. ⏳ **组件录制** - 录制Shopee平台核心组件

---

## 📚 参考文档

- [组件驱动架构设计](design.md#d1-组件驱动架构设计)
- [弹窗处理方案设计](design.md#d16-弹窗处理方案设计)（新增）
- [账号配置设计](design.md#账号配置来源设计)（新增）
- [验证码处理流程](design.md#d13-远程验证码处理流程)
- [录制流程指南](design.md#d3-组件录制工具设计)

---

**审查结论**: ✅ **提案设计完整，所有疑问已澄清，可以开始实施开发**

