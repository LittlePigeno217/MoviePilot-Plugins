<script setup>
import { ref, watch } from 'vue'
import { pluginRequest } from '../utils/plugin'

const props = defineProps({
  modelValue: {
    type: Boolean,
    default: false,
  },
  api: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['update:modelValue', 'selected', 'toast'])

const loading = ref(false)
const basePath = ref('')
const currentPath = ref('')
const items = ref([])
const breadcrumbs = ref([])

async function loadDirectory(path = '') {
  loading.value = true
  try {
    const queryPath = path ? `?path=${encodeURIComponent(path)}` : ''
    const result = await pluginRequest(props.api, `/browse_local${queryPath}`, { method: 'GET' })

    if (!result?.success) {
      emit('toast', result?.msg || '获取目录失败', 'error')
      return
    }

    basePath.value = result.data.base
    currentPath.value = result.data.current || ''
    items.value = result.data.items || []

    // 更新面包屑
    updateBreadcrumbs(path)
  } catch (error) {
    emit('toast', error?.message || '获取目录失败', 'error')
  } finally {
    loading.value = false
  }
}

function updateBreadcrumbs(path) {
  breadcrumbs.value = [{ name: '媒体库', path: '' }]

  if (path) {
    const parts = path.split('/').filter(Boolean)
    let currentBreadPath = ''
    for (const part of parts) {
      currentBreadPath += (currentBreadPath ? '/' : '') + part
      breadcrumbs.value.push({ name: part, path: currentBreadPath })
    }
  }
}

function navigateToDirectory(item) {
  loadDirectory(item.path)
}

function navigateToBreadcrumb(breadcrumb) {
  loadDirectory(breadcrumb.path)
}

function selectCurrentDirectory() {
  const fullPath = currentPath.value ? currentPath.value : ''
  emit('selected', fullPath)
  emit('update:modelValue', false)
}

function closeDialog() {
  emit('update:modelValue', false)
}

watch(
  () => props.modelValue,
  (isOpen) => {
    if (isOpen) {
      loadDirectory('')
    }
  }
)
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="600px"
    persistent
    @update:model-value="closeDialog"
  >
    <v-card class="local-path-selector">
      <v-card-title class="d-flex align-center justify-space-between">
        <span>选择本地目录</span>
        <v-icon icon="mdi-folder-outline" />
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <!-- 面包屑导航 -->
        <div v-if="breadcrumbs.length > 0" class="breadcrumb-bar mb-4">
          <v-breadcrumbs :items="breadcrumbs" small>
            <template #item="{ item, index }">
              <v-breadcrumbs-item
                :href="`#`"
                @click.prevent="navigateToBreadcrumb(item)"
                :disabled="loading"
              >
                {{ item.name }}
              </v-breadcrumbs-item>
            </template>
          </v-breadcrumbs>
        </div>

        <!-- 加载状态 -->
        <v-progress-linear v-if="loading" indeterminate class="mb-3" />

        <!-- 目录列表 -->
        <v-list v-else density="compact" class="directory-list">
          <v-list-item
            v-if="items.length === 0"
            disabled
            class="text-center text-grey"
          >
            <span>此目录为空</span>
          </v-list-item>

          <v-list-item
            v-for="item in items"
            :key="item.path"
            @click="navigateToDirectory(item)"
            class="directory-item"
          >
            <template #prepend>
              <v-icon icon="mdi-folder" color="#167A5B" />
            </template>
            <v-list-item-title>{{ item.name }}</v-list-item-title>
            <template #append>
              <v-icon icon="mdi-chevron-right" size="small" color="#999" />
            </template>
          </v-list-item>
        </v-list>
      </v-card-text>

      <v-divider />

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="plain" @click="closeDialog" :disabled="loading">
          取消
        </v-btn>
        <v-btn
          color="#167A5B"
          variant="flat"
          @click="selectCurrentDirectory"
          :disabled="loading"
        >
          选择当前目录
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.local-path-selector {
  min-height: 400px;
}

.breadcrumb-bar {
  border-bottom: 1px solid #e0e0e0;
  padding-bottom: 12px;
}

.directory-list {
  max-height: 400px;
  overflow-y: auto;
}

.directory-item {
  cursor: pointer;
  transition: background-color 0.2s;
}

.directory-item:hover {
  background-color: rgba(22, 122, 91, 0.08);
}
</style>
