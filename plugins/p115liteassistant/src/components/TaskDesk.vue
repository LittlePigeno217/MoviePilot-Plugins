<script setup>
/**
 * 任务台 —— 只负责「看」，不负责「起」。
 *
 * 触发按钮留在总览的「手动跑一次」：一个动作放两处会有两套禁用条件要维护，迟早对不上。
 * 这里回答的是按下去之后的事：现在在跑什么、跑了多久、谁在排队、日志里正在发生什么。
 *
 * 三件事这一版**做不到**，因为它们要改 strm.py 与 uploader.py 的主循环（插件最核心的
 * 两段代码，改它们得配单测）：
 *   · 跑到第几个 / 当前在处理哪个文件 —— 要在那两个循环里加进度回调
 *   · 中途停下 —— 要加 cancel 标记并在循环里检查
 *   · 失败的单独重试 —— 现在只记聚合计数，不留失败清单
 * 所以下面只有「已跑多久」这一个时间读数，不画进度条 —— 画一根永远不动的进度条
 * 比不画更糟。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { pluginGet } from '../plugin.js'
import { seconds } from '../format.js'

const props = defineProps({
  api: { type: [Object, Function], default: null },
  status: { type: Object, default: () => ({}) },
  trusted: { type: Boolean, default: false },
  probeNote: { type: String, default: '' },
  reloadToken: { type: Number, default: 0 },
})

const tasks = computed(() => props.status.tasks || [])
const pendingSweep = computed(() => String(props.status.pending_sweep || ''))
const working = computed(() => tasks.value.length > 0)

// ── 日志尾部 ──
// 后端按字节偏移给增量：第一次从尾部往前截一段，之后只拿新增的。日志被轮转过
// （offset 超过文件长度）后端会回 rotated，这时清屏重来，而不是把新旧日志接在一起。
const LINE_CAP = 800
const lines = ref([])
const offset = ref(0)
const missing = ref(false)
const paused = ref(false)
const follow = ref(true)
const logError = ref('')
const viewport = ref(null)
let timer = null

const LOG_LINE = /^【([A-Z]+)】(?:\d{4}-\d{2}-\d{2}\s+)?(\d{2}:\d{2}:\d{2})[.,]?\d*\s+-\s+(\S+)\s+-\s+(.*)$/

// 解析失败就整行原样显示，不丢内容 —— 日志格式变了也不该白屏
function parse(raw) {
  const matched = LOG_LINE.exec(raw)
  if (!matched) return { level: '', time: '', source: '', text: raw }
  return { level: matched[1], time: matched[2], source: matched[3], text: matched[4] }
}

const parsed = computed(() => lines.value.map((raw, index) => ({ key: `${index}-${raw.length}`, ...parse(raw) })))

function scrollToEnd() {
  const node = viewport.value
  if (!node) return
  requestAnimationFrame(() => {
    node.scrollTop = node.scrollHeight
  })
}

async function pull() {
  if (!props.api || paused.value) return
  try {
    const data = await pluginGet(props.api, '/logs/tail', { offset: offset.value })
    const page = data?.data || data
    missing.value = Boolean(page?.missing)
    logError.value = ''
    if (page?.rotated) lines.value = []
    const incoming = page?.lines || []
    if (incoming.length) {
      lines.value = lines.value.concat(incoming).slice(-LINE_CAP)
      if (follow.value) scrollToEnd()
    }
    offset.value = Number(page?.next_offset || 0)
  } catch (error) {
    logError.value = error?.message || '日志读不到'
  }
}

// 有任务在跑就盯紧点，空闲时慢慢来 —— 空闲期每秒问一次纯属白问
function schedule() {
  if (timer) clearInterval(timer)
  timer = setInterval(pull, working.value ? 1500 : 4000)
}

watch(working, schedule)
watch(() => props.reloadToken, value => {
  if (value) pull()
})
watch(paused, value => {
  if (!value) pull()
})

onMounted(() => {
  pull()
  schedule()
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="desk">
    <section class="p115-panel p115-enter">
      <div class="p115-panel__head">
        <div>
          <h3 class="p115-section-title">正在跑</h3>
          <p class="p115-hint">
            {{ !trusted ? probeNote : working ? '三个 115 数据任务共用一把锁，跑完才轮到下一个。' : '当前空闲。去总览的「手动跑一次」触发。' }}
          </p>
        </div>
      </div>
      <div class="p115-panel__body">
        <p v-if="!trusted" class="p115-probe">{{ probeNote }}</p>
        <div v-else-if="working" class="desk__tasks">
          <article v-for="task in tasks" :key="task.kind" class="job">
            <span class="job__dot" aria-hidden="true" />
            <span class="job__name">{{ task.label }}</span>
            <span class="job__elapsed p115-mono">已跑 {{ seconds(task.elapsed_ms) || '不到 1 秒' }}</span>
            <span v-if="task.holds_cloud_lock" class="p115-pill">占用 115 任务锁</span>
          </article>
        </div>
        <p v-else class="p115-empty">当前没有任务在跑。触发一次后这里会显示它跑了多久。</p>

        <p v-if="trusted && pendingSweep" class="desk__queue">
          <span class="p115-label">排队中</span>
          反向删除已排队（{{ pendingSweep }}），等当前任务结束后自动补跑。
        </p>
      </div>
    </section>

    <section class="p115-panel p115-enter p115-enter--2">
      <div class="p115-panel__head">
        <div>
          <h3 class="p115-section-title">插件日志</h3>
          <p class="p115-hint">
            只读这个插件自己的日志文件，{{ paused ? '已暂停，不再拉取新行。' : working ? '每 1.5 秒拉一次新行。' : '每 4 秒拉一次新行。' }}
          </p>
        </div>
        <div class="desk__logacts">
          <v-btn variant="text" size="small" :prepend-icon="follow ? 'mdi-arrow-down-bold-box' : 'mdi-arrow-down-bold-box-outline'" @click="follow = !follow">
            {{ follow ? '跟随最新' : '不跟随' }}
          </v-btn>
          <v-btn variant="text" size="small" :prepend-icon="paused ? 'mdi-play' : 'mdi-pause'" @click="paused = !paused">
            {{ paused ? '继续' : '暂停' }}
          </v-btn>
          <v-btn variant="text" size="small" prepend-icon="mdi-broom" @click="lines = []">清屏</v-btn>
        </div>
      </div>
      <div class="p115-panel__body">
        <p v-if="logError" class="desk__logerr">{{ logError }}</p>
        <p v-else-if="missing" class="p115-empty">
          还没有日志文件。插件跑过一次任务后就会在 /config/logs/plugins 下生成。
        </p>
        <div v-else ref="viewport" class="desk__log" role="log" aria-live="off">
          <p v-if="!parsed.length" class="desk__logempty">日志尾部是空的。</p>
          <div
            v-for="line in parsed"
            :key="line.key"
            class="desk__line"
            :class="line.level ? `desk__line--${line.level.toLowerCase()}` : ''"
          >
            <span class="desk__time p115-mono">{{ line.time }}</span>
            <span class="desk__src p115-mono">{{ line.source }}</span>
            <span class="desk__text">{{ line.text }}</span>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped lang="scss">
.desk__tasks {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 10px;
}

.job {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 11px 13px;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: var(--p115-paper);
}

// 呼吸的点只说一件事：这块此刻活着
.job__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--p115-accent);
  animation: deskPulse 3.2s var(--p115-ease) infinite;
}

@keyframes deskPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.job__name {
  font-size: 13px;
  font-weight: 600;
}

.job__elapsed {
  color: var(--p115-muted);
  margin-inline-start: auto;
}

.desk__queue {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 12px 0 0;
  padding: 9px 12px;
  border-inline-start: 2px solid var(--p115-hold);
  border-radius: 0 var(--p115-radius-sm) var(--p115-radius-sm) 0;
  background: var(--p115-hold-soft);
  font-size: 12px;
}

.desk__logacts {
  display: flex;
  gap: 4px;
  flex: none;
}

.desk__logerr {
  margin: 0;
  font-size: 12px;
  color: rgb(var(--v-theme-error));
}

// 日志用凹槽底：它是一段外部产物，不是插件自己排的版，视觉上该沉下去
.desk__log {
  max-height: 30rem;
  overflow: auto;
  padding: 8px 0;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: var(--p115-well);
}

.desk__logempty {
  margin: 0;
  padding: 6px 12px;
  font-size: 12px;
  color: var(--p115-muted);
}

.desk__line {
  display: grid;
  grid-template-columns: 4.5rem 9rem minmax(0, 1fr);
  gap: 10px;
  padding: 2px 12px;
  font-size: 11px;
  line-height: 1.6;
}

.desk__line:hover {
  background: var(--p115-faint);
}

.desk__time,
.desk__src {
  color: var(--p115-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.desk__text {
  white-space: pre-wrap;
  word-break: break-word;
}

.desk__line--warning .desk__text { color: rgb(var(--v-theme-warning)); }
.desk__line--error .desk__text { color: rgb(var(--v-theme-error)); }
.desk__line--debug .desk__text { color: var(--p115-muted); }

@media (max-width: 720px) {
  .desk__line {
    grid-template-columns: 4.5rem minmax(0, 1fr);
  }

  .desk__src {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .job__dot {
    animation-duration: 1ms !important;
  }
}
</style>
