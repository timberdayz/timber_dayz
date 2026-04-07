# 数据采集模块优化 - OpenSpec提案

**提案ID**: `verify-collection-and-sync-e2e`  
**创建时间**: 2025-12-19  
**状态**: ✅ 提案已验证，等待实施

---

## 📋 提案概述

### 目标

验证并完善数据采集和同步的完整管道，确保生产环境可部署。

### 范围

- **数据采集**: 验证录制工具、更新组件YAML、测试端到端流程
- **数据同步**: 验证同步API、定时任务、数据完整性
- **云端部署**: 检查环境变量、Docker配置、无头浏览器

---

## 📂 提案文件

| 文件 | 说明 | 状态 |
|------|------|------|
| [proposal.md](./proposal.md) | 提案说明（Why/What/Impact） | ✅ 完成 |
| [tasks.md](./tasks.md) | 详细任务清单（7个Phase） | ✅ 完成 |
| [specs/data-collection/spec.md](./specs/data-collection/spec.md) | 数据采集规格变更 | ✅ 完成 |
| [specs/data-sync/spec.md](./specs/data-sync/spec.md) | 数据同步规格变更 | ✅ 完成 |
| [CURRENT_STATUS.md](./CURRENT_STATUS.md) | 系统当前状态分析 | ✅ 完成 |
| [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md) | 实施指南 | ✅ 完成 |

---

## 🎯 关键发现

### ✅ 已完成的工作

1. **架构代码100%完成**
   - 录制工具: 902行，功能完整
   - 执行引擎: 2212行，功能完整
   - 前端界面: 3个页面全部实现
   - 数据同步API: 完整实现

2. **系统服务全部运行**
   - ✅ PostgreSQL: healthy
   - ✅ 后端API: localhost:8001
   - ✅ 前端: localhost:5173
   - ✅ Metabase: localhost:8080

3. **合规性验证通过**
   - ✅ SSOT架构: 100%
   - ✅ Contract-First: 重复定义已修复
   - ✅ 无硬编码路径

### ⚠️ 待完成的工作

1. **组件YAML需要实际录制**
   - ❌ login.yaml: 包含TODO占位符
   - ❌ navigation.yaml: 包含TODO占位符
   - ⚠️ orders_export.yaml: 通用选择器

2. **端到端流程未验证**
   - ⏸️ 采集流程
   - ⏸️ 同步流程
   - ⏸️ 定时任务

3. **物化视图无定时刷新**
   - ❌ APScheduler未注册刷新任务
   - ⚠️ 建议添加（每天凌晨2点）

---

## 🚀 快速开始

### 1. 查看实施指南

```bash
cat openspec/changes/verify-collection-and-sync-e2e/IMPLEMENTATION_GUIDE.md
```

### 2. 运行基础验证测试

```bash
# 验证系统基础功能（不需要真实账号）
pytest tests/e2e/test_complete_collection_to_sync.py -v -k "not manual"

# 预期: 14/14 passed, 2 skipped
```

### 3. 准备录制环境

**需要提供**:
- 妙手ERP账号ID或凭证
- 确认网络可访问妙手ERP
- 确认Playwright已安装

### 4. 执行录制（用户操作）

```bash
# 录制登录组件
python tools/record_component.py \
  --platform miaoshou \
  --component login \
  --account {YOUR_ACCOUNT_ID}

# 录制导航组件
python tools/record_component.py \
  --platform miaoshou \
  --component navigation \
  --account {YOUR_ACCOUNT_ID}

# 录制导出组件
python tools/record_component.py \
  --platform miaoshou \
  --component export \
  --account {YOUR_ACCOUNT_ID}
```

### 5. 端到端测试（用户操作）

- 访问: http://localhost:5173/collection-tasks
- 点击"快速采集"
- 选择妙手ERP + orders + 昨天
- 观察执行过程
- 验证结果

---

## 📊 验证结果

### 提案验证

```bash
$ openspec validate verify-collection-and-sync-e2e --strict
✅ Change 'verify-collection-and-sync-e2e' is valid
```

### SSOT验证

```bash
$ python scripts/verify_architecture_ssot.py
✅ Compliance Rate: 100.0%
✅ Architecture complies with Enterprise ERP SSOT standard
```

### Contract-First验证

```bash
$ python scripts/verify_contract_first.py
✅ No duplicate Pydantic model definitions found
⚠️ response_model coverage: 35% (不阻塞，作为改进项)
```

---

## 🔗 相关资源

### 文档

- [OpenSpec指南](../../openspec/AGENTS.md)
- [组件录制指南](../../docs/guides/component_recording.md)
- [环境变量配置](../../docs/deployment/CLOUD_ENVIRONMENT_VARIABLES.md)
- [开发规范](.cursorrules)
- [Playwright使用规范](./proposal.md#playwright-使用规范2025-12-21-新增) ⭐⭐⭐ **新增：避免重复实现问题**

### 代码

- [录制工具](../../tools/record_component.py)
- [测试工具](../../tools/test_component.py)
- [执行引擎](../../modules/apps/collection_center/executor_v2.py)
- [组件加载器](../../modules/apps/collection_center/component_loader.py)

### 配置

- [妙手ERP组件](../../config/collection_components/miaoshou/)
- [Shopee组件](../../config/collection_components/shopee/)
- [TikTok组件](../../config/collection_components/tiktok/)

---

## 📈 预期收益

**完成阶段1后**:
- 功能完整性: 75% → 90%
- 生产就绪度: 60% → 80%
- 核心流程可用: orders域采集和同步

**完成阶段2后**:
- 功能完整性: 90% → 95%
- 生产就绪度: 80% → 95%
- 所有数据域可用: 6个域全部支持

---

## ✅ 批准和实施

### 提案状态
- ✅ 提案已创建
- ✅ OpenSpec验证通过
- ✅ 合规性检查通过
- ⏸️ 等待用户批准和提供账号信息

### 实施流程

1. 用户提供妙手ERP账号信息
2. 执行组件录制（1-1.5小时）
3. 端到端测试（30分钟）
4. 数据同步验证（30分钟）
5. 创建测试报告
6. 归档提案（`openspec archive verify-collection-and-sync-e2e`）

---

**准备好开始了吗？** 🚀

提供妙手ERP账号信息，我们就可以开始录制和测试！
