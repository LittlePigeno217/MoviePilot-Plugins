<script setup>
import { computed, reactive, watch } from 'vue'

const props = defineProps({
  initialConfig: {
    type: Object,
    default: () => ({}),
  },
  api: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['save', 'close', 'switch'])

const defaultConfig = {
  enabled: false,
  notify: true,
  message: 'Hello MoviePilot',
}

const config = reactive({ ...defaultConfig, ...(props.initialConfig || {}) })

watch(
  () => props.initialConfig,
  (value) => {
    Object.assign(config, defaultConfig, value || {})
  },
  { deep: true }
)

function saveConfig() {
  emit('save', { ...config })
}

function resetConfig() {
  Object.assign(config, defaultConfig, props.initialConfig || {})
}

const previewText = computed(() => config.message || 'Hello MoviePilot')
</script>

<template>
  <div class="template-config">
    <div class="template-config__header">
      <div>
        <div class="template-config__title">插件配置模板</div>
        <div class="template-config__subtitle">按你的业务替换字段和交互逻辑</div>
      </div>
      <v-btn-group variant="tonal" density="compact">
        <v-btn color="primary" @click="emit('switch')">状态页</v-btn>
        <v-btn color="primary" @click="resetConfig">重置</v-btn>
        <v-btn color="primary" @click="saveConfig">保存</v-btn>
        <v-btn color="primary" @click="emit('close')">
          <v-icon icon="mdi-close" />
        </v-btn>
      </v-btn-group>
    </div>

    <v-row>
      <v-col cols="12" md="6">
        <v-card variant="outlined">
          <v-card-title>基础配置</v-card-title>
          <v-card-text>
            <v-switch v-model="config.enabled" color="primary" label="启用插件" inset />
            <v-switch v-model="config.notify" color="primary" label="执行后发送通知" inset />
            <v-text-field
              v-model="config.message"
              label="展示文本"
              variant="outlined"
              prepend-inner-icon="mdi-message-text-outline"
              hint="可替换为你的业务配置项"
              persistent-hint
            />
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="6">
        <v-card variant="outlined">
          <v-card-title>预览说明</v-card-title>
          <v-card-text>
            <v-alert type="info" variant="tonal" class="mb-3">
              当前模板默认实现 `/config`、`/status`、`/run` 三个基础接口。
            </v-alert>
            <div class="text-subtitle-2 mb-2">当前预览文本</div>
            <div class="template-preview">{{ previewText }}</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<style scoped>
.template-config {
  padding: 16px;
}

.template-config__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.template-config__title {
  font-size: 20px;
  font-weight: 700;
}

.template-config__subtitle {
  color: #64748b;
  margin-top: 4px;
}

.template-preview {
  min-height: 88px;
  border: 1px dashed #cbd5e1;
  border-radius: 12px;
  padding: 16px;
  background: #f8fafc;
  color: #0f172a;
}
</style>
