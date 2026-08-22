export function getControlledPersonalAuditNotice(employeePerformance) {
  const details = employeePerformance?.calculation_details || {}
  const status = details.status || employeePerformance?.calculation_status
  if (status === 'not_participating') {
    return '本月未参与个人绩效：不产生个人绩效工资或排名，基础工资与独立店铺提成不受影响。'
  }
  if (status !== 'partial') return ''
  const messages = []
  if ((details.missing_personal_metrics || []).length) messages.push('未完成个人运营目标录入')
  if ((details.missing_shop_scores || []).length) messages.push('缺少店铺基础分')
  return messages.length
    ? `个人绩效尚未完成：${messages.join('；')}。暂不进入正式收入、绩效工资和工资结算。`
    : '个人绩效尚未完成，暂不进入正式收入、绩效工资和工资结算。'
}
