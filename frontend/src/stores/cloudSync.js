import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import cloudSyncApi from '@/api/cloudSync'

function createLoadingState() {
  return {
    health: false,
    tables: false,
    tasks: false,
    events: false,
    action: false,
  }
}

function normalizeErrorMessage(error, fallback) {
  return error?.response?.data?.detail || error?.message || fallback
}

export const useCloudSyncStore = defineStore('cloudSync', {
  state: () => ({
    health: null,
    tableStates: [],
    tasks: [],
    events: [],
    selectedTableName: '',
    taskFilters: {
      status: '',
      source_table_name: '',
    },
    loading: createLoadingState(),
    lastError: null,
    lastActionResult: null,
  }),

  getters: {
    pendingTaskCount: (state) => state.health?.queue?.pending || 0,
    runningTaskCount: (state) => state.health?.queue?.running || 0,
    retryWaitingTaskCount: (state) => state.health?.queue?.retry_waiting || 0,
    failedTaskCount: (state) => state.health?.queue?.failed || 0,
    workerStatus: (state) => state.health?.worker?.status || 'unknown',
    selectedTableState: (state) =>
      state.tableStates.find((row) => row.source_table_name === state.selectedTableName) || null,
  },

  actions: {
    async loadHealth(showError = false) {
      this.loading.health = true
      try {
        this.health = await cloudSyncApi.getHealth()
        return this.health
      } catch (error) {
        this.lastError = normalizeErrorMessage(error, '加载云端同步健康状态失败')
        if (showError) {
          ElMessage.error(this.lastError)
        }
        throw error
      } finally {
        this.loading.health = false
      }
    },

    async loadTableStates(params = {}, showError = false) {
      this.loading.tables = true
      try {
        this.tableStates = await cloudSyncApi.getTables(params)
        return this.tableStates
      } catch (error) {
        this.lastError = normalizeErrorMessage(error, '加载云端同步表状态失败')
        if (showError) {
          ElMessage.error(this.lastError)
        }
        throw error
      } finally {
        this.loading.tables = false
      }
    },

    async loadTasks(params = {}, showError = false) {
      this.loading.tasks = true
      try {
        const mergedParams = { ...this.taskFilters, ...params }
        this.tasks = await cloudSyncApi.getTasks(mergedParams)
        return this.tasks
      } catch (error) {
        this.lastError = normalizeErrorMessage(error, '加载云端同步任务失败')
        if (showError) {
          ElMessage.error(this.lastError)
        }
        throw error
      } finally {
        this.loading.tasks = false
      }
    },

    async loadEvents(params = {}, showError = false) {
      this.loading.events = true
      try {
        this.events = await cloudSyncApi.getEvents(params)
        return this.events
      } catch (error) {
        if (error?.response?.status === 404) {
          this.events = []
          return this.events
        }
        this.lastError = normalizeErrorMessage(error, '加载云端同步事件失败')
        if (showError) {
          ElMessage.error(this.lastError)
        }
        throw error
      } finally {
        this.loading.events = false
      }
    },

    async refreshDashboard(options = {}) {
      const {
        includeEvents = false,
        showError = false,
        tableParams = {},
        taskParams = {},
        eventParams = {},
      } = options

      const jobs = [
        this.loadHealth(showError),
        this.loadTableStates(tableParams, showError),
        this.loadTasks(taskParams, showError),
      ]

      if (includeEvents) {
        jobs.push(this.loadEvents(eventParams, showError))
      }

      return await Promise.all(jobs)
    },

    async triggerSync(sourceTableName) {
      return await this.runAction(
        () => cloudSyncApi.triggerSync({ source_table_name: sourceTableName }),
        '手动触发同步成功',
      )
    },

    async retryTask(jobId) {
      return await this.runAction(
        () => cloudSyncApi.retryTask(jobId),
        '任务重试已提交',
      )
    },

    async cancelTask(jobId) {
      return await this.runAction(
        () => cloudSyncApi.cancelTask(jobId),
        '任务已取消',
      )
    },

    async dryRunTable(tableName, payload = {}) {
      return await this.runAction(
        () => cloudSyncApi.dryRunTable(tableName, payload),
        'Dry-run 已提交',
      )
    },

    async repairCheckpoint(tableName, payload = {}) {
      return await this.runAction(
        () => cloudSyncApi.repairCheckpoint(tableName, payload),
        'Checkpoint 修复已提交',
      )
    },

    async refreshProjection(tableName, payload = {}) {
      return await this.runAction(
        () => cloudSyncApi.refreshProjection(tableName, payload),
        'Projection 刷新已提交',
      )
    },

    async runAction(action, successMessage) {
      this.loading.action = true
      try {
        const result = await action()
        this.lastActionResult = result
        if (successMessage) {
          ElMessage.success(successMessage)
        }
        await Promise.allSettled([
          this.loadHealth(false),
          this.loadTableStates({}, false),
          this.loadTasks({}, false),
        ])
        return result
      } catch (error) {
        this.lastError = normalizeErrorMessage(error, '执行云端同步操作失败')
        ElMessage.error(this.lastError)
        throw error
      } finally {
        this.loading.action = false
      }
    },

    setSelectedTableName(tableName) {
      this.selectedTableName = tableName || ''
    },

    setTaskFilters(filters) {
      this.taskFilters = { ...this.taskFilters, ...filters }
    },

    clearTaskFilters() {
      this.taskFilters = {
        status: '',
        source_table_name: '',
      }
    },
  },
})
