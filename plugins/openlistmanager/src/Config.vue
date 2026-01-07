<template>
  <v-form ref="formRef">
    <v-card variant="outlined" class="mb-3" style="border-radius: 8px;">
      <v-card-text class="pa-3">
        <div class="d-flex align-center mb-3">
          <v-avatar color="primary" size="32" class="mr-2">
            <v-icon icon="mdi-cog" size="20"></v-icon>
          </v-avatar>
          <div>
            <div class="text-subtitle-1 font-weight-bold">基本设置</div>
            <div class="text-caption text-grey-darken-1">配置插件的基本运行参数</div>
          </div>
        </div>

        <v-row>
          <v-col cols="12" sm="6" md="3">
            <v-switch
              v-model="config.enabled"
              label="启动插件"
              color="primary"
              hide-details="auto"
            ></v-switch>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-switch
              v-model="config.enable_custom_suffix"
              label="刮削文件"
              color="primary"
              hint="额外复制字幕(.srt,.ass)、元数据(.nfo)、封面图(.jpg,.png)文件"
              persistent-hint
            ></v-switch>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-switch
              v-model="config.onlyonce"
              label="立即运行复制任务"
              color="success"
              hide-details="auto"
            ></v-switch>
          </v-col>
          <v-col cols="12" sm="6" md="3">
            <v-switch
              v-model="config.clear_cache"
              label="清理统计"
              color="warning"
              hide-details="auto"
            ></v-switch>
          </v-col>
        </v-row>

        <v-divider class="my-3"></v-divider>

        <v-row>
          <v-col cols="12" sm="4">
            <v-switch
              v-model="config.enable_wechat_notify"
              label="发送通知"
              color="primary"
              hint="当有复制任务时发送企业微信卡片通知"
              persistent-hint
            ></v-switch>
          </v-col>
          <v-col cols="12" sm="4">
            <v-switch
              v-model="config.use_moviepilot_config"
              label="使用MoviePilot的内置OpenList"
              color="primary"
              hint="使用MoviePilot中已配置的OpenList实例"
              persistent-hint
              :disabled="!openlistAvailable"
            ></v-switch>
          </v-col>
          <v-col cols="12" sm="4">
            <v-text-field
              v-model="config.cron"
              label="执行周期"
              placeholder="0 2 * * *"
              hint="Cron表达式，默认每天凌晨2点执行复制任务"
              persistent-hint
              prepend-icon="mdi-clock-outline"
            ></v-text-field>
          </v-col>
        </v-row>

        <v-divider class="my-3"></v-divider>

        <v-row>
          <v-col cols="12" sm="6">
            <v-text-field
              v-model="config.openlist_url"
              label="OpenList地址"
              placeholder="http://localhost:5244"
              hint="请输入完整的OpenList服务地址，如果使用MoviePilot配置则此项可留空"
              persistent-hint
              prepend-icon="mdi-link"
              :disabled="config.use_moviepilot_config && openlistAvailable"
            ></v-text-field>
          </v-col>
          <v-col cols="12" sm="6">
            <v-text-field
              v-model="config.openlist_token"
              label="OpenList令牌"
              type="password"
              placeholder="在OpenList后台获取"
              hint="在OpenList管理后台的'设置'-'全局'中获取令牌，如果使用MoviePilot配置则此项可留空"
              persistent-hint
              prepend-icon="mdi-key"
              :disabled="config.use_moviepilot_config && openlistAvailable"
            ></v-text-field>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card variant="outlined" class="mb-3" style="border-radius: 8px;">
      <v-card-text class="pa-3">
        <div class="d-flex align-center mb-3">
          <v-avatar color="primary" size="32" class="mr-2">
            <v-icon icon="mdi-folder-multiple" size="20"></v-icon>
          </v-avatar>
          <div>
            <div class="text-subtitle-1 font-weight-bold">目录配对设置</div>
            <div class="text-caption text-grey-darken-1">配置源目录和目标目录的映射关系</div>
          </div>
        </div>

        <v-row>
          <v-col cols="12">
            <v-textarea
              v-model="config.directory_pairs"
              label="目录配对"
              placeholder="源目录1#目标目录1&#10;源目录2#目标目录2"
              rows="3"
              hint="每行一组配对，使用#分隔源目录和目标目录"
              persistent-hint
              prepend-icon="mdi-folder-network"
            ></v-textarea>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>

    <v-card variant="outlined" class="mt-3" style="border-radius: 8px;">
      <v-card-text class="pa-3">
        <div class="d-flex align-center mb-3">
          <v-avatar color="info" size="32" class="mr-2">
            <v-icon icon="mdi-information" size="20"></v-icon>
          </v-avatar>
          <div>
            <div class="text-subtitle-1 font-weight-bold">使用说明</div>
            <div class="text-caption text-grey-darken-1">插件功能介绍和注意事项</div>
          </div>
        </div>

        <v-row>
          <v-col cols="12">
            <div class="text-body-2 mb-2">
              <strong>功能特点：</strong>
            </div>
            <ul class="text-body-2 mb-3" style="padding-left: 20px;">
              <li>支持多目录配对，自动将源目录的媒体文件复制到目标目录</li>
              <li>智能检测，只复制目标目录中不存在的文件，避免重复</li>
              <li>支持定时任务和手动触发两种执行方式</li>
              <li>支持刮削文件（字幕、元数据、封面图）的复制</li>
              <li>支持企业微信通知，及时了解复制任务执行情况</li>
              <li>支持使用MoviePilot内置的OpenList配置</li>
            </ul>

            <div class="text-body-2 mb-2">
              <strong>注意事项：</strong>
            </div>
            <ul class="text-body-2 mb-3" style="padding-left: 20px;">
              <li>确保OpenList服务正常运行，地址和令牌配置正确</li>
              <li>源目录和目标目录必须在OpenList中正确配置</li>
              <li>复制操作不会删除源目录中的文件</li>
              <li>清理统计功能会清空所有已复制文件的记录，请谨慎使用</li>
              <li>建议在非高峰期执行定时任务，避免影响系统性能</li>
            </ul>

            <div class="text-body-2 mb-2">
              <strong>目录配对格式：</strong>
            </div>
            <div class="text-body-2 mb-2" style="padding-left: 20px;">
              每行一组配对，使用#分隔源目录和目标目录，例如：
            </div>
            <div class="text-body-2 mb-3" style="padding-left: 20px; background: #f5f5f5; padding: 10px; border-radius: 4px;">
              /电影/源目录#/电影/目标目录<br>
              /电视剧/源目录#/电视剧/目标目录
            </div>

            <div class="text-body-2 mb-2">
              <strong>Cron表达式示例：</strong>
            </div>
            <ul class="text-body-2" style="padding-left: 20px;">
              <li>0 2 * * * - 每天凌晨2点执行</li>
              <li>0 */6 * * * - 每6小时执行一次</li>
              <li>0 0 * * 0 - 每周日午夜执行</li>
            </ul>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>
  </v-form>
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

onMounted(() => {
  if (props.initialConfig) {
    Object.assign(config, props.initialConfig)
  }
})

watch(config, (newConfig) => {
  emit('update:config', newConfig)
}, { deep: true })

defineExpose({
  config,
  formRef
})
</script>

<style scoped>
.v-card {
  transition: all 0.3s ease;
}

.v-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
</style>
