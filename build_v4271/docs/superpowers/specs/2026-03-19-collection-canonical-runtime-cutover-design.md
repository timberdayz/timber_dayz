# 采集正式运行主路径收敛设计

日期：2026-03-19

状态：已实现并已于 2026-03-20 合并到 `main`

## 背景

当前采集模块已经具备以下核心能力：

- 录制器通过 Inspector 采集用户操作步骤
- 生成器将步骤转换为 Python 组件
- 组件以版本化形式保存到 `modules/platforms/<platform>/components/`
- 执行器负责登录、导出、验证码暂停、弹窗治理、会话复用、下载处理与步骤可观测
- 手动任务与定时任务共用执行器主链路

但当前系统仍存在一个关键问题：**正式运行路径还没有真正收敛成唯一主路径**。

具体表现为：

- 正式运行仍存在按模块名直接加载组件的路径
- 版本管理已存在，但正式运行并未完全以 `ComponentVersion.file_path` 为唯一事实源
- 历史模板生成器、原始回放脚本、录制中间产物仍容易被误解为可正式运行资产
- “录制成功”“保存成功”和“正式可运行”这三件事在用户认知与系统行为上还没有被严格区分

这会导致：

- 正式任务运行版本漂移
- 调试路径与生产路径混淆
- 回滚和验收边界不清晰
- 后续 worker 拆分前缺少稳定的运行边界

本设计聚焦第一阶段收敛工作，不涉及 worker 从 API 进程拆出。

## 目标

第一阶段只完成两件事：

1. 让正式采集运行路径收敛成唯一主路径
2. 让正式运行只认版本化 `stable` 组件

本阶段完成后，系统必须满足：

- 手动正式采集和定时采集都只能运行 `stable` 版本
- 正式运行只能通过 `ComponentVersion -> file_path` 解析组件
- 录制、生成、保存得到的组件默认不进入正式采集
- 旧模板脚本、原始回放脚本、`temp/recordings` 中间产物全部失去正式运行资格

## 非目标

本阶段明确不做以下事情：

- 不拆分浏览器采集 worker 出 API 进程
- 不重构整个组件版本表结构
- 不统一所有前端页面视觉样式
- 不立即删除全部历史录制文件
- 不引入新的录制方式或新的生成器

## 方案比较

### 方案 A：硬切换到稳定版主路径

做法：

- 正式运行只允许 `stable` 版本
- 入口必须先解析出 `file_path`
- 没有 `stable` 时正式任务直接失败
- 停止正式路径中的模块名兜底加载

优点：

- 边界最清晰
- 真正切断旧路径
- 版本验收、回滚、调度行为可预测

缺点：

- 会暴露现有未补齐的 stable 组件问题
- 迁移期阻力更大

结论：

推荐。

### 方案 B：优先 stable，缺失时回退 active

做法：

- 尝试优先用 stable
- 没有 stable 时回退到最新 active

优点：

- 切换阻力小
- 存量组件更容易继续运行

缺点：

- 实际没有切断旧路径
- 正式运行版本仍然会漂移
- 版本治理失去强约束意义

结论：

不推荐。

### 方案 C：对外单路径，内部双实现

做法：

- 表面统一入口
- 内部继续兼容旧模块名加载与新版 file_path 解析

优点：

- 对现网更温和

缺点：

- 技术债被隐藏
- 后续更难彻底切断旧路径

结论：

不推荐。

## 推荐方案

采用 **方案 A：硬切换到稳定版主路径**。

正式采集链路的唯一 canonical path 定义为：

`任务创建/调度 -> 解析 stable ComponentVersion -> 按 file_path 加载 Python 组件 -> 执行器运行`

录制链路的 canonical path 定义为：

`Inspector 录制 -> steps -> steps_to_python -> 保存为 draft 版本组件 -> 测试/验收 -> promote to stable`

## 目标状态

### 两条明确链路

系统只保留两条语义明确的链路：

1. **录制链路**
   - 用于生成和修改组件
   - 产物默认是 `draft`
   - 不直接进入正式采集

2. **正式采集链路**
   - 用于手动正式采集、定时采集、并行采集
   - 只允许消费 `stable` 组件
   - 只允许通过 `ComponentVersion.file_path` 解析组件

### 正式运行权限

正式运行权限不再由 `is_active` 单独决定，而由“**当前是否为 stable 且 file_path 可解析**”共同决定。

`is_active` 表示版本有效性，不等于正式可运行权限。

## 版本状态语义

第一阶段不强制改数据库字段，但必须统一以下业务语义：

- `draft`
  - 新录制保存后的默认状态
  - 可以编辑、测试、验收
  - 不允许正式运行

- `candidate`
  - 已通过 lint、基本 smoke、人工检查
  - 可以进入测试/验收流程
  - 不允许正式运行

- `stable`
  - 唯一允许正式采集使用的状态
  - 手动任务、调度任务、并行任务全部只认 stable

- `disabled`
  - 不再有效
  - 不允许任何运行路径使用

### 第一阶段字段映射建议

在不改表结构前提下，可先约定：

- `draft`：`is_active=true, is_stable=false, is_testing=false`
- `candidate`：`is_active=true, is_stable=false, is_testing=true`
- `stable`：`is_active=true, is_stable=true, is_testing=false`
- `disabled`：`is_active=false`

后续若要引入显式状态字段，可在第二阶段之后再做。

## 正式运行架构边界

### 正式入口

正式入口包括：

- 手动任务创建：`backend/routers/collection_tasks.py`
- 定时任务触发：`backend/services/collection_scheduler.py`

这两个入口都必须在创建执行上下文前完成组件解析。

### 新增统一解析层

建议新增：

- `backend/services/component_runtime_resolver.py`

职责：

- 根据 `platform + component_type + data_domain + sub_domain` 构造 `component_name`
- 查询 `ComponentVersion`
- 解析当前唯一可运行的 `stable` 版本
- 校验 `file_path` 存在且可加载
- 返回运行时 manifest

建议输出结构：

```python
{
    "component_name": "shopee/orders_export",
    "version": "1.2.0",
    "file_path": "modules/platforms/shopee/components/orders_export_v1_2_0.py",
    "platform": "shopee",
    "component_type": "export",
    "data_domain": "orders",
    "sub_domain": None,
}
```

### Runtime Manifest

正式运行不再只传 `data_domain`，而是传完整 runtime manifest。

manifest 至少包含：

- 登录组件 manifest
- 导出组件 manifest 列表
- 组件版本号
- file_path
- 任务参数
- 平台和数据域信息

## 执行器改造方向

### 正式路径

`CollectionExecutorV2` 在正式路径中必须：

- 只消费入口层已解析好的 manifest
- 只按 manifest 中的 `file_path` 加载组件
- 不再在正式路径里按模块名兜底 import

### 顺序与并行统一

顺序执行与并行执行必须共享同一套组件解析结果和加载规则：

- 顺序执行使用 manifest 中的 stable 登录组件和 stable 导出组件
- 并行执行在登录后把同一份 stable 解析结果分发到各数据域上下文
- `sub_domain` 也必须进入 manifest，而不是只在部分路径里隐式传递

### 适配器定位收缩

`python_component_adapter.py` 可保留，但角色调整为：

- 录制测试路径使用
- 组件单测/验收路径使用
- 调试路径使用

它不再是正式任务的最终组件选择器。

## 录制与保存规则

### 录制保存默认行为

`POST /recorder/save` 保存新组件时：

- 一律创建新版本
- 默认保存为 `draft`
- 不自动替换 stable
- 不自动进入正式采集

### promote to stable

`promote to stable` 成为唯一正式切换入口。

约束：

- 同一 `component_name` 只能存在一个 stable
- 提升新 stable 时必须取消旧 stable
- 正式采集永远只读取当前 stable

## 旧路径切断规则

以下对象必须明确降级为历史/调试/中间产物，不再具备正式运行资格：

- `modules/utils/collection_template_generator.py`
- `data/recordings/` 下原始回放脚本
- `temp/recordings/` 下录制中间产物
- 同步 Playwright 回放脚本
- 正式路径中的模块名兜底加载

### 切断方式

第一阶段采用“保留文件、切断运行权限”的方式：

1. 切断正式运行入口
2. 切断前端产品入口
3. 在文档和 UI 上重定义这些资产的语义

这样既能保留历史追溯能力，又能终止它们继续进入生产链路。

## 敏感资产治理

对历史录制资产必须附带做治理：

- 清理或脱敏明文账号密码
- 限制 trace、步骤文件、样本脚本的长期保留范围
- 明确这些文件不参与正式采集

这项治理与主路径收敛绑定进行，不应视为可选优化。

## 迁移顺序

### 第一步：建立正式运行解析器

先建立 stable-only 的解析能力，但暂时不删除旧逻辑。

### 第二步：改正式入口

让手动任务与调度任务都先经过解析器，拿到 manifest 后才能进入执行器。

### 第三步：改执行器

让顺序和并行执行统一消费 manifest，并移除正式路径中的模块名兜底。

### 第四步：切断旧路径

当正式路径稳定后，再彻底把旧模板生成器、原始回放脚本、历史录制产物从正式链路中剥离。

## 风险与控制

### 主要风险

- 部分组件尚无 stable 版本
- 某些现有测试/调试流程依赖模块名直载
- 顺序与并行路径尚未完全等价
- 调度任务存在历史配置，切换后会直接失败

### 控制措施

- 先做 stable 覆盖率盘点
- 正式入口增加 preflight 检查
- 调度失败写入明确日志，不启动浏览器
- 保留旧文件但切断正式入口
- 同步更新前端录制页与版本管理页文案

## 验收标准

第一阶段完成后，必须满足：

1. 手动正式采集创建任务时，没有 stable 就直接失败
2. 定时调度触发时，没有 stable 不启动浏览器，只记录失败原因
3. 顺序执行和并行执行都只按 stable `file_path` 运行
4. 录制保存的新版本默认不会进入正式采集
5. promote to stable 后，正式任务与调度都切到该版本
6. `temp/recordings`、`data/recordings`、旧模板生成器不再能进入正式采集链路
7. 前端文案清晰表达“录制 -> 保存版本 -> 测试/验收 -> promote to stable -> 正式运行”

## 对现有代码的影响范围

重点涉及：

- `backend/routers/collection_tasks.py`
- `backend/services/collection_scheduler.py`
- `modules/apps/collection_center/executor_v2.py`
- `modules/apps/collection_center/python_component_adapter.py`
- `backend/services/component_version_service.py`
- 新增 `backend/services/component_runtime_resolver.py`
- `backend/routers/component_recorder.py`
- `frontend/src/views/ComponentRecorder.vue`
- `frontend/src/views/ComponentVersions.vue`

## 结论

第一阶段的本质不是“再做一个版本管理功能”，而是**把正式运行权从代码文件本身转移到 stable 版本解析结果**。

只要这一步完成，系统就能真正切断旧路径，把录制、保存、测试、验收、正式运行串成一条清晰的主链路。之后再做 worker 拆分、运行隔离、资源调度，都会更稳。
