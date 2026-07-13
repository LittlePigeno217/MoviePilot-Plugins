<script setup>
import { reactive, ref } from 'vue'
import { pluginRequest } from '../utils/plugin'

const props = defineProps({
  api: {
    type: Object,
    default: () => ({}),
  },
  config: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['update:config', 'toast'])

const loading = reactive({ qrcode: false, check: false })
const qrcodeImage = ref('')
const qrcodeText = ref('')

function update(key, value) {
  emit('update:config', { ...props.config, [key]: value })
}

async function generateQrcode() {
  loading.qrcode = true
  try {
    const result = await pluginRequest(props.api, '/qrcode', { method: 'POST' })
    if (!result?.success) throw new Error(result?.message || '生成二维码失败')
    qrcodeImage.value = result?.data?.qrcode || ''
    qrcodeText.value = result?.data?.codeContent || ''
    emit('toast', '二维码已生成，请用手机 115 APP 扫描')
  } catch (error) {
    emit('toast', error?.message || '生成二维码失败', 'error')
    qrcodeImage.value = ''
    qrcodeText.value = ''
  } finally {
    loading.qrcode = false
  }
}

async function checkLogin() {
  loading.check = true
  try {
    const result = await pluginRequest(props.api, '/check_login')
    if (!result?.success) throw new Error(result?.message || '登录未完成')
    emit('toast', result?.data?.tip || '登录状态已更新')
  } catch (error) {
    emit('toast', error?.message || '检查登录失败', 'error')
  } finally {
    loading.check = false
  }
}
</script>

<template>
  <section class="auth-panel">
    <div class="section-title">115 授权</div>
    <v-btn-toggle
      :model-value="config.auth_mode"
      mandatory
      color="#167A5B"
      variant="outlined"
      density="comfortable"
      @update:model-value="update('auth_mode', $event)"
    >
      <v-btn value="cookie"><v-icon icon="mdi-cookie-outline" class="mr-1" />Cookie</v-btn>
      <v-btn value="qrcode"><v-icon icon="mdi-qrcode-scan" class="mr-1" />扫码</v-btn>
    </v-btn-toggle>

    <v-textarea
      v-if="config.auth_mode === 'cookie'"
      :model-value="config.cookie"
      label="115 Cookie"
      variant="outlined"
      rows="4"
      auto-grow
      hide-details
      @update:model-value="update('cookie', $event)"
    />

    <div v-else class="qrcode-box">
      <div class="qrcode-actions">
        <v-btn color="#167A5B" variant="flat" :loading="loading.qrcode" @click="generateQrcode">
          <v-icon icon="mdi-qrcode-plus" class="mr-1" />生成二维码
        </v-btn>
        <v-btn color="#245B7A" variant="tonal" :loading="loading.check" @click="checkLogin">
          <v-icon icon="mdi-check-circle-outline" class="mr-1" />检查登录
        </v-btn>
      </div>

      <!-- 二维码图片显示 -->
      <div v-if="qrcodeImage" class="qrcode-image-container">
        <img :src="qrcodeImage" alt="115 登录二维码" class="qrcode-image" />
        <p class="qrcode-hint">用手机 115 APP 扫描上方二维码登录</p>
      </div>

      <!-- 二维码内容备用显示（用于调试或二维码显示失败） -->
      <v-textarea
        v-show="qrcodeText"
        v-model="qrcodeText"
        label="二维码内容（备用）"
        variant="outlined"
        rows="2"
        readonly
        hide-details
        density="compact"
        class="mt-2"
      />
    </div>
  </section>
</template>

<style scoped>
.auth-panel {
  display: grid;
  gap: 12px;
}

.section-title {
  font-weight: 700;
  color: #17201c;
  margin-bottom: 4px;
}

.qrcode-box {
  display: grid;
  gap: 10px;
}

.qrcode-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.qrcode-image-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border: 1px dashed #d9e0da;
  border-radius: 8px;
  background-color: #f5f7f6;
}

.qrcode-image {
  width: 200px;
  height: 200px;
  border: 2px solid #167A5B;
  border-radius: 4px;
  padding: 8px;
  background-color: white;
}

.qrcode-hint {
  color: #66736d;
  font-size: 13px;
  margin: 0;
  text-align: center;
}
</style>
