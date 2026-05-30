export function buildMyIncomeSummaryCards(income = {}) {
  const payroll = income?.breakdown?.payroll ?? null
  const fixedSalary =
    income?.base_salary ??
    (payroll
      ? Number(payroll.base_salary || 0) + Number(payroll.position_salary || 0)
      : null)

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
      body: '提成来自店铺利润分配结果，口径为店铺利润基数 × 可分配利润率 × 个人提成比例 × 店铺绩效系数。'
    },
    {
      key: 'performance_salary_source',
      title: '绩效工资来源',
      body: '绩效工资来自独立绩效包 × 个人绩效系数，不再使用底薪或岗位工资去参与绩效乘法。'
    },
    {
      key: 'performance_score_source',
      title: '个人绩效来源',
      body: '个人绩效优先由个人绩效输入项驱动，再叠加考勤和人工调整；未配置输入项时才回退到店铺绩效聚合。'
    }
  ]
}
