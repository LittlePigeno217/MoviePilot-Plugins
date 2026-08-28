<script setup>
import { computed, inject, onMounted, reactive, ref } from 'vue'
import AppBar from './ui/AppBar.vue'
import { pluginGet, pluginPost, useHostNotice } from '../plugin.js'
import '../styles/kit.scss'

const props = defineProps({
  api: { type: [Object, Function], default: null },
  show_switch: { type: Boolean, default: false },
})
const emit = defineEmits(['switch', 'close', 'action'])

const status = ref({ running: [], recent_uploads: [], history: [] })
const busy = ref(false)
const local = reactive({ text: '', kind: 'info' })
const notice = useHostNotice(inject('moviepilot:toast', null), (text, kind) => {
  local.text = text
  local.kind = kind
})

const uploads = computed(() => status.value.recent_uploads || [])
const visibleUploads = computed(() => uploads.value.slice(0, 10))
const history = computed(() => status.value.history || [])
// 执行记录：只显示最近 6 条（卡片式，节约空间）
const visibleHistory = computed(() => history.value.slice(0, 6))
const running = computed(() => status.value.running || [])
const workingNow = computed(() => running.value.some(kind => kind === 'strm' || kind === 'upload'))

const kindNames = { strm: '生成 STRM', upload: '上传', checkin: '签到' }

// 服务条：每一项都是“现在能不能干活”的答案，不是装饰性的计数
const services = computed(() => [
  {
    key: 'auth',
    label: '115 授权',
    value: status.value.authenticated ? '已连接' : '未登录',
    ok: Boolean(status.value.authenticated),
    hint: status.value.authenticated ? '' : '去设置里扫码登录',
  },
  {
    key: 'strm',
    label: 'STRM 通道',
    value: `${status.value.strm_mappings || 0} 条`,
    ok: Boolean(status.value.strm_mappings),
    hint: status.value.strm_mappings ? '' : '还没有配置通道',
  },
  {
    key: 'upload',
    label: '上传通道',
    value: `${status.value.upload_mappings || 0} 条`,
    ok: Boolean(status.value.upload_mappings),
    hint: status.value.upload_mappings ? '' : '还没有配置通道',
  },
  {
    key: 'life',
    label: '生活事件',
    value: status.value.life_monitor_running ? '监听中' : status.value.life_monitor_enabled ? '等待启动' : '未启用',
    ok: Boolean(status.value.life_monitor_running),
    hint: '',
  },
])

const actions = [
  { key: 'strm', label: '生成 STRM', icon: 'mdi-file-link-outline', path: '/strm/sync', payload: {} },
  { key: 'full', label: '全量上传', icon: 'mdi-tray-arrow-up', path: '/upload', payload: { incremental: false } },
  { key: 'inc', label: '增量上传', icon: 'mdi-tray-plus', path: '/upload', payload: { incremental: true } },
  { key: 'checkin', label: '立即签到', icon: 'mdi-calendar-check-outline', path: '/checkin', payload: {} },
]

async function refresh() {
  if (!props.api) return
  busy.value = true
  try {
    status.value = await pluginGet(props.api, '/status')
  } catch (error) {
    notice.error(error?.message || '状态获取失败')
  } finally {
    busy.value = false
  }
}

async function run(action) {
  try {
    const result = await pluginPost(props.api, action.path, action.payload)
    if (result.success) notice.success(result.message || `${action.label}已开始`)
    else notice.error(result.message || `${action.label}未能开始`)
    await refresh()
    emit('action')
  } catch (error) {
    notice.error(error?.message || `${action.label}失败`)
  }
}

function seconds(ms) {
  const value = Number(ms)
  if (!Number.isFinite(value) || value <= 0) return ''
  return value < 1000 ? `${value}ms` : `${(value / 1000).toFixed(1)}s`
}

// 每种任务只汇报它自己有意义的那几个数，避免整排 0
function tally(entry) {
  const pick = keys => keys.filter(([, key]) => Number(entry[key]) > 0).map(([label, key]) => `${label} ${entry[key]}`)
  if (entry.kind === 'strm') {
    const parts = pick([['新增', 'added'], ['更新', 'updated'], ['清理', 'removed'], ['附加', 'sidecars'], ['跳过', 'skipped'], ['冲突', 'conflicts'], ['失败', 'errors']])
    return parts.length ? parts : ['没有变化']
  }
  if (entry.kind === 'upload') {
    const parts = pick([['上传', 'uploaded'], ['秒传', 'instant'], ['STRM', 'strm_generated'], ['跳过', 'skipped'], ['删除', 'deleted'], ['延后', 'deferred'], ['失败', 'errors']])
    return parts.length ? parts : ['没有变化']
  }
  if (entry.kind === 'checkin') {
    const parts = []
    if (entry.already) parts.push('今天已签过')
    if (Number(entry.continuous_day) > 0) parts.push(`连续 ${entry.continuous_day} 天`)
    if (Number(entry.points_num) > 0) parts.push(`+${entry.points_num} 积分`)
    return parts.length ? parts : [entry.message || '已签到']
  }
  return [entry.message || '已完成']
}

onMounted(refresh)
</script>

<template>
  <div class="p115 run">
    <AppBar
      view="运行台"
      :online="Boolean(status.authenticated)"
      :show-switch="show_switch"
      :busy="busy"
      show-refresh
      @refresh="refresh"
      @switch="emit('switch')"
      @close="emit('close')"
    />

    <button v-if="local.text" type="button" class="run__local" :class="`run__local--${local.kind}`" @click="local.text = ''">
      {{ local.text }}
      <span class="run__local-dismiss">知道了</span>
    </button>

    <div class="run__body">
      <div class="run__strip">
        <div v-for="item in services" :key="item.key" class="svc" :class="{ 'svc--ok': item.ok }">
          <span class="svc__label p115-endpoint-tag">{{ item.label }}</span>
          <span class="svc__value">{{ item.value }}</span>
          <span v-if="item.hint" class="svc__hint">{{ item.hint }}</span>
        </div>
      </div>

      <div class="p115-panel">
        <div class="p115-panel__head">
          <div>
            <h3 class="p115-section-title">手动跑一次</h3>
            <p class="p115-hint">
              {{ workingNow ? `正在跑：${running.map(kind => kindNames[kind] || kind).join('、')}` : '当前空闲，按需触发。' }}
            </p>
          </div>
        </div>
        <div class="p115-panel__body">
          <div class="run__acts">
            <v-btn
              v-for="action in actions"
              :key="action.key"
              class="run__act"
              variant="outlined"
              size="small"
              :prepend-icon="action.icon"
              :disabled="workingNow"
              @click="run(action)"
            >
              {{ action.label }}
            </v-btn>
          </div>
        </div>
      </div>

      <div class="p115-panel">
        <div class="p115-panel__head">
          <div>
            <h3 class="p115-section-title">最近上传</h3>
            <p class="p115-hint">最新 {{ visibleUploads.length }} 部，标了「秒传」的没有实际耗流量。</p>
          </div>
        </div>
        <div class="p115-panel__body">
          <div v-if="visibleUploads.length" class="card-grid">
            <div v-for="item in visibleUploads" :key="`${item.path}-${item.uploaded_at}`" class="card">
              <span class="card__name" :title="item.name">{{ item.name }}</span>
              <span class="card__meta">
                <span class="card__when p115-mono">{{ item.uploaded_at }}</span>
                <span class="card__tag" :class="{ 'card__tag--instant': item.method === 'instant' }">
                  {{ item.method === 'instant' ? '秒传' : '上传' }}
                </span>
              </span>
            </div>
          </div>
          <p v-else class="p115-empty">还没有上传记录。配好上传通道后跑一次全量上传就会出现在这里。</p>
        </div>
      </div>

      <div class="p115-panel">
        <div class="p115-panel__head">
          <div>
            <h3 class="p115-section-title">执行记录</h3>
            <p class="p115-hint">最近 {{ visibleHistory.length }} 条，最新的在最上面。</p>
          </div>
        </div>
        <div class="p115-panel__body">
          <div v-if="visibleHistory.length" class="log-grid">
            <div v-for="(entry, index) in visibleHistory" :key="`${entry.kind}-${entry.time}-${index}`" class="log-card">
              <div class="log-card__top">
                <span class="log-card__kind">{{ kindNames[entry.kind] || entry.kind }}</span>
                <span v-if="seconds(entry.duration_ms)" class="log-card__cost p115-mono">{{ seconds(entry.duration_ms) }}</span>
              </div>
              <div class="log-card__when p115-mono">{{ entry.time || '' }}</div>
              <div class="log-card__tally">
                <span v-for="text in tally(entry)" :key="text" class="log-card__chip">{{ text }}</span>
              </div>
            </div>
          </div>
          <p v-else class="p115-empty">还没有执行记录。跑一次任务后这里会记下每次的结果。</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.run {
  display: flex;
  flex-direction: column;
}

.run__local {
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

.run__local-dismiss {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--p115-muted);
}

.run__local--error {
  color: rgb(var(--v-theme-error));
}

.run__local--success {
  color: rgb(var(--v-theme-success));
}

.run__body {
  padding: 18px 18px 24px;
}

// ── 服务条（签名亮点：顶部状态细线）───────────────────────────────
.run__strip {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  margin-bottom: 18px;
}

.svc {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 14px 14px 12px;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: var(--p115-paper);
  overflow: hidden;
}

// 签名：顶部 2px 状态细线。亮 = 该链路正常（primary 色），灰 = 未就绪。
.svc::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  background: var(--p115-faint);
}

.svc--ok::before {
  background: var(--p115-accent);
}

.svc__label {
  color: var(--p115-muted);
}

.svc__value {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.svc--ok .svc__value {
  color: var(--p115-ink);
}

.svc__hint {
  font-size: 11px;
  color: var(--p115-muted);
}

// ── 手动跑一次按钮区（简约：主按钮实心，间距放大）────────────────
.run__acts {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.run__act {
  min-width: 0;
}

.haul {
  margin: 0;
  padding: 0;
  list-style: none;
}

.haul__row:first-child {
  border-top: 0;
}

// ── 卡片网格（最近上传，简约）───────────────────────────────────
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.card {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 12px 14px;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: var(--p115-paper);
  min-width: 0;
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
}

.card:hover {
  border-color: var(--p115-muted);
  box-shadow: var(--p115-shadow);
}

.card__name {
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.4;
}

.card__meta {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--p115-muted);
}

.card__when {
  white-space: nowrap;
}

.card__tag {
  padding: 1px 8px;
  border: 1px solid var(--p115-hairline);
  border-radius: 999px;
  font-size: 10px;
  line-height: 1.5;
  white-space: nowrap;
}

.card__tag--instant {
  border-color: var(--p115-accent);
  color: var(--p115-accent);
}

// ── 执行记录（卡片式，简约）───────────────────────────────────
.log-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}

.log-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 11px 13px;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: var(--p115-paper);
  min-width: 0;
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
}

.log-card:hover {
  border-color: var(--p115-muted);
  box-shadow: var(--p115-shadow);
}

.log-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.log-card__kind {
  font-size: 12px;
  font-weight: 700;
  color: var(--p115-accent);
  white-space: nowrap;
}

.log-card__cost {
  color: var(--p115-muted);
  white-space: nowrap;
}

.log-card__when {
  color: var(--p115-muted);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.log-card__tally {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  font-size: 11px;
}

.log-card__chip {
  padding: 1px 7px;
  border: 1px solid var(--p115-hairline);
  border-radius: 999px;
  background: var(--p115-faint);
  white-space: nowrap;
}

@media (max-width: 620px) {
  .card-grid,
  .log-grid {
    grid-template-columns: 1fr;
  }
}



</style>
