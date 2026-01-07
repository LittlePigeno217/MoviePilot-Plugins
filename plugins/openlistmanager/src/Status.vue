<template>
  <v-card variant="outlined" class="status-card">
    <v-card-text class="pa-3">
      <div class="d-flex align-center justify-space-between mb-3">
        <div class="d-flex align-center">
          <v-icon icon="mdi-view-dashboard" color="primary" size="medium" class="mr-2"></v-icon>
          <div>
            <div class="text-h6 font-weight-bold">OpenList管理器</div>
            <div class="text-caption text-grey-darken-1">文件复制与管理状态监控</div>
          </div>
        </div>
        <v-btn
          color="primary"
          variant="outlined"
          size="small"
          prepend-icon="mdi-refresh"
          :loading="loading"
          @click="refreshStatus"
        >
          刷新
        </v-btn>
      </div>

      <v-row class="mb-3">
        <v-col cols="12" sm="4">
          <v-card
            color="primary"
            variant="tonal"
            class="status-card-item"
            style="min-height: 80px; height: 100%; border-radius: 8px; transition: all 0.3s ease;"
          >
            <v-card-text class="text-center pa-2">
              <v-avatar color="primary" size="36" class="mb-1">
                <v-icon icon="mdi-folder-open" size="20"></v-icon>
              </v-avatar>
              <div class="text-caption font-weight-medium text-primary-darken-1 mb-1">目标目录媒体文件数</div>
              <div class="text-h5 font-weight-bold text-primary-darken-2">{{ status.targetFilesCount || 0 }}</div>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" sm="4">
          <v-card
            color="warning"
            variant="tonal"
            class="status-card-item"
            style="min-height: 80px; height: 100%; border-radius: 8px; transition: all 0.3s ease;"
          >
            <v-card-text class="text-center pa-2">
              <v-avatar color="warning" size="36" class="mb-1">
                <v-icon icon="mdi-progress-clock" size="20"></v-icon>
              </v-avatar>
              <div class="text-caption font-weight-medium text-warning-darken-1 mb-1">正在复制媒体文件</div>
              <div class="text-h5 font-weight-bold text-warning-darken-2">{{ status.copyingFilesCount || 0 }}</div>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" sm="4">
          <v-card
            color="success"
            variant="tonal"
            class="status-card-item"
            style="min-height: 80px; height: 100%; border-radius: 8px; transition: all 0.3s ease;"
          >
            <v-card-text class="text-center pa-2">
              <v-avatar color="success" size="36" class="mb-1">
                <v-icon icon="mdi-check-circle-outline" size="20"></v-icon>
              </v-avatar>
              <div class="text-caption font-weight-medium text-success-darken-1 mb-1">累计复制媒体文件</div>
              <div class="text-h5 font-weight-bold text-success-darken-2">{{ status.completedFilesCount || 0 }}</div>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <v-row class="mb-3">
        <v-col cols="12">
          <v-card variant="outlined" class="file-list-card" style="border-radius: 8px;">
            <v-card-title class="d-flex align-center pa-2 bg-orange-lighten-5">
              <v-avatar color="orange" size="28" class="mr-2">
                <v-icon icon="mdi-progress-upload" size="16"></v-icon>
              </v-avatar>
              <div>
                <div class="text-subtitle-2 font-weight-bold text-orange-darken-2">正在复制的媒体文件</div>
                <div class="text-caption text-grey-darken-1">共 {{ status.copyingFiles?.length || 0 }} 个文件</div>
              </div>
            </v-card-title>
            <v-card-text class="pa-2">
              <v-list v-if="status.copyingFiles && status.copyingFiles.length > 0" density="compact">
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
              <v-alert v-else type="info" variant="tonal" density="compact" class="mt-2">
                暂无正在复制的文件
              </v-alert>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>

      <v-row>
        <v-col cols="12">
          <v-card variant="outlined" class="file-list-card" style="border-radius: 8px;">
            <v-card-title class="d-flex align-center pa-2 bg-green-lighten-5">
              <v-avatar color="success" size="28" class="mr-2">
                <v-icon icon="mdi-check-circle" size="16"></v-icon>
              </v-avatar>
              <div>
                <div class="text-subtitle-2 font-weight-bold text-green-darken-2">最近完成的媒体文件</div>
                <div class="text-caption text-grey-darken-1">共 {{ status.completedFiles?.length || 0 }} 个文件</div>
              </div>
            </v-card-title>
            <v-card-text class="pa-2">
              <v-list v-if="status.completedFiles && status.completedFiles.length > 0" density="compact">
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
              <v-alert v-else type="info" variant="tonal" density="compact" class="mt-2">
                暂无已完成复制的文件
              </v-alert>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
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
  try {
    const response = await props.api.status.get()
    if (response && response.data) {
      Object.assign(status, response.data)
    }
  } catch (error) {
    console.error('获取状态失败:', error)
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

.status-card-item {
  transition: all 0.3s ease;
}

.status-card-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.file-list-card {
  transition: all 0.3s ease;
}

.file-list-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.v-list-item {
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

.v-list-item:last-child {
  border-bottom: none;
}
</style>
