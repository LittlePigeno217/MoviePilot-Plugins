<template>
  <v-card flat class="rounded border">
    <v-card-title class="text-subtitle-1 d-flex align-center px-3 py-2 bg-primary-lighten-5">
      <v-icon icon="mdi-cog" class="mr-2" color="primary" size="small"></v-icon>
      <span>OpenList管理器配置</span>
    </v-card-title>
    <v-card-text class="px-3 py-2">
      <v-alert v-if="error" type="error" density="compact" class="mb-2 text-caption" variant="tonal" closable>
        {{ error }}
      </v-alert>
      <v-alert v-if="successMessage" type="success" density="compact" class="mb-2 text-caption" variant="tonal" closable>
        {{ successMessage }}
      </v-alert>

      <v-form ref="formRef" v-model="isFormValid" @submit.prevent="saveFullConfig">
        <v-card flat class="rounded mb-3 border config-card">
          <v-card-title class="text-caption d-flex align-center px-3 py-2 bg-primary-lighten-5">
            <v-icon icon="mdi-tune" class="mr-2" color="primary" size="small"></v-icon>
            <span>基本设置</span>
          </v-card-title>
          <v-card-text class="px-3 py-2">
            <v-row>
              <v-col cols="12" md="6">
                <div class="d-flex align-center">
                  <v-icon icon="mdi-power" size="small" :color="config.enabled ? 'success' : 'grey'" class="mr-3"></v-icon>
                  <div>
                    <div class="text-subtitle-2">启用插件</div>
                    <div class="text-caption text-grey">是否启用OpenList文件复制功能</div>
                  </div>
                  <v-switch v-model="config.enabled" color="primary" inset density="compact" hide-details class="small-switch ml-auto"></v-switch>
                </div>
              </v-col>
              <v-col cols="12" md="6">
                <div class="d-flex align-center">
                  <v-icon icon="mdi-file-multiple" size="small" :color="config.enable_custom_suffix ? 'info' : 'grey'" class="mr-3"></v-icon>
                  <div>
                    <div class="text-subtitle-2">刮削文件</div>
                    <div class="text-caption text-grey">额外复制字幕、元数据、封面图文件</div>
                  </div>
                  <v-switch v-model="config.enable_custom_suffix" color="info" inset density="compact" hide-details class="small-switch ml-auto"></v-switch>
                </div>
              </v-col>
            </v-row>

            <v-divider class="my-2"></v-divider>

            <v-row>
              <v-col cols="12" md="6">
                <div class="d-flex align-center">
                  <v-icon icon="mdi-bell" size="small" :color="config.enable_wechat_notify ? 'warning' : 'grey'" class="mr-3"></v-icon>
                  <div>
                    <div class="text-subtitle-2">发送通知</div>
                    <div class="text-caption text-grey">当有复制任务时发送企业微信通知</div>
                  </div>
                  <v-switch v-model="config.enable_wechat_notify" color="warning" inset density="compact" hide-details class="small-switch ml-auto"></v-switch>
                </div>
              </v-col>
              <v-col cols="12" md="6">
                <div class="d-flex align-center">
                  <v-icon icon="mdi-link" size="small" :color="config.use_moviepilot_config ? 'success' : 'grey'" class="mr-3"></v-icon>
                  <div>
                    <div class="text-subtitle-2">使用MoviePilot配置</div>
                    <div class="text-caption text-grey">使用MoviePilot中已配置的OpenList实例</div>
                  </div>
                  <v-switch v-model="config.use_moviepilot_config" color="success" inset density="compact" hide-details :disabled="!openlistAvailable" class="small-switch ml-auto"></v-switch>
                </div>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>

        <v-card flat class="rounded mb-3 border config-card">
          <v-card-title class="text-caption d-flex align-center px-3 py-2 bg-primary-lighten-5">
            <v-icon icon="mdi-clock-time-five" class="mr-2" color="primary" size="small"></v-icon>
            <span>定时任务设置</span>
          </v-card-title>
          <v-card-text class="px-3 py-2">
            <v-text-field
              v-model="config.cron"
              label="CRON表达式"
              placeholder="0 2 * * *"
              hint="设置文件复制的执行周期，如：0 2 * * * (每天凌晨2点)"
              persistent-hint
              prepend-inner-icon="mdi-clock-outline"
              variant="outlined"
              density="compact"
              class="text-caption"
            ></v-text-field>
            <div class="text-caption mb-1">常用预设：</div>
            <div class="d-flex flex-wrap">
              <v-chip v-for="preset in cronPresets" :key="preset.value" class="ma-1" variant="flat" size="x-small" color="primary" @click="config.cron = preset.value">
                {{ preset.title }}
              </v-chip>
            </div>
          </v-card-text>
        </v-card>

        <v-card flat class="rounded mb-3 border config-card">
          <v-card-title class="text-caption d-flex align-center px-3 py-2 bg-primary-lighten-5">
            <v-icon icon="mdi-server-network" class="mr-2" color="primary" size="small"></v-icon>
            <span>OpenList配置</span>
          </v-card-title>
          <v-card-text class="px-3 py-2">
            <v-text-field
              v-model="config.openlist_url"
              label="OpenList地址"
              placeholder="http://localhost:5244"
              hint="请输入完整的OpenList服务地址"
              persistent-hint
              prepend-inner-icon="mdi-link"
              variant="outlined"
              density="compact"
              class="text-caption"
              :disabled="config.use_moviepilot_config && openlistAvailable"
            ></v-text-field>
            <v-text-field
              v-model="config.openlist_token"
              label="OpenList令牌"
              type="password"
              placeholder="在OpenList后台获取"
              hint="在OpenList管理后台的'设置'-'全局'中获取令牌"
              persistent-hint
              prepend-inner-icon="mdi-key"
              variant="outlined"
              density="compact"
              class="text-caption"
              :disabled="config.use_moviepilot_config && openlistAvailable"
            ></v-text-field>
          </v-card-text>
        </v-card>

        <v-card flat class="rounded mb-3 border config-card">
          <v-card-title class="text-caption d-flex align-center px-3 py-2 bg-primary-lighten-5">
            <v-icon icon="mdi-folder-network" class="mr-2" color="primary" size="small"></v-icon>
            <span>目录配对设置</span>
          </v-card-title>
          <v-card-text class="px-3 py-2">
            <v-textarea
              v-model="config.directory_pairs"
              label="目录配对"
              placeholder="源目录1#目标目录1&#10;源目录2#目标目录2"
              rows="3"
              hint="每行一组配对，使用#分隔源目录和目标目录"
              persistent-hint
              prepend-inner-icon="mdi-folder-network"
              variant="outlined"
              density="compact"
              class="text-caption"
            ></v-textarea>
          </v-card-text>
        </v-card>

        <v-card flat class="rounded mb-3 border config-card">
          <v-card-title class="text-caption d-flex align-center px-3 py-2 bg-primary-lighten-5">
            <v-icon icon="mdi-play-circle" class="mr-2" color="primary" size="small"></v-icon>
            <span>手动操作</span>
          </v-card-title>
          <v-card-text class="px-3 py-2">
            <v-row>
              <v-col cols="12" md="6">
                <div class="d-flex align-center">
                  <v-icon icon="mdi-play" size="small" :color="config.onlyonce ? 'success' : 'grey'" class="mr-3"></v-icon>
                  <div>
                    <div class="text-subtitle-2">立即运行</div>
                    <div class="text-caption text-grey">立即执行一次文件复制任务</div>
                  </div>
                  <v-switch v-model="config.onlyonce" color="success" inset density="compact" hide-details class="small-switch ml-auto"></v-switch>
                </div>
              </v-col>
              <v-col cols="12" md="6">
                <div class="d-flex align-center">
                  <v-icon icon="mdi-delete-sweep" size="small" :color="config.clear_cache ? 'error' : 'grey'" class="mr-3"></v-icon>
                  <div>
                    <div class="text-subtitle-2">清理统计</div>
                    <div class="text-caption text-grey">清空所有已复制文件的记录</div>
                  </div>
                  <v-switch v-model="config.clear_cache" color="error" inset density="compact" hide-details class="small-switch ml-auto"></v-switch>
                </div>
              </v-col>
            </v-row>
          </v-card-text>
        </v-card>

        <v-card-actions>
          <v-spacer></v-spacer>
          <v-btn color="primary" variant="elevated" size="small" :loading="saving" :disabled="!isFormValid" type="submit">
            <v-icon start icon="mdi-content-save"></v-icon>
            保存配置
          </v-btn>
        </v-card-actions>
      </v-form>
    </v-card-text>
  </v-card>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'

const props = defineProps({
  initialConfig: {
    type: Object,
    default: () => ({})
  },
  openlistAvailable: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:config'])

const formRef = ref(null)
const isFormValid = ref(false)
const saving = ref(false)
const error = ref('')
const successMessage = ref('')

const config = reactive({
  enabled: false,
  enable_custom_suffix: false,
  onlyonce: false,
  clear_cache: false,
  enable_wechat_notify: false,
  use_moviepilot_config: true,
  cron: '0 2 * * *',
  openlist_url: '',
  openlist_token: '',
  directory_pairs: ''
})

const cronPresets = [
  { title: '每天凌晨2点', value: '0 2 * * *' },
  { title: '每天凌晨3点', value: '0 3 * * *' },
  { title: '每6小时', value: '0 */6 * * *' },
  { title: '每天午夜', value: '0 0 * * *' },
  { title: '每周日午夜', value: '0 0 * * 0' }
]

onMounted(() => {
  if (props.initialConfig) {
    Object.assign(config, props.initialConfig)
  }
})

watch(config, (newConfig) => {
  emit('update:config', newConfig)
}, { deep: true })

const saveFullConfig = async () => {
  saving.value = true
  error.value = ''
  successMessage.value = ''
  
  try {
    const result = await props.api.config.post(config)
    if (result.success) {
      successMessage.value = result.message || '配置保存成功'
      setTimeout(() => {
        successMessage.value = ''
      }, 3000)
    } else {
      error.value = result.message || '配置保存失败'
    }
  } catch (err) {
    error.value = '保存配置时发生错误: ' + err.message
  } finally {
    saving.value = false
  }
}

defineExpose({
  config,
  formRef
})
</script>

<style scoped>
.config-card {
  border: 1px solid rgba(0, 0, 0, 0.12);
}

.small-switch {
  transform: scale(0.8);
  transform-origin: right center;
}
</style>
