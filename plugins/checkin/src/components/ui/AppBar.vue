<script setup>
/**
 * 插件自己的标题栏。MoviePilot 的 vue 渲染分支不提供标题和关闭按钮
 * （VCardText 用了 pa-0），所以这些控件必须由插件提供。
 */
defineProps({
  view: { type: String, default: '' },
  state: { type: String, default: '' },
  tone: { type: String, default: 'idle' },
  showSwitch: { type: Boolean, default: true },
  showRefresh: { type: Boolean, default: false },
  busy: { type: Boolean, default: false },
})
const emit = defineEmits(['switch', 'close', 'refresh'])
</script>

<template>
  <header class="bar">
    <span class="bar__mark" aria-hidden="true">签</span>

    <span class="bar__names">
      <span class="bar__name">自用签到</span>
      <span class="bar__view ck-eyebrow">{{ view }}</span>
    </span>

    <span v-if="state" class="bar__state" :class="`bar__state--${tone}`">
      <span class="bar__dot" aria-hidden="true" />
      {{ state }}
    </span>

    <span class="bar__tools">
      <v-btn
        v-if="showRefresh"
        icon="mdi-refresh"
        variant="text"
        size="small"
        :loading="busy"
        aria-label="刷新状态"
        @click="emit('refresh')"
      />
      <v-btn
        v-if="showSwitch"
        icon="mdi-swap-horizontal"
        variant="text"
        size="small"
        :aria-label="view === '台账' ? '前往设置' : '前往台账'"
        @click="emit('switch')"
      />
      <v-btn icon="mdi-close" variant="text" size="small" aria-label="关闭" @click="emit('close')" />
    </span>
  </header>
</template>

<style scoped lang="scss">
.bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px 10px 16px;
  border-bottom: 1px solid var(--ck-line);
  background: var(--ck-paper);
  position: sticky;
  top: 0;
  z-index: 3;
}

.bar__mark {
  display: grid;
  place-items: center;
  inline-size: 26px;
  block-size: 26px;
  flex: none;
  border: 1px solid var(--ck-line-strong);
  border-radius: 6px;
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
}

.bar__names {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.bar__name {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
  line-height: 1.25;
}

.bar__view {
  line-height: 1.2;
}

.bar__state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-inline-start: auto;
  font-size: 12px;
  color: var(--ck-ink-50);
  white-space: nowrap;
}

.bar__dot {
  inline-size: 6px;
  block-size: 6px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.55;
}

.bar__state--on {
  color: var(--ck-accent);
}

.bar__state--warn {
  color: var(--ck-warn);
}

.bar__state--bad {
  color: var(--ck-bad);
}

.bar__state--on .bar__dot,
.bar__state--warn .bar__dot,
.bar__state--bad .bar__dot {
  opacity: 1;
}

.bar__tools {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-inline-start: auto;
}

.bar__state + .bar__tools {
  margin-inline-start: 0;
}

@media (max-width: 560px) {
  .bar__state {
    display: none;
  }
}
</style>
