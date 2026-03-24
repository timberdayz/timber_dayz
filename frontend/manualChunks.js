function containsAny(id, patterns) {
  return patterns.some((pattern) => id.includes(pattern))
}

export function resolveManualChunk(id) {
  if (!id.includes('node_modules')) {
    return
  }

  if (id.includes('vue-echarts')) {
    return 'vendor-vue-echarts'
  }

  if (id.includes('zrender')) {
    return 'vendor-zrender'
  }

  if (id.includes('echarts')) {
    if (containsAny(id, ['/chart/', '\\chart\\', 'charts'])) {
      return 'vendor-echarts-charts'
    }
    if (containsAny(id, ['/component/', '\\component\\', 'components'])) {
      return 'vendor-echarts-components'
    }
    return 'vendor-echarts-core'
  }

  if (id.includes('element-plus') || id.includes('@element-plus')) {
    if (
      containsAny(id, [
        '/table',
        '\\table',
        '/pagination',
        '\\pagination',
        '/descriptions',
        '\\descriptions',
        '/statistic',
        '\\statistic',
      ])
    ) {
      return 'vendor-element-plus-data'
    }

    if (
      containsAny(id, [
        '/date-picker',
        '\\date-picker',
        '/time-picker',
        '\\time-picker',
        '/calendar',
        '\\calendar',
      ])
    ) {
      return 'vendor-element-plus-datetime'
    }

    if (
      containsAny(id, [
        '/form',
        '\\form',
        '/input',
        '\\input',
        '/select',
        '\\select',
        '/checkbox',
        '\\checkbox',
        '/radio',
        '\\radio',
        '/switch',
        '\\switch',
        '/upload',
        '\\upload',
      ])
    ) {
      return 'vendor-element-plus-form'
    }

    if (
      containsAny(id, [
        '/message',
        '\\message',
        '/notification',
        '\\notification',
        '/message-box',
        '\\message-box',
        '/loading',
        '\\loading',
        '/dialog',
        '\\dialog',
        '/drawer',
        '\\drawer',
        '/popover',
        '\\popover',
        '/tooltip',
        '\\tooltip',
        '/overlay',
        '\\overlay',
        '/popper',
        '\\popper',
      ])
    ) {
      return 'vendor-element-plus-feedback'
    }

    return 'vendor-element-plus-base'
  }

  return 'vendor-misc'
}
