<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted } from 'vue'
// 自定义事件，用于通知主应用刷新数据
const emit = defineEmits(['action', 'switch', 'close'])

// 接收API对象
const props = defineProps({
  api: {
    type: Object,
    default: () => {}
  }
})

// 类型定义
interface FileRecord {
  key: string
  filename: string
  start_time?: string
  complete_time?: string
}

interface StatusData {
  target_files_count: number
  // 任务状态字段
  status?: string
  progress?: number
  message?: string
  start_time?: string
  end_time?: string
  total_files?: number
  copied_files?: number
  skipped_files?: number
  current_pair?: string
  total_pairs?: number
  completed_pairs?: number
  // 计数字段
  copying_count?: number
  completed_count?: number
  copied_files_count?: number
}

// 页面数据
const status = ref<StatusData>({ 
  target_files_count: 0,
  status: 'idle',
  progress: 0,
  message: '等待执行',
  copying_count: 0,
  completed_count: 0
})
const copyingFiles = ref<FileRecord[]>([])
const completedFiles = ref<FileRecord[]>([])
const refreshInterval = ref<number | null>(null)

// 计算属性：将正在复制的文件按每行4个分组
const copyingFilesChunked4 = computed(() => {
  const chunks = []
  for (let i = 0; i < copyingFiles.value.length; i += 4) {
    chunks.push(copyingFiles.value.slice(i, i + 4))
  }
  return chunks
})

// 计算属性：将已完成的文件按每行6个分组
const completedFilesChunked6 = computed(() => {
  const chunks = []
  for (let i = 0; i < completedFiles.value.length; i += 6) {
    chunks.push(completedFiles.value.slice(i, i + 6))
  }
  return chunks
})

// 计算属性：判断任务是否正在运行
const isTaskRunning = computed(() => {
  return status.value.status === 'running'
})

// 初始化数据
async function initData() {
  try {
    const statusData = await props.api.get('plugin/OpenListManagerNew/status')
    if (statusData && statusData.data) {
      // 更新状态数据
      status.value = {
        target_files_count: statusData.data.target_files_count || 0,
        // 任务状态数据
        status: statusData.data.status || 'idle',
        progress: statusData.data.progress || 0,
        message: statusData.data.message || '等待执行',
        start_time: statusData.data.start_time,
        end_time: statusData.data.end_time,
        total_files: statusData.data.total_files || 0,
        copied_files: statusData.data.copied_files || 0,
        skipped_files: statusData.data.skipped_files || 0,
        current_pair: statusData.data.current_pair,
        total_pairs: statusData.data.total_pairs || 0,
        completed_pairs: statusData.data.completed_pairs || 0,
        // 计数数据
        copying_count: statusData.data.copying_count || 0,
        completed_count: statusData.data.completed_count || 0,
        copied_files_count: statusData.data.copied_files_count || 0
      }
      
      // 这里需要根据实际API返回的数据结构调整
      // 目前暂时使用模拟数据，后续需要根据后端API实现调整
      copyingFiles.value = []
      completedFiles.value = []
    }
  } catch (error) {
    console.error('获取数据失败:', error)
  }
}

// 执行复制任务
async function runTask() {
  try {
    await props.api.post('plugin/OpenListManagerNew/run')
    await initData()
    // 开始实时刷新
    startAutoRefresh()
  } catch (error) {
    console.error('执行任务失败:', error)
  }
}

// 开始自动刷新
function startAutoRefresh() {
  // 清除之前的定时器
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
  }
  // 每2秒刷新一次
  refreshInterval.value = window.setInterval(() => {
    initData()
  }, 2000)
}

// 停止自动刷新
function stopAutoRefresh() {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
    refreshInterval.value = null
  }
}

// 通知主应用刷新数据
function notifyRefresh() {
  initData()
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

// 初始化加载数据
onMounted(() => {
  initData()
  // 如果任务正在运行，开始自动刷新
  if (isTaskRunning.value) {
    startAutoRefresh()
  }
})

// 组件卸载时清除定时器
onUnmounted(() => {
  stopAutoRefresh()
})
</script>

<template>
  <div class="plugin-page">
    <v-card variant="outlined" class="status-card">
      <v-card-text class="pa-3">
        <!-- 页面标题 -->
        <div class="d-flex align-center justify-space-between mb-3">
          <div class="d-flex align-center">
            <v-avatar color="primary" size="32" class="mr-2">
              <v-icon icon="mdi-view-dashboard" size="20"></v-icon>
            </v-avatar>
            <div>
              <div class="text-subtitle-1 font-weight-bold">OpenList管理器新</div>
              <div class="text-caption text-grey-darken-1">文件复制与管理状态监控</div>
            </div>
          </div>
          <div>
            <v-btn color="primary" @click="runTask">立即执行</v-btn>
            <v-btn color="primary" @click="notifyRefresh" class="ml-2">刷新数据</v-btn>
            <v-btn color="primary" @click="notifySwitch" class="ml-2">配置插件</v-btn>
            <v-btn color="primary" @click="notifyClose" class="ml-2">关闭页面</v-btn>
          </div>
        </div>
        
        <!-- 第一行：三个状态框 -->
        <v-row class="mb-3">
          <!-- 状态框1：目标目录媒体文件数 -->
          <v-col cols="12" sm="4">
            <v-card color="primary" variant="tonal" class="status-card-item" style="min-height: 80px; height: 100%; border-radius: 8px; transition: all 0.3s ease;">
              <v-card-text class="text-center pa-2">
                <v-avatar color="primary" size="36" class="mb-1">
                  <v-icon icon="mdi-folder-open" size="20"></v-icon>
                </v-avatar>
                <div class="text-caption font-weight-medium text-primary-darken-1 mb-1">目标目录媒体文件数</div>
                <div class="text-h5 font-weight-bold text-primary-darken-2">{{ status.target_files_count || 0 }}</div>
              </v-card-text>
            </v-card>
          </v-col>
          <!-- 状态框2：正在复制媒体文件 -->
          <v-col cols="12" sm="4">
            <v-card color="warning" variant="tonal" class="status-card-item" style="min-height: 80px; height: 100%; border-radius: 8px; transition: all 0.3s ease;">
              <v-card-text class="text-center pa-2">
                <v-avatar color="warning" size="36" class="mb-1">
                  <v-icon icon="mdi-progress-clock" size="20"></v-icon>
                </v-avatar>
                <div class="text-caption font-weight-medium text-warning-darken-1 mb-1">正在复制的媒体文件</div>
                <div class="text-h5 font-weight-bold text-warning-darken-2">{{ status.copying_count || 0 }}</div>
              </v-card-text>
            </v-card>
          </v-col>
          <!-- 状态框3：累计复制媒体文件 -->
          <v-col cols="12" sm="4">
            <v-card color="success" variant="tonal" class="status-card-item" style="min-height: 80px; height: 100%; border-radius: 8px; transition: all 0.3s ease;">
              <v-card-text class="text-center pa-2">
                <v-avatar color="success" size="36" class="mb-1">
                  <v-icon icon="mdi-check-circle-outline" size="20"></v-icon>
                </v-avatar>
                <div class="text-caption font-weight-medium text-success-darken-1 mb-1">累计复制媒体文件</div>
                <div class="text-h5 font-weight-bold text-success-darken-2">{{ status.completed_count || 0 }}</div>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
        
        <!-- 任务进度卡片 -->
        <v-card variant="outlined" class="mb-3" style="border-radius: 8px;">
          <v-card-text class="pa-3">
            <div class="d-flex align-center justify-space-between mb-2">
              <div class="d-flex align-center">
                <v-avatar :color="isTaskRunning ? 'blue' : 'grey'" size="28" class="mr-2">
                  <v-icon :icon="isTaskRunning ? 'mdi-progress-clock' : 'mdi-check-circle'" size="16"></v-icon>
                </v-avatar>
                <div>
                  <div class="text-subtitle-2 font-weight-bold">
                    {{ isTaskRunning ? '任务正在执行中' : '任务状态' }}
                  </div>
                  <div class="text-caption text-grey-darken-1">{{ status.message }}</div>
                </div>
              </div>
              <div class="text-caption text-grey-darken-1">
                进度: {{ status.progress }}%
              </div>
            </div>
            
            <!-- 进度条 -->
            <v-progress-linear 
              v-model="status.progress" 
              height="8"
              :color="isTaskRunning ? 'blue' : 'grey'"
              rounded
              class="mb-3"
              style="border-radius: 4px;"
            ></v-progress-linear>
            
            <!-- 任务详情 -->
            <v-row dense class="mb-2">
              <v-col cols="12" sm="6" md="3">
                <div class="text-caption text-grey-darken-1">开始时间</div>
                <div class="text-body-2">{{ status.start_time || '未开始' }}</div>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <div class="text-caption text-grey-darken-1">结束时间</div>
                <div class="text-body-2">{{ status.end_time || (isTaskRunning ? '执行中' : '未结束') }}</div>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <div class="text-caption text-grey-darken-1">总计文件</div>
                <div class="text-body-2">{{ status.total_files || 0 }}</div>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <div class="text-caption text-grey-darken-1">已复制</div>
                <div class="text-body-2">{{ status.copied_files || 0 }}</div>
              </v-col>
            </v-row>
            
            <v-row dense class="mb-2">
              <v-col cols="12" sm="6" md="3">
                <div class="text-caption text-grey-darken-1">已跳过</div>
                <div class="text-body-2">{{ status.skipped_files || 0 }}</div>
              </v-col>
              <v-col cols="12" sm="6" md="3">
                <div class="text-caption text-grey-darken-1">目录配对</div>
                <div class="text-body-2">{{ status.completed_pairs || 0 }} / {{ status.total_pairs || 0 }}</div>
              </v-col>
            </v-row>
            
            <!-- 当前处理的目录配对 -->
            <div v-if="status.current_pair" class="mt-2">
              <div class="text-caption text-grey-darken-1 mb-1">当前处理</div>
              <v-card variant="outlined" class="pa-2" style="border-radius: 6px;">
                <div class="text-body-2 text-truncate">{{ status.current_pair }}</div>
              </v-card>
            </div>
          </v-card-text>
        </v-card>
        
        <!-- 第二行：正在复制的媒体文件列表 -->
        <v-row class="mb-3">
          <v-col cols="12">
            <v-card variant="outlined" class="file-list-card" style="border-radius: 8px;">
              <v-card-title class="d-flex align-center pa-2 bg-orange-lighten-5">
                <v-avatar color="orange" size="28" class="mr-2">
                  <v-icon icon="mdi-progress-upload" size="16"></v-icon>
                </v-avatar>
                <div>
                  <div class="text-subtitle-2 font-weight-bold text-orange-darken-2">正在复制的媒体文件</div>
                  <div class="text-caption text-grey-darken-1">共 {{ copyingFiles.length }} 个文件</div>
                </div>
              </v-card-title>
              <v-card-text class="pa-2">
                <template v-if="copyingFiles.length === 0">
                  <div class="text-center text-grey py-8">
                    <v-icon icon="mdi-file-sync-outline" size="48" color="grey-lighten-1" class="mb-2"></v-icon>
                    <div class="text-body-2 text-grey-darken-1">暂无正在复制的媒体文件</div>
                  </div>
                </template>
                <template v-else>
                  <!-- 按每行4个分组 -->
                  <v-row v-for="(row, rowIndex) in copyingFilesChunked4" :key="rowIndex" class="mb-1" dense align="stretch">
                    <v-col v-for="file in row" :key="file.key" cols="12" sm="3" md="3" lg="3" class="pa-1">
                      <v-card 
                        color="orange-lighten-5" 
                        variant="flat" 
                        class="text-center compact-file-card" 
                        style="min-height: 60px; height: 100%; border-radius: 8px; transition: all 0.2s ease;"
                      >
                        <v-card-text 
                          class="pa-2 d-flex flex-column align-center justify-center" 
                          style="min-height: 60px;"
                        >
                          <div class="d-flex align-center justify-center w-100 mb-1">
                            <v-icon 
                              icon="mdi-progress-clock" 
                              size="x-small" 
                              class="text-orange mr-1" 
                              style="min-width: 14px;"
                            ></v-icon>
                            <span 
                              class="text-caption text-left compact-filename" 
                              style="word-break: break-all; line-height: 1.1; max-height: 2.2em; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; font-size: 0.7rem; flex: 1;"
                            >{{ file.filename }}</span>
                          </div>
                          <div 
                            class="text-caption text-grey-darken-1 mt-1" 
                            style="font-size: 0.6rem;"
                          >{{ file.start_time }}</div>
                        </v-card-text>
                      </v-card>
                    </v-col>
                    <!-- 填充空列以保持对称 -->
                    <v-col v-for="i in (4 - row.length)" :key="i" cols="12" sm="3" md="3" lg="3" class="pa-1"></v-col>
                  </v-row>
                </template>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
        
        <!-- 第三行：最近完成的媒体文件列表 -->
        <v-row>
          <v-col cols="12">
            <v-card variant="outlined" class="file-list-card" style="border-radius: 8px;">
              <v-card-title class="d-flex align-center pa-2 bg-green-lighten-5">
                <v-avatar color="success" size="28" class="mr-2">
                  <v-icon icon="mdi-check-circle" size="16"></v-icon>
                </v-avatar>
                <div>
                  <div class="text-subtitle-2 font-weight-bold text-green-darken-2">最近完成的媒体文件</div>
                  <div class="text-caption text-grey-darken-1">共 {{ completedFiles.length }} 个文件</div>
                </div>
              </v-card-title>
              <v-card-text class="pa-2">
                <template v-if="completedFiles.length === 0">
                  <div class="text-center text-grey py-8">
                    <v-icon icon="mdi-file-question" size="48" color="grey-lighten-1" class="mb-2"></v-icon>
                    <div class="text-body-2 text-grey-darken-1">暂无完成的媒体文件记录</div>
                  </div>
                </template>
                <template v-else>
                  <!-- 按每行6个分组 -->
                  <v-row v-for="(row, rowIndex) in completedFilesChunked6" :key="rowIndex" class="mb-1" dense align="stretch">
                    <v-col v-for="file in row" :key="file.key" cols="12" sm="2" md="2" lg="2" class="pa-1">
                      <v-card 
                        color="green-lighten-5" 
                        variant="flat" 
                        class="text-center compact-file-card" 
                        style="min-height: 50px; height: 100%; border-radius: 6px; transition: all 0.2s ease;"
                      >
                        <v-card-text 
                          class="pa-1 d-flex flex-column align-center justify-center" 
                          style="min-height: 50px;"
                        >
                          <div class="d-flex align-center justify-center w-100 mb-1">
                            <v-icon 
                              icon="mdi-check-circle" 
                              size="x-small" 
                              class="text-success mr-1" 
                              style="min-width: 14px;"
                            ></v-icon>
                            <span 
                              class="text-caption text-left compact-filename" 
                              style="word-break: break-all; line-height: 1.1; max-height: 2.2em; overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; font-size: 0.7rem; flex: 1;"
                            >{{ file.filename }}</span>
                          </div>
                          <div 
                            class="text-caption text-grey-darken-1 mt-1" 
                            style="font-size: 0.6rem;"
                          >{{ file.complete_time }}</div>
                        </v-card-text>
                      </v-card>
                    </v-col>
                    <!-- 填充空列以保持对称 -->
                    <v-col v-for="i in (6 - row.length)" :key="i" cols="12" sm="2" md="2" lg="2" class="pa-1"></v-col>
                  </v-row>
                </template>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>
  </div>
</template>