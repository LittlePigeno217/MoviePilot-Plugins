<script setup>
/**
 * 115 扫码登录。轮询 /check-login，成功后由调用方重新拉取配置拿到 Cookie。
 */
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { pluginGet, pluginPost } from '../../plugin.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  api: { type: [Object, Function], default: null },
})
const emit = defineEmits(['update:modelValue', 'authenticated', 'error'])

const clients = [
  { label: '支付宝', value: 'alipaymini' },
  { label: '微信', value: 'wechatmini' },
  { label: '安卓', value: '115android' },
  { label: 'iOS', value: '115ios' },
  { label: '网页', value: 'web' },
  { label: 'PAD', value: '115ipad' },
  { label: 'TV', value: 'tv' },
]

const state = reactive({ loading: false, failed: '', code: '', client: 'alipaymini', step: '等待扫码' })
const timer = ref(null)
const activeClient = computed(() => clients.find(item => item.value === state.client) || clients[0])

function stopPolling() {
  if (timer.value) {
    clearInterval(timer.value)
    timer.value = null
  }
}

async function poll() {
  try {
    const data = await pluginGet(props.api, '/check-login')
    const code = Number(data.status)
    if (code === 2) {
      stopPolling()
      state.step = '登录成功'
      emit('authenticated')
      emit('update:modelValue', false)
    } else if (code === 1) {
      state.step = '已扫码，请在设备上确认'
    } else if (code === -1 || code === -2) {
      stopPolling()
      state.failed = data.tip || (code === -1 ? '二维码已过期，请刷新' : '登录已取消')
    } else {
      state.step = data.tip || '等待扫码'
    }
  } catch (error) {
    stopPolling()
    state.failed = error?.message || '登录状态检查失败'
  }
}

async function issue() {
  stopPolling()
  state.loading = true
  state.failed = ''
  state.code = ''
  state.step = '正在获取二维码'
  try {
    const result = await pluginPost(props.api, '/qrcode', { client_type: state.client })
    if (!result.success || !result.data?.qrcode) throw new Error(result.message || '115 未返回二维码')
    state.code = result.data.qrcode
    state.client = result.data.client_type || state.client
    state.step = '等待扫码'
    timer.value = window.setInterval(poll, 3000)
  } catch (error) {
    state.failed = error?.message || '获取二维码失败'
    emit('error', state.failed)
  } finally {
    state.loading = false
  }
}

async function useClient(value) {
  if (value === state.client) return
  state.client = value
  await issue()
}

watch(
  () => props.modelValue,
  async open => {
    if (open) await issue()
    else stopPolling()
  },
)
onBeforeUnmount(stopPolling)
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="420"
    @update:model-value="value => emit('update:modelValue', value)"
  >
    <v-card class="qr p115-portal">
      <div class="qr__head">
        <div>
          <div class="p115-endpoint-tag">115 授权</div>
          <h2 class="qr__title">扫码登录</h2>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="关闭" @click="emit('update:modelValue', false)" />
      </div>

      <v-card-text class="qr__body">
        <div class="qr__clients" role="group" aria-label="选择扫码客户端">
          <v-btn
            v-for="client in clients"
            :key="client.value"
            size="x-small"
            :variant="state.client === client.value ? 'flat' : 'outlined'"
            :color="state.client === client.value ? 'primary' : undefined"
            @click="useClient(client.value)"
          >
            {{ client.label }}
          </v-btn>
        </div>

        <div class="qr__stage">
          <div v-if="state.loading" class="qr__pending">
            <v-progress-circular indeterminate color="primary" size="34" />
          </div>
          <img v-else-if="state.code" :src="state.code" alt="115 登录二维码" class="qr__code" />
          <div v-else class="qr__pending p115-muted">二维码不可用</div>
        </div>

        <p v-if="state.failed" class="qr__failed">{{ state.failed }}</p>
        <p v-else class="qr__step">用 {{ activeClient.label }} 扫描 · {{ state.step }}</p>
      </v-card-text>

      <div class="qr__foot">
        <v-btn variant="text" size="small" prepend-icon="mdi-refresh" :disabled="state.loading" @click="issue">
          换一张
        </v-btn>
        <v-btn variant="text" size="small" @click="emit('update:modelValue', false)">关闭</v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped lang="scss">
.qr {
  background: rgb(var(--v-theme-surface));
}

.qr__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 12px 12px 18px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.qr__title {
  margin: 2px 0 0;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.qr__body {
  padding: 16px 18px 8px;
}

.qr__clients {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
  margin-bottom: 16px;
}

.qr__stage {
  display: grid;
  place-items: center;
  min-height: 196px;
  padding: 11px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  background: rgb(var(--v-theme-background));
}

// 二维码必须在白底上才扫得动，深色主题下也不能反色
.qr__code {
  inline-size: 174px;
  block-size: 174px;
  image-rendering: pixelated;
  background: #fff;
  padding: 6px;
  border-radius: 4px;
}

.qr__pending {
  display: grid;
  place-items: center;
  min-height: 174px;
  font-size: 13px;
}

.qr__step,
.qr__failed {
  margin: 12px 0 0;
  text-align: center;
  font-size: 13px;
}

.qr__step {
  color: rgba(var(--v-theme-on-surface), var(--v-medium-emphasis-opacity, 0.6));
}

.qr__failed {
  color: rgb(var(--v-theme-error));
}

.qr__foot {
  display: flex;
  justify-content: space-between;
  padding: 8px 12px 12px;
}
</style>
