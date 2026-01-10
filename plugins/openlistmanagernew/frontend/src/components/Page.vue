<template>
  <div class="plugin-page" style="padding: 16px;">
    <!-- 页面标题和操作按钮 -->
    <div class="d-flex justify-space-between align-center mb-4">
      <h2>OpenList管理器新</h2>
      <div>
        <v-btn color="primary" @click="runTask" :disabled="taskStatus.status === 'running'" class="mr-2">
          <template v-if="taskStatus.status === 'running'">
            <v-icon class="mr-1">mdi-loading</v-icon>
            任务运行中
          </template>
          <template v-else>
            <v-icon class="mr-1">mdi-play</v-icon>
            执行复制任务
          </template>
        </v-btn>
        <v-btn color="secondary" @click="notifySwitch">
          <v-icon class="mr-1">mdi-cog</v-icon>
          配置
        </v-btn>
      </div>
    </div>

    <!-- 任务状态卡片 -->
    <v-card variant="outlined" class="mb-4">
      <v-card-title>任务状态</v-card-title>
      <v-card-text>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <!-- 状态信息 -->
          <div>
            <v-row class="mb-2">
              <v-col cols="4">状态:</v-col>
              <v-col cols="8">
                <v-chip :color="statusColor" size="small">{{ taskStatus.status }}</v-chip>
              </v-col>
            </v-row>
            <v-row class="mb-2">
              <v-col cols="4">进度:</v-col>
              <v-col cols="8">
                <v-progress-linear :value="taskStatus.progress" height="8" :color="statusColor" class="mb-1"></v-progress-linear>
                <span>{{ taskStatus.progress }}%</span>
              </v-col>
            </v-row>
            <v-row class="mb-2">
              <v-col cols="4">消息:</v-col>
              <v-col cols="8">{{ taskStatus.message || '无' }}</v-col>
            </v-row>
          </div>

          <!-- 统计信息 -->
          <div>
            <v-row class="mb-2">
              <v-col cols="4">总文件数:</v-col>
              <v-col cols="8">{{ taskStatus.total_files }}</v-col>
            </v-row>
            <v-row class="mb-2">
              <v-col cols="4">已复制:</v-col>
              <v-col cols="8">{{ taskStatus.copied_files }}</v-col>
            </v-row>
            <v-row class="mb-2">
              <v-col cols="4">已跳过:</v-col>
              <v-col cols="8">{{ taskStatus.skipped_files }}</v-col>
            </v-row>
            <v-row class="mb-2">
              <v-col cols="4">目录对:</v-col>
              <v-col cols="8">{{ taskStatus.completed_pairs }}/{{ taskStatus.total_pairs }}</v-col>
            </v-row>
          </div>
        </div>

        <!-- 当前处理目录对 -->
        <v-row class="mt-4" v-if="taskStatus.current_pair">
          <v-col cols="4">当前处理:</v-col>
          <v-col cols="8">
            <v-chip color="info" size="small">{{ taskStatus.current_pair }}</v-chip>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <!-- 目标目录媒体文件数 -->
    <v-card variant="outlined" class="mb-4">
      <v-card-title>目标目录媒体文件数</v-card-title>
      <v-card-text class="text-h4 font-weight-bold">{{ targetFilesCount }}</v-card-text>
    </v-card>

    <!-- 最近复制的文件 -->
    <v-card variant="outlined">
      <v-card-title>最近复制的文件</v-card-title>
      <v-card-text>
        <v-data-table
          :headers="[
            { title: '文件名', value: 'filename' },
            { title: '源目录', value: 'source_path' },
            { title: '目标目录', value: 'target_path' },
            { title: '复制时间', value: 'copy_time' }
          ]"
          :items="copiedFiles"
          :items-per-page="10"
          hide-default-footer
        >
          <template #empty>
            <div class="text-center py-4">暂无复制记录</div>
          </template>
        </v-data-table>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, computed } from 'vue'

// 自定义事件，用于通知主应用刷新数据
const emit = defineEmits(['action', 'switch', 'close'])

// 接收API对象
const props = defineProps({
  api: {
    type: Object,
    default: () => {}
  }
})

// 任务状态数据
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

// 复制文件记录
const copiedFiles = ref([])

// 目标文件数量
const targetFilesCount = ref(0)

// 状态颜色映射
const statusColor = computed(() => {
  const status = taskStatus.value.status
  switch (status) {
    case 'running':
      return 'primary'
    case 'completed':
      return 'success'
    case 'error':
      return 'error'
    default:
      return 'grey'
  }
})

// 获取任务状态
async function getStatus() {
  if (!props.api) return
  try {
    const response = await props.api.get('plugin/OpenListManagerNew/status')
    if (response && response.success) {
      taskStatus.value = response.data
    }
  } catch (error) {
    console.error('获取任务状态失败:', error)
  }
}

// 执行复制任务
async function runTask() {
  if (!props.api) return
  try {
    await props.api.post('plugin/OpenListManagerNew/run')
    // 立即刷新状态
    await getStatus()
  } catch (error) {
    console.error('执行复制任务失败:', error)
  }
}

// 定时刷新任务状态
let refreshTimer = null
function startRefreshTimer() {
  refreshTimer = setInterval(getStatus, 2000)
}

function stopRefreshTimer() {
  if (refreshTimer) {
    clearInterval(refreshTimer)
    refreshTimer = null
  }
}

// 页面挂载时获取初始状态并开始定时刷新
onMounted(() => {
  getStatus()
  startRefreshTimer()
})

// 页面卸载时停止定时刷新
onUnmounted(() => {
  stopRefreshTimer()
})

// 通知主应用刷新数据
function notifyRefresh() {
  emit('action')
}

// 通知主应用切换到配置页面
function notifySwitch() {
  emit('switch')
}

// 通知主应用关闭当前页面
function notifyClose() {
  emit('close')
}
</script>