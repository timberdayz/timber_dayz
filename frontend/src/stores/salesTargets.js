import { defineStore } from 'pinia'
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

import salesTargetsApi from '@/api/salesTargets.js'
import { buildSalesTargetMutationPayload, normalizeSalesTargetsResponse } from '@/utils/pageStandards.js'

export const useSalesTargetsStore = defineStore('salesTargets', () => {
  const shops = ref([])
  const targets = ref([])
  const isLoading = ref(false)
  const isSubmitting = ref(false)

  async function fetchShops() {
    try {
      const response = await salesTargetsApi.getShops()
      shops.value = Array.isArray(response) ? response : (response?.data || [])
      return shops.value
    } catch (error) {
      ElMessage.error(`加载店铺列表失败: ${error.response?.data?.detail || error.message}`)
      throw error
    }
  }

  async function fetchTargets(params = {}, showLoading = true) {
    if (showLoading) {
      isLoading.value = true
    }

    try {
      const response = await salesTargetsApi.getList(params)
      targets.value = normalizeSalesTargetsResponse(response)
      return targets.value
    } catch (error) {
      ElMessage.error(`加载销售目标失败: ${error.response?.data?.detail || error.message}`)
      throw error
    } finally {
      if (showLoading) {
        isLoading.value = false
      }
    }
  }

  async function createTarget(form) {
    isSubmitting.value = true
    try {
      const payload = {
        shop_id: form.shop_id,
        year_month: form.year_month,
        ...buildSalesTargetMutationPayload(form),
      }
      const response = await salesTargetsApi.create(payload)
      ElMessage.success('创建销售目标成功')
      return response?.data ?? response
    } catch (error) {
      ElMessage.error(`创建销售目标失败: ${error.response?.data?.detail || error.message}`)
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  async function updateTarget(id, form) {
    isSubmitting.value = true
    try {
      const response = await salesTargetsApi.update(id, buildSalesTargetMutationPayload(form))
      ElMessage.success('更新销售目标成功')
      return response?.data ?? response
    } catch (error) {
      ElMessage.error(`更新销售目标失败: ${error.response?.data?.detail || error.message}`)
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  async function deleteTarget(id) {
    isSubmitting.value = true
    try {
      await salesTargetsApi.remove(id)
      targets.value = targets.value.filter((item) => item.id !== id)
      ElMessage.success('删除销售目标成功')
    } catch (error) {
      ElMessage.error(`删除销售目标失败: ${error.response?.data?.detail || error.message}`)
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  return {
    shops,
    targets,
    isLoading,
    isSubmitting,
    fetchShops,
    fetchTargets,
    createTarget,
    updateTarget,
    deleteTarget,
  }
})
