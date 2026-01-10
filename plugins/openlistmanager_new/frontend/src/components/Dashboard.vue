<script setup lang="ts">
import { ref, onMounted } from 'vue'
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

// 仪表板数据
const dashboardData = ref({
  targetFilesCount: 0,
  copyingFilesCount: 0,
  completedFilesCount: 0,
  lastRunTime: null
})

// 刷新数据
async function refreshData() {
  try {
    // 这里可以添加从API获取数据的逻辑
    // const data = await props.api.get('plugin/OpenListManagerNew/dashboard')
    // dashboardData.value = data
  } catch (error) {
    console.error('刷新仪表板数据失败:', error)
  }
}

// 初始化数据
onMounted(() => {
  refreshData()
})
</script>

<template>
  <div class="dashboard-widget">
    <v-hover>
      <!-- 仪表板内容 -->
      <template #default="{ isHovering, props: hoverProps }">
        <v-card v-bind="hoverProps" class="dashboard-card" style="border-radius: 8px;">
          <v-card-title class="pa-2">
            <div class="d-flex align-center">
              <v-icon icon="mdi-folder-network" size="20" class="mr-2"></v-icon>
              <span>{{ config.title || 'OpenList管理器新' }}</span>
            </div>
            <v-menu location="bottom">
              <template #activator="{ props }">
                <v-btn
                  v-bind="props"
                  icon
                  size="small"
                  variant="text"
                  class="ml-2"
                >
                  <v-icon icon="mdi-dots-vertical"></v-icon>
                </v-btn>
              </template>
              <v-list>
                <v-list-item v-if="allowRefresh" @click="refreshData">
                  <v-list-item-title>
                    <v-icon icon="mdi-refresh" size="16" class="mr-2"></v-icon>
                    刷新
                  </v-list-item-title>
                </v-list-item>
              </v-list>
            </v-menu>
          </v-card-title>
          <v-card-text class="pa-2">
            <v-row class="text-center">
              <v-col cols="12" class="mb-2">
                <div class="text-caption text-grey-darken-1">目标目录媒体文件数</div>
                <div class="text-h5 font-weight-bold">{{ dashboardData.targetFilesCount }}</div>
              </v-col>
              <v-col cols="6">
                <div class="text-caption text-grey-darken-1">正在复制</div>
                <div class="text-h6 font-weight-bold text-orange">{{ dashboardData.copyingFilesCount }}</div>
              </v-col>
              <v-col cols="6">
                <div class="text-caption text-grey-darken-1">已完成</div>
                <div class="text-h6 font-weight-bold text-green">{{ dashboardData.completedFilesCount }}</div>
              </v-col>
            </v-row>
            <v-divider class="my-2"></v-divider>
            <div v-if="dashboardData.lastRunTime" class="text-xs text-grey-darken-1 text-center">
              最后运行：{{ new Date(dashboardData.lastRunTime).toLocaleString() }}
            </div>
            <div v-else class="text-xs text-grey-darken-1 text-center">
              尚未运行
            </div>
          </v-card-text>
          <!-- 只在悬停时显示拖拽图标 -->
          <div v-show="isHovering" class="absolute right-5 top-5">
            <v-icon class="cursor-move">mdi-drag</v-icon>
          </div>
        </v-card>
      </template>
    </v-hover>
  </div>
</template>