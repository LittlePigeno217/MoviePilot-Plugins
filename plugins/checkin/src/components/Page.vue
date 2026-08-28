<script setup>
// 自用签到 · 台账页。视觉重做，接口契约不变：
// /status 拉状态、/run 立即签到、/test-login 测连通、/history/clear 清历史。
import { computed, inject, onMounted, reactive, ref } from 'vue'
import AppBar from './ui/AppBar.vue'
import Tape from './ui/Tape.vue'
import { SITE_META, pluginGet, pluginPost, useHostNotice } from '../plugin.js'
import { rankOf, shortTime, streakOf, tapeOf, todayVerdict } from '../lib/ledger.js'
import '../styles/kit.scss'

const props = defineProps({
  api: { type: [Object, Function], default: null },
  show_switch: { type: Boolean, default: true },
})
const emit = defineEmits(['switch', 'close', 'action'])

const status = ref({ sites: [], history: [] })
const busy = reactive({ load: false, run: false, test: false, clear: false })
const local = reactive({ text: '', kind: 'info' })
const notice = useHostNotice(inject('moviepilot:toast', null), (text, kind) => {
  local.text = text
  local.kind = kind
})

const history = computed(() => status.value.history || [])
// 执行记录：只显示最近 6 条（卡片式，节约空间）
const visibleHistory = computed(() => history.value.slice(0, 6))
const sites = computed(() => (status.value.sites || []).filter(site => site.enabled))
const verdict = computed(() => todayVerdict(status.value))
const streak = computed(() => streakOf(history.value))
const tape = computed(() => tapeOf(history.value, 30))

const TONE = { 3: 'on', 2: 'warn', 1: 'bad', 0: 'idle' }
const CHIP = { 3: 'ck-chip--on', 2: 'ck-chip--warn', 1: 'ck-chip--bad', 0: '' }

const barState = computed(() => {
  if (!status.value.enabled) return '未启用'
  if (!status.value.configured) return '配置待完善'
  return verdict.value.headline
})
const barTone = computed(() => {
  if (!status.value.enabled) return 'idle'
  if (!status.value.configured) return 'warn'
  return TONE[verdict.value.rank]
})

function chip(text) {
  return CHIP[rankOf(text)]
}

function badge(key) {
  return SITE_META[key]?.badge || '·'
}

async function refresh() {
  busy.load = true
  try {
    status.value = await pluginGet(props.api, '/status')
  } catch (error) {
    notice.error(error?.message || '状态获取失败')
  } finally {
    busy.load = false
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

// 清空历史是危险操作：先确认再执行，防止误触
const clearConfirm = ref(false)
const wipe = () => {
  if (!clearConfirm.value) {
    clearConfirm.value = true
    // 3 秒没二次点击就复位
    setTimeout(() => (clearConfirm.value = false), 3000)
    return
  }
  clearConfirm.value = false
  call('clear', '/history/clear', '历史已清空')
}

onMounted(refresh)
</script>

<template>
  <div class="ck run">
    <AppBar
      view="台账"
      :state="barState"
      :tone="barTone"
      :show-switch="show_switch"
      :busy="busy.load"
      show-refresh
      @refresh="refresh"
      @switch="emit('switch')"
      @close="emit('close')"
    />

    <button v-if="local.text" type="button" class="run__local" :class="`run__local--${local.kind}`" @click="local.text = ''">
      {{ local.text }}
      <span class="run__local-x">知道了</span>
    </button>

    <!-- ── 紧凑招牌：打卡带 + 一行状态/统计/操作 ── -->
    <section class="ck-sheet run__lede">
      <Tape
        :cells="tape"
        :busy="busy.run"
        :disabled="!status.enabled"
        @punch="punch"
      />
      <div class="lede__row">
        <span class="lede__tag" :class="`lede__tag--${TONE[verdict.rank]}`">{{ verdict.headline }}</span>
        <span class="lede__fact ck-mono">
          连续 <strong>{{ streak }}</strong> 天
        </span>
        <span class="lede__fact ck-mono">
          下次 <strong>{{ status.next_run_time || '—' }}</strong>
        </span>
        <span class="lede__fact ck-mono">
          上次 <strong>{{ shortTime(status.last_run) }}</strong>
        </span>
        <span class="lede__fact ck-mono">
          站点 <strong>{{ status.configured_site_count || 0 }} / {{ status.enabled_site_count || 0 }}</strong>
        </span>
        <span class="lede__acts">
          <!-- 签到 = 主操作：实心 + 图标 + 光晕，视觉焦点 -->
          <v-btn
            class="ck-btn ck-btn--primary"
            variant="flat"
            color="primary"
            size="small"
            :loading="busy.run"
            :disabled="!status.enabled"
            @click="punch"
          >
            <v-icon start icon="mdi-calendar-check" size="16" />
            签到
          </v-btn>
          <!-- 测试 = 次级：描边 + 图标 -->
          <v-btn
            class="ck-btn ck-btn--ghost"
            variant="outlined"
            size="small"
            :loading="busy.test"
            @click="test"
          >
            <v-icon start icon="mdi-connection" size="16" />
            测试
          </v-btn>
          <!-- 清空 = 危险：红色描边 + 图标 + hover 警示，需二次确认 -->
          <v-btn
            class="ck-btn ck-btn--danger"
            :class="{ 'ck-btn--danger-confirm': clearConfirm }"
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
      <p class="lede__note">{{ verdict.detail }}</p>
    </section>

    <!-- ── 站点 ── -->
    <section class="ck-sheet">
      <div class="ck-sheet__head">
        <h3 class="ck-title">站点</h3>
        <p class="ck-hint">每行一个已启用的站点，写的是它上一次的结果。</p>
      </div>

      <ul v-if="sites.length" class="sites">
        <li v-for="site in sites" :key="site.key" class="site">
          <span class="site__badge ck-mono" aria-hidden="true">{{ badge(site.key) }}</span>
          <span class="site__id">
            <span class="site__name">{{ site.name }}</span>
            <span class="site__acct ck-mono">{{ site.account || '未填账号' }}</span>
          </span>
          <span class="site__tags">
            <span class="ck-chip">{{ site.mode }}</span>
            <span v-if="site.use_proxy" class="ck-chip">代理</span>
            <span v-if="!site.configured" class="ck-chip ck-chip--warn">待填写</span>
          </span>
          <span class="site__result">
            <span class="ck-chip" :class="chip(site.last_status)">{{ site.last_status }}</span>
            <span class="site__msg">{{ site.last_message === '-' ? '' : site.last_message }}</span>
          </span>
          <span class="site__when ck-mono">{{ shortTime(site.last_run) }}</span>
        </li>
      </ul>
      <p v-else class="ck-empty">还没有启用站点。去设置里打开一个站点、填好账号，这里就会出现它的签到行。</p>
    </section>

    <!-- ── 执行记录 ── -->
    <section class="ck-sheet">
      <div class="ck-sheet__head">
        <h3 class="ck-title">执行记录</h3>
        <p class="ck-hint">保留最近 {{ visibleHistory.length }} 次，展开看每个站点当次的回复。</p>
      </div>

      <div v-if="visibleHistory.length" class="log-grid">
        <details v-for="(entry, index) in visibleHistory" :key="`${entry.time}-${index}`" class="log-card" :open="index === 0">
          <summary class="log-card__sum">
            <span class="log-card__top">
              <span class="log-card__when ck-mono">{{ shortTime(entry.time) }}</span>
              <span class="log-card__score ck-mono">{{ entry.success_count }}/{{ entry.site_count }}</span>
            </span>
            <span class="log-card__mid">
              <span class="ck-chip" :class="chip(entry.status)">{{ entry.status }}</span>
              <span class="log-card__msg">{{ entry.message }}</span>
            </span>
          </summary>
          <ul class="detail">
            <li v-for="(item, di) in entry.details" :key="di" class="detail__row">
              <span class="detail__site">{{ item.site_name }}</span>
              <span class="ck-chip" :class="chip(item.status)">{{ item.status }}</span>
              <span class="detail__msg">{{ item.message }}</span>
              <span v-if="item.reward_mb && item.reward_mb !== '-'" class="detail__gain ck-mono">
                +{{ item.reward_mb }}
              </span>
            </li>
          </ul>
        </details>
      </div>
      <p v-else class="ck-empty">还没有执行记录。按一次「立即签到」，这里就会记下每个站点的回复。</p>
    </section>
  </div>
</template>

<style scoped lang="scss">
.run__local {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  margin: 0;
  padding: 6px 14px;
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

// ── 紧凑招牌 ──
.run__lede {
  padding-bottom: 14px;
}

.lede__row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 12px;
  margin-top: 8px;
}

.lede__tag {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.6;
  white-space: nowrap;
}

.lede__tag--on {
  color: var(--ck-accent);
  background: var(--ck-accent-soft);
  border: 1px solid var(--ck-accent-line);
}

.lede__tag--warn {
  color: var(--ck-warn);
  background: var(--ck-warn-soft);
  border: 1px solid var(--ck-warn-line);
}

.lede__tag--bad {
  color: var(--ck-bad);
  background: var(--ck-bad-soft);
  border: 1px solid var(--ck-bad-line);
}

.lede__tag--idle {
  color: var(--ck-ink-50);
  background: var(--ck-faint);
  border: 1px solid var(--ck-line-strong);
}

.lede__fact {
  font-size: 11px;
  color: var(--ck-ink-70);
  white-space: nowrap;
}

.lede__fact strong {
  font-weight: 700;
  color: var(--ck-ink);
}

.lede__acts {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-left: auto;
}

// ── 操作按钮：签到是主操作，测试是次级，清空是危险 ──
.ck-btn {
  border-radius: var(--ck-radius);
  font-weight: 600;
  letter-spacing: 0;
}

// 签到：实心主色 + 柔和光晕，是这一行唯一的视觉焦点
.ck-btn--primary {
  box-shadow: 0 2px 10px rgba(var(--v-theme-primary), 0.32);
  transition: box-shadow 0.15s ease, transform 0.1s ease;
}

.ck-btn--primary:hover:not(:disabled) {
  box-shadow: 0 3px 16px rgba(var(--v-theme-primary), 0.45);
  transform: translateY(-1px);
}

// 测试：纯描边，安静
.ck-btn--ghost {
  color: var(--ck-ink-70);
}

// 清空：危险操作，平时中性、hover 变警示红
.ck-btn--danger {
  color: var(--ck-ink-50);
  border-color: var(--ck-line-strong);
}

.ck-btn--danger:hover:not(:disabled) {
  color: var(--ck-bad);
  border-color: var(--ck-bad);
  background: var(--ck-bad-soft);
}

// 确认清空态：整颗按钮变警示红，提示"再点一次就删"
.ck-btn--danger-confirm {
  color: var(--ck-bad) !important;
  border-color: var(--ck-bad) !important;
  background: var(--ck-bad-soft) !important;
  box-shadow: 0 2px 10px rgba(var(--v-theme-error), 0.3);
}

.lede__note {
  font-size: 11px;
  color: var(--ck-ink-50);
  margin: 6px 0 0;
  line-height: 1.4;
}

// ── 站点行 ──
.sites,
.log {
  margin: 0;
  padding: 0;
  list-style: none;
}

.site {
  display: grid;
  grid-template-columns: 24px minmax(0, 1.1fr) auto minmax(0, 1.3fr) auto;
  align-items: center;
  gap: 4px 10px;
  padding: 6px 0;
  border-top: 1px solid var(--ck-line);
}

.site:first-child {
  border-top: 0;
}

.site__badge {
  display: grid;
  place-items: center;
  inline-size: 24px;
  block-size: 18px;
  border: 1px solid var(--ck-line-strong);
  border-radius: 3px;
  font-size: 9px;
  font-weight: 700;
  color: var(--ck-ink-70);
}

.site__id {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.site__name {
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.site__acct {
  font-size: 10px;
  color: var(--ck-ink-50);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.site__tags,
.site__result {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.site__msg {
  font-size: 11px;
  color: var(--ck-ink-50);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.site__when {
  font-size: 10px;
  color: var(--ck-ink-50);
  white-space: nowrap;
}

// ── 执行记录（卡片式，简约）───────────────────────────────────
.log-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.log-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--ck-line);
  border-radius: var(--ck-radius);
  background: var(--ck-paper);
  min-width: 0;
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
}

.log-card:hover {
  border-color: var(--ck-line-strong);
  box-shadow: var(--ck-shadow);
}

.log-card__sum {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 11px 13px;
  cursor: pointer;
  list-style: none;
}

.log-card__sum::-webkit-details-marker {
  display: none;
}

.log-card__sum:focus-visible {
  outline: 2px solid var(--ck-accent);
  outline-offset: 2px;
  border-radius: var(--ck-radius);
}

.log-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.log-card__when {
  font-size: 11px;
  color: var(--ck-ink-70);
  white-space: nowrap;
}

.log-card__score {
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.log-card__mid {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.log-card__msg {
  font-size: 11px;
  color: var(--ck-ink-50);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

// 展开明细（保留竖线缩进）
.detail {
  margin: 0;
  padding: 0 13px 10px;
  list-style: none;
  border-inline-start: 2px solid var(--ck-line);
  margin-inline-start: 13px;
}

.detail__row {
  display: grid;
  grid-template-columns: 6.5rem auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 4px 10px;
  padding: 5px 0 5px 10px;
  font-size: 11px;
}

.detail__site {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail__msg {
  color: var(--ck-ink-50);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.detail__gain {
  font-weight: 700;
  color: var(--ck-accent);
  white-space: nowrap;
}

@media (max-width: 720px) {
  .lede__row {
    gap: 4px 8px;
  }

  .lede__acts {
    width: 100%;
    justify-content: flex-start;
    margin-left: 0;
  }

  .site {
    grid-template-columns: 24px minmax(0, 1fr) auto;
  }

  .site__tags {
    grid-column: 2 / -1;
  }

  .site__result {
    grid-column: 2 / -1;
  }

  .site__when {
    grid-row: 1;
    grid-column: 3;
  }

  .log-grid {
    grid-template-columns: 1fr;
  }

  .detail__row {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .detail__msg {
    grid-column: 1 / -1;
  }
}
</style>