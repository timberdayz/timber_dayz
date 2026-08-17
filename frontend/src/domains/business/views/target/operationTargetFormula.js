function roundHalfUp(value) {
  return Math.floor(value + 0.5)
}

function pending(formula) {
  return { status: 'pending', auto_score: null, formula }
}

export function buildOperationEntryPreview(metric = {}) {
  const input = metric.input_payload || {}
  const inputKind = metric.input_kind
  const maxScore = Number(metric.max_score || 0)

  if (inputKind === 'training_counts') {
    const completed = input.completed_count
    const required = input.required_count
    const formula = `得分 = 四舍五入(${maxScore} × 已完成人数 / 应完成人数)；应完成人数为 0 时按 100% 计。`
    if (completed == null || required == null || completed < 0 || required < 0 || completed > required) return pending(formula)
    const rate = required === 0 ? 1 : Number(completed) / Number(required)
    return { status: 'completed', auto_score: roundHalfUp(maxScore * rate), formula }
  }

  if (inputKind === 'special_check') {
    const formula = `通过得 ${maxScore} 分，部分完成得四舍五入(${maxScore} × 50%) 分，未通过得 0 分。`
    const result = input.result
    const note = String(input.note || '').trim()
    if (!['passed', 'partial', 'failed'].includes(result) || (['partial', 'failed'].includes(result) && !note)) return pending(formula)
    const rate = result === 'passed' ? 1 : result === 'partial' ? 0.5 : 0
    return { status: 'completed', auto_score: roundHalfUp(maxScore * rate), formula }
  }

  const target = Number(metric.target_value)
  const actual = input.actual_value
  const direction = metric.metric_direction
  const formula = direction === 'lower_better'
    ? `实际值不高于目标 ${metric.target_value} 时得 ${maxScore} 分；超过目标时按目标值 / 实际值比例四舍五入。`
    : `得分 = 四舍五入(${maxScore} × min(实际值 / 目标值 ${metric.target_value}, 100%))。`
  if (actual == null || !Number.isFinite(target) || target < 0 || !['higher_better', 'lower_better'].includes(direction)) return pending(formula)
  const numericActual = Number(actual)
  if (!Number.isFinite(numericActual) || numericActual < 0 || (direction === 'higher_better' && target <= 0)) return pending(formula)
  const rate = direction === 'higher_better'
    ? Math.min(numericActual / target, 1)
    : numericActual <= target ? 1 : target / numericActual
  return { status: 'completed', auto_score: roundHalfUp(maxScore * rate), formula }
}

export function buildOperationTargetPreview(form = {}, metric = null) {
  if (!metric) {
    return { calculation: '请选择运营指标模板', score: '—' }
  }

  const direction = metric.direction || form.metric_direction || ''
  const maxScore = Number(form.max_score || 0)

  if (direction === 'manual_score' || form.manual_score_enabled) {
    const score = Math.max(0, Math.min(Number(form.manual_score_value || 0), maxScore))
    return {
      calculation: `manual_score=${score.toFixed(2)}`,
      score: `${score.toFixed(2)} 分`
    }
  }

  if (!form.target_value || form.achieved_value == null) {
    return {
      calculation: '缺少目标值或实际值，当前不参与绩效得分',
      score: '0.00 分'
    }
  }

  const targetValue = Number(form.target_value || 0)
  const achievedValue = Number(form.achieved_value || 0)

  if (direction === 'higher_better') {
    const ratio = Math.min(Math.max(achievedValue / targetValue, 0), 1)
    return {
      calculation: `min(${achievedValue.toFixed(2)} / ${targetValue.toFixed(2)}, 1) × ${maxScore.toFixed(2)}`,
      score: `${(maxScore * ratio).toFixed(2)} 分`
    }
  }

  const ratio = achievedValue <= targetValue ? 1 : Math.min(Math.max(targetValue / achievedValue, 0), 1)
  let score = maxScore * ratio
  let penalty = 0
  if (form.penalty_enabled && form.penalty_threshold != null && achievedValue > Number(form.penalty_threshold || 0)) {
    penalty = Math.min(
      (achievedValue - Number(form.penalty_threshold || 0)) * Number(form.penalty_per_unit || 0),
      Number(form.penalty_max || 0)
    )
  }
  score = Math.max(score - penalty, -maxScore)
  return {
    calculation: `base=min(${targetValue.toFixed(2)} / ${Math.max(achievedValue, 1e-9).toFixed(2)}, 1) × ${maxScore.toFixed(2)}; penalty=${penalty.toFixed(2)}`,
    score: `${score.toFixed(2)} 分`
  }
}
