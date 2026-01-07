# Design: 数据采集模块异步化改造与 Python 组件集成

## Context

### 背景

西虹 ERP 的数据采集模块当前使用两套并行的组件系统：

1. **YAML 组件**：通过`component_loader.py`加载，由`executor_v2.py`执行（**将被废弃**）
2. **Python 组件**：位于`modules/platforms/`，但未与 executor 集成（**将统一使用**）

旧项目（CLI 版本）的 Python 组件已经过实际采集验证，包含成熟的：

- 弹窗处理（`overlay_guard.py`）
- 等待和重试逻辑
- 多层降级策略
- 2FA 验证处理（TikTok）
- iframe 遍历

通过差异对比（`scripts/compare_legacy_components.py`），发现：

- `modules/platforms/`与`migration_temp/legacy_components/`中的 38 个组件文件几乎完全相同
- 4 个文件有微小差异（数据域命名更新），新版本更优

**决策**：移除 YAML 组件支持，避免双维护问题，统一使用 Python 组件。

### 约束

1. **FastAPI 异步框架**：所有 Playwright 调用必须使用`async_playwright`
2. **Windows 平台**：禁止使用 emoji 字符（UnicodeEncodeError）
3. **仅 Python 组件**：移除 YAML 组件支持，避免双维护
4. **仅 Inspector 模式**：移除 Codegen 模式，仅使用 Inspector API 录制
5. **SSOT 原则**：Python 组件只在`modules/platforms/`定义，不重复

### 利益相关者

- 数据采集用户：需要稳定可靠的自动化采集
- 开发人员：需要清晰的组件开发规范
- 运维人员：需要监控和日志支持

## Goals / Non-Goals

### Goals

1. ✅ 将 38 个 Python 组件改造为异步版本，兼容 FastAPI
2. ✅ 创建 Python 组件适配层，与 executor_v2 集成
3. ✅ 统一密码解密逻辑
4. ✅ 修复 Windows 日志兼容性问题
5. ✅ 移除 YAML 组件支持，统一使用 Python 组件
6. ✅ 移除 Codegen 模式，仅使用 Inspector 模式录制

### Non-Goals

1. ❌ 不删除 migration_temp 备份目录
2. ❌ 不重写组件业务逻辑（仅做异步改造）
3. ❌ 不修改数据库模型
4. ❌ 不保留 YAML 组件支持（避免双维护）

## Decisions

### Decision 1: 异步 API 选择

**决策**：使用`async_playwright`替换`sync_playwright`

**理由**：

- Playwright 官方建议在异步框架中使用`async_playwright`
- 避免事件循环冲突（`RuntimeError: Event loop is running`）
- 简化代码，无需线程/进程隔离

**替代方案**：

- ~~`sync_playwright` + threading~~：违反官方建议，复杂度高
- ~~`sync_playwright` + subprocess~~：进程间通信复杂，调试困难

### Decision 2: 组件适配层设计

**决策**：创建`PythonComponentAdapter`作为统一入口

```python
# modules/apps/collection_center/python_component_adapter.py

class PythonComponentAdapter:
    def __init__(self, platform: str, account: dict, config: dict = None, logger=None):
        self.ctx = ExecutionContext(...)
        self.adapter = PLATFORM_ADAPTERS[platform](self.ctx)

    async def login(self, page) -> dict:
        component = self.adapter.login()
        return await component.run(page)

    async def navigate(self, page, target_page) -> dict:
        component = self.adapter.navigation()
        return await component.run(page, target_page)

    async def export(self, page, data_domain: str) -> dict:
        exporter = self._get_exporter(data_domain)
        return await exporter.run(page)
```

**理由**：

- 统一的入口点，便于 executor 调用
- 集中处理账号预处理（密码解密）
- 便于后续扩展

### Decision 3: 密码解密统一

**决策**：在适配层统一解密密码

```python
def _prepare_account(self, account: dict) -> dict:
    prepared = account.copy()
    if "password_encrypted" in prepared:
        try:
            svc = get_encryption_service()
            prepared["password"] = svc.decrypt_password(prepared["password_encrypted"])
        except Exception:
            # 降级：使用原值
            pass
    return prepared
```

**理由**：

- 集中管理，避免重复代码
- 降级策略确保兼容性
- 遵循现有加密服务规范

### Decision 4: 日志规范化

**决策**：使用 ASCII 符号替代 emoji

| 原 emoji | 替换为         |
| -------- | -------------- |
| ✅ ✓     | [OK] [PASS]    |
| ❌ ✗     | [FAIL] [ERROR] |
| ⚠️       | [WARN]         |
| ℹ️       | [INFO]         |
| 🔐       | [AUTH]         |
| ⏱️       | [WAIT]         |

**理由**：

- Windows 控制台默认 GBK 编码，无法处理 emoji
- 保持日志可读性
- 遵循`.cursorrules`规范

### Decision 5: 仅支持 Python 组件

**决策**：executor_v2 仅支持 Python 组件，移除 YAML 组件支持

```python
async def _execute_component(self, page, component_name, ...):
    # 统一使用Python组件
    adapter = PythonComponentAdapter(platform, account, config, logger)
    return await adapter.execute_component(page, component_name, ...)
```

**理由**：

- 避免 YAML 和 Python 双维护问题
- 简化代码逻辑，降低维护成本
- Python 组件功能更强大，支持复杂操作
- 旧 YAML 组件已基本废弃

### Decision 6: 仅使用 Inspector 模式录制

**决策**：移除 Codegen 模式，仅使用 Inspector API 录制

**理由**：

- Inspector 模式功能更强大（持久化会话、固定指纹、Trace 回放）
- Codegen 模式不稳定，不适合复杂场景
- 统一录制模式，降低维护成本

**实现**：

- 移除`RECORDING_MODE`配置
- 移除`_launch_playwright_codegen_subprocess()`方法
- 统一使用`tools/launch_inspector_recorder.py`

### Decision 7: Python 组件调用机制

**决策**：通过适配器实现组件间调用，替代 YAML 的`component_call`

**方案**：

```python
# Python组件中调用其他组件
class OrdersExportComponent:
    async def run(self, page, account, params, **kwargs):
        # 调用日期选择组件
        date_picker = self.ctx.adapter.date_picker()
        await date_picker.run(page, params['date_from'], params['date_to'])

        # 调用店铺切换组件（可选）
        if params.get('shop_name'):
            shop_switch = self.ctx.adapter.shop_switch()
            await shop_switch.run(page, params['shop_name'])

        # 继续执行导出逻辑
        ...
```

**理由**：

- Python 组件直接通过适配器获取子组件实例
- 无需通过 executor 的`component_call`机制
- 类型安全，IDE 支持更好
- 参数传递更直观（Python 函数参数）

**对比 YAML 的 component_call**：

- YAML：`action: component_call` → executor 加载并执行
- Python：直接调用适配器方法 → 更简洁高效

### Decision 8: Python 组件元数据定义

**决策**：使用类属性定义组件元数据

**方案**：

```python
# modules/platforms/shopee/components/orders_export.py
class OrdersExportComponent:
    # 组件元数据（必需）
    platform = "shopee"
    component_type = "export"
    data_domain = "orders"

    # 可选元数据
    description = "Shopee订单数据导出组件"
    version = "1.0.0"

    def __init__(self, ctx: ExecutionContext):
        self.ctx = ctx
        self.logger = ctx.logger

    async def run(self, page, account: dict, params: dict, **kwargs) -> dict:
        """执行组件逻辑"""
        ...
        return {"success": True, "file_path": "..."}
```

**理由**：

- 类属性便于静态检查和反射
- 与 YAML 的元数据字段对应（platform、type、data_domain）
- 适配层可以通过`inspect`模块读取元数据

**适配层使用**：

```python
# PythonComponentAdapter._get_exporter()
component_class = load_python_component_class("shopee/orders_export")
if component_class.data_domain == data_domain:
    return component_class(ctx)
```

### Decision 9: 变量替换机制（Python 组件参数传递）

**决策**：Python 组件通过函数参数接收数据，无需模板替换

**方案**：

```python
# YAML组件（旧方式）
# value: '{{account.username}}'  → ComponentLoader替换为实际值

# Python组件（新方式）
async def run(self, page, account: dict, params: dict, **kwargs):
    username = account['username']  # 直接使用，无需模板
    password = account['password']  # 适配层已解密
    date_from = params['date_from']
    ...
```

**理由**：

- Python 函数参数比模板字符串更安全（类型检查、IDE 提示）
- 适配层负责准备参数（解密密码、合并参数等）
- 组件代码更清晰，无需处理模板语法

**适配层职责**：

```python
# PythonComponentAdapter
def _prepare_account(self, account: dict) -> dict:
    """准备账号信息（解密密码等）"""
    prepared = account.copy()
    if "password_encrypted" in prepared:
        prepared["password"] = self._decrypt_password(prepared["password_encrypted"])
    return prepared

async def login(self, page) -> dict:
    """执行登录组件"""
    account = self._prepare_account(self.account)
    component = self.adapter.login()
    return await component.run(page, account=account, params=self.config)
```

### Decision 10: 文件命名标准化

**决策**：使用 `StandardFileName.generate()` 生成标准文件名

**方案**：

```python
# 使用标准文件名生成器
from modules.core.file_naming import StandardFileName

filename = StandardFileName.generate(
    source_platform="shopee",
    data_domain="orders",
    granularity="daily",
    sub_domain="",  # 可选
    ext="xlsx",
    timestamp=None  # 自动生成
)
# 输出: shopee_orders_daily_20251229_120000.xlsx
```

**理由**：

- 与数据同步模块对齐，确保文件可被正确扫描和识别
- 统一命名规则，便于追溯和管理
- 包含平台、数据域、粒度等关键信息

**替换原有方案**：

```python
# 原有方案（已废弃）
filename = build_filename(data_type, granularity, account, shop, ...)
# 输出: 20251229_120000__account__shop__orders__daily.xlsx
```

### Decision 11: 文件存储路径标准化

**决策**：采集完成后移动文件到 `data/raw/YYYY/`（年份分区）

**方案**：

```python
# 文件保存流程
import shutil
from pathlib import Path
from datetime import datetime

# 1. 下载到临时目录
temp_path = Path("temp/outputs") / filename

# 2. 生成标准文件名
standard_filename = StandardFileName.generate(...)

# 3. 移动到最终目录
year = datetime.now().strftime("%Y")
final_dir = Path("data/raw") / year
final_dir.mkdir(parents=True, exist_ok=True)
final_path = final_dir / standard_filename
shutil.move(temp_path, final_path)
```

**理由**：

- 数据同步模块仅扫描 `data/raw/YYYY/` 目录（参见 `catalog_scanner.py`）
- 年份分区便于数据管理和清理
- 与现有数据同步流程对齐

### Decision 12: 伴生文件格式标准化

**决策**：使用 `MetadataManager.create_meta_file()` 生成 `.meta.json` 文件

**方案**：

```python
from modules.services.metadata_manager import MetadataManager

# 创建伴生文件
MetadataManager.create_meta_file(
    file_path=final_path,
    business_metadata={
        "source_platform": "shopee",
        "data_domain": "orders",
        "sub_domain": "",
        "granularity": "daily",
        "date_from": "2025-12-29",
        "date_to": "2025-12-29",
        "shop_id": "shop123"
    },
    collection_info={
        "method": "python_component",
        "collection_platform": "shopee",
        "account": "main_account",
        "shop_id": "shop123",
        "collected_at": "2025-12-29T12:00:00"
    },
    data_quality=None  # 可选
)
# 输出: shopee_orders_daily_20251229_120000.meta.json
```

**理由**：

- `.meta.json` 是数据同步模块期望的伴生文件格式
- 包含完整的业务元数据和采集信息
- 与 `catalog_files` 表字段对应

**伴生文件结构**：

```json
{
  "file_info": {
    "file_name": "shopee_orders_daily_20251229_120000.xlsx",
    "file_size": 12345,
    "file_ext": ".xlsx",
    "created_at": "2025-12-29T12:00:00"
  },
  "business_metadata": {
    "source_platform": "shopee",
    "data_domain": "orders",
    "sub_domain": "",
    "granularity": "daily",
    "date_from": "2025-12-29",
    "date_to": "2025-12-29",
    "shop_id": "shop123"
  },
  "collection_info": {
    "method": "python_component",
    "collection_platform": "shopee",
    "account": "main_account",
    "shop_id": "shop123",
    "collected_at": "2025-12-29T12:00:00"
  }
}
```

### Decision 13: 文件注册自动化

**决策**：采集完成后自动调用 `register_single_file()` 注册到 `catalog_files` 表

**方案**：

```python
from modules.services.catalog_scanner import register_single_file

# 注册文件
catalog_id = register_single_file(str(final_path))
if catalog_id:
    logger.info(f"[OK] File registered: {final_path} (id={catalog_id})")
else:
    logger.error(f"[FAIL] File registration failed: {final_path}")
```

**理由**：

- 确保数据同步模块可以识别新文件
- 避免依赖定时扫描任务
- 提供即时反馈

### Decision 14: Python 组件测试工具更新

**决策**：更新测试工具支持 Python 组件加载和执行

**方案**：

```python
# tools/test_component.py 更新

from modules.apps.collection_center.component_loader import ComponentLoader

# 加载 Python 组件
loader = ComponentLoader()
component_class = loader.load_python_component(platform, component_name)

# 创建适配器
adapter = PythonComponentAdapter(platform, account, config, logger)

# 执行组件
result = await adapter.execute_component(page, component_name, params)
```

**理由**：

- 现有测试工具仅支持 YAML 组件
- 需要与 Python 组件统一执行流程对齐
- 前端测试功能依赖此更新

## Risks / Trade-offs

### Risk 1: 异步改造遗漏

**风险**：可能遗漏某些同步调用，导致运行时错误

**缓解**：

- 使用 IDE 类型检查
- 运行时检测（检查返回值是否为 coroutine）
- 逐个组件测试

### Risk 2: 等待逻辑失效

**风险**：`while`循环等待逻辑可能行为不一致

**缓解**：

- 保持等待时间不变
- 添加日志记录实际等待时间
- 端到端测试验证

### Risk 3: 性能影响

**风险**：异步改造可能影响执行性能

**缓解**：

- 基准测试对比改造前后性能
- 异步本身应提升并发能力

### Risk 4: component_call 机制缺失

**风险**：Python 组件无法调用子组件，导致代码重复

**缓解**：

- 在适配层提供组件调用方法（Decision 7）
- 导出组件通过适配器调用 date_picker、shop_switch 等子组件
- 保持与 YAML 组件相同的功能完整性

### Risk 5: ComponentVersion 表迁移失败

**风险**：现有 ComponentVersion 记录存储`.yaml`路径，迁移到`.py`可能失败

**缓解**：

- 编写数据迁移脚本（`.yaml` → `.py`）
- 保留原路径字段作为备份
- 添加`file_type`字段区分 YAML 和 Python
- 回滚计划：恢复原路径字段

### Risk 6: Trace 解析器生成代码质量

**风险**：自动生成的 Python 代码骨架可能不完整或有问题

**缓解**：

- 生成代码后人工审核
- 提供代码模板和最佳实践
- 生成代码包含基本错误处理
- 前端代码编辑器支持语法高亮和检查

## Migration Plan

### 阶段 1：核心改造（第 1-4 天）

1. **创建异步改造脚本**

   - 正则替换`page.`为`await page.`
   - 添加`async`关键字
   - 人工审核关键逻辑

2. **逐平台改造**

   - Shopee（17 文件）→ TikTok（12 文件）→ Miaoshou（9 文件）
   - 每个平台完成后立即测试

3. **密码解密统一**

   - 修改 3 个登录组件
   - 测试解密逻辑

4. **日志规范化**
   - 批量替换 emoji
   - 验证 Windows 控制台输出

### 阶段 2：集成开发（第 5-6 天）

1. **创建适配层**

   - `python_component_adapter.py`
   - 单元测试

2. **修改 executor_v2**

   - 添加`_execute_python_component()`
   - 集成测试

3. **组件加载器扩展**
   - Python 组件检测逻辑
   - 测试加载逻辑

### 阶段 3：数据同步对齐（第 7-8 天）

1. **文件命名标准化**

   - 替换 `build_filename()` 为 `StandardFileName.generate()`
   - 更新所有导出组件

2. **文件存储路径标准化**

   - 实现文件移动逻辑（`temp/outputs/` → `data/raw/YYYY/`）
   - 更新 executor_v2 的 `_process_files()` 方法

3. **伴生文件格式标准化**

   - 替换 `_write_manifest()` 为 `MetadataManager.create_meta_file()`
   - 确保 `.meta.json` 包含完整元数据

4. **文件注册自动化**

   - 在文件移动后调用 `register_single_file()`
   - 添加错误处理和日志

5. **Python 组件测试工具更新**
   - 更新 `tools/test_component.py`
   - 更新 `tools/run_component_test.py`
   - 更新 `backend/routers/component_versions.py`

### 阶段 4：测试验证（第 9-10 天）

1. **单元测试**

   - 每个组件的异步调用
   - 密码解密逻辑
   - 适配层接口
   - 文件命名和伴生文件生成

2. **集成测试**

   - executor_v2 与 Python 组件集成
   - 完整采集流程
   - 数据同步模块扫描验证

3. **回归测试**
   - 现有 API 接口不受影响
   - 前端组件管理页面正常
   - 定时采集功能正常
   - Python 组件测试功能正常

### 回滚计划

如果改造失败：

1. 恢复`modules/platforms/`中的同步版本（从 Git 恢复）
2. 恢复`executor_v2.py`中的 YAML 组件执行逻辑（如果需要）
3. `migration_temp/`作为备份参考

## User Flows

### Flow 1: 组件录制流程（Inspector 模式）

**工具链**：

- 前端：`ComponentRecorder.vue`
- 后端 API：`backend/routers/component_recorder.py`
- 录制脚本：`tools/launch_inspector_recorder.py`
- Trace 解析：`backend/utils/trace_parser.py`

**流程**：

1. 用户在前端选择平台、组件类型、测试账号
2. 点击"开始录制" → 前端调用 `POST /collection/recorder/start`
3. 后端启动子进程执行 `tools/launch_inspector_recorder.py`
4. InspectorRecorder 创建持久化浏览器上下文（`PersistentBrowserManager`）
5. 应用固定设备指纹（`DeviceFingerprintManager`）
6. 自动执行 login 组件（如果录制非 login 组件）
7. 启动 Trace 录制（`context.tracing.start()`）
8. 打开 Playwright Inspector（`page.pause()`）
9. 用户在浏览器中执行操作
10. 系统捕获操作事件（click/fill/goto/wait）
11. 用户点击"停止录制" → 前端调用 `POST /collection/recorder/stop`
12. 系统停止 Trace 录制，保存 trace.zip 文件
13. 系统使用`TraceParser`解析 Trace 文件
14. 系统生成 Python 组件代码骨架
15. 用户在代码编辑器编辑 Python 代码
16. 用户保存组件 → 前端调用 `POST /collection/recorder/save`
17. 后端保存 Python 文件到 `modules/platforms/{platform}/components/{name}.py`
18. 创建 ComponentVersion 记录

### Flow 2: 组件测试流程

**工具链**：

- 前端：`ComponentVersions.vue` / `ComponentRecorder.vue`
- 后端 API：`backend/routers/component_recorder.py`
- 测试服务：`backend/services/component_test_service.py`
- 测试脚本：`tools/run_component_test.py`
- 组件适配器：`PythonComponentAdapter`

**流程**：

1. 用户选择 Python 组件
2. 点击"测试组件" → 前端调用 `POST /collection/recorder/test`
3. ComponentTestService 准备账号信息（解密密码）
4. 启动子进程执行 `tools/run_component_test.py`
5. ComponentTester 加载 Python 组件（`component_loader.load_python_component()`）
6. 创建 PythonComponentAdapter
7. 创建 Playwright 浏览器（`async_playwright`）
8. 打开浏览器窗口（非 headless 模式）
9. 根据组件类型执行：
   - login → `adapter.login(page)`
   - navigation → `adapter.navigate(page, target_page)`
   - export → `adapter.export(page, data_domain)`
10. 实时执行每个步骤，记录结果（成功/失败/耗时）
11. 失败时保存错误截图
12. 验证 success_criteria
13. 生成 ComponentTestResult
14. 保存测试历史到`ComponentTestHistory`表
15. 返回测试结果给前端
16. 前端显示测试报告（步骤详情、成功率、失败截图）

### Flow 3: 生产环境采集流程（定时/手动触发）

**工具链**：

- 调度器：`backend/services/collection_scheduler.py`（APScheduler）
- 任务 API：`backend/routers/collection.py`
- 执行引擎：`modules/apps/collection_center/executor_v2.py`
- 组件适配器：`PythonComponentAdapter`
- 账号加载：`AccountLoaderService`
- 文件注册：`FileRegistrationService`

**流程**：

1. **定时触发**：APScheduler 到达 Cron 时间 → `CollectionScheduler._execute_scheduled_task()`
   **手动触发**：前端/API 调用 → `POST /collection/tasks`
2. 检查任务冲突（同一配置是否已有运行任务）
3. 为每个账号创建`CollectionTask`记录
4. 启动后台任务（`asyncio.create_task()`）
5. 加载账号信息（`AccountLoaderService.load_account()`）
6. 解密账号密码（`EncryptionService.decrypt_password()`）
7. 创建 CollectionExecutorV2
8. 创建 Playwright 浏览器（`async_playwright`）
9. 执行登录组件（`PythonComponentAdapter.login()`）
10. 循环处理每个数据域（`executor.execute_parallel_domains()`）：
    - 并行执行多个数据域（`asyncio.gather()`）
    - 每个数据域：
      a. 执行导航组件（`adapter.navigate()`）
      b. 执行日期选择组件（`adapter.date_picker()`）
      c. 执行导出组件（`adapter.export()`）
      d. 下载 Excel 文件（`page.expect_download()`）
      e. 文件系统兜底（扫描下载目录）
      f. 生成标准文件名（`StandardFileName.generate()`）
      g. 移动到 `data/raw/YYYY/` 目录
      h. 生成伴生文件（`MetadataManager.create_meta_file()`）
      i. 注册到 catalog_files 表（`register_single_file()`）
11. 汇总所有数据域结果
12. 更新任务状态（completed/partial_success/failed）
13. 前端轮询 `GET /collection/tasks/{task_id}` 获取进度
14. 前端显示采集进度和结果

## Open Questions

1. **Q: 是否需要同时支持同步和异步版本？**

   - A: 不需要。FastAPI 是异步框架，统一使用异步版本即可。

2. **Q: 组件测试如何进行？**

   - A: 使用 pytest-asyncio 进行异步测试，每个组件有独立的测试用例。

3. **Q: 如何处理长时间运行的采集任务？**

   - A: 使用`asyncio.create_task()`启动后台任务，通过 HTTP 轮询报告进度。

4. **Q: 为什么移除 YAML 组件支持？**

   - A: 避免双维护问题。YAML 格式无法处理复杂操作（悬停、动态下拉框、iframe 遍历、2FA 验证等），Python 组件功能更强大且已通过实际验证。

5. **Q: 为什么移除 Codegen 模式？**
   - A: Codegen 模式不稳定，不适合复杂场景。Inspector 模式功能更强大（持久化会话、固定指纹、Trace 回放），且是 Playwright 官方推荐的录制方式。
