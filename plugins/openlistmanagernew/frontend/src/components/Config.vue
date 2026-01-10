<template>
  <div class="plugin-config" style="padding: 16px;">
    <!-- 页面标题和操作按钮 -->
    <div class="d-flex justify-space-between align-center mb-4">
      <h2>OpenList管理器新配置</h2>
      <div>
        <v-btn color="secondary" @click="notifySwitch">
          <v-icon class="mr-1">mdi-arrow-left</v-icon>
          返回状态页
        </v-btn>
      </div>
    </div>

    <!-- 配置表单 -->
    <v-card variant="outlined">
      <v-card-title>基本设置</v-card-title>
      <v-card-text>
        <v-form>
          <!-- 启用插件 -->
          <v-row class="mb-4">
            <v-col cols="12">
              <v-switch
                v-model="config.enabled"
                label="启用插件"
                color="primary"
              ></v-switch>
            </v-col>
          </v-row>

          <!-- OpenList配置 -->
          <v-row class="mb-4">
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="config.openlist_url"
                label="OpenList地址"
                placeholder="http://localhost:5244"
                prepend-icon="mdi-link"
                :disabled="config.use_moviepilot_config"
              ></v-text-field>
            </v-col>
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="config.openlist_token"
                label="OpenList令牌"
                type="password"
                placeholder="在OpenList后台获取"
                prepend-icon="mdi-key"
                :disabled="config.use_moviepilot_config"
              ></v-text-field>
            </v-col>
          </v-row>

          <!-- 使用MoviePilot配置 -->
          <v-row class="mb-4">
            <v-col cols="12">
              <v-switch
                v-model="config.use_moviepilot_config"
                label="使用MoviePilot的内置OpenList"
                color="primary"
              ></v-switch>
            </v-col>
          </v-row>

          <!-- 目录配对 -->
          <v-row class="mb-4">
            <v-col cols="12">
              <v-textarea
                v-model="config.directory_pairs"
                label="目录配对"
                placeholder="源目录1#目标目录1\n源目录2#目标目录2"
                rows="3"
                prepend-icon="mdi-folder-network"
                hint="每行一组配对，使用#分隔源目录和目标目录"
                persistent-hint
              ></v-textarea>
            </v-col>
          </v-row>

          <!-- 自定义后缀 -->
          <v-row class="mb-4">
            <v-col cols="12">
              <v-switch
                v-model="config.enable_custom_suffix"
                label="启用自定义后缀"
                color="primary"
              ></v-switch>
            </v-col>
          </v-row>

          <!-- 执行周期 -->
          <v-row class="mb-4">
            <v-col cols="12" sm="6">
              <v-text-field
                v-model="config.cron"
                label="执行周期"
                placeholder="30 3 * * *"
                prepend-icon="mdi-clock-outline"
                hint="Cron表达式，默认每天凌晨3点30分执行"
                persistent-hint
              ></v-text-field>
            </v-col>
            <v-col cols="12" sm="6">
              <v-switch
                v-model="config.enable_wechat_notify"
                label="启用微信通知"
                color="primary"
              ></v-switch>
            </v-col>
          </v-row>

          <!-- 立即运行和清理缓存 -->
          <v-row class="mb-4">
            <v-col cols="12" sm="6">
              <v-switch
                v-model="config.onlyonce"
                label="立即运行复制任务"
                color="success"
              ></v-switch>
            </v-col>
            <v-col cols="12" sm="6">
              <v-switch
                v-model="config.clear_cache"
                label="清理统计数据"
                color="warning"
              ></v-switch>
            </v-col>
          </v-row>

          <!-- 保存按钮 -->
          <div class="d-flex justify-end mt-6">
            <v-btn color="primary" @click="saveConfig" variant="elevated">
              <v-icon class="mr-1">mdi-content-save</v-icon>
              保存配置
            </v-btn>
          </div>
        </v-form>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'

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
const config = reactive({...props.initialConfig})

// 自定义事件，用于保存配置
const emit = defineEmits(['save', 'close', 'switch'])

// 保存配置
function saveConfig() {
  emit('save', config)
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