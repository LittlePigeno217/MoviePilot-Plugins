<template>
  <div class="openlist-manager-dashboard">
    <h3>OpenList 管理器新</h3>
    <div class="dashboard-card">
      <div class="stat-item">
        <div class="stat-label">任务状态</div>
        <div class="stat-value">{{ status }}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">已复制文件</div>
        <div class="stat-value">{{ copiedFilesCount }}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">总文件数</div>
        <div class="stat-value">{{ totalFilesCount }}</div>
      </div>
      <div class="stat-item">
        <div class="stat-label">最近运行</div>
        <div class="stat-value">{{ lastRun }}</div>
      </div>
    </div>
    <button class="run-button" @click="runTask" :disabled="status === 'running'">
      {{ status === 'running' ? '运行中...' : '立即执行' }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const status = ref('idle')
const copiedFilesCount = ref(0)
const totalFilesCount = ref(0)
const lastRun = ref('从未运行')
const refreshInterval = ref<number | null>(null)

const fetchStatus = async () => {
  try {
    const response = await fetch('/api/v1/plugin/openlistmanagernew/status', {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
    })
    if (response.ok) {
      const data = await response.json()
      status.value = data.status.status
      copiedFilesCount.value = data.status.copied_files
      totalFilesCount.value = data.status.total_files
      
      if (data.status.last_run) {
        lastRun.value = new Date(data.status.last_run).toLocaleString()
      } else {
        lastRun.value = '从未运行'
      }
    }
  } catch (error) {
    console.error('获取仪表盘状态失败:', error)
  }
}

const runTask = async () => {
  try {
    const response = await fetch('/api/v1/plugin/openlistmanagernew/run', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
    })
    if (response.ok) {
      await fetchStatus()
    }
  } catch (error) {
    console.error('执行任务失败:', error)
  }
}

onMounted(() => {
  fetchStatus()
  refreshInterval.value = window.setInterval(fetchStatus, 5000)
})

onUnmounted(() => {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
  }
})
</script>

<style scoped>
.openlist-manager-dashboard {
  padding: 15px;
  font-family: Arial, sans-serif;
  background: #f5f5f5;
  border-radius: 8px;
}

h3 {
  margin: 0 0 15px 0;
  color: #333;
  font-size: 16px;
}

.dashboard-card {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 15px;
  margin-bottom: 15px;
}

.stat-item {
  background: white;
  padding: 10px;
  border-radius: 6px;
  text-align: center;
}

.stat-label {
  font-size: 12px;
  color: #666;
  margin-bottom: 5px;
}

.stat-value {
  font-size: 18px;
  font-weight: bold;
  color: #333;
}

.run-button {
  width: 100%;
  background: #42b983;
  color: white;
  border: none;
  padding: 8px 0;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
}

.run-button:disabled {
  background: #ccc;
  cursor: not-allowed;
}
</style>