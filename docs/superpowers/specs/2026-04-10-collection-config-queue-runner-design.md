# Collection Config Queue Runner Design

## Goal

将当前“定时触发后直接后台启动采集配置”的模型，改造成“配置运行实例入队 -> 单 worker 串行消费 -> 当前配置完成后自动续跑下一配置”的模型，确保单台采集机在资源受限条件下优先获得稳定性与成功率。

## Scope

本设计覆盖以下触发来源：

- 定时采集配置
- 手动运行配置

本设计不把以下触发来源并入同一个主队列：

- 手动快速采集任务

但快速采集必须增加运行闸门，在存在运行中的配置队列任务时，默认拒绝直接启动，避免与配置调度并发。

## Non-Goals

- 不在第一阶段引入“全局 2 并行配置执行”
- 不在第一阶段引入“快速采集插队”
- 不改变单个 `CollectionTask` 内部的数据域执行模型
- 不改变现有验证码恢复、日志明细、文件处理的核心行为

## Current Problems

### 1. Scheduler 直接起任务，缺少全局配置级排队

当前 APScheduler 在到点后直接调用配置执行入口，配置再展开为多个 `CollectionTask` 并通过 `asyncio.create_task(...)` 直接后台启动。系统里虽然存在 `TaskQueueService` 与 `queued` 状态设计，但当前配置执行主链路并没有真正接入这一层。

结果是：

- 多个主账号配置如果同一时刻触发，会并发创建并启动任务
- 配置内多个店铺任务也会被直接放飞
- 单机 Playwright 浏览器实例数量不可控

### 2. 系统缺少“配置执行一次”的一等对象

当前只有：

- `CollectionConfig`
- `CollectionTask`

缺少一个“某个配置本次被执行了一次”的持久化对象，导致：

- 无法可靠表达配置级的 `queued/running/completed/failed`
- 无法准确判断“这个主账号配置整体是否已经执行完成”
- 无法围绕配置级建立真正的队列与续跑语义

### 3. 人工错峰不能从根本解决问题

人工将多个主账号配置设置为相隔 10-20 分钟，只是时间层面的规避，不是系统层面的串行消费。它仍然存在以下风险：

- 前一个主账号执行时间超过预估时，与后一个配置重叠
- 不同平台、不同日期范围、不同验证码情况会导致执行时长不稳定
- 运维成本高，扩展性差

## Desired Behavior

系统应满足以下行为：

1. 所有定时配置、手动运行配置都进入统一的“配置运行队列”
2. 队列在第一阶段全局只允许一个配置运行实例处于 `running`
3. 当前配置运行实例完成后，系统立即继续下一条 `queued` 配置
4. 同一时刻即使有多个配置到点触发，也只会形成多条 `queued` 记录，不会并发起采集
5. 一个配置运行实例内部的店铺任务按顺序执行
6. 一个店铺任务内部维持当前默认的顺序数据域执行
7. 快速采集在存在运行中配置实例时默认拒绝启动

## Architecture

### New First-Class Entity: `CollectionConfigRun`

新增配置运行实例实体，用来表示“某个采集配置本次运行了一次”。

建议字段：

- `id`
- `run_id`
- `config_id`
- `platform`
- `main_account_id`
- `trigger_type`，例如 `scheduled` / `manual`
- `status`，例如 `queued` / `running` / `completed` / `partial_success` / `failed` / `cancelled`
- `scheduled_for`
- `started_at`
- `completed_at`
- `error_message`
- `created_at`
- `updated_at`

建议关系：

- `CollectionConfigRun` `1 -> N` `CollectionTask`
- `CollectionTask` 新增 `config_run_id`

该实体负责承载：

- 配置级排队状态
- 配置级执行生命周期
- 配置级结果汇总

### Queue Layers

系统分为三层执行对象：

1. `CollectionConfig`
   - 描述“要采什么”
2. `CollectionConfigRun`
   - 描述“这次实际跑了一次配置”
3. `CollectionTask`
   - 描述“这次配置运行中的某个店铺任务”

执行层级为：

`CollectionConfig` -> `CollectionConfigRun` -> `CollectionTask`

### Queue Ownership

APScheduler 不再负责直接执行采集，而只负责投递配置运行请求。

新增 `CollectionQueueRunner` 常驻后台消费组件，负责：

- 查询是否已有 `running` 的 `CollectionConfigRun`
- 如果没有，则领取最早一条 `queued` 的 `CollectionConfigRun`
- 顺序执行该 run 下的所有 `CollectionTask`
- 执行结束后更新 run 状态
- 立即继续领取下一条 queued run

## Execution Flow

### A. 定时触发

1. APScheduler 到点触发某个 `config_id`
2. 系统创建一条 `CollectionConfigRun(status='queued')`
3. 如果当前没有运行中的 run，则 `CollectionQueueRunner` 立即领取它
4. runner 将 run 标记为 `running`
5. runner 为该 run 展开店铺级 `CollectionTask`
6. runner 按顺序执行这些 `CollectionTask`
7. 所有任务进入终态后，runner 汇总 run 状态并标记终态
8. runner 继续领取下一条 queued run

### B. 手动运行配置

1. 用户点击“运行配置”
2. 系统创建一条 `CollectionConfigRun(status='queued', trigger_type='manual')`
3. 返回 run 已入队的信息，而不是直接返回多个后台任务已启动
4. 由同一个 `CollectionQueueRunner` 负责消费

### C. 快速采集

1. 用户发起快速采集
2. 系统检查当前是否存在 `CollectionConfigRun(status='running')`
3. 如果存在，默认拒绝并返回“配置队列繁忙，请稍后执行”
4. 如果不存在，可沿用现有快速采集路径

### D. 配置内部执行

对于单个 `CollectionConfigRun`：

1. 调用“配置展开服务”生成该 run 对应的店铺级 `CollectionTask`
2. 不再对这些任务执行 `asyncio.create_task(...)` 放飞
3. runner 顺序取每个 `CollectionTask`
4. 调用现有 `_execute_collection_task_background` 或拆出的等价同步编排入口执行该任务
5. 单个 `CollectionTask` 维持当前默认的顺序数据域执行模型

## State Model

### `CollectionConfigRun.status`

建议状态集合：

- `queued`
- `running`
- `completed`
- `partial_success`
- `failed`
- `cancelled`

状态流转：

- `queued -> running`
- `running -> completed`
- `running -> partial_success`
- `running -> failed`
- `queued -> cancelled`
- `running -> cancelled`

### `CollectionTask.status`

保留现有任务状态模型，但它不再承担“配置级排队”的职责。

第一阶段建议保留：

- `pending`
- `running`
- `verification_required`
- `verification_submitted`
- `paused`
- `completed`
- `partial_success`
- `failed`
- `cancelled`
- `interrupted`

队列语义重点上移到 `CollectionConfigRun`。

## File-Level Design

### 1. `modules/core/db/schema.py`

新增：

- `CollectionConfigRun`

修改：

- `CollectionTask` 增加 `config_run_id`
- 增加相应 relationship
- 增加按 `status`、`created_at`、`config_id` 的索引

### 2. Alembic Migration

新增迁移，完成：

- 创建 `collection_config_runs`
- 为 `collection_tasks` 增加 `config_run_id`
- 添加外键与索引

### 3. `backend/services/collection_scheduler.py`

重构定时执行逻辑：

- 当前：到点直接 `create_tasks_for_config(..., start_background=True)`
- 目标：到点仅创建 `CollectionConfigRun(status='queued')`

### 4. `backend/services/collection_config_run_service.py`

新增服务，负责：

- 创建 run
- 查询 queued run
- 原子领取 run
- 更新 run 状态
- 汇总 run 结果

### 5. `backend/services/collection_queue_runner.py`

新增单 worker runner，负责：

- 应用启动时初始化
- 循环或事件驱动消费 queued run
- 单实例串行消费
- 执行完成后触发下一个

### 6. `backend/services/collection_config_execution.py`

重构为“配置展开服务”：

- 保留按配置生成店铺级 `CollectionTask` 的能力
- 默认不再做后台自动启动
- 返回任务列表给 queue runner 顺序执行

### 7. `backend/routers/collection_tasks.py`

重构两个入口：

- `POST /configs/{config_id}/run`
  - 从“立即启动配置任务”改为“创建 queued run”
- 快速采集创建入口
  - 增加运行中配置闸门

### 8. `backend/routers/collection_schedule.py`

健康检查与调度信息扩展为：

- 当前 running 的配置 run 数
- queued 的配置 run 数
- 当前正在执行哪个 `main_account_id / config_id`

## Concurrency Rules

第一阶段采用严格规则：

- 全局最多 1 个 `CollectionConfigRun` 运行
- 同一 run 内部的店铺任务严格顺序执行
- 单个 `CollectionTask` 维持现有默认顺序数据域执行

这样形成完整的三层串行边界：

- 配置级串行
- 店铺任务级串行
- 数据域级默认串行

这不是吞吐最优方案，但对于单台资源有限的采集机，是稳定性最优方案。

## Error Handling

### Run Creation

如果调度器到点但配置已失效：

- 不创建 run
- 记录 warning 日志

如果重复触发同一配置：

- 允许生成新的 queued run，但应避免同一个配置在已有 `queued/running` run 时重复入队
- 第一阶段建议直接做去重保护：
  - 同一 `config_id`
  - 存在 `queued/running`
  - 则拒绝重复入队

### Task Failures Inside a Run

如果某个店铺任务失败：

- 记录到 `CollectionTask`
- 不影响同一个 run 中后续店铺任务继续执行
- run 最终汇总为：
  - 全成功：`completed`
  - 部分失败：`partial_success`
  - 全失败：`failed`

### Verification Pause

如果店铺任务进入 `verification_required` / `paused`：

- 第一阶段建议将该任务视为 run 仍处于 `running`
- queue runner 不切换到下一个配置
- 因为你要求的是“前一个主账号执行完，下一个接续”，而验证码暂停本质上意味着“前一个主账号尚未完成”

这会牺牲吞吐，但保持语义一致和安全。

## Observability

建议新增配置级可观测性：

- 当前运行中的 run
- 队列长度
- 每个 run 已生成多少店铺任务
- 已完成多少店铺任务
- 当前卡在哪个店铺 / 哪个任务

前端与健康接口应能直接展示：

- `main_account_id`
- `config_id`
- `trigger_type`
- `status`
- `queued_at`
- `started_at`
- `completed_at`

## Compatibility Strategy

为了降低改造风险，建议分两步：

### Phase 1

- 引入 `CollectionConfigRun`
- APScheduler 改为入队
- 手动运行配置改为入队
- queue runner 串行消费
- 快速采集增加闸门

### Phase 2

在 Phase 1 跑稳后再考虑：

- 全局最大并行数从 `1` 扩到 `2`
- 快速采集插队策略
- 基于机器负载动态调节并发

## Recommended Initial Policy

第一阶段推荐的生产策略：

- `CollectionConfigRun` 全局单 worker
- 不允许配置 run 并发
- 不允许快速采集在 run 执行期间直接启动
- 所有主账号配置可以使用同一个 cron 时间，系统自动排队续跑

## Testing Strategy

测试应覆盖以下层面：

### Contract Tests

- 创建定时配置时，到点应生成 queued run，而不是直接起任务
- 手动运行配置应创建 queued run
- 快速采集在存在 running run 时被拒绝

### Queue Runner Tests

- 无 running run 时，runner 能领取最早 queued run
- 一个 run 完成后，runner 自动继续下一个 queued run
- 同一配置在 queued/running 存在时不会重复入队

### Integration Tests

- 多个配置同一时刻触发时，仅有一个 run 进入 running
- 其余 run 保持 queued，直到前一个完成
- run 内部多个店铺任务按顺序执行

### Failure Tests

- 单个店铺任务失败时，run 结果为 `partial_success`
- 全部店铺失败时，run 结果为 `failed`
- 验证码暂停时，run 保持 `running`

## Trade-Offs

### Chosen Trade-Off

优先稳定性，而不是吞吐量。

这意味着：

- 单机吞吐下降
- 但采集成功率更高
- 更适合当前单台 Windows 采集机 + Playwright 的现实环境

### Deferred Trade-Off

未来如果采集机扩容、监控成熟、验证码与恢复路径稳定，可以将“全局 1 配置并行”扩展到“全局 2 配置并行”。但这应作为第二阶段优化，而不是当前的基础调度模型。

## Acceptance Criteria

当以下条件满足时，该设计视为完成：

1. 多个主账号配置即使同一时刻定时触发，也不会并发执行
2. 当前配置完成后，下一配置无需等待固定 cron 间隔，立即续跑
3. 手动运行配置不会绕过全局串行队列
4. 快速采集不会在配置运行中偷偷并发抢占资源
5. 前后端都能清晰观察当前运行配置与排队配置状态
