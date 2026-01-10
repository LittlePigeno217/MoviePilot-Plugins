<script setup lang="ts">
import { ref, computed } from 'vue'

// 接收初始配置和API对象
const props = defineProps({
  initialConfig: {
    type: Object,
    default: () => ({})
  },
  api: {
    type: Object,
    default: () => {}
  }
})

// 配置数据
const config = ref({...props.initialConfig})

// 自定义事件，用于保存配置
const emit = defineEmits(['save', 'close', 'switch'])

// 计算属性：检查是否使用MoviePilot配置
const useMoviePilotConfig = computed(() => config.value.use_moviepilot_config)

// 保存配置
function saveConfig() {
  emit('save', config.value)
}

// 通知主应用切换到详情页面
function notifySwitch() {
  emit('switch')
}

// 通知主应用关闭当前页面
function notifyClose() {
  emit('close')
}
</script>

<template>
  <div class="plugin-config">
    <v-form>
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
                hint="额外复制字幕(.srt,.ass)、元数据(.nfo)、封面图(.jpg,.png)"
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
                :disabled="useMoviePilotConfig"
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
                :disabled="useMoviePilotConfig"
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
                placeholder="源目录1#目标目录1\n源目录2#目标目录2"
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
              <div class="text-subtitle-1 font-weight-bold">说明信息</div>
              <div class="text-caption text-grey-darken-1">插件使用说明和注意事项</div>
            </div>
          </div>
          <v-row>
            <v-col cols="12" md="6">
              <v-alert
                type="info"
                text="true"
                variant="tonal"
                class="mb-0"
                density="compact"
              >
                <div class="font-weight-bold mb-1">文件尾缀说明：</div>
                <div>• 默认：自动匹配常用视频格式（mp4, mkv, avi, mov等）</div>
                <div>• 勾选复制字幕/元数据/封面图：额外匹配字幕(.srt,.ass)、元数据(.nfo)、封面图(.jpg,.png)</div>
              </v-alert>
            </v-col>
            <v-col cols="12" md="6">
              <v-alert
                type="warning"
                text="true"
                variant="tonal"
                class="mb-0"
                density="compact"
              >
                <div class="font-weight-bold mb-1">清除缓存说明：</div>
                <div>• 勾选此选项后保存，将清空所有复制记录和任务状态</div>
                <div>• 插件将重新开始记录复制历史</div>
                <div>• 此操作不可逆，请谨慎使用</div>
              </v-alert>
            </v-col>
          </v-row>
        </v-card-text>
      </v-card>
      
      <v-row class="mt-4">
        <v-col cols="12" class="text-right">
          <v-btn color="primary" @click="saveConfig" class="mr-2">保存配置</v-btn>
          <v-btn color="primary" @click="notifySwitch" class="mr-2">切换到详情页面</v-btn>
          <v-btn color="primary" @click="notifyClose">关闭页面</v-btn>
        </v-col>
      </v-row>
    </v-form>
  </div>
</template>