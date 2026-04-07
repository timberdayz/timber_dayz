# 组件化采集框架 / Components Architecture

> 文档索引（推荐入口）: docs/INDEX.md

目标：以“组件化优先”的生产路径，沉淀跨账号可复用的采集能力；录制脚本作为稳定版/临时任务的补充。

## 目录结构

- modules/components/
  - base.py（ComponentBase/ExecutionContext/ResultBase）
  - login/base.py
  - navigation/base.py
  - date_picker/base.py
  - export/base.py
  - metrics_selector/base.py（可选）
- modules/platforms/
  - adapter_base.py（PlatformAdapter）
  - shopee/adapter.py + components/
  - （预留）miaoshou、tiktok、lazada、amazon

## 组件接口约定

- 统一入参：ExecutionContext(ctx) 注入平台、账号、logger、配置
- 统一返回：ResultBase 派生，含 success/message/details
- 统一错误：ComponentError 及派生类；日志使用 loguru 规范
- 明确职责：
  - LoginComponent.run(page)
  - NavigationComponent.run(page, target)
  - DatePickerComponent.run(page, option)
  - ExportComponent.run(page, mode)
  - MetricsSelectorComponent.run(page, metrics)

## 平台适配

- PlatformAdapter 声明 platform_id、capabilities()
- 工厂方法返回具体平台组件实例
- 通过 adapter.{login/navigation/date_picker/exporter} 获取组件

## 执行策略（推荐）

1. 组件化优先（生产）
2. 稳定版录制脚本（回归/应急）
3. 最新录制脚本（试运行）
4. 程序化兜底（永不阻塞）

## 开发步骤

1. 在 modules/platforms/<platform>/components/ 实现平台组件（最小可用）
2. 在 adapter.py 中返回对应组件实例
3. 在业务流程中注入 ctx 并调用组件组合
4. 为组件编写单元/集成测试；在 nightly 冒烟中回放稳定版脚本

## 扩展指引

- 新增组件：在 modules/components/<new>/base.py 定义抽象与 Result；平台实现对应类
- 新增平台：创建 modules/platforms/<platform>/，实现 adapter 与 components
- 版本治理：为组件与配方引入版本号，记录变更日志，可回滚

## 输出路径计算最佳实践（统一接口，推荐）

- 统一使用导出基类提供的 `build_standard_output_root(ctx, data_type, granularity, subtype=None)` 计算落盘目录。
- 目录形态：`temp/outputs/<platform>/<account>/<shop>__<shop_id>/<data_type>[/<subtype>]/<granularity>`
- 特点：
  - 自动读取 `path_options.include_shop_id`（新架构默认 true）
  - 自动解析 `account_label / shop_name / shop_id`，提供健壮回退
  - 子类型（如 services 的 ai_assistant/agent）以内层目录体现

示例（任意导出器中）：

```python
from modules.components.export.base import build_standard_output_root

out_root = build_standard_output_root(
    ctx,
    data_type="services",   # 如 products/traffic/services/orders/finance
    granularity="daily",    # daily/weekly/monthly/manual
    subtype="ai_assistant", # 可选：仅当该数据域存在子类型
)
out_root.mkdir(parents=True, exist_ok=True)
```

注意：

- 无子类型时，省略 `subtype` 参数即可。
- 如需仅生成文件名，继续复用 `modules.utils.path_sanitizer.build_filename()`。
