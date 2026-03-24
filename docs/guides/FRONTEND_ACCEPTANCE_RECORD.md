# 前端验收记录

更新时间：2026-03-24

使用说明：
- 每完成一页人工验收，就在对应行更新结果
- `人工状态` 建议只使用：`PASS` / `PASS_WITH_FIXES` / `BLOCKED` / `TODO`
- `问题类型` 建议使用：`视觉` / `布局` / `交互` / `数据` / `权限`
- `处理动作` 可写成简短命令式说明，例如“修复筛选栏换行”“补非空 SMTP 样本”

建议执行顺序：
1. 先验第一批核心页面，优先建立视觉和交互基线
2. 再验第二批高频管理页面，重点看表格、批量操作、危险操作和弹窗
3. 最后补特殊样本页面，处理真实业务数据或非空配置样本

记录规则：
- 若页面可用但存在轻微视觉/交互问题，记录为 `PASS_WITH_FIXES`
- 若页面出现阻塞业务使用的问题，记录为 `BLOCKED`
- 每次验收只记录最重要的 1-3 个问题，不写泛泛描述
- 修复完成后二次验收，直接更新同一行，不另起新记录

建议问题类型用法：
- `视觉`：标题层级、卡片风格、间距、颜色、排版
- `布局`：换行、溢出、表格宽度、响应式错位
- `交互`：按钮无反馈、弹窗异常、切换/筛选不符合预期
- `数据`：空态、错误态、非空数据、统计值不正确
- `权限`：按钮显隐不对、页面不可见、角色限制错误

建议初判规则：
- `建议初判 = PASS_WITH_FIXES`
  适用于：页面结构已统一、自动化已通过，但仍未经过人工点击流确认
- `建议初判 = BLOCKED`
  仅适用于：当前已知缺真实样本或高风险操作尚未验证，存在明显业务阻塞可能
- `建议初判 = PASS`
  不预填。只有人工验收实际完成后再填写

## 第一批核心页面

建议顺序：
1. `BusinessOverview`
2. `SystemConfig`
3. `TargetManagement`
4. `UserManagement`
5. `RoleManagement`
6. `PermissionManagement`
7. `SalesDashboardV3`
8. `InventoryManagement`

| 页面 | 优先级 | 风险 | 自动化 | 建议初判 | 人工状态 | 首要检查点 | 高风险关注 | 建议问题类型 | 常见故障提示 | 处理动作 | 验收人 | 日期 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `BusinessOverview` | P0 | HIGH | SMOKE_PASS + PERF_PASS | PASS_WITH_FIXES | TODO | 全局日期、对比区、店铺赛马、流量排名 | 模块切换多、数据密度高，最容易出现布局和加载态问题 | 视觉 / 布局 / 数据 | 日期切换后模块未同步、表格/图表错位、空态与加载态混淆 |  |  |  |
| `SalesDashboardV3` | P1 | MEDIUM | SMOKE_PASS | PASS_WITH_FIXES | TODO | 页面头部、图表区、加载态 | 页面结构未像 `BusinessOverview` 一样深度收口 | 视觉 / 布局 | 图表区留白、标题层级弱、加载反馈不明显 |  |  |  |
| `SystemConfig` | P0 | MEDIUM | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 表单全宽输入、保存、刷新、说明卡片 | 配置保存成功但页面反馈需人工确认 | 交互 / 数据 | 保存后提示异常、刷新后值回填不完整、说明区层级不清 |  |  |  |
| `InventoryManagement` | P1 | MEDIUM | SMOKE_PASS | PASS_WITH_FIXES | TODO | 列表区、筛选区、分页、空态 | 主要风险在表格密度和空态视觉 | 布局 / 数据 | 筛选栏拥挤、分页错位、空态信息不足 |  |  |  |
| `TargetManagement` | P0 | HIGH | SMOKE_PASS | PASS_WITH_FIXES | TODO | 月度/产品/战役三视图、拆分输入、详情弹窗 | 视图和拆分逻辑复杂，容易出现交互遗漏 | 交互 / 数据 / 布局 | 视图切换状态串扰、拆分总和不对、详情卡片信息不全 |  |  |  |
| `UserManagement` | P0 | HIGH | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 创建、编辑、重置密码、已删除用户恢复 | 弹窗多、权限操作多，容易出现按钮链路问题 | 交互 / 权限 / 数据 | 弹窗提交无反馈、软删除恢复链路异常、角色展示不完整 |  |  |  |
| `RoleManagement` | P0 | HIGH | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 创建、编辑、权限配置弹窗 | 权限配置弹窗是最高风险点 | 交互 / 权限 | 权限勾选状态异常、保存后角色权限未更新 |  |  |  |
| `PermissionManagement` | P0 | HIGH | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 资源筛选、详情、权限测试、引用角色展示 | 筛选和详情内容正确性需人工确认 | 数据 / 交互 | 筛选无效、详情信息缺失、测试结果提示不清晰 |  |  |  |

## 第二批高频管理页面

建议顺序：
1. `DataSyncFiles`
2. `CollectionTasks`
3. `CollectionHistory`
4. `SystemNotifications`
5. `Sessions`
6. `DatabaseConfig`
7. `SecuritySettings`
8. `SystemLogs`
9. `DataBackup`
10. `SystemMaintenance`
11. `AccountManagement`
12. `NotificationConfig`
13. `ExpenseManagement`

| 页面 | 优先级 | 风险 | 自动化 | 建议初判 | 人工状态 | 首要检查点 | 高风险关注 | 建议问题类型 | 常见故障提示 | 处理动作 | 验收人 | 日期 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `DataSyncFiles` | P0 | HIGH | PROBE_PASS | PASS_WITH_FIXES | TODO | 批量同步、重试、治理概览、历史记录 | 批量操作与危险操作组合，需人工确认交互反馈 | 交互 / 数据 | 批量按钮反馈异常、历史列表未刷新、错误弹窗信息不足 |  |  |  |
| `CollectionTasks` | P0 | HIGH | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 快速采集、任务详情、日志、验证码恢复 | 验证码恢复和任务详情抽屉最容易出问题 | 交互 / 数据 | 任务状态不刷新、详情抽屉信息缺项、验证码恢复链路中断 |  |  |  |
| `CollectionHistory` | P1 | MEDIUM | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 筛选、导出、失败重试、详情对话框 | 失败重试和导出链路需人工确认 | 交互 / 数据 | 筛选条件不生效、导出失败、详情信息不全 |  |  |  |
| `SystemNotifications` | P1 | MEDIUM | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 列表/分组切换、批量已读、删除、中文文案 | 分组视图和中文文案完整性需人工确认 | 交互 / 视觉 | 切换模式后状态错乱、已读/删除反馈不明显、中文文案遗漏 |  |  |  |
| `Sessions` | P1 | MEDIUM | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 当前会话标记、登出其他设备、时间显示 | 会话识别和撤销动作需人工确认 | 交互 / 数据 | 当前设备标记不稳定、登出后列表未刷新 |  |  |  |
| `DatabaseConfig` | P1 | HIGH | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 测试连接、保存、空密码不修改 | 存在真实配置风险，必须人工确认 | 数据 / 交互 | 测试连接反馈不准确、空密码逻辑异常 |  |  |  |
| `SecuritySettings` | P1 | HIGH | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 四个 tab、白名单、提示文本、保存流程 | 多 tab 和白名单操作风险较高 | 交互 / 权限 | tab 切换数据丢失、白名单增删异常、保存后未刷新 |  |  |  |
| `SystemLogs` | P1 | MEDIUM | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 筛选、详情、导出、清空日志 | 清空日志属于危险操作，需明确确认 | 交互 / 数据 | 筛选结果不一致、导出失败、危险操作提示不足 |  |  |  |
| `DataBackup` | P1 | HIGH | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 创建备份、下载、恢复、自动备份配置 | 恢复备份属于高风险操作 | 数据 / 交互 | 创建后列表不刷新、恢复警告不足、自动备份配置保存异常 |  |  |  |
| `SystemMaintenance` | P1 | HIGH | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 缓存清理、数据清理、升级检查 | 数据清理与升级检查属于高风险操作 | 交互 / 数据 | 清理操作反馈不明确、状态刷新不及时 |  |  |  |
| `AccountManagement` | P1 | HIGH | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 批量店铺、导入、能力配置、状态切换 | 批量创建与状态切换需人工确认 | 交互 / 数据 / 权限 | 批量店铺表单异常、状态切换回滚、能力配置展示不完整 |  |  |  |
| `NotificationConfig` | P1 | HIGH | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | SMTP、模板、告警规则 | 非空 SMTP 样本仍缺，结论不能过满 | 数据 / 交互 | SMTP 测试反馈不准、模板/规则保存后未刷新 |  |  |  |
| `ExpenseManagement` | P1 | HIGH | SMOKE_PASS + PROBE_PASS | PASS_WITH_FIXES | TODO | 月度视图、店铺视图、批量保存 | 双视图和批量保存链路较复杂 | 交互 / 数据 | 视图切换状态错乱、批量保存后统计不刷新 |  |  |  |

## 特殊样本补充页面

| 页面 | 优先级 | 风险 | 自动化 | 建议初判 | 人工状态 | 当前缺口 | 首要检查点 | 高风险关注 | 处理动作 | 验收人 | 日期 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `AccountAlignment` | P0 | HIGH | PASS_EMPTY_STATE | BLOCKED | TODO | 缺真实业务订单源样本 | 非空数据加载、映射结果、错误提示 | 若继续在空态上验收，结论会失真 | 补真实业务样本后复验 |  |  |
| `NotificationConfig` | P0 | HIGH | PASS_EMPTY_SMTP | PASS_WITH_FIXES | TODO | 缺非空 SMTP 样本 | 非空 SMTP 连接、模板、告警规则 | 若没有 SMTP 样本，不能判定真正可用 | 准备 SMTP 样本后复验 |  |  |

## 验收完成标准

- `PASS`
  - 页面可正常进入
  - 关键操作链路无阻塞
  - 无明显视觉/布局问题
  - 无严重业务或权限问题

- `PASS_WITH_FIXES`
  - 页面可用
  - 有低风险视觉或交互问题
  - 可以继续下一页，同时记录后续修复

- `BLOCKED`
  - 存在影响实际使用的问题
  - 必须先修复再继续推进同一批页面验收
