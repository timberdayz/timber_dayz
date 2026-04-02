# Main Account Shop Account Domain Chain Design

**日期:** 2026-04-02

**目标:** 重构采集账号体系，明确“主账号ID / 店铺账号ID / 平台店铺ID / 店铺别名 / 店铺数据域能力”的边界，打通账号管理、组件测试、正式采集、数据归属四条链路，形成“店铺级采集，主账号级持久会话”的统一模型。

## 1. 背景

当前仓库已经具备以下事实：

- 账号管理页面已经围绕“一个主账号下维护多个店铺”进行交互设计。
- 当前记录中同时包含：
  - 登录信息
  - 店铺名称
  - 店铺区域
  - 店铺 ID
  - 能力配置
- 采集组件运行时已经会消费 `shop_id / shop_region / shop_name` 一类店铺上下文。
- 组件版本测试页仍然以“账号”为测试目标，没有把店铺上下文显式建模并注入。
- 采集执行器当前仍以 `account_id` 作为持久 profile / session / storage_state 的复用粒度。
- 现有“账号别名”只能表达单个别名，无法稳定处理一店铺多别名和待认领别名池。

这导致当前系统同时存在两类语义冲突：

1. 一条记录既像“登录账号”，又像“店铺目标”。
2. 运行时会话复用粒度和采集目标粒度不一致。

本次设计直接解决这两个冲突，不保留旧结构兼容层。

## 2. 设计目标

本次设计要一次性达成以下目标：

1. 明确三层标识语义：
   - `主账号ID`
   - `店铺账号ID`
   - `平台店铺ID`
2. 采集目标、组件测试目标全部切换为“店铺账号”。
3. 持久会话、profile、storage_state 复用全部切换为“主账号”。
4. 店铺别名从单字段升级为独立映射表，支撑多别名归属。
5. 店铺数据域能力成为正式生效配置，而非仅用于展示。
6. 平台店铺ID允许自动发现、自动回填、待确认和人工补录。
7. 账号管理页面不推翻现有骨架，仅同步语义和后端模型。
8. 直接进行数据库物理重构，不保留旧字段命名。

## 3. 术语与语义

### 3.1 主账号ID

`主账号ID` 表示登录身份和持久会话拥有者。

它回答的是：

- 谁来登录平台
- 谁拥有浏览器持久 profile
- 谁拥有 storage_state / session cache

示例：

- `hongxikeji:main`
- `miaoshou:ops-main`

### 3.2 店铺账号ID

`店铺账号ID` 表示系统中的店铺级业务对象唯一标识。

它回答的是：

- 组件测试正在测试哪个店铺对象
- 正式采集任务正在采哪个店铺对象
- 日志、测试历史、文件、任务归属到哪个业务对象

示例：

- `shopee_sg_hongxi_local`
- `tiktok_global_hongxi_tools`

### 3.3 平台店铺ID

`平台店铺ID` 表示平台真实运行时使用的店铺标识。

它回答的是：

- 平台页面当前到底是哪家店
- 页面 URL 参数、导出接口、数据落库、事实表关联使用哪个真实店铺标识

示例：

- `100018822`
- `cnsc_shop_id=99220011`

### 3.4 店铺别名

`店铺别名` 表示原始数据、平台页面、历史文件里出现的各种店铺名称、标签、显示名。

它不是主键，不等于店铺账号ID。

它的职责是：

- 作为归属入口
- 最终映射到某个店铺账号ID

### 3.5 数据域能力

`店铺数据域能力` 表示某个店铺账号在系统中允许执行的数据域集合。

它最终控制：

- 组件测试能不能测试某个数据域
- 正式采集任务能不能对该店铺创建某个数据域任务

## 4. 总体原则

### 4.1 店铺级采集，主账号级持久会话

全系统统一原则：

- 采集目标是店铺账号
- 登录态主体是主账号

### 4.2 店铺账号是一等业务对象

后续以下能力都以店铺账号作为核心对象：

- 组件测试
- 正式采集
- 测试历史
- 采集任务
- 文件归属
- 数据归属

### 4.3 平台店铺ID优先自动发现

平台店铺ID不是创建时必填字段。

系统在首次登录、切店、进入目标业务页、首次采集成功时优先自动发现：

- 单候选时自动绑定
- 多候选时进入待确认列表
- 失败时允许人工补录

### 4.4 别名是映射，不是主键

原始店铺标签的归属路径固定为：

`原始店铺标签 -> 店铺别名表 -> 店铺账号ID -> 业务归属`

## 5. 目标数据模型

本次重构后的核心表如下。

### 5.1 `core.main_accounts`

表示主账号。

关键字段：

- `id`
- `platform`
- `main_account_id`
- `username`
- `password_encrypted`
- `login_url`
- `enabled`
- `notes`
- `created_at`
- `updated_at`

约束：

- `platform + main_account_id` 唯一

职责：

- 登录身份
- 持久 profile/session/storage_state 复用主体
- 主账号级默认能力上限

### 5.2 `core.shop_accounts`

表示店铺账号。

关键字段：

- `id`
- `platform`
- `shop_account_id`
- `main_account_id`，外键指向 `core.main_accounts.main_account_id`
- `store_name`
- `platform_shop_id`
- `platform_shop_id_status`
- `shop_region`
- `shop_type`
- `enabled`
- `notes`
- `created_at`
- `updated_at`

状态建议：

- `missing`
- `auto_bound`
- `pending_confirm`
- `manual_confirmed`

约束：

- `platform + shop_account_id` 唯一
- `platform + platform_shop_id` 在非空时唯一

职责：

- 店铺级采集对象
- 店铺级测试对象
- 结果归属对象

### 5.3 `core.shop_account_aliases`

表示店铺别名映射。

关键字段：

- `id`
- `platform`
- `shop_account_id`
- `alias_value`
- `alias_normalized`
- `alias_type`
- `source`
- `is_primary`
- `is_active`
- `created_at`
- `updated_at`

约束：

- `platform + alias_normalized + is_active=true` 唯一

职责：

- 原始数据归属入口
- 支撑一店铺多别名
- 支撑未匹配别名认领

### 5.4 `core.shop_account_capabilities`

表示店铺级最终生效的数据域能力。

关键字段：

- `id`
- `shop_account_id`
- `data_domain`
- `enabled`
- `created_at`
- `updated_at`

约束：

- `shop_account_id + data_domain` 唯一

职责：

- 测试与采集的最终能力判断

### 5.5 `core.platform_shop_discoveries`

表示平台店铺ID自动发现与待确认记录。

关键字段：

- `id`
- `platform`
- `main_account_id`
- `detected_store_name`
- `detected_platform_shop_id`
- `detected_region`
- `candidate_shop_account_ids`
- `status`
- `raw_payload`
- `created_at`
- `updated_at`

状态建议：

- `detected_single_bound`
- `detected_pending_confirm`
- `detected_failed`
- `manual_confirmed`

职责：

- 自动发现
- 多候选确认
- 审计

## 6. 账号管理页面语义

现有账号管理页面骨架保留，但所有文案和数据源改为新模型。

### 6.1 列表语义

建议主表列为：

- 平台
- 主账号ID
- 店铺账号ID
- 店铺别名
- 店铺名称
- 平台店铺ID
- 店铺类型
- 店铺区域
- 店铺数据域能力
- 启用状态
- 操作

其中：

- `店铺别名` 显示为主别名或“X 个别名”，不再作为单字段录入
- `平台店铺ID` 需要配合状态标签显示

### 6.2 创建流程

支持两条入口：

1. 先创建主账号，再挂店铺
2. 在已有主账号下批量添加店铺

### 6.3 批量添加店铺

当前批量添加功能可以保留，但语义改成：

- 选择一个主账号ID
- 输入多个店铺
- 为每个店铺生成一个店铺账号ID

### 6.4 页面状态提示

页面应明确显示：

- 该店铺归属哪个主账号ID
- 该店铺的平台店铺ID当前是：
  - 未识别
  - 自动识别
  - 待确认
  - 人工确认

## 7. 平台店铺ID自动发现流程

### 7.1 触发点

自动发现可以在以下节点触发：

- 主账号首次登录成功后
- 店铺切换成功后
- 首次进入目标业务页后
- 首次采集成功后

### 7.2 发现内容

系统尽可能抽取：

- 页面当前展示店铺名
- 页面 URL 中的店铺参数
- 区域值
- 平台真实店铺ID

### 7.3 绑定规则

- 若主账号下只有一个候选店铺账号，则自动回填并标记 `auto_bound`
- 若主账号下有多个候选店铺账号，则生成 `platform_shop_discoveries` 记录并标记 `pending_confirm`
- 若完全无法识别，则记录失败并保持 `missing`

### 7.4 人工确认

当状态为 `pending_confirm` 时，用户在账号管理页确认：

- 这条发现记录归属哪个店铺账号ID

确认后：

- 回填 `platform_shop_id`
- 状态改为 `manual_confirmed`

## 8. 店铺别名与数据归属

### 8.1 别名设计原则

别名不再保留为 `shop_accounts` 上的单字段。

原因：

- 一个店铺可能存在多个别名
- 原始数据来源会持续产生新的店铺标签
- 需要支持停用、主别名、来源追踪、未匹配认领

### 8.2 归属链路

后续业务概览和导入归属统一按以下步骤执行：

1. 取原始店铺字段，如 `store_label_raw / store_name / 店铺名`
2. 标准化为 `alias_normalized`
3. 按 `platform + alias_normalized` 匹配 `shop_account_aliases`
4. 命中后得到 `shop_account_id`
5. 再归属到店铺账号及其主账号

### 8.3 未匹配别名池

现有“未匹配店铺别名”改造成正式的待认领流程：

- 发现未匹配别名后写入待认领列表
- 用户认领一次
- 写入 `shop_account_aliases`
- 后续自动归属

## 9. 数据域能力模型

### 9.1 归属层级

规则固定为：

- 主账号能力 = 默认/上限能力
- 店铺账号能力 = 最终生效能力

### 9.2 生效规则

组件测试和正式采集都必须校验：

- 主账号允许该数据域
- 店铺账号也允许该数据域

最终以店铺账号能力为准。

### 9.3 页面与接口用途

店铺数据域能力必须同时控制：

- 店铺创建与编辑
- 组件测试页可选域
- 采集任务创建
- 调度过滤

## 10. 组件测试重构

### 10.1 测试对象

组件测试页不再选择“账号”，而是选择“店铺账号”。

### 10.2 请求模型

组件测试请求改为至少包含：

- `shop_account_id`
- `granularity`
- `time_mode`
- `date_preset`
- `start_date`
- `end_date`
- `sub_domain`

### 10.3 后端解析

后端收到 `shop_account_id` 后：

1. 加载店铺账号
2. 反查主账号
3. 生成主账号级登录上下文
4. 注入店铺级运行上下文
5. 校验店铺数据域能力

### 10.4 测试弹窗展示

弹窗中建议展示：

- 店铺账号ID
- 主账号ID
- 店铺名称
- 平台店铺ID及状态
- 时间参数
- 子数据域

## 11. 正式采集与执行器重构

### 11.1 会话复用粒度

所有持久 profile、storage_state、session cache 都按 `main_account_id` 复用。

### 11.2 采集目标粒度

所有采集任务都按 `shop_account_id` 创建。

### 11.3 执行顺序

测试与正式采集统一为：

1. 恢复主账号会话
2. 校验登录态
3. 加载店铺上下文
4. 执行 `shop_switch`
5. 自动发现或确认平台店铺ID
6. 执行日期、筛选、导出

### 11.4 ExecutionContext 语义

运行时上下文建议拆成两类来源：

- `login_account`
  - 主账号信息
- `shop_context`
  - 店铺账号信息

兼容阶段可以继续使用：

- `ctx.account` 承载主账号登录信息
- `ctx.config` 承载 `shop_account_id / platform_shop_id / store_name / shop_region / data_domain / sub_domain`

### 11.5 归属规则

- 会话归属：`main_account_id`
- 测试/任务/文件归属：`shop_account_id`
- 平台跳转参数与数据落库：`platform_shop_id`

## 12. API 设计

### 12.1 主账号 API

- `GET /main-accounts`
- `POST /main-accounts`
- `PUT /main-accounts/{main_account_id}`
- `DELETE /main-accounts/{main_account_id}`

### 12.2 店铺账号 API

- `GET /shop-accounts`
- `POST /shop-accounts`
- `POST /shop-accounts/batch`
- `PUT /shop-accounts/{shop_account_id}`
- `DELETE /shop-accounts/{shop_account_id}`

### 12.3 店铺别名 API

- `GET /shop-account-aliases`
- `POST /shop-account-aliases`
- `PUT /shop-account-aliases/{id}`
- `DELETE /shop-account-aliases/{id}`
- `GET /shop-account-aliases/unmatched`
- `POST /shop-account-aliases/claim`

### 12.4 平台店铺ID确认 API

- `GET /platform-shop-discoveries`
- `POST /platform-shop-discoveries/{id}/confirm`
- `POST /platform-shop-discoveries/{id}/reject`

### 12.5 组件测试 API

组件测试相关接口统一转为以 `shop_account_id` 为输入。

## 13. 数据库迁移策略

本次迁移直接进行物理重构，不保留旧命名兼容层。

### 13.1 新表

新建：

- `core.main_accounts`
- `core.shop_accounts`
- `core.shop_account_aliases`
- `core.shop_account_capabilities`
- `core.platform_shop_discoveries`

### 13.2 旧表迁移

从旧 `core.platform_accounts` 迁移：

1. 按 `platform + parent_account` 聚合为 `main_accounts`
2. 每条旧记录迁移为一条 `shop_accounts`
3. 旧 `account_alias` 迁移到 `shop_account_aliases`
4. 旧 `capabilities` 拆到 `shop_account_capabilities`

### 13.3 迁移后约束

迁移完成后：

- 代码不再读取旧表
- 旧表仅作为回滚窗口短暂保留，或直接删除

## 14. 页面文案与命名统一

本次直接统一语义：

- `主账号` -> `主账号ID`
- `账号ID` -> `店铺账号ID`
- `店铺ID` -> `平台店铺ID`
- `账号别名` -> `店铺别名`
- `能力配置` -> `店铺数据域能力`
- `测试账号` -> `测试店铺`

## 15. 验收标准

### 15.1 账号管理

- 可创建主账号并挂多个店铺账号
- 店铺数据域能力可独立配置
- 店铺别名可一店多别名

### 15.2 组件测试

- 测试页按店铺账号选择
- 同主账号下连续测试多个店铺不重复登录
- 测试结果归属到店铺账号ID

### 15.3 自动发现

- 平台店铺ID可自动识别并回填
- 多候选可进入待确认列表
- 确认后后续不再重复提示

### 15.4 数据归属

- 原始店铺标签可通过店铺别名归属到店铺账号ID
- 业务概览和后续聚合都以店铺账号ID为稳定归属入口

## 16. 非目标

本次设计不包含：

- 新建更上层的组织、团队或租户模型
- 抽象跨平台通用授权中心
- 在本次阶段引入过度复杂的会话版本管理

## 17. 结论

这次重构的本质不是“给现有账号页补几个字段”，而是把采集系统的核心对象从语义上理顺：

- 主账号负责登录与会话
- 店铺账号负责测试、采集和业务归属
- 平台店铺ID负责真实平台识别
- 店铺别名负责原始数据入口映射
- 店铺数据域能力负责最终可执行范围

在测试开发环境中直接完成物理重构，是当前成本最低、收益最高的窗口。
