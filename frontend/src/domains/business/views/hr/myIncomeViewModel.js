export function buildMyIncomeSummaryCards(income = {}) {
  const payroll = income?.breakdown?.payroll ?? null
  const fixedSalary = income?.base_salary ?? (payroll ? Number(payroll.base_salary || 0) + Number(payroll.position_salary || 0) : null)

  return [
    {
      key: 'total_income',
      title: '当月实发',
      value: income?.total_income ?? payroll?.net_salary ?? null
    },
    {
      key: 'fixed_salary',
      title: '固定薪资',
      value: fixedSalary
    },
    {
      key: 'performance_salary',
      title: '绩效工资',
      value: payroll?.performance_salary ?? null
    },
    {
      key: 'commission',
      title: '提成',
      value: income?.commission_amount ?? payroll?.commission ?? null
    }
  ]
}

export function buildMyIncomeExplanations() {
  return [
    {
      key: 'commission_source',
      title: '提成来源',
      body: '提成来自店铺利润分配结果，当前口径已包含店铺绩效系数影响。'
    },
    {
      key: 'performance_salary_source',
      title: '绩效工资来源',
      body: '绩效工资按固定薪资基座乘以绩效比例和个人绩效得分计算。'
    },
    {
      key: 'performance_score_source',
      title: '绩效得分来源',
      body: '个人绩效得分当前来自店铺绩效继承结果，再叠加考勤和人工调整项。'
    }
  ]
}
