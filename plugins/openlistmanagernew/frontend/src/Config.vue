<template>
  <div class="openlist-manager-config">
    <h1>OpenList 管理器新 - 配置</h1>
    <div class="config-form">
      <div class="form-group">
        <label>启用插件</label>
        <input type="checkbox" v-model="config.enabled">
      </div>
      
      <div class="form-group">
        <label>使用 MoviePilot 配置</label>
        <input type="checkbox" v-model="config.use_moviepilot_config">
      </div>
      
      <div v-if="!config.use_moviepilot_config" class="form-group">
        <label>OpenList URL</label>
        <input type="text" v-model="config.openlist_url" placeholder="http://example.com">
      </div>
      
      <div v-if="!config.use_moviepilot_config" class="form-group">
        <label>OpenList Token</label>
        <input type="text" v-model="config.openlist_token" placeholder="Your Token">
      </div>
      
      <div class="form-group">
        <label>目录对配置</label>
        <textarea 
          v-model="config.directory_pairs" 
          placeholder="源目录1,目标目录1\n源目录2,目标目录2" 
          rows="5"
        ></textarea>
        <small>格式：每行一个目录对，源目录和目标目录用逗号分隔</small>
      </div>
      
      <div class="form-group">
        <label>启用自定义后缀</label>
        <input type="checkbox" v-model="config.enable_custom_suffix">
      </div>
      
      <div class="form-group">
        <label>定时任务 (Cron)</label>
        <input type="text" v-model="config.cron" placeholder="30 3 * * *">
        <small>默认：每天凌晨3:30执行</small>
      </div>
      
      <div class="form-group">
        <label>启用微信通知</label>
        <input type="checkbox" v-model="config.enable_wechat_notify">
      </div>
      
      <div class="form-group">
        <label>立即执行一次</label>
        <input type="checkbox" v-model="config.onlyonce">
      </div>
      
      <div class="form-group">
        <label>清空插件数据</label>
        <input type="checkbox" v-model="config.clear_cache">
        <small>会清除所有复制记录和状态数据</small>
      </div>
      
      <div class="form-actions">
        <button class="save-button" @click="saveConfig">保存配置</button>
        <button class="cancel-button" @click="cancelConfig">取消</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface Config {
  enabled: boolean
  onlyonce: boolean
  clear_cache: boolean
  openlist_url: string
  openlist_token: string
  directory_pairs: string
  enable_custom_suffix: boolean
  use_moviepilot_config: boolean
  enable_wechat_notify: boolean
  cron: string
}

const config = ref<Config>({
  enabled: false,
  onlyonce: false,
  clear_cache: false,
  openlist_url: '',
  openlist_token: '',
  directory_pairs: '',
  enable_custom_suffix: false,
  use_moviepilot_config: true,
  enable_wechat_notify: false,
  cron: '30 3 * * *'
})

// 保存配置
const saveConfig = async () => {
  try {
    // 这里模拟保存配置，实际会由插件系统处理
    console.log('保存配置:', config.value)
    // 触发保存事件，由插件系统处理
    if (window.parent && window.parent.__plugin_save_config__) {
      window.parent.__plugin_save_config__(config.value)
    }
  } catch (error) {
    console.error('保存配置失败:', error)
  }
}

// 取消配置
const cancelConfig = () => {
  // 触发取消事件，由插件系统处理
  if (window.parent && window.parent.__plugin_cancel_config__) {
    window.parent.__plugin_cancel_config__()
  }
}

// 初始化配置
onMounted(() => {
  // 从插件系统获取初始配置
  if (window.parent && window.parent.__plugin_get_config__) {
    const initialConfig = window.parent.__plugin_get_config__()
    if (initialConfig) {
      config.value = { ...config.value, ...initialConfig }
    }
  }
})
</script>

<style scoped>
.openlist-manager-config {
  padding: 20px;
  font-family: Arial, sans-serif;
}

h1 {
  color: #333;
  margin-bottom: 20px;
}

.config-form {
  max-width: 600px;
}

.form-group {
  margin-bottom: 20px;
}

label {
  display: block;
  margin-bottom: 8px;
  font-weight: bold;
  color: #666;
}

input[type="text"],
textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid #ddd;
  border-radius: 4px;
  font-size: 14px;
  box-sizing: border-box;
}

textarea {
  resize: vertical;
}

input[type="checkbox"] {
  margin-right: 8px;
  transform: scale(1.2);
}

.form-group small {
  display: block;
  margin-top: 5px;
  color: #999;
  font-size: 12px;
}

.form-actions {
  margin-top: 30px;
  display: flex;
  gap: 10px;
}

.save-button {
  background: #42b983;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
}

.cancel-button {
  background: #f5f5f5;
  color: #333;
  border: 1px solid #ddd;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 16px;
}
</style>