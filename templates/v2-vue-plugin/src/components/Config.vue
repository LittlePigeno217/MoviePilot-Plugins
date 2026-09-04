<script setup>
// 设置页骨架。外壳照 docs/Plugin_UI_Spec.md 第 4.3 节：左边一条导轨、右边一个分区面板。
// 分区按你的插件真实的关注点划分，导轨上每一项带一行状态（已开启 / 待填写 / 3 条），
// 不点进去就知道哪个还没配好。
import { computed, inject, reactive, ref, watch } from 'vue'
import AppBar from './ui/AppBar.vue'
import '../styles/kit.scss'

const props = defineProps({
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: [Object, Function], default: null },
  saving: { type: Boolean, default: false },
})
const emit = defineEmits(['save', 'close', 'switch'])

const DEFAULT_CONFIG = { enabled: false, notify: true, cron: '10 8 * * *', target: '' }
const config = reactive({ ...DEFAULT_CONFIG })
const section = ref('run')
const local = reactive({ text: '', kind: 'info' })
const toast = inject('moviepilot:toast', null)

function notify(text, kind = 'info') {
  if (toast) toast[kind]?.(text) ?? toast(text)
  else Object.assign(local, { text, kind })
}

// 导轨：一项一个分区，note 是那一项此刻的状态
const sections = computed(() => [
  { key: 'run', icon: 'mdi-clock-outline', label: '执行方式', note: config.enabled ? '已开启' : '已关闭' },
  { key: 'target', icon: 'mdi-folder-outline', label: '目标', note: config.target ? '已填写' : '待填写' },
])

const barState = computed(() => (config.enabled ? '已开启' : '已关闭'))
const barTone = computed(() => (config.enabled ? 'on' : 'idle'))

watch(() => props.initialConfig, value => Object.assign(config, DEFAULT_CONFIG, value || {}), {
  immediate: true,
  deep: true,
})

const reload = () => Object.assign(config, DEFAULT_CONFIG, props.initialConfig || {})

function save() {
  if (config.enabled && !config.target) {
    notify('开启之后要先填目标', 'error')
    return
  }
  emit('save', { ...config })
}
</script>

<template>
  <div class="tpl cfg">
    <AppBar
      view="设置"
      :state="barState"
      :tone="barTone"
      show-refresh
      @refresh="reload"
      @switch="emit('switch')"
      @close="emit('close')"
    />

    <button
      v-if="local.text"
      type="button"
      class="cfg__local"
      :class="`cfg__local--${local.kind}`"
      @click="local.text = ''"
    >
      {{ local.text }}
      <span class="cfg__local-x">知道了</span>
    </button>

    <div class="cfg__shell">
      <nav class="cfg__rail" aria-label="设置分区">
        <button
          v-for="item in sections"
          :key="item.key"
          type="button"
          class="cfg__tab"
          :class="{ 'cfg__tab--on': section === item.key }"
          :aria-current="section === item.key ? 'true' : undefined"
          @click="section = item.key"
        >
          <v-icon :icon="item.icon" size="17" />
          <span class="cfg__tab-text">
            <span class="cfg__tab-label">{{ item.label }}</span>
            <span class="cfg__tab-note">{{ item.note }}</span>
          </span>
        </button>
      </nav>

      <!-- key 跟着分区变：切换时这块重新挂载，入场动画重播一次。
           不用 <Transition>，因为 out-in 会给切换硬加一段离场延迟，
           而设置面板的手感应该是「立刻到」。 -->
      <div :key="section" class="cfg__pane tpl-enter">
        <section v-if="section === 'run'" class="tpl-panel">
          <div class="tpl-panel__head">
            <div>
              <h3 class="tpl-section-title">执行方式</h3>
              <p class="tpl-hint">关掉插件就不执行。这句话说清「开关意味着什么」，别写成「是否启用」。</p>
            </div>
          </div>
          <div class="tpl-panel__body">
            <div class="cfg__switches">
              <v-switch v-model="config.enabled" color="primary" density="compact" hide-details label="启用插件" />
              <v-switch v-model="config.notify" color="primary" density="compact" hide-details label="执行后发送通知" />
            </div>
            <div class="cfg__fields tpl-row-sep">
              <v-text-field
                v-model="config.cron"
                label="执行时间"
                variant="outlined"
                density="compact"
                placeholder="10 8 * * *"
                hint="cron 表达式，10 8 * * * 是每天 08:10"
                persistent-hint
              />
            </div>
          </div>
        </section>

        <section v-else class="tpl-panel">
          <div class="tpl-panel__head">
            <h3 class="tpl-section-title">
              目标
              <span v-if="!config.target" class="tpl-pill tpl-pill--warn">待填写</span>
            </h3>
          </div>
          <div class="tpl-panel__body">
            <div class="cfg__fields">
              <v-text-field
                v-model="config.target"
                label="目标目录"
                variant="outlined"
                density="compact"
                hide-details
              />
            </div>
          </div>
        </section>
      </div>
    </div>

    <footer class="cfg__foot">
      <span class="cfg__foot-note tpl-muted">保存后立即生效，不用重启 MoviePilot。</span>
      <span class="cfg__foot-acts">
        <v-btn variant="text" size="small" :disabled="saving" @click="reload">放弃改动</v-btn>
        <v-btn color="primary" variant="flat" size="small" :loading="saving" @click="save">保存配置</v-btn>
      </span>
    </footer>
  </div>
</template>

<style scoped lang="scss">
.cfg__local {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  margin: 0;
  padding: 8px 16px;
  border: 0;
  border-bottom: 1px solid var(--tpl-line);
  background: var(--tpl-faint);
  color: inherit;
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.cfg__local-x {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--tpl-ink-50);
}

.cfg__local--error {
  color: var(--tpl-bad);
}

.cfg__local--success {
  color: var(--tpl-ok);
}

.cfg__shell {
  display: grid;
  grid-template-columns: 13rem minmax(0, 1fr);
  align-items: start;
  gap: 16px;
  padding: 16px;
}

.cfg__rail {
  display: flex;
  flex-direction: column;
  gap: 2px;
  position: sticky;
  top: 58px;
}

.cfg__tab {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--tpl-ink-50);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.cfg__tab:hover {
  background: var(--tpl-faint);
}

.cfg__tab:focus-visible {
  outline: 2px solid var(--tpl-accent);
  outline-offset: 1px;
}

.cfg__tab--on {
  background: var(--tpl-accent-soft);
  border-color: var(--tpl-accent);
  color: var(--tpl-accent);
}

.cfg__tab-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.cfg__tab-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--tpl-ink);
  line-height: 1.3;
}

.cfg__tab--on .cfg__tab-label {
  color: var(--tpl-accent);
}

.cfg__tab-note {
  font-size: 11px;
  color: var(--tpl-ink-50);
  line-height: 1.3;
}

.cfg__pane {
  min-width: 0;
}

.cfg__switches {
  display: grid;
  gap: 2px 20px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.cfg__fields {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  align-items: start;
}

.cfg__wide {
  grid-column: 1 / -1;
}

.cfg__foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  border-top: 1px solid var(--tpl-line);
  background: var(--tpl-paper);
  position: sticky;
  bottom: 0;
  z-index: 2;
}

.cfg__foot-note {
  font-size: 12px;
}

.cfg__foot-acts {
  display: flex;
  gap: 8px;
  margin-inline-start: auto;
}

@media (max-width: 720px) {
  .cfg__shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .cfg__rail {
    position: static;
    flex-direction: row;
    overflow-x: auto;
    padding-bottom: 2px;
  }

  .cfg__tab {
    flex: 0 0 auto;
  }

  .cfg__tab-note {
    display: none;
  }

  .cfg__foot-note {
    display: none;
  }
}
</style>
