<template>
  <span class="shop-display-text" :class="{ 'shop-display-text--compact': compact }">
    <span class="shop-display-text__main" :title="meta.display_name">{{ meta.display_name }}</span>
    <span v-if="meta.secondary_name" class="shop-display-text__secondary">
      {{ meta.secondary_name }}
    </span>
  </span>
</template>

<script setup>
/**
 * 店铺显示名单元格 —— 全站统一显示名口径的唯一入口。
 *
 * 显示「内部编号（主名）+ 店名（副显）」，
 * 而不是把 `shop_id` / `platform_shop_id` 这种键值直接甩给用户。
 *
 * 用法：
 * ```html
 * <el-table-column label="店铺" min-width="160">
 *   <template #default="{ row }">
 *     <ShopDisplayText :row="row" />
 *   </template>
 * </el-table-column>
 * ```
 *
 * 目录加载失败时会退回显示原始键值（不会让整页挂掉）。
 */
import { computed, onMounted } from 'vue'

import { useShopDisplay } from '@/composables/useShopDisplay'

const props = defineProps({
  /** 行数据：任意带 shop_id / platform_shop_id / shop_account_id 的对象 */
  row: {
    type: Object,
    default: () => ({})
  },
  /** 紧凑模式：主名与副显同一行 */
  compact: {
    type: Boolean,
    default: false
  }
})

const { resolveShopDisplay, ensureShopDisplayLookup } = useShopDisplay()

const meta = computed(() => resolveShopDisplay(props.row || {}))

onMounted(() => {
  ensureShopDisplayLookup()
})
</script>

<style scoped>
.shop-display-text {
  display: inline-flex;
  flex-direction: column;
  line-height: 1.35;
}

.shop-display-text--compact {
  flex-direction: row;
  align-items: baseline;
  gap: 6px;
}

.shop-display-text__main {
  font-weight: 500;
}

.shop-display-text__secondary {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
