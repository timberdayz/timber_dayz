# Active 采集组件清单

本文档定义当前仍属于 V2 主链路的“活跃组件”，以及哪些旧组件只能作为归档参考。

## 目的

这份清单用于回答三个问题：

1. 哪些组件仍可进入默认开发、测试和正式运行链路
2. 哪些组件只能视为历史参考，不再进入默认主链路
3. 哪些文件在移动到 `archive/` 之前必须先完成 runtime 指针切换

## 当前活跃 V2 组件

当前已确认属于活跃主链路的组件：

- `miaoshou/login`
- `miaoshou/orders_export`

说明：

- 这些组件已经完成 V2 迁移或被明确指定为当前活跃入口
- 默认测试、stable 运行、后续维护应优先围绕这些逻辑组件展开

## 归档参考组件

以下组件或文件应默认视为：

- `reference_only`
- `legacy_archive`
- `not runtime`

包括但不限于：

- recorder-era 中间实现
- 旧 monolithic exporter
- 版本化旧文件中不再被 stable `file_path` 指向的文件
- 仅供选择器/流程借鉴的历史逻辑文件

## 归档前置条件

某个旧组件文件只有在满足下面条件后，才允许移动到：

- `modules/platforms/<platform>/archive/`

前置条件：

1. 不在当前活跃组件清单里
2. 没有 stable `ComponentVersion.file_path` 指向它
3. 不再被 canonical V2 组件直接 import
4. 默认 loader/runtime/register 流程已对 archive 做隔离

## archive 目录语义

`archive/` 目录中的文件：

- 保留给人或 agent 做历史参考
- 不进入默认批量注册
- 不进入默认 stable 运行
- 不作为新开发的默认修改目标

## 一句话规则

如果一个组件不在活跃清单里，它就不应该再出现在默认运行链路里；如果它还要保留，也应该逐步进入 `archive/`，仅供参考。
