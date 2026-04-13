# 审批中心运行手册

## 当前能力

审批中心当前已经提供：

- 我的申请
- 审批历史
- 流程配置（只读模板视图）
- 审批详情查看
- 审批通过 / 驳回 / 撤回

统一待办仍然保留在任务中心：

- 审批实例本身属于审批中心
- 当前待审批步骤会投影成任务中心中的一条待办
- 用户日常处理入口仍然是 `我的待办`

## 已接入的审批类型

当前已经接入审批中心的审批类型：

1. 用户注册审批
   - 注册创建 `pending` 用户时自动提交审批实例
   - 管理员在用户管理里审批通过 / 拒绝时回写审批中心

2. 月度利润结算审批
   - 结算重建成功后自动提交审批实例
   - 财务 / 管理员在结算页面批准时回写审批中心

3. 跟投结算审批
   - 结算计算成功且返回 settlement id 后自动提交审批实例
   - 财务 / 管理员在结算页面批准时回写审批中心

## 当前模板列表

审批模板当前至少包含：

- `user_registration_approval`
- `monthly_profit_settlement_approval`
- `follow_investment_settlement_approval`

其他模板会随着后续业务接入继续扩展。

## 当前已知限制

1. 流程配置页当前为只读模板视图
   - 还未开放图形化流程编辑
   - 还未开放多级条件分支编排

2. 当前审批人解析规则仍然偏轻量
   - 用户注册 / 财务结算审批默认解析到首个活跃 admin / superuser
   - 后续应逐步迁移到显式流程配置

3. HR 请假 / 加班审批尚未正式接入
   - 原因是现有 `hr_attendance.py` 审批接口没有统一 `current_user` 依赖
   - 需要先补权限与审批人模型，再接入审批中心

## 关键接口

审批中心 API：

- `GET /api/approval-center/requests`
- `GET /api/approval-center/history`
- `GET /api/approval-center/templates`
- `GET /api/approval-center/{approval_id}`
- `POST /api/approval-center/{approval_id}/approve`
- `POST /api/approval-center/{approval_id}/reject`
- `POST /api/approval-center/{approval_id}/withdraw`

## 前端页面

- `frontend/src/views/approval/MyRequests.vue`
- `frontend/src/views/approval/ApprovalHistory.vue`
- `frontend/src/views/approval/WorkflowConfig.vue`

## 验证命令

后端：

```powershell
python -m pytest backend/tests/test_approval_center_schema.py backend/tests/test_approval_center_service.py backend/tests/test_approval_center_routes.py backend/tests/test_user_registration_api.py backend/tests/test_monthly_profit_settlement_routes.py backend/tests/test_follow_investment_routes.py -q
```

前端：

```powershell
node --test frontend/scripts/employeeTaskUi.test.mjs frontend/scripts/approvalCenterUi.test.mjs
npm -C frontend run type-check
```
