<template>
  <section class="erp-page-header" :class="[familyClass, { 'erp-page-header--compact': compact }]">
    <div class="erp-page-header__main">
      <div class="erp-page-header__title-row">
        <el-icon v-if="icon" class="erp-page-header__icon">
          <component :is="icon" />
        </el-icon>
        <h1 class="erp-page-header__title">{{ title }}</h1>
      </div>
      <p v-if="subtitle" class="erp-page-header__subtitle">{{ subtitle }}</p>
    </div>

    <div v-if="$slots.actions" class="erp-page-header__actions">
      <slot name="actions" />
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

import { getPageFamilyClass } from '@/utils/pageStandards.js'

const props = defineProps({
  title: {
    type: String,
    required: true
  },
  subtitle: {
    type: String,
    default: ''
  },
  icon: {
    type: Object,
    default: null
  },
  family: {
    type: String,
    default: 'admin'
  },
  compact: {
    type: Boolean,
    default: false
  }
})

const familyClass = computed(() => getPageFamilyClass(props.family))
</script>

<style scoped>
.erp-page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-lg);
  padding: var(--spacing-lg) var(--spacing-xl);
  border: 1px solid var(--border-color);
  border-radius: var(--border-radius-lg);
  background: var(--white);
  box-shadow: var(--shadow-sm);
}

.erp-page-header__main {
  min-width: 0;
}

.erp-page-header__title-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.erp-page-header__icon {
  font-size: var(--font-size-xl);
  color: var(--secondary-color);
}

.erp-page-header__title {
  margin: 0;
  font-size: var(--font-size-2xl);
  font-weight: var(--font-weight-semibold);
  color: var(--text-primary);
}

.erp-page-header__subtitle {
  margin: var(--spacing-xs) 0 0 0;
  font-size: var(--font-size-sm);
  line-height: 1.6;
  color: var(--text-secondary);
}

.erp-page-header__actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  justify-content: flex-end;
}

/*
 * 紧凑档（2026-11-28）：录入型/台账型页面用。
 * 默认档的页头块高约 120px，在「一屏看更多行」的场景里占比过高。
 * 紧凑档把内边距与标题字号各收一档，其余（结构、样式变量、栅格）完全一致。
 */
.erp-page-header--compact {
  margin-bottom: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-base);
}

.erp-page-header--compact .erp-page-header__title {
  font-size: var(--font-size-xl);
}

.erp-page-header--compact .erp-page-header__subtitle {
  margin-top: 2px;
  font-size: var(--font-size-xs);
  line-height: 1.5;
}

.erp-page--dashboard {
  background: linear-gradient(180deg, rgba(52, 152, 219, 0.08) 0%, rgba(255, 255, 255, 0.98) 100%);
}

.erp-page--admin {
  background: linear-gradient(180deg, rgba(44, 62, 80, 0.04) 0%, rgba(255, 255, 255, 0.98) 100%);
}

@media (max-width: 768px) {
  .erp-page-header {
    flex-direction: column;
    padding: var(--spacing-base);
  }

  .erp-page-header__actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
