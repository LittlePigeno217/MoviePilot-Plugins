<script setup>
/**
 * 「等你确认删除」的审阅账本。
 *
 * 从运行台里抽出来的，因为**两个入口都得有它**：清单是现在的主界面，可这一块是整个插件里
 * 最要紧的决定（本地没了、网盘还在、删不删），只放在插件列表那张卡片里等于把它藏了。
 * 抽成一个组件而不是抄两份 —— 确认走的是批次 ID，两份代码一旦漂开就可能把错的批次删掉。
 *
 * 粒度是**批次**，不是单部片：一次巡检发现的一批算一张，后端的确认接口也只认批次 ID。
 * 想知道某一部片牵扯在哪张批次里，用清单上的「等你确认删除」筛选。
 */
import { computed, reactive, ref, watch } from 'vue'
import { pluginGet, pluginPost } from '../../plugin.js'
import { bytes, fileName, shortDir, shortTime } from '../../format.js'

const props = defineProps({
  api: { type: [Object, Function], default: null },
  batches: { type: Array, default: () => [] },
  // 有 115 数据任务在跑时，确认删除起不来（三个任务共用一把锁）
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['done', 'notice'])

const deciding = ref('')
const expanded = ref('')
const detail = reactive({ id: '', total: 0, items: [], loading: false })

const pendingTotal = computed(() =>
  props.batches.reduce((sum, batch) => sum + Number(batch.count || 0), 0),
)
const pendingIds = computed(() => props.batches.map(batch => batch.id))

function say(text, kind) {
  emit('notice', { text, kind })
}

// 确认就真删，驳回只丢清单。两个动作都要防连点。
async function decidePending(batchIds, approve) {
  const ids = [].concat(batchIds)
  if (deciding.value || !ids.length) return
  deciding.value = ids.length > 1 ? 'all' : ids[0]
  try {
    const path = approve ? '/strm/sweep/confirm' : '/strm/sweep/dismiss'
    const result = await pluginPost(props.api, path, { batch_ids: ids })
    say(result.message || (approve ? '已开始清理网盘' : '已忽略'), result.success ? 'success' : 'error')
    if (ids.includes(expanded.value)) expanded.value = ''
    emit('done')
  } catch (error) {
    say(error?.message || '操作失败', 'error')
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
    say(error?.message || '清单读取失败', 'error')
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

// 默认摊开第一批（等得最久的那批）。这个区块存在的意义就是让人真的看一眼清单，
// 所以不要求先点一下「查看清单」；其余批次仍然按需展开。
watch(pendingIds, ids => {
  if (expanded.value && !ids.includes(expanded.value)) expanded.value = ''
  if (!expanded.value && ids.length) toggleDetail({ id: ids[0] })
}, { immediate: true })
</script>

<template>
  <section v-if="batches.length" class="p115-panel pend p115-enter">
    <header class="pend__head">
      <div>
        <span class="p115-label">待你审阅</span>
        <h3 class="p115-section-title">本地已消失，网盘上还在</h3>
      </div>
      <div v-if="batches.length > 1" class="pend__acts">
        <v-btn variant="text" size="small" :disabled="Boolean(deciding)" @click="decidePending(pendingIds, false)">
          全部保留
        </v-btn>
        <v-btn
          class="pend__commit"
          color="error"
          variant="outlined"
          size="small"
          :loading="deciding === 'all'"
          :disabled="Boolean(deciding) || busy"
          @click="decidePending(pendingIds, true)"
        >
          全部删除 {{ pendingTotal }} 个
        </v-btn>
      </div>
    </header>

    <article v-for="batch in batches" :key="batch.id" class="pend__batch">
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
        <p v-if="batch.items_truncated" class="pend__truncated">
          这批 {{ batch.count }} 个，只留了前 {{ detail.total }} 个明细；剩下的等下一轮巡检重新统计。
        </p>
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
            :disabled="Boolean(deciding) || busy"
            @click="decidePending(batch.id, true)"
          >
            删除 {{ batch.count }} 个<template v-if="bytes(batch.total_size)"> · {{ bytes(batch.total_size) }}</template>
          </v-btn>
        </div>
      </footer>
    </article>

    <p class="pend__note">删掉的进 115 回收站，能在 115 上还原。</p>
  </section>
</template>

<style scoped lang="scss">
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
// 这条是本轮才加进运行台的，从 git HEAD 抽样式时没带上，补回来
.pend__truncated {
  margin: 10px 0 0;
  font-size: 11px;
  color: var(--p115-muted);
}

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
</style>
