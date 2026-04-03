# Shop Discovery Current Only Design

**日期:** 2026-04-03

**目标:** 为主账号冷启动场景补齐“登录后识别当前店铺并回填店铺账号”的闭环，新增 `shop_discovery(current_only)` 平台能力组件，并明确它与 `login`、`navigation`、`shop_switch`、账号管理页、组件测试页之间的边界。

## 1. 背景

`main_accounts + shop_accounts` 的账号域设计已经明确了两个原则：

1. 登录态主体是主账号。
2. 组件测试、正式采集、结果归属主体是店铺账号。

当前缺口在于冷启动：

- 组件测试页已经改为选择 `shop_account_id`，但新主账号第一次接入时还没有可选店铺账号。
- 现有平台能力里，`login`、`navigation`、`shop_switch` 与“识别当前店铺是谁”之间还没有单独的能力分层。
- 如果 `login` 仍然要求店铺级输入，会形成“没有店铺账号就无法登录，也无法发现店铺账号”的循环依赖。

本设计的核心是打破这个循环依赖：

- `login` 回归主账号级。
- `shop_discovery` 成为登录后的首个店铺发现能力。
- 第一版只做 `current_only`，只识别当前激活店铺，不做全量枚举。

## 2. 设计结论

本次设计确认以下结论：

1. `login` 必须是主账号级组件，输入 `main_account_id`，不再要求已有 `shop_account_id`。
2. `shop_discovery` 是新的 canonical 平台能力组件，不是业务采集组件。
3. `shop_discovery(current_only)` 是第一版范围，只负责识别当前页面对应的店铺上下文。
4. `shop_switch` 不进入第一版冷启动闭环；它属于后续 `enumerate_all` 扩展能力。
5. 账号管理页是店铺探测的标准入口；组件测试页只保留兜底快捷入口。

## 3. 组件分层

### 3.1 主账号级组件

- `login`

职责：

- 恢复或建立主账号登录态
- 管理主账号级 `profile / storage_state / session`

输入：

- `platform`
- `main_account_id`

输出：

- 主账号级登录上下文
- 可复用的主账号会话

### 3.2 平台引导组件

- `navigation`

职责：

- 将页面导航到稳定、可识别当前店铺的落点页

输入：

- `platform`
- 主账号级登录上下文

输出：

- 稳定页面上下文

### 3.3 店铺探测组件

- `shop_discovery`

职责：

- 在已登录浏览器上下文中识别“当前页面正在操作哪个店铺”
- 产出结构化店铺发现结果与证据

第一版模式：

- `current_only`

### 3.4 店铺运行组件

- `shop_switch`
- `export`

职责：

- `shop_switch` 负责切店或枚举店铺
- `export` 负责业务采集

这两个组件不属于本次冷启动最小闭环的必需依赖。

## 4. P1 范围

P1 只实现以下闭环：

```text
main_account
-> login
-> navigation
-> shop_discovery(current_only)
-> discovery record
-> auto bind / pending confirm / create shop account
-> 后续组件测试与正式采集改用 shop_account
```

P1 明确不做：

- 枚举主账号下全部店铺
- 强依赖 `shop_switch`
- 正式业务采集
- 自动运行导出组件
- 复杂的跨页面多轮探测

## 5. `shop_discovery(current_only)` 契约

### 5.1 输入契约

```json
{
  "platform": "shopee",
  "main_account_id": "hongxikeji:main",
  "mode": "current_only",
  "reuse_session": true,
  "expected_region": "SG",
  "capture_evidence": true
}
```

字段说明：

- `platform`: 平台名
- `main_account_id`: 登录主体
- `mode`: 第一版固定为 `current_only`
- `reuse_session`: 优先复用主账号会话
- `expected_region`: 可选，用于提高匹配置信度
- `capture_evidence`: 是否产出截图与取证元数据

### 5.2 输出契约

```json
{
  "success": true,
  "platform": "shopee",
  "main_account_id": "hongxikeji:main",
  "mode": "current_only",
  "discovery": {
    "detected_store_name": "HongXi SG",
    "detected_platform_shop_id": "1227491331",
    "detected_region": "SG",
    "current_url": "https://seller.example/path?shop_id=1227491331",
    "source": {
      "platform_shop_id": "url",
      "store_name": "dom",
      "region": "url"
    },
    "confidence": 0.92
  },
  "match": {
    "status": "auto_bound",
    "shop_account_id": "shopee_sg_hongxi_local",
    "candidate_count": 1
  },
  "evidence": {
    "screenshot_path": "temp/discovery/xxx.png"
  }
}
```

### 5.3 成功判定

以下任一条件满足即可视为 discovery 成功：

- 有 `detected_platform_shop_id`
- 或有 `detected_store_name + detected_region`

以下情况视为失败：

- 关键字段均为空
- 页面无法稳定进入可识别状态
- 主账号登录态无法建立

## 6. 探测方式

`shop_discovery` 探测的不是账号密码，而是“当前登录后店铺上下文”。

第一版探测来源按以下优先级执行：

### 6.1 URL 参数

优先提取：

- `shop_id`
- `cnsc_shop_id`
- `region`
- `shop_region`

这是第一版最高优先级来源，因为结构稳定、可调试、证据明确。

### 6.2 页面 DOM

读取以下可见区域：

- 页头当前店铺名
- 侧栏店铺名
- 当前店铺信息卡片

### 6.3 页面初始化接口响应

若平台初始化接口明确返回店铺标识，可作为补充来源，但不作为第一版必需项。

### 6.4 浏览器存储

读取：

- `localStorage`
- `sessionStorage`

只作为补充，不作为第一版主路径。

## 7. Playwright 执行步骤

标准执行顺序固定为：

1. 恢复主账号会话，必要时执行 `login`
2. 执行 `navigation`
3. 等待页面进入稳定可识别状态
4. 采集 URL / DOM / 可用响应信息
5. 统一整理为结构化 discovery 结果
6. 保存证据截图
7. 返回 discovery 结果给上层 service/router

`shop_discovery` 组件本身不负责数据库写入，也不负责创建店铺账号。

## 8. 匹配与绑定规则

发现结果返回后，由后端 service 负责系统匹配。

匹配优先级：

1. `platform + platform_shop_id`
2. `platform + alias_normalized`
3. `platform + store_name + region`

匹配结果：

- 唯一命中：`auto_bound`
- 多个候选：`pending_confirm`
- 零候选：`no_match`

当 `no_match` 时，允许用户基于本次 discovery 结果直接创建新 `shop_account`。

## 9. Discovery 状态机

第一版状态控制保持克制，只保留以下状态：

- `detected`
- `auto_bound`
- `pending_confirm`
- `created_shop_account`
- `failed`

说明：

- `detected`: 已提取到店铺上下文，但尚未确认归属
- `auto_bound`: 已自动匹配到现有 `shop_account`
- `pending_confirm`: 存在多个候选或置信度不足，需用户确认
- `created_shop_account`: 用户基于本次 discovery 创建了新店铺账号
- `failed`: 未提取到有效店铺上下文或运行失败

## 10. 后端 API

### 10.1 触发当前店铺探测

- `POST /main-accounts/{main_account_id}/shop-discovery/current`

职责：

- 以主账号为输入触发一次 `shop_discovery(current_only)`
- 返回本次 discovery 结果

### 10.2 查看 discovery 记录

- `GET /platform-shop-discoveries`

支持按以下维度筛选：

- `platform`
- `main_account_id`
- `status`

### 10.3 确认绑定

- `POST /platform-shop-discoveries/{id}/confirm`

职责：

- 将 discovery 结果确认绑定到指定 `shop_account_id`

### 10.4 基于 discovery 创建店铺账号

- `POST /platform-shop-discoveries/{id}/create-shop-account`

职责：

- 使用 discovery 结果预填并创建新的 `shop_account`

## 11. 前端交互

### 11.1 账号管理页标准入口

在主账号列表行增加按钮：

- `探测当前店铺`

点击后流程：

1. 恢复或创建主账号会话
2. 执行 `login`
3. 执行 `navigation`
4. 执行 `shop_discovery(current_only)`
5. 展示结果与后续动作

### 11.2 结果展示

前端至少展示：

- 平台
- 主账号ID
- 探测到的店铺名
- 探测到的 `platform_shop_id`
- 探测到的区域
- 当前页面 URL
- 证据截图
- 匹配状态

### 11.3 结果分支

- `auto_bound`: 显示“已自动绑定到 xxx”
- `pending_confirm`: 展示候选店铺账号列表，供用户确认
- `no_match`: 提供“创建店铺账号”
- `failed`: 展示失败原因、截图、重试按钮

### 11.4 组件测试页兜底入口

组件测试页仍然以 `shop_account_id` 为正式测试目标。

若用户发现当前主账号下尚无可选店铺账号，可提供：

- `先探测当前店铺`

但该入口只是快捷跳转或调用同一套 discovery 流程，不改变“正式测试目标必须是店铺账号”的语义。

## 12. 置信度与失败策略

### 12.1 置信度规则

- `0.95`: 有 `platform_shop_id`，且同时有 `store_name` 或 `region`
- `0.80`: 无 `platform_shop_id`，但有 `store_name + region`
- `0.60`: 仅有 `store_name`
- `0.00`: 关键字段为空

### 12.2 重试策略

第一版只做有限重试：

1. 首次失败后重新执行一次 `navigation`
2. 若仍失败，刷新页面后再次提取
3. 三次内仍失败则返回 `failed`

不做：

- 无限重试
- 自动切换多个业务页
- 自动启动导出组件
- 将 discovery 与业务采集强耦合

## 13. 验收标准

满足以下条件即可认为 P1 可上线验证：

1. `login` 已回归主账号级输入
2. 账号管理页可从主账号触发一次当前店铺探测
3. 探测结果至少可稳定输出 `store_name` 或 `platform_shop_id`
4. 用户可基于 discovery 结果自动绑定或创建新 `shop_account`
5. 组件测试页仍坚持店铺账号级测试目标，不回退到主账号级测试

## 14. 后续阶段

P2 再进入：

- `shop_discovery(enumerate_all)`
- 与 `shop_switch` 深度集成
- 一主多店批量枚举
- 更丰富的接口响应取证
- 平台差异化 discovery 策略

第一版不提前预埋复杂的多店状态机，先以 `current_only` 形成真实可用闭环。
