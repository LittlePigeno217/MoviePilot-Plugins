<script setup>
/**
 * 文件管理台 —— 不建通道，跑一次就完事。
 *
 * 左边一列 115 目录、右边一列本地目录，各自点进去选定「当前目录」，然后两个方向各一个
 * 动作：把左边生成成 STRM 放到右边、把右边传上去放到左边。通道是给「以后一直同步」用的，
 * 这里是给「就这一次」用的。
 *
 * 一件必须说清的事：**一次性任务生成的 STRM 不受反向删除管。** 记录照样写（增量能跳过、
 * 体检能看见），但反向删除只遍历配置里的通道，`once:` 不在里面 —— 本地删了不会联动网盘。
 */
import { computed, onMounted, ref } from 'vue'
import { pluginGet, pluginPost } from '../plugin.js'

const props = defineProps({
  api: { type: [Object, Function], default: null },
  busy: { type: Boolean, default: false },
  reloadToken: { type: Number, default: 0 },
})
const emit = defineEmits(['done', 'notice'])

// ── 115 一侧：一路点下去，来路自己攒着，翻上一层不用再问后端 ──
const cloudTrail = ref([{ cid: '0', name: '115 根目录' }])
const cloudItems = ref([])
const cloudLoading = ref(false)
const cloudError = ref('')
const cloudCid = computed(() => cloudTrail.value[cloudTrail.value.length - 1].cid)
const cloudPath = computed(() => {
  const names = cloudTrail.value.slice(1).map(node => node.name)
  return names.length ? `/${names.join('/')}` : '/'
})

// ── 本地一侧：后端给的是相对 base 的路径，父目录靠砍最后一段 ──
const localBase = ref('')
const localCurrent = ref('')
const localItems = ref([])
const localLoading = ref(false)
const localError = ref('')
const localPath = computed(() => (localCurrent.value ? `${localBase.value}/${localCurrent.value}` : localBase.value))

const incremental = ref(true)
const running = ref('')

async function loadCloud() {
  if (!props.api) return
  cloudLoading.value = true
  cloudError.value = ''
  try {
    const data = await pluginGet(props.api, '/browse-115', { cid: cloudCid.value })
    if (data?.error) throw new Error(data.error)
    cloudItems.value = data?.items || []
  } catch (error) {
    cloudError.value = error?.message || '115 目录读不到'
    cloudItems.value = []
  } finally {
    cloudLoading.value = false
  }
}

async function loadLocal() {
  if (!props.api) return
  localLoading.value = true
  localError.value = ''
  try {
    const data = await pluginGet(props.api, '/browse-local', { path: localCurrent.value })
    if (data?.error) throw new Error(data.error)
    localBase.value = data?.base || ''
    localCurrent.value = data?.current || ''
    localItems.value = data?.items || []
  } catch (error) {
    localError.value = error?.message || '本地目录读不到'
    localItems.value = []
  } finally {
    localLoading.value = false
  }
}

function enterCloud(item) {
  cloudTrail.value = [...cloudTrail.value, { cid: item.cid, name: item.name }]
  loadCloud()
}

function jumpCloud(index) {
  cloudTrail.value = cloudTrail.value.slice(0, index + 1)
  loadCloud()
}

function enterLocal(item) {
  localCurrent.value = item.path
  loadLocal()
}

function upLocal() {
  const parts = localCurrent.value.split('/').filter(Boolean)
  parts.pop()
  localCurrent.value = parts.join('/')
  loadLocal()
}

async function run(kind) {
  if (running.value) return
  running.value = kind
  try {
    const path = kind === 'strm' ? '/task/strm-once' : '/task/upload-once'
    const body = kind === 'strm'
      ? { source_cid: cloudCid.value, source_path: cloudPath.value, target_dir: localPath.value }
      : { source: localPath.value, target: cloudPath.value, incremental: incremental.value }
    const result = await pluginPost(props.api, path, body)
    emit('notice', { text: result.message || (result.success ? '已开始' : '没能开始'), kind: result.success ? 'success' : 'error' })
    emit('done')
  } catch (error) {
    emit('notice', { text: error?.message || '任务没能开始', kind: 'error' })
  } finally {
    running.value = ''
  }
}

onMounted(() => {
  loadCloud()
  loadLocal()
})
</script>

<template>
  <div class="fd">
    <div class="fd__panes">
      <section class="p115-panel p115-enter">
        <div class="p115-panel__head">
          <div>
            <h3 class="p115-section-title">115 目录</h3>
            <p class="p115-hint">点进去选定一个目录，它就是源（生成 STRM）或目标（上传）。</p>
          </div>
        </div>
        <div class="p115-panel__body">
          <nav class="fd__trail" aria-label="115 目录来路">
            <button
              v-for="(node, index) in cloudTrail"
              :key="`${node.cid}-${index}`"
              type="button"
              class="fd__crumb"
              :class="{ 'fd__crumb--on': index === cloudTrail.length - 1 }"
              @click="jumpCloud(index)"
            >
              {{ node.name }}
            </button>
          </nav>
          <p class="fd__picked p115-mono">{{ cloudPath }}</p>
          <p v-if="cloudError" class="fd__err">{{ cloudError }}</p>
          <p v-else-if="cloudLoading" class="p115-probe">正在读取…</p>
          <div v-else-if="cloudItems.length" class="fd__list">
            <button
              v-for="item in cloudItems"
              :key="item.cid"
              type="button"
              class="fd__row"
              @click="enterCloud(item)"
            >
              <v-icon icon="mdi-folder-outline" size="16" />
              <span class="fd__name">{{ item.name }}</span>
            </button>
          </div>
          <p v-else class="p115-empty">这个目录下没有子目录。它本身就可以当源或目标。</p>
        </div>
      </section>

      <section class="p115-panel p115-enter p115-enter--2">
        <div class="p115-panel__head">
          <div>
            <h3 class="p115-section-title">本地目录</h3>
            <p class="p115-hint">MoviePilot 容器里的路径。点进去选定一个目录。</p>
          </div>
        </div>
        <div class="p115-panel__body">
          <nav class="fd__trail" aria-label="本地目录来路">
            <button type="button" class="fd__crumb" :disabled="!localCurrent" @click="upLocal">
              上一层
            </button>
            <span class="fd__crumb fd__crumb--on">{{ localCurrent ? localCurrent.split('/').pop() : '根目录' }}</span>
          </nav>
          <p class="fd__picked p115-mono">{{ localPath || '读取中…' }}</p>
          <p v-if="localError" class="fd__err">{{ localError }}</p>
          <p v-else-if="localLoading" class="p115-probe">正在读取…</p>
          <div v-else-if="localItems.length" class="fd__list">
            <button
              v-for="item in localItems"
              :key="item.path"
              type="button"
              class="fd__row"
              @click="enterLocal(item)"
            >
              <v-icon icon="mdi-folder-outline" size="16" />
              <span class="fd__name">{{ item.name }}</span>
            </button>
          </div>
          <p v-else class="p115-empty">这个目录下没有子目录。它本身就可以当输出或源。</p>
        </div>
      </section>
    </div>

    <section class="p115-panel p115-enter p115-enter--3">
      <div class="p115-panel__head">
        <div>
          <h3 class="p115-section-title">跑一次</h3>
          <p class="p115-hint">
            一次性任务和通道走同一套执行逻辑，但<strong>不受反向删除管</strong>——本地删了不会联动网盘。要联动就去设置里建一条通道。
          </p>
        </div>
      </div>
      <div class="p115-panel__body">
        <div class="fd__acts">
          <div class="fd__act">
            <p class="fd__act-line p115-mono">{{ cloudPath }} → {{ localPath }}</p>
            <v-btn
              variant="outlined"
              size="small"
              prepend-icon="mdi-file-link-outline"
              :loading="running === 'strm'"
              :disabled="busy || Boolean(running) || !localPath"
              @click="run('strm')"
            >
              生成 STRM 到本地
            </v-btn>
          </div>
          <div class="fd__act">
            <p class="fd__act-line p115-mono">{{ localPath }} → {{ cloudPath }}</p>
            <div class="fd__act-row">
              <v-btn
                variant="outlined"
                size="small"
                prepend-icon="mdi-tray-arrow-up"
                :loading="running === 'upload'"
                :disabled="busy || Boolean(running) || !localPath"
                @click="run('upload')"
              >
                上传到 115
              </v-btn>
              <label class="fd__inc">
                <input v-model="incremental" type="checkbox">
                只传没传过的
              </label>
            </div>
          </div>
        </div>
        <p v-if="busy" class="fd__note">已经有 115 数据任务在跑，三个任务共用一把锁，等它跑完再来。</p>
      </div>
    </section>
  </div>
</template>

<style scoped lang="scss">
.fd__panes {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 18px;
}

.fd__panes > .p115-panel + .p115-panel {
  margin-top: 0;
}

.fd__trail {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  margin-bottom: 8px;
}

.fd__crumb {
  padding: 2px 8px;
  border: 1px solid var(--p115-hairline);
  border-radius: 999px;
  background: transparent;
  color: var(--p115-muted);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.fd__crumb:disabled {
  opacity: 0.4;
  cursor: default;
}

.fd__crumb--on {
  border-color: var(--p115-accent);
  background: var(--p115-accent-soft);
  color: var(--p115-accent);
}

.fd__crumb:focus-visible {
  outline: 2px solid var(--p115-accent);
  outline-offset: 2px;
}

// 选定的那条路要一眼看见：两个动作的措辞都指着它
.fd__picked {
  margin: 0 0 10px;
  padding: 7px 10px;
  border-inline-start: 2px solid var(--p115-accent);
  border-radius: 0 var(--p115-radius-sm) var(--p115-radius-sm) 0;
  background: var(--p115-accent-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fd__list {
  max-height: 22rem;
  overflow-y: auto;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: var(--p115-well);
}

.fd__row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 7px 10px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.fd__row + .fd__row {
  border-top: 1px solid var(--p115-faint);
}

.fd__row:hover {
  background: var(--p115-faint);
}

.fd__row:focus-visible {
  outline: 2px solid var(--p115-accent);
  outline-offset: -2px;
}

.fd__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fd__err {
  margin: 0;
  font-size: 12px;
  color: rgb(var(--v-theme-error));
}

.fd__acts {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 12px;
}

.fd__act {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 11px 13px;
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: var(--p115-paper);
}

.fd__act-line {
  margin: 0;
  color: var(--p115-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fd__act-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.fd__inc {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--p115-muted);
  cursor: pointer;
}

.fd__note {
  margin: 12px 0 0;
  font-size: 12px;
  color: var(--p115-muted);
}
</style>
