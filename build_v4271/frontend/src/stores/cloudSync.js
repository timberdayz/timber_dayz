import { defineStore } from 'pinia'
import { ElMessage } from 'element-plus'

import cloudSyncApi from '@/api/cloudSync'

function createLoadingState() {
  return {
    summary: false,
    diagnostics: false,
    events: false,
    action: false,
  }
}

function normalizeErrorMessage(error, fallback) {
  return error?.response?.data?.detail || error?.message || fallback
}

export const useCloudSyncStore = defineStore('cloudSync', {
  state: () => ({
    overview: null,
    runtime: null,
    history: [],
    settings: null,
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
    autoSyncEnabled: (state) => state.settings?.auto_sync_enabled ?? state.overview?.auto_sync_enabled ?? true,
    catchUpStatus: (state) => state.overview?.catch_up_status || 'up_to_date',
    exceptionTaskCount: (state) => state.overview?.exception_task_count || 0,
    failedTaskCount: (state) => state.overview?.failed_task_count || 0,
    partialSuccessTaskCount: (state) => state.overview?.partial_success_task_count || 0,
    pendingTaskCount: (state) => (state.overview?.pending_task_count ?? state.health?.queue?.pending ?? 0),
    runningTaskCount: (state) => (state.overview?.running_task_count ?? state.health?.queue?.running ?? 0),
    retryWaitingTaskCount: (state) => (state.overview?.retry_waiting_task_count ?? state.health?.queue?.retry_waiting ?? 0),
    workerSummaryStatus: (state) => state.overview?.worker_status || state.runtime?.worker_status || state.health?.worker?.status || 'unknown',
    lastSuccessAt: (state) => state.overview?.last_success_at || null,
    runtimeRunning: (state) => state.runtime?.is_running || false,
    selectedTableState: (state) =>
      state.tableStates.find((row) => row.source_table_name === state.selectedTableName) || null,
  },

  actions: {
    async loadOverview(showError = false) {
      this.loading.summary = true
      try {
        this.overview = await cloudSyncApi.getOverview()
        return this.overview
      } catch (error) {
        this.lastError = normalizeErrorMessage(error, '加载云端追平总览失败')
        if (showError) ElMessage.error(this.lastError)
        throw error
      } finally {
        this.loading.summary = false
      }
    },

    async loadRuntime(showError = false) {
      this.loading.summary = true
      try {
        this.runtime = await cloudSyncApi.getRuntime()
        return this.runtime
      } catch (error) {
        this.lastError = normalizeErrorMessage(error, '加载同步运行状态失败')
        if (showError) ElMessage.error(this.lastError)
        throw error
      } finally {
        this.loading.summary = false
      }
    },

    async loadHistory(params = {}, showError = false) {
      this.loading.summary = true
      try {
        this.history = await cloudSyncApi.getHistory(params)
        return this.history
      } catch (error) {
        this.lastError = normalizeErrorMessage(error, '加载同步历史失败')
        if (showError) ElMessage.error(this.lastError)
        throw error
      } finally {
        this.loading.summary = false
      }
    },

    async loadSettings(showError = false) {
      this.loading.summary = true
      try {
        this.settings = await cloudSyncApi.getSettings()
        return this.settings
      } catch (error) {
        this.lastError = normalizeErrorMessage(error, '加载自动同步设置失败')
        if (showError) ElMessage.error(this.lastError)
        throw error
      } finally {
        this.loading.summary = false
      }
    },

    async loadHealth(showError = false) {
      this.loading.summary = true
      try {
        this.health = await cloudSyncApi.getHealth()
        return this.health
      } catch (error) {
        this.lastError = normalizeErrorMessage(error, '加载同步健康状态失败')
        if (showError) ElMessage.error(this.lastError)
        throw error
      } finally {
        this.loading.summary = false
      }
    },

    async loadTableStates(params = {}, showError = false) {
      this.loading.diagnostics = true
      try {
        this.tableStates = await cloudSyncApi.getTables(params)
        return this.tableStates
      } catch (error) {
        this.lastError = normalizeErrorMessage(error, '加载高级诊断表状态失败')
        if (showError) ElMessage.error(this.lastError)
        throw error
      } finally {
        this.loading.diagnostics = false
      }
    },

    async loadTasks(params = {}, showError = false) {
      this.loading.diagnostics = true
      try {
        const mergedParams = { ...this.taskFilters, ...params }
        this.tasks = await cloudSyncApi.getTasks(mergedParams)
        return this.tasks
      } catch (error) {
        this.lastError = normalizeErrorMessage(error, '加载高级诊断任务失败')
        if (showError) ElMessage.error(this.lastError)
        throw error
      } finally {
        this.loading.diagnostics = false
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
        this.lastError = normalizeErrorMessage(error, '加载同步事件失败')
        if (showError) ElMessage.error(this.lastError)
        throw error
      } finally {
        this.loading.events = false
      }
    },

    async refreshDashboard(options = {}) {
      const {
        includeEvents = false,
        includeDiagnostics = true,
        showError = false,
        tableParams = {},
        taskParams = {},
        eventParams = {},
      } = options

      const jobs = [
        this.loadOverview(showError),
        this.loadRuntime(showError),
        this.loadHistory({}, showError),
        this.loadSettings(showError),
        this.loadHealth(showError),
      ]

      if (includeDiagnostics) {
        jobs.push(this.loadTableStates(tableParams, showError))
        jobs.push(this.loadTasks(taskParams, showError))
      }

      if (includeEvents) {
        jobs.push(this.loadEvents(eventParams, showError))
      }

      return await Promise.all(jobs)
    },

    async syncNow() {
      return await this.runAction(() => cloudSyncApi.syncNow(), '已提交追平到最新任务')
    },

    async toggleAutoSync(enabled) {
      return await this.runAction(
        () => cloudSyncApi.updateSettings({ auto_sync_enabled: enabled }),
        enabled ? '已开启自动同步' : '已暂停自动同步',
      )
    },

    async retryFailed() {
      return await this.runAction(() => cloudSyncApi.retryFailed(), '已提交异常任务重试')
    },

    async retryTask(jobId) {
      return await this.runAction(() => cloudSyncApi.retryTask(jobId), '已提交任务重试')
    },

    async cancelTask(jobId) {
      return await this.runAction(() => cloudSyncApi.cancelTask(jobId), '已取消任务')
    },

    async dryRunTable(tableName, payload = {}) {
      return await this.runAction(() => cloudSyncApi.dryRunTable(tableName, payload), '已提交模拟执行')
    },

    async repairCheckpoint(tableName, payload = {}) {
      return await this.runAction(() => cloudSyncApi.repairCheckpoint(tableName, payload), '已提交同步点修复')
    },

    async refreshProjection(tableName, payload = {}) {
      return await this.runAction(() => cloudSyncApi.refreshProjection(tableName, payload), '已提交投影刷新')
    },

    async runAction(action, successMessage) {
      this.loading.action = true
      try {
        const result = await action()
        this.lastActionResult = result
        if (result?.metadata?.auto_sync_enabled !== undefined) {
          this.settings = {
            ...(this.settings || {}),
            ...result.metadata,
          }
        }
        if (successMessage) {
          ElMessage.success(successMessage)
        }
        await Promise.allSettled([
          this.loadOverview(false),
          this.loadRuntime(false),
          this.loadHistory({}, false),
          this.loadSettings(false),
          this.loadHealth(false),
          this.loadTableStates({}, false),
          this.loadTasks({}, false),
        ])
        return result
      } catch (error) {
        this.lastError = normalizeErrorMessage(error, '执行云端追平操作失败')
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
  },
})
