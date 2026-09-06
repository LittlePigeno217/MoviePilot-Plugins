<script setup>
/**
 * 网盘管理 —— 把这一页当 115 用。
 *
 * 能做什么由接口决定，不由界面决定（清单见 docs/research/115-api.md）：浏览、新建目录、
 * 改名、删除都在开放接口里；**移动、容量、回收站列表与还原只有 cookie 链路能做，而那几个
 * 端点还没实测过**，所以这一版干脆不给这些按钮 —— 留一个按下去会报错的按钮比没有更糟。
 *
 * 删除进 115 回收站，能在 115 上还原；「同时删掉本地对应的 STRM」是个显式勾选，默认不勾：
 * 在网盘上删一个文件和把本地那份也删掉是两件事，不该悄悄一起做。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { pluginGet, pluginPost } from '../plugin.js'
import { bytes } from '../format.js'

const props = defineProps({
  api: { type: [Object, Function], default: null },
  reloadToken: { type: Number, default: 0 },
})
const emit = defineEmits(['notice'])

const trail = ref([{ id: '0', name: '115 根目录' }])
const items = ref([])
const loading = ref(false)
const error = ref('')
const picked = ref(new Set())
const busy = ref(false)

const dialog = ref('')
const draftName = ref('')
const alsoLocal = ref(false)

const cid = computed(() => trail.value[trail.value.length - 1].id)
const pathText = computed(() => {
  const names = trail.value.slice(1).map(node => node.name)
  return names.length ? `/${names.join('/')}` : '/'
})
const pickedItems = computed(() => items.value.filter(item => picked.value.has(item.id)))
const single = computed(() => (pickedItems.value.length === 1 ? pickedItems.value[0] : null))

async function load() {
  if (!props.api) return
  loading.value = true
  error.value = ''
  try {
    const data = await pluginGet(props.api, '/disk/list', { cid: cid.value })
    const payload = data?.data || data
    if (data?.success === false) throw new Error(data.message || '目录读不到')
    items.value = payload?.items || []
    picked.value = new Set()
  } catch (err) {
    error.value = err?.message || '目录读不到'
    items.value = []
  } finally {
    loading.value = false
  }
}

function enter(item) {
  if (!item.is_dir) return
  trail.value = [...trail.value, { id: item.id, name: item.name }]
  load()
}

function jump(index) {
  trail.value = trail.value.slice(0, index + 1)
  load()
}

function toggle(item) {
  const next = new Set(picked.value)
  if (next.has(item.id)) next.delete(item.id)
  else next.add(item.id)
  picked.value = next
}

function open(kind) {
  draftName.value = kind === 'rename' ? single.value?.name || '' : ''
  alsoLocal.value = false
  dialog.value = kind
}

async function submit() {
  if (busy.value) return
  busy.value = true
  try {
    let result
    if (dialog.value === 'mkdir') {
      result = await pluginPost(props.api, '/disk/mkdir', { cid: cid.value, name: draftName.value })
    } else if (dialog.value === 'rename') {
      result = await pluginPost(props.api, '/disk/rename', { file_id: single.value?.id, name: draftName.value })
    } else {
      result = await pluginPost(props.api, '/disk/delete', {
        file_ids: pickedItems.value.map(item => item.id),
        also_local: alsoLocal.value,
      })
    }
    emit('notice', { text: result.message || '已完成', kind: result.success ? 'success' : 'error' })
    if (result.success) {
      dialog.value = ''
      await load()
    }
  } catch (err) {
    emit('notice', { text: err?.message || '操作失败', kind: 'error' })
  } finally {
    busy.value = false
  }
}

function stamp(seconds) {
  const value = Number(seconds)
  if (!Number.isFinite(value) || value <= 0) return ''
  return new Date(value * 1000).toISOString().slice(0, 16).replace('T', ' ')
}

watch(() => props.reloadToken, value => {
  if (value) load()
})

onMounted(load)
</script>

<template>
  <div class="dk">
    <section class="p115-panel p115-enter">
      <div class="p115-panel__head">
        <div>
          <h3 class="p115-section-title">网盘</h3>
          <p class="p115-hint">删除进 115 回收站，能在 115 上还原。移动、容量、回收站还原这一版没有，见下面那句。</p>
        </div>
        <div class="dk__tools">
          <v-btn variant="text" size="small" prepend-icon="mdi-folder-plus-outline" @click="open('mkdir')">新建目录</v-btn>
          <v-btn variant="text" size="small" prepend-icon="mdi-rename-outline" :disabled="!single" @click="open('rename')">改名</v-btn>
          <v-btn variant="text" size="small" color="error" prepend-icon="mdi-delete-outline" :disabled="!pickedItems.length" @click="open('delete')">
            删除{{ pickedItems.length ? ` ${pickedItems.length} 个` : '' }}
          </v-btn>
          <v-btn variant="text" size="small" prepend-icon="mdi-refresh" :loading="loading" @click="load" />
        </div>
      </div>
      <div class="p115-panel__body">
        <nav class="dk__trail" aria-label="115 目录来路">
          <button
            v-for="(node, index) in trail"
            :key="`${node.id}-${index}`"
            type="button"
            class="dk__crumb"
            :class="{ 'dk__crumb--on': index === trail.length - 1 }"
            @click="jump(index)"
          >
            {{ node.name }}
          </button>
        </nav>
        <p class="dk__picked p115-mono">{{ pathText }}</p>

        <p v-if="error" class="dk__err">{{ error }}</p>
        <p v-else-if="loading" class="p115-probe">正在读取…</p>
        <div v-else-if="items.length" class="dk__list">
          <div class="dk__head">
            <span />
            <span>名称</span>
            <span class="dk__num">体积</span>
            <span class="dk__num">修改时间</span>
          </div>
          <div v-for="item in items" :key="item.id" class="dk__row" :class="{ 'dk__row--on': picked.has(item.id) }">
            <label class="dk__check">
              <input type="checkbox" :checked="picked.has(item.id)" @change="toggle(item)">
            </label>
            <button type="button" class="dk__name" :disabled="!item.is_dir" @click="enter(item)">
              <v-icon :icon="item.is_dir ? 'mdi-folder-outline' : 'mdi-file-outline'" size="16" />
              <span>{{ item.name }}</span>
            </button>
            <span class="dk__num p115-mono">{{ item.is_dir ? '—' : bytes(item.size) || '0 B' }}</span>
            <span class="dk__num p115-mono">{{ stamp(item.mtime) }}</span>
          </div>
        </div>
        <p v-else class="p115-empty">这个目录是空的。</p>

        <p class="dk__gap">
          <strong>移动</strong>、<strong>网盘容量</strong>、<strong>回收站列表与还原</strong>这一版没有：开放接口里没有这几个端点，
          参考实现全部走 cookie 的 web 接口，而那几个端点还没在这台机器上实测过。
          要还原删掉的东西，去 115 的 App 或网页版回收站。
        </p>
      </div>
    </section>

    <Teleport to="body">
      <div v-if="dialog" class="dk__backdrop p115 p115-portal" @click.self="dialog = ''">
        <section class="dk__dialog" role="dialog" aria-modal="true">
          <header class="dk__dialog-head">
            <span class="p115-label">{{ pathText }}</span>
            <h3 class="p115-section-title">
              {{ dialog === 'mkdir' ? '新建目录' : dialog === 'rename' ? '改名' : `删除 ${pickedItems.length} 个` }}
            </h3>
          </header>

          <div class="dk__dialog-body">
            <v-text-field
              v-if="dialog !== 'delete'"
              v-model="draftName"
              :label="dialog === 'mkdir' ? '目录名' : '新名字'"
              variant="outlined"
              density="compact"
              hide-details
              autofocus
            />
            <template v-else>
              <p class="dk__confirm">这些会进 115 回收站，能在 115 上还原：</p>
              <ul class="dk__targets">
                <li v-for="item in pickedItems.slice(0, 12)" :key="item.id" class="p115-mono">{{ item.name }}</li>
              </ul>
              <p v-if="pickedItems.length > 12" class="dk__more">还有 {{ pickedItems.length - 12 }} 个没列出来。</p>
              <label class="dk__also">
                <input v-model="alsoLocal" type="checkbox">
                同时删掉本地对应的 STRM 与记录（不勾的话本地那份会变成死链）
              </label>
            </template>
          </div>

          <footer class="dk__dialog-foot">
            <v-btn variant="text" size="small" :disabled="busy" @click="dialog = ''">取消</v-btn>
            <v-btn
              :color="dialog === 'delete' ? 'error' : 'primary'"
              :variant="dialog === 'delete' ? 'flat' : 'outlined'"
              size="small"
              :loading="busy"
              :disabled="dialog !== 'delete' && !draftName.trim()"
              @click="submit"
            >
              {{ dialog === 'mkdir' ? '新建' : dialog === 'rename' ? '改名' : '确认删除' }}
            </v-btn>
          </footer>
        </section>
      </div>
    </Teleport>
  </div>
</template>

<style scoped lang="scss">
.dk__tools {
  display: flex;
  gap: 2px;
  flex: none;
  flex-wrap: wrap;
}

.dk__trail {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.dk__crumb {
  padding: 2px 8px;
  border: 1px solid var(--p115-hairline);
  border-radius: 999px;
  background: transparent;
  color: var(--p115-muted);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.dk__crumb--on {
  border-color: var(--p115-accent);
  background: var(--p115-accent-soft);
  color: var(--p115-accent);
}

.dk__crumb:focus-visible {
  outline: 2px solid var(--p115-accent);
  outline-offset: 2px;
}

.dk__picked {
  margin: 0 0 10px;
  padding: 7px 10px;
  border-inline-start: 2px solid var(--p115-accent);
  border-radius: 0 var(--p115-radius-sm) var(--p115-radius-sm) 0;
  background: var(--p115-accent-soft);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dk__list {
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius-sm);
  background: var(--p115-well);
  overflow: hidden;
}

.dk__head,
.dk__row {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 7rem 10rem;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
}

.dk__head {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: var(--p115-muted);
  border-bottom: 1px solid var(--p115-hairline);
}

.dk__row + .dk__row {
  border-top: 1px solid var(--p115-faint);
}

.dk__row:hover {
  background: var(--p115-faint);
}

.dk__row--on {
  background: var(--p115-accent-soft);
}

.dk__check {
  display: grid;
  place-items: center;
  cursor: pointer;
}

.dk__name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 0;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

// 文件点不进去，光标就该照实说
.dk__name:disabled {
  cursor: default;
}

.dk__name span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dk__name:focus-visible {
  outline: 2px solid var(--p115-accent);
  outline-offset: 2px;
}

.dk__num {
  text-align: right;
  font-size: 11px;
  color: var(--p115-muted);
}

.dk__err {
  margin: 0;
  font-size: 12px;
  color: rgb(var(--v-theme-error));
}

.dk__gap {
  margin: 12px 0 0;
  font-size: 11px;
  color: var(--p115-muted);
  line-height: 1.7;
}

.dk__backdrop {
  position: fixed;
  inset: 0;
  z-index: 2400;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(0, 0, 0, 0.45);
}

.dk__dialog {
  width: min(520px, 100%);
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius);
  background: var(--p115-paper);
  box-shadow: var(--p115-shadow);
  overflow: hidden;
}

.dk__dialog-head {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 16px 18px 0;
}

.dk__dialog-body {
  padding: 12px 18px 4px;
}

.dk__confirm {
  margin: 0 0 6px;
  font-size: 12px;
}

.dk__targets {
  margin: 0;
  padding: 0 0 0 18px;
  font-size: 12px;
  color: var(--p115-muted);
  max-height: 12rem;
  overflow-y: auto;
}

.dk__more {
  margin: 6px 0 0;
  font-size: 11px;
  color: var(--p115-muted);
}

.dk__also {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 12px;
  font-size: 12px;
  line-height: 1.6;
  cursor: pointer;
}

.dk__dialog-foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 18px 16px;
  border-top: 1px solid var(--p115-hairline);
  margin-top: 12px;
}
</style>
