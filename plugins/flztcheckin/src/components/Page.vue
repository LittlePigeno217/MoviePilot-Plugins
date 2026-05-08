<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { pluginRequest, statusColor } from '../utils/flzt'

const props = defineProps({
  api: { type: [Function, Object], default: null },
  initialConfig: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['switch', 'close', 'action'])

const loading = ref(false)
const running = ref(false)
const testing = ref(false)
const clearing = ref(false)
const snackbar = reactive({ show: false, text: '', type: 'success' })
const status = ref({
  enabled: false,
  configured: false,
  cron: '',
  email: '-',
  last_status: '未执行',
  last_run: '-',
  history: [],
  history_count: 0,
  next_run_time: '未配置定时任务',
  task_status: '未启用',
  last_result: null,
})

function showMessage(text, type = 'success') {
  snackbar.text = text
  snackbar.type = type
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
      showMessage('状态已刷新')
    }
  } catch (error) {
    showMessage(error?.message || '获取状态失败', 'error')
  } finally {
    loading.value = false
  }
}

async function runCheckin() {
  running.value = true
  try {
    const result = await pluginRequest(props.api, '/run', { method: 'POST', body: {} })
    if (!result?.success) {
      throw new Error(result?.message || '执行失败')
    }
    showMessage(result?.message || '执行成功')
    await loadStatus()
    emit('action')
  } catch (error) {
    showMessage(error?.message || '执行失败', 'error')
  } finally {
    running.value = false
  }
}

async function testLogin() {
  testing.value = true
  try {
    const result = await pluginRequest(props.api, '/test-login', { method: 'POST', body: {} })
    if (!result?.success) {
      throw new Error(result?.message || '测试失败')
    }
    showMessage(result?.message || '登录测试成功')
  } catch (error) {
    showMessage(error?.message || '登录测试失败', 'error')
  } finally {
    testing.value = false
  }
}

async function clearHistory() {
  clearing.value = true
  try {
    const result = await pluginRequest(props.api, '/history/clear', { method: 'POST', body: {} })
    if (!result?.success) {
      throw new Error(result?.message || '清空失败')
    }
    showMessage(result?.message || '已清空历史')
    await loadStatus()
  } catch (error) {
    showMessage(error?.message || '清空历史失败', 'error')
  } finally {
    clearing.value = false
  }
}

const statusChipColor = computed(() => statusColor(status.value.last_status))
const resultItems = computed(() => {
  const result = status.value.last_result || {}
  return [
    { label: '最近结果', value: result.status || status.value.last_status || '-' },
    { label: '返回消息', value: result.message || '-' },
    { label: '本次奖励', value: result.reward_mb ? `${result.reward_mb} MB` : '-' },
    { label: '累计流量', value: result.total_traffic || '-' },
  ]
})

onMounted(() => {
  loadStatus()
})
</script>

<template>
  <div class="flzt-page">
    <div class="flzt-page__hero">
      <div>
        <div class="flzt-page__title">FLZT 自动签到</div>
        <div class="flzt-page__subtitle">查看当前状态、手动签到、测试登录与管理历史记录</div>
      </div>
      <v-btn-group variant="tonal" density="comfortable">
        <v-btn color="primary" :loading="loading" @click="loadStatus(true)">
          <v-icon icon="mdi-refresh" class="mr-1" />刷新
        </v-btn>
        <v-btn color="primary" @click="emit('switch')">
          <v-icon icon="mdi-cog-outline" class="mr-1" />配置
        </v-btn>
        <v-btn color="primary" @click="emit('close')">
          <v-icon icon="mdi-close" />
        </v-btn>
      </v-btn-group>
    </div>

    <v-row>
      <v-col cols="12" lg="5">
        <v-card variant="outlined" class="mb-4">
          <v-card-title>运行概览</v-card-title>
          <v-card-text>
            <div class="overview-grid">
              <div class="overview-item">
                <div class="overview-item__label">插件状态</div>
                <v-chip :color="status.enabled ? 'success' : 'grey'" variant="tonal">
                  {{ status.enabled ? '已启用' : '未启用' }}
                </v-chip>
              </div>
              <div class="overview-item">
                <div class="overview-item__label">账号配置</div>
                <v-chip :color="status.configured ? 'success' : 'warning'" variant="tonal">
                  {{ status.configured ? '已配置' : '未配置' }}
                </v-chip>
              </div>
              <div class="overview-item">
                <div class="overview-item__label">签到账号</div>
                <div class="overview-item__value">{{ status.email || '-' }}</div>
              </div>
              <div class="overview-item">
                <div class="overview-item__label">最近状态</div>
                <v-chip :color="statusChipColor" variant="tonal">{{ status.last_status || '-' }}</v-chip>
              </div>
              <div class="overview-item">
                <div class="overview-item__label">最近执行</div>
                <div class="overview-item__value">{{ status.last_run || '-' }}</div>
              </div>
              <div class="overview-item">
                <div class="overview-item__label">下次执行</div>
                <div class="overview-item__value">{{ status.next_run_time || '-' }}</div>
              </div>
              <div class="overview-item">
                <div class="overview-item__label">任务状态</div>
                <div class="overview-item__value">{{ status.task_status || '-' }}</div>
              </div>
              <div class="overview-item">
                <div class="overview-item__label">Cron</div>
                <div class="overview-item__value">{{ status.cron || '-' }}</div>
              </div>
            </div>
          </v-card-text>
          <v-divider />
          <v-card-actions class="flex-wrap ga-2 pa-4">
            <v-btn color="success" :loading="running" @click="runCheckin">
              <v-icon icon="mdi-play-circle-outline" class="mr-1" />立即签到
            </v-btn>
            <v-btn color="info" variant="tonal" :loading="testing" @click="testLogin">
              <v-icon icon="mdi-shield-check-outline" class="mr-1" />测试登录
            </v-btn>
            <v-btn color="error" variant="tonal" :loading="clearing" @click="clearHistory">
              <v-icon icon="mdi-delete-sweep-outline" class="mr-1" />清空历史
            </v-btn>
          </v-card-actions>
        </v-card>

        <v-card variant="outlined">
          <v-card-title>最近结果</v-card-title>
          <v-card-text>
            <v-list lines="two" density="comfortable">
              <v-list-item v-for="item in resultItems" :key="item.label">
                <v-list-item-title>{{ item.label }}</v-list-item-title>
                <v-list-item-subtitle>{{ item.value }}</v-list-item-subtitle>
              </v-list-item>
            </v-list>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" lg="7">
        <v-card variant="outlined">
          <v-card-title class="d-flex align-center justify-space-between">
            <span>签到历史</span>
            <v-chip color="primary" variant="tonal">{{ status.history_count || 0 }} 条</v-chip>
          </v-card-title>
          <v-card-text>
            <v-table density="comfortable">
              <thead>
                <tr>
                  <th>时间</th>
                  <th>状态</th>
                  <th>奖励</th>
                  <th>累计流量</th>
                  <th>消息</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, index) in status.history || []" :key="`${item.time}-${index}`">
                  <td>{{ item.time }}</td>
                  <td>
                    <v-chip size="small" :color="statusColor(item.status)" variant="tonal">
                      {{ item.status }}
                    </v-chip>
                  </td>
                  <td>{{ item.reward_mb ? `${item.reward_mb} MB` : '-' }}</td>
                  <td>{{ item.total_traffic || '-' }}</td>
                  <td class="history-message">{{ item.message || '-' }}</td>
                </tr>
                <tr v-if="!(status.history || []).length">
                  <td colspan="5" class="text-center text-medium-emphasis py-6">暂无签到历史</td>
                </tr>
              </tbody>
            </v-table>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-snackbar v-model="snackbar.show" :color="snackbar.type" timeout="3000">
      {{ snackbar.text }}
    </v-snackbar>
  </div>
</template>

<style scoped>
.flzt-page {
  padding: 16px;
}

.flzt-page__hero {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.flzt-page__title {
  font-size: 24px;
  font-weight: 700;
  color: #0f172a;
}

.flzt-page__subtitle {
  color: #64748b;
  margin-top: 4px;
}

.overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.overview-item__label {
  font-size: 13px;
  color: #64748b;
  margin-bottom: 6px;
}

.overview-item__value {
  color: #0f172a;
  word-break: break-all;
}

.history-message {
  max-width: 320px;
  white-space: normal;
  word-break: break-word;
}

@media (max-width: 760px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
