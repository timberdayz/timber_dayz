import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const myRequestsSource = fs.readFileSync(path.resolve(__dirname, '../src/views/approval/MyRequests.vue'), 'utf8')
const approvalHistorySource = fs.readFileSync(path.resolve(__dirname, '../src/views/approval/ApprovalHistory.vue'), 'utf8')
const workflowConfigSource = fs.readFileSync(path.resolve(__dirname, '../src/views/approval/WorkflowConfig.vue'), 'utf8')
const approvalApiSource = fs.readFileSync(path.resolve(__dirname, '../src/api/approvalCenter.js'), 'utf8')

test('my requests page exposes approval request summary and withdrawal flow', () => {
  for (const label of ['我的申请', '申请总数', '审批中', '已完成', '撤回申请', '审批详情']) {
    assert.equal(myRequestsSource.includes(label), true, `MyRequests.vue should contain ${label}`)
  }
})

test('approval history page exposes handled approvals and detail drawer', () => {
  for (const label of ['审批历史', '我的动作', '当前结果', '动作日志', '审批详情']) {
    assert.equal(approvalHistorySource.includes(label), true, `ApprovalHistory.vue should contain ${label}`)
  }
})

test('workflow config page exposes approval template read model', () => {
  for (const label of ['流程配置', '审批模板', '模板名称', '模板编码', '目标页面', '已启用']) {
    assert.equal(workflowConfigSource.includes(label), true, `WorkflowConfig.vue should contain ${label}`)
  }
})

test('approval center api exposes request, history, template and action methods', () => {
  for (const methodName of ['listRequests', 'listHistory', 'listTemplates', 'getApproval', 'approve', 'reject', 'withdraw']) {
    assert.equal(approvalApiSource.includes(methodName), true, `approvalCenter.js should contain ${methodName}`)
  }
})
