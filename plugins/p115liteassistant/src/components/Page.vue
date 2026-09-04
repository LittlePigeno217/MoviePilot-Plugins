<script setup>
import { computed, inject, onMounted, reactive, ref, watch } from 'vue'
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
// 第一次 /status 回来之前不知道有没有记录，所以空态不能说「还没有」。
// ready = 问过了，failed = 问了但没答上来，两者都不该展示真空态文案。
const ready = ref(false)
const failed = ref(false)
const probeNote = computed(() =>
  failed.value ? '状态没读到。点右上角的刷新重试一次。' : '正在读取…',
)
const trusted = computed(() => ready.value && !failed.value)
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
// strm / upload / sweep 共用同一把 115 数据任务锁，任何一个在跑其它都起不来
const workingNow = computed(() =>
  running.value.some(kind => kind === 'strm' || kind === 'upload' || kind === 'sweep'),
)

// 反向删除：先看有没有实时监听，没有就看开关，关着就直说
const sweepValue = computed(() => {
  if (!status.value.strm_delete_enabled) return '未启用'
  return status.value.strm_delete_watch_running ? '监听中' : '仅巡检'
})

const pendingDeletes = computed(() => status.value.pending_deletes || [])

const kindNames = { strm: '生成 STRM', upload: '上传', checkin: '签到', strm_sweep: '网盘清理' }

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
    live: Boolean(status.value.life_monitor_running),
    hint: '',
  },
  {
    key: 'sweep',
    label: '网盘清理',
    value: sweepValue.value,
    ok: Boolean(status.value.strm_delete_enabled),
    live: Boolean(status.value.strm_delete_watch_running),
    hint: status.value.pending_sweep ? `${status.value.pending_sweep}排队中` : '',
  },
])

const actions = [
  { key: 'strm', label: '生成 STRM', icon: 'mdi-file-link-outline', path: '/strm/sync', payload: {} },
  { key: 'full', label: '全量上传', icon: 'mdi-tray-arrow-up', path: '/upload', payload: { incremental: false } },
  { key: 'inc', label: '增量上传', icon: 'mdi-tray-plus', path: '/upload', payload: { incremental: true } },
  { key: 'sweep', label: '清理网盘', icon: 'mdi-cloud-off-outline', path: '/strm/sweep', payload: {} },
  { key: 'checkin', label: '立即签到', icon: 'mdi-calendar-check-outline', path: '/checkin', payload: {} },
]

async function refresh() {
  if (!props.api) return
  busy.value = true
  try {
    status.value = await pluginGet(props.api, '/status')
    failed.value = false
  } catch (error) {
    failed.value = true
    notice.error(error?.message || '状态获取失败')
  } finally {
    busy.value = false
    ready.value = true
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

const deciding = ref('')
const expanded = ref('')
const detail = reactive({ id: '', total: 0, items: [], loading: false })

// 待确认删除：确认就真删，驳回只丢清单。两个动作都要防连点。
async function decidePending(batchIds, approve) {
  const ids = [].concat(batchIds)
  if (deciding.value || !ids.length) return
  deciding.value = ids.length > 1 ? 'all' : ids[0]
  try {
    const path = approve ? '/strm/sweep/confirm' : '/strm/sweep/dismiss'
    const result = await pluginPost(props.api, path, { batch_ids: ids })
    if (result.success) notice.success(result.message || (approve ? '已开始清理网盘' : '已忽略'))
    else notice.error(result.message || '操作未生效')
    if (ids.includes(expanded.value)) expanded.value = ''
    await refresh()
    emit('action')
  } catch (error) {
    notice.error(error?.message || '操作失败')
  } finally {
    deciding.value = ''
  }
}

// 删除前先看清单：整批的完整路径按页取，几百上千条也不至于一次灌进页面
async function loadDetail(batchId, append = false) {
  detail.loading = true
  try {
    const offset = append ? detail.items.length : 0
    const data = await pluginGet(props.api, '/strm/sweep/pending', { batch_id: batchId, offset, limit: 200 })
    const page = data?.data || data
    detail.id = batchId
    detail.total = Number(page?.total || 0)
    detail.items = append ? detail.items.concat(page?.items || []) : (page?.items || [])
  } catch (error) {
    notice.error(error?.message || '清单读取失败')
    detail.items = []
  } finally {
    detail.loading = false
  }
}

async function toggleDetail(batch) {
  if (expanded.value === batch.id) {
    expanded.value = ''
    return
  }
  expanded.value = batch.id
  await loadDetail(batch.id)
}

const pendingTotal = computed(() =>
  pendingDeletes.value.reduce((sum, batch) => sum + Number(batch.count || 0), 0),
)
const pendingIds = computed(() => pendingDeletes.value.map(batch => batch.id))

// 默认摊开第一批（等得最久的那批）。这个界面存在的意义就是让人真的看一眼清单，
// 所以不要求先点一下「查看清单」；其余批次仍然按需展开。
watch(pendingIds, ids => {
  if (expanded.value && !ids.includes(expanded.value)) expanded.value = ''
  if (!expanded.value && ids.length) toggleDetail({ id: ids[0] })
})

// 体积用等宽 + 定宽单位，好让一列数字对齐着扫
function bytes(value) {
  let left = Number(value) || 0
  if (left <= 0) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let unit = 0
  while (left >= 1024 && unit < units.length - 1) {
    left /= 1024
    unit += 1
  }
  const shown = unit === 0 || left >= 100 ? Math.round(left) : left.toFixed(1)
  return `${shown} ${units[unit]}`
}

// 网盘路径只留头尾：中间几层跟判断无关，末尾那个季目录才是「在库里的哪儿」
function shortDir(cloudPath) {
  const parts = String(cloudPath || '').split('/').filter(Boolean)
  if (parts.length <= 1) return '/'
  const dirs = parts.slice(0, -1)
  if (dirs.length <= 2) return `/${dirs.join('/')}`
  return `/${dirs[0]}/…/${dirs[dirs.length - 1]}`
}

// 路径分隔符不写字面反斜杠，省掉一层转义坑（宿主可能跑在 Windows 上）
const PATH_SEPARATORS = ['/', String.fromCharCode(92)]

function fileName(path) {
  let value = String(path || '')
  for (const separator of PATH_SEPARATORS) {
    const cut = value.lastIndexOf(separator)
    if (cut >= 0) value = value.slice(cut + 1)
  }
  return value
}

function shortTime(stamp) {
  return String(stamp || '').replace('T', ' ').slice(5, 16)
}

// 与通知层的 _duration_text 同一个写法：写「3.1 秒」而不是「3100ms」，毫秒是给日志看的
function seconds(ms) {
  const value = Number(ms)
  if (!Number.isFinite(value) || value <= 0) return ''
  if (value < 1000) return '不到 1 秒'
  const total = value / 1000
  if (total < 60) return `${total.toFixed(1)} 秒`
  const mins = Math.floor(total / 60)
  const rest = Math.round(total % 60)
  return rest ? `${mins} 分 ${rest} 秒` : `${mins} 分`
}

// 每种任务只汇报它自己有意义的那几个数，避免整排 0。词表与通知层共用一份：
// 刮削文件 / 清理 / 等你确认 / 网盘删了 / 对不上网盘文件 / 网盘上没了 —— 同一件事在
// 通知、运行台、设置三处只有一个名字。出事的那颗丸子着红，一眼能挑出来。
function tally(entry) {
  const pick = keys =>
    keys
      .filter(([, key]) => Number(entry[key]) > 0)
      .map(([label, key]) => ({ text: `${label} ${entry[key]}`, tone: key === 'errors' ? 'bad' : '' }))
  const plain = text => [{ text, tone: '' }]
  if (entry.kind === 'strm') {
    const parts = pick([['新增', 'added'], ['更新', 'updated'], ['清理', 'removed'], ['刮削文件', 'sidecars'], ['跳过', 'skipped'], ['同名', 'conflicts'], ['没生成', 'errors']])
    return parts.length ? parts : plain('已经是最新的')
  }
  if (entry.kind === 'upload') {
    const parts = pick([['上传', 'uploaded'], ['秒传', 'instant'], ['STRM', 'strm_generated'], ['跳过', 'skipped'], ['删除本地', 'deleted'], ['延后', 'deferred'], ['没传上', 'errors']])
    return parts.length ? parts : plain('没有变化')
  }
  if (entry.kind === 'strm_sweep') {
    const parts = pick([['网盘删了', 'cloud_deleted'], ['刮削文件', 'scrapes_deleted'], ['空文件夹', 'cloud_dirs_deleted'], ['等你确认', 'pending'], ['网盘上没了', 'already_gone'], ['对不上网盘文件', 'unidentified'], ['没删掉', 'errors']])
    if (parts.length) return parts
    return plain(entry.reason || '没有要删的')
  }
  if (entry.kind === 'checkin') {
    const parts = []
    if (entry.already) parts.push({ text: '今天已经签过了', tone: '' })
    if (Number(entry.continuous_day) > 0) parts.push({ text: `连续 ${entry.continuous_day} 天`, tone: '' })
    if (Number(entry.points_num) > 0) parts.push({ text: `+${entry.points_num} 积分`, tone: '' })
    return parts.length ? parts : plain(entry.message || '已签到')
  }
  return plain(entry.message || '已完成')
}

onMounted(refresh)
</script>

<template>
  <div class="p115 run">
    <AppBar
      view="运行台"
      :online="Boolean(status.authenticated)"
      :probing="!trusted"
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
      <div class="run__strip p115-enter">
        <div
          v-for="item in services"
          :key="item.key"
          class="svc"
          :class="{ 'svc--ok': trusted && item.ok, 'svc--live': trusted && item.live }"
        >
          <span class="svc__label p115-label">{{ item.label }}</span>
          <span class="svc__value">{{ ready ? item.value : '···' }}</span>
          <span v-if="trusted && item.hint" class="svc__hint">{{ item.hint }}</span>
        </div>
      </div>

      <div class="p115-panel p115-enter p115-enter--2">
        <div class="p115-panel__head">
          <div>
            <h3 class="p115-section-title">手动跑一次</h3>
            <p class="p115-hint">
              {{ !trusted ? probeNote : workingNow ? `正在跑：${running.map(kind => kindNames[kind] || kind).join('、')}` : '当前空闲，按需触发。' }}
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
              :disabled="workingNow || !trusted"
              @click="run(action)"
            >
              {{ action.label }}
            </v-btn>
          </div>
        </div>
      </div>

      <!-- 待审阅：本地已消失 / 115 上仍在的对账清单。整块保持冷静，只有提交按钮是热的 -->
      <section v-if="pendingDeletes.length" class="p115-panel pend p115-enter">
        <header class="pend__head">
          <div>
            <span class="p115-label">待你审阅</span>
            <h3 class="p115-section-title">本地已消失，网盘上还在</h3>
          </div>
          <div v-if="pendingDeletes.length > 1" class="pend__acts">
            <v-btn variant="text" size="small" :disabled="Boolean(deciding)" @click="decidePending(pendingIds, false)">
              全部保留
            </v-btn>
            <v-btn
              class="pend__commit"
              color="error"
              variant="outlined"
              size="small"
              :loading="deciding === 'all'"
              :disabled="Boolean(deciding) || workingNow"
              @click="decidePending(pendingIds, true)"
            >
              全部删除 {{ pendingTotal }} 个
            </v-btn>
          </div>
        </header>

        <article v-for="batch in pendingDeletes" :key="batch.id" class="pend__batch">
          <div class="pend__tally">
            <span class="p115-readout">{{ batch.count }}</span>
            <span class="pend__unit">个文件</span>
            <span v-if="bytes(batch.total_size)" class="pend__weight p115-mono">{{ bytes(batch.total_size) }}</span>
            <button
              type="button"
              class="pend__toggle"
              :aria-expanded="expanded === batch.id ? 'true' : 'false'"
              @click="toggleDetail(batch)"
            >
              {{ expanded === batch.id ? '收起清单' : '查看清单' }}
            </button>
          </div>
          <p class="pend__meta p115-mono">
            {{ batch.mapping }}<template v-if="batch.created_at"> · 发现于 {{ shortTime(batch.created_at) }}</template>
          </p>

          <div v-if="expanded === batch.id" class="pend__ledger">
            <div class="pend__ledger-head">
              <span>本地 STRM →</span>
              <span>网盘上的位置</span>
              <span class="pend__bytes">体积</span>
            </div>
            <p v-if="detail.loading && !detail.items.length" class="pend__state">读取清单…</p>
            <p v-else-if="!detail.items.length" class="pend__state">这批清单空了，下一轮巡检会重新统计。</p>
            <div v-else class="pend__rows">
              <div v-for="item in detail.items" :key="item.path" class="pend__pair">
                <span class="pend__gone p115-mono" :title="item.path">{{ fileName(item.path) }}</span>
                <span class="pend__where p115-mono" :title="item.cloud_path">{{ shortDir(item.cloud_path) }}</span>
                <span class="pend__bytes p115-mono">{{ bytes(item.size) }}</span>
              </div>
            </div>
            <div v-if="detail.items.length && detail.items.length < detail.total" class="pend__more">
              <span class="p115-mono">已看 {{ detail.items.length }} / {{ detail.total }}</span>
              <v-btn variant="text" size="small" :loading="detail.loading" @click="loadDetail(batch.id, true)">
                再看 {{ Math.min(200, detail.total - detail.items.length) }} 条
              </v-btn>
            </div>
          </div>

          <footer class="pend__foot">
            <div class="pend__acts">
              <v-btn variant="text" size="small" :disabled="Boolean(deciding)" @click="decidePending(batch.id, false)">
                保留
              </v-btn>
              <v-btn
                class="pend__commit"
                color="error"
                variant="flat"
                size="small"
                :loading="deciding === batch.id"
                :disabled="Boolean(deciding) || workingNow"
                @click="decidePending(batch.id, true)"
              >
                删除 {{ batch.count }} 个<template v-if="bytes(batch.total_size)"> · {{ bytes(batch.total_size) }}</template>
              </v-btn>
            </div>
          </footer>
        </article>

        <p class="pend__note">删掉的进 115 回收站，能在 115 上还原。</p>
      </section>

      <div class="p115-panel p115-enter p115-enter--3">
        <div class="p115-panel__head">
          <div>
            <h3 class="p115-section-title">最近上传</h3>
            <p class="p115-hint">标了「秒传」的那几部没有实际耗流量。</p>
          </div>
        </div>
        <div class="p115-panel__body">
          <p v-if="!trusted" class="p115-probe">{{ probeNote }}</p>
          <div v-else-if="visibleUploads.length" class="card-grid">
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

      <div class="p115-panel p115-enter p115-enter--4">
        <div class="p115-panel__head">
          <div>
            <h3 class="p115-section-title">执行记录</h3>
            <p class="p115-hint">最新的在最上面，只留最近几次。</p>
          </div>
        </div>
        <div class="p115-panel__body">
          <p v-if="!trusted" class="p115-probe">{{ probeNote }}</p>
          <div v-else-if="visibleHistory.length" class="log-grid">
            <div v-for="(entry, index) in visibleHistory" :key="`${entry.kind}-${entry.time}-${index}`" class="log-card">
              <div class="log-card__top">
                <span class="log-card__kind">{{ kindNames[entry.kind] || entry.kind }}</span>
                <span v-if="seconds(entry.duration_ms)" class="log-card__cost p115-mono">{{ seconds(entry.duration_ms) }}</span>
              </div>
              <div class="log-card__when p115-mono">{{ entry.time || '' }}</div>
              <div class="log-card__tally">
                <span
                  v-for="pill in tally(entry)"
                  :key="pill.text"
                  class="p115-pill"
                  :class="pill.tone ? `p115-pill--${pill.tone}` : ''"
                >{{ pill.text }}</span>
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
// 挂载时整条一起扫过一次 —— 520ms 正好盖住一次 /status 往返，于是「面板通电」
// 和「请求在路上」是同一个视觉事件，不需要再加转圈。
.svc::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  background: var(--p115-faint);
  transform-origin: left center;
  animation: p115-trace 520ms var(--p115-ease) both;
}

.svc--ok::before {
  background: var(--p115-accent);
}

// 正在监听的链路：底线退回浅色，由上面这条呼吸的线来表示「有信号在走」。
// 单独用 ::after 而不是给 ::before 叠第二个动画，是为了不和上面的 animation
// 简写抢 animation-delay。顺序敏感：这条必须排在 .svc--ok::before 之后。
.svc--live::before {
  background: var(--p115-faint);
}

.svc--live::after {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  background: var(--p115-accent);
  transform-origin: left center;
  animation:
    p115-trace 520ms var(--p115-ease) both,
    p115-breathe 3.2s ease-in-out 520ms infinite;
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

// ── 待你审阅（对账清单，不是告警）───────────────────────────────
// 这块是一张对账表：左边本地已经没了，右边 115 上还在。整块保持冷静 ——
// 竖着的 2px 线（对应服务条那条横线）表示「在等你决定」，红色只出现一次，
// 在真正不可逆的那个按钮上。
.pend {
  position: relative;
  padding: 16px 18px 14px 20px;
  border-left: 2px solid var(--p115-hold);
  background: var(--p115-hold-soft);
}

.pend__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.pend__head .p115-label {
  display: block;
  color: var(--p115-hold);
}

.pend__acts {
  display: flex;
  align-items: center;
  gap: 6px;
}

.pend__batch {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--p115-hairline);
}

// 先给出量级：个数与体积并排，都是等宽数字，看一眼就知道这次要动多少
.pend__tally {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.pend__unit {
  font-size: 12px;
  color: var(--p115-muted);
}

.pend__weight {
  color: var(--p115-muted);
}

.pend__weight::before {
  content: '·';
  margin-inline-end: 6px;
}

.pend__toggle {
  margin-inline-start: auto;
  padding: 0;
  border: 0;
  background: none;
  color: var(--p115-hold);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.pend__toggle:hover {
  text-decoration: underline;
}

.pend__meta {
  margin: 4px 0 0;
  color: var(--p115-muted);
}

// 清单主体：一行就是一次对账 —— 划掉的本地名 ⇄ 网盘上的位置 ⇄ 体积。
// 高度封顶 + contain，几百行也不让整页重新布局；不给行做逐条入场动画。
.pend__ledger {
  margin-top: 10px;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: var(--p115-paper);
  overflow: hidden;
  contain: content;
  animation: p115-rise 200ms var(--p115-ease) both;
}

.pend__ledger-head,
.pend__pair {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 76px;
  gap: 12px;
  align-items: baseline;
  padding: 6px 12px;
}

.pend__ledger-head {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: var(--p115-muted);
  border-bottom: 1px solid var(--p115-hairline);
}

// 285px ≈ 9.5 行：故意露出半行，让「下面还有」这件事不用额外说明。
.pend__rows {
  max-height: 285px;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.pend__pair + .pend__pair {
  border-top: 1px solid var(--p115-faint);
}

.pend__gone,
.pend__where {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

// 本地那一列压成弱色就够了 —— 标题已经说过「本地已消失」，再加删除线是把
// 最需要认片名的那一列牺牲掉换一个重复的语义。
.pend__gone {
  color: var(--p115-muted);
}

.pend__where {
  color: var(--p115-ink);
}

.pend__bytes {
  text-align: right;
  color: var(--p115-muted);
}

.pend__state {
  margin: 0;
  padding: 14px 12px;
  font-size: 12px;
  color: var(--p115-muted);
}

.pend__more {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 6px 4px 12px;
  border-top: 1px solid var(--p115-hairline);
  color: var(--p115-muted);
}

.pend__foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 10px;
}

// 整块只说一次：回收站这件事对所有批次都一样，重复一遍只是噪音
.pend__note {
  margin: 12px 0 0;
  font-size: 11px;
  color: var(--p115-muted);
}

.pend__commit {
  font-variant-numeric: tabular-nums;
}

// 窄屏：一行拆成两行 —— 上行「文件名 + 体积」，下行网盘上的位置。
// 三个格子必须显式定位，否则自动流会把体积挤到第三行单独占一行。
@media (max-width: 560px) {
  .pend__ledger-head {
    display: none;
  }

  .pend__pair {
    grid-template-columns: minmax(0, 1fr) 76px;
    row-gap: 1px;
    padding-block: 7px;
  }

  .pend__gone {
    grid-area: 1 / 1 / 2 / 2;
  }

  .pend__bytes {
    grid-area: 1 / 2 / 2 / 3;
  }

  .pend__where {
    grid-area: 2 / 1 / 3 / 3;
    font-size: 11px;
  }
}


// ── 执行记录（卡片式，简约）───────────────────────────────────
.log-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
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
  font-size: 12px;
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
}

@media (max-width: 620px) {
  .card-grid,
  .log-grid {
    grid-template-columns: 1fr;
  }
}



</style>
