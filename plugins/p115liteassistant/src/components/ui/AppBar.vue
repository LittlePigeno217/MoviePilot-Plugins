<script setup>
/**
 * 插件自己的标题栏。MoviePilot 的 vue 渲染分支不提供标题和关闭按钮
 * （VCardText 用了 pa-0），所以这些控件必须由插件提供。
 */
defineProps({
  view: { type: String, default: '' },
  online: { type: Boolean, default: false },
  // 第一次状态还没读到时既不是已连接也不是未连接，别替用户下结论
  probing: { type: Boolean, default: false },
  showSwitch: { type: Boolean, default: true },
  busy: { type: Boolean, default: false },
  showRefresh: { type: Boolean, default: false },
})
const emit = defineEmits(['switch', 'close', 'refresh'])
</script>

<template>
  <header class="bar">
    <div class="bar__id">
      <span class="bar__glyph" aria-hidden="true">115</span>
      <span class="bar__names">
        <span class="bar__name">轻量助手</span>
        <span class="bar__view p115-label">{{ view }}</span>
      </span>
    </div>

    <span class="bar__link" :class="{ 'bar__link--on': online && !probing }">
      <span class="bar__dot" aria-hidden="true" />
      {{ probing ? '正在读取…' : online ? '已连接 115' : '未连接 115' }}
    </span>

    <div class="bar__tools">
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
        :aria-label="view === '运行台' ? '前往设置' : '前往运行台'"
        @click="emit('switch')"
      />
      <v-btn icon="mdi-close" variant="text" size="small" aria-label="关闭" @click="emit('close')" />
    </div>
  </header>
</template>

<style scoped lang="scss">
.bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 12px 10px 16px;
  border-bottom: 1px solid var(--p115-hairline);
  background: var(--p115-paper);
  position: sticky;
  top: 0;
  z-index: 3;
}

.bar__id {
  display: flex;
  align-items: center;
  gap: 10px;
  // 由它吃掉中间的空白：这样不论状态那一格在不在，工具按钮都贴着右边
  flex: 1 1 auto;
  min-width: 0;
}

.bar__glyph {
  display: grid;
  place-items: center;
  inline-size: 34px;
  block-size: 26px;
  border-radius: 6px;
  background: var(--p115-accent);
  color: rgb(var(--v-theme-on-primary));
  font-family: var(--p115-mono);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.02em;
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

.bar__link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: none;
  font-size: 12px;
  color: var(--p115-muted);
  white-space: nowrap;
}

.bar__dot {
  inline-size: 6px;
  block-size: 6px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.5;
}

.bar__link--on {
  color: rgb(var(--v-theme-success));
}

.bar__link--on .bar__dot {
  opacity: 1;
}

.bar__tools {
  display: flex;
  align-items: center;
  gap: 2px;
  flex: none;
}

@media (max-width: 560px) {
  .bar__link {
    display: none;
  }
}
</style>
