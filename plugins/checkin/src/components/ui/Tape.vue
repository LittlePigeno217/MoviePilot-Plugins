<script setup>
/**
 * 打卡带：最近 30 天，一天一格。今天那一格是真的按钮 —— 按下去就是签到，
 * 这个界面里唯一需要每天点一次的地方，就是记录本身。
 */
import { computed } from 'vue'
import { RANK_WORD } from '../../lib/ledger.js'

const props = defineProps({
  cells: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['punch'])

const RANK_CLASS = { 3: 'tape__cell--full', 2: 'tape__cell--part', 1: 'tape__cell--miss', 0: '' }

const first = computed(() => props.cells[0]?.label || '')
const last = computed(() => props.cells[props.cells.length - 1]?.label || '')
const signedDays = computed(() => props.cells.filter(cell => cell.rank === 3).length)

function title(cell) {
  return `${cell.day} · ${RANK_WORD[cell.rank]}`
}
</script>

<template>
  <div class="tape">
    <ol class="tape__run">
      <li v-for="cell in cells" :key="cell.day" class="tape__slot" :class="{ 'tape__slot--today': cell.today }">
        <button
          v-if="cell.today"
          type="button"
          class="tape__cell tape__cell--today"
          :class="[RANK_CLASS[cell.rank], { 'tape__cell--busy': busy }]"
          :disabled="disabled || busy"
          :aria-label="busy ? '正在签到' : `签到 ${cell.day}，当前${RANK_WORD[cell.rank]}`"
          :title="busy ? '正在签到' : `${title(cell)} · 点击签到`"
          @click="emit('punch')"
        >
          <span class="tape__today-hit" aria-hidden="true" />
        </button>
        <span
          v-else
          class="tape__cell"
          :class="RANK_CLASS[cell.rank]"
          :title="title(cell)"
        />
      </li>
    </ol>

    <div class="tape__scale ck-mono">
      <span>{{ first }}</span>
      <span class="tape__scale-mid">30 天里签上 {{ signedDays }} 天</span>
      <span>{{ last }} 今天</span>
    </div>
  </div>
</template>

<style scoped lang="scss">
.tape {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tape__run {
  display: flex;
  align-items: stretch;
  gap: 3px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.tape__slot {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
}

// 今天那一格既是记录也是按钮，给它更宽的落点
.tape__slot--today {
  flex: 0 0 34px;
}

// 每格是一道刻痕：没签是空槽，签上了是实心
.tape__cell {
  flex: 1 1 auto;
  min-width: 0;
  block-size: 46px;
  border: 1px solid var(--ck-line);
  border-radius: 3px;
  background: var(--ck-well);
  padding: 0;
}

.tape__cell--full {
  border-color: transparent;
  background: var(--ck-accent);
}

.tape__cell--part {
  border-color: transparent;
  background: var(--ck-warn);
}

.tape__cell--miss {
  border-color: transparent;
  background: var(--ck-ink-14);
}

.tape__cell--today {
  position: relative;
  border-color: var(--ck-ink);
  border-width: 2px;
  cursor: pointer;
  transition: transform 0.14s ease, background 0.14s ease;
}

.tape__cell--today:hover:not(:disabled) {
  transform: translateY(-2px);
  background: var(--ck-accent-soft);
}

.tape__cell--today.tape__cell--full:hover:not(:disabled),
.tape__cell--today.tape__cell--part:hover:not(:disabled) {
  background: var(--ck-accent);
}

.tape__cell--today:focus-visible {
  outline: 2px solid var(--ck-accent);
  outline-offset: 2px;
}

.tape__cell--today:disabled {
  cursor: default;
}

// 今天那一格里立着一根待打的针；正在跑的时候它上下动
.tape__today-hit {
  display: block;
  inline-size: 2px;
  block-size: 14px;
  margin: 0 auto;
  border-radius: 1px;
  background: var(--ck-ink);
}

.tape__cell--full .tape__today-hit,
.tape__cell--part .tape__today-hit {
  background: rgb(var(--v-theme-on-primary));
}

.tape__cell--busy .tape__today-hit {
  animation: tape-punch 0.7s ease-in-out infinite;
}

@keyframes tape-punch {
  0%,
  100% {
    transform: translateY(-6px);
  }
  50% {
    transform: translateY(6px);
  }
}

.tape__scale {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
  font-size: 10px;
  color: var(--ck-ink-50);
}

.tape__scale-mid {
  text-align: center;
}

@media (max-width: 620px) {
  .tape__run {
    gap: 2px;
  }

  .tape__cell {
    block-size: 38px;
  }

  .tape__slot--today {
    flex: 0 0 28px;
  }

  .tape__scale-mid {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .tape__cell--today {
    transition: none;
  }

  .tape__cell--today:hover:not(:disabled) {
    transform: none;
  }

  .tape__cell--busy .tape__today-hit {
    animation: none;
  }
}
</style>
