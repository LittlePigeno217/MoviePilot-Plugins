<script setup>
/**
 * 媒体清单 —— 一部电影一行，一季剧一行。
 *
 * 这一个分区取代了原来的「体检」：重复、季集不全、记录外、取不到链、等你确认删除，全都变成
 * 行上的标记，靠筛选挑出来，而不是五个各自独立的问题清单。
 *
 * 口径：以网盘为库。在网盘上的算已入库；上传通道源目录里还没传上去的算未入库；输出目录里
 * 有 .strm 但记录里没有的，入库状态判不出来，单独标一类。
 *
 * 两件这一版没有的事，界面上不留假按钮：
 *   · 做种约束 —— 要接宿主的下载器，还没定要不要做
 *   · 网盘上到底还在不在 —— 要回查 115，几万条会打爆限流，得先有快照机制
 * 后端返回 has_seeding / has_cloud_check，是 false 就不画那两组筛选。
 */
import { computed, onMounted, ref, watch } from 'vue'
import ReviewQueue from './ui/ReviewQueue.vue'
import { pluginGet, pluginPost } from '../plugin.js'
import { ago, bytes } from '../format.js'
import {
  FLAG_LABELS,
  SORTS,
  buildGroups,
  createFilterState,
  filterRows,
  optionCount,
} from '../ledger_filter.js'

const props = defineProps({
  api: { type: [Object, Function], default: null },
  busy: { type: Boolean, default: false },
  reloadToken: { type: Number, default: 0 },
  // 等你确认删除的批次。由外壳读 /status 拿到再传进来，清单不必自己再问一遍。
  pending: { type: Array, default: () => [] },
})
const emit = defineEmits(['notice', 'done'])

const report = ref(null)
const loading = ref(false)
const failed = ref(false)
const state = ref(createFilterState())
const search = ref('')
// 默认按入库时间升序：打开清单先看见在库里待得最久的那些
const sort = ref('library')
const descending = ref(false)
const showFilters = ref(true)
const picked = ref(new Set())
const acting = ref('')
const confirm = ref(null)

const rows = computed(() => report.value?.rows || [])
const groups = computed(() => buildGroups(report.value?.channels || [], {
  hasSeeding: Boolean(report.value?.has_seeding),
  hasCloudCheck: Boolean(report.value?.has_cloud_check),
}).map(group => ({
  ...group,
  options: group.options.map(option => ({
    ...option,
    count: optionCount(rows.value, state.value, group.id, option.id),
  })),
})))
const visible = computed(() => filterRows(rows.value, {
  state: state.value,
  search: search.value,
  sort: sort.value,
  descending: descending.value,
}))

/** 当前生效的筛选，做成可一键摘掉的筹码 —— 吸顶条上要能看见「现在筛的是什么」。 */
const activeChips = computed(() => {
  const chips = []
  for (const group of groups.value) {
    if (group.id === 'flags') {
      for (const option of group.options) {
        if (state.value.flags.includes(option.id)) {
          chips.push({ group: group.id, id: option.id, label: option.label })
        }
      }
      continue
    }
    const picked = state.value[group.id]
    if (!picked || picked === 'all') continue
    const option = group.options.find(item => item.id === picked)
    if (option) chips.push({ group: group.id, id: option.id, label: option.label })
  }
  return chips
})

function dropChip(chip) {
  if (chip.group === 'flags') {
    state.value = { ...state.value, flags: state.value.flags.filter(id => id !== chip.id) }
    return
  }
  state.value = { ...state.value, [chip.group]: 'all' }
}

function pickSort(key) {
  if (sort.value === key) {
    descending.value = !descending.value
    return
  }
  sort.value = key
  // 入库时间默认升序（久的在前），体积默认降序（大的在前）—— 各自最有用的那一头
  descending.value = key === 'size'
}

/** 入库时间：秒级 epoch。0 表示还没入库。 */
function libraryDate(value) {
  const seconds = Number(value || 0)
  if (!seconds) return ''
  return new Date(seconds * 1000).toISOString().slice(0, 10)
}
const pickedRows = computed(() => visible.value.filter(row => picked.value.has(row.id)))
const pickedSize = computed(() => pickedRows.value.reduce((sum, row) => sum + Number(row.size || 0), 0))
const pickedFiles = computed(() => pickedRows.value.reduce((sum, row) => sum + Number(row.files || 0), 0))
/**
 * 顶上那行总计。**跟着当前筛选走**，不是全库固定值 —— 筛到「源文件还占地方」就直接看见
 * 这一筛能腾出多少空间，那才是这行数字存在的理由。没筛的时候它就是全库。
 *
 * 「可回收」只算已经传上网盘、本地源文件还占着地方的那部分：那是唯一一次点击就能腾出来的。
 * 「网盘上没了」只数核对过的行 —— 没核对过的不算「没了」。
 */
const totals = computed(() => {
  const tally = { rows: 0, size: 0, inLib: 0, inLibSize: 0, out: 0, outSize: 0, reclaim: 0, gone: 0 }
  for (const row of visible.value) {
    tally.rows += 1
    tally.size += Number(row.size || 0)
    if (row.in_library === 'yes') {
      tally.inLib += 1
      tally.inLibSize += Number(row.size || 0)
      if (Number(row.source_uploaded || 0)) tally.reclaim += Number(row.source_size || 0)
    } else if (row.in_library === 'no') {
      tally.out += 1
      tally.outSize += Number(row.size || 0)
    }
    if (row.cloud_state === 'no') tally.gone += 1
  }
  return tally
})

const pendingFileTotal = computed(() =>
  props.pending.reduce((sum, batch) => sum + Number(batch.count || 0), 0),
)

const dirty = computed(() => {
  const base = createFilterState()
  return state.value.kind !== base.kind || state.value.library !== base.library
    || state.value.channel !== base.channel || state.value.cloud !== base.cloud
    || state.value.seeding !== base.seeding || state.value.flags.length > 0
})

const verifying = ref(false)

/** 核对网盘：选中了就只核对这一批，没选就核对最久没核对过的那一批。 */
async function verify() {
  if (verifying.value) return
  verifying.value = true
  try {
    const ids = pickedRows.value.map(row => row.id)
    const result = await pluginPost(props.api, '/ledger/verify', ids.length ? { row_ids: ids } : {})
    emit('notice', { text: result.message || '已核对', kind: result.success ? 'success' : 'error' })
    if (result.success) await load()
  } catch (error) {
    emit('notice', { text: error?.message || '核对失败', kind: 'error' })
  } finally {
    verifying.value = false
  }
}

async function load() {
  if (!props.api) return
  loading.value = true
  try {
    const data = await pluginGet(props.api, '/ledger')
    if (data?.success === false) throw new Error(data.message || '清单没算出来')
    report.value = data?.data || data
    failed.value = false
  } catch (error) {
    failed.value = true
    emit('notice', { text: error?.message || '清单没算出来', kind: 'error' })
  } finally {
    loading.value = false
  }
}

function isOn(group, option) {
  if (group.id === 'flags') return state.value.flags.includes(option.id)
  return state.value[group.id] === option.id
}

function choose(group, option) {
  if (group.id === 'flags') {
    const flags = state.value.flags.includes(option.id)
      ? state.value.flags.filter(id => id !== option.id)
      : [...state.value.flags, option.id]
    state.value = { ...state.value, flags }
    return
  }
  // 再点一次已经选中的那个就回到「全部」：没有「全部」按钮，反选就是它
  const next = state.value[group.id] === option.id ? 'all' : option.id
  state.value = { ...state.value, [group.id]: next }
}

function toggle(row) {
  const next = new Set(picked.value)
  if (next.has(row.id)) next.delete(row.id)
  else next.add(row.id)
  picked.value = next
}

function toggleVisible() {
  const ids = visible.value.map(row => row.id)
  const every = ids.length > 0 && ids.every(id => picked.value.has(id))
  picked.value = every ? new Set() : new Set(ids)
}

/**
 * 三个删除动作对应三个地方，可撤回性各不相同，所以它们是三个动作而不是一个带参数的动作：
 *
 *   strm   本地 .strm 与记录 —— 重跑一次同步就回来了
 *   source 本地源文件 —— **删了就没了**，本地文件系统没有回收站
 *   cloud  网盘文件 —— 进 115 回收站，能在 115 上还原；可以勾上顺带删本地 STRM
 */
const TARGETS = {
  strm: {
    title: '删除 STRM 文件',
    where: '本地 STRM 与记录',
    undo: '重跑一次同步就回来了。网盘上一个文件都不动。',
    count: row => (row.strm_paths || []).length,
  },
  source: {
    title: '删除源文件',
    where: '上传通道源目录里的媒体文件',
    undo: '删了就没了 —— 本地文件系统没有回收站。网盘与 STRM 都不动。',
    count: row => (row.source_paths || []).length,
    // 还在做种的删了就掉种，有 H&R 的站会出事 —— 所以这里是锁，不是点了才报错
    locked: row => Boolean(row.seeding),
    lockedWhy: row => `有 ${row.seeds} 个种子还在做这部片，删了可能掉种`,
  },
  cloud: {
    title: '删除网盘文件',
    where: '115 上的文件',
    undo: '进 115 回收站，能在 115 上还原。',
    count: row => (row.file_ids || []).length,
  },
}

async function act(kind, targets, options = {}) {
  if (acting.value) return
  const list = [].concat(targets).filter(Boolean)
  if (!list.length) return
  acting.value = kind
  try {
    let result
    if (kind === 'resync') {
      result = await pluginPost(props.api, '/strm/sync', { mapping_id: list[0].channel_id })
    } else if (kind === 'upload') {
      result = await pluginPost(props.api, '/task/upload-once', {
        source: list[0].source_folder || list[0].folder,
        target: list[0].upload_target,
        incremental: true,
      })
    } else if (kind === 'strm') {
      result = await pluginPost(props.api, '/library/drop', {
        paths: list.flatMap(row => row.strm_paths || []),
      })
    } else if (kind === 'source') {
      result = await pluginPost(props.api, '/source/drop', {
        paths: list.flatMap(row => row.source_paths || []),
      })
    } else {
      result = await pluginPost(props.api, '/disk/delete', {
        file_ids: list.flatMap(row => row.file_ids || []),
        also_local: Boolean(options.alsoLocal),
      })
    }
    emit('notice', { text: result.message || '已完成', kind: result.success ? 'success' : 'error' })
    if (result.success) {
      confirm.value = null
      picked.value = new Set()
      emit('done')
      if (kind !== 'resync' && kind !== 'upload') await load()
    }
  } catch (error) {
    emit('notice', { text: error?.message || '操作失败', kind: 'error' })
  } finally {
    acting.value = ''
  }
}

const alsoLocal = ref(false)

function ask(kind, targets) {
  const spec = TARGETS[kind]
  const wanted = [].concat(targets || pickedRows.value).filter(row => spec.count(row) > 0)
  // 锁住的行直接剔出去，并在弹窗里说清剔掉了几行、为什么
  const locked = wanted.filter(row => spec.locked?.(row))
  const list = wanted.filter(row => !spec.locked?.(row))
  if (!list.length) {
    emit('notice', {
      text: locked.length ? '选中的都还在做种，删了可能掉种。先去下载器里停种。' : '选中的这些没有可删的东西',
      kind: 'error',
    })
    return
  }
  alsoLocal.value = false
  confirm.value = {
    kind,
    spec: TARGETS[kind],
    targets: list,
    rows: list.length,
    files: list.reduce((sum, row) => sum + TARGETS[kind].count(row), 0),
    size: list.reduce((sum, row) => sum + Number(row.size || 0), 0),
    blocked: list.filter(row => (row.flags || []).includes('pending_delete')),
    skipped: locked.length,
  }
}

/** 这一行在哪几个地方有东西，就给哪几个删除动作；锁住的那个照样列出来但点不动。 */
function targetsOf(row) {
  return Object.entries(TARGETS)
    .filter(([, spec]) => spec.count(row) > 0)
    .map(([kind, spec]) => ({
      kind,
      title: spec.title,
      count: spec.count(row),
      locked: Boolean(spec.locked?.(row)),
      why: spec.locked?.(row) ? spec.lockedWhy(row) : '',
    }))
}

watch(() => props.reloadToken, value => {
  if (value) load()
})

onMounted(load)
</script>

<template>
  <div class="ml">
    <!--
      审阅账本放在最前面：本地没了、网盘还在、删不删 —— 这是整个插件里最要紧的决定，
      有事等人的时候它该第一个被看见，而不是等你想起来去筛「等你确认删除」。
      和插件列表那张卡片用的是同一个组件。
    -->
    <ReviewQueue
      :api="props.api"
      :batches="pending"
      :busy="busy"
      @done="emit('done')"
      @notice="event => emit('notice', event)"
    />

    <section class="p115-panel p115-enter">
      <div class="p115-panel__head">
        <div>
          <h3 class="p115-section-title">媒体清单</h3>
          <p class="p115-hint">
            一部电影一行，一季剧一行。在网盘上的算已入库，本地还没传上去的算未入库。
            <template v-if="report">{{ report.records }} 条记录聚合成 {{ rows.length }} 行。</template>
          </p>
        </div>
        <v-btn variant="outlined" size="small" prepend-icon="mdi-refresh" :loading="loading" @click="load">
          刷新清单
        </v-btn>
      </div>

      <div class="p115-panel__body">
        <p v-if="failed" class="ml__err">清单没算出来。点「重新聚合」再试一次。</p>
        <p v-else-if="!report" class="p115-probe">正在聚合…</p>

        <template v-else>
          <div class="ml__head-grid">
          <!-- 总计跟着筛选走，所以筛一下就知道那一筛的账 -->
          <div class="ml__totals">
            <span class="ml__total">
              <i class="p115-label">已入库</i>
              <b>{{ totals.inLib }} 部<em>{{ bytes(totals.inLibSize) || '0 B' }}</em></b>
            </span>
            <span class="ml__total">
              <i class="p115-label">未入库</i>
              <b>{{ totals.out }} 部<em>{{ bytes(totals.outSize) || '0 B' }}</em></b>
            </span>
            <span class="ml__total" :class="{ 'ml__total--act': totals.reclaim > 0 }">
              <i class="p115-label">源文件可回收</i>
              <b>{{ bytes(totals.reclaim) || '0 B' }}</b>
            </span>
            <span class="ml__total" :class="{ 'ml__total--bad': totals.gone > 0 }">
              <i class="p115-label">网盘上没了</i>
              <b>{{ totals.gone }} 部</b>
            </span>
            <span class="ml__total" :class="{ 'ml__total--hold': pendingFileTotal > 0 }">
              <i class="p115-label">等你确认删除</i>
              <b>{{ pendingFileTotal }} 个文件</b>
            </span>
          </div>

          <!--
            没有组标题：每个筛码自己说清自己是什么（「电影」「已入库」「季集不全」）。
            单选组画成连体的分段控件、多选组是分开的丸子 —— 形状说明「这一组只能选一个」还是
            「可以叠加」。组名交给 aria-label，读屏还听得到。
          -->
          <!--
            没有组标题：每个筛码自己说清自己是什么（「电影」「已入库」「季集不全」）。
            单选组画成连体的分段控件、多选组是分开的丸子 —— 形状说明「这一组只能选一个」还是
            「可以叠加」。组名交给 aria-label，读屏还听得到。
          -->
          <nav v-show="showFilters" class="ml__filters" aria-label="清单筛选">
            <div
              v-for="group in groups"
              :key="group.id"
              class="ml__options"
              :class="group.multi ? 'ml__options--loose' : 'ml__options--joined'"
              role="group"
              :aria-label="group.label"
            >
              <button
                v-for="option in group.options"
                :key="option.id"
                type="button"
                class="ml__option"
                :class="[{ 'ml__option--on': isOn(group, option) }, option.tone ? `ml__option--${option.tone}` : '']"
                :aria-pressed="isOn(group, option)"
                :title="`${group.label}：${option.label}`"
                @click="choose(group, option)"
              >
                {{ option.label }}<span>{{ option.count }}</span>
              </button>
            </div>
          </nav>
          </div>
        </template>
      </div>
    </section>

    <!--
      吸顶条：385 行的清单里，筛选面板会滚出视野，而「现在筛的是什么、筛出多少条、按什么排」
      恰恰是边扫边要看的。所以这一条单独吸在标题栏底下，和上面那块筛选面板分工不同 ——
      面板给的是「有哪些选项、各有多少」，这条给的是「当前状态」。
    -->
    <div v-if="report && !failed" class="ml__sticky">
      <div class="ml__sticky-row">
      <label class="ml__search">
        <v-icon icon="mdi-magnify" size="15" />
        <input v-model="search" aria-label="搜索片名" placeholder="搜片名、年份或目录">
      </label>

      <div class="ml__chips">
        <button
          v-for="chip in activeChips"
          :key="`${chip.group}-${chip.id}`"
          type="button"
          class="ml__chip"
          :title="`不再按「${chip.label}」筛`"
          @click="dropChip(chip)"
        >
          {{ chip.label }} ×
        </button>
        <button v-if="!activeChips.length" type="button" class="ml__jump" @click="showFilters = !showFilters">
          {{ showFilters ? '收起筛选' : '展开筛选' }}
        </button>
        <button v-else type="button" class="ml__jump" @click="state = createFilterState()">全部清除</button>
      </div>

      <div class="ml__sorts">
        <button
          v-for="(spec, key) in SORTS"
          :key="key"
          type="button"
          class="ml__sort"
          :class="{ 'ml__sort--on': sort === key }"
          :aria-pressed="sort === key"
          @click="pickSort(key)"
        >
          {{ spec.label }}<template v-if="sort === key"> {{ descending ? '↓' : '↑' }}</template>
        </button>
      </div>

      <button
        v-if="report.has_cloud_check"
        type="button"
        class="ml__sort"
        :disabled="verifying || Boolean(report.cloud_cooldown)"
        :title="report.cloud_note"
        @click="verify"
      >
        {{ verifying ? '核对中…' : pickedRows.length ? `核对选中的 ${pickedRows.length} 行` : '核对网盘' }}
      </button>

      <span class="ml__result">
        <strong>{{ visible.length }}</strong> / {{ rows.length }} 条
      </span>
      </div>

      <!--
        勾选后的动作也留在这条吸顶里，不再往屏幕底下弹一个浮层：那东西会盖住清单最后几行，
        而这条本来就一直在。三个动作删的是三个地方，措辞不合并。
      -->
      <div v-if="pickedRows.length" class="ml__sticky-pick">
        <span class="ml__picked">
          已选 <strong>{{ pickedRows.length }}</strong> 部 · {{ pickedFiles }} 个文件 ·
          {{ bytes(pickedSize) || '0 B' }}
        </span>
        <button type="button" class="ml__jump" @click="picked = new Set()">取消勾选</button>
        <span class="ml__pick-acts">
          <v-btn variant="outlined" size="x-small" :disabled="Boolean(acting)" @click="ask('strm')">
            删 STRM
          </v-btn>
          <v-btn variant="outlined" size="x-small" :disabled="Boolean(acting)" @click="ask('source')">
            删源文件
          </v-btn>
          <v-btn color="error" variant="flat" size="x-small" :disabled="Boolean(acting)" @click="ask('cloud')">
            删网盘文件
          </v-btn>
        </span>
        <span class="ml__pick-note">只有源文件删了找不回来。</span>
      </div>
    </div>

    <section v-if="report && !failed" class="p115-panel p115-enter p115-enter--2">
      <div class="ml__table">
        <div class="ml__head">
          <button type="button" class="ml__check" @click="toggleVisible">
            {{ visible.length && visible.every(row => picked.has(row.id)) ? '✓' : '' }}
          </button>
          <span>资源</span>
          <span>入库</span>
          <span>本地</span>
          <span class="ml__num">体积</span>
          <span class="ml__num">操作</span>
        </div>

        <p v-if="loading" class="ml__state">正在聚合…</p>
        <p v-else-if="!visible.length" class="p115-empty">没有符合条件的媒体。取消几个筛选或换个关键词。</p>

        <article v-for="row in visible" v-else :key="row.id" class="ml__row" :class="{ 'ml__row--on': picked.has(row.id) }">
          <button type="button" class="ml__check" @click="toggle(row)">
            {{ picked.has(row.id) ? '✓' : '' }}
          </button>

          <div class="ml__title">
            <strong>
              {{ row.title }}
              <em v-if="row.year">{{ row.year }}</em>
              <em v-if="row.kind === 'tv'">第 {{ row.season }} 季</em>
            </strong>
            <span class="ml__where" :title="row.cloud_folder || row.folder">
              <i v-if="libraryDate(row.library_at)" class="ml__when p115-mono">{{ libraryDate(row.library_at) }}</i>
              <i v-else class="ml__when">还没入库</i>
              · {{ row.kind === 'tv' ? '剧集' : '电影' }} · {{ row.channel }} ·
              <i class="p115-mono">{{ row.cloud_folder || row.folder }}</i>
            </span>
          </div>

          <div class="ml__cell ml__cell--wrap">
            <strong :class="`ml__lib ml__lib--${row.in_library}`">
              {{ row.in_library === 'yes' ? '已入库' : row.in_library === 'no' ? '未入库' : '判不出来' }}
            </strong>
            <!-- 只在真核对过时才说话：!== 'unchecked' 会把字段缺失也算成「还在」 -->
            <span
              v-if="row.cloud_state === 'yes' || row.cloud_state === 'no'"
              class="p115-pill"
              :class="row.cloud_state === 'no' ? 'p115-pill--bad' : 'p115-pill--on'"
              :title="`${ago(row.cloud_checked_at * 1000)}核对`"
            >{{ row.cloud_state === 'no' ? '网盘上没了' : '网盘还在' }}</span>
            <span v-if="row.seeding" class="p115-pill p115-pill--warn" title="还在做种，删源文件会掉种">
              做种 {{ row.seeds }}
            </span>
            <span
              v-for="flag in row.flags.slice(0, 2)"
              :key="flag"
              class="p115-pill"
              :class="flag === 'pending_delete' ? 'p115-pill--hold' : 'p115-pill--warn'"
            >
              {{ FLAG_LABELS[flag] || flag }}
            </span>
            <span
              v-if="row.flags.length > 2"
              class="p115-pill"
              :title="row.flags.map(flag => FLAG_LABELS[flag] || flag).join('、')"
            >+{{ row.flags.length - 2 }}</span>
          </div>

          <div class="ml__cell">
            <strong>{{ row.files }} 个</strong>
            <span v-if="row.kind === 'tv' && row.span">
              集 {{ row.span }}<template v-if="row.missing.length"> · 缺 {{ row.missing.join('、') }}</template>
            </span>
            <span v-else-if="row.strm_gone">少了 {{ row.strm_gone }} 个 STRM</span>
          </div>

          <div class="ml__cell ml__num">
            <strong class="ml__size p115-mono">{{ bytes(row.size) || '—' }}</strong>
          </div>

          <!-- 主动作按状态给一个，三个删除动作收进菜单：一行摆四个按钮就没法扫了 -->
          <div class="ml__acts">
            <v-btn
              v-if="row.in_library === 'no' && row.upload_target"
              variant="outlined"
              size="x-small"
              :disabled="busy || Boolean(acting)"
              @click="act('upload', row)"
            >
              上传
            </v-btn>
            <v-btn
              v-else-if="row.strm_gone"
              variant="outlined"
              size="x-small"
              :disabled="busy || Boolean(acting)"
              @click="act('resync', row)"
            >
              同步
            </v-btn>

            <v-menu v-if="targetsOf(row).length" location="bottom end">
              <!--
                触发器写成有字的按钮而不是一个「⋯」图标：388 行的表格里，
                只靠一个字形说明「这儿藏着三个删除动作」太弱，而且 text 变体的
                纯图标按钮在没有图标字体时是完全不可见的。
              -->
              <template #activator="{ props: menu }">
                <v-btn
                  v-bind="menu"
                  variant="text"
                  size="x-small"
                  append-icon="mdi-menu-down"
                  :disabled="Boolean(acting)"
                >
                  删除
                </v-btn>
              </template>
              <v-list density="compact" class="p115 p115-portal ml__menu">
                <v-list-item
                  v-for="item in targetsOf(row)"
                  :key="item.kind"
                  :disabled="item.locked"
                  :title="item.why"
                  @click="ask(item.kind, row)"
                >
                  <span class="ml__menu-item" :class="{ 'ml__menu-item--locked': item.locked }">
                    {{ item.title }}<b>{{ item.locked ? item.why : `${item.count} 个` }}</b>
                  </span>
                </v-list-item>
              </v-list>
            </v-menu>
          </div>
        </article>
      </div>
    </section>

    <Teleport to="body">
      <div v-if="confirm" class="ml__backdrop p115 p115-portal" @click.self="confirm = null">
        <section class="ml__dialog" role="dialog" aria-modal="true">
          <header class="ml__dialog-head">
            <span class="p115-label">{{ confirm.spec.where }}</span>
            <h3 class="p115-section-title">{{ confirm.spec.title }}</h3>
          </header>

          <div class="ml__dialog-body">
            <p class="ml__sum">
              {{ confirm.rows }} 部 · {{ confirm.files }} 个文件<template v-if="bytes(confirm.size)"> · {{ bytes(confirm.size) }}</template>
            </p>
            <p class="ml__what" :class="{ 'ml__what--final': confirm.kind === 'source' }">
              {{ confirm.spec.undo }}
            </p>

            <label v-if="confirm.kind === 'cloud'" class="ml__also">
              <input v-model="alsoLocal" type="checkbox">
              同时删掉本地的 STRM 与记录（不勾的话本地那份会变成死链）
            </label>

            <ul class="ml__targets">
              <li v-for="row in confirm.targets.slice(0, 10)" :key="row.id">
                <span>{{ row.title }}</span>
                <span class="p115-mono">{{ confirm.spec.count(row) }} 个</span>
              </li>
            </ul>
            <p v-if="confirm.targets.length > 10" class="ml__more">
              还有 {{ confirm.targets.length - 10 }} 部没列出来。
            </p>


            <p v-if="confirm.skipped" class="ml__warn">
              另有 {{ confirm.skipped }} 部还在做种，已经从这次删除里剔掉了 —— 删了可能掉种。
              要删得先去下载器里停种。
            </p>
            <p v-if="confirm.blocked.length" class="ml__warn">
              其中 {{ confirm.blocked.length }} 部正挂在「等你确认删除」的队列里。这里删掉之后那些批次会在下一轮巡检时自行失效。
            </p>
            <p class="ml__estimate">
              这份账按刚才那份清单算的。中间跑过同步或上传的话，先回去点「刷新清单」。
            </p>
          </div>

          <footer class="ml__dialog-foot">
            <v-btn variant="text" size="small" :disabled="Boolean(acting)" @click="confirm = null">返回</v-btn>
            <v-btn
              :color="confirm.kind === 'strm' ? 'primary' : 'error'"
              :variant="confirm.kind === 'strm' ? 'outlined' : 'flat'"
              size="small"
              :loading="Boolean(acting)"
              @click="act(confirm.kind, confirm.targets, { alsoLocal })"
            >
              确认{{ confirm.spec.title }}
            </v-btn>
          </footer>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<style scoped lang="scss">
.ml {
  padding: 16px 0 0;
}

.ml__err {
  margin: 0;
  font-size: 12px;
  color: rgb(var(--v-theme-error));
}

// 总计与筛选并排：一列摞一列在宽屏上白占两百多像素高，头部矮一半清单就早两百像素出现
.ml__head-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px 20px;
}

@media (min-width: 1200px) {
  .ml__head-grid {
    grid-template-columns: minmax(0, 1fr) 21rem;
    align-items: start;
  }

  // 宽屏下总计竖着摞在右边一栏，正好和左边六行筛选等高
  .ml__totals {
    grid-template-columns: minmax(0, 1fr) !important;
    order: 2;
  }
}

// 读数格照规范：内边距 14px 14px 12px，值 15px|700，条 gap 12，minmax(150px, 1fr)
.ml__totals {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}

// ── 吸顶条 ──────────────────────────────────────────────────────
// 这一层是竖着摞两行（主控制行 + 勾选行），不是横排 ——
// 写成 flex 的话两行会并排挤在一起，各自内部又跟着换行，看着像散了
.ml__sticky {
  position: sticky;
  top: 58px;
  z-index: 2;
  margin: 12px 0 0;
  padding: 8px 18px;
  border-top: 1px solid var(--p115-hairline);
  border-bottom: 1px solid var(--p115-hairline);
  background: var(--p115-paper);
}

// 只占自己需要的宽度：flex 1 会把右边的排序和计数挤到第二行去
.ml__chips {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  flex: 0 1 auto;
  min-width: 0;
}

.ml__chip {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 10px;
  border: 1px solid var(--p115-accent);
  border-radius: 999px;
  background: var(--p115-accent-soft);
  color: var(--p115-accent);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.ml__jump {
  padding: 3px 4px;
  border: 0;
  background: none;
  color: var(--p115-muted);
  font: inherit;
  font-size: 11px;
  text-decoration: underline;
  text-underline-offset: 2px;
  cursor: pointer;
}

.ml__chip:focus-visible,
.ml__jump:focus-visible {
  outline: 2px solid var(--p115-accent);
  outline-offset: 2px;
}

.ml__sorts {
  display: flex;
  gap: 0;
  flex: none;
  // 右侧那组控件靠右：排序、核对、计数是一组，和左边的搜索与筛选分开
  margin-inline-start: auto;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  overflow: hidden;
}

.ml__sorts .ml__sort {
  border: 0;
  border-radius: 0;
}

.ml__sorts .ml__sort + .ml__sort {
  box-shadow: inset 1px 0 0 var(--p115-hairline);
}

.ml__sort--on {
  background: var(--p115-accent-soft);
  color: var(--p115-accent);
  font-weight: 600;
}

// 标签在上、数在下：竖着一栏是靠标签找的，和运行台的读数格同一个读法
.ml__total {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px 14px 11px;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: var(--p115-well);
}

.ml__total i {
  font-style: normal;
}

.ml__total b {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.01em;
  font-variant-numeric: tabular-nums;
}

// 体积是这一格的补充读数，不跟主数抢
.ml__total em {
  margin-inline-start: auto;
  font-style: normal;
  font-weight: 400;
  font-size: 11px;
  color: var(--p115-muted);
}

// 三个「有事可做」的数字在非零时才着色：全零的库不该有一片颜色
.ml__total--act b { color: rgb(var(--v-theme-success)); }
.ml__total--bad b { color: rgb(var(--v-theme-error)); }
.ml__total--hold b { color: var(--p115-hold); }

.ml__toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

// 搜索框限宽：查询词都很短，铺满 1300px 只是把筛选组挤下去
.ml__search {
  display: flex;
  align-items: center;
  gap: 7px;
  flex: 0 1 22rem;
  height: 28px;
  padding: 0 10px;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: var(--p115-well);
  color: var(--p115-muted);
}

.ml__search input {
  flex: 1 1 auto;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--p115-ink);
  font: inherit;
  font-size: 12px;
}

// 和 v-btn 的常档对齐到同一个 28px：吸顶条上原来是 24 / 28 / 20 三种高度混着，
// 那是「比例不对劲」最刺眼的一处
.ml__sort,
.ml__clear {
  flex: none;
  display: inline-flex;
  align-items: center;
  height: 28px;
  padding: 0 11px;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: transparent;
  color: var(--p115-muted);
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}

.ml__sort:hover,
.ml__clear:hover {
  border-color: var(--p115-accent);
  color: var(--p115-accent);
}

.ml__sort:focus-visible,
.ml__clear:focus-visible {
  outline: 2px solid var(--p115-accent);
  outline-offset: 2px;
}

.ml__result {
  margin-inline-start: auto;
  font-size: 11px;
  color: var(--p115-muted);
  font-variant-numeric: tabular-nums;
}

.ml__result strong {
  font-size: 13px;
  color: var(--p115-ink);
}

// ── 筛选组 ──────────────────────────────────────────────────────
//
// 一组一行。没有组标题，所以行本身就是分组：一行读完是一个维度，不必在 18px 的间距里
// 猜哪几个筛码是一伙的。行与行之间一条极淡的分隔线，比纯留白更说明「这是另一组」。
.ml__filters {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 4px 14px;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: var(--p115-well);
}

.ml__filters > .ml__options {
  width: 100%;
  padding: 8px 0;
}

// 用 hairline 不用 faint：3% 的极淡线在这儿根本看不见，那这条分隔就白写了
.ml__filters > .ml__options + .ml__options {
  border-top: 1px solid var(--p115-hairline);
}

.ml__options {
  display: flex;
  flex-wrap: wrap;
}

// 连体 = 这一组里只能选一个；分开的丸子 = 可以叠加。形状本身就是规则说明。
.ml__options--joined {
  gap: 0;
}

// 连体的边框只包住筛码本身：直接挂在行容器上会被 width:100% 拉满整行
.ml__options--joined .ml__option {
  border: 1px solid var(--p115-hairline);
  border-inline-start-width: 0;
  border-radius: 0;
  background: var(--p115-paper);
}

.ml__options--joined .ml__option:first-child {
  border-inline-start-width: 1px;
  border-start-start-radius: var(--p115-radius-sm);
  border-end-start-radius: var(--p115-radius-sm);
}

.ml__options--joined .ml__option:last-child {
  border-start-end-radius: var(--p115-radius-sm);
  border-end-end-radius: var(--p115-radius-sm);
}

.ml__options--loose {
  gap: 8px;
}

.ml__options--loose .ml__option {
  border: 1px solid var(--p115-hairline);
  border-radius: 999px;
  background: var(--p115-paper);
}

.ml__option {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 13px;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 12px;
  line-height: 1.4;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.ml__option span {
  color: var(--p115-muted);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.ml__option:hover {
  color: var(--p115-accent);
}

.ml__option:focus-visible {
  outline: 2px solid var(--p115-accent);
  outline-offset: -2px;
}

.ml__option--on {
  background: var(--p115-accent-soft);
  color: var(--p115-accent);
  font-weight: 600;
}

.ml__options--loose .ml__option--on {
  border-color: var(--p115-accent);
}

.ml__option--on span {
  color: var(--p115-accent);
}

// 待处理那组用暖色区分「有毛病」和「等你决定」，和清单里的读数丸对上
.ml__option--warning.ml__option--on {
  border-color: rgb(var(--v-theme-warning));
  background: rgba(var(--v-theme-warning), 0.12);
  color: rgb(var(--v-theme-warning));
}

.ml__option--warning.ml__option--on span {
  color: rgb(var(--v-theme-warning));
}

.ml__option--hold.ml__option--on {
  border-color: var(--p115-hold);
  background: var(--p115-hold-soft);
  color: var(--p115-hold);
}

.ml__option--hold.ml__option--on span {
  color: var(--p115-hold);
}

// ── 清单表 ──────────────────────────────────────────────────────
//
// 一行两行文字，不是三行。388 行的清单里，行高比字号更决定能不能扫 ——
// 三行的时候一屏看 8 部，两行的时候看 14 部。
.ml__table {
  padding: 4px 0 0;
}

.ml__head,
.ml__row {
  display: grid;
  grid-template-columns: 30px minmax(0, 2.6fr) minmax(0, 1.35fr) minmax(0, 1fr) 5rem 9.5rem;
  align-items: center;
  gap: 10px;
  padding: 7px 18px;
}

// 表头跟着吸顶条一起吸住：滚到第 200 行还得知道哪一列是什么
.ml__head {
  position: sticky;
  top: 105px;
  z-index: 1;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: var(--p115-muted);
  background: var(--p115-paper);
  border-bottom: 1px solid var(--p115-hairline);
}

.ml__row + .ml__row {
  border-top: 1px solid var(--p115-faint);
}

.ml__row:hover {
  background: var(--p115-faint);
}

.ml__row--on {
  background: var(--p115-accent-soft);
}

.ml__check {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  border: 1px solid var(--p115-hairline);
  border-radius: 5px;
  background: var(--p115-paper);
  color: var(--p115-accent);
  font: inherit;
  font-size: 11px;
  line-height: 1;
  cursor: pointer;
}

.ml__check:focus-visible {
  outline: 2px solid var(--p115-accent);
  outline-offset: 2px;
}

.ml__title,
.ml__cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

// 片名领读，年份和季号跟在同一行但退到次要色 —— 它们是限定语，不是标题
.ml__title strong {
  font-size: 13px;
  font-weight: 700;
  line-height: 1.35;
}

.ml__title em {
  margin-inline-start: 5px;
  font-style: normal;
  font-weight: 400;
  font-size: 11px;
  color: var(--p115-muted);
}

.ml__where,
.ml__cell span {
  font-size: 11px;
  color: var(--p115-muted);
  line-height: 1.45;
}

.ml__where {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ml__where i {
  font-style: normal;
}

// 入库时间是默认排序键，所以它领读这一行
.ml__when {
  color: var(--p115-ink);
}

.ml__cell strong {
  font-size: 11px;
  font-weight: 700;
}

// 入库状态与标记同一行内换行：标记竖着排会把行高翻倍
.ml__cell--wrap {
  flex-direction: row;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

// 体积是这一行里唯一要竖着扫的数字，所以让它在几个读数里领先一档
.ml__size {
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.ml__lib--yes { color: rgb(var(--v-theme-success)); }
.ml__lib--no { color: var(--p115-hold); }
.ml__lib--unknown { color: var(--p115-muted); }

.ml__num {
  text-align: right;
}

.ml__acts {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  justify-content: flex-end;
}

.ml__state {
  margin: 0;
  padding: 14px 18px;
  font-size: 12px;
  color: var(--p115-muted);
}

// ── 勾选段与确认 ────────────────────────────────────────────────
.ml__sticky-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 10px;
}

// 勾选后多出来的这一行也在吸顶范围内：动作跟着「选了什么」一起看得见，
// 不用往屏幕底下弹一个会盖住最后几行的浮层
.ml__sticky-pick {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px 10px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--p115-faint);
}

.ml__picked {
  font-size: 12px;
  color: var(--p115-muted);
}

.ml__picked strong {
  font-size: 13px;
  color: var(--p115-accent);
  font-variant-numeric: tabular-nums;
}

.ml__pick-acts {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.ml__pick-note {
  margin-inline-start: auto;
  font-size: 11px;
  color: var(--p115-muted);
}

.ml__backdrop {
  position: fixed;
  inset: 0;
  z-index: 2500;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.45);
}

.ml__dialog {
  width: min(560px, 100%);
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius);
  background: var(--p115-paper);
  box-shadow: var(--p115-shadow);
  overflow: hidden;
}

.ml__dialog-head {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 16px 18px 0;
}

.ml__dialog-body {
  padding: 12px 18px 4px;
}

.ml__sum {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.ml__what {
  margin: 4px 0 10px;
  font-size: 12px;
  color: var(--p115-muted);
  line-height: 1.6;
}

// 三个删除里只有源文件是找不回来的，那句话得自己站出来
.ml__what--final {
  color: rgb(var(--v-theme-error));
  font-weight: 600;
}

.ml__also {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.6;
  cursor: pointer;
}

.ml__menu-item {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 12px;
}

.ml__menu-item b {
  margin-inline-start: auto;
  font-weight: 400;
  font-size: 11px;
  color: var(--p115-muted);
}

.ml__menu-item--locked b {
  color: rgb(var(--v-theme-warning));
}

.ml__targets {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 10rem;
  overflow-y: auto;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: var(--p115-well);
}

.ml__targets li {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 5px 10px;
  font-size: 12px;
}

.ml__targets li + li {
  border-top: 1px solid var(--p115-faint);
}

.ml__targets li span:last-child {
  color: var(--p115-muted);
  flex: none;
}

.ml__more,
.ml__estimate {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--p115-muted);
  line-height: 1.6;
}

// 有牵连的那句用 info 不用红：它是提醒，不是报错
.ml__warn {
  margin: 10px 0 0;
  padding: 8px 10px;
  border-inline-start: 2px solid var(--p115-hold);
  border-radius: 0 var(--p115-radius-sm) var(--p115-radius-sm) 0;
  background: var(--p115-hold-soft);
  font-size: 12px;
  line-height: 1.6;
}

.ml__dialog-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 18px 16px;
  margin-top: 12px;
  border-top: 1px solid var(--p115-hairline);
}

// 窄屏：六列表格改成「勾选框一列、其余全部堆在第二列」。
// 只把列数改成两列是不够的 —— 六个格子会自己接着往下一行的第一列排，
// 于是体积跑到勾选框底下、标记压在集号上，整行看着像坏了。
@media (max-width: 1000px) {
  .ml__head {
    display: none;
  }

  .ml__row {
    grid-template-columns: 30px minmax(0, 1fr);
    align-items: start;
    row-gap: 3px;
    padding: 10px 14px;
  }

  .ml__row > *:not(.ml__check) {
    grid-column: 2;
  }

  .ml__num,
  .ml__acts {
    text-align: start;
    justify-content: flex-start;
  }

  .ml__toolbar {
    flex-wrap: wrap;
  }

  .ml__search {
    flex: 1 1 12rem;
  }
}
</style>
