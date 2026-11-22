<template>
  <!--
    字段口径说明小问号。

    为什么要有这个组件：同一段口径说明（"这个数怎么算的""为什么这么贵""人工维护还是实测"）
    写在表格的行模板里，会在**每一行**重复一遍 —— 十行就是十遍，表格被撑到没法看。
    口径说明是**列级/字段级**的，天然只该说一次 ⇒ 收进表头的小问号，悬浮即看。

    交互对齐「业务概览」的 KPI 小问号（el-popover + hover）：
      * 桌面端悬停触发，移动端点击触发（Element Plus popover 两种都支持）
      * 键盘可达：按钮 + Enter / Space
      * 内容分区展示：指标含义 / 计算口径 / 业务作用 / 口径状态

    ⚠️ 样式用**非 scoped** 块：el-popover 默认 teleport 到 body，
       scoped 里的 :deep() 选择器匹配不到弹层根节点 ⇒ 边框/阴影会失效。
       所以这里用 pc- 前缀的全局类名规避（也不会和别的页面撞名）。
  -->
  <el-popover
    :width="340"
    trigger="hover"
    placement="top"
    popper-class="pc-field-help-popover"
  >
    <template #reference>
      <button
        type="button"
        class="pc-field-help-trigger"
        :aria-label="`查看${title}说明`"
        @click.stop
        @keydown.enter.prevent
        @keydown.space.prevent
      >
        <el-icon class="pc-field-help-icon"><QuestionFilled /></el-icon>
      </button>
    </template>
    <div class="pc-field-help-panel">
      <div class="pc-field-help-header">
        <span class="pc-field-help-title">{{ title }}</span>
        <el-tag
          v-if="statusText"
          size="small"
          effect="plain"
          class="pc-field-help-status"
          :type="statusTagType"
        >
          {{ statusText }}
        </el-tag>
      </div>
      <div v-for="item in visibleSections" :key="item.label" class="pc-field-help-row">
        <div class="pc-field-help-label">{{ item.label }}</div>
        <div class="pc-field-help-text">{{ item.text }}</div>
      </div>
    </div>
  </el-popover>
</template>

<script setup>
import { computed } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'

const props = defineProps({
  /** 面板标题，一般就是字段名 */
  title: { type: String, required: true },
  /** 口径状态：stable / observe / manual / blocked；空则不显示状态标签 */
  status: { type: String, default: '' },
  /** 分区说明 [{ label, text }]；给了它就优先用它 */
  sections: { type: Array, default: () => [] },
  /** 简单一段说明（适合行内、随行变化的动态文案） */
  content: { type: String, default: '' }
})

const STATUS_TEXT = {
  stable: '稳定口径',
  observe: '观察口径',
  manual: '人工维护',
  blocked: '谨慎使用'
}

const STATUS_TAG_TYPE = {
  stable: 'success',
  observe: 'warning',
  manual: 'warning',
  blocked: 'danger'
}

const statusText = computed(() => STATUS_TEXT[props.status] || '')
const statusTagType = computed(() => STATUS_TAG_TYPE[props.status] || 'info')

const visibleSections = computed(() => {
  const list = (props.sections || []).filter((item) => item && item.text)
  if (list.length) return list
  if (props.content) return [{ label: '说明', text: props.content }]
  return []
})
</script>

<style>
/* ⚠️ 非 scoped：弹层被 teleport 到 body，scoped 的 :deep() 匹配不到。 */
.pc-field-help-popover.el-popover {
  padding: 14px 16px;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 12px;
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.16);
}

.pc-field-help-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: none;
  background: transparent;
  cursor: help;
  color: inherit;
  vertical-align: middle;
}

.pc-field-help-trigger:focus-visible {
  outline: 2px solid rgba(37, 99, 235, 0.35);
  outline-offset: 2px;
  border-radius: 6px;
}

.pc-field-help-icon {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  transition: color 0.2s ease;
}

.pc-field-help-trigger:hover .pc-field-help-icon,
.pc-field-help-trigger:focus-visible .pc-field-help-icon {
  color: var(--el-color-primary);
}

.pc-field-help-panel {
  color: #334155;
}

.pc-field-help-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.pc-field-help-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.pc-field-help-row + .pc-field-help-row {
  margin-top: 8px;
}

.pc-field-help-label {
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  margin-bottom: 2px;
}

.pc-field-help-text {
  font-size: 12px;
  line-height: 1.6;
  color: #475569;
  white-space: pre-wrap;
}
</style>
