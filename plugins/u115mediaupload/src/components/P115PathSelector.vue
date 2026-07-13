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
const refreshing = ref(false)
const items = ref([])
const breadcrumbs = ref([{ cid: '0', name: '115云盘' }])

async function loadDirectory(cid = '0', isRefresh = false) {
  const isInitial = !isRefresh && breadcrumbs.value.length === 1

  if (isInitial) {
    loading.value = true
  } else if (isRefresh) {
    refreshing.value = true
  }

  try {
    const refreshParam = isRefresh ? '&refresh=true' : ''
    const result = await pluginRequest(
      props.api,
      `/browse_115?cid=${cid}${refreshParam}`,
      { method: 'GET' }
    )

    if (!result?.success) {
      emit('toast', result?.msg || '获取目录失败', 'error')
      return
    }

    items.value = result.data.items || []

    if (!isRefresh && cid !== '0') {
      // 导航到新目录时更新面包屑
      const currentBreadcrumb = breadcrumbs.value[breadcrumbs.value.length - 1]
      if (currentBreadcrumb.cid !== cid) {
        const itemName = items.value[0]?.name || `文件夹 ${cid}`
        breadcrumbs.value.push({ cid, name: itemName })
      }
    }

    if (isRefresh) {
      emit('toast', '目录已刷新', 'success')
    }
  } catch (error) {
    emit('toast', error?.message || '获取目录失败', 'error')
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function navigateToDirectory(item) {
  // 更新面包屑，然后加载子目录
  breadcrumbs.value.push({ cid: item.cid, name: item.name })
  loadDirectory(item.cid, false)
}

function goBack() {
  if (breadcrumbs.value.length > 1) {
    breadcrumbs.value.pop()
    const currentCid = breadcrumbs.value[breadcrumbs.value.length - 1].cid
    loadDirectory(currentCid, false)
  }
}

function refresh() {
  const currentCid = breadcrumbs.value[breadcrumbs.value.length - 1].cid
  loadDirectory(currentCid, true)
}

function selectCurrentDirectory() {
  const current = breadcrumbs.value[breadcrumbs.value.length - 1]
  emit('selected', current.cid, current.name)
  emit('update:modelValue', false)
  breadcrumbs.value = [{ cid: '0', name: '115云盘' }]
}

function closeDialog() {
  emit('update:modelValue', false)
  breadcrumbs.value = [{ cid: '0', name: '115云盘' }]
}

watch(
  () => props.modelValue,
  (isOpen) => {
    if (isOpen) {
      loadDirectory('0', false)
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
    <v-card class="p115-path-selector">
      <v-card-title class="d-flex align-center justify-space-between">
        <span>选择 115 云盘目录</span>
        <v-btn
          icon="mdi-refresh"
          size="small"
          variant="text"
          :loading="refreshing"
          :disabled="loading || refreshing"
          @click="refresh"
          title="刷新目录缓存"
        />
      </v-card-title>

      <v-divider />

      <v-card-text class="pa-4">
        <!-- 面包屑导航 -->
        <div class="breadcrumb-bar mb-4">
          <v-btn
            icon="mdi-arrow-left"
            size="small"
            variant="text"
            :disabled="breadcrumbs.length <= 1 || loading"
            @click="goBack"
            title="返回上一级"
          />
          <span class="breadcrumb-text">
            {{ breadcrumbs.map(b => b.name).join(' / ') }}
          </span>
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
            :key="item.cid"
            @click="navigateToDirectory(item)"
            class="directory-item"
          >
            <template #prepend>
              <v-icon icon="mdi-folder" color="#245B7A" />
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
          color="#245B7A"
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
.p115-path-selector {
  min-height: 400px;
}

.breadcrumb-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  border-bottom: 1px solid #e0e0e0;
  padding-bottom: 12px;
}

.breadcrumb-text {
  font-size: 14px;
  color: #666;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  background-color: rgba(36, 91, 122, 0.08);
}
</style>
