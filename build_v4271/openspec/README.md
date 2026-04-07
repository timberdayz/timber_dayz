# OpenSpec 规范文档

## 📋 概述

本项目使用 OpenSpec 进行规范驱动开发（Spec-Driven Development）。本文档说明如何使用 OpenSpec 工作流。

## 📁 目录结构

```
openspec/
├── project.md              # 项目上下文和规范（已填充）
├── AGENTS.md               # OpenSpec工作流说明文档
├── specs/                  # 当前已实现功能的规范
│   ├── data-collection/    # 数据采集中心
│   ├── field-mapping/      # 字段映射系统
│   ├── data-sync/          # 数据同步
│   ├── finance-management/ # 财务管理
│   ├── dashboard/         # 数据看板
│   └── materialized-views/# 物化视图语义层
└── changes/                # 变更提案（待实施的功能）
    └── archive/            # 已完成的变更
```

## ✅ 已完成的工作

### 1. 项目上下文文档
- ✅ `openspec/project.md` - 完整的项目上下文，包括：
  - 项目目的和目标
  - 技术栈（后端/前端/基础设施）
  - 项目规范（代码风格/架构模式/测试策略/Git工作流）
  - 领域上下文（跨境电商业务领域）
  - 重要约束（技术/业务/开发/安全约束）
  - 外部依赖

### 2. 核心功能规范
已为以下核心功能创建了初始规范（所有规范文件已翻译成中文）：

#### ✅ 数据采集中心 (`specs/data-collection/`)
- 多平台数据采集（Shopee/TikTok/Amazon/妙手ERP）
- Playwright反检测技术
- 文件注册和元数据索引
- 账号配置管理
- 7个数据域支持
- 采集状态监控

#### ✅ 字段映射系统 (`specs/field-mapping/`)
- 智能字段识别（AI驱动）
- 四层映射架构
- Pattern-based Mapping
- 全球货币支持（180+货币）
- 7个数据域支持
- 模板系统
- 数据隔离区
- 时间字段自动检测

#### ✅ 数据同步 (`specs/data-sync/`)
- 单文件数据同步
- 批量数据同步
- 异步处理和并发控制（FastAPI BackgroundTasks）
- 进度跟踪和历史记录（数据库持久化）
- 数据质量Gate检查
- 错误处理和重试机制
- 与数据采集、字段映射、数据入库系统集成

#### ✅ 财务管理 (`specs/finance-management/`)
- CNY本位币
- Universal Journal
- 移动加权平均成本
- 三单匹配（PO-GRN-Invoice）
- 费用分摊引擎
- 应收账款管理
- 应付账款管理
- 税务合规
- 财务报表

#### ✅ 数据看板 (`specs/dashboard/`)
- 销售看板（KPI、趋势图、平台对比）
- 库存看板（库存概览、低库存预警、周转率分析）
- 财务看板（财务KPI、利润趋势、费用分解）
- 店铺健康看板（健康评分、风险等级、趋势分析）
- 实时数据更新
- 数据筛选和钻取
- 响应式设计

#### ✅ 物化视图语义层 (`specs/materialized-views/`)
- 18个物化视图（产品5个、销售5个、财务3个、库存3个、C类数据2个）
- 一键刷新（依赖管理）
- 刷新历史记录
- 自动定时刷新（每天凌晨2点）
- 业务域分类
- 视图健康监控
- 性能优化
- One View Multiple Pages模式

## 🚀 下一步工作

### 选项1：创建变更提案
当需要添加新功能或进行重大变更时：
1. 使用命令 `/openspec-proposal` 或手动创建变更提案
2. 在 `openspec/changes/[change-id]/` 目录下创建：
   - `proposal.md` - 为什么、改什么、影响范围
   - `tasks.md` - 实施清单
   - `design.md` - 技术决策（可选）
   - `specs/[capability]/spec.md` - 规范增量文件

### 选项2：实施已批准的变更
当变更提案被批准后：
1. 使用命令 `/openspec-apply` 或按照 `tasks.md` 逐项实施
2. 完成后将所有任务标记为 `- [x]`
3. 部署后归档变更到 `changes/archive/`

### 选项3：学习 OpenSpec 工作流
详细阅读 `openspec/AGENTS.md` 了解：
- 三阶段工作流（创建变更 → 实施变更 → 归档变更）
- 规范文件格式要求
- 场景格式要求（`#### Scenario:`）
- 变更提案结构

## 📖 快速参考

### CLI命令
```bash
# 列出所有规范
openspec list --specs

# 列出所有变更提案
openspec list

# 查看规范详情
openspec show data-collection --type spec

# 查看变更提案详情
openspec show <change-id>

# 验证规范
openspec validate --specs --strict

# 验证变更提案
openspec validate <change-id> --strict

# 归档已完成的变更
openspec archive <change-id> --yes
```

### 规范文件格式
- 使用 `## Requirements` 作为主标题
- 每个需求使用 `### Requirement: [名称]` 格式
- 每个需求必须包含至少一个场景
- 场景使用 `#### Scenario: [名称]` 格式
- 场景内容使用 `- **WHEN** ...` 和 `- **THEN** ...` 格式

### 变更提案格式
- 使用 `## ADDED Requirements` 添加新功能
- 使用 `## MODIFIED Requirements` 修改现有功能
- 使用 `## REMOVED Requirements` 移除功能
- 使用 `## RENAMED Requirements` 重命名功能

## 🔗 相关文档

- [OpenSpec工作流说明](AGENTS.md) - 详细的工作流和规范说明
- [项目上下文](project.md) - 项目技术栈、规范和约束
- [项目README](../README.md) - 项目总体说明

## 📝 注意事项

1. **规范是真理**：`specs/` 目录中的规范代表当前已实现的功能
2. **变更是提案**：`changes/` 目录中的变更提案代表计划中的功能
3. **保持同步**：实施变更后，必须更新 `specs/` 中的规范
4. **验证严格**：创建变更提案后，必须运行 `openspec validate --strict` 验证
5. **归档及时**：部署完成后，及时归档变更到 `changes/archive/`
6. **语言规范**：所有spec文件使用中文编写，保持与项目文档一致

