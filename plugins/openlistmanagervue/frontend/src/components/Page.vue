<template>
  <div class="plugin-page">
    <v-card>
      <v-card-item>
        <v-card-title>OpenList管理器</v-card-title>
        <template #append>
          <v-chip
            :color="statusColor"
            size="small"
            class="mr-2"
          >
            {{ statusText }}
          </v-chip>
          <v-btn icon color="primary" variant="text" @click="notifyClose">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </template>
      </v-card-item>
      <v-card-text>
        <v-alert v-if="error" type="error" class="mb-4">{{ error }}</v-alert>
        <v-skeleton-loader v-if="loading" type="card"></v-skeleton-loader>
        <div v-else>
          <v-row>
            <v-col cols="12" sm="6" md="3">
              <v-card variant="outlined" class="text-center">
                <v-card-text>
                  <div class="text-h4 font-weight-bold text-primary">{{ taskStatus.total_files || 0 }}</div>
                  <div class="text-subtitle-1">总文件数</div>
                </v-card-text>
              </v-card>
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-card variant="outlined" class="text-center">
                <v-card-text>
                  <div class="text-h4 font-weight-bold text-success">{{ taskStatus.copied_files || 0 }}</div>
                  <div class="text-subtitle-1">已复制</div>
                </v-card-text>
              </v-card>
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-card variant="outlined" class="text-center">
                <v-card-text>
                  <div class="text-h4 font-weight-bold text-warning">{{ taskStatus.skipped_files || 0 }}</div>
                  <div class="text-subtitle-1">已跳过</div>
                </v-card-text>
              </v-card>
            </v-col>
            <v-col cols="12" sm="6" md="3">
              <v-card variant="outlined" class="text-center">
                <v-card-text>
                  <div class="text-h4 font-weight-bold text-purple">{{ taskStatus.total_pairs || 0 }}</div>
                  <div class="text-subtitle-1">目录对</div>
                </v-card-text>
              </v-card>
            </v-col>
          </v-row>

          <v-card variant="outlined" class="mt-4">
            <v-card-text>
              <div class="text-subtitle-2 mb-2">任务进度</div>
              <v-progress-linear
                :model-value="taskStatus.progress || 0"
                :color="progressColor"
                height="25"
                rounded
              >
                <template v-slot:default="{ value }">
                  <strong>{{ Math.ceil(value) }}%</strong>
                </template>
              </v-progress-linear>
              <v-row class="mt-4">
                <v-col cols="12" sm="6">
                  <div class="text-caption text-grey-darken-1">当前处理</div>
                  <div class="text-subtitle-1">{{ taskStatus.current_pair || '无' }}</div>
                </v-col>
                <v-col cols="12" sm="6">
                  <div class="text-caption text-grey-darken-1">完成进度</div>
                  <div class="text-subtitle-1">
                    {{ taskStatus.completed_pairs || 0 }} / {{ taskStatus.total_pairs || 0 }}
                  </div>
                </v-col>
              </v-row>
              <v-alert
                v-if="taskStatus.message"
                :type="messageType"
                class="mt-4"
                density="compact"
              >
                {{ taskStatus.message }}
              </v-alert>
            </v-card-text>
          </v-card>

          <v-card variant="outlined" class="mt-4">
            <v-card-title class="text-subtitle-1">最近复制记录</v-card-title>
            <v-card-text>
              <v-list v-if="recentCopies.length > 0" density="compact">
                <v-list-item
                  v-for="(item, index) in recentCopies"
                  :key="index"
                  class="px-0"
                >
                  <template v-slot:prepend>
                    <v-icon
                      :icon="item.success ? 'mdi-check-circle' : 'mdi-alert-circle'"
                      :color="item.success ? 'success' : 'error'"
                      class="mr-2"
                    />
                  </template>
                  <v-list-item-title class="text-body-2">
                    {{ item.source }}
                  </v-list-item-title>
                  <v-list-item-subtitle class="text-caption">
                    {{ item.target }}
                  </v-list-item-subtitle>
                </v-list-item>
              </v-list>
              <v-alert v-else type="info" density="compact">
                暂无复制记录
              </v-alert>
            </v-card-text>
          </v-card>

          <div class="mt-4 text-subtitle-2">
            <div><strong>上次运行:</strong> {{ lastRunTime }}</div>
            <div><strong>开始时间:</strong> {{ startTime }}</div>
            <div><strong>结束时间:</strong> {{ endTime }}</div>
          </div>
        </div>
      </v-card-text>
      <v-card-actions>
        <v-btn color="primary" @click="runTask" :loading="isRunning" :disabled="isRunning">
          <v-icon start>mdi-play</v-icon>
          执行复制任务
        </v-btn>
        <v-btn color="grey" variant="outlined" @click="refreshData" :loading="loading">
          <v-icon start>mdi-refresh</v-icon>
          刷新数据
        </v-btn>
        <v-spacer></v-spacer>
        <v-btn color="primary" @click="notifySwitch">
          <v-icon start>mdi-cog</v-icon>
          配置
        </v-btn>
      </v-card-actions>
    </v-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  model: {
    type: Object,
    default: () => {},
  },
  api: {
    type: Object,
    default: () => {},
  },
  plugin: {
    type: Object,
    default: () => {},
  },
})

const emit = defineEmits(['action', 'switch', 'close'])

const taskStatus = ref({
  status: 'idle',
  progress: 0,
  message: '',
  last_run: null,
  start_time: null,
  end_time: null,
  total_files: 0,
  copied_files: 0,
  skipped_files: 0,
  current_pair: '',
  total_pairs: 0,
  completed_pairs: 0
})

const recentCopies = ref([])
const loading = ref(true)
const error = ref(null)
const isRunning = ref(false)
let statusInterval = null

const statusColor = computed(() => {
  switch (taskStatus.value.status) {
    case 'running':
      return 'info'
    case 'completed':
      return 'success'
    case 'error':
      return 'error'
    default:
      return 'grey'
  }
})

const statusText = computed(() => {
  switch (taskStatus.value.status) {
    case 'running':
      return '运行中'
    case 'completed':
      return '已完成'
    case 'error':
      return '错误'
    default:
      return '空闲'
  }
})

const progressColor = computed(() => {
  const progress = taskStatus.value.progress || 0
  if (progress < 30) return 'error'
  if (progress < 70) return 'warning'
  return 'success'
})

const messageType = computed(() => {
  if (!taskStatus.value.message) return 'info'
  if (taskStatus.value.status === 'error') return 'error'
  if (taskStatus.value.status === 'completed') return 'success'
  return 'info'
})

const lastRunTime = computed(() => {
  return taskStatus.value.last_run 
    ? new Date(taskStatus.value.last_run).toLocaleString('zh-CN')
    : '未运行'
})

const startTime = computed(() => {
  return taskStatus.value.start_time
    ? new Date(taskStatus.value.start_time).toLocaleString('zh-CN')
    : '-'
})

const endTime = computed(() => {
  return taskStatus.value.end_time
    ? new Date(taskStatus.value.end_time).toLocaleString('zh-CN')
    : '-'
})

async function fetchStatus() {
  try {
    const data = await props.api.get(`plugin/${props.plugin.id}/status`)
    taskStatus.value = data || taskStatus.value
    isRunning.value = taskStatus.value.status === 'running'
  } catch (err) {
    console.error('获取状态失败:', err)
  }
}

async function runTask() {
  try {
    isRunning.value = true
    await props.api.post(`plugin/${props.plugin.id}/run`)
    await fetchStatus()
  } catch (err) {
    console.error('执行任务失败:', err)
    error.value = err.message || '执行任务失败'
  } finally {
    isRunning.value = false
  }
}

async function refreshData() {
  loading.value = true
  error.value = null
  try {
    await fetchStatus()
    emit('action')
  } catch (err) {
    console.error('获取数据失败:', err)
    error.value = err.message || '获取数据失败'
  } finally {
    loading.value = false
  }
}

function notifySwitch() {
  emit('switch')
}

function notifyClose() {
  emit('close')
}

onMounted(() => {
  refreshData()
  statusInterval = setInterval(fetchStatus, 5000)
})

onUnmounted(() => {
  if (statusInterval) {
    clearInterval(statusInterval)
  }
})
</script>



