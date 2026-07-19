<script setup>
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { clone, normalizeConfig, pluginGet, pluginPost } from '../plugin.js'

const props = defineProps({
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: [Object, Function], default: null },
  saving: { type: Boolean, default: false },
})
const emit = defineEmits(['save', 'close', 'switch'])

const config = reactive(normalizeConfig())
const activeTab = ref('login')
const notice = ref('')
const noticeColor = ref('info')
const redirectModes = [
  { title: 'Cookie', value: 'cookie' },
  { title: 'Open API', value: 'open' },
]
const qrClients = [
  { label: '支付宝', value: 'alipaymini' },
  { label: '微信', value: 'wechatmini' },
  { label: '安卓', value: '115android' },
  { label: 'iOS', value: '115ios' },
  { label: '网页', value: 'web' },
  { label: 'PAD', value: '115ipad' },
  { label: 'TV', value: 'tv' },
]
const qrDialog = reactive({ open: false, loading: false, error: '', code: '', clientType: 'alipaymini', status: '等待扫码', timer: null })
const picker = reactive({ open: false, type: '', index: -1, cid: '0', path: '', localBase: '', roots: [], remoteTrail: [], items: [] })
const pickerTitle = computed(() => ({ strm_source: '选择 115 源目录', upload_target: '选择 115 上传目录', strm_target: '选择本地 STRM 目录', upload_source: '选择本地上传目录', upload_strm_target: '选择上传 STRM 输出目录' }[picker.type] || '选择目录'))
const isRemotePicker = computed(() => ['strm_source', 'upload_target'].includes(picker.type))
const connectionReady = computed(() => Boolean(String(config.cookie || '').trim()))
const selectedQrClient = computed(() => qrClients.find(item => item.value === qrDialog.clientType) || qrClients[0])

function applyConfig(value = {}) {
  Object.assign(config, normalizeConfig(value))
}

function tell(text, color = 'info') {
  notice.value = text
  noticeColor.value = color
}

async function save() {
  if (!props.api) {
    emit('save', clone(config))
    return
  }
  try {
    const result = await pluginPost(props.api, '/config', clone(config))
    tell(result.message || '配置已保存', result.success ? 'success' : 'error')
    if (result.success) emit('save', clone(config))
  } catch (error) {
    tell(error?.message || '保存失败', 'error')
  }
}

function addStrmMapping() {
  config.strm_mappings.push({ id: crypto.randomUUID?.() || String(Date.now()), enabled: true, source_cid: '', source_path: '', target_dir: '' })
}

function useCurrentMoviePilotAddress() {
  const origin = globalThis.location?.origin
  if (!origin) return tell('无法识别当前站点地址', 'error')
  config.moviepilot_address = origin
  tell('已使用当前站点地址', 'success')
}

function addUploadMapping() {
  config.upload_mappings.push({ enabled: true, source: '', target: '', strm_target: '' })
}

function remove(items, index) {
  items.splice(index, 1)
}

function clearQrPoll() {
  if (qrDialog.timer) {
    clearInterval(qrDialog.timer)
    qrDialog.timer = null
  }
}

async function pollQrLogin() {
  try {
    const data = await pluginGet(props.api, '/check-login')
    const status = Number(data.status)
    if (status === 2) {
      clearQrPoll()
      qrDialog.status = '登录成功'
      applyConfig(await pluginGet(props.api, '/config'))
      tell('115 登录成功，Cookie 已保存', 'success')
    } else if (status === 1) {
      qrDialog.status = '已扫码，请在设备上确认'
    } else if (status === -1 || status === -2) {
      clearQrPoll()
      qrDialog.status = status === -1 ? '二维码已过期' : '已取消登录'
      qrDialog.error = data.tip || qrDialog.status
    } else {
      qrDialog.status = data.tip || '等待扫码'
    }
  } catch (error) {
    clearQrPoll()
    qrDialog.error = error?.message || '登录状态检查失败'
  }
}

async function refreshQrCode() {
  clearQrPoll()
  qrDialog.loading = true
  qrDialog.error = ''
  qrDialog.code = ''
  qrDialog.status = '正在获取二维码'
  try {
    const result = await pluginPost(props.api, '/qrcode', { client_type: qrDialog.clientType })
    if (!result.success || !result.data?.qrcode) throw new Error(result.message || '115 未返回二维码')
    qrDialog.code = result.data.qrcode
    qrDialog.clientType = result.data.client_type || qrDialog.clientType
    qrDialog.status = '等待扫码'
    qrDialog.timer = window.setInterval(pollQrLogin, 3000)
  } catch (error) {
    qrDialog.error = error?.message || '获取二维码失败'
  } finally {
    qrDialog.loading = false
  }
}

async function openQrDialog() {
  qrDialog.open = true
  await refreshQrCode()
}

function closeQrDialog() {
  clearQrPoll()
  qrDialog.open = false
}

async function selectQrClient(clientType) {
  if (clientType === qrDialog.clientType) return
  qrDialog.clientType = clientType
  await refreshQrCode()
}

async function openPicker(type, index) {
  Object.assign(picker, { open: true, type, index, cid: '0', path: '', localBase: '', roots: [], remoteTrail: [], items: [] })
  await browsePicker()
}

async function browsePicker(next) {
  try {
    if (isRemotePicker.value) {
      if (next) {
        picker.remoteTrail.push({ cid: picker.cid, name: next.name })
        picker.cid = next.cid
      }
      const data = await pluginGet(props.api, '/browse-115', { cid: picker.cid })
      picker.items = data.items || []
    } else {
      if (next) picker.path = next.path
      const data = await pluginGet(props.api, '/browse-local', { path: picker.path, root: picker.localBase })
      picker.localBase = data.base || picker.localBase
      picker.roots = data.roots || picker.roots
      picker.path = data.current || ''
      picker.items = data.items || []
    }
  } catch (error) {
    tell(error?.message || '目录读取失败', 'error')
  }
}

async function switchLocalRoot(root) {
  picker.localBase = root || ''
  picker.path = ''
  await browsePicker()
}

async function pickerBack() {
  if (isRemotePicker.value) {
    const previous = picker.remoteTrail.pop()
    if (!previous) return
    picker.cid = previous.cid
  } else if (picker.path) {
    picker.path = picker.path.split('/').slice(0, -1).join('/')
  } else {
    return
  }
  await browsePicker()
}

function selectPicker() {
  const localPath = picker.path ? `${picker.localBase.replace(/[\\/]+$/, '')}/${picker.path}` : picker.localBase
  if (picker.type === 'strm_source') {
    const mapping = config.strm_mappings[picker.index]
    mapping.source_cid = picker.cid
    mapping.source_path = `/${picker.remoteTrail.map(item => item.name).join('/')}`.replace(/\/$/, '') || '/'
  } else if (picker.type === 'upload_target') {
    config.upload_mappings[picker.index].target = `/${picker.remoteTrail.map(item => item.name).join('/')}`.replace(/\/$/, '') || '/'
  } else if (picker.type === 'strm_target') {
    config.strm_mappings[picker.index].target_dir = localPath
  } else if (picker.type === 'upload_source') {
    config.upload_mappings[picker.index].source = localPath
  } else if (picker.type === 'upload_strm_target') {
    config.upload_mappings[picker.index].strm_target = localPath
  }
  picker.open = false
}

watch(() => props.initialConfig, applyConfig, { immediate: true, deep: true })
onBeforeUnmount(clearQrPoll)
</script>

<template>
  <div class="station-config">
    <header class="station-head">
      <div class="station-title">
        <span class="kicker">115 DRIVE / CONTROL ROOM</span>
        <div class="title-row"><span class="title-index">115</span><h2>轻量助手</h2></div>
      </div>

      <div class="signal-rail" aria-label="处理链路">
        <span :class="{ active: connectionReady }"><i>115</i><b>授权</b></span>
        <em />
        <span :class="{ active: config.enabled }"><i>302</i><b>转发</b></span>
        <em />
        <span :class="{ active: config.strm_mappings.length }"><i>STRM</i><b>落盘</b></span>
      </div>

      <div class="head-tools">
        <v-tooltip text="运行台" location="bottom"><template #activator="{ props: tipProps }"><v-btn v-bind="tipProps" icon="mdi-view-dashboard-outline" variant="text" size="small" @click="emit('switch')" /></template></v-tooltip>
        <v-tooltip text="关闭" location="bottom"><template #activator="{ props: tipProps }"><v-btn v-bind="tipProps" icon="mdi-close" variant="text" size="small" @click="emit('close')" /></template></v-tooltip>
      </div>
    </header>

    <div class="station-shell">
      <nav class="station-nav" aria-label="配置区域">
        <button :class="{ current: activeTab === 'login' }" @click="activeTab = 'login'"><v-icon icon="mdi-shield-key-outline" size="18" /><span>登录</span></button>
        <button :class="{ current: activeTab === 'strm' }" @click="activeTab = 'strm'"><v-icon icon="mdi-file-link-outline" size="18" /><span>STRM</span><b>{{ config.strm_mappings.length }}</b></button>
        <button :class="{ current: activeTab === 'upload' }" @click="activeTab = 'upload'"><v-icon icon="mdi-folder-upload-outline" size="18" /><span>目录上传</span><b>{{ config.upload_mappings.length }}</b></button>
        <button :class="{ current: activeTab === 'checkin' }" @click="activeTab = 'checkin'"><v-icon icon="mdi-calendar-check-outline" size="18" /><span>签到</span></button>
      </nav>

      <main class="station-workspace">
        <v-alert v-if="notice" :type="noticeColor" density="compact" variant="tonal" class="station-alert">{{ notice }}</v-alert>

        <v-window v-model="activeTab" :touch="false">
          <v-window-item value="login">
            <section class="work-header">
              <div><span class="work-code">AUTH / 115</span><h3>授权连接</h3></div>
              <v-switch v-model="config.enabled" label="启用插件" color="primary" hide-details density="compact" class="head-switch" />
            </section>
            <section class="auth-deck">
              <div class="auth-portal">
                <div class="auth-portal-head">
                  <div><span class="work-code">QR / SECURE SESSION</span><h4>扫码授权</h4></div>
                  <span class="auth-chip" :class="{ ready: connectionReady }"><i />{{ connectionReady ? '已保存' : '未授权' }}</span>
                </div>
                <v-btn class="auth-qr-action station-primary" size="large" block prepend-icon="mdi-qrcode-scan" @click="openQrDialog">扫码登录 115</v-btn>
              </div>
              <div class="cookie-vault">
                <div class="cookie-vault-head"><span class="work-code">COOKIE / CREDENTIAL</span><span>手工凭据</span></div>
                <v-text-field v-model="config.cookie" type="password" label="115 Cookie" variant="outlined" density="comfortable" hide-details autocomplete="new-password" spellcheck="false" class="cookie-field" />
              </div>
              <aside class="auth-state" :class="{ ready: connectionReady }">
                <span class="auth-state-icon"><v-icon :icon="connectionReady ? 'mdi-shield-check-outline' : 'mdi-shield-key-outline'" size="26" /></span>
                <span class="work-code">115 SESSION</span>
                <strong>{{ connectionReady ? '凭据已保存' : '等待授权' }}</strong>
              </aside>
            </section>
          </v-window-item>

          <v-window-item value="strm">
            <section class="work-header">
              <div><span class="work-code">ROUTE / STRM</span><h3>文件映射</h3></div>
              <div class="head-switches">
                <v-switch v-model="config.strm_incremental" label="增量生成" color="primary" hide-details density="compact" class="head-switch" />
                <v-switch v-model="config.strm_download_sidecars" label="回传附属文件" color="primary" hide-details density="compact" class="head-switch" />
                <v-switch v-model="config.same_playback" label="多端播放" color="primary" hide-details density="compact" class="head-switch" />
                <v-switch v-model="config.life_monitor_enabled" label="监控115生活事件" color="primary" hide-details density="compact" class="head-switch" />
              </div>
            </section>
            <section class="strm-address-row">
              <v-text-field v-model="config.moviepilot_address" label="STRM 文件内链接地址" placeholder="http://moviepilot:3000" variant="outlined" density="comfortable" hide-details>
                <template #append-inner>
                  <v-tooltip text="使用当前站点地址" location="top"><template #activator="{ props: tipProps }"><v-btn v-bind="tipProps" aria-label="使用当前站点地址" icon="mdi-web" variant="text" size="small" @click.stop="useCurrentMoviePilotAddress" /></template></v-tooltip>
                </template>
              </v-text-field>
              <v-select v-model="config.link_redirect_mode" :items="redirectModes" label="302 取链模式" variant="outlined" density="comfortable" hide-details />
            </section>
            <div class="mapping-list">
              <div class="mapping-caption"><span>115 源目录</span><span>本地 STRM 输出目录</span></div>
              <section v-for="(mapping, index) in config.strm_mappings" :key="mapping.id || index" class="mapping-row">
                <v-switch v-model="mapping.enabled" aria-label="启用映射" color="primary" hide-details density="compact" />
                <v-text-field v-model="mapping.source_path" class="mapping-primary-field" label="115 源目录" variant="outlined" density="comfortable" readonly hide-details @click="openPicker('strm_source', index)" />
                <v-text-field v-model="mapping.target_dir" class="mapping-secondary-field" label="本地 STRM 输出目录" variant="outlined" density="comfortable" readonly hide-details @click="openPicker('strm_target', index)" />
                <v-tooltip text="删除映射" location="top"><template #activator="{ props: tipProps }"><v-btn v-bind="tipProps" icon="mdi-delete-outline" variant="text" color="error" size="small" @click="remove(config.strm_mappings, index)" /></template></v-tooltip>
              </section>
              <div v-if="!config.strm_mappings.length" class="empty-row">尚未添加映射</div>
              <v-btn class="station-add" variant="text" prepend-icon="mdi-plus" @click="addStrmMapping">添加 STRM 目录</v-btn>
            </div>
          </v-window-item>

          <v-window-item value="upload">
            <section class="work-header">
              <div><span class="work-code">SYNC / UPLOAD</span><h3>目录上传</h3></div>
              <div class="head-switches">
                <v-switch v-model="config.upload_include_sidecars" label="上传附属文件" color="primary" hide-details density="compact" class="head-switch" />
                <v-switch v-model="config.upload_generate_strm" label="上传完成生成 STRM" color="primary" hide-details density="compact" class="head-switch" />
                <v-switch v-model="config.upload_delete_source" label="上传完成后删除源文件" color="primary" hide-details density="compact" class="head-switch" />
              </div>
            </section>
            <section class="work-grid extension-grid">
              <v-text-field v-model="config.upload_media_extensions" label="媒体扩展名" variant="outlined" density="comfortable" hide-details />
              <v-text-field v-model="config.upload_sidecar_extensions" label="上传与 STRM 附属文件扩展名" variant="outlined" density="comfortable" hide-details />
            </section>
            <div class="mapping-list">
              <div class="mapping-caption upload-mapping-caption" :class="{ 'with-strm-target': config.upload_generate_strm }"><span>本地源目录</span><span>115 目标目录</span><span v-if="config.upload_generate_strm">STRM 输出目录</span></div>
              <section v-for="(mapping, index) in config.upload_mappings" :key="index" class="mapping-row upload-mapping-row" :class="{ 'with-strm-target': config.upload_generate_strm }">
                <v-switch v-model="mapping.enabled" aria-label="启用上传映射" color="primary" hide-details density="compact" />
                <v-text-field v-model="mapping.source" class="mapping-primary-field upload-source-field" label="本地源目录" variant="outlined" density="comfortable" readonly hide-details @click="openPicker('upload_source', index)" />
                <v-text-field v-model="mapping.target" class="mapping-secondary-field upload-target-field" label="115 目标目录" variant="outlined" density="comfortable" readonly hide-details @click="openPicker('upload_target', index)" />
                <v-text-field v-if="config.upload_generate_strm" v-model="mapping.strm_target" class="mapping-tertiary-field upload-strm-field" label="STRM 输出目录" variant="outlined" density="comfortable" readonly hide-details @click="openPicker('upload_strm_target', index)" />
                <v-tooltip text="删除映射" location="top"><template #activator="{ props: tipProps }"><v-btn v-bind="tipProps" icon="mdi-delete-outline" variant="text" color="error" size="small" @click="remove(config.upload_mappings, index)" /></template></v-tooltip>
              </section>
              <div v-if="!config.upload_mappings.length" class="empty-row">尚未添加上传目录</div>
              <v-btn class="station-add" variant="text" prepend-icon="mdi-plus" @click="addUploadMapping">添加上传目录</v-btn>
            </div>
          </v-window-item>

          <v-window-item value="checkin">
            <section class="work-header">
              <div><span class="work-code">PULSE / DAILY</span><h3>每日签到</h3></div>
              <v-switch v-model="config.checkin_enabled" label="启用定时签到" color="primary" hide-details density="compact" class="head-switch" />
            </section>
            <section class="work-grid checkin-grid">
              <v-text-field v-model="config.checkin_time_range" label="签到时间段" placeholder="06:00-09:00" variant="outlined" density="comfortable" hide-details />
            </section>
          </v-window-item>
        </v-window>

        <footer class="station-footer">
          <span class="save-state"><i :class="{ live: config.enabled }" />{{ config.enabled ? '配置已启用' : '配置未启用' }}</span>
          <div>
            <v-btn class="station-secondary" variant="text" @click="applyConfig(props.initialConfig)">重置</v-btn>
            <v-btn class="station-primary" :loading="saving" prepend-icon="mdi-content-save-outline" @click="save">保存更改</v-btn>
          </div>
        </footer>
      </main>
    </div>

    <v-dialog v-model="qrDialog.open" max-width="480" @update:model-value="value => { if (!value) closeQrDialog() }">
      <v-card class="qr-login-dialog">
        <div class="qr-login-head"><div><v-icon icon="mdi-qrcode" size="18" /><span>115网盘扫码登录</span></div><v-btn icon="mdi-close" variant="text" size="small" @click="closeQrDialog" /></div>
        <v-card-text class="qr-login-body">
          <v-alert v-if="qrDialog.error" type="error" density="compact" variant="tonal" class="mb-4">{{ qrDialog.error }}</v-alert>
          <template v-if="qrDialog.loading"><div class="qr-loading"><v-progress-circular indeterminate color="primary" size="30" /><span>正在获取二维码</span></div></template>
          <template v-else>
            <p class="qr-login-label">请选择扫码方式</p>
            <div class="qr-client-types"><v-btn v-for="client in qrClients" :key="client.value" :class="{ selected: qrDialog.clientType === client.value }" variant="outlined" size="small" @click="selectQrClient(client.value)">{{ client.label }}</v-btn></div>
            <div v-if="qrDialog.code" class="qr-code-stage"><div class="qr-code-frame"><img :src="qrDialog.code" alt="115 登录二维码" /></div><p>请使用{{ selectedQrClient.label }}扫描二维码登录</p><strong>{{ qrDialog.status }}</strong><v-btn class="qr-refresh" prepend-icon="mdi-refresh" size="small" @click="refreshQrCode">刷新二维码</v-btn></div>
          </template>
        </v-card-text>
        <v-divider />
        <v-card-actions class="qr-login-actions"><v-btn prepend-icon="mdi-close" variant="text" @click="closeQrDialog">关闭</v-btn><v-spacer /><v-btn prepend-icon="mdi-refresh" variant="text" :disabled="qrDialog.loading" @click="refreshQrCode">刷新二维码</v-btn></v-card-actions>
      </v-card>
    </v-dialog>

    <v-dialog v-model="picker.open" max-width="760">
      <v-card class="picker-dialog">
        <div class="picker-head"><span>{{ pickerTitle }}</span><v-btn icon="mdi-close" variant="text" size="small" @click="picker.open = false" /></div>
        <v-card-text>
          <div class="picker-toolbar">
            <v-btn icon="mdi-arrow-up" variant="text" size="small" :disabled="isRemotePicker ? !picker.remoteTrail.length : !picker.path" title="上级目录" @click="pickerBack" />
            <span class="mono">{{ isRemotePicker ? `/${picker.remoteTrail.map(item => item.name).join('/')}` || '/' : picker.path || picker.localBase || '/' }}</span>
          </div>
          <v-select v-if="!isRemotePicker && picker.roots.length > 1" :model-value="picker.localBase" :items="picker.roots" item-title="name" item-value="path" label="本地根目录" variant="outlined" density="compact" hide-details class="picker-root" @update:model-value="switchLocalRoot" />
          <v-list density="compact" lines="one" class="picker-list">
            <v-list-item v-for="item in picker.items" :key="item.cid || item.path" prepend-icon="mdi-folder-outline" :title="item.name" @click="browsePicker(item)" />
          </v-list>
        </v-card-text>
        <v-card-actions class="picker-actions"><v-spacer /><v-btn class="station-secondary" @click="picker.open = false">取消</v-btn><v-btn class="station-primary" @click="selectPicker">选择当前目录</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped lang="scss">
.station-config {
  --ink: #16211d;
  --muted: #64716a;
  --line: #c7d0ca;
  --soft-line: #dbe2de;
  --paper: #eef2f0;
  --paper-strong: #f8faf9;
  --cyan: #0d7483;
  --green: #14946f;
  --orange: #c9691a;
  --danger: #bd3d35;
  color: var(--ink);
  background: var(--paper);
  border: 1px solid var(--line);
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
  max-width: 1160px;
}

:global(.v-theme--dark) .station-config {
  --ink: #e7eee9;
  --muted: #9eaaa3;
  --line: #3c4a43;
  --soft-line: #2c3832;
  --paper: #18211d;
  --paper-strong: #202a25;
  --cyan: #4dc5d5;
  --green: #54c79c;
  --orange: #f0a95b;
  --danger: #f37d75;
}

.station-head { display: grid; grid-template-columns: minmax(180px, 1fr) auto auto; align-items: center; gap: 24px; min-height: 90px; padding: 18px 24px; border-bottom: 1px solid var(--line); }
.station-title { min-width: 0; }.kicker, .work-code { display: block; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; font-weight: 700; letter-spacing: .08em; }
.title-row { display: flex; align-items: baseline; gap: 10px; }.title-index { color: var(--green); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 21px; font-weight: 800; }.title-row h2 { margin: 3px 0 0; font-size: 21px; font-weight: 720; letter-spacing: 0; }
.signal-rail { display: flex; align-items: center; min-width: 0; }.signal-rail > span { display: grid; gap: 1px; min-width: 52px; color: var(--muted); }.signal-rail i { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; font-style: normal; font-weight: 800; }.signal-rail b { font-size: 11px; font-weight: 650; }.signal-rail em { width: 26px; height: 1px; margin: 0 7px; background: var(--line); }.signal-rail > span.active { color: var(--cyan); }.signal-rail > span.active i::before { content: "● "; color: var(--green); font-size: 8px; }
.head-tools { display: flex; gap: 4px; }.head-tools :deep(.v-btn) { color: var(--muted); }.head-tools :deep(.v-btn:hover) { color: var(--ink); background: color-mix(in srgb, var(--ink) 7%, transparent); }

.station-shell { display: grid; grid-template-columns: 174px minmax(0, 1fr); }.station-nav { padding: 14px 0; border-right: 1px solid var(--line); }.station-nav button { display: grid; grid-template-columns: 24px minmax(0, 1fr) auto; align-items: center; width: 100%; min-height: 46px; padding: 0 16px 0 20px; color: var(--muted); background: transparent; border: 0; border-left: 3px solid transparent; cursor: pointer; text-align: left; font: inherit; font-size: 13px; }.station-nav button:hover { color: var(--ink); background: color-mix(in srgb, var(--ink) 4%, transparent); }.station-nav button.current { color: var(--ink); border-left-color: var(--green); background: color-mix(in srgb, var(--green) 9%, transparent); font-weight: 700; }.station-nav b { min-width: 18px; color: var(--cyan); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 11px; text-align: right; }
.station-workspace { display: flex; flex-direction: column; min-width: 0; padding: 28px 30px 0; }.station-alert { margin-bottom: 16px; }.work-header { display: flex; justify-content: space-between; align-items: end; gap: 16px; padding-bottom: 17px; border-bottom: 2px solid var(--ink); }.work-header h3 { margin: 4px 0 0; font-size: 18px; font-weight: 750; }.head-switches { display: flex; flex-wrap: wrap; justify-content: end; gap: 12px; }.head-switch { margin-bottom: -2px; }.work-grid { display: grid; gap: 16px; padding: 22px 0; }.auth-grid { grid-template-columns: minmax(0, 1fr) 210px; align-items: stretch; }.field-lane { display: grid; gap: 14px; }.auth-state { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 13px; padding: 16px; border-left: 1px solid var(--line); color: var(--muted); text-align: center; font-size: 13px; }.auth-state.ready { color: var(--cyan); }.command-row { display: flex; flex-wrap: wrap; gap: 9px; }.extension-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.mapping-list { padding-top: 3px; }.mapping-caption { display: grid; grid-template-columns: 58px minmax(0, 1fr) minmax(0, 1fr) 36px; gap: 12px; padding: 0 5px 8px; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 10px; font-weight: 700; letter-spacing: .04em; }.mapping-caption span:first-child { grid-column: 2; }.mapping-row { display: grid; grid-template-columns: 58px minmax(0, 1fr) minmax(0, 1fr) 36px; align-items: center; gap: 12px; min-height: 64px; padding: 9px 5px; border-top: 1px solid var(--soft-line); }.mapping-row :deep(.v-text-field) { cursor: pointer; }.mapping-row :deep(.v-field__input) { cursor: pointer; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; }.empty-row { padding: 24px 0; color: var(--muted); border-top: 1px solid var(--soft-line); font-size: 13px; text-align: center; }.station-add { margin: 10px 0 0 -8px; color: var(--cyan); font-weight: 700; }
.station-footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 26px; padding: 18px 0 20px; border-top: 1px solid var(--line); }.station-footer > div { display: flex; align-items: center; gap: 8px; }.save-state { display: inline-flex; align-items: center; gap: 7px; color: var(--muted); font-size: 12px; }.save-state i { width: 7px; height: 7px; border-radius: 50%; background: var(--line); }.save-state i.live { background: var(--green); box-shadow: 0 0 0 3px color-mix(in srgb, var(--green) 18%, transparent); }
.station-primary { background: var(--ink) !important; color: var(--paper-strong) !important; border-radius: 4px !important; box-shadow: none !important; }.station-primary:hover { background: var(--green) !important; }.station-secondary { color: var(--ink) !important; border: 1px solid var(--line) !important; border-radius: 4px !important; }.station-secondary:hover { background: color-mix(in srgb, var(--ink) 6%, transparent) !important; }.station-config :deep(.v-btn:focus-visible), .station-nav button:focus-visible { outline: 2px solid var(--cyan); outline-offset: 2px; }.station-config :deep(.v-field__outline) { --v-field-border-opacity: 1; color: var(--line); }.station-config :deep(.v-field--focused .v-field__outline) { color: var(--cyan); }.station-config :deep(.v-switch .v-selection-control--dirty .v-switch__track) { background: var(--green); opacity: .35; }.station-config :deep(.v-switch .v-selection-control--dirty .v-switch__thumb) { color: var(--green); }.station-config :deep(.v-label) { color: var(--muted); }

.picker-dialog { background: var(--paper-strong); color: var(--ink); border: 1px solid var(--line); border-radius: 6px !important; }.picker-head { display: flex; align-items: center; justify-content: space-between; min-height: 58px; padding: 0 18px; border-bottom: 1px solid var(--line); font-weight: 750; }.picker-toolbar { display: flex; align-items: center; gap: 9px; min-height: 42px; color: var(--muted); overflow: hidden; }.picker-root { margin-bottom: 12px; }.mono { overflow: hidden; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }.picker-list { max-height: 330px; overflow: auto; border-top: 1px solid var(--soft-line); border-bottom: 1px solid var(--soft-line); }.picker-list :deep(.v-list-item) { border-bottom: 1px solid var(--soft-line); }.picker-actions { padding: 12px 18px 16px; }

.qr-login-dialog { background: var(--paper-strong); color: var(--ink); border: 1px solid var(--line); border-radius: 6px !important; }.qr-login-head { display: flex; align-items: center; justify-content: space-between; min-height: 56px; padding: 0 15px 0 18px; border-bottom: 1px solid var(--soft-line); }.qr-login-head > div { display: inline-flex; align-items: center; gap: 9px; color: var(--cyan); font-size: 15px; font-weight: 750; }.qr-login-head span { color: var(--ink); }.qr-login-body { min-height: 400px; padding: 24px 26px 18px !important; text-align: center; }.qr-login-label { margin: 0 0 15px; font-size: 14px; font-weight: 700; }.qr-client-types { display: flex; flex-wrap: wrap; justify-content: center; gap: 7px; }.qr-client-types :deep(.v-btn) { min-width: 50px; height: 27px; padding: 0 10px; border-radius: 14px; color: var(--muted); border-color: var(--line); font-size: 12px; }.qr-client-types :deep(.v-btn.selected) { color: var(--cyan); border-color: var(--cyan); background: color-mix(in srgb, var(--cyan) 7%, transparent); }.qr-code-stage { display: flex; flex-direction: column; align-items: center; padding-top: 18px; }.qr-code-frame { display: grid; width: 214px; height: 214px; place-items: center; padding: 14px; background: #fff; border: 1px solid var(--line); border-radius: 6px; }.qr-code-frame img { display: block; width: 184px; height: 184px; image-rendering: pixelated; }.qr-code-stage p { margin: 11px 0 4px; color: var(--muted); font-size: 12px; }.qr-code-stage strong { color: var(--cyan); font-size: 13px; }.qr-refresh { margin-top: 14px; color: var(--cyan) !important; background: color-mix(in srgb, var(--cyan) 9%, transparent) !important; border-radius: 4px !important; }.qr-loading { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 320px; gap: 13px; color: var(--muted); font-size: 13px; }.qr-login-actions { min-height: 48px; padding: 6px 14px; }.qr-login-actions :deep(.v-btn) { color: var(--muted); }.qr-login-actions :deep(.v-btn:last-child) { color: var(--cyan); }

@media (max-width: 860px) {
  .station-head { grid-template-columns: 1fr auto; }
  .signal-rail { grid-column: 1 / -1; grid-row: 2; }
  .station-shell { grid-template-columns: 1fr; }
  .station-nav { display: flex; overflow-x: auto; padding: 0; border-right: 0; border-bottom: 1px solid var(--line); }
  .station-nav button { grid-template-columns: 22px auto auto; flex: 0 0 auto; min-height: 48px; padding: 0 14px; border-left: 0; border-bottom: 3px solid transparent; }
  .station-nav button.current { border-left-color: transparent; border-bottom-color: var(--green); }
  .station-workspace { padding: 23px 20px 0; }
  .mapping-caption { display: none; }
  .mapping-row { grid-template-columns: 46px minmax(0, 1fr) 36px; }
  .mapping-row :deep(.v-btn) { grid-column: 3; grid-row: 1; }
  .auth-grid { grid-template-columns: 1fr; }
  .auth-state { min-height: 185px; border-top: 1px solid var(--line); border-left: 0; }
  .extension-grid { grid-template-columns: 1fr; }
}
@media (max-width: 560px) { .station-config { border-left: 0; border-right: 0; }.station-head { padding: 16px; gap: 12px; }.signal-rail em { width: 12px; margin: 0 4px; }.station-workspace { padding: 20px 16px 0; }.work-header { align-items: start; flex-direction: column; }.head-switches { justify-content: start; }.head-switch { margin-bottom: 0; }.mapping-row { grid-template-columns: 42px minmax(0, 1fr) 32px; gap: 8px; }.station-footer { align-items: stretch; flex-direction: column; }.station-footer > div { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }.station-footer > div :deep(.v-btn) { width: 100%; min-width: 0; }.title-row h2 { font-size: 19px; } }
@media (prefers-reduced-motion: reduce) { .station-config * { transition: none !important; } }
</style>

<style scoped lang="scss">
.station-config {
  --ink: #172a34;
  --muted: #667b87;
  --line: #d5e1e7;
  --soft-line: #e8eff3;
  --paper: #eef4f7;
  --paper-strong: #ffffff;
  --header: #17333b;
  --cyan: #147fb8;
  --green: #168c79;
  --orange: #d88822;
  --danger: #ca4c5d;
  width: min(100%, 1180px);
  max-width: 1180px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--paper);
  box-shadow: 0 14px 32px rgb(27 53 65 / 10%);
  font-family: "HarmonyOS Sans SC", "Microsoft YaHei", sans-serif;
}

:global(.v-theme--dark) .station-config {
  --ink: #e8f1f2;
  --muted: #a9b9bd;
  --line: #3a4b50;
  --soft-line: #2a383c;
  --paper: #172126;
  --paper-strong: #202d31;
  --header: #102b31;
  --cyan: #50bde8;
  --green: #53c9ad;
  --orange: #f0af5a;
  --danger: #ef8591;
  box-shadow: none;
}

.station-head {
  position: relative;
  grid-template-columns: minmax(220px, 1fr) auto auto;
  gap: 30px;
  min-height: 96px;
  padding: 16px 28px;
  color: #f5fbfc;
  background: var(--header);
  border: 0;
}

.station-head::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 3px;
  background: var(--cyan);
  content: "";
}

.kicker,
.work-code {
  color: #a9c5ce;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .11em;
}

.title-row { gap: 11px; }
.title-index { color: #60d2bb; font-size: 25px; }
.title-row h2 { margin-top: 2px; color: #fff; font-size: 22px; font-weight: 760; }

.signal-rail { gap: 0; }
.signal-rail > span { min-width: 58px; padding: 5px 0; color: #a9c5ce; }
.signal-rail i { color: inherit; font-size: 10px; }
.signal-rail b { font-size: 12px; font-weight: 700; }
.signal-rail em { width: 22px; margin: 0 8px; background: rgb(217 238 241 / 28%); }
.signal-rail > span.active { color: #fff; }
.signal-rail > span.active i::before { color: #60d2bb; }
.head-tools { gap: 5px; }
.head-tools :deep(.v-btn) { color: #d8e8eb; }
.head-tools :deep(.v-btn:hover) { color: #fff; background: rgb(255 255 255 / 12%); }

.station-shell { grid-template-columns: 196px minmax(0, 1fr); background: var(--paper-strong); }
.station-nav { padding: 18px 12px; background: color-mix(in srgb, var(--paper) 74%, var(--paper-strong)); border-right-color: var(--line); }
.station-nav button {
  grid-template-columns: 25px minmax(0, 1fr) auto;
  min-height: 48px;
  margin: 3px 0;
  padding: 0 12px;
  color: var(--muted);
  border-left: 0;
  border-radius: 6px;
  font-size: 13px;
}
.station-nav button:hover { color: var(--ink); background: color-mix(in srgb, var(--cyan) 8%, transparent); }
.station-nav button.current { color: var(--ink); background: color-mix(in srgb, var(--cyan) 13%, var(--paper-strong)); box-shadow: inset 3px 0 0 var(--cyan); }
.station-nav b { min-width: 22px; padding: 2px 5px; color: var(--cyan); background: color-mix(in srgb, var(--cyan) 10%, transparent); border-radius: 4px; font-size: 10px; }

.station-workspace { padding: 30px 34px 0; background: var(--paper-strong); }
.station-alert { margin-bottom: 18px; border-left: 3px solid var(--cyan); border-radius: 4px; }
.work-header { align-items: center; padding-bottom: 18px; border-bottom: 1px solid var(--line); }
.work-header h3 { margin-top: 5px; font-size: 21px; font-weight: 760; }
.work-code { color: var(--cyan); }
.head-switches { gap: 18px; }
.head-switch { margin-bottom: 0; }
.station-config :deep(.v-switch .v-label) { color: var(--muted); font-size: 12px; font-weight: 650; }
.station-config :deep(.v-switch .v-selection-control--dirty .v-switch__track) { background: var(--cyan); opacity: .45; }
.station-config :deep(.v-switch .v-selection-control--dirty .v-switch__thumb) { color: var(--cyan); }

.work-grid { gap: 18px; padding: 24px 0; }
.auth-deck { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.25fr) 178px; gap: 14px; padding: 24px 0; }
.auth-portal,
.cookie-vault,
.auth-state { min-width: 0; border: 1px solid var(--line); border-radius: 6px; }
.auth-portal { padding: 18px; background: color-mix(in srgb, var(--paper) 64%, var(--paper-strong)); }
.auth-portal-head,
.cookie-vault-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.auth-portal h4 { margin: 5px 0 0; color: var(--ink); font-size: 17px; font-weight: 760; }
.auth-chip { display: inline-flex; align-items: center; gap: 6px; flex: 0 0 auto; color: var(--muted); font-size: 11px; font-weight: 700; }
.auth-chip i { width: 7px; height: 7px; border-radius: 50%; background: var(--muted); }
.auth-chip.ready { color: var(--green); }.auth-chip.ready i { background: var(--green); box-shadow: 0 0 0 3px color-mix(in srgb, var(--green) 17%, transparent); }
.auth-qr-action { min-height: 44px; margin-top: 20px; font-weight: 750; }
.cookie-vault { display: flex; flex-direction: column; justify-content: center; padding: 18px; background: var(--paper-strong); }
.cookie-vault-head { margin-bottom: 14px; color: var(--muted); font-size: 12px; font-weight: 700; }
.cookie-vault-head .work-code { color: var(--cyan); }.cookie-field :deep(input) { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; letter-spacing: .02em; }
.auth-state { align-items: flex-start; justify-content: center; gap: 8px; padding: 20px; color: var(--muted); background: color-mix(in srgb, var(--paper) 76%, var(--paper-strong)); text-align: left; }
.auth-state.ready { color: var(--green); }.auth-state-icon { display: grid; width: 38px; height: 38px; place-items: center; margin-bottom: 4px; color: var(--cyan); background: color-mix(in srgb, var(--cyan) 10%, transparent); border-radius: 5px; }.auth-state.ready .auth-state-icon { color: var(--green); background: color-mix(in srgb, var(--green) 11%, transparent); }
.auth-state .work-code { color: inherit; opacity: .78; }.auth-state strong { color: var(--ink); font-size: 14px; }
.auth-state.ready strong { color: var(--green); }

.station-config :deep(.v-field) { background: var(--paper-strong); border-radius: 5px; }
.station-config :deep(.v-field__outline) { --v-field-border-opacity: 1; color: var(--line); }
.station-config :deep(.v-field--focused .v-field__outline) { color: var(--cyan); }
.station-config :deep(.v-label) { color: var(--muted); }
.station-config :deep(.v-field__input) { color: var(--ink); }

.mapping-list { padding-top: 12px; }
.strm-address-row { display: grid; grid-template-columns: minmax(0, 1fr) 180px; gap: 14px; padding: 20px 0 8px; border-bottom: 1px solid var(--soft-line); }
.strm-address-row :deep(input) { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.strm-address-row :deep(.v-btn) { color: var(--cyan); }
.mapping-caption { padding: 0 12px 8px; color: var(--muted); font-size: 10px; }
.mapping-row { min-height: 72px; margin-bottom: 9px; padding: 11px 12px; background: var(--paper-strong); border: 1px solid var(--line); border-radius: 6px; }
.upload-mapping-caption.with-strm-target,
.upload-mapping-row.with-strm-target { grid-template-columns: 58px repeat(3, minmax(0, 1fr)) 36px; }
.mapping-row:hover { border-color: color-mix(in srgb, var(--cyan) 52%, var(--line)); }
.mapping-row :deep(.v-field__input) { font-size: 12px; }
.empty-row { padding: 32px 0; background: color-mix(in srgb, var(--paper) 58%, var(--paper-strong)); border: 1px dashed var(--line); border-radius: 6px; }
.station-add { margin: 5px 0 0 -8px; color: var(--cyan); font-weight: 750; }

.station-footer { margin-top: 24px; padding: 17px 0 22px; border-top-color: var(--line); }
.save-state { font-size: 12px; font-weight: 650; }
.save-state i { background: var(--muted); }
.save-state i.live { background: var(--green); box-shadow: 0 0 0 4px color-mix(in srgb, var(--green) 16%, transparent); }
.station-primary { min-height: 38px; padding: 0 16px !important; background: var(--cyan) !important; color: #fff !important; border-radius: 5px !important; }
.station-primary:hover { background: #0b679b !important; }
.station-secondary { min-height: 38px; color: var(--ink) !important; background: var(--paper-strong) !important; border-color: var(--line) !important; border-radius: 5px !important; }
.station-secondary:hover { background: var(--paper) !important; }
.station-config :deep(.v-btn:focus-visible),
.station-nav button:focus-visible { outline-color: var(--cyan); }

.picker-dialog,
.qr-login-dialog { background: var(--paper-strong); color: var(--ink); border: 1px solid var(--line); border-radius: 8px !important; box-shadow: 0 18px 44px rgb(19 43 52 / 20%); }
.picker-head,
.qr-login-head { min-height: 64px; padding: 0 20px; background: color-mix(in srgb, var(--paper) 64%, var(--paper-strong)); border-bottom-color: var(--line); }
.picker-head { font-size: 15px; }
.qr-login-head > div { color: var(--cyan); font-size: 15px; }
.qr-login-head span { color: var(--ink); }
.picker-toolbar { min-height: 46px; padding: 0 4px; background: var(--paper); border-radius: 5px; }
.picker-list { max-height: 360px; border-color: var(--line); }
.picker-list :deep(.v-list-item) { min-height: 46px; border-bottom-color: var(--soft-line); }
.picker-list :deep(.v-list-item:hover) { background: color-mix(in srgb, var(--cyan) 8%, transparent); }
.picker-actions { min-height: 64px; padding: 12px 20px; }

.qr-login-body { min-height: 0; padding: 24px 30px 20px !important; }
.qr-login-label { color: var(--ink); }
.qr-client-types { gap: 8px; }
.qr-client-types :deep(.v-btn) { min-width: 54px; height: 29px; border-radius: 5px; }
.qr-client-types :deep(.v-btn.selected) { color: var(--cyan); background: color-mix(in srgb, var(--cyan) 9%, transparent); }
.qr-code-frame { width: 210px; height: 210px; padding: 13px; border-color: var(--line); border-radius: 6px; box-shadow: 0 8px 18px rgb(20 55 68 / 8%); }
.qr-code-frame img { width: 182px; height: 182px; }
.qr-refresh { color: #fff !important; background: var(--cyan) !important; }
.qr-login-actions { min-height: 56px; padding: 8px 16px; background: color-mix(in srgb, var(--paper) 55%, var(--paper-strong)); }

@media (max-width: 1080px) {
  .auth-deck { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .auth-state { grid-column: 1 / -1; flex-direction: row; align-items: center; justify-content: flex-start; min-height: 76px; padding: 16px 20px; }
  .auth-state-icon { margin-bottom: 0; }
}

@media (max-width: 900px) {
  .station-config { border-radius: 0; }
  .station-head { grid-template-columns: minmax(0, 1fr) auto; gap: 14px; }
  .signal-rail { grid-column: 1 / -1; grid-row: 2; }
  .station-shell { grid-template-columns: 1fr; }
  .station-nav { display: flex; gap: 4px; padding: 8px 12px; overflow-x: auto; border-right: 0; border-bottom: 1px solid var(--line); }
  .station-nav button { grid-template-columns: 22px auto auto; flex: 0 0 auto; min-height: 42px; margin: 0; padding: 0 11px; }
  .station-nav button.current { box-shadow: inset 0 -3px 0 var(--cyan); }
  .station-workspace { padding: 26px 24px 0; }
}

@media (max-width: 860px) {
  .upload-mapping-row.with-strm-target { grid-template-columns: 46px minmax(0, 1fr) 36px; }
  .mapping-row :deep(.mapping-primary-field) { grid-column: 2; grid-row: 1; }
  .mapping-row :deep(.mapping-secondary-field) { grid-column: 2; grid-row: 2; }
  .mapping-row :deep(.mapping-tertiary-field) { grid-column: 2; grid-row: 3; }
}

@media (max-width: 620px) {
  .station-config { border-right: 0; border-left: 0; }
  .station-head { min-height: 116px; padding: 15px 16px 14px; }
  .signal-rail > span { min-width: 48px; }
  .signal-rail em { width: 12px; margin: 0 5px; }
  .station-workspace { padding: 22px 16px 0; }
  .work-header { align-items: flex-start; flex-direction: column; gap: 13px; }
  .head-switches { justify-content: flex-start; gap: 4px 12px; }
  .auth-deck { grid-template-columns: 1fr; }
  .auth-state { grid-column: auto; flex-direction: column; align-items: flex-start; min-height: 124px; }
  .auth-state-icon { margin-bottom: 4px; }
  .extension-grid { grid-template-columns: 1fr; }
  .strm-address-row { grid-template-columns: 1fr; }
  .mapping-caption { display: none; }
  .mapping-row { grid-template-columns: 40px minmax(0, 1fr) 32px; gap: 8px; padding: 9px; }
  .mapping-row :deep(.v-btn) { grid-column: 3; grid-row: 1; }
  .station-footer { align-items: stretch; flex-direction: column; }
  .station-footer > div { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .station-footer > div :deep(.v-btn) { width: 100%; min-width: 0; }
  .picker-actions { flex-wrap: wrap; }
  .qr-login-body { min-height: 0; padding: 22px 18px 18px !important; }
}
</style>
