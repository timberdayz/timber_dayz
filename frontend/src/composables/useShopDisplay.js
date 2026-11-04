/**
 * 店铺显示名 —— 全站共用的加载与解析入口。
 *
 * 为什么做成 composable 而不是每个页面各写一遍
 * ----------------------------------------
 * 页面有二十多个，如果每个页面自己写一遍「取目录 → 建 lookup → 解析」，
 * 就会出现三种不同的实现、三种不同的兜底行为。现在统一走这里：
 *
 * - **目录只请求一次**：模块级缓存 promise，多个页面共用同一个请求；
 * - **加载失败不拖垮页面**：catch 住，lookup 置空 ⇒ 退回显示原始键值，
 *   而不是让整页报错；
 * - **口径只有一份**：解析规则在 ``@/utils/shopDisplay`` 里。
 *
 * 用法：
 * ```js
 * const { shopDisplayLookup, ensureShopDisplayLookup, resolveShopDisplay } = useShopDisplay()
 * onMounted(() => { ensureShopDisplayLookup() })
 * // 模板里：{{ resolveShopDisplay(row).display_name }}
 * ```
 */
import { ref } from 'vue'

import api from '@/api'
import { buildShopAccountLookup, resolveShopDisplay } from '@/utils/shopDisplay'

// 模块级状态：整个应用共享一份目录
const shopDisplayLookup = ref(new Map())
let directoryPromise = null

function normalizeResponse(response) {
  if (Array.isArray(response)) return response
  if (Array.isArray(response?.data)) return response.data
  if (Array.isArray(response?.data?.items)) return response.data.items
  return []
}

async function ensureShopDisplayLookup() {
  if (!directoryPromise) {
    directoryPromise = api
      .getShopDirectory({ enabled: true })
      .then((response) => {
        shopDisplayLookup.value = buildShopAccountLookup(normalizeResponse(response))
        return shopDisplayLookup.value
      })
      .catch((error) => {
        // 目录拿不到就退回显示原始键值 —— 不能因为「显示名加载失败」让整页挂掉
        console.warn('[shopDisplay] 店铺目录加载失败，暂用原始键值显示', error)
        shopDisplayLookup.value = new Map()
        return shopDisplayLookup.value
      })
  }
  return directoryPromise
}

export function useShopDisplay() {
  return {
    shopDisplayLookup,
    ensureShopDisplayLookup,
    resolveShopDisplay: (entity) => resolveShopDisplay(entity || {}, shopDisplayLookup.value),
    shopDisplayName: (entity) =>
      resolveShopDisplay(entity || {}, shopDisplayLookup.value).display_name,
    shopDisplaySecondaryName: (entity) =>
      resolveShopDisplay(entity || {}, shopDisplayLookup.value).secondary_name
  }
}
