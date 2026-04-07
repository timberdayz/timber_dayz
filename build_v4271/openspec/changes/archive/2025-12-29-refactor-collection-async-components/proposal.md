# Change: 数据采集模块异步化改造与 Python 组件集成

## Why

当前数据采集模块存在以下问题：

1. **YAML 驱动局限性**：YAML 格式无法处理复杂的 Playwright 操作（如悬停、动态下拉框、iframe 遍历、2FA 验证等）
2. **同步 API 不兼容**：现有 Python 组件使用同步 Playwright API，无法在 FastAPI 异步框架中直接使用
3. **组件未集成**：`modules/platforms/`下的成熟 Python 组件（38 个文件）未与 executor_v2 集成
4. **密码解密分散**：登录组件的密码解密逻辑不统一，部分直接读取明文
5. **日志不兼容**：组件中使用 emoji 字符，在 Windows 控制台导致 UnicodeEncodeError

旧项目的 Python 组件已经过实际验证，包含完善的：

- 弹窗处理机制
- 等待和重试逻辑
- 多层降级策略（UI 监听 → 文件系统兜底 → API 兜底）
- 2FA 验证处理
- iframe 遍历逻辑

**差异对比结果**（已通过`scripts/compare_legacy_components.py`验证）：

- 34 个文件完全相同（无需迁移）
- 4 个文件有微小差异（新版本已更新数据域命名，保留 target 版本）
- 0 个文件仅在 legacy 中存在

## What Changes

### 阶段 1：核心改造（P0）

1. **同步转异步改造**

   - 将 38 个 Python 组件从`sync_playwright`改为`async_playwright`
   - 所有方法添加`async`关键字，所有 Playwright 调用添加`await`
   - 修改`while`循环等待逻辑为异步等待

2. **密码解密统一**

   - 创建统一的密码解密辅助方法
   - 修改 3 个登录组件使用解密后的密码
   - 处理解密失败的降级逻辑

3. **日志 Emoji 替换**
   - 替换所有 emoji 为 ASCII 符号（如`[OK]`、`[ERROR]`）
   - 确保 Windows 控制台兼容性

### 阶段 2：集成开发（P1）

4. **创建 Python 组件适配层**

   - 新建`modules/apps/collection_center/python_component_adapter.py`
   - 封装 PlatformAdapter 调用
   - 提供统一的组件执行接口

5. **修改 executor_v2 仅支持 Python 组件**

   - 移除 YAML 组件执行逻辑
   - 移除组件类型判断（统一使用 Python 组件）
   - 简化组件加载流程

6. **组件加载器重构**

   - 移除 YAML 组件加载逻辑
   - 仅支持 Python 组件加载（`load_python_component()`）
   - 支持组件路径解析（如 `shopee/products_export`）

7. **录制工具优化**
   - 移除 Codegen 模式支持
   - 仅保留 Inspector 模式（`tools/launch_inspector_recorder.py`）
   - 优化 Trace 解析生成 Python 组件骨架

### 阶段 3：数据同步对齐（P0）

8. **文件命名标准化**

   - 使用 `StandardFileName.generate()` 生成标准文件名
   - 格式：`{platform}_{data_domain}[_{sub_domain}]_{granularity}_{timestamp}.xlsx`
   - 替换原有的 `build_filename()` 方法

9. **文件存储路径标准化**

   - 采集完成后移动文件到 `data/raw/YYYY/`（年份分区）
   - 数据同步模块仅扫描此目录
   - 删除 `temp/outputs/` 中的临时文件

10. **伴生文件格式标准化**

    - 使用 `MetadataManager.create_meta_file()` 生成 `.meta.json` 文件
    - 伴生文件与数据文件同目录（`data/raw/YYYY/`）
    - 包含完整的 `business_metadata` 和 `collection_info`

11. **文件注册自动化**

    - 采集完成后自动调用 `register_single_file()` 注册到 `catalog_files` 表
    - 确保数据同步模块可以识别新文件

12. **Python 组件测试工具更新**
    - 更新 `tools/test_component.py` 支持 Python 组件
    - 更新 `tools/run_component_test.py` 支持 `.py` 文件路径
    - 更新 `backend/routers/component_versions.py` 支持 Python 组件测试

### 阶段 4：组件管理功能完善（P0）

13. **YAML 组件清理**

    - 创建清理脚本 `scripts/cleanup_yaml_components.py`
    - 移动 YAML 文件到 `backups/yaml_components_YYYYMMDD/`
    - 禁用 ComponentVersion 表中所有 `.yaml` 路径的记录
    - 添加 `[已废弃 - YAML组件已迁移到Python]` 到 description

14. **Python 组件自动注册**

    - 创建批量注册脚本 `scripts/register_python_components.py`
    - 使用 `ComponentLoader.list_python_components()` 扫描所有平台
    - 检查 `component_name + file_path` 是否已存在，已存在则跳过
    - 新组件注册为 `1.0.0` 版本

15. **批量注册 API 端点**

    - `POST /component-versions/batch-register-python`
    - 参数：`platform: Optional[str]`（可选）
    - 返回：注册统计和详细信息

16. **组件录制工具保存逻辑更新**

    - 更新 `RecorderSaveRequest` 支持 `python_code` 和 `data_domain`
    - 保存到 `modules/platforms/{platform}/components/{name}.py`
    - 实现更新覆盖逻辑（稳定版本更新不创建新版本）
    - 验证 Python 代码语法（`ast.parse`）

17. **前端组件管理功能**

    - 添加"批量注册 Python 组件"按钮
    - 显示组件类型标识（Python/YAML）
    - 更新保存功能发送 `python_code`

18. **稳定版本唯一性保证**
    - 增强 `promote_to_stable()` 自动取消相同文件路径的其他稳定版本
    - 完善 `save_component` 更新逻辑

### 不变更的内容

- **保留 migration_temp 目录**：作为备份，不删除
- **不修改数据库模型**：使用现有的 catalog_files 等表
- **保留组件版本管理**：ComponentVersion 表继续使用

## Impact

### 受影响的 Specs

- `data-collection`：新增异步组件执行要求

### 受影响的代码

| 目录/文件                                                    | 变更类型                     | 文件数 |
| ------------------------------------------------------------ | ---------------------------- | ------ |
| `modules/platforms/shopee/components/*.py`                   | 修改（异步化+文件命名）      | 17     |
| `modules/platforms/tiktok/components/*.py`                   | 修改（异步化+文件命名）      | 12     |
| `modules/platforms/miaoshou/components/*.py`                 | 修改（异步化+文件命名）      | 9      |
| `modules/apps/collection_center/python_component_adapter.py` | 新增                         | 1      |
| `modules/apps/collection_center/executor_v2.py`              | 修改（+文件处理）            | 1      |
| `modules/apps/collection_center/component_loader.py`         | 修改                         | 1      |
| `tools/test_component.py`                                    | 修改（支持 Python 组件）     | 1      |
| `tools/run_component_test.py`                                | 修改（支持.py 路径）         | 1      |
| `backend/routers/component_versions.py`                      | 修改（支持 Python 组件测试） | 1      |
| `backend/routers/component_recorder.py`                      | 修改（Python 代码保存）      | 1      |
| `scripts/cleanup_yaml_components.py`                         | 新增                         | 1      |
| `scripts/register_python_components.py`                      | 新增                         | 1      |
| `frontend/src/views/collection/ComponentVersions.vue`        | 修改（批量注册+类型显示）    | 1      |
| `frontend/src/views/collection/ComponentRecorder.vue`        | 修改（Python 代码保存）      | 1      |

### 风险评估

| 风险                      | 概率 | 影响 | 缓解措施                 |
| ------------------------- | ---- | ---- | ------------------------ |
| 异步改造遗漏同步调用      | 中   | 高   | 使用类型检查和运行时检测 |
| 等待逻辑失效              | 中   | 中   | 逐个组件测试             |
| component_call 机制缺失   | 中   | 高   | 在适配层实现组件调用方法 |
| ComponentVersion 迁移失败 | 低   | 中   | 数据迁移脚本 + 回滚计划  |
| Trace 解析器生成代码质量  | 中   | 中   | 人工审核生成的代码骨架   |

### 工作量估算

| 阶段     | 任务                         | 工作量         |
| -------- | ---------------------------- | -------------- |
| 阶段 1   | 同步转异步改造               | 2-3 天         |
| 阶段 1   | 密码解密统一                 | 0.5 天         |
| 阶段 1   | 日志 Emoji 替换              | 0.5 天         |
| 阶段 2   | Python 组件适配层            | 0.5 天         |
| 阶段 2   | executor_v2 重构             | 1 天           |
| 阶段 2   | 组件加载器重构               | 0.5 天         |
| 阶段 2   | 录制工具优化（移除 Codegen） | 0.5 天         |
| 阶段 2   | ComponentVersion 迁移        | 0.5 天         |
| 阶段 3   | 文件命名标准化               | 0.5 天         |
| 阶段 3   | 文件存储路径标准化           | 0.5 天         |
| 阶段 3   | 伴生文件格式标准化           | 0.5 天         |
| 阶段 3   | 文件注册自动化               | 0.5 天         |
| 阶段 3   | Python 组件测试工具更新      | 1 天           |
| 阶段 4   | YAML 组件清理                | 0.5 天         |
| 阶段 4   | Python 组件批量注册          | 0.5 天         |
| 阶段 4   | 批量注册 API + 前端          | 1 天           |
| 阶段 4   | 录制工具保存逻辑更新         | 0.5 天         |
| 阶段 5   | 测试验证                     | 2 天           |
| **总计** |                              | **13.5-14.5 天** |

---

## 当前状态（2025-12-29）

### 已完成工作

#### ✅ 阶段 1：核心改造（100% 完成）
- **同步转异步改造**：38 个 Python 组件全部完成异步化
  - Shopee 平台：11 个组件（login, navigation, date_picker, export, orders_export, products_export, finance_export, services_export, analytics_export, metrics_selector）
  - TikTok 平台：5 个组件（login, navigation, date_picker, export, shop_selector）
  - Miaoshou 平台：4 个组件（login, navigation, date_picker, export）
- **密码解密统一**：在 `PythonComponentAdapter` 中实现统一解密逻辑
- **日志 Emoji 替换**：所有组件中的 emoji 已替换为 ASCII 符号

#### ✅ 阶段 2：集成开发（90% 完成）
- **Python 组件适配层**：`python_component_adapter.py` 已创建并实现核心功能
- **executor_v2 重构**：已支持 Python 组件执行，文件处理逻辑已对齐数据同步模块
- **组件加载器重构**：已实现 Python 组件加载和验证
- **录制工具优化**：已移除 Codegen 模式，仅保留 Inspector 模式
- **Trace 解析器**：已实现 Python 代码骨架生成

#### ✅ 阶段 3：数据同步对齐（100% 完成）
- **文件命名标准化**：使用 `StandardFileName.generate()` 生成标准文件名
- **文件存储路径标准化**：采集文件保存到 `data/raw/YYYY/` 目录
- **伴生文件格式标准化**：使用 `MetadataManager.create_meta_file()` 生成 `.meta.json` 文件
- **文件注册自动化**：采集完成后自动注册到 `catalog_files` 表
- **Python 组件测试工具更新**：`tools/test_component.py` 已支持 Python 组件测试

#### ✅ 阶段 4：组件管理功能完善（95% 完成）
- **YAML 组件清理脚本**：`scripts/cleanup_yaml_components.py` 已创建
- **Python 组件批量注册脚本**：`scripts/register_python_components.py` 已创建并修复（排除 config 文件）
- **批量注册 API 端点**：`POST /component-versions/batch-register-python` 已实现
- **组件录制工具保存逻辑**：已支持保存 Python 组件到 `modules/platforms/{platform}/components/`
- **前端组件管理功能**：已添加批量注册按钮和组件类型显示
- **稳定版本唯一性保证**：`promote_to_stable()` 已增强
- **Config 文件过滤**：后端 API 和注册脚本已添加过滤逻辑，清理了 14 个错误注册的 config 组件

#### ⚠️ 阶段 5：测试验证（30% 完成）
- ✅ 架构验证脚本通过
- ✅ Contract-First 验证通过
- ✅ 组件元数据验证通过（8 个缺失元数据的组件已修复）
- ❌ 完整采集流程测试（需要实际环境）
- ❌ 数据同步模块扫描验证（需要实际环境）
- ❌ 前端组件测试功能验证（存在已知问题）

### 已知问题

1. **组件测试功能不稳定**
   - 部分组件（除 login 外）在测试时出现错误
   - 组件加载和验证逻辑需要进一步优化
   - 测试结果状态判断逻辑存在边界情况

2. **组件元数据不完整**
   - 部分组件缺少 `platform`、`component_type`、`data_domain` 元数据（已修复 8 个）
   - 需要全面检查所有组件的元数据完整性

3. **组件调用机制待验证**
   - Python 组件调用子组件的机制已实现，但未经过完整测试
   - 需要验证导出组件调用 date_picker、navigation 等子组件的场景

4. **文件处理流程待验证**
   - 文件命名、存储路径、伴生文件生成已实现，但未经过端到端测试
   - 需要验证数据同步模块能否正确扫描和处理采集的文件

### 搁置原因

由于系统着急上线，数据采集模块的优化工作暂时搁置，原因如下：

1. **测试验证不完整**：大量功能已实现但未经过完整测试，存在未知风险
2. **已知问题较多**：组件测试功能不稳定，可能影响生产环境使用
3. **时间紧迫**：完整测试和问题修复需要额外 2-3 天时间
4. **风险控制**：为避免影响系统上线，优先保证核心功能稳定

### 后续计划

待系统上线稳定后，继续完成以下工作：

1. **问题修复**（优先级 P0）
   - 修复组件测试功能的问题
   - 完善组件元数据完整性检查
   - 验证组件调用机制

2. **测试验证**（优先级 P0）
   - 运行完整采集流程测试
   - 验证数据同步模块扫描功能
   - 前端组件测试功能验证

3. **文档完善**（优先级 P1）
   - 更新 `.cursorrules` 中的组件开发规范
   - 更新数据采集模块文件处理文档
   - 编写组件开发最佳实践

4. **代码优化**（优先级 P2）
   - 编写适配层单元测试
   - 编写 executor 集成测试
   - 优化组件加载性能

### 归档说明

本提案已完成大部分核心功能开发，但由于测试验证不完整和已知问题，暂时搁置。已完成的工作已提交到代码库，未完成的工作和已知问题已记录在本文档中，待系统上线稳定后继续完成。
