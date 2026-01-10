<script setup lang="ts">
import { ref, onMounted } from 'vue'
// 自定义事件，用于通知主应用刷新数据
const emit = defineEmits(['action', 'switch', 'close'])

// 接收API对象
const props = defineProps({
  api: {
    type: Object,
    default: () => {}
  }
})

// 页面逻辑代码...
interface ActivityItem {
  action: string
  timestamp: string
}

const recentActivity = ref<ActivityItem[]>([])
const loading = ref(false)

const fetchRecentActivity = async () => {
  loading.value = true
  try {
    // 使用api模块调用插件接口
    recentActivity.value = await props.api.get(`plugin/OpenListManagerExtension/activity`)
  } catch (error) {
    console.error('获取活动记录失败:', error)
  } finally {
    loading.value = false
  }
}

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

// 组件挂载时获取数据
onMounted(() => {
  fetchRecentActivity()
})
</script>

<template>
  <div class="plugin-page">
    <!-- 插件详情页面操作按钮示例 -->
    <v-btn @click="notifyRefresh">刷新数据</v-btn>
    <v-btn @click="notifySwitch">配置插件</v-btn>
    <v-btn @click="notifyClose">关闭页面</v-btn>
    
    <v-card class="mt-4">
      <v-card-title>OpenList管理器扩展</v-card-title>
      <v-card-text>
        <v-progress-linear v-if="loading" indeterminate></v-progress-linear>
        <v-list v-else>
          <v-list-item v-for="(item, index) in recentActivity" :key="index">
            <v-list-item-title>{{ item.action }}</v-list-item-title>
            <v-list-item-subtitle>{{ item.timestamp }}</v-list-item-subtitle>
          </v-list-item>
        </v-list>
        <div v-if="!loading && recentActivity.length === 0" class="text-center text-muted">
          暂无活动记录
        </div>
      </v-card-text>
    </v-card>
  </div>
</template>

<style scoped>
.plugin-page {
  padding: 20px;
}
</style>