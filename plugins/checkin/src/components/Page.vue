<script setup>
// 自用签到 · 运行台。接口契约不变：/status 拉状态、/run 立即签到、
// /test-login 测连通、/history/clear 清历史。
import { computed, inject, onMounted, reactive, ref } from 'vue'
import AppBar from './ui/AppBar.vue'
import Tape from './ui/Tape.vue'
import { SITE_META, pluginGet, pluginPost, useHostNotice } from '../plugin.js'
import {
  catchupNote,
  rankOf,
  runTally,
  runVerdict,
  shortTime,
  siteRow,
  streakOf,
  tapeOf,
  todayVerdict,
} from '../lib/ledger.js'
import '../styles/kit.scss'

const props = defineProps({
  api: { type: [Object, Function], default: null },
  show_switch: { type: Boolean, default: true },
})
const emit = defineEmits(['switch', 'close', 'action'])

const status = ref({ sites: [], history: [] })
// 第一次 /status 还没回来时不替用户下结论：读数显示占位，不显示「未启用」。
// ready = 问过了，failed = 问了但没答上来，两者都不该展示真空态文案 —— 以前 probed 在
// finally 里无条件置真，于是「状态读失败」会显示成「还没有执行记录」，把读不到说成没有。
const probed = ref(false)
const failed = ref(false)
const probeNote = computed(() =>
  failed.value ? '状态没读到。点右上角的刷新重试一次。' : '正在读取…',
)
const trusted = computed(() => probed.value && !failed.value)
const busy = reactive({ load: false, run: false, test: false, clear: false })
const local = reactive({ text: '', kind: 'info' })
const notice = useHostNotice(inject('moviepilot:toast', null), (text, kind) => {
  local.text = text
  local.kind = kind
})

const history = computed(() => status.value.history || [])
const visibleHistory = computed(() => history.value.slice(0, 6))
const sites = computed(() => (status.value.sites || []).filter(site => site.enabled))
const verdict = computed(() => todayVerdict(status.value))
const streak = computed(() => streakOf(history.value))
const tape = computed(() => tapeOf(history.value, 30))
const catchup = computed(() => catchupNote(status.value))

const TONE = { 3: 'on', 2: 'warn', 1: 'bad', 0: '' }
const CHIP = { 3: 'ck-pill--on', 2: 'ck-pill--warn', 1: 'ck-pill--bad', 0: '' }

// 四格读数：与 115 轻量助手的服务条同构 —— 小标签、一个值、必要时一句补充
const readouts = computed(() => {
  const enabledCount = Number(status.value.enabled_site_count) || 0
  const readyCount = Number(status.value.configured_site_count) || 0
  const missing = enabledCount - readyCount
  return [
    {
      key: 'streak',
      label: '连续',
      value: probed.value ? `${streak.value} 天` : '···',
      tone: streak.value ? 'on' : '',
    },
    {
      key: 'next',
      label: '下次',
      value: probed.value ? status.value.next_run_time || '—' : '···',
      hint: probed.value && !status.value.enabled ? '插件已关闭' : '',
      tone: status.value.enabled ? 'on' : '',
    },
    {
      key: 'last',
      label: '上次',
      value: probed.value ? shortTime(status.value.last_run) : '···',
      tone: TONE[rankOf(status.value.last_status)],
    },
    {
      key: 'sites',
      label: '站点',
      value: probed.value ? `${readyCount} / ${enabledCount}` : '···',
      hint: missing > 0 ? `${missing} 个待填写` : '',
      tone: missing > 0 ? 'warn' : enabledCount ? 'on' : '',
    },
  ]
})

const barState = computed(() => {
  if (!probed.value) return '正在读取…'
  if (!status.value.enabled) return '未启用'
  if (!status.value.configured) return '配置待完善'
  return verdict.value.headline
})
const barTone = computed(() => {
  if (!probed.value || !status.value.enabled) return 'idle'
  if (!status.value.configured) return 'warn'
  return TONE[verdict.value.rank] || 'idle'
})

const chip = text => CHIP[rankOf(text)]
// 记录卡三段的内容都由 ledger.js 算好，模板只负责摆
const verdictOf = entry => runVerdict(entry)
const tallyOf = entry => runTally(entry)
// 站点面板那一行和记录展开里的行是同一个东西，只是数据来自 /status 的站点对象
const rowOf = site =>
  siteRow({
    site_name: site.name,
    status: site.last_status,
    message: site.last_message,
    reward_mb: site.reward_mb,
    total_traffic: site.total_traffic,
  })
const badge = key => SITE_META[key]?.badge || '·'

async function refresh() {
  busy.load = true
  try {
    status.value = await pluginGet(props.api, '/status')
    failed.value = false
  } catch (error) {
    failed.value = true
    notice.error(error?.message || '状态没读到')
  } finally {
    busy.load = false
    probed.value = true
  }
}

async function call(key, path, fallback) {
  busy[key] = true
  try {
    const result = await pluginPost(props.api, path)
    if (result.success) notice.success(result.message || fallback)
    else notice.error(result.message || fallback)
    await refresh()
    emit('action')
  } catch (error) {
    notice.error(error?.message || fallback)
  } finally {
    busy[key] = false
  }
}

const punch = () => call('run', '/run', '签到已执行')
const test = () => call('test', '/test-login', '连通性测试完成')

// 清空历史不可撤销：先确认再执行，3 秒没二次点击就复位
const clearConfirm = ref(false)
let clearTimer = 0
const wipe = () => {
  if (!clearConfirm.value) {
    clearConfirm.value = true
    clearTimer = window.setTimeout(() => (clearConfirm.value = false), 3000)
    return
  }
  window.clearTimeout(clearTimer)
  clearConfirm.value = false
  call('clear', '/history/clear', '历史已清空')
}

onMounted(refresh)
</script>

<template>
  <div class="ck run">
    <AppBar
      view="运行台"
      :state="barState"
      :tone="barTone"
      :show-switch="show_switch"
      :busy="busy.load"
      show-refresh
      @refresh="refresh"
      @switch="emit('switch')"
      @close="emit('close')"
    />

    <button
      v-if="local.text"
      type="button"
      class="run__local"
      :class="`run__local--${local.kind}`"
      @click="local.text = ''"
    >
      {{ local.text }}
      <span class="run__local-x">知道了</span>
    </button>

    <div class="run__body">
      <!-- ── 招牌：一个月的打卡带，今天那一格就是签到按钮 ── -->
      <section class="ck-panel ck-enter">
        <div class="ck-panel__body run__lede">
          <Tape :cells="tape" :busy="busy.run" :disabled="!status.enabled" @punch="punch" />

          <div class="lede__row">
            <span class="lede__verdict">
              <span class="lede__tag" :class="`lede__tag--${TONE[verdict.rank] || 'idle'}`">
                {{ verdict.headline }}
              </span>
              <span class="lede__note">{{ verdict.detail }}</span>
            </span>

            <span class="lede__acts">
              <v-btn
                color="primary"
                variant="flat"
                size="small"
                :loading="busy.run"
                :disabled="!status.enabled"
                @click="punch"
              >
                <v-icon start icon="mdi-calendar-check" size="16" />
                签到
              </v-btn>
              <v-btn variant="outlined" size="small" :loading="busy.test" @click="test">
                <v-icon start icon="mdi-connection" size="16" />
                测试
              </v-btn>
              <v-btn
                class="act--danger"
                :class="{ 'act--armed': clearConfirm }"
                variant="outlined"
                size="small"
                :loading="busy.clear"
                :disabled="!history.length"
                @click="wipe"
              >
                <v-icon start :icon="clearConfirm ? 'mdi-alert' : 'mdi-trash-can-outline'" size="16" />
                {{ clearConfirm ? '确认清空？' : '清空' }}
              </v-btn>
            </span>
          </div>
        </div>
      </section>

      <!-- ── 四格读数：顶部细线扫过一次，代表这一格的读数刚建立 ── -->
      <div class="run__strip ck-enter ck-enter--2">
        <div
          v-for="item in readouts"
          :key="item.key"
          class="dial ck-lined"
          :class="item.tone ? `ck-lined--${item.tone}` : ''"
        >
          <span class="dial__label ck-label">{{ item.label }}</span>
          <span class="dial__value ck-mono">{{ item.value }}</span>
          <span v-if="item.hint" class="dial__hint">{{ item.hint }}</span>
        </div>
      </div>

      <!-- ── 漏签待补：左边一条竖线，表示这块在等一件事发生 ── -->
      <section v-if="catchup" class="hold ck-enter" :class="{ 'hold--bad': catchup.tone === 'bad' }">
        <span class="hold__tag ck-label">漏签待补</span>
        <h3 class="ck-section-title">{{ catchup.headline }}</h3>
        <p class="ck-hint">{{ catchup.detail }}</p>
      </section>

      <!-- ── 站点 ── -->
      <section class="ck-panel ck-enter ck-enter--3">
        <div class="ck-panel__head">
          <h3 class="ck-section-title">站点</h3>
          <p class="ck-hint">一行一个已启用的站点，写它上一次的结果。</p>
        </div>
        <div class="ck-panel__body">
          <ul v-if="sites.length" class="sites">
            <li v-for="site in sites" :key="site.key" class="site">
              <span class="site__badge ck-mono" aria-hidden="true">{{ badge(site.key) }}</span>
              <span class="site__id">
                <span class="site__name">{{ site.name }}</span>
                <span class="site__acct ck-mono">{{ site.account || '未填账号' }}</span>
              </span>
              <span class="site__tags">
                <span class="ck-pill">{{ site.mode }}</span>
                <span v-if="site.use_proxy" class="ck-pill">代理</span>
                <span v-if="!site.configured" class="ck-pill ck-pill--warn">待填写</span>
              </span>
              <span class="site__result">
                <span class="detail__mark" :class="`detail__mark--${rowOf(site).tone}`" aria-hidden="true">
                  {{ rowOf(site).mark }}
                </span>
                <span class="site__msg">{{ rowOf(site).note }}</span>
              </span>
              <span class="site__when ck-mono">{{ shortTime(site.last_run) }}</span>
            </li>
          </ul>
          <p v-else-if="!trusted" class="ck-probe">{{ probeNote }}</p>
          <p v-else class="ck-empty">
            还没有启用站点。去设置里打开一个站点、填好账号，这里就会出现它的签到行。
          </p>
        </div>
      </section>

      <!-- ── 执行记录：与 115 轻量助手的记录卡同构，多的只是可以展开 ── -->
      <section class="ck-panel ck-enter ck-enter--4">
        <div class="ck-panel__head">
          <h3 class="ck-section-title">执行记录</h3>
          <p class="ck-hint">最新的在最上面，只留最近几次。展开看每个站点的回复。</p>
        </div>
        <div class="ck-panel__body">
          <div v-if="visibleHistory.length" class="log-grid">
            <details
              v-for="(entry, index) in visibleHistory"
              :key="`${entry.time}-${index}`"
              class="log-card"
              :open="index === 0"
            >
              <summary class="log-card__sum">
                <span class="log-card__top">
                  <span class="log-card__kind" :class="`log-card__kind--${verdictOf(entry).tone || 'idle'}`">
                    {{ verdictOf(entry).text }}
                  </span>
                  <span class="log-card__cost ck-mono">{{ entry.site_count }} 个站点</span>
                </span>
                <span class="log-card__when ck-mono">{{ entry.time }}</span>
                <span class="log-card__tally">
                  <span
                    v-for="pill in tallyOf(entry)"
                    :key="pill.text"
                    class="ck-pill"
                    :class="pill.tone ? `ck-pill--${pill.tone}` : ''"
                  >{{ pill.text }}</span>
                </span>
              </summary>
              <ul class="detail">
                <li v-for="(item, di) in entry.details" :key="di" class="detail__row">
                  <span class="detail__mark" :class="`detail__mark--${siteRow(item).tone}`" aria-hidden="true">
                    {{ siteRow(item).mark }}
                  </span>
                  <span class="detail__site">{{ siteRow(item).name }}</span>
                  <span class="detail__note">{{ siteRow(item).note }}</span>
                </li>
              </ul>
            </details>
          </div>
          <p v-else-if="!trusted" class="ck-probe">{{ probeNote }}</p>
          <p v-else class="ck-empty">还没有执行记录。按一次「签到」，这里就会记下每个站点的回复。</p>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped lang="scss">
// 宿主缺席时的本地提示条（独立联调用）
.run__local {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  margin: 0;
  padding: 6px 16px;
  border: 0;
  border-bottom: 1px solid var(--ck-line);
  background: var(--ck-faint);
  color: inherit;
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.run__local-x {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--ck-ink-50);
}

.run__local--error {
  color: var(--ck-bad);
}

.run__local--success {
  color: var(--ck-ok);
}

.run__body {
  padding: 18px 18px 24px;
}

// ── 招牌 ────────────────────────────────────────────────────────────
.run__lede {
  padding-top: 16px;
  display: grid;
  gap: 14px;
}

.lede__row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px 16px;
}

.lede__verdict {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.lede__tag {
  justify-self: start;
  padding: 1px 8px;
  border: 1px solid var(--ck-line-strong);
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.6;
  white-space: nowrap;
  color: var(--ck-ink-70);
}

.lede__tag--on {
  color: var(--ck-accent);
  border-color: var(--ck-accent-line);
  background: var(--ck-accent-soft);
}

.lede__tag--warn {
  color: var(--ck-warn);
  border-color: var(--ck-warn-line);
  background: var(--ck-warn-soft);
}

.lede__tag--bad {
  color: var(--ck-bad);
  border-color: var(--ck-bad-line);
  background: var(--ck-bad-soft);
}

.lede__note {
  margin: 0;
  font-size: 12px;
  color: var(--ck-ink-50);
}

.lede__acts {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-inline-start: auto;
}

// 清空是不可撤销操作：平时中性，hover 与待确认时才变警示色
.ck .act--danger {
  color: var(--ck-ink-50);
  border-color: var(--ck-line-strong);
  transition: color 0.15s ease, border-color 0.15s ease, background-color 0.15s ease;
}

.ck .act--danger:hover:not(:disabled),
.ck .act--armed {
  color: var(--ck-bad);
  border-color: var(--ck-bad);
  background: var(--ck-bad-soft);
}

// ── 四格读数 ────────────────────────────────────────────────────────
.run__strip {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  margin: 18px 0;
}

.dial {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 14px 14px 12px;
  border: 1px solid var(--ck-line);
  border-radius: var(--ck-radius-sm);
  background: var(--ck-paper);
}

.dial__value {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.dial__hint {
  font-size: 11px;
  color: var(--ck-ink-50);
}

// ── 漏签待补：竖线在左，说明这块在等一件事发生 ──────────────────────
// 与 115 轻量助手的「待你审阅」块同一个形制：左侧 2px 竖线 + 极淡底，颜色用 info
// 不用红 —— 等一件事发生不是报错。两个插件的这一块必须长一个样。
.hold {
  margin: 0 0 18px;
  padding: 16px 18px 14px 20px;
  border-left: 2px solid var(--ck-hold);
  background: var(--ck-hold-soft);
  border-radius: 0 var(--ck-radius-sm) var(--ck-radius-sm) 0;
}

.hold__tag {
  display: block;
  margin-bottom: 1px;
  // 状态色落在这行小标签上：淡背景在深色主题里等于没有，小标签的字色两种主题都成立
  color: var(--ck-hold);
}

// 补跑次数用满：这才是需要人动手的状态
.hold--bad {
  border-left-color: var(--ck-bad);
  background: var(--ck-bad-soft);
}

.hold--bad .hold__tag {
  color: var(--ck-bad);
}

// ── 站点 ────────────────────────────────────────────────────────────
.sites {
  margin: 0;
  padding: 0;
  list-style: none;
}

.site {
  display: grid;
  grid-template-columns: 30px minmax(120px, 1fr) auto minmax(140px, 1.4fr) auto;
  align-items: center;
  gap: 10px;
  padding: 9px 0;
}

.site + .site {
  border-top: 1px solid var(--ck-line);
}

.site__badge {
  display: grid;
  place-items: center;
  block-size: 22px;
  border: 1px solid var(--ck-line-strong);
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  color: var(--ck-ink-70);
}

.site__id {
  display: grid;
  gap: 1px;
  min-width: 0;
}

.site__name {
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.site__acct {
  font-size: 11px;
  color: var(--ck-ink-50);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.site__tags,
.site__result {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.site__msg {
  font-size: 12px;
  color: var(--ck-ink-50);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.site__when {
  font-size: 11px;
  color: var(--ck-ink-50);
  white-space: nowrap;
}

// ── 执行记录 ────────────────────────────────────────────────────────
// 卡片形制与 115 轻量助手的记录卡逐字相同（栅格 240 / gap 10 / 内边距 11-13 /
// 悬停描边）。本插件多一段：summary 可以展开出当次每个站点的回复。
.log-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
  // 展开一张卡片不该把同排的另几张一起撑高
  align-items: start;
}

.log-card {
  padding: 11px 13px;
  border: 1px solid var(--ck-line);
  border-radius: var(--ck-radius-sm);
  background: var(--ck-paper);
  min-width: 0;
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
}

.log-card:hover {
  border-color: var(--ck-ink-50);
  box-shadow: var(--ck-shadow);
}

.log-card__sum {
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: pointer;
  list-style: none;
}

.log-card__sum::-webkit-details-marker {
  display: none;
}

.log-card__sum:focus-visible {
  outline: 2px solid var(--ck-accent);
  outline-offset: 3px;
  border-radius: 3px;
}

.log-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

// 115 那边这一格是任务名（永远是强调色），这边是结论 —— 同一个位置、同一个字号，
// 颜色改由结果决定，因为签到只有一种任务，变的是它成没成
.log-card__kind {
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
  color: var(--ck-ink-70);
}

.log-card__kind--on {
  color: var(--ck-accent);
}

.log-card__kind--warn {
  color: var(--ck-warn);
}

.log-card__kind--bad {
  color: var(--ck-bad);
}

.log-card__cost {
  font-size: 12px;
  color: var(--ck-ink-50);
  white-space: nowrap;
}

.log-card__when {
  font-size: 11px;
  color: var(--ck-ink-50);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.log-card__tally {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

// 展开时明细整块升起一次。details 原生切换是硬跳，这一下让内容「落进来」
.detail {
  margin: 9px 0 0;
  padding: 9px 0 0;
  border-top: 1px solid var(--ck-line);
  list-style: none;
  display: grid;
  gap: 5px;
  animation: ck-rise 200ms var(--ck-ease) both;
}

// 站点行的写法与通知里那几行同构：状态位自己对齐成一列，名称，再是拿到了什么
.detail__row {
  display: grid;
  grid-template-columns: 14px auto minmax(0, 1fr);
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
}

.detail__mark {
  font-size: 11px;
  line-height: 1.5;
  color: var(--ck-ink-50);
}

.detail__mark--on {
  color: var(--ck-accent);
}

.detail__mark--bad {
  color: var(--ck-bad);
}

.detail__site {
  font-weight: 600;
  white-space: nowrap;
}

.detail__note {
  color: var(--ck-ink-50);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

// ── 窄屏：站点行改成两行堆叠，读数条降到两列 ────────────────────────
@media (max-width: 700px) {
  .site {
    grid-template-columns: 26px 1fr auto;
    row-gap: 4px;
  }

  .site__tags {
    grid-column: 3;
  }

  .site__result {
    grid-column: 2 / -1;
  }

  .site__when {
    grid-column: 2 / -1;
  }
}

@media (max-width: 520px) {
  .run__body {
    padding: 12px 12px 18px;
  }

  .lede__acts {
    margin-inline-start: 0;
    width: 100%;
  }
}
</style>
