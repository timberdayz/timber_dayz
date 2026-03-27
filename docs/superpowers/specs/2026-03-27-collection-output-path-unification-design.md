# 采集输出路径统一设计

日期：2026-03-27

状态：proposed

## 背景

当前仓库在“采集导出 -> catalog 注册 -> 自动入库/同步”链路上同时保留了两种路径语义：

- 正式链路已经部分收敛到 `data/raw/`
- 历史代码和部分工具仍把 `temp/outputs/` 当作正式采集输出目录

这种双路径状态说明系统还停留在迁移中间态，而不是最终形态。它会带来：

- 正式数据真源不清晰
- catalog / 同步 / 排障文档语义不一致
- 新代码容易继续写入旧路径
- 兼容逻辑长期滞留在主链路

## 目标

将正式采集主链路收敛为：

`下载工作目录 -> 校验/命名 -> move 到 data/raw/YYYY/ -> catalog 注册 -> 自动入库/同步`

收敛后满足：

1. `data/raw/` 是唯一正式采集数据入口
2. catalog 注册和自动同步只把 `data/raw/` 视为正式来源
3. `temp/outputs/` 退出正式主链路，只保留兼容读取或调试用途
4. 路径解析器默认按 `data/raw` 语义工作，而不是反推 `temp/outputs`

## 非目标

本轮不做：

- 全仓库历史脚本与 archive 文档清理
- 所有 legacy collector/utility 的路径重构
- 一次性删除 `temp/outputs/` 目录
- 修改所有旧测试报告或一次性脚本输出目录

## 方案比较

### 方案 A：主链路硬收口到 `data/raw/`，`temp/outputs/` 仅兼容读取

做法：

- 执行器继续/统一把正式文件移动到 `data/raw/YYYY/`
- `register_single_file()` 和 catalog 默认来源使用 `data/raw`
- 文件路径解析器改为 `data/raw` 优先语义
- `_safe_resolve_path()` 仍保留对 `temp/outputs` 的读取兼容，避免旧数据立即失效

优点：

- 正式链路定义清晰
- 改动集中在主链路
- 不会把存量旧记录一次性打断

缺点：

- 迁移期仍需维护少量 legacy 兼容代码

结论：

推荐。

### 方案 B：维持双路径，但通过文档规定优先级

做法：

- 继续允许组件落盘到 `temp/outputs/`
- catalog 和同步链路自行兼容
- 只在文档上强调最终会迁移到 `data/raw/`

缺点：

- 无法真正消除双链路
- 后续代码会继续沿旧语义扩散

结论：

不推荐。

## 推荐方案

采用方案 A。

### 路径语义

- `data/raw/`
  - 唯一正式采集原始数据目录
  - catalog、入库、同步、审计围绕此目录对齐

- `output/playwright/work/` 或任务级 `downloads/`
  - 浏览器临时下载工作目录
  - 只承担下载中间态，不作为正式数据真源

- `output/playwright/profiles/`、`output/playwright/state/`
  - 浏览器 profile / session state / 调试资产

- `temp/outputs/`
  - 仅保留给 legacy 工具、历史记录兼容、测试报告或临时诊断文件
  - 不再作为正式采集数据源目录

### 代码边界

本轮优先收口以下位置：

- `modules/apps/collection_center/executor_v2.py`
  - 确认正式文件 move 到 `data/raw/YYYY/`
  - 避免主链路继续写死 `Path("data/raw")`

- `modules/services/catalog_scanner.py`
  - 注册单文件时把 `source` 明确写为 `data/raw`
  - 兼容扫描接口保持废弃状态，不恢复 `temp/outputs` 扫描

- `backend/services/file_path_resolver.py`
  - 从“重建 `temp/outputs` 路径”改为“定位 `data/raw` 文件”
  - 搜索优先级改为 `data/raw -> downloads -> data/input -> legacy temp/outputs`

- `modules/core/db/schema.py`
  - `CatalogFile.source` 默认值改为 `data/raw`
  - 注释同步更新，避免新代码继续沿旧默认语义扩散

### 兼容策略

本轮保留兼容但降级为 legacy：

- `_safe_resolve_path()` 仍允许解析旧记录里的 `temp/outputs` 路径
- `to_relative_path()` 保留 `temp/outputs` 关键路径提取
- `scan_legacy_outputs()` 继续存在，但保持废弃状态

这样可以保证：

- 新链路不再依赖 `temp/outputs`
- 旧 catalog 记录和旧数据仍可读取
- 后续可再单独做“legacy 文件迁移”和“兼容代码删除”

## 测试策略

本轮采用 TDD，至少覆盖：

1. 路径解析器默认重建/查找 `data/raw` 路径
2. catalog 默认来源字段为 `data/raw`
3. 执行器正式落盘目录由统一路径管理器提供，而不是手写相对路径

## 验收标准

满足以下条件才算完成：

1. 正式采集主链路不再把 `temp/outputs` 当正式输出目录
2. 新注册的 `CatalogFile.source` 默认语义为 `data/raw`
3. 文件定位逻辑优先命中 `data/raw`
4. 旧 `temp/outputs` 记录仍能被兼容解析
