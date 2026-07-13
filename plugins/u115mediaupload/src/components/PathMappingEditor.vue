<script setup>
import { ref } from 'vue'
import LocalPathSelector from './LocalPathSelector.vue'
import P115PathSelector from './P115PathSelector.vue'
import { pluginRequest } from '../utils/plugin'

const props = defineProps({
  api: Object,
  mappings: {
    type: Array,
    default: () => [],
  },
})

const emit = defineEmits(['update:mappings', 'toast'])

const localPathDialogOpen = ref(false)
const p115PathDialogOpen = ref(false)
const editingIndex = ref(null)
const savingMappings = ref(false)

function addMapping() {
  emit('update:mappings', [
    ...props.mappings,
    {
      enabled: true,
      source: '',
      sourceDesc: '',
      target: '/',
      targetCid: '0',
    },
  ])
}

function removeMapping(index) {
  emit('update:mappings', props.mappings.filter((_, idx) => idx !== index))
}

function toggleMapping(index) {
  const updated = [...props.mappings]
  updated[index].enabled = !updated[index].enabled
  emit('update:mappings', updated)
}

function openLocalPathSelector(index) {
  editingIndex.value = index
  localPathDialogOpen.value = true
}

function onLocalPathSelected(path) {
  if (editingIndex.value === null) return

  const mapping = props.mappings[editingIndex.value]
  const updated = [...props.mappings]
  const displayName = path.split('/').pop() || path || '媒体库'

  updated[editingIndex.value] = {
    ...mapping,
    source: path,
    sourceDesc: displayName,
  }

  emit('update:mappings', updated)
  localPathDialogOpen.value = false
  editingIndex.value = null
}

function openP115PathSelector(index) {
  editingIndex.value = index
  p115PathDialogOpen.value = true
}

function onP115PathSelected(cid, name) {
  if (editingIndex.value === null) return

  const mapping = props.mappings[editingIndex.value]
  const updated = [...props.mappings]

  updated[editingIndex.value] = {
    ...mapping,
    target: name,
    targetCid: cid,
  }

  emit('update:mappings', updated)
  p115PathDialogOpen.value = false
  editingIndex.value = null
}

async function saveMappings() {
  savingMappings.value = true
  try {
    const result = await pluginRequest(props.api, '/path_mappings', {
      method: 'POST',
      body: props.mappings,
    })

    if (!result?.success) {
      emit('toast', result?.msg || '保存失败', 'error')
      return
    }

    emit('toast', '路径映射已保存', 'success')
  } catch (error) {
    emit('toast', error?.message || '保存失败', 'error')
  } finally {
    savingMappings.value = false
  }
}
</script>

<template>
  <section class="mapping-editor">
    <!-- 表头 -->
    <div class="mapping-editor__head">
      <div>
        <div class="section-title">路径映射</div>
        <div class="section-subtitle">本地目录上传到对应 115 目录</div>
      </div>
      <v-btn color="#167A5B" variant="flat" size="small" @click="addMapping">
        <v-icon icon="mdi-plus" class="mr-1" />新增
      </v-btn>
    </div>

    <!-- 映射列表 -->
    <div v-if="!mappings.length" class="empty-line">暂无路径映射</div>

    <div v-else class="mappings-list">
      <div v-for="(mapping, index) in mappings" :key="index" class="mapping-row">
        <!-- 启用开关 -->
        <v-switch
          :model-value="mapping.enabled"
          color="#167A5B"
          density="compact"
          hide-details
          inset
          @update:model-value="toggleMapping(index)"
          class="mapping-switch"
        />

        <!-- 本地目录字段 -->
        <div class="path-field">
          <v-text-field
            :model-value="mapping.sourceDesc || mapping.source || '未选择'"
            label="本地目录"
            variant="outlined"
            density="compact"
            hide-details
            readonly
            prepend-inner-icon="mdi-folder-outline"
            class="path-input"
          />
          <v-btn
            icon="mdi-folder-open-outline"
            size="small"
            variant="text"
            color="#167A5B"
            @click="openLocalPathSelector(index)"
            title="浏览本地目录"
          />
        </div>

        <!-- 115 目录字段 -->
        <div class="path-field">
          <v-text-field
            :model-value="mapping.target || '未选择'"
            label="115 目录"
            variant="outlined"
            density="compact"
            hide-details
            readonly
            prepend-inner-icon="mdi-cloud-outline"
            class="path-input"
          />
          <v-btn
            icon="mdi-cloud-search-outline"
            size="small"
            variant="text"
            color="#245B7A"
            @click="openP115PathSelector(index)"
            title="浏览 115 目录"
          />
        </div>

        <!-- 删除按钮 -->
        <v-btn
          icon="mdi-delete-outline"
          size="small"
          variant="text"
          color="#B42318"
          @click="removeMapping(index)"
          title="删除此映射"
        />
      </div>
    </div>

    <!-- 保存按钮 -->
    <div v-if="mappings.length" class="mapping-actions mt-3">
      <v-btn
        color="#167A5B"
        variant="flat"
        :loading="savingMappings"
        @click="saveMappings"
      >
        <v-icon icon="mdi-content-save" class="mr-1" />保存映射
      </v-btn>
    </div>

    <!-- 本地目录选择器 -->
    <LocalPathSelector
      v-model="localPathDialogOpen"
      :api="api"
      @selected="onLocalPathSelected"
      @toast="(msg, type) => $emit('toast', msg, type)"
    />

    <!-- 115 目录选择器 -->
    <P115PathSelector
      v-model="p115PathDialogOpen"
      :api="api"
      @selected="onP115PathSelected"
      @toast="(msg, type) => $emit('toast', msg, type)"
    />
  </section>
</template>

<style scoped>
.mapping-editor {
  display: grid;
  gap: 12px;
}

.mapping-editor__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.section-title {
  font-weight: 700;
  color: #17201c;
}

.section-subtitle {
  color: #66736d;
  font-size: 13px;
  margin-top: 2px;
}

.empty-line {
  border: 1px dashed #d9e0da;
  color: #66736d;
  padding: 12px;
  border-radius: 8px;
  text-align: center;
}

.mappings-list {
  display: grid;
  gap: 12px;
}

.mapping-row {
  display: grid;
  grid-template-columns: 56px 1fr 1fr 44px;
  gap: 8px;
  align-items: center;
  padding: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  background-color: #fafbfa;
  transition: background-color 0.2s;
}

.mapping-row:hover {
  background-color: #f5f7f6;
}

.mapping-switch {
  justify-self: center;
}

.path-field {
  display: flex;
  gap: 4px;
  align-items: center;
}

.path-input {
  flex: 1;
}

.mapping-actions {
  display: flex;
  gap: 8px;
}

@media (max-width: 1024px) {
  .mapping-row {
    grid-template-columns: 48px 1fr 44px;
  }

  .path-field:nth-child(3) {
    grid-column: 2 / 4;
  }
}

@media (max-width: 600px) {
  .mapping-row {
    grid-template-columns: 1fr;
  }

  .path-field {
    grid-column: 1 / -1;
  }
}
</style>
