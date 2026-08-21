<script setup>
/**
 * 通道（Conduit）—— 本插件的签名元素。
 *
 * 插件做的每件事都是一次“搬运”：115 的某个目录 → 本地某个目录。与其把它拆成
 * 两个互不相干的输入框，这里把一条映射画成一条真实的通道：左端是起点，右端是
 * 终点，中间是带方向的管线。通道亮起代表这条映射启用，熄灭代表停用——开关的
 * 状态因此不需要额外文字解释。
 */
import { computed } from 'vue'

const props = defineProps({
  enabled: { type: Boolean, default: true },
  stops: { type: Array, default: () => [] },
  index: { type: Number, default: 0 },
})
const emit = defineEmits(['update:enabled', 'pick', 'remove'])

const live = computed(() => props.enabled)
</script>

<template>
  <div class="conduit" :class="{ 'conduit--live': live }">
    <div class="conduit__bar">
      <v-switch
        :model-value="enabled"
        color="primary"
        density="compact"
        hide-details
        :aria-label="enabled ? '停用这条通道' : '启用这条通道'"
        @update:model-value="value => emit('update:enabled', Boolean(value))"
      />
      <span class="conduit__ordinal p115-mono">通道 {{ index + 1 }}</span>
      <v-spacer />
      <v-btn
        icon="mdi-close"
        variant="text"
        size="x-small"
        aria-label="删除这条通道"
        @click="emit('remove')"
      />
    </div>

    <div class="conduit__track">
      <template v-for="(stop, position) in stops" :key="stop.key">
        <span v-if="position" class="conduit__flow" aria-hidden="true">
          <span class="conduit__flow-line" />
          <v-icon icon="mdi-chevron-right" size="16" class="conduit__flow-head" />
        </span>
        <button type="button" class="conduit__stop" @click="emit('pick', stop.key)">
          <span class="conduit__stop-tag">
            <v-icon :icon="stop.icon" size="13" />
            {{ stop.tag }}
          </span>
          <span v-if="stop.value" class="conduit__stop-path p115-mono">{{ stop.value }}</span>
          <span v-else class="conduit__stop-path conduit__stop-path--empty">{{ stop.placeholder }}</span>
        </button>
      </template>
    </div>
  </div>
</template>

<style scoped lang="scss">
.conduit {
  border: 1px solid var(--p115-hairline);
  border-radius: var(--p115-radius);
  background: var(--p115-paper);
  overflow: hidden;
}

.conduit + .conduit {
  margin-top: 10px;
}

.conduit__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px 6px 12px;
  border-bottom: 1px solid var(--p115-hairline);
  background: var(--p115-faint);
}

.conduit__ordinal {
  color: var(--p115-muted);
  letter-spacing: 0.08em;
}

.conduit--live .conduit__ordinal {
  color: var(--p115-accent);
}

.conduit__track {
  display: flex;
  align-items: stretch;
  gap: 0;
  padding: 12px;
  flex-wrap: wrap;
}

.conduit__stop {
  flex: 1 1 190px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 5px;
  padding: 10px 12px;
  border: 1px solid var(--p115-hairline);
  border-radius: 8px;
  background: var(--p115-well);
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.conduit__stop:hover,
.conduit__stop:focus-visible {
  border-color: var(--p115-accent);
  background: var(--p115-accent-soft);
}

.conduit__stop:focus-visible {
  outline: 2px solid var(--p115-accent);
  outline-offset: 1px;
}

.conduit__stop-tag {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: var(--p115-muted);
}

.conduit--live .conduit__stop-tag {
  color: var(--p115-accent);
}

.conduit__stop-path {
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--p115-mono);
  font-size: 12px;
}

.conduit__stop-path--empty {
  color: var(--p115-muted);
  font-style: italic;
}

// 管线本体：熄灭时是一条静止的细线，亮起时流动
.conduit__flow {
  flex: 0 0 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  color: var(--p115-muted);
}

.conduit__flow-line {
  position: absolute;
  inset-inline: 2px;
  height: 2px;
  background: currentColor;
  opacity: 0.35;
}

.conduit--live .conduit__flow {
  color: var(--p115-accent);
}

.conduit--live .conduit__flow-line {
  opacity: 1;
  background: repeating-linear-gradient(
    90deg,
    currentColor 0 6px,
    transparent 6px 12px
  );
  animation: conduit-drift 0.9s linear infinite;
}

.conduit__flow-head {
  position: relative;
  background: var(--p115-paper);
}

@keyframes conduit-drift {
  to {
    background-position-x: 12px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .conduit--live .conduit__flow-line {
    animation: none;
  }
}

@media (max-width: 620px) {
  .conduit__track {
    flex-direction: column;
  }

  .conduit__stop {
    flex: 0 0 auto;
    width: 100%;
  }

  .conduit__flow {
    flex: 0 0 24px;
    width: 100%;
    justify-content: flex-start;
    padding-inline-start: 18px;
  }

  .conduit__flow-line {
    inset-inline: auto;
    inset-inline-start: 22px;
    width: 2px;
    height: 100%;
  }

  .conduit--live .conduit__flow-line {
    background: repeating-linear-gradient(180deg, currentColor 0 6px, transparent 6px 12px);
    animation: none;
  }

  .conduit__flow-head {
    transform: rotate(90deg);
  }
}
</style>
