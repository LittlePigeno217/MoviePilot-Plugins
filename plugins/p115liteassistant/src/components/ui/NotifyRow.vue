<script setup>
/** 通知事件行。聚合模式由父组件决定，本组件只呈现事件选择和可选类型。 */
import { computed } from 'vue'
import { NOTIFY_TYPES } from '../../plugin.js'

const props = defineProps({
  checked: { type: Boolean, default: false },
  type: { type: String, default: 'Plugin' },
  showType: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  label: { type: String, required: true },
  hint: { type: String, default: '' },
  types: { type: Array, default: null },
})
const emit = defineEmits(['update:checked', 'update:type'])
const typeOptions = computed(() => (Array.isArray(props.types) && props.types.length ? props.types : NOTIFY_TYPES))
</script>

<template>
  <div class="ntf" :class="{ 'ntf--disabled': props.disabled }">
    <div class="ntf__line">
      <v-checkbox
        :model-value="props.checked"
        :disabled="props.disabled"
        color="primary"
        density="compact"
        hide-details
        :label="props.label"
        @update:model-value="value => emit('update:checked', Boolean(value))"
      />
      <v-select
        v-if="props.showType"
        :model-value="props.type"
        :items="typeOptions"
        :disabled="props.disabled || !props.checked"
        class="ntf__type"
        label="消息类型"
        variant="outlined"
        density="compact"
        hide-details
        @update:model-value="value => emit('update:type', value)"
      />
    </div>
    <p v-if="props.hint" class="p115-hint">{{ props.hint }}</p>
  </div>
</template>

<style scoped lang="scss">
.ntf + .ntf {
  padding-top: 10px;
  margin-top: 10px;
  border-top: 1px solid var(--p115-hairline);
}

.ntf__line {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.ntf__type {
  flex: 0 1 12rem;
  min-width: 9rem;
  margin-inline-start: auto;
}

.ntf--disabled {
  opacity: var(--v-disabled-opacity, 0.42);
}
</style>
