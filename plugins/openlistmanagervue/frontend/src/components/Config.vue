<template>
  <div class="plugin-config">
    <v-card>
      <v-card-item>
        <v-card-title>OpenList管理器配置</v-card-title>
        <template #append>
          <v-btn icon color="primary" variant="text" @click="notifyClose">
            <v-icon>mdi-close</v-icon>
          </v-btn>
        </template>
      </v-card-item>
      <v-card-text class="overflow-y-auto">
        <v-alert v-if="error" type="error" class="mb-4">{{ error }}</v-alert>
        <v-alert v-if="success" type="success" class="mb-4">{{ success }}</v-alert>

        <v-form ref="form" v-model="isFormValid" @submit.prevent="saveConfig">
          <div class="text-subtitle-1 font-weight-bold mt-4 mb-2">基本设置</div>
          <v-row>
            <v-col cols="12" sm="6">
              <v-switch
                v-model="config.enabled"
                label="启用插件"
                color="primary"
                inset
                hint="启用插件后，将按计划执行复制任务"
                persistent-hint
              ></v-switch>
            </v-col>
            <v-col cols="12" sm="6">
              <v-switch
                v-model="config.enable_custom_suffix"
                label="刮削文件"
                color="primary"
                inset
                hint="额外复制字幕(.srt,.ass)、元数据(.nfo)、封面图(.jpg,.png)文件"
                persistent-hint
              ></v-switch>
            </v-col>
          </v-row>

          <v-divider class="my-4"></v-divider>

          <div class="text-subtitle-1 font-weight-bold mt-4 mb-2">OpenList配置</div>
          <v-row>
            <v-col cols="12">
              <v-switch
                v-model="config.use_moviepilot_config"
                label="使用MoviePilot的内置OpenList"
                color="primary"
                inset
                hint="使用MoviePilot中已配置的OpenList实例"
                persistent-hint
              ></v-switch>
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="config.openlist_url"
                label="OpenList地址"
                variant="outlined"
                hint="OpenList服务地址"
                :disabled="config.use_moviepilot_config"
                :rules="[v => !config.use_moviepilot_config && !v ? '请输入OpenList地址' : true]"
              ></v-text-field>
            </v-col>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="config.openlist_token"
                label="OpenList令牌"
                variant="outlined"
                hint="OpenList访问令牌"
                :disabled="config.use_moviepilot_config"
                :append-inner-icon="showToken ? 'mdi-eye-off' : 'mdi-eye'"
                :type="showToken ? 'text' : 'password'"
                @click:append-inner="showToken = !showToken"
              ></v-text-field>
            </v-col>
          </v-row>

          <v-divider class="my-4"></v-divider>

          <div class="text-subtitle-1 font-weight-bold mt-4 mb-2">目录配置</div>
          <v-row>
            <v-col cols="12">
              <v-textarea
                v-model="config.directory_pairs"
                label="目录对配置"
                variant="outlined"
                rows="6"
                hint="每行一个目录对，格式：源目录->目标目录"
                persistent-hint
                placeholder="/movies/source->/movies/target&#10;/tv/source->/tv/target"
              ></v-textarea>
            </v-col>
          </v-row>

          <v-divider class="my-4"></v-divider>

          <div class="text-subtitle-1 font-weight-bold mt-4 mb-2">任务配置</div>
          <v-row>
            <v-col cols="12" md="6">
              <v-text-field
                v-model="config.cron"
                label="定时任务"
                variant="outlined"
                hint="Cron表达式，例如：30 3 * * * 表示每天凌晨3:30执行"
                persistent-hint
              ></v-text-field>
            </v-col>
            <v-col cols="12" md="6">
              <v-switch
                v-model="config.enable_wechat_notify"
                label="发送通知"
                color="primary"
                inset
                hint="当有复制任务时发送企业微信卡片通知"
                persistent-hint
              ></v-switch>
            </v-col>
          </v-row>

          <v-expansion-panels variant="accordion" class="mt-4">
            <v-expansion-panel>
              <v-expansion-panel-title>操作选项</v-expansion-panel-title>
              <v-expansion-panel-text>
                <v-row>
                  <v-col cols="12" sm="6">
                    <v-switch
                      v-model="config.onlyonce"
                      label="立即运行复制任务"
                      color="success"
                      inset
                      hint="保存配置后立即执行一次复制任务"
                      persistent-hint
                    ></v-switch>
                  </v-col>
                  <v-col cols="12" sm="6">
                    <v-switch
                      v-model="config.clear_cache"
                      label="清理统计"
                      color="warning"
                      inset
                      hint="清空所有统计数据和复制记录"
                      persistent-hint
                    ></v-switch>
                  </v-col>
                </v-row>
              </v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
        </v-form>
      </v-card-text>
      <v-card-actions>
        <v-btn color="secondary" @click="resetForm">重置</v-btn>
        <v-spacer></v-spacer>
        <v-btn color="primary" :disabled="!isFormValid" @click="saveConfig" :loading="saving">保存配置</v-btn>
      </v-card-actions>
    </v-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'

const props = defineProps({
  initialConfig: {
    type: Object,
    default: () => ({}),
  },
  api: {
    type: Object,
    default: () => {},
  },
  plugin: {
    type: Object,
    default: () => {},
  },
})

const emit = defineEmits(['save', 'close', 'switch'])

const form = ref(null)
const isFormValid = ref(true)
const error = ref(null)
const success = ref(null)
const saving = ref(false)
const showToken = ref(false)

const defaultConfig = {
  enabled: false,
  openlist_url: '',
  openlist_token: '',
  directory_pairs: '',
  enable_custom_suffix: false,
  cron: '30 3 * * *',
  use_moviepilot_config: true,
  enable_wechat_notify: false,
  onlyonce: false,
  clear_cache: false,
}

const config = reactive({ ...defaultConfig })

watch(() => config.use_moviepilot_config, (newVal) => {
  if (newVal) {
    config.openlist_url = ''
    config.openlist_token = ''
  }
})

onMounted(() => {
  if (props.initialConfig) {
    Object.keys(props.initialConfig).forEach(key => {
      if (key in config) {
        config[key] = props.initialConfig[key]
      }
    })
  }
})

async function saveConfig() {
  if (!isFormValid.value) {
    error.value = '请修正表单错误'
    return
  }

  saving.value = true
  error.value = null
  success.value = null

  try {
    await props.api.put(`plugin/${props.plugin.id}/config`, { ...config })
    success.value = '配置保存成功'
    emit('save', { ...config })
    
    setTimeout(() => {
      success.value = null
    }, 3000)
  } catch (err) {
    console.error('保存配置失败:', err)
    error.value = err.message || '保存配置失败'
  } finally {
    saving.value = false
  }
}

function resetForm() {
  Object.keys(defaultConfig).forEach(key => {
    config[key] = defaultConfig[key]
  })

  if (form.value) {
    form.value.resetValidation()
  }
  error.value = null
  success.value = null
}

function notifyClose() {
  emit('close')
}
</script>
