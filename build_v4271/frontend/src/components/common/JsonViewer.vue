<template>
  <div class="json-viewer">
    <div
      v-for="(item, index) in formattedData"
      :key="index"
      class="json-item"
      :class="{ 'json-expanded': item.expanded }"
    >
      <div class="json-line" @click="toggleExpand(item)">
        <span class="json-key">{{ item.key }}</span>
        <span class="json-separator">:</span>
        <span
          v-if="!item.expandable"
          class="json-value"
          :class="getValueClass(item.type)"
        >
          {{ item.displayValue }}
        </span>
        <span v-else class="json-toggle">
          <el-icon v-if="item.expanded"><ArrowDown /></el-icon>
          <el-icon v-else><ArrowRight /></el-icon>
          <span class="json-preview">{{ item.preview }}</span>
        </span>
      </div>
      <div v-if="item.expandable && item.expanded" class="json-children">
        <JsonViewer
          v-if="item.type === 'object'"
          :data="item.value"
          :level="level + 1"
        />
        <div
          v-else-if="item.type === 'array'"
          v-for="(child, childIndex) in item.value"
          :key="childIndex"
          class="json-array-item"
        >
          <span class="json-array-index">[{{ childIndex }}]</span>
          <JsonViewer :data="child" :level="level + 1" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ArrowDown, ArrowRight } from '@element-plus/icons-vue'

const props = defineProps({
  data: {
    type: [Object, Array, String, Number, Boolean, null],
    required: true
  },
  level: {
    type: Number,
    default: 0
  }
})

const formattedData = computed(() => {
  if (props.data === null || props.data === undefined) {
    return [{
      key: '',
      value: null,
      type: 'null',
      displayValue: 'null',
      expandable: false,
      expanded: false
    }]
  }

  if (typeof props.data === 'string') {
    return [{
      key: '',
      value: props.data,
      type: 'string',
      displayValue: `"${props.data}"`,
      expandable: false,
      expanded: false
    }]
  }

  if (typeof props.data === 'number') {
    return [{
      key: '',
      value: props.data,
      type: 'number',
      displayValue: props.data,
      expandable: false,
      expanded: false
    }]
  }

  if (typeof props.data === 'boolean') {
    return [{
      key: '',
      value: props.data,
      type: 'boolean',
      displayValue: props.data ? 'true' : 'false',
      expandable: false,
      expanded: false
    }]
  }

  if (Array.isArray(props.data)) {
    if (props.data.length === 0) {
      return [{
        key: '',
        value: [],
        type: 'array',
        displayValue: '[]',
        expandable: false,
        expanded: false
      }]
    }
    return props.data.map((item, index) => ({
      key: `[${index}]`,
      value: item,
      type: Array.isArray(item) ? 'array' : typeof item === 'object' ? 'object' : 'primitive',
      preview: Array.isArray(item) ? `Array(${item.length})` : typeof item === 'object' ? `Object(${Object.keys(item).length} keys)` : String(item),
      expandable: true,
      expanded: false
    }))
  }

  if (typeof props.data === 'object') {
    const keys = Object.keys(props.data)
    if (keys.length === 0) {
      return [{
        key: '',
        value: {},
        type: 'object',
        displayValue: '{}',
        expandable: false,
        expanded: false
      }]
    }
    return keys.map(key => {
      const value = props.data[key]
      const type = Array.isArray(value) ? 'array' : typeof value === 'object' && value !== null ? 'object' : typeof value
      return {
        key,
        value,
        type,
        preview: Array.isArray(value) ? `Array(${value.length})` : typeof value === 'object' && value !== null ? `Object(${Object.keys(value).length} keys)` : String(value),
        expandable: type === 'object' || type === 'array',
        expanded: false
      }
    })
  }

  return []
})

const toggleExpand = (item) => {
  if (item.expandable) {
    item.expanded = !item.expanded
  }
}

const getValueClass = (type) => {
  return {
    'json-value-string': type === 'string',
    'json-value-number': type === 'number',
    'json-value-boolean': type === 'boolean',
    'json-value-null': type === 'null'
  }
}
</script>

<style scoped>
.json-viewer {
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
  font-size: 13px;
  line-height: 1.6;
  padding-left: 0;
}

.json-item {
  margin: 2px 0;
}

.json-line {
  display: flex;
  align-items: center;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 2px;
  transition: background-color 0.2s;
}

.json-line:hover {
  background-color: #f5f7fa;
}

.json-key {
  color: #905;
  font-weight: 500;
  margin-right: 4px;
}

.json-separator {
  color: #999;
  margin: 0 4px;
}

.json-value {
  color: #333;
}

.json-value-string {
  color: #07a;
}

.json-value-number {
  color: #905;
}

.json-value-boolean {
  color: #0086b3;
}

.json-value-null {
  color: #999;
  font-style: italic;
}

.json-toggle {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #666;
}

.json-preview {
  color: #999;
  font-style: italic;
}

.json-children {
  padding-left: 20px;
  margin-left: 8px;
  border-left: 1px solid #e4e7ed;
}

.json-array-item {
  display: flex;
  align-items: flex-start;
  margin: 2px 0;
}

.json-array-index {
  color: #999;
  margin-right: 8px;
  font-weight: 500;
}
</style>

