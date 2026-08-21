<script setup>
/**
 * 通道通知开关。一条通道一个实例，开关和消息类型都是独立字段——
 * STRM 只关心自己的，签到失败不会因为上传没开通知而静默。
 */
import { NOTIFY_TYPES } from '../../plugin.js'

const props = defineProps({
  enabled: { type: Boolean, default: false },
  type: { type: String, default: 'Plugin' },
  label: { type: String, default: '执行后发送通知' },
  hint: { type: String, default: '' },
})
const emit = defineEmits(['update:enabled', 'update:type'])
</script>

<template>
  <div class="ntf">
    <div class="ntf__line">
      <v-switch
        :model-value="props.enabled"
        color="primary"
        density="compact"
        hide-details
        :label="props.label"
        @update:model-value="value => emit('update:enabled', Boolean(value))"
      />
      <v-select
        :model-value="props.type"
        :items="NOTIFY_TYPES"
        :disabled="!props.enabled"
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
.ntf {
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
}
</style>
