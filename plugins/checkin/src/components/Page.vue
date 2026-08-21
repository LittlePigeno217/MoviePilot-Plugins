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
const wipe = () => call('clear', '/history/clear', '历史已清空')

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

    <!-- 招牌：一条 30 天打卡带，今天那一格就是签到按钮 -->
    <section class="run__lede ck-sheet">
      <div class="lede__read">
        <p class="ck-eyebrow">今天</p>
        <h2 class="lede__head" :class="`lede__head--${TONE[verdict.rank]}`">{{ verdict.headline }}</h2>
        <p class="lede__note">{{ verdict.detail }}</p>
      </div>

      <Tape
        :cells="tape"
        :busy="busy.run"
        :disabled="!status.enabled"
        @punch="punch"
      />

      <dl class="lede__facts">
        <div class="fact">
          <dt class="fact__k ck-eyebrow">连续</dt>
          <dd class="fact__v ck-mono">{{ streak }} 天</dd>
        </div>
        <div class="fact">
          <dt class="fact__k ck-eyebrow">下次执行</dt>
          <dd class="fact__v ck-mono">{{ status.next_run_time || '未配置' }}</dd>
        </div>
        <div class="fact">
          <dt class="fact__k ck-eyebrow">上次执行</dt>
          <dd class="fact__v ck-mono">{{ shortTime(status.last_run) }}</dd>
        </div>
        <div class="fact">
          <dt class="fact__k ck-eyebrow">站点</dt>
          <dd class="fact__v ck-mono">{{ status.configured_site_count || 0 }} / {{ status.enabled_site_count || 0 }} 配置完整</dd>
        </div>
      </dl>

      <div class="lede__acts">
        <v-btn variant="flat" color="primary" size="small" :loading="busy.run" :disabled="!status.enabled" @click="punch">
          立即签到
        </v-btn>
        <v-btn variant="outlined" size="small" :loading="busy.test" @click="test">测试连通性</v-btn>
        <v-btn variant="text" size="small" :loading="busy.clear" :disabled="!history.length" @click="wipe">
          清空历史
        </v-btn>
      </div>
    </section>

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

    <section class="ck-sheet">
      <div class="ck-sheet__head">
        <h3 class="ck-title">执行记录</h3>
        <p class="ck-hint">保留最近 {{ history.length }} 次，展开看每个站点当次的回复。</p>
      </div>

      <ul v-if="history.length" class="log">
        <li v-for="(entry, index) in history" :key="`${entry.time}-${index}`" class="log__row">
          <details :open="index === 0">
            <summary class="log__sum">
              <span class="log__when ck-mono">{{ shortTime(entry.time) }}</span>
              <span class="ck-chip" :class="chip(entry.status)">{{ entry.status }}</span>
              <span class="log__msg">{{ entry.message }}</span>
              <span class="log__score ck-mono">{{ entry.success_count }}/{{ entry.site_count }}</span>
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
        </li>
      </ul>
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
  padding: 8px 16px;
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

// ── 招牌区 ──────────────────────────────────────────────────────────
.run__lede {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.lede__head {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.15;
  margin: 4px 0 0;
}

.lede__head--on {
  color: var(--ck-accent);
}

.lede__head--warn {
  color: var(--ck-warn);
}

.lede__head--bad {
  color: var(--ck-bad);
}

.lede__note {
  font-size: 13px;
  color: var(--ck-ink-70);
  margin: 4px 0 0;
}

.lede__facts {
  display: grid;
  gap: 10px 20px;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  margin: 0;
  padding-top: 14px;
  border-top: 1px solid var(--ck-line);
}

.fact__k {
  display: block;
}

.fact__v {
  margin: 2px 0 0;
  font-size: 13px;
  font-weight: 600;
}

.lede__acts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

// ── 站点行 ──────────────────────────────────────────────────────────
.sites,
.log {
  margin: 0;
  padding: 0;
  list-style: none;
}

.site {
  display: grid;
  grid-template-columns: 30px minmax(0, 1.1fr) auto minmax(0, 1.3fr) auto;
  align-items: center;
  gap: 6px 12px;
  padding: 11px 0;
  border-top: 1px solid var(--ck-line);
}

.site:first-child {
  border-top: 0;
}

.site__badge {
  display: grid;
  place-items: center;
  inline-size: 30px;
  block-size: 22px;
  border: 1px solid var(--ck-line-strong);
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  color: var(--ck-ink-70);
}

.site__id {
  display: flex;
  flex-direction: column;
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
.log__row {
  border-top: 1px solid var(--ck-line);
}

.log__row:first-child {
  border-top: 0;
}

.log__sum {
  display: grid;
  grid-template-columns: 5.6rem auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px 12px;
  padding: 11px 0;
  cursor: pointer;
  list-style: none;
}

.log__sum::-webkit-details-marker {
  display: none;
}

.log__sum:focus-visible {
  outline: 2px solid var(--ck-accent);
  outline-offset: 2px;
}

.log__when {
  font-size: 12px;
  color: var(--ck-ink-70);
  white-space: nowrap;
}

.log__msg {
  font-size: 12px;
  color: var(--ck-ink-50);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.log__score {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.detail {
  margin: 0 0 12px;
  padding: 0;
  list-style: none;
  border-inline-start: 2px solid var(--ck-line);
}

.detail__row {
  display: grid;
  grid-template-columns: 7rem auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 4px 12px;
  padding: 7px 0 7px 12px;
  font-size: 12px;
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
  .lede__head {
    font-size: 22px;
  }

  .site {
    grid-template-columns: 30px minmax(0, 1fr) auto;
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

  .log__sum {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .log__msg {
    grid-column: 1 / -1;
  }

  .detail__row {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .detail__msg {
    grid-column: 1 / -1;
  }
}
</style>
