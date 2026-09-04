<script setup>
import { computed, inject, onMounted, reactive, ref, watch } from 'vue'
import AppBar from './ui/AppBar.vue'
import Conduit from './ui/Conduit.vue'
import DirPicker from './ui/DirPicker.vue'
import NotifyRow from './ui/NotifyRow.vue'
import QrLogin from './ui/QrLogin.vue'
import { clone, newId, normalizeConfig, pluginGet, pluginPost, useHostNotice } from '../plugin.js'
import '../styles/kit.scss'

const props = defineProps({
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: [Object, Function], default: null },
  saving: { type: Boolean, default: false },
})
const emit = defineEmits(['save', 'close', 'switch', 'layout'])

const config = reactive(normalizeConfig())
const section = ref('link')
const busy = ref(false)
const local = reactive({ text: '', kind: 'info' })
const notice = useHostNotice(inject('moviepilot:toast', null), (text, kind) => {
  local.text = text
  local.kind = kind
})

const qrOpen = ref(false)
const pick = reactive({ open: false, remote: false, title: '', apply: null })

const connected = computed(() => Boolean(String(config.cookie || '').trim()))
const redirectModes = [
  { title: 'Cookie 取链', value: 'cookie' },
  { title: 'Open API 取链', value: 'open' },
]
const sections = computed(() => [
  { key: 'link', icon: 'mdi-link-variant', label: '连接', note: connected.value ? '已授权' : '待授权' },
  { key: 'strm', icon: 'mdi-transit-connection-variant', label: 'STRM 通道', note: `${config.strm_mappings.length} 条` },
  { key: 'upload', icon: 'mdi-tray-arrow-up', label: '上传通道', note: `${config.upload_mappings.length} 条` },
  { key: 'checkin', icon: 'mdi-calendar-check-outline', label: '每日签到', note: config.checkin_enabled ? '已开启' : '已关闭' },
])

function apply(value = {}) {
  Object.assign(config, normalizeConfig(value))
}

async function reload() {
  if (!props.api) return
  try {
    apply(await pluginGet(props.api, '/config'))
  } catch (error) {
    notice.error(error?.message || '配置读取失败')
  }
}

async function save() {
  if (!props.api) {
    emit('save', clone(config))
    return
  }
  busy.value = true
  try {
    const result = await pluginPost(props.api, '/config', clone(config))
    if (result.success) {
      notice.success(result.message || '配置已保存')
      emit('save', clone(config))
    } else {
      notice.error(result.message || '保存失败')
    }
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
    { key: 'target', tag: 'STRM 输出', icon: 'mdi-folder-outline', value: mapping.target_dir, placeholder: '点击选择本地目录' },
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
    openPicker('选择 STRM 输出目录', false, result => {
      mapping.target_dir = result.path
    })
  }
}

function pickUpload(mapping, key) {
  if (key === 'source') {
    openPicker('选择本地源目录', false, result => {
      mapping.source = result.path
    })
  } else if (key === 'target') {
    openPicker('选择 115 目标目录', true, result => {
      mapping.target = result.path
    })
  } else {
    openPicker('选择 STRM 输出目录', false, result => {
      mapping.strm_target = result.path
    })
  }
}

watch(() => props.initialConfig, apply, { immediate: true, deep: true })
onMounted(() => emit('layout', { maxWidth: '58rem' }))
</script>

<template>
  <div class="p115 cfg">
    <AppBar
      view="设置"
      :online="connected"
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
          <v-icon :icon="item.icon" size="17" />
          <span class="cfg__tab-text">
            <span class="cfg__tab-label">{{ item.label }}</span>
            <span class="cfg__tab-note">{{ item.note }}</span>
          </span>
        </button>
      </nav>

      <!-- key 跟着分区变：切换时这块重新挂载，入场动画重播一次。
           不用 <Transition>，因为 out-in 会给切换硬加一段离场延迟，
           而设置面板的手感应该是「立刻到」。 -->
      <div :key="section" class="cfg__pane p115-enter">
        <section v-if="section === 'link'">
          <div class="p115-panel">
            <div class="p115-panel__head">
              <div>
                <h3 class="p115-section-title">115 授权</h3>
                <p class="p115-hint">扫码后 Cookie 由后端写入，也可以手动粘贴已有的 Cookie。</p>
              </div>
              <v-btn color="primary" variant="flat" size="small" prepend-icon="mdi-qrcode-scan" @click="qrOpen = true">
                扫码登录
              </v-btn>
            </div>
            <div class="p115-panel__body">
              <v-text-field
                v-model="config.cookie"
                label="115 Cookie"
                type="password"
                variant="outlined"
                density="compact"
                hide-details
                autocomplete="off"
                placeholder="UID=...; CID=...; SEID=..."
              />
              <p class="p115-hint">Cookie 只存在 MoviePilot 本地，界面不回显明文。</p>
            </div>
          </div>

          <div class="p115-panel">
            <div class="p115-panel__head">
              <div>
                <h3 class="p115-section-title">播放地址</h3>
                <p class="p115-hint">写进 STRM 的回源地址，播放器要能连上。</p>
              </div>
            </div>
            <div class="p115-panel__body">
              <div class="p115-fields">
                <v-text-field
                  v-model="config.moviepilot_address"
                  label="MoviePilot 访问地址"
                  variant="outlined"
                  density="compact"
                  hide-details
                  placeholder="http://HOST:PORT"
                >
                  <template #append-inner>
                    <v-btn variant="text" size="x-small" @click="useThisSite">用当前站点</v-btn>
                  </template>
                </v-text-field>
                <v-select
                  v-model="config.link_redirect_mode"
                  :items="redirectModes"
                  label="取链方式"
                  variant="outlined"
                  density="compact"
                  hide-details
                />
              </div>
              <div class="p115-switches mt-2">
                <v-switch
                  v-model="config.enabled"
                  color="primary"
                  density="compact"
                  hide-details
                  label="启用插件"
                />
                <v-switch
                  v-model="config.same_playback"
                  color="primary"
                  density="compact"
                  hide-details
                  label="播放时同步 115 观看记录"
                />
                <v-switch
                  v-model="config.life_monitor_enabled"
                  color="primary"
                  density="compact"
                  hide-details
                  label="监听 115 生活事件，自动增量同步"
                />
              </div>
            </div>
          </div>
        </section>
        <section v-else-if="section === 'strm'">
          <div class="p115-panel">
            <div class="p115-panel__head">
              <div>
                <h3 class="p115-section-title">STRM 通道</h3>
                <p class="p115-hint">一条通道把一个 115 目录生成成本地 STRM。</p>
              </div>
              <v-btn variant="outlined" size="small" prepend-icon="mdi-plus" @click="addStrm">加一条通道</v-btn>
            </div>
            <div class="p115-panel__body">
              <div class="p115-switches">
                <v-switch
                  v-model="config.strm_incremental"
                  color="primary"
                  density="compact"
                  hide-details
                  label="只处理新增和变化的文件"
                />
                <v-switch
                  v-model="config.strm_download_sidecars"
                  color="primary"
                  density="compact"
                  hide-details
                  label="一并下载刮削文件和字幕"
                />
                <v-switch
                  v-model="config.strm_delete_cloud_on_missing"
                  color="primary"
                  density="compact"
                  hide-details
                  label="本地 STRM 删了，网盘上跟着删"
                />
              </div>
              <div v-if="config.strm_delete_cloud_on_missing" class="p115-subpanel">
                <p class="p115-hint p115-hint--warn">
                  本地 STRM 不见了就删掉 115 上对应的媒体、同名刮削文件与随之变空的目录（进 115
                  回收站，可人工还原）。媒体库未挂载、缺失比例过高时会整轮放弃，源目录与一级目录永不删除。
                </p>
                <p class="p115-hint">
                  从旧版本升级后请先跑一次「生成 STRM」补齐溯源信息，否则大部分文件会因为拿不到
                  115 文件 ID 而跳过。
                </p>
                <div class="p115-fields">
                  <v-text-field
                    v-model="config.strm_delete_sweep_cron"
                    label="巡检周期（cron 表达式，留空不巡检）"
                    variant="outlined"
                    density="compact"
                    hide-details
                    placeholder="37 */2 * * *"
                  />
                  <v-text-field
                    v-model.number="config.strm_delete_confirm_threshold"
                    type="number"
                    min="0"
                    label="一次要删超过这个数就先等你确认（0 = 不等）"
                    variant="outlined"
                    density="compact"
                    hide-details
                  />
                </div>
                <v-switch
                  v-model="config.strm_delete_watch"
                  color="primary"
                  density="compact"
                  hide-details
                  label="本地目录实时监听（网络挂载可能收不到）"
                />
                <p class="p115-hint">
                  实时监听只是加速：删除事件安静 30 秒后才上报。真正兜底的是定时巡检。
                </p>
              </div>
              <NotifyRow
                v-model:enabled="config.strm_notify"
                v-model:type="config.strm_notify_type"
                :types="config.notify_types"
                label="STRM 同步完成后发送通知"
                hint="每次同步完发一条，一条通道一行。"
              />
            </div>
          </div>

          <Conduit
            v-for="(mapping, index) in config.strm_mappings"
            :key="mapping.id"
            :enabled="mapping.enabled !== false"
            :stops="strmStops(mapping)"
            :index="index"
            @update:enabled="value => (mapping.enabled = value)"
            @pick="key => pickStrm(mapping, key)"
            @remove="drop(config.strm_mappings, index)"
          />
          <p v-if="!config.strm_mappings.length" class="p115-empty">
            还没有 STRM 通道。加一条，选好 115 源目录和本地输出目录就能同步。
          </p>
        </section>
        <section v-else-if="section === 'upload'">
          <div class="p115-panel">
            <div class="p115-panel__head">
              <div>
                <h3 class="p115-section-title">上传通道</h3>
                <p class="p115-hint">一条通道把一个本地目录传到 115。</p>
              </div>
              <v-btn variant="outlined" size="small" prepend-icon="mdi-plus" @click="addUpload">加一条通道</v-btn>
            </div>
            <div class="p115-panel__body">
              <div class="p115-switches">
                <v-switch
                  v-model="config.upload_include_sidecars"
                  color="primary"
                  density="compact"
                  hide-details
                  label="一并上传刮削文件和字幕"
                />
                <v-switch
                  v-model="config.upload_generate_strm"
                  color="primary"
                  density="compact"
                  hide-details
                  label="上传后生成 STRM"
                />
                <v-switch
                  v-model="config.upload_delete_source"
                  color="primary"
                  density="compact"
                  hide-details
                  label="上传成功后删除本地源文件"
                />
              </div>
              <div class="p115-fields mt-3">
                <v-textarea
                  v-model="config.upload_media_extensions"
                  label="媒体文件后缀"
                  variant="outlined"
                  density="compact"
                  rows="2"
                  auto-grow
                  hide-details
                />
                <v-textarea
                  v-model="config.upload_sidecar_extensions"
                  label="刮削文件后缀"
                  variant="outlined"
                  density="compact"
                  rows="2"
                  auto-grow
                  hide-details
                />
              </div>
              <p class="p115-hint">用英文逗号分隔，带上点号，例如 <span class="p115-mono">.mp4,.mkv</span>。</p>
              <NotifyRow
                v-model:enabled="config.upload_notify"
                v-model:type="config.upload_notify_type"
                :types="config.notify_types"
                label="上传完成后发送通知"
                hint="一部片子一条，带海报和这一季齐没齐。手动传和入库后自动传都算。"
              />
            </div>
          </div>

          <Conduit
            v-for="(mapping, index) in config.upload_mappings"
            :key="mapping.id"
            :enabled="mapping.enabled !== false"
            :stops="uploadStops(mapping)"
            :index="index"
            @update:enabled="value => (mapping.enabled = value)"
            @pick="key => pickUpload(mapping, key)"
            @remove="drop(config.upload_mappings, index)"
          />
          <p v-if="!config.upload_mappings.length" class="p115-empty">
            还没有上传通道。加一条，选好本地源目录和 115 目标目录就能上传。
          </p>
        </section>
        <section v-else>
          <div class="p115-panel">
            <div class="p115-panel__head">
              <div>
                <h3 class="p115-section-title">每日签到</h3>
                <p class="p115-hint">每天在这个时间段里随机挑一刻执行。</p>
              </div>
              <v-switch
                v-model="config.checkin_enabled"
                color="primary"
                density="compact"
                hide-details
                :label="config.checkin_enabled ? '已开启' : '已关闭'"
              />
            </div>
            <div class="p115-panel__body">
              <div class="p115-fields">
                <v-text-field
                  v-model="config.checkin_time_range"
                  label="随机时间窗"
                  variant="outlined"
                  density="compact"
                  hide-details
                  placeholder="06:00-09:00"
                />
              </div>
              <p class="p115-hint">留空按 06:00-09:00 处理。</p>
              <NotifyRow
                v-model:enabled="config.checkin_notify"
                v-model:type="config.checkin_notify_type"
                :types="config.notify_types"
                label="签到后发送通知"
                hint="签上了带积分和连续天数，没签上带原因。"
              />
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
    <DirPicker
      v-model="pick.open"
      :api="api"
      :remote="pick.remote"
      :title="pick.title"
      @select="onPicked"
      @error="notice.error"
    />
  </div>
</template>

<style scoped lang="scss">
.cfg {
  display: flex;
  flex-direction: column;
}

.cfg__local {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  margin: 0;
  padding: 8px 16px;
  border: 0;
  border-bottom: 1px solid var(--p115-hairline);
  background: var(--p115-faint);
  color: inherit;
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.cfg__local-dismiss {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--p115-muted);
}

.cfg__local--error {
  color: rgb(var(--v-theme-error));
}

.cfg__local--success {
  color: rgb(var(--v-theme-success));
}

.cfg__shell {
  display: grid;
  grid-template-columns: 13rem minmax(0, 1fr);
  align-items: start;
  gap: 16px;
  padding: 16px;
}

.cfg__rail {
  display: flex;
  flex-direction: column;
  gap: 2px;
  position: sticky;
  top: 58px;
}

.cfg__tab {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--p115-muted);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.cfg__tab:hover {
  background: var(--p115-faint);
}

.cfg__tab:focus-visible {
  outline: 2px solid var(--p115-accent);
  outline-offset: 1px;
}

.cfg__tab--on {
  background: var(--p115-accent-soft);
  border-color: var(--p115-accent);
  color: var(--p115-accent);
}
.cfg__tab-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.cfg__tab-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--p115-ink);
  line-height: 1.3;
}

.cfg__tab--on .cfg__tab-label {
  color: var(--p115-accent);
}

.cfg__tab-note {
  font-size: 11px;
  color: var(--p115-muted);
  line-height: 1.3;
}

.cfg__pane {
  min-width: 0;
}

.cfg__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  border-top: 1px solid var(--p115-hairline);
  background: var(--p115-paper);
  position: sticky;
  bottom: 0;
  z-index: 2;
}

.cfg__foot-note {
  font-size: 12px;
}

.cfg__foot-acts {
  display: flex;
  gap: 8px;
  margin-inline-start: auto;
}

@media (max-width: 720px) {
  .cfg__shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .cfg__rail {
    position: static;
    flex-direction: row;
    overflow-x: auto;
    padding-bottom: 2px;
  }

  .cfg__tab {
    flex: 0 0 auto;
  }

  .cfg__tab-note {
    display: none;
  }

  .cfg__foot-note {
    display: none;
  }
}

</style>
