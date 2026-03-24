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
    return 'vendor-element-plus'
  }

  return 'vendor-misc'
}
