# Active 采集组件清单

本文档定义当前仍属于 V2 主链路的活跃组件，以及哪些旧组件只能作为归档参考。

## 当前活跃组件

当前已确认进入 V2 主链路的组件只有：

- `miaoshou/login`
- `miaoshou/orders_export`

这些组件具备以下特征：

- 允许进入默认开发和维护流程
- 允许进入默认组件测试和 stable 运行链路
- 后续新功能和问题修复优先围绕这些 canonical 组件展开

## 归档参考组件

以下对象默认不再属于主链路：

- recorder-era 中间实现
- 历史 monolithic exporter
- 旧兼容包装层
- 已不再被 stable `file_path` 指向的历史版本文件

这些文件后续可以保留，但只能视为：

- `reference_only`
- `legacy_archive`
- `not runtime`

当前已进入 `modules/platforms/miaoshou/archive/` 的第一批文件：

- `miaoshou_login.py`
- `login_v1_0_1.py`
- `login_v1_0_2.py`

当前已进入 `modules/platforms/miaoshou/archive/` 的第二批文件：

- `export.py`
- `navigation.py`
- `date_picker.py`

当前已进入 `modules/platforms/shopee/archive/` 的第一批文件：

- `login_v1_0_1.py`
- `recorder_test_login.py`
- `metrics_selector.py`

当前 Shopee 平台旧组件已整体退出 `components/` 主链路，历史业务组件与配置文件已移入 `modules/platforms/shopee/archive/`。

当前已进入 `modules/platforms/tiktok/archive/` 的第一批文件：

- `shop_selector.py`

当前 TikTok 平台旧组件已整体退出 `components/` 主链路，历史业务组件与配置文件已移入 `modules/platforms/tiktok/archive/`。

## Archive 前置条件

某个旧文件只有在满足下面条件后，才允许移动到：

- `modules/platforms/<platform>/archive/`

前置条件：

1. 不在当前活跃组件清单中
2. 没有 stable `ComponentVersion.file_path` 指向该文件
3. 默认 runtime / register / loader guard 已经生效
4. canonical V2 组件不再直接 import 该文件

如果以上任一条件不满足，就不能先移动文件。

## Archive 目录语义

`archive/` 目录中的文件固定语义是：

- 只供人或 agent 参考
- 不参与默认批量注册
- 不参与默认 stable 运行
- 不作为新开发的默认修改目标

## 使用规则

默认情况下：

- 新开发只看活跃组件
- 旧组件只在需要历史借鉴时查阅
- 任何 archive 文件都不能再被当成默认 runtime 入口

## 一句话规则

如果一个组件不在活跃清单里，它就不应该继续出现在默认运行链路里；如果还要保留，也应该逐步进入 `archive/`，仅供参考。
