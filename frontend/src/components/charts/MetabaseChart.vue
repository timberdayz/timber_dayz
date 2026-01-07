<template>
  <div class="metabase-chart-container" :style="{ height: `${height}px` }">
    <!-- 加载状态 -->
    <div v-if="loading" class="chart-loading">
      <el-skeleton :rows="5" animated />
    </div>

    <!-- 错误状态 -->
    <div v-else-if="error" class="chart-error">
      <el-alert
        :title="error"
        type="error"
        :closable="false"
        show-icon
      />
      <el-button @click="reload" type="primary" style="margin-top: 10px">
        重新加载
      </el-button>
    </div>

    <!-- Metabase iframe -->
    <iframe
      v-else
      ref="metabaseIframe"
      :src="iframeUrl"
      class="metabase-iframe"
      frameborder="0"
      :style="{ height: `${height}px`, width: '100%' }"
      @load="onIframeLoad"
      @error="onIframeError"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import metabaseApi from '@/services/metabase'

const props = defineProps({
  // Dashboard ID
  dashboardId: {
    type: [Number, String],
    required: true
  },
  // 筛选器对象
  filters: {
    type: Object,
    default: () => ({})
  },
  // 时间粒度
  granularity: {
    type: String,
    default: 'daily',
    validator: (value) => ['daily', 'weekly', 'monthly'].includes(value)
  },
  // 高度（像素）
  height: {
    type: Number,
    default: 600
  },
  // 是否自动刷新
  autoRefresh: {
    type: Boolean,
    default: false
  },
  // 刷新间隔（秒）
  refreshInterval: {
    type: Number,
    default: 300
  }
})

const emit = defineEmits(['loaded', 'error', 'filter-change'])

// 状态
const loading = ref(true)
const error = ref(null)
const embeddingToken = ref(null)
const metabaseIframe = ref(null)
let refreshTimer = null

// 计算iframe URL
const iframeUrl = computed(() => {
  if (!embeddingToken.value) {
    return null
  }

  const baseUrl = import.meta.env.VITE_METABASE_URL || 'http://localhost:8080'
  const params = new URLSearchParams()

  // 添加嵌入token
  params.append('embedding_token', embeddingToken.value)

  // 添加筛选器参数
  if (props.filters.date_range) {
    params.append('date_range', props.filters.date_range)
  }
  if (props.filters.platform) {
    if (Array.isArray(props.filters.platform)) {
      props.filters.platform.forEach(p => params.append('platform', p))
    } else {
      params.append('platform', props.filters.platform)
    }
  }
  if (props.filters.shop_id) {
    if (Array.isArray(props.filters.shop_id)) {
      props.filters.shop_id.forEach(s => params.append('shop_id', s))
    } else {
      params.append('shop_id', props.filters.shop_id)
    }
  }
  if (props.filters.shop_name) {
    if (Array.isArray(props.filters.shop_name)) {
      props.filters.shop_name.forEach(s => params.append('shop_name', s))
    } else {
      params.append('shop_name', props.filters.shop_name)
    }
  }

  // 添加粒度参数
  params.append('granularity', props.granularity)

  // 添加主题参数（可选）
  params.append('theme', 'transparent')
  params.append('hide_parameters', 'false')

  return `${baseUrl}/embed/dashboard/${props.dashboardId}?${params.toString()}`
})

// 获取嵌入token
const fetchEmbeddingToken = async () => {
  try {
    loading.value = true
    error.value = null

    const token = await metabaseApi.getEmbeddingToken({
      dashboard_id: props.dashboardId,
      filters: props.filters
    })

    embeddingToken.value = token
  } catch (err) {
    error.value = err.message || '获取Metabase嵌入token失败'
    console.error('获取嵌入token失败:', err)
    emit('error', err)
  } finally {
    loading.value = false
  }
}

// iframe加载完成
const onIframeLoad = () => {
  loading.value = false
  emit('loaded')
}

// iframe加载错误
const onIframeError = () => {
  loading.value = false
  error.value = '加载Metabase图表失败'
  emit('error', new Error('加载Metabase图表失败'))
}

// 重新加载
const reload = () => {
  fetchEmbeddingToken()
}

// 监听筛选器变化
watch(
  () => [props.filters, props.granularity],
  () => {
    if (embeddingToken.value) {
      // Token仍然有效，只需要更新iframe URL
      // iframe会自动重新加载
    } else {
      // 需要重新获取token
      fetchEmbeddingToken()
    }
  },
  { deep: true }
)

// 自动刷新
const startAutoRefresh = () => {
  if (props.autoRefresh && props.refreshInterval > 0) {
    refreshTimer = setInterval(() => {
      reload()
    }, props.refreshInterval * 1000)
  }
}

const stopAutoRefresh = () => {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

// 生命周期
onMounted(() => {
  fetchEmbeddingToken()
  startAutoRefresh()
})

onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<style scoped>
.metabase-chart-container {
  position: relative;
  width: 100%;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  overflow: hidden;
  background: #fff;
}

.chart-loading {
  padding: 20px;
}

.chart-error {
  padding: 20px;
  text-align: center;
}

.metabase-iframe {
  border: none;
  display: block;
}
</style>

