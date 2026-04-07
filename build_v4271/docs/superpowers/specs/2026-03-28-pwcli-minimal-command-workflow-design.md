# pwcli 最小命令工作流设计

日期: 2026-03-28  
状态: Draft  
范围: 采集组件开发工作流，不涉及运行时执行器改造

## 背景

当前仓库已经明确将 `pwcli + playwright skill + agent` 设为采集组件开发主流程，但实际操作仍然偏重手工约定：

- 用户需要记住 `pwcli` 原始命令
- 用户需要手工组织 `before / after snapshot`
- 用户需要手工命名步骤与目录
- 用户需要自己判断哪些证据足以交给 agent

这导致主流程虽然正确，但操作成本偏高，且不同人执行时容易漂移。

本设计要解决的问题不是某一个组件如何录制，而是让当前系统下的 `pwcli + agent` 形成一套统一、低摩擦、可重复的最小工作流。

## 目标

1. 降低用户操作成本，让用户尽量只记少量命令。
2. 固化正式组件所需的最小证据包标准。
3. 保持 `pwcli` 作为证据采集工具的定位，不让其退化为旧式录制器。
4. 让 agent 接收到的输入尽量稳定、可结构化、可比较。
5. 兼容现有 `scripts/pwcli.ps1` 与 `PWCLI_AGENT_COLLECTION_SOP.md`。

## 非目标

1. 不替代运行时执行器。
2. 不引入新的 Inspector 录制链路。
3. 不让 `pwcli` 直接生成正式组件。
4. 不覆盖版本管理、stable 提升或生产调度逻辑。

## 设计原则

### 1. 最小动作原则

用户每一步尽量只做一件事：

- 打开会话
- 抓取状态
- 执行动作
- 再抓一次状态
- 可选补一句说明

### 2. 证据优先原则

正式组件生成依赖的是状态变化证据，而不是动作回放脚本。

### 3. 语义优先原则

步骤语义优先通过目录名、文件名和少量说明表达，而不是强制填写大块 JSON。

### 4. 分层原则

- `pwcli`: 采证
- agent: 分析与生成组件
- 组件测试: 校验
- 版本管理: 沉淀 stable

## 候选方案

### 方案 A：完全自由式 `pwcli`

用户只使用原始 `pwcli` 命令，自行组织所有目录、文件和命名。

优点：

- 零额外封装
- 与原始 `playwright-cli` 一致

缺点：

- 学习成本高
- 输出风格不统一
- agent 输入质量容易波动

### 方案 B：最小命令集封装

在 `scripts/pwcli.ps1` 之上提供 4 到 5 个固定命令，统一目录、命名和证据包结构。

优点：

- 操作最简
- 证据包结构稳定
- 易于培训和复制
- 不改变 `pwcli` 的本质定位

缺点：

- 需要额外维护一层脚本
- 需要定义命令边界

### 方案 C：强结构化 manifest 驱动

要求用户每步都填写结构化 JSON manifest，再由 agent 消费。

优点：

- 输入信息最完整
- 自动化潜力高

缺点：

- 用户负担重
- 与“简化操作”的目标冲突

## 推荐方案

推荐采用 **方案 B：最小命令集封装**。

原因：

- 比完全自由式 `pwcli` 更稳
- 比强结构化 manifest 更轻
- 与当前仓库“`pwcli + agent` 是主流程”的方向一致
- 可以渐进式演进，不阻塞现有工作

## 最小命令集

推荐最小命令集如下：

### 1. `pw-open`

用途：

- 统一打开平台工作目录
- 绑定平台 profile
- 绑定任务级 session
- 打开起始页面

最小参数：

- `-Platform`
- `-WorkTag`
- `-Url`

示例：

```powershell
pw-open -Platform miaoshou -WorkTag login -Url "https://erp.91miaoshou.com"
```

### 2. `pw-step`

用途：

- 采集某一步的 `before` 或 `after` 证据
- 统一命名输出文件
- 保存 `pwcli snapshot` 完整输出，而不是只存 `.yml`

最小参数：

- `-Step`
- `-Name`
- `-Phase` (`before` / `after`)

示例：

```powershell
pw-step -Step 01 -Name open-login-page -Phase before
pw-step -Step 01 -Name open-login-page -Phase after
```

输出示例：

- `01-open-login-page-before.txt`
- `01-open-login-page-after.txt`

### 3. `pw-note`

用途：

- 仅在复杂步骤下补一句语义说明
- 不强制 JSON

最小参数：

- `-Step`
- `-Text`

示例：

```powershell
pw-note -Step 04 -Text "action=click 登录按钮; expected=进入工作台或出现验证码"
```

输出示例：

- `04-note.txt`

### 4. `pw-shot`

用途：

- 在复杂场景补截图
- 适用于验证码、弹窗、iframe、下载确认框

最小参数：

- `-Step`
- `-Name`

示例：

```powershell
pw-shot -Step 04 -Name captcha-visible
```

### 5. `pw-pack`

用途：

- 汇总当前工作目录证据
- 输出可直接交给 agent 的清单
- 检查缺失项

最小参数：

- `-WorkTag`

示例：

```powershell
pw-pack -WorkTag miaoshou-login
```

## 工作目录设计

建议统一目录结构：

```text
output/playwright/
  work/
    miaoshou-login/
      01-open-login-page-before.txt
      01-open-login-page-after.txt
      02-fill-username-before.txt
      02-fill-username-after.txt
      04-note.txt
      04-captcha-visible.png
```

说明：

- 一个组件一个 `work` 目录
- 一个目录对应一次完整证据收集任务
- 文件按步骤编号排序

## 正式组件证据包最低要求

### 普通步骤

必须有：

- `before.txt`
- `after.txt`

### 复杂步骤

以下场景至少额外补一项：

- 验证码
- 弹窗
- iframe
- 新标签页
- 下载
- disabled -> enabled
- 悬停展开菜单

补充形式：

- `note.txt`
- `png`
- 必要时 `trace.zip`

## 与 agent 的衔接规则

agent 在消费证据包时应遵循：

1. 优先读取 `before / after` 的完整 snapshot 输出。
2. 以文件名作为步骤语义第一来源。
3. 以 `note.txt` 作为复杂步骤的补充语义来源。
4. 不把 `pwcli` 交互记录直接当正式组件源码。
5. 生成结果必须升级为 canonical Python 组件。

## 用户最小操作流

推荐用户视角下的标准流程：

1. `pw-open`
2. `pw-step before`
3. 用户手工执行页面动作
4. `pw-step after`
5. 复杂步骤时执行 `pw-note` 或 `pw-shot`
6. 所有关键步骤完成后执行 `pw-pack`
7. 将工作目录交给 agent 生成组件

## 设计决策

### 为什么不强制 `step.json`

因为当前目标是降低用户成本。只要保留：

- 完整 snapshot 输出
- 清晰文件命名
- 少量复杂步骤说明

agent 已能稳定理解大部分页面状态变化。

`step.json` 可保留为可选扩展，而不是默认入口。

### 为什么要保存 snapshot 完整输出而不是只保存 `.yml`

因为 `pwcli snapshot` 的终端输出会包含：

- `Page URL`
- `Page Title`
- snapshot 文件路径

这比单独保存 `.yml` 更适合直接交给 agent。

## 风险与约束

1. 如果文件命名过于随意，agent 理解成本会升高。
2. 如果用户只保留 `.yml` 而不保留 snapshot 完整输出，URL 信息会丢失。
3. 如果用户把多个组件证据混在同一目录，会削弱组件边界。
4. 如果用户跳过复杂步骤说明，验证码和弹窗场景会退化为草稿质量。

## 建议的下一步

1. 在 `scripts/` 中实现最小命令集包装。
2. 为 `pw-pack` 定义证据完整性检查规则。
3. 更新 `PWCLI_AGENT_COLLECTION_SOP.md`，加入命令示例。
4. 选 `miaoshou/login` 作为第一个试点组件。
