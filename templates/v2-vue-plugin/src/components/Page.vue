<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { pluginRequest } from '../utils/plugin'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  initialConfig: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['switch', 'close', 'action'])

const loading = ref(false)
const running = ref(false)
const snackbar = reactive({ show: false, text: '', color: 'success' })
const status = ref({
  enabled: false,
  notify: true,
  message: 'Hello MoviePilot',
  last_run: '-',
})

function toast(text, color = 'success') {
  snackbar.text = text
  snackbar.color = color
  snackbar.show = true
}

async function loadStatus(showSuccess = false) {
  loading.value = true
  try {
    const result = await pluginRequest(props.api, '/status')
    if (!result?.success) {
      throw new Error(result?.message || '获取状态失败')
    }
    status.value = result.data || status.value
    if (showSuccess) {
      toast('状态已刷新')
    }
  } catch (error) {
    toast(error?.message || '获取状态失败', 'error')
  } finally {
    loading.value = false
  }
}

async function runAction() {
  running.value = true
  try {
    const result = await pluginRequest(props.api, '/run', { method: 'POST', body: {} })
    if (!result?.success) {
      throw new Error(result?.message || '执行失败')
    }
    toast(result?.message || '执行成功')
    await loadStatus()
    emit('action')
  } catch (error) {
    toast(error?.message || '执行失败', 'error')
  } finally {
    running.value = false
  }
}

const statusColor = computed(() => (status.value.enabled ? 'success' : 'grey'))

onMounted(() => {
  loadStatus()
})
</script>

<template>
  <div class="template-page">
    <div class="template-page__header">
      <div>
        <div class="template-page__title">插件状态模板</div>
        <div class="template-page__subtitle">可在这里改造成业务概览、统计图、列表或控制台</div>
      </div>
      <v-btn-group variant="tonal" density="compact">
        <v-btn color="primary" :loading="loading" @click="loadStatus(true)">刷新</v-btn>
        <v-btn color="primary" @click="emit('switch')">配置</v-btn>
        <v-btn color="primary" @click="emit('close')">
          <v-icon icon="mdi-close" />
        </v-btn>
      </v-btn-group>
    </div>

    <v-row>
      <v-col cols="12" md="5">
        <v-card variant="outlined" class="mb-4">
          <v-card-title>运行状态</v-card-title>
          <v-card-text>
            <div class="status-grid">
              <div>
                <div class="status-label">插件状态</div>
                <v-chip :color="statusColor" variant="tonal">
                  {{ status.enabled ? '已启用' : '未启用' }}
                </v-chip>
              </div>
              <div>
                <div class="status-label">通知开关</div>
                <v-chip :color="status.notify ? 'success' : 'grey'" variant="tonal">
                  {{ status.notify ? '已开启' : '已关闭' }}
                </v-chip>
              </div>
              <div>
                <div class="status-label">最近执行时间</div>
                <div class="status-value">{{ status.last_run || '-' }}</div>
              </div>
            </div>
          </v-card-text>
          <v-divider />
          <v-card-actions class="pa-4">
            <v-btn color="success" :loading="running" @click="runAction">
              <v-icon icon="mdi-play-circle-outline" class="mr-1" />执行示例动作
            </v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" md="7">
        <v-card variant="outlined">
          <v-card-title>业务区域占位</v-card-title>
          <v-card-text>
            <v-alert type="info" variant="tonal" class="mb-3">
              将这里替换为你的业务内容，例如日志、任务表、图表、媒体列表等。
            </v-alert>
            <div class="placeholder-box">
              {{ status.message || 'Hello MoviePilot' }}
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-snackbar v-model="snackbar.show" :color="snackbar.color" timeout="3000">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.template-page {
  padding: 16px;
}

.template-page__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.template-page__title {
  font-size: 24px;
  font-weight: 700;
}

.template-page__subtitle {
  color: #64748b;
  margin-top: 4px;
}

.status-grid {
  display: grid;
  gap: 16px;
}

.status-label {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 6px;
}

.status-value {
  color: #0f172a;
}

.placeholder-box {
  min-height: 160px;
  border-radius: 16px;
  border: 1px dashed #cbd5e1;
  background: linear-gradient(135deg, #f8fafc 0%, #eef2ff 100%);
  color: #334155;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  text-align: center;
}
</style>
