<template>
  <el-card class="alias-arbitration" style="margin-bottom: 20px;">
    <template #header>
      <div class="alias-arbitration__header">
        <span>别名裁决</span>
        <el-button size="small" :loading="loading" @click="loadConflicts">
          <el-icon><Refresh /></el-icon>
          刷新冲突
        </el-button>
      </div>
    </template>

    <el-alert
      v-if="loadError"
      type="error"
      show-icon
      :closable="false"
      class="alias-arbitration__alert"
      title="别名冲突加载失败"
      :description="`${loadError}。下面的列表不是最新的冲突，请点击「刷新冲突」重试。`"
    />

    <template v-else>
      <el-alert
        v-if="!conflicts.length"
        type="success"
        show-icon
        :closable="false"
        class="alias-arbitration__alert"
        title="没有待裁决的别名冲突"
        description="同一个列名没有被对齐到两个不同的标准字段。"
      />

      <el-alert
        v-else
        type="warning"
        show-icon
        :closable="false"
        class="alias-arbitration__alert"
        :title="`有 ${conflicts.length} 个列名撞了不同含义，需要人来裁决`"
        description="在裁决之前，这些别名不进推断链路 —— 系统不会替您猜一个。"
      />

      <el-table v-if="conflicts.length" :data="conflicts" stripe border max-height="420">
        <el-table-column prop="data_domain" label="数据域" width="110">
          <template #default="{ row }">
            {{ row.data_domain === '*' ? '不限域' : row.data_domain }}
          </template>
        </el-table-column>
        <el-table-column prop="raw_alias" label="列名" min-width="140" />
        <el-table-column label="当前生效" min-width="160">
          <template #default="{ row }">
            <el-tag type="info" size="small">{{ semanticLabel(row.active_semantic_key) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="新断言" min-width="160">
          <template #default="{ row }">
            <el-tag type="warning" size="small">{{ semanticLabel(row.conflicting_semantic_key) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="裁决" min-width="280">
          <template #default="{ row }">
            <div class="alias-arbitration__actions">
              <el-button
                size="small"
                type="primary"
                :loading="resolvingKey === actionKey(row, 'accept')"
                @click="resolve(row, 'accept', row.conflicting_semantic_key)"
              >
                用「{{ semanticLabel(row.conflicting_semantic_key) }}」
              </el-button>
              <el-button
                size="small"
                :loading="resolvingKey === actionKey(row, 'reject')"
                @click="resolve(row, 'reject', row.active_semantic_key)"
              >
                维持当前
              </el-button>
              <el-button
                size="small"
                :loading="resolvingKey === actionKey(row, 'disable')"
                @click="resolve(row, 'disable', row.active_semantic_key)"
              >
                停用
              </el-button>
            </div>
            <div class="alias-arbitration__custom">
              <el-select
                v-model="customSelections[row.raw_alias]"
                size="small"
                clearable
                placeholder="改判为其它标准字段"
                style="width: 220px;"
              >
                <el-option
                  v-for="option in semanticOptions"
                  :key="option.value"
                  :label="option.label"
                  :value="option.value"
                />
              </el-select>
              <el-button
                size="small"
                text
                type="primary"
                :disabled="!customSelections[row.raw_alias]"
                @click="resolve(row, 'accept', customSelections[row.raw_alias])"
              >
                改判
              </el-button>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </el-card>
</template>

<script setup>
/**
 * 别名裁决面板(批次 D · API-5)。
 *
 * 背景
 * ----
 * 同一个列名被对齐到**两个**标准字段时, 系统**不静默覆盖**:
 * 原记录保持不动, 另写一条 `status='conflict'` 的候选记录, 并在这里列出来。
 *
 * 为什么必须由人裁决
 * ------------------
 * 「销售额」在 orders 域是 `sales_amount`, 在别的域可能是别的含义;
 * 系统替用户猜一个 ⇒ 一旦猜错, 所有引用该别名的模板都会跟着错。
 * 与其猜, 不如停在「待裁决」, 让人一句话定下来。
 *
 * 裁决之后
 * --------
 * 别名立即进推断索引(后端会刷新运行时索引), 其它模板自动命中 ——
 * 这就是「对齐一次, 处处生效」。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

import api from '@/api'
import { getSemanticFieldOptionGroupsForDomain } from '@/domains/data_platform/utils/headerBindings'
import { loadSemanticFieldRegistry } from '@/domains/data_platform/utils/semanticFieldRegistryApi'

const loading = ref(false)
const loadError = ref('')
const conflicts = ref([])
const resolvingKey = ref('')
const customSelections = reactive({})

const semanticOptions = computed(() =>
  getSemanticFieldOptionGroupsForDomain('').flatMap(group =>
    (group.options || []).map(option => ({
      value: option.value,
      label: option.label,
    }))
  )
)

function semanticLabel(semanticKey) {
  const key = String(semanticKey || '').trim()
  if (!key) return '(未指定)'
  const option = semanticOptions.value.find(item => item.value === key)
  return option ? option.label : key
}

function actionKey(row, action) {
  return `${row.data_domain}|${row.raw_alias}|${action}`
}

async function loadConflicts() {
  loading.value = true
  loadError.value = ''
  try {
    const payload = await api.getSemanticFieldAliasConflicts()
    conflicts.value = Array.isArray(payload?.conflicts) ? payload.conflicts : []
  } catch (error) {
    loadError.value = error?.message || '未知错误'
    conflicts.value = []
  } finally {
    loading.value = false
  }
}

async function resolve(row, action, semanticKey) {
  const key = actionKey(row, action)
  resolvingKey.value = key
  try {
    const payload = await api.resolveSemanticFieldAlias({
      data_domain: row.data_domain,
      raw_alias: row.raw_alias,
      platform_code: row.platform_code || null,
      granularity: row.granularity || null,
      semantic_key: semanticKey || row.active_semantic_key,
      action,
    })
    ElMessage.success(payload?.message || '裁决完成')
    delete customSelections[row.raw_alias]
    await loadConflicts()
    // 裁决结果立刻进推断索引 —— 不用等刷新页面。
    await loadSemanticFieldRegistry({ force: true })
  } catch (error) {
    ElMessage.error(error?.message || '裁决失败')
  } finally {
    resolvingKey.value = ''
  }
}

onMounted(loadConflicts)
</script>

<style scoped>
.alias-arbitration__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.alias-arbitration__alert {
  margin-bottom: 12px;
}

.alias-arbitration__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.alias-arbitration__custom {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}
</style>
