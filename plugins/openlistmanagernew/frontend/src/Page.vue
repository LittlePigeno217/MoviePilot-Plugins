<template>
  <div class="openlist-manager-page">
    <h1>OpenList 管理器新</h1>
    <div class="status-section">
      <h2>任务状态</h2>
      <div class="status-card">
        <div class="status-item">
          <span class="label">状态：</span>
          <span class="value">{{ taskStatus.status }}</span>
        </div>
        <div class="status-item">
          <span class="label">进度：</span>
          <span class="value">{{ taskStatus.progress }}%</span>
        </div>
        <div class="status-item">
          <span class="label">总文件数：</span>
          <span class="value">{{ taskStatus.total_files }}</span>
        </div>
        <div class="status-item">
          <span class="label">已复制：</span>
          <span class="value">{{ taskStatus.copied_files }}</span>
        </div>
        <div class="status-item">
          <span class="label">跳过：</span>
          <span class="value">{{ taskStatus.skipped_files }}</span>
        </div>
        <div class="status-item">
          <span class="label">当前操作：</span>
          <span class="value">{{ taskStatus.message }}</span>
        </div>
      </div>
      <button 
        class="run-button" 
        @click="runTask" 
        :disabled="taskStatus.status === 'running'"
      >
        {{ taskStatus.status === 'running' ? '任务运行中...' : '立即执行任务' }}
      </button>
    </div>
    <div class="files-section">
      <h2>复制记录</h2>
      <div class="files-list">
        <div v-if="Object.keys(copiedFiles).length === 0" class="empty-message">
          暂无复制记录
        </div>
        <div v-else class="file-item" v-for="(file, key) in copiedFiles" :key="key">
          <span class="file-name">{{ file.name }}</span>
          <span class="file-status">{{ file.status }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

interface TaskStatus {
  status: string
  progress: number
  message: string
  last_run: string | null
  start_time: string | null
  end_time: string | null
  total_files: number
  copied_files: number
  skipped_files: number
  current_pair: string
  total_pairs: number
  completed_pairs: number
}

interface CopiedFile {
  name: string
  status: string
}

const taskStatus = ref<TaskStatus>({
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

const copiedFiles = ref<Record<string, CopiedFile>>({})
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
      taskStatus.value = data.status
      copiedFiles.value = data.copied_files
    }
  } catch (error) {
    console.error('获取状态失败:', error)
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
  refreshInterval.value = window.setInterval(fetchStatus, 3000)
})

onUnmounted(() => {
  if (refreshInterval.value) {
    clearInterval(refreshInterval.value)
  }
})
</script>

<style scoped>
.openlist-manager-page {
  padding: 20px;
  font-family: Arial, sans-serif;
}

h1 {
  color: #333;
  margin-bottom: 20px;
}

h2 {
  color: #555;
  margin: 20px 0 10px;
  font-size: 18px;
}

.status-section {
  margin-bottom: 30px;
}

.status-card {
  background: #f5f5f5;
  padding: 15px;
  border-radius: 8px;
  margin-bottom: 15px;
}

.status-item {
  margin: 10px 0;
  display: flex;
  justify-content: space-between;
}

.label {
  font-weight: bold;
  color: #666;
}

.value {
  color: #333;
}

.run-button {
  background: #42b983;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
}

.run-button:disabled {
  background: #ccc;
  cursor: not-allowed;
}

.files-section {
  margin-top: 30px;
}

.files-list {
  background: #f5f5f5;
  padding: 15px;
  border-radius: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.file-item {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid #eee;
}

.file-name {
  color: #333;
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-status {
  color: #666;
  font-size: 14px;
}

.empty-message {
  color: #999;
  text-align: center;
  padding: 20px;
}
</style>