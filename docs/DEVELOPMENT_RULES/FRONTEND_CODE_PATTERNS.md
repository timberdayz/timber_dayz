# Frontend Code Patterns

**Version**: v4.20.0
**Stack**: Vue 3 (Composition API) + Element Plus + Pinia + Vite

> This document is the frontend equivalent of `CODE_PATTERNS.md`. All new frontend pages and components MUST follow these templates.

---

## Mandatory Rules (enforced in `.cursorrules`)

1. **No direct axios calls in Vue components.** All HTTP requests must go through `frontend/src/api/*.js`.
2. **State may only be modified via Pinia `actions` or `$patch()`.** Never mutate store state directly in components.
3. **List pages must use the unified pagination/query pattern** defined in Template 3.
4. **New pages must follow these templates.** Existing pages should migrate on modification.

---

## Template 1: API Function (`frontend/src/api/`)

```javascript
/**
 * [Domain] API
 *
 * Naming convention: get{Entity}, create{Entity}, update{Entity}, delete{Entity}
 * GET: use params object
 * POST/PUT/PATCH/DELETE: use data object
 * Error handling: delegated to the response interceptor in index.js
 */
import api from './index.js'

export default {
  /**
   * Get paginated list
   * @param {Object} params - Query parameters: { page, page_size, ...filters }
   * @returns {Promise<{data: Array, pagination: {total, page, page_size}}>}
   */
  async getList(params = {}) {
    return await api._get('/domain/', { params })
  },

  /**
   * Get single entity
   * @param {number|string} id
   * @returns {Promise<{data: Object}>}
   */
  async getById(id) {
    return await api._get(`/domain/${id}`)
  },

  /**
   * Create entity
   * @param {Object} payload
   * @returns {Promise<{data: Object}>}
   */
  async create(payload) {
    return await api._post('/domain/', payload)
  },

  /**
   * Update entity (full replace)
   * @param {number|string} id
   * @param {Object} payload
   */
  async update(id, payload) {
    return await api._put(`/domain/${id}`, payload)
  },

  /**
   * Partial update
   * @param {number|string} id
   * @param {Object} patch
   */
  async patch(id, patch) {
    return await api._patch(`/domain/${id}`, patch)
  },

  /**
   * Delete entity
   * @param {number|string} id
   */
  async remove(id) {
    return await api._delete(`/domain/${id}`)
  }
}
```

**Key constraints:**
- Always import from `./index.js` — never `import axios from 'axios'`
- Return the raw API response; let the store or component unwrap `.data`
- Do NOT use `ElMessage` in API layer — error feedback belongs in the store or component

---

## Template 2: Pinia Store (`frontend/src/stores/`)

```javascript
/**
 * [Domain] Store
 *
 * Pattern: Composition API style (defineStore with setup function)
 * Loading state: one isLoading per async boundary
 * Error handling: catch in action, display via ElMessage, re-throw for callers
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import domainApi from '@/api/domain'
import { ElMessage } from 'element-plus'

export const useDomainStore = defineStore('domain', () => {
  // --- State ---
  const list = ref([])
  const current = ref(null)
  const total = ref(0)
  const isLoading = ref(false)
  const isSubmitting = ref(false)

  // --- Getters ---
  const hasItems = computed(() => list.value.length > 0)
  const isEmpty = computed(() => !isLoading.value && list.value.length === 0)

  // --- Actions ---

  /**
   * Fetch paginated list.
   * @param {Object} params - { page, page_size, ...filters }
   * @param {boolean} [showLoading=true] - Pass false for background silent refresh.
   */
  async function fetchList(params = {}, showLoading = true) {
    if (showLoading) isLoading.value = true
    try {
      const response = await domainApi.getList(params)
      const items = Array.isArray(response) ? response : (response.data ?? [])
      list.value = items
      total.value = response.pagination?.total ?? response.total ?? items.length
      return items
    } catch (error) {
      ElMessage.error('Failed to load list: ' + (error.response?.data?.detail ?? error.message))
      throw error
    } finally {
      if (showLoading) isLoading.value = false
    }
  }

  /**
   * Fetch single entity.
   * @param {number|string} id
   */
  async function fetchById(id) {
    isLoading.value = true
    try {
      const response = await domainApi.getById(id)
      current.value = response.data ?? response
      return current.value
    } catch (error) {
      ElMessage.error('Failed to load record: ' + (error.response?.data?.detail ?? error.message))
      throw error
    } finally {
      isLoading.value = false
    }
  }

  /**
   * Create entity.
   * @param {Object} payload
   */
  async function create(payload) {
    isSubmitting.value = true
    try {
      const response = await domainApi.create(payload)
      ElMessage.success('Created successfully')
      return response.data ?? response
    } catch (error) {
      ElMessage.error('Create failed: ' + (error.response?.data?.detail ?? error.message))
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  /**
   * Update entity.
   * @param {number|string} id
   * @param {Object} payload
   */
  async function update(id, payload) {
    isSubmitting.value = true
    try {
      const response = await domainApi.update(id, payload)
      ElMessage.success('Updated successfully')
      return response.data ?? response
    } catch (error) {
      ElMessage.error('Update failed: ' + (error.response?.data?.detail ?? error.message))
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  /**
   * Delete entity.
   * @param {number|string} id
   */
  async function remove(id) {
    isSubmitting.value = true
    try {
      await domainApi.remove(id)
      ElMessage.success('Deleted successfully')
      list.value = list.value.filter(item => item.id !== id)
    } catch (error) {
      ElMessage.error('Delete failed: ' + (error.response?.data?.detail ?? error.message))
      throw error
    } finally {
      isSubmitting.value = false
    }
  }

  return {
    // state
    list, current, total, isLoading, isSubmitting,
    // getters
    hasItems, isEmpty,
    // actions
    fetchList, fetchById, create, update, remove
  }
})
```

**Key constraints:**
- Separate `isLoading` (read) from `isSubmitting` (write) for independent UX control
- Always use `showLoading = false` for background/silent refresh
- `ElMessage` belongs in the store, not in the API layer
- Do NOT expose raw `ref` mutations — only expose actions and readonly state

---

## Template 3: List Page (`frontend/src/views/`)

```vue
<template>
  <div class="page-container">
    <!-- Toolbar: filter + search + action buttons -->
    <div class="toolbar">
      <el-form :inline="true" :model="query" @submit.prevent="handleSearch">
        <el-form-item label="Keyword">
          <el-input v-model="query.keyword" placeholder="Search..." clearable />
        </el-form-item>
        <el-form-item label="Status">
          <el-select v-model="query.status" placeholder="All" clearable>
            <el-option label="Active" value="active" />
            <el-option label="Inactive" value="inactive" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" native-type="submit" :loading="store.isLoading">
            Search
          </el-button>
          <el-button @click="handleReset">Reset</el-button>
        </el-form-item>
      </el-form>

      <!-- Permission-gated action buttons (see Template 5) -->
      <div class="actions" v-if="hasPermission('domain.write')">
        <el-button type="primary" @click="handleCreate">+ Create</el-button>
      </div>
    </div>

    <!-- Table with partial loading (not full-page spinner) -->
    <el-table
      v-loading="store.isLoading"
      :data="store.list"
      border
      stripe
    >
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="Name" />
      <el-table-column prop="status" label="Status" width="100" />
      <el-table-column label="Actions" width="180" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="handleEdit(row)">Edit</el-button>
          <el-button
            size="small"
            type="danger"
            v-if="hasPermission('domain.delete')"
            @click="handleDelete(row.id)"
          >
            Delete
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- Pagination -->
    <div class="pagination-container">
      <el-pagination
        v-model:current-page="pagination.page"
        v-model:page-size="pagination.pageSize"
        :total="store.total"
        :page-sizes="[10, 20, 50]"
        layout="total, sizes, prev, pager, next"
        @size-change="handlePageChange"
        @current-change="handlePageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessageBox } from 'element-plus'
import { useDomainStore } from '@/stores/domain'
import { hasPermission } from '@/utils/auth'

const store = useDomainStore()

// Query state (do NOT put query state in the store — it's local to this page)
const query = reactive({
  keyword: '',
  status: ''
})

const pagination = reactive({
  page: 1,
  pageSize: 20
})

// Load data on mount
onMounted(() => fetchData())

function buildParams() {
  return {
    page: pagination.page,
    page_size: pagination.pageSize,
    ...(query.keyword && { keyword: query.keyword }),
    ...(query.status && { status: query.status })
  }
}

async function fetchData(showLoading = true) {
  await store.fetchList(buildParams(), showLoading)
}

function handleSearch() {
  pagination.page = 1
  fetchData()
}

function handleReset() {
  query.keyword = ''
  query.status = ''
  pagination.page = 1
  fetchData()
}

function handlePageChange() {
  fetchData()
}

function handleCreate() {
  // navigate to form or open dialog
}

function handleEdit(row) {
  // navigate to form or open dialog
}

async function handleDelete(id) {
  try {
    await ElMessageBox.confirm('Confirm delete?', 'Warning', { type: 'warning' })
    await store.remove(id)
    fetchData(false)  // silent refresh after delete
  } catch {
    // user cancelled — no action needed
  }
}
</script>
```

**Key constraints:**
- Query state (filters, pagination) lives in the component, NOT in the store
- Use `v-loading` on the table, never a full-page loading mask
- After write operations, refresh with `showLoading = false` (silent refresh)

---

## Template 4: Form Page (`frontend/src/views/`)

```vue
<template>
  <div class="form-page">
    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-width="120px"
      v-loading="isPageLoading"
    >
      <el-form-item label="Name" prop="name">
        <el-input v-model="form.name" placeholder="Enter name" />
      </el-form-item>

      <el-form-item label="Status" prop="status">
        <el-select v-model="form.status">
          <el-option label="Active" value="active" />
          <el-option label="Inactive" value="inactive" />
        </el-select>
      </el-form-item>

      <el-form-item>
        <el-button
          type="primary"
          :loading="store.isSubmitting"
          @click="handleSubmit"
        >
          {{ isEditMode ? 'Update' : 'Create' }}
        </el-button>
        <el-button @click="handleCancel">Cancel</el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDomainStore } from '@/stores/domain'

const props = defineProps({
  id: { type: [Number, String], default: null }
})

const route = useRoute()
const router = useRouter()
const store = useDomainStore()
const formRef = ref(null)
const isPageLoading = ref(false)

const entityId = computed(() => props.id ?? route.params.id ?? null)
const isEditMode = computed(() => !!entityId.value)

const form = reactive({
  name: '',
  status: 'active'
})

const rules = {
  name: [
    { required: true, message: 'Name is required', trigger: 'blur' },
    { min: 2, max: 50, message: 'Length must be 2-50 characters', trigger: 'blur' }
  ],
  status: [{ required: true, message: 'Status is required', trigger: 'change' }]
}

onMounted(async () => {
  if (isEditMode.value) {
    isPageLoading.value = true
    try {
      const data = await store.fetchById(entityId.value)
      Object.assign(form, {
        name: data.name,
        status: data.status
      })
    } finally {
      isPageLoading.value = false
    }
  }
})

async function handleSubmit() {
  await formRef.value.validate()
  if (isEditMode.value) {
    await store.update(entityId.value, { ...form })
  } else {
    await store.create({ ...form })
  }
  router.back()
}

function handleCancel() {
  router.back()
}
</script>
```

**Key constraints:**
- Form loading (pre-fill) uses local `isPageLoading`, not store's `isLoading`
- Submit spinner uses `store.isSubmitting`
- Call `formRef.value.validate()` before submitting — let Element Plus handle validation messages
- After success, `router.back()` — do NOT manually navigate to list path

---

## Template 5: Permission Button Pattern

```vue
<script setup>
import { hasPermission } from '@/utils/auth'
</script>

<template>
  <!-- Single permission gate -->
  <el-button v-if="hasPermission('domain.write')" @click="handleCreate">
    Create
  </el-button>

  <!-- Admin-only -->
  <el-button v-if="hasPermission('admin')" type="danger" @click="handleDanger">
    Admin Action
  </el-button>

  <!-- Disable instead of hide (for discoverability) -->
  <el-button :disabled="!hasPermission('domain.write')" @click="handleEdit">
    Edit
  </el-button>
</template>
```

**Permission keys convention** (from `rolePermissions.js`):

| Permission Key | Description |
|---|---|
| `admin` | Full admin access |
| `{domain}.read` | View access for a domain |
| `{domain}.write` | Create/edit access for a domain |
| `{domain}.delete` | Delete access for a domain |
| `{domain}.export` | Export access (restricted data requires extra confirmation) |

---

## Template 6: Partial Loading Pattern

**RULE: Full-page loading masks are prohibited.** Use these patterns instead.

```vue
<!-- Correct: table-level loading -->
<el-table v-loading="store.isLoading" :data="store.list">...</el-table>

<!-- Correct: card-level loading -->
<el-card v-loading="isCardLoading">...</el-card>

<!-- Correct: button spinner during submit -->
<el-button :loading="store.isSubmitting" @click="handleSubmit">Save</el-button>

<!-- WRONG: Do not do this -->
<!-- <div v-loading.fullscreen="isLoading">entire page</div> -->
```

For skeleton loading on initial page render:

```vue
<template>
  <el-skeleton :loading="isInitialLoad" animated :count="3">
    <template #default>
      <!-- actual content -->
    </template>
  </el-skeleton>
</template>

<script setup>
import { ref, onMounted } from 'vue'
const isInitialLoad = ref(true)
onMounted(async () => {
  await store.fetchList()
  isInitialLoad.value = false
})
</script>
```

---

## Template 7: Background Refresh Pattern

For non-critical data that should refresh silently (without spinner):

```javascript
// In a store action
async function silentRefresh() {
  await fetchList(buildParams(), false)  // showLoading = false
}

// Polling (use with care — prefer WebSocket for real-time needs)
let refreshTimer = null

function startPolling(intervalMs = 30000) {
  stopPolling()
  refreshTimer = setInterval(() => silentRefresh(), intervalMs)
}

function stopPolling() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

// In component:
// onMounted(() => startPolling())
// onUnmounted(() => stopPolling())
```

**Optimistic update pattern:**

```javascript
// Remove from list immediately, revert on failure
async function removeOptimistic(id) {
  const index = list.value.findIndex(item => item.id === id)
  const backup = list.value[index]
  list.value.splice(index, 1)  // optimistic remove
  try {
    await domainApi.remove(id)
    ElMessage.success('Deleted')
  } catch (error) {
    list.value.splice(index, 0, backup)  // revert
    ElMessage.error('Delete failed: ' + (error.response?.data?.detail ?? error.message))
    throw error
  }
}
```

---

## Checklist: Before Submitting a New Page

- [ ] All HTTP requests go through `api/*.js` (no direct `axios` calls in component)
- [ ] Store state is only modified via `actions` or `$patch()`
- [ ] List page uses `v-loading` on table, not full-page mask
- [ ] Pagination and filter state are local to component, not in store
- [ ] Form validates via `formRef.validate()` before submit
- [ ] Write operations followed by silent refresh (`showLoading = false`)
- [ ] Permission-gated buttons use `hasPermission()` + `v-if`
- [ ] Error messages come from `error.response?.data?.detail ?? error.message`
- [ ] No emoji characters in any string literals (Windows GBK encoding risk)
