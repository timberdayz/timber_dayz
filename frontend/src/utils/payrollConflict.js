const PAYROLL_FIELD_LABELS = {
  base_salary: '基本工资',
  position_salary: '岗位工资',
  performance_salary: '绩效工资',
  overtime_pay: '加班费',
  commission: '提成',
  allowances: '津贴',
  bonus: '奖金',
  gross_salary: '应发合计',
  social_insurance_personal: '个人社保',
  housing_fund_personal: '个人公积金',
  income_tax: '个税',
  other_deductions: '其他扣款',
  total_deductions: '扣款合计',
  net_salary: '实发工资',
  social_insurance_company: '公司社保',
  housing_fund_company: '公司公积金',
  total_cost: '公司总成本'
}

const PAYROLL_STATUS_LABELS = {
  draft: '草稿',
  confirmed: '已确认',
  paid: '已发放'
}

export function formatPayrollLockedConflictSummary(details = [], count = 0) {
  if (!Array.isArray(details) || details.length === 0) {
    return `共有 ${count} 份已锁定工资单未被覆盖`
  }

  return details
    .map((item) => {
      const fields = Array.isArray(item.changed_fields)
        ? item.changed_fields.map((field) => PAYROLL_FIELD_LABELS[field] || field).join('、')
        : ''
      const status = PAYROLL_STATUS_LABELS[item.payroll_status] || item.payroll_status || '已锁定'
      return `${item.employee_code}（${status}）: ${fields}`
    })
    .join('\n')
}
