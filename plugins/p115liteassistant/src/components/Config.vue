<script setup>
import { computed, inject, nextTick, onMounted, reactive, ref, watch } from 'vue'
import AppBar from './ui/AppBar.vue'
import Conduit from './ui/Conduit.vue'
import DirPicker from './ui/DirPicker.vue'
import NotifyRow from './ui/NotifyRow.vue'
import QrLogin from './ui/QrLogin.vue'
import {
  applyNotificationSettings,
  applyReverseDeleteMode,
  clone,
  deriveAuthState,
  deriveNotificationSettings,
  deriveReverseDeleteMode,
  mappingStats,
  newId,
  normalizeConfig,
  NOTIFY_TYPES,
  pluginGet,
  pluginPost,
  toWritableConfig,
  useHostNotice,
  validateConfig,
} from '../plugin.js'
import '../styles/kit.scss'

const props = defineProps({
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: [Object, Function], default: null },
  saving: { type: Boolean, default: false },
  wide: { type: Boolean, default: false },
})
const emit = defineEmits(['save', 'close', 'switch', 'layout'])

const config = reactive(normalizeConfig())
const section = ref('start')
const busy = ref(false)
const local = reactive({ text: '', kind: 'info' })
const status = reactive({ ready: false, failed: false, data: null })
const advanced = reactive({ start: false, strm: false, upload: false, automation: false, notify: false })
const notification = reactive(deriveNotificationSettings(config))
const reverseDeleteMode = ref('off')
const initialDeleteSource = ref(false)
const deleteSourceConfirmed = ref(false)
const qrOpen = ref(false)
const pick = reactive({ open: false, remote: false, title: '', apply: null })
const confirm = reactive({ open: false, resolve: null })
const fieldErrors = ref([])

const notice = useHostNotice(inject('moviepilot:toast', null), (text, kind) => {
  local.text = text
  local.kind = kind
})

const redirectModes = [
  { title: 'Cookie 取链', value: 'cookie' },
  { title: 'Open API 取链', value: 'open' },
]
const conflictPolicies = [
  { title: '挂到清单等我处理', value: 'ask' },
  { title: '自动采用网盘文件', value: 'adopt' },
  { title: '自动删掉网盘文件并重传', value: 'reupload' },
]
const reverseModes = [
  { title: '关闭', value: 'off' },
  { title: '安全模式（推荐）', value: 'safe' },
  { title: '自定义', value: 'custom' },
]

const stats = computed(() => mappingStats(config))
const authState = computed(() => deriveAuthState(config, status))
const authorized = computed(() => authState.value === 'authorized')
const notifyTypes = computed(() => (
  Array.isArray(config.notify_types) && config.notify_types.length ? config.notify_types : NOTIFY_TYPES
))
const enabledUploads = computed(() => (
  Array.isArray(config.upload_mappings)
    ? config.upload_mappings.filter(item => item && item.enabled !== false)
    : []
))
const needsMoviePilotAddress = computed(() => (
  stats.value.strm.usable > 0 || (config.upload_generate_strm && enabledUploads.value.length > 0)
))
const lifeMonitorBlocked = computed(() => stats.value.strm.usable === 0)
const notificationCount = computed(() => (
  Object.values(notification.events || {}).filter(item => item.checked).length
))

const authPresentation = computed(() => ({
  authorized: { text: '已授权', tone: 'on' },
  expired: { text: '授权已失效', tone: 'bad' },
  unauthorized: { text: '未授权', tone: 'warn' },
  unknown: { text: '状态未知', tone: 'hold' },
}[authState.value]))

function mappingNote(value) {
  const pieces = [`${value.usable} 条可用`]
  if (value.incomplete) pieces.push(`${value.incomplete} 条待填写`)
  if (value.disabled) pieces.push(`${value.disabled} 条已关闭`)
  return pieces.join('，')
}

const sections = computed(() => [
  { key: 'start', icon: 'mdi-play-circle-outline', label: '开始使用', note: authPresentation.value.text },
  { key: 'strm', icon: 'mdi-transit-connection-variant', label: '生成 STRM', note: mappingNote(stats.value.strm) },
  { key: 'upload', icon: 'mdi-tray-arrow-up', label: '上传到网盘', note: mappingNote(stats.value.upload) },
  {
    key: 'automation', icon: 'mdi-calendar-sync-outline', label: '自动任务',
    note: config.life_monitor_enabled && lifeMonitorBlocked.value
      ? '待填写'
      : (config.checkin_enabled || config.life_monitor_enabled ? '已开启' : '已关闭'),
  },
  { key: 'notify', icon: 'mdi-bell-outline', label: '通知', note: notification.enabled ? '已开启' : '已关闭' },
])

function hydrateNotification(value) {
  const derived = deriveNotificationSettings(value)
  Object.assign(notification, derived)
  notification.events = clone(derived.events)
  advanced.notify = derived.inconsistent
}

function apply(value = {}, { snapshot = true } = {}) {
  const normalized = normalizeConfig(value)
  for (const key of Object.keys(config)) delete config[key]
  Object.assign(config, normalized)
  hydrateNotification(config)
  reverseDeleteMode.value = deriveReverseDeleteMode(config)
  fieldErrors.value = []
  if (snapshot) {
    initialDeleteSource.value = Boolean(config.upload_delete_source)
    deleteSourceConfirmed.value = false
  }
}

function validStatusData(value) {
  return value && typeof value === 'object' && !value.error && typeof value.authenticated === 'boolean'
}

async function reload() {
  if (!props.api) {
    apply(props.initialConfig)
    status.ready = false
    status.failed = false
    status.data = null
    return
  }
  busy.value = true
  const [configResult, statusResult] = await Promise.allSettled([
    pluginGet(props.api, '/config'),
    pluginGet(props.api, '/status'),
  ])
  if (configResult.status === 'fulfilled' && !configResult.value?.error) {
    apply(configResult.value)
  } else {
    const reason = configResult.status === 'rejected' ? configResult.reason : configResult.value?.error
    notice.error(reason?.message || reason || '配置读取失败')
  }
  status.ready = true
  status.failed = statusResult.status !== 'fulfilled' || !validStatusData(statusResult.value)
  status.data = statusResult.status === 'fulfilled' ? statusResult.value : null
  if (status.failed) notice.warning('状态没读到。点右上角的刷新重试一次。')
  busy.value = false
}

function notificationDraft() {
  const draft = applyNotificationSettings(config, notification)
  return applyReverseDeleteMode(draft, reverseDeleteMode.value)
}

function errorsFor(field) {
  return fieldErrors.value.filter(item => item.field === field).map(item => item.message)
}

function mappingErrors(kind, index) {
  return errorsFor(`${kind}-${index}`)
}

async function focusError(error) {
  section.value = error.section
  if (error.advanced) advanced[error.section] = true
  await nextTick()
  const target = document.querySelector(`[data-field="${error.field}"]`)
  target?.querySelector?.('input, textarea, button, [tabindex]')?.focus?.()
}

async function save() {
  let draft = notificationDraft()
  fieldErrors.value = validateConfig(draft)
  if (fieldErrors.value.length) {
    const first = fieldErrors.value[0]
    await focusError(first)
    notice.error(first.message)
    return
  }
  if (!initialDeleteSource.value && draft.upload_delete_source && !deleteSourceConfirmed.value) {
    const accepted = await askDeleteSourceConfirmation()
    if (!accepted) return
    deleteSourceConfirmed.value = true
    draft = notificationDraft()
  }
  const payload = toWritableConfig(draft)
  if (!props.api) {
    emit('save', payload)
    return
  }
  busy.value = true
  try {
    const result = await pluginPost(props.api, '/config', payload)
    if (!result.success) {
      notice.error(result.message || '保存失败')
      return
    }
    notice.success(result.message || '配置已保存')
    emit('save', payload)
    await reload()
  } catch (error) {
    notice.error(error?.message || '保存失败')
  } finally {
    busy.value = false
  }
}

function useThisSite() {
  const origin = globalThis.location?.origin
  if (!origin) return notice.error('无法识别当前站点地址')
  config.moviepilot_address = origin
  notice.success('已填入当前站点地址')
}

function addStrm() {
  config.strm_mappings.push({ id: newId(), enabled: true, source_cid: '', source_path: '', target_dir: '' })
}

function addUpload() {
  config.upload_mappings.push({ id: newId(), enabled: true, source: '', target: '', strm_target: '' })
}

function drop(list, index) {
  list.splice(index, 1)
}

function openPicker(title, remote, apply_) {
  Object.assign(pick, { open: true, remote, title, apply: apply_ })
}

function onPicked(result) {
  pick.apply?.(result)
  pick.apply = null
}

function strmStops(mapping) {
  return [
    { key: 'source', tag: '115 源目录', icon: 'mdi-cloud-outline', value: mapping.source_path, placeholder: '点击选择 115 目录' },
    { key: 'target', tag: '本地输出', icon: 'mdi-folder-outline', value: mapping.target_dir, placeholder: '点击选择本地目录' },
  ]
}

function uploadStops(mapping) {
  const stops = [
    { key: 'source', tag: '本地源目录', icon: 'mdi-folder-outline', value: mapping.source, placeholder: '点击选择本地目录' },
    { key: 'target', tag: '115 目标目录', icon: 'mdi-cloud-outline', value: mapping.target, placeholder: '点击选择 115 目录' },
  ]
  if (config.upload_generate_strm) {
    stops.push({ key: 'strm', tag: 'STRM 输出', icon: 'mdi-file-link-outline', value: mapping.strm_target, placeholder: '点击选择本地目录' })
  }
  return stops
}

function pickStrm(mapping, key) {
  if (key === 'source') {
    openPicker('选择 115 源目录', true, result => {
      mapping.source_cid = result.cid
      mapping.source_path = result.path
    })
  } else {
    openPicker('选择 STRM 输出目录', false, result => { mapping.target_dir = result.path })
  }
}

function pickUpload(mapping, key) {
  if (key === 'source') {
    openPicker('选择本地源目录', false, result => { mapping.source = result.path })
  } else if (key === 'target') {
    openPicker('选择 115 目标目录', true, result => { mapping.target = result.path })
  } else {
    openPicker('选择 STRM 输出目录', false, result => { mapping.strm_target = result.path })
  }
}

function toggleAdvanced(key) {
  advanced[key] = !advanced[key]
}

function goToExtensions() {
  section.value = 'strm'
  advanced.strm = true
}

function updateNotificationMaster(value) {
  notification.enabled = Boolean(value)
}

function updateNotificationChecked(event, value) {
  notification.events[event].checked = Boolean(value)
  if (value) notification.enabled = true
}

function useUnifiedNotifications() {
  const selected = Object.values(notification.events).find(item => item.checked)
  notification.unifiedType = selected?.type || notification.unifiedType || 'Plugin'
  notification.mode = 'unified'
  advanced.notify = false
}

function useSeparateNotifications() {
  notification.mode = 'separate'
  advanced.notify = true
}

function resolveConfirmation(accepted) {
  confirm.open = false
  const done = confirm.resolve
  confirm.resolve = null
  done?.(accepted)
}

function askDeleteSourceConfirmation() {
  confirm.open = true
  return new Promise(resolve => { confirm.resolve = resolve })
}

async function updateDeleteSource(value) {
  if (!value) {
    config.upload_delete_source = false
    deleteSourceConfirmed.value = false
    return
  }
  const accepted = await askDeleteSourceConfirmation()
  config.upload_delete_source = accepted
  deleteSourceConfirmed.value = accepted
}

watch(() => props.initialConfig, value => {
  if (!props.api) apply(value)
}, { immediate: true, deep: true })

onMounted(() => {
  emit('layout', { maxWidth: '62rem' })
  if (props.api) reload()
})
</script>

<template>
  <div class="p115 cfg">
    <AppBar
      view="设置"
      :online="authorized"
      :show-close="!wide"
      :busy="busy"
      show-refresh
      @refresh="reload"
      @switch="emit('switch')"
      @close="emit('close')"
    />

    <button v-if="local.text" type="button" class="cfg__local" :class="`cfg__local--${local.kind}`" @click="local.text = ''">
      {{ local.text }}
      <span class="cfg__local-dismiss">知道了</span>
    </button>

    <div class="cfg__shell">
      <nav class="cfg__rail" aria-label="设置分区">
        <button
          v-for="item in sections"
          :key="item.key"
          type="button"
          class="cfg__tab"
          :class="{ 'cfg__tab--on': section === item.key }"
          :aria-current="section === item.key ? 'true' : undefined"
          @click="section = item.key"
        >
          <v-icon :icon="item.icon" size="17" aria-hidden="true" />
          <span class="cfg__tab-text">
            <span class="cfg__tab-label">{{ item.label }}</span>
            <span class="cfg__tab-note p115-mono">{{ item.note }}</span>
          </span>
        </button>
      </nav>

      <div :key="section" class="cfg__pane p115-enter">
        <section v-if="section === 'start'">
          <div class="p115-panel">
            <div class="p115-panel__head">
              <div>
                <h3 class="p115-section-title">115 授权</h3>
                <p class="p115-hint">扫码登录或手工填写 Cookie，让插件访问你的 115。</p>
              </div>
              <v-switch v-model="config.enabled" color="primary" density="compact" hide-details :label="config.enabled ? '已开启' : '已关闭'" />
            </div>
            <div class="p115-panel__body">
              <div class="cfg__status-line">
                <span v-if="authState !== 'unknown'" class="p115-pill" :class="`p115-pill--${authPresentation.tone}`">
                  {{ authPresentation.text }}
                </span>
                <p v-else class="p115-probe">{{ status.failed ? '状态没读到。点右上角的刷新重试一次。' : '正在读取授权状态…' }}</p>
                <v-btn color="primary" variant="flat" size="small" prepend-icon="mdi-qrcode-scan" @click="qrOpen = true">扫码登录</v-btn>
              </div>
            </div>
          </div>

          <div class="p115-panel" data-field="moviepilot_address">
            <div class="p115-panel__head">
              <div>
                <h3 class="p115-section-title">播放地址</h3>
                <p class="p115-hint">
                  {{ needsMoviePilotAddress ? '写入 STRM 的 MoviePilot 访问地址，播放设备必须能访问。' : '当前功能不需要填写。' }}
                </p>
              </div>
            </div>
            <div class="p115-panel__body">
              <v-text-field
                v-model="config.moviepilot_address"
                :label="needsMoviePilotAddress ? 'MoviePilot 访问地址（必填）' : 'MoviePilot 访问地址'"
                :error-messages="errorsFor('moviepilot_address')"
                variant="outlined"
                density="compact"
                placeholder="http://HOST:PORT"
              >
                <template #append-inner><v-btn variant="text" size="x-small" @click="useThisSite">用当前站点</v-btn></template>
              </v-text-field>
            </div>
          </div>

          <button type="button" class="cfg__advanced" :aria-expanded="advanced.start" @click="toggleAdvanced('start')">
            <span><v-icon icon="mdi-tune-variant" size="16" aria-hidden="true" /> 登录与播放</span>
            <v-icon :icon="advanced.start ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="17" aria-hidden="true" />
          </button>
          <div v-if="advanced.start" class="p115-panel cfg__advanced-panel">
            <div class="p115-panel__body">
              <div class="p115-fields">
                <v-text-field
                  v-model="config.cookie"
                  label="115 Cookie"
                  type="password"
                  variant="outlined"
                  density="compact"
                  autocomplete="off"
                  placeholder="UID=...; CID=...; SEID=..."
                />
                <v-select v-model="config.link_redirect_mode" :items="redirectModes" label="取链方式" variant="outlined" density="compact" />
              </div>
              <p class="p115-hint">Cookie 会加密保存在 MoviePilot 本地，并以密码形式遮挡；重新打开设置时仍会读取已保存值。</p>
              <v-switch v-model="config.same_playback" color="primary" density="compact" hide-details label="播放时同步 115 观看记录" />
            </div>
          </div>
        </section>

        <section v-else-if="section === 'strm'">
          <div class="p115-panel">
            <div class="p115-panel__head">
              <div>
                <h3 class="p115-section-title">生成 STRM</h3>
                <p class="p115-hint">一条映射把一个 115 目录生成到本地输出目录。</p>
              </div>
              <v-btn variant="outlined" size="small" prepend-icon="mdi-plus" @click="addStrm">加一条映射</v-btn>
            </div>
            <div class="p115-panel__body">
              <v-switch v-model="config.strm_download_sidecars" color="primary" density="compact" hide-details label="一并下载刮削文件" />
            </div>
          </div>

          <div v-for="(mapping, index) in config.strm_mappings" :key="mapping.id" :data-field="`strm-${index}`" class="cfg__mapping">
            <Conduit
              :enabled="mapping.enabled !== false"
              :stops="strmStops(mapping)"
              :index="index"
              @update:enabled="value => (mapping.enabled = value)"
              @pick="key => pickStrm(mapping, key)"
              @remove="drop(config.strm_mappings, index)"
            />
            <p v-for="message in mappingErrors('strm', index)" :key="message" class="cfg__field-error">{{ message }}</p>
            <p v-if="mapping.enabled !== false && mapping.source_cid && !mapping.source_path" class="p115-hint">已保存 115 目录 ID；重新选择后会补回可读路径。</p>
          </div>
          <p v-if="!config.strm_mappings.length" class="p115-empty">还没有 STRM 映射。加一条，选好 115 源目录和本地输出目录就能同步。</p>

          <button type="button" class="cfg__advanced" :aria-expanded="advanced.strm" @click="toggleAdvanced('strm')">
            <span><v-icon icon="mdi-tune-variant" size="16" aria-hidden="true" /> 高级设置</span>
            <v-icon :icon="advanced.strm ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="17" aria-hidden="true" />
          </button>
          <div v-if="advanced.strm" class="cfg__advanced-stack">
            <div class="p115-panel">
              <div class="p115-panel__head"><div><h3 class="p115-section-title">同步方式</h3><p class="p115-hint">默认只处理新增和变化的文件。</p></div></div>
              <div class="p115-panel__body"><v-switch v-model="config.strm_incremental" color="primary" density="compact" hide-details label="只处理新增和变化的文件" /></div>
            </div>

            <div class="p115-panel">
              <div class="p115-panel__head"><div><h3 class="p115-section-title">网盘反向清理</h3><p class="p115-hint">本地 STRM 不见后，按保护规则清理对应网盘文件。</p></div></div>
              <div class="p115-panel__body">
                <v-select v-model="reverseDeleteMode" :items="reverseModes" label="清理模式" variant="outlined" density="compact" />
                <div v-if="reverseDeleteMode !== 'off'" class="p115-subpanel">
                  <p class="p115-hint p115-hint--warn">网盘文件会进入 115 回收站；媒体库未挂载、空目录或缺失比例过高时会放弃，源目录与一级目录不删。</p>
                  <p v-if="reverseDeleteMode === 'safe'" class="p115-hint">每 2 小时巡检，不实时监听；一次超过 16 个媒体文件时等你确认。</p>
                  <div v-else class="cfg__advanced-stack">
                    <div class="p115-fields" data-field="reverse_cron">
                      <v-text-field v-model="config.strm_delete_sweep_cron" :error-messages="errorsFor('reverse_cron')" label="巡检周期（cron，可留空）" variant="outlined" density="compact" placeholder="37 */2 * * *" />
                      <v-text-field v-model.number="config.strm_delete_confirm_threshold" type="number" min="0" label="超过多少个先等你确认（0 = 不等）" variant="outlined" density="compact" />
                    </div>
                    <v-switch v-model="config.strm_delete_watch" color="primary" density="compact" hide-details label="实时监听本地目录变化" />
                    <p class="p115-hint">实时监听只负责加速；网络挂载可能收不到事件，定时巡检才是兜底。</p>
                  </div>
                </div>
              </div>
            </div>

            <div class="p115-panel">
              <div class="p115-panel__head"><div><h3 class="p115-section-title">文件识别规则</h3><p class="p115-hint">STRM 刮削下载、上传、LifeMonitor 与反向清理共同使用。</p></div></div>
              <div class="p115-panel__body">
                <div class="p115-fields">
                  <v-textarea v-model="config.upload_media_extensions" label="媒体文件后缀" variant="outlined" density="compact" rows="2" auto-grow />
                  <v-textarea v-model="config.upload_sidecar_extensions" label="刮削文件后缀" variant="outlined" density="compact" rows="2" auto-grow />
                </div>
                <p class="p115-hint">用英文逗号分隔并带上点号，例如 <span class="p115-mono">.mp4,.mkv</span>。</p>
              </div>
            </div>
          </div>
        </section>

        <section v-else-if="section === 'upload'">
          <div class="p115-panel">
            <div class="p115-panel__head">
              <div><h3 class="p115-section-title">上传到网盘</h3><p class="p115-hint">一条映射把一个本地目录上传到 115。</p></div>
              <v-btn variant="outlined" size="small" prepend-icon="mdi-plus" @click="addUpload">加一条映射</v-btn>
            </div>
            <div class="p115-panel__body">
              <div class="p115-switches">
                <v-switch v-model="config.upload_include_sidecars" color="primary" density="compact" hide-details label="一并上传刮削文件" />
                <v-switch v-model="config.upload_generate_strm" color="primary" density="compact" hide-details label="上传后生成 STRM" />
              </div>
            </div>
          </div>

          <div v-for="(mapping, index) in config.upload_mappings" :key="mapping.id" :data-field="`upload-${index}`" class="cfg__mapping">
            <Conduit
              :enabled="mapping.enabled !== false"
              :stops="uploadStops(mapping)"
              :index="index"
              @update:enabled="value => (mapping.enabled = value)"
              @pick="key => pickUpload(mapping, key)"
              @remove="drop(config.upload_mappings, index)"
            />
            <p v-for="message in mappingErrors('upload', index)" :key="message" class="cfg__field-error">{{ message }}</p>
          </div>
          <p v-if="!config.upload_mappings.length" class="p115-empty">还没有上传映射。加一条，选好本地源目录和 115 目标目录就能上传。</p>

          <div class="p115-panel cfg__danger" data-field="upload_delete_source">
            <div class="p115-panel__head">
              <div><h3 class="p115-section-title">上传后删除本地源文件</h3><p class="p115-hint">这是独立的破坏性操作，打开前需要再次确认。</p></div>
              <v-switch :model-value="config.upload_delete_source" color="error" density="compact" hide-details :label="config.upload_delete_source ? '已开启' : '已关闭'" @update:model-value="updateDeleteSource" />
            </div>
            <div class="p115-panel__body">
              <p class="p115-hint p115-hint--warn">上传确认成功后删除本地源文件。本地删除不进入 115 回收站，可能无法恢复。</p>
              <p v-for="message in errorsFor('upload_delete_source')" :key="message" class="cfg__field-error">{{ message }}</p>
            </div>
          </div>

          <button type="button" class="cfg__advanced" :aria-expanded="advanced.upload" @click="toggleAdvanced('upload')">
            <span><v-icon icon="mdi-tune-variant" size="16" aria-hidden="true" /> 高级设置</span>
            <v-icon :icon="advanced.upload ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="17" aria-hidden="true" />
          </button>
          <div v-if="advanced.upload" class="p115-panel cfg__advanced-panel">
            <div class="p115-panel__head"><div><h3 class="p115-section-title">冲突处理</h3><p class="p115-hint">上传记录与网盘同路径文件对不上时，决定下一步。</p></div></div>
            <div class="p115-panel__body">
              <v-select v-model="config.upload_conflict_policy" :items="conflictPolicies" label="上传身份冲突的处理方式" variant="outlined" density="compact" />
              <p class="p115-hint p115-hint--warn">“自动删掉网盘文件并重传”会先删除网盘上的现有文件；被删文件进入 115 回收站。</p>
              <button type="button" class="cfg__text-link" @click="goToExtensions">文件后缀统一在“生成 STRM → 文件识别规则”中设置</button>
            </div>
          </div>
        </section>

        <section v-else-if="section === 'automation'">
          <div class="p115-panel" data-field="checkin_time_range">
            <div class="p115-panel__head">
              <div><h3 class="p115-section-title">每日签到</h3><p class="p115-hint">每天在指定时间窗里随机挑一刻签到。</p></div>
              <v-switch v-model="config.checkin_enabled" color="primary" density="compact" hide-details :label="config.checkin_enabled ? '已开启' : '已关闭'" />
            </div>
            <div class="p115-panel__body">
              <v-text-field v-model="config.checkin_time_range" :error-messages="errorsFor('checkin_time_range')" label="随机时间窗" variant="outlined" density="compact" placeholder="06:00-09:00" />
            </div>
          </div>

          <div class="p115-panel" data-field="life_monitor_enabled">
            <div class="p115-panel__head">
              <div><h3 class="p115-section-title">网盘变化自动同步</h3><p class="p115-hint">115 出现上传、移动等变化时，自动增量更新 STRM。</p></div>
              <v-switch v-model="config.life_monitor_enabled" :disabled="lifeMonitorBlocked && !config.life_monitor_enabled" color="primary" density="compact" hide-details :label="config.life_monitor_enabled ? '已开启' : '已关闭'" />
            </div>
            <div class="p115-panel__body">
              <p v-if="lifeMonitorBlocked" class="p115-hint p115-hint--warn">{{ config.life_monitor_enabled ? '当前不会运行。先在生成 STRM 中填写并开启至少一条映射。' : '先在生成 STRM 中填写并开启至少一条映射。' }}</p>
              <p v-for="message in errorsFor('life_monitor_enabled')" :key="message" class="cfg__field-error">{{ message }}</p>
            </div>
          </div>

          <div class="p115-panel">
            <div class="p115-panel__head"><div><h3 class="p115-section-title">自动上传</h3><p class="p115-hint">沿用当前触发方式，不新增无法保存的模式。</p></div></div>
            <div class="p115-panel__body">
              <p class="p115-hint">插件已开启且有可用上传映射时，会监听本地源目录；MoviePilot 整理完成也会触发上传。</p>
            </div>
          </div>
        </section>

        <section v-else>
          <div class="p115-panel">
            <div class="p115-panel__head">
              <div><h3 class="p115-section-title">通知</h3><p class="p115-hint">选择哪些任务完成后发消息。</p></div>
              <v-switch :model-value="notification.enabled" color="primary" density="compact" hide-details :label="notification.enabled ? '已开启' : '已关闭'" @update:model-value="updateNotificationMaster" />
            </div>
            <div class="p115-panel__body">
              <NotifyRow :checked="notification.events.strm.checked" :type="notification.events.strm.type" :disabled="!notification.enabled" :types="notifyTypes" label="STRM 同步" hint="网盘删除通知当前跟随 STRM 同步通知。" @update:checked="value => updateNotificationChecked('strm', value)" @update:type="value => (notification.events.strm.type = value)" />
              <NotifyRow :checked="notification.events.upload.checked" :type="notification.events.upload.type" :disabled="!notification.enabled" :types="notifyTypes" label="上传" @update:checked="value => updateNotificationChecked('upload', value)" @update:type="value => (notification.events.upload.type = value)" />
              <NotifyRow :checked="notification.events.checkin.checked" :type="notification.events.checkin.type" :disabled="!notification.enabled" :types="notifyTypes" label="每日签到" @update:checked="value => updateNotificationChecked('checkin', value)" @update:type="value => (notification.events.checkin.type = value)" />
              <v-select v-if="notification.mode === 'unified' && notification.enabled && notificationCount" v-model="notification.unifiedType" :items="notifyTypes" class="cfg__notify-type" label="统一消息类型" variant="outlined" density="compact" />
              <p v-if="notification.enabled && !notificationCount" class="p115-hint p115-hint--warn">至少选择一个通知事件；不选择时保存后通知保持关闭。</p>
              <v-btn v-if="notification.mode === 'unified'" variant="text" size="small" @click="useSeparateNotifications">分别设置消息类型</v-btn>
            </div>
          </div>

          <button type="button" class="cfg__advanced" :aria-expanded="advanced.notify" @click="toggleAdvanced('notify')">
            <span><v-icon icon="mdi-tune-variant" size="16" aria-hidden="true" /> 分别设置类型</span>
            <v-icon :icon="advanced.notify ? 'mdi-chevron-up' : 'mdi-chevron-down'" size="17" aria-hidden="true" />
          </button>
          <div v-if="advanced.notify" class="p115-panel cfg__advanced-panel">
            <div class="p115-panel__head">
              <div><h3 class="p115-section-title">分别设置类型</h3><p v-if="notification.inconsistent" class="p115-hint p115-hint--warn">现有通知类型不同，已保留分别设置。</p></div>
              <v-btn variant="text" size="small" @click="useUnifiedNotifications">使用统一类型</v-btn>
            </div>
            <div class="p115-panel__body">
              <NotifyRow v-for="event in [{ key: 'strm', label: 'STRM 同步' }, { key: 'upload', label: '上传' }, { key: 'checkin', label: '每日签到' }]" :key="event.key" :checked="notification.events[event.key].checked" :type="notification.events[event.key].type" :disabled="!notification.enabled" :types="notifyTypes" show-type :label="event.label" @update:checked="value => updateNotificationChecked(event.key, value)" @update:type="value => (notification.events[event.key].type = value)" />
            </div>
          </div>
        </section>
      </div>
    </div>

    <footer class="cfg__foot">
      <span class="cfg__foot-note p115-muted">保存后立即生效，不用重启 MoviePilot。</span>
      <div class="cfg__foot-acts">
        <v-btn variant="text" size="small" :disabled="busy" @click="reload">放弃改动</v-btn>
        <v-btn color="primary" variant="flat" size="small" :loading="busy || saving" @click="save">保存配置</v-btn>
      </div>
    </footer>

    <QrLogin v-model="qrOpen" :api="api" @authenticated="reload" @error="notice.error" />
    <DirPicker v-model="pick.open" :api="api" :remote="pick.remote" :title="pick.title" @select="onPicked" @error="notice.error" />

    <v-dialog :model-value="confirm.open" max-width="460" persistent>
      <v-card class="p115-portal cfg-confirm">
        <v-card-title>确认开启删源</v-card-title>
        <v-card-text>上传确认成功后删除本地源文件。本地删除不进入 115 回收站，可能无法恢复。</v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" size="small" @click="resolveConfirmation(false)">取消</v-btn>
          <v-btn color="error" variant="flat" size="small" @click="resolveConfirmation(true)">确认开启删源</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped lang="scss">
.cfg { display: flex; flex-direction: column; }

.cfg__local {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  width: 100%; margin: 0; padding: 8px 16px; border: 0;
  border-bottom: 1px solid var(--p115-hairline); background: var(--p115-faint);
  color: inherit; font: inherit; font-size: 13px; text-align: left; cursor: pointer;
}
.cfg__local-dismiss { flex: 0 0 auto; font-size: 11px; color: var(--p115-muted); }
.cfg__local--error { color: rgb(var(--v-theme-error)); }
.cfg__local--success { color: rgb(var(--v-theme-success)); }

.cfg__shell {
  display: grid; grid-template-columns: 13rem minmax(0, 1fr); align-items: start;
  gap: 16px; padding: 16px;
}
.cfg__rail { display: flex; flex-direction: column; gap: 2px; position: sticky; top: 58px; }
.cfg__tab {
  display: flex; align-items: center; gap: 10px; padding: 9px 10px;
  border: 1px solid transparent; border-radius: 8px; background: transparent;
  color: var(--p115-muted); font: inherit; text-align: left; cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}
.cfg__tab:hover { background: var(--p115-faint); }
.cfg__tab:focus-visible, .cfg__advanced:focus-visible, .cfg__text-link:focus-visible {
  outline: 2px solid var(--p115-accent); outline-offset: 2px;
}
.cfg__tab--on { background: var(--p115-accent-soft); border-color: var(--p115-accent); color: var(--p115-accent); }
.cfg__tab-text { display: flex; flex-direction: column; min-width: 0; }
.cfg__tab-label { font-size: 13px; font-weight: 600; color: var(--p115-ink); line-height: 1.3; }
.cfg__tab--on .cfg__tab-label { color: var(--p115-accent); }
.cfg__tab-note { font-size: 11px; color: var(--p115-muted); line-height: 1.3; }
.cfg__pane { min-width: 0; }

.cfg__status-line { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.cfg__mapping { margin-top: 10px; }
.cfg__field-error { margin: 5px 12px 0; color: rgb(var(--v-theme-error)); font-size: 12px; line-height: 1.45; }

.cfg__advanced {
  width: 100%; display: flex; align-items: center; justify-content: space-between;
  margin: 14px 0 0; padding: 9px 10px; border: 1px solid var(--p115-hairline);
  border-radius: 8px; background: var(--p115-faint); color: var(--p115-muted);
  font: inherit; font-size: 13px; font-weight: 600; cursor: pointer;
}
.cfg__advanced > span { display: inline-flex; align-items: center; gap: 7px; }
.cfg__advanced-panel, .cfg__advanced-stack { margin-top: 10px; }
.cfg__advanced-stack { display: grid; gap: 18px; }
.cfg__advanced-stack .p115-panel + .p115-panel { margin-top: 0; }
.cfg__danger { margin-top: 18px; border-color: rgba(var(--v-theme-error), 0.42); }
.cfg__danger .p115-panel__head { border-left: 2px solid rgb(var(--v-theme-error)); }
.cfg__notify-type { max-width: 22rem; margin-top: 16px; }
.cfg__text-link {
  margin-top: 12px; padding: 0; border: 0; background: transparent; color: var(--p115-accent);
  font: inherit; font-size: 12px; cursor: pointer; text-align: left;
}

.cfg__foot {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 16px; border-top: 1px solid var(--p115-hairline); background: var(--p115-paper);
  position: sticky; bottom: 0; z-index: 2;
}
.cfg__foot-note { font-size: 12px; }
.cfg__foot-acts { display: flex; gap: 8px; margin-inline-start: auto; }
.cfg-confirm { background: rgb(var(--v-theme-surface)); }

@media (max-width: 720px) {
  .cfg__shell { grid-template-columns: minmax(0, 1fr); }
  .cfg__rail { position: static; flex-direction: row; overflow-x: auto; padding-bottom: 2px; }
  .cfg__tab { flex: 0 0 auto; }
  .cfg__tab-note, .cfg__foot-note { display: none; }
}
</style>
