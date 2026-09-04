<script setup>
// 运行台骨架。外壳照 docs/Plugin_UI_Spec.md 第 4.2 节：读数条 → 手动区 → 执行记录。
// 三态分清楚：还没问到（probe）、问了没答上来（同一句 probeNote）、确实没有（empty）。
import { computed, inject, onMounted, reactive, ref } from 'vue'
import AppBar from './ui/AppBar.vue'
import '../styles/kit.scss'

const props = defineProps({
  api: { type: [Object, Function], default: null },
  showSwitch: { type: Boolean, default: true },
})
const emit = defineEmits(['switch', 'close', 'action'])

const status = ref({ history: [] })
const ready = ref(false)
const failed = ref(false)
const busy = reactive({ load: false, run: false })
const local = reactive({ text: '', kind: 'info' })
const toast = inject('moviepilot:toast', null)

// 问过了才敢说「确实没有」：把读不到说成没有，等于替用户下结论
const trusted = computed(() => ready.value && !failed.value)
const probeNote = computed(() =>
  failed.value ? '状态没读到。点右上角的刷新重试一次。' : '正在读取…',
)
const history = computed(() => (status.value.history || []).slice(0, 6))

// 读数条：每一格都是「现在能不能干活」的答案，不是装饰性的计数
const readouts = computed(() => [
  { key: 'state', label: '状态', value: status.value.enabled ? '已开启' : '已关闭', tone: status.value.enabled ? 'on' : '' },
  { key: 'next', label: '下次', value: status.value.next_run_time || '—', tone: '' },
  { key: 'last', label: '上次', value: status.value.last_run || '—', tone: '' },
])

function notify(text, kind = 'info') {
  if (toast) toast[kind]?.(text) ?? toast(text)
  else Object.assign(local, { text, kind })
}

async function refresh() {
  if (!props.api) return
  busy.load = true
  try {
    const result = typeof props.api === 'function' ? await props.api('/status') : await props.api.get('/status')
    status.value = result?.data ?? result ?? {}
    failed.value = false
  } catch (error) {
    failed.value = true
    notify(error?.message || '状态没读到', 'error')
  } finally {
    busy.load = false
    ready.value = true
  }
}

async function run() {
  busy.run = true
  try {
    const result = typeof props.api === 'function' ? await props.api('/run', 'post') : await props.api.post('/run')
    notify(result?.message || '已开始', result?.success === false ? 'error' : 'success')
    await refresh()
    emit('action')
  } catch (error) {
    notify(error?.message || '没跑起来', 'error')
  } finally {
    busy.run = false
  }
}

// 一次执行只报有意义的那几个数，避免整排 0；出事的那颗着红
function tally(entry) {
  const pick = keys =>
    keys
      .filter(([, key]) => Number(entry[key]) > 0)
      .map(([label, key]) => ({ text: `${label} ${entry[key]}`, tone: key === 'errors' ? 'bad' : '' }))
  const parts = pick([['处理', 'handled'], ['跳过', 'skipped'], ['失败', 'errors']])
  return parts.length ? parts : [{ text: '没有变化', tone: '' }]
}

// 耗时说人话：毫秒是给日志看的
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

onMounted(refresh)
</script>

<template>
  <div class="tpl run">
    <AppBar
      view="运行台"
      :state="trusted ? (status.enabled ? '已开启' : '已关闭') : probeNote"
      :tone="trusted && status.enabled ? 'on' : 'idle'"
      :show-switch="showSwitch"
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
      <!-- 读数条：顶部 2px 细线扫过一次，代表这一格的读数刚建立 -->
      <div class="run__strip tpl-enter">
        <div
          v-for="item in readouts"
          :key="item.key"
          class="dial tpl-lined"
          :class="item.tone ? `tpl-lined--${item.tone}` : ''"
        >
          <span class="dial__label tpl-label">{{ item.label }}</span>
          <span class="dial__value tpl-mono">{{ trusted ? item.value : '···' }}</span>
        </div>
      </div>

      <section class="tpl-panel tpl-enter tpl-enter--2">
        <div class="tpl-panel__head">
          <div>
            <h3 class="tpl-section-title">手动跑一次</h3>
            <p class="tpl-hint">{{ trusted ? '当前空闲，按需触发。' : probeNote }}</p>
          </div>
        </div>
        <div class="tpl-panel__body">
          <v-btn
            variant="outlined"
            size="small"
            prepend-icon="mdi-play"
            :loading="busy.run"
            :disabled="!trusted"
            @click="run"
          >
            立即执行
          </v-btn>
        </div>
      </section>

      <!-- 执行记录：三段式卡片，见 docs/Plugin_UI_Spec.md 第 5 节 -->
      <section class="tpl-panel tpl-enter tpl-enter--3">
        <div class="tpl-panel__head">
          <h3 class="tpl-section-title">执行记录</h3>
          <p class="tpl-hint">最新的在最上面，只留最近几次。</p>
        </div>
        <div class="tpl-panel__body">
          <div v-if="trusted && history.length" class="log-grid">
            <div v-for="(entry, index) in history" :key="`${entry.time}-${index}`" class="log-card">
              <div class="log-card__top">
                <span class="log-card__kind">{{ entry.kind || '执行' }}</span>
                <span v-if="seconds(entry.duration_ms)" class="log-card__cost tpl-mono">
                  {{ seconds(entry.duration_ms) }}
                </span>
              </div>
              <div class="log-card__when tpl-mono">{{ entry.time }}</div>
              <div class="log-card__tally">
                <span
                  v-for="pill in tally(entry)"
                  :key="pill.text"
                  class="tpl-pill"
                  :class="pill.tone ? `tpl-pill--${pill.tone}` : ''"
                >{{ pill.text }}</span>
              </div>
            </div>
          </div>
          <p v-else-if="!trusted" class="tpl-probe">{{ probeNote }}</p>
          <p v-else class="tpl-empty">还没有执行记录。跑一次任务后这里会记下每次的结果。</p>
        </div>
      </section>
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
  border-bottom: 1px solid var(--tpl-line);
  background: var(--tpl-faint);
  color: inherit;
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.run__local-x {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--tpl-ink-50);
}

.run__local--error {
  color: var(--tpl-bad);
}

.run__local--success {
  color: var(--tpl-ok);
}

.run__body {
  padding: 18px 18px 24px;
}

.run__strip {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  margin: 0 0 18px;
}

.dial {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 14px 14px 12px;
  border: 1px solid var(--tpl-line);
  border-radius: var(--tpl-radius-sm);
  background: var(--tpl-paper);
}

.dial__value {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

// ── 执行记录 ────────────────────────────────────────────────────────
// 数值与仓库里其它插件逐字相同，改之前先看 docs/Plugin_UI_Spec.md 第 2 节
.log-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
  align-items: start;
}

.log-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 11px 13px;
  border: 1px solid var(--tpl-line);
  border-radius: var(--tpl-radius-sm);
  background: var(--tpl-paper);
  min-width: 0;
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
}

.log-card:hover {
  border-color: var(--tpl-ink-50);
  box-shadow: var(--tpl-shadow);
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
  color: var(--tpl-accent);
  white-space: nowrap;
}

.log-card__cost {
  font-size: 12px;
  color: var(--tpl-ink-50);
  white-space: nowrap;
}

.log-card__when {
  font-size: 11px;
  color: var(--tpl-ink-50);
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
  .log-grid {
    grid-template-columns: 1fr;
  }
}
</style>
