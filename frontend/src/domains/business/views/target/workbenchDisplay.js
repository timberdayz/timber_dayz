const DIRECTION_LABELS = {
  higher_better: '越高越好',
  lower_better: '越低越好',
  manual_score: '按检查结论',
  manual_result: '按任务结论'
}

const GUIDANCE_BY_METRIC = {
  customer_satisfaction: '填写当月客户满意度百分比，例如 95 表示 95%。',
  complaint_count: '填写当月投诉次数，不高于目标次数即可获得满分。',
  reply_timeliness: '填写当月及时回复率，例如 95 表示 95%。',
  operation_special_check: '选择通过、部分完成或未通过；后两种必须填写说明。',
  attendance_compliance_rate: '填写当月考勤达标率，例如 95 表示 95%。',
  training_completion_rate: '填写已完成人数和应完成人数，系统自动计算完成率。',
  personal_goal_completion_rate: '填写当月个人目标实际完成比例，例如 90 表示 90%。',
  personal_special_task: '选择完成、部分完成或未完成；后两种必须填写说明。'
}

export function formatWorkbenchDirection(direction) {
  return DIRECTION_LABELS[direction] || '按目录规则计算'
}

export function formatWorkbenchGuidance(metric) {
  return GUIDANCE_BY_METRIC[metric?.metric_code] || metric?.guidance || '按本月指标规则录入实绩，系统自动计算得分。'
}

export function formatWorkbenchFormula(metric) {
  if (metric?.input_kind === 'training_counts') {
    return '完成率 = 已完成 ÷ 应完成，按自动满分四舍五入取整。'
  }
  if (metric?.input_kind === 'special_check' || metric?.input_kind === 'special_task') {
    return '完成得满分；部分完成得一半分；未完成得 0 分。'
  }
  if (metric?.metric_direction === 'lower_better') {
    return '实际值不高于目标即可得满分；超过目标时按比例计算。'
  }
  return '得分按实际值与固定目标的比例计算，达到目标即可得满分。'
}
