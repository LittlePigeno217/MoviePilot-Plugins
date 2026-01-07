<template>
  <v-card flat class="rounded border">
    <v-card-title class="text-subtitle-1 d-flex align-center px-3 py-2 bg-primary-lighten-5">
      <v-icon icon="mdi-view-dashboard" class="mr-2" color="primary" size="small"></v-icon>
      <span>OpenList管理器状态</span>
      <v-spacer></v-spacer>
      <v-btn
        color="primary"
        variant="text"
        size="x-small"
        prepend-icon="mdi-refresh"
        :loading="loading"
        @click="refreshStatus"
      >
        刷新
      </v-btn>
    </v-card-title>
    <v-card-text class="px-3 py-2">
      <v-alert v-if="error" type="error" density="compact" class="mb-2 text-caption" variant="tonal" closable>
        {{ error }}
      </v-alert>

      <v-row class="mb-2">
        <v-col cols="12" sm="4">
          <v-card flat class="rounded border status-card">
            <v-card-text class="text-center pa-2">
              <v-icon icon="mdi-folder-open" color="primary" size="large" class="mb-1"></v-icon>
              <div class="text-caption text-grey mb-1">目标目录媒体文件数</div>
              <div class="text-h6 font-weight-bold text-primary">{{ status.targetFilesCount || 0 }}</div>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" sm="4">
          <v-card flat class="rounded border status-card">
            <v-card-text class="text-center pa-2">
              <v-icon icon="mdi-progress-clock" color="warning" size="large" class="mb-1"></v-icon>
              <div class="text-caption text-grey mb-1">正在复制媒体文件</div>
              <div class="text-h6 font-weight-bold text-warning">{{ status.copyingFilesCount || 0 }}</div>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" sm="4">
          <v-card flat class="rounded border status-card">
            <v-card-text class="text-center pa-2">
              <v-icon icon="mdi-check-circle-outline" color="success" size="large" class="mb-1"></v-icon>
              <div class="text-caption text-grey mb-1">累计复制媒体文件</div>
              <div class="text-h6 font-weight-bold text-success">{{ status.completedFilesCount || 0 }}</div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <v-card flat class="rounded mb-2 border">
        <v-card-title class="text-caption d-flex align-center px-3 py-2 bg-orange-lighten-5">
          <v-icon icon="mdi-progress-upload" class="mr-2" color="orange" size="small"></v-icon>
          <span>正在复制的媒体文件 ({{ status.copyingFiles?.length || 0 }})</span>
        </v-card-title>
        <v-card-text class="px-3 py-2">
          <v-list v-if="status.copyingFiles && status.copyingFiles.length > 0" density="compact" class="pa-0">
            <v-list-item
              v-for="file in status.copyingFiles"
              :key="file.id"
              class="px-2 py-1"
            >
              <template v-slot:prepend>
                <v-icon icon="mdi-file-video" color="orange" size="small" class="mr-2"></v-icon>
              </template>
              <v-list-item-title class="text-subtitle-2">{{ file.filename }}</v-list-item-title>
              <v-list-item-subtitle class="text-caption">
                {{ file.sourceDir }} → {{ file.targetDir }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
          <v-alert v-else type="info" density="compact" class="text-caption" variant="tonal">
            暂无正在复制的文件
          </v-alert>
        </v-card-text>
      </v-card>

      <v-card flat class="rounded border">
        <v-card-title class="text-caption d-flex align-center px-3 py-2 bg-green-lighten-5">
          <v-icon icon="mdi-check-circle" class="mr-2" color="success" size="small"></v-icon>
          <span>最近完成的媒体文件 ({{ status.completedFiles?.length || 0 }})</span>
        </v-card-title>
        <v-card-text class="px-3 py-2">
          <v-list v-if="status.completedFiles && status.completedFiles.length > 0" density="compact" class="pa-0">
            <v-list-item
              v-for="file in status.completedFiles"
              :key="file.id"
              class="px-2 py-1"
            >
              <template v-slot:prepend>
                <v-icon icon="mdi-file-check" color="success" size="small" class="mr-2"></v-icon>
              </template>
              <v-list-item-title class="text-subtitle-2">{{ file.filename }}</v-list-item-title>
              <v-list-item-subtitle class="text-caption">
                {{ file.targetDir }} - {{ formatTime(file.completedAt) }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
          <v-alert v-else type="info" density="compact" class="text-caption" variant="tonal">
            暂无已完成复制的文件
          </v-alert>
        </v-card-text>
      </v-card>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  api: {
    type: Object,
    required: true
  }
})

const loading = ref(false)
const error = ref('')
const status = reactive({
  targetFilesCount: 0,
  copyingFilesCount: 0,
  completedFilesCount: 0,
  copyingFiles: [],
  completedFiles: []
})

let refreshInterval = null

const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}

const refreshStatus = async () => {
  loading.value = true
  error.value = ''
  try {
    const response = await props.api.status.get()
    if (response && response.data && response.data.data) {
      Object.assign(status, response.data.data)
    }
  } catch (err) {
    error.value = '获取状态失败: ' + err.message
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refreshStatus()
  refreshInterval = setInterval(refreshStatus, 30000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
  }
})

defineExpose({
  refreshStatus
})
</script>

<style scoped>
.status-card {
  transition: all 0.3s ease;
}

.status-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.v-list-item {
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

.v-list-item:last-child {
  border-bottom: none;
}
</style>
