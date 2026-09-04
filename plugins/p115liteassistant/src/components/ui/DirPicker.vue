<script setup>
/**
 * 目录选择器。远端浏览 115（按 cid 逐层下钻），本地浏览 MoviePilot 可见目录
 * （按相对路径下钻）。选中当前所在目录后回传，由调用方决定写进哪个字段。
 */
import { computed, reactive, ref, watch } from 'vue'
import { pluginGet } from '../../plugin.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  api: { type: [Object, Function], default: null },
  remote: { type: Boolean, default: false },
  title: { type: String, default: '选择目录' },
})
const emit = defineEmits(['update:modelValue', 'select', 'error'])

const cid = ref('0')
const trail = ref([])
const path = ref('')
const localBase = ref('')
const roots = ref([])
const items = ref([])
const loading = ref(false)
const state = reactive({ failed: '' })

const remotePath = computed(() => {
  const joined = trail.value.map(stop => stop.name).join('/')
  return joined ? `/${joined}` : '/'
})
const localPath = computed(() => {
  const base = localBase.value.replace(/[\\/]+$/, '')
  return path.value ? `${base}/${path.value}` : base || '/'
})
const here = computed(() => (props.remote ? remotePath.value : localPath.value))
const canAscend = computed(() => (props.remote ? trail.value.length > 0 : Boolean(path.value)))

async function load(step) {
  loading.value = true
  state.failed = ''
  try {
    if (props.remote) {
      if (step) {
        trail.value.push({ cid: cid.value, name: step.name })
        cid.value = step.cid
      }
      const data = await pluginGet(props.api, '/browse-115', { cid: cid.value })
      if (data.error) throw new Error(data.error)
      items.value = data.items || []
    } else {
      if (step) path.value = step.path
      const data = await pluginGet(props.api, '/browse-local', { path: path.value, root: localBase.value })
      if (data.error) throw new Error(data.error)
      localBase.value = data.base || localBase.value
      roots.value = data.roots || roots.value
      path.value = data.current || ''
      items.value = data.items || []
    }
  } catch (error) {
    state.failed = error?.message || '目录读取失败'
    emit('error', state.failed)
  } finally {
    loading.value = false
  }
}

async function ascend() {
  if (!canAscend.value) return
  if (props.remote) {
    const previous = trail.value.pop()
    if (!previous) return
    cid.value = previous.cid
  } else {
    path.value = path.value.split('/').slice(0, -1).join('/')
  }
  await load()
}

async function switchRoot(root) {
  localBase.value = root || ''
  path.value = ''
  await load()
}

function confirm() {
  emit('select', props.remote ? { cid: cid.value, path: remotePath.value } : { path: localPath.value })
  emit('update:modelValue', false)
}

watch(
  () => props.modelValue,
  async open => {
    if (!open) return
    cid.value = '0'
    trail.value = []
    path.value = ''
    localBase.value = ''
    roots.value = []
    items.value = []
    await load()
  },
)
</script>

<template>
  <v-dialog
    :model-value="modelValue"
    max-width="620"
    scrollable
    @update:model-value="value => emit('update:modelValue', value)"
  >
    <v-card class="picker p115-portal">
      <div class="picker__head">
        <div>
          <div class="p115-label">{{ remote ? '115 网盘' : 'MOVIEPILOT 本地' }}</div>
          <h2 class="picker__title">{{ title }}</h2>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="关闭" @click="emit('update:modelValue', false)" />
      </div>

      <div class="picker__here">
        <v-btn
          icon="mdi-arrow-up"
          variant="text"
          size="x-small"
          :disabled="!canAscend"
          aria-label="回到上一级"
          @click="ascend"
        />
        <span class="picker__path p115-mono">{{ here }}</span>
      </div>

      <v-select
        v-if="!remote && roots.length > 1"
        :model-value="localBase"
        :items="roots"
        item-title="name"
        item-value="path"
        label="根目录"
        variant="outlined"
        density="compact"
        hide-details
        class="mx-4 mb-3"
        @update:model-value="switchRoot"
      />

      <v-card-text class="picker__list">
        <v-progress-linear v-if="loading" indeterminate color="primary" />
        <p v-if="state.failed" class="picker__failed">{{ state.failed }}</p>
        <v-list v-else-if="items.length" density="compact" lines="one" bg-color="transparent">
          <v-list-item
            v-for="item in items"
            :key="item.cid || item.path"
            prepend-icon="mdi-folder-outline"
            :title="item.name"
            @click="load(item)"
          />
        </v-list>
        <p v-else-if="!loading" class="p115-empty">这一层没有子目录，可直接选它。</p>
      </v-card-text>

      <div class="picker__foot">
        <v-btn variant="text" size="small" @click="emit('update:modelValue', false)">取消</v-btn>
        <v-btn color="primary" variant="flat" size="small" :disabled="loading" @click="confirm">
          选用当前目录
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<style scoped lang="scss">
.picker {
  background: rgb(var(--v-theme-surface));
}

.picker__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 12px 12px 18px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.picker__title {
  margin: 2px 0 0;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.picker__here {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 16px;
  padding: 6px 8px 6px 4px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  background: rgb(var(--v-theme-background));
}

.picker__path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  direction: rtl;
  text-align: left;
}

.picker__list {
  min-height: 220px;
  max-height: 46vh;
  padding: 0 16px 8px;
}

.picker__failed {
  margin: 16px 0;
  font-size: 13px;
  color: rgb(var(--v-theme-error));
}

.picker__foot {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
