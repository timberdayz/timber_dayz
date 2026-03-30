# pwcli + agent 组件调试 SOP

版本: v1.0  
更新日期: 2026-03-30  
适用范围:
- 组件版本管理页测试失败后的调试
- `tools/test_component.py` 失败后的调试
- `login / navigation / date_picker / filters / export` 组件局部复现

---

## 1. 目标

这份 SOP 定义的是一套标准的 `pwcli + agent` 调试流程。

它不是正式验收流程，也不是录制 SOP 的重复版本，而是用来解决下面这类问题：

- 正式测试失败了，但不知道具体哪一步错了
- 代码看起来执行了，页面状态却没有按预期变化
- 不确定是 locator、参数映射、控件提交、成功信号还是上下文问题
- 需要把失败拆成可复现、可观察、可修复的局部步骤

一句话原则：

`正式测试负责发现失败；pwcli + agent 负责复现失败、核对状态、定位根因。`

---

## 2. 与正式测试的关系

### 2.1 正式测试负责验收

正式测试仍然使用：

- 组件版本管理页
- `tools/test_component.py`
- 真实账号
- 持久化 profile
- 验证码回填
- 下载目录 / 运行时上下文

正式测试回答的问题是：

- 组件能否进入真实运行链
- 在正式上下文下是否达成业务成功标准

### 2.2 `pwcli + agent` 负责调试

`pwcli + agent` 回答的问题是：

- 失败到底发生在哪一步
- 该步前后页面状态有没有真的变化
- 动作是否提交成功
- 根因属于哪一类

所以：

- 正式测试是验收
- `pwcli + agent` 是诊断器

---

## 3. 标准调试输入

一旦正式测试失败，先固定收集这 3 类输入，不要先猜代码。

### 3.1 必要输入

- `temp/component_tests/<test_id>/config.json`
- `temp/component_tests/<test_id>/progress.json`
- `temp/test_results/<latest-error>.png`

### 3.2 可选补充输入

- `result.json`
- `verification_state.json`
- `verification_response.json`
- 浏览器控制台错误

### 3.3 输入用途

- `config.json`：告诉 agent 测试用的账号、平台、参数
- `progress.json`：告诉 agent 失败阶段和错误信息
- 错误截图：告诉 agent 页面最后真实长什么样

---

## 4. 标准调试流程

### 4.1 先判断失败阶段

先从 `progress.json` 判断失败属于哪一类：

- `login`
- `navigation`
- `date_picker`
- `filters`
- `export`

原则：

- 只复现失败阶段
- 不重做无关步骤

### 4.2 用同账号、同平台、同 profile 打开 `pwcli`

优先复用已经存在的 PowerShell profile 命令：

- `Open-PwcliMiaoshou`
- `Open-PwcliShopee`
- `Open-PwcliTiktok`
- `pwsnap`
- `pwnote`
- `pwshot`
- `pwpack`

目标不是重新跑整条链，而是用和正式测试尽量一致的账号上下文复现失败阶段。

### 4.3 只复现失败阶段

例如：

- `login` 失败：只复现登录页到首页
- `date_picker` 失败：只复现日期控件打开、选择、提交
- `filters` 失败：只复现筛选器打开、选择、关闭
- `export` 失败：只复现导出菜单打开、导出触发、下载确认

不要把调试阶段重新录成一条长链。

### 4.4 每个关键动作都保留 before / after

每一步固定保留：

- `01-<name>-before.md`
- `01-<name>-after.md`

必要时补：

- `01-note.md`
- `01-<name>.png`

最小模板：

```powershell
pwsnap 01-step-before
# 手工执行动作
pwsnap 01-step-after
pwnote 01-note expected=页面应出现某个变化
```

### 4.5 agent 只判断“页面状态有没有真的变化”

不要只看代码里有没有执行 click / fill。

必须判断：

- 面板是否真的打开
- 目标按钮是否真的被选中
- 输入值是否真的写回筛选条
- 浮层是否真的关闭
- 搜索结果是否真的刷新
- 下载是否真的触发

调试的核心公式：

`动作 + before snapshot + after snapshot + 预期状态变化`

### 4.6 根因分类

调试时统一按以下类别归因：

- `locator_wrong`
- `scope_too_wide`
- `parameter_mapping_wrong`
- `action_not_committed`
- `success_signal_wrong`
- `runtime_context_issue`

统一分类有两个好处：

- 后续失败不需要重新发明描述语言
- 更容易沉淀成规则或自动化分析

### 4.7 修代码后先做局部回归

不要每次修完就直接回前端跑整条正式链。

优先做：

- 相关单元测试
- 相关契约测试
- 必要时再用 `pwcli` 复现一次关键步骤

### 4.8 最后回到正式测试复验

只有正式测试重新通过，问题才算关闭。

标准闭环：

`正式测试失败 -> pwcli 复现 -> agent 定位 -> 修代码 -> 局部回归 -> 正式测试复验`

---

## 5. 标准命名规范

### 5.1 work tag

建议使用：

- `login-debug`
- `orders-export-debug`
- `date-picker-debug`
- `filters-debug`

### 5.2 文件名

建议统一：

- `01-open-before.md`
- `01-open-after.md`
- `02-apply-before.md`
- `02-apply-after.md`
- `02-note.md`

### 5.3 note 内容

`note` 只写必要信息：

- `expected=...`
- `actual=...`
- `phase=...`

不要把 note 写成长篇分析。

---

## 6. 哪些场景必须补 note / screenshot

以下场景不要只留 snapshot：

- 验证码
- 弹窗
- iframe
- 下载
- 新标签页
- disabled -> enabled
- 点击后页面无明显变化，但预期应该变化

这类步骤至少补：

- `note.md`
- 必要时 `screenshot.png`

---

## 7. 各类组件的最小调试单元

### 7.1 `login`

只复现：

- 输入账号密码
- 点击登录
- 验证码回填
- 首页成功信号

### 7.2 `navigation`

只复现：

- 打开目标菜单
- 点击目标页面入口
- 判断目标页特征是否出现

### 7.3 `date_picker`

只复现：

- 打开日期控件
- 选择快捷项或填写自定义范围
- 判断筛选条显示值是否真的更新

### 7.4 `filters`

只复现：

- 打开筛选器
- 判断全选 / 指定状态是否真的生效
- 面板关闭后状态是否保留

### 7.5 `export`

只复现：

- 打开导出菜单
- 点击导出项
- 判断下载是否真实触发并落地

---

## 8. `pwcli + agent` 调试的边界

### 8.1 它不代替正式测试

`pwcli + agent` 不能替代：

- 组件版本管理页测试
- 运行时 profile / 验证码 / 下载链路验证
- stable 验收

### 8.2 它最适合做什么

- 失败复现
- 局部状态核对
- locator 精修
- 参数映射核对
- 成功信号设计
- 改后快速回归

---

## 9. 推荐的后续自动化方向

后续可以把这条调试链进一步自动化成：

### 9.1 失败转调试任务

当正式测试失败时，自动读取：

- `config.json`
- `progress.json`
- 失败截图

再生成一份 `pwcli + agent` 调试任务输入。

### 9.2 agent 自动生成局部复现步骤

根据失败阶段自动给出：

- 应打开哪个页面
- 应抓哪些 before / after
- 应重点观察什么状态变化

### 9.3 调试结果反哺组件规则

每次根因确认后，优先沉淀为：

- locator 收紧
- 参数映射补齐
- 成功信号增强
- 环境基线规则

---

## 10. 一句话工作法

以后统一这样执行：

`先用正式测试发现失败，再用 pwcli + agent 把失败拆成局部可观察的页面状态问题，修完后再回正式测试验收。`

