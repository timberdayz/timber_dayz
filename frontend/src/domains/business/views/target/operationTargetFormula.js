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
