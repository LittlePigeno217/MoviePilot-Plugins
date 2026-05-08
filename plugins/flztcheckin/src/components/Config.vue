<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { cloneConfig } from '../utils/flzt'

const props = defineProps({
  initialConfig: {
    type: Object,
    default: () => ({}),
  },
  api: {
    type: [Function, Object],
    default: null,
  },
})

const emit = defineEmits(['save', 'close', 'switch'])
const saving = ref(false)
const message = ref('')
const messageType = ref('success')

const defaultConfig = {
  enabled: false,
  notify: true,
  use_proxy: false,
  cron: '10 8 * * *',
  email: '',
  password: '',
  timeout: 10,
  retry_count: 3,
}

const config = reactive({ ...defaultConfig, ...cloneConfig(props.initialConfig) })

watch(
  () => props.initialConfig,
  (value) => {
    Object.assign(config, defaultConfig, cloneConfig(value))
  },
  { deep: true }
)

function resetConfig() {
  Object.assign(config, defaultConfig, cloneConfig(props.initialConfig))
  message.value = '已恢复为当前已保存配置'
  messageType.value = 'info'
}

async function saveConfig() {
  saving.value = true
  message.value = ''
  try {
    emit('save', { ...config })
    message.value = '配置已提交'
    messageType.value = 'success'
  } catch (error) {
    message.value = error?.message || '配置保存失败'
    messageType.value = 'error'
  } finally {
    saving.value = false
  }
}

const cronHint = computed(() => '示例：10 8 * * * 表示每天 08:10 自动执行签到')
</script>

<template>
  <div class="flzt-config">
    <div class="flzt-topbar">
      <div>
        <div class="flzt-topbar__title">FLZT 自动签到配置</div>
        <div class="flzt-topbar__subtitle">配置账号、定时策略和通知行为</div>
      </div>
      <v-btn-group variant="tonal" density="compact">
        <v-btn color="primary" @click="emit('switch')">
          <v-icon icon="mdi-view-dashboard-outline" class="mr-1" />
          状态页
        </v-btn>
        <v-btn color="primary" @click="resetConfig">
          <v-icon icon="mdi-restore" class="mr-1" />
          重置
        </v-btn>
        <v-btn color="primary" :loading="saving" @click="saveConfig">
          <v-icon icon="mdi-content-save-outline" class="mr-1" />
          保存
        </v-btn>
        <v-btn color="primary" @click="emit('close')">
          <v-icon icon="mdi-close" />
        </v-btn>
      </v-btn-group>
    </div>

    <v-alert
      v-if="message"
      :type="messageType"
      variant="tonal"
      density="comfortable"
      class="mb-4"
    >
      {{ message }}
    </v-alert>

    <v-row>
      <v-col cols="12" lg="6">
        <v-card class="h-100" variant="outlined">
          <v-card-title class="d-flex align-center">
            <v-icon icon="mdi-account-cog-outline" class="mr-2" color="primary" />
            基础与账号
          </v-card-title>
          <v-card-text>
            <v-switch v-model="config.enabled" color="primary" label="启用插件" inset />
            <v-switch v-model="config.notify" color="primary" label="执行后发送通知" inset />
            <v-switch v-model="config.use_proxy" color="primary" label="使用系统代理" inset />

            <v-text-field
              v-model="config.email"
              label="FLZT 邮箱"
              variant="outlined"
              prepend-inner-icon="mdi-email-outline"
              hint="填写 FLZT 登录邮箱"
              persistent-hint
            />
            <v-text-field
              v-model="config.password"
              label="FLZT 密码"
              variant="outlined"
              type="password"
              prepend-inner-icon="mdi-lock-outline"
              hint="保存后由 MoviePilot 后端用于登录签到"
              persistent-hint
            />
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" lg="6">
        <v-card class="h-100" variant="outlined">
          <v-card-title class="d-flex align-center">
            <v-icon icon="mdi-timer-cog-outline" class="mr-2" color="success" />
            调度与重试
          </v-card-title>
          <v-card-text>
            <v-text-field
              v-model="config.cron"
              label="Cron 表达式"
              variant="outlined"
              prepend-inner-icon="mdi-calendar-clock-outline"
              :hint="cronHint"
              persistent-hint
            />
            <v-text-field
              v-model.number="config.timeout"
              label="请求超时（秒）"
              type="number"
              variant="outlined"
              min="5"
              max="60"
              prepend-inner-icon="mdi-timer-sand"
            />
            <v-text-field
              v-model.number="config.retry_count"
              label="失败重试次数"
              type="number"
              variant="outlined"
              min="1"
              max="10"
              prepend-inner-icon="mdi-refresh-circle"
            />

            <v-alert type="info" variant="tonal" class="mt-2">
              插件流程：登录 `FLZT` → 调用 `/api/v1/user/checkIn` → 保存历史 → 可选发送通知。
            </v-alert>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<style scoped>
.flzt-config {
  padding: 16px;
}

.flzt-topbar {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.flzt-topbar__title {
  font-size: 20px;
  font-weight: 700;
  color: #0f172a;
}

.flzt-topbar__subtitle {
  color: #64748b;
  margin-top: 4px;
}
</style>
