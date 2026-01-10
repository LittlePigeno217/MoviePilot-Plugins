<template>
  <div class="dashboard-widget">
    <v-hover>
      <!-- 仪表板内容 -->
      <template #default="{ isHovering, props: hoverProps }">
        <v-card v-bind="hoverProps" variant="outlined" style="border-radius: 8px;">
          <v-card-title class="d-flex justify-space-between align-center">
            <span>OpenList管理器新</span>
            <!-- 只在悬停时显示拖拽图标 -->
            <v-icon v-show="isHovering" class="cursor-move">mdi-drag</v-icon>
          </v-card-title>
          <v-card-text>
            <!-- 任务状态 -->
            <div class="mb-3">
              <div class="text-caption text-secondary mb-1">任务状态</div>
              <v-chip :color="statusColor" size="small">{{ taskStatus.status }}</v-chip>
            </div>

            <!-- 复制进度 -->
            <div class="mb-3">
              <div class="text-caption text-secondary mb-1">复制进度</div>
              <v-progress-linear
                :value="taskStatus.progress"
                height="6"
                :color="statusColor"
                class="mb-1"
              ></v-progress-linear>
              <div class="text-caption">
                {{ taskStatus.copied_files }}/{{ taskStatus.total_files }} 文件
              </div>
            </div>

            <!-- 目录对进度 -->
            <div>
              <div class="text-caption text-secondary mb-1">目录对进度</div>
              <div class="text-caption">
                {{ taskStatus.completed_pairs }}/{{ taskStatus.total_pairs }} 目录对
              </div>
            </div>
          </v-card-text>
          <!-- 操作按钮 -->
          <v-card-actions class="justify-end pb-3 pr-3">
            <v-btn size="small" color="primary" @click="runTask" :disabled="taskStatus.status === 'running'">
              <template v-if="taskStatus.status === 'running'">
                <v-icon size="small" class="mr-1">mdi-loading</v-icon>
                运行中
              </template>
              <template v-else>
                <v-icon size="small" class="mr-1">mdi-play</v-icon>
                运行任务
              </template>
            </v-btn>
          </v-card-actions>
        </v-card>
      </template>
    </v-hover>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

// 接收配置和刷新控制
const props = defineProps({
  config: {
    type: Object,
    default: () => ({})
  },
  allowRefresh: {
    type: Boolean,
    default: true
  }
})

// 任务状态数据
const taskStatus = ref({
  status: 'idle',
  progress: 0,
  copied_files: 0,
  total_files: 0,
  completed_pairs: 0,
  total_pairs: 0
})

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
  // 这里应该调用API获取任务状态，但在仪表板组件中可能不需要实时刷新
  // 或者通过props接收状态数据
}

// 执行复制任务
function runTask() {
  // 这里应该发送事件通知主应用执行任务
}

// 组件挂载时获取初始状态
onMounted(() => {
  getStatus()
})

// 组件卸载时清理资源
onUnmounted(() => {
  // 清理资源
})
</script>