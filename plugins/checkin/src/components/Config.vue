<script setup>
// 自用签到 · 设置页。视觉与运行台同一套语言，校验逻辑不变：
// 保存前跑一遍 validateConfig，通过后交给宿主写入配置。
import { computed, inject, reactive, ref, watch } from 'vue'
import AppBar from './ui/AppBar.vue'
import { SITE_META, clone, normalizeConfig, pluginGet, validateConfig, useHostNotice } from '../plugin.js'
import '../styles/kit.scss'

const props = defineProps({
  initialConfig: { type: Object, default: () => ({}) },
  api: { type: [Object, Function], default: null },
  saving: { type: Boolean, default: false },
  lastSavedAt: { type: Number, default: 0 },
})
const emit = defineEmits(['save', 'close', 'switch'])

const config = reactive(normalizeConfig())
const submitted = ref(false)
const local = reactive({ text: '', kind: 'info' })
const notice = useHostNotice(inject('moviepilot:toast', null), (text, kind) => {
  local.text = text
  local.kind = kind
})

const siteList = Object.values(SITE_META)

// 设置分区：与 115 轻量助手同一套外壳 —— 左边一条导轨，右边一个分区面板。
// 一个站点一个分区，导轨上顺带把每个站点的状态摆出来（已开启 / 待填写 / 已关闭），
// 不用点进去就知道哪个还没配好。
const section = ref('run')
const SECTION_ICON = {
  run: 'mdi-clock-outline',
  flzt: 'mdi-download-network-outline',
  right_forum: 'mdi-forum-outline',
  ypojie: 'mdi-package-variant-closed',
}

// 每个站点是不是「开了但没填」——设置页唯一需要提醒的事
function pending(key) {
  const site = config.sites[key]
  if (!site?.enabled) return false
  if (key === 'right_forum') return !String(site.cookie || '').trim()
  return !site.email || !site.password
}

const openCount = computed(() => siteList.filter(site => config.sites[site.key]?.enabled).length)
const pendingCount = computed(() => siteList.filter(site => pending(site.key)).length)

const barState = computed(() => {
  if (!openCount.value) return '没有启用站点'
  if (pendingCount.value) return `${pendingCount.value} 个站点待填写`
  return `${openCount.value} 个站点就绪`
})
const barTone = computed(() => {
  if (!openCount.value) return 'idle'
  return pendingCount.value ? 'warn' : 'on'
})

const siteNote = key => {
  if (!config.sites[key]?.enabled) return '已关闭'
  return pending(key) ? '待填写' : '已开启'
}

const sections = computed(() => [
  { key: 'run', icon: SECTION_ICON.run, label: '执行方式', note: config.enabled ? '已开启' : '已关闭' },
  ...siteList.map(site => ({
    key: site.key,
    icon: SECTION_ICON[site.key],
    label: site.title,
    note: siteNote(site.key),
  })),
])

// 当前分区对应的站点；执行方式那一分区返回 null
const activeSite = computed(() => SITE_META[section.value] || null)

function apply(value = {}) {
  Object.assign(config, normalizeConfig(value))
}

async function reload() {
  if (!props.api) {
    apply(props.initialConfig)
    return
  }
  try {
    apply(await pluginGet(props.api, '/config'))
    notice.info('已读取当前配置')
  } catch (error) {
    notice.error(error?.message || '配置读取失败')
  }
}

function save() {
  const errors = validateConfig(config)
  if (errors.length) {
    submitted.value = false
    notice.error(errors.join('；'))
    return
  }
  submitted.value = true
  emit('save', clone(config))
}

watch(() => props.initialConfig, apply, { immediate: true, deep: true })
watch(() => props.lastSavedAt, value => {
  if (!value || !submitted.value) return
  submitted.value = false
  notice.success('配置已保存')
})
</script>

<template>
  <div class="ck cfg">
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
      <div :key="section" class="cfg__pane ck-enter">
        <section v-if="section === 'run'" class="ck-panel">
          <div class="ck-panel__head">
            <div>
              <h3 class="ck-section-title">执行方式</h3>
              <p class="ck-hint">关掉插件就不执行。到点机器没在跑也不会漏，每半小时自动补一次。</p>
            </div>
          </div>
          <div class="ck-panel__body">
            <div class="cfg__switches">
              <v-switch v-model="config.enabled" color="primary" density="compact" hide-details label="启用插件" />
              <v-switch v-model="config.notify" color="primary" density="compact" hide-details label="执行后发送通知" />
            </div>

            <div class="cfg__fields ck-row-sep">
              <v-text-field
                v-model="config.cron"
                label="执行时间"
                variant="outlined"
                density="compact"
                placeholder="10 8 * * *"
                hint="cron 表达式，10 8 * * * 是每天 08:10"
                persistent-hint
              />
              <v-text-field
                v-model.number="config.timeout"
                label="单次请求超时（秒）"
                type="number"
                min="5"
                variant="outlined"
                density="compact"
                hide-details
              />
              <v-text-field
                v-model.number="config.retry_count"
                label="失败重试次数"
                type="number"
                min="1"
                variant="outlined"
                density="compact"
                hide-details
              />
            </div>
          </div>
        </section>

        <section v-else-if="activeSite" class="ck-panel">
          <div class="ck-panel__head">
            <h3 class="ck-section-title cfg__site-title">
              <span class="cfg__badge ck-mono" aria-hidden="true">{{ activeSite.badge }}</span>
              {{ activeSite.title }}
              <span class="ck-pill">{{ activeSite.mode }}</span>
              <span v-if="pending(activeSite.key)" class="ck-pill ck-pill--warn">待填写</span>
            </h3>
            <v-switch
              v-model="config.sites[activeSite.key].enabled"
              color="primary"
              density="compact"
              hide-details
              :label="config.sites[activeSite.key].enabled ? '已开启' : '已关闭'"
            />
          </div>

          <div class="ck-panel__body">
            <div class="cfg__fields">
              <template v-if="activeSite.key === 'right_forum'">
                <v-textarea
                  v-model="config.sites[activeSite.key].cookie"
                  class="cfg__wide"
                  label="Cookie"
                  variant="outlined"
                  density="compact"
                  rows="3"
                  auto-grow
                  no-resize
                  hint="从浏览器复制登录后的完整 Cookie，需要包含 auth 或 saltkey"
                  persistent-hint
                />
              </template>
              <template v-else>
                <v-text-field
                  v-model="config.sites[activeSite.key].email"
                  :label="activeSite.key === 'flzt' ? '登录邮箱' : '登录账号'"
                  variant="outlined"
                  density="compact"
                  autocomplete="off"
                  hide-details
                />
                <v-text-field
                  v-model="config.sites[activeSite.key].password"
                  label="密码"
                  type="password"
                  variant="outlined"
                  density="compact"
                  autocomplete="new-password"
                  hide-details
                />
              </template>
              <v-switch
                v-model="config.sites[activeSite.key].use_proxy"
                color="primary"
                density="compact"
                hide-details
                label="通过代理访问"
              />
            </div>
          </div>
        </section>
      </div>
    </div>

    <footer class="cfg__foot">
      <span class="cfg__foot-note ck-muted">保存后立即生效，不用重启 MoviePilot。</span>
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
  border-bottom: 1px solid var(--ck-line);
  background: var(--ck-faint);
  color: inherit;
  font: inherit;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
}

.cfg__local-x {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--ck-ink-50);
}

.cfg__local--error {
  color: var(--ck-bad);
}

.cfg__local--success {
  color: var(--ck-ok);
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
  color: var(--ck-ink-50);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
}

.cfg__tab:hover {
  background: var(--ck-faint);
}

.cfg__tab:focus-visible {
  outline: 2px solid var(--ck-accent);
  outline-offset: 1px;
}

.cfg__tab--on {
  background: var(--ck-accent-soft);
  border-color: var(--ck-accent);
  color: var(--ck-accent);
}

.cfg__tab-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.cfg__tab-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--ck-ink);
  line-height: 1.3;
}

.cfg__tab--on .cfg__tab-label {
  color: var(--ck-accent);
}

.cfg__tab-note {
  font-size: 11px;
  color: var(--ck-ink-50);
  line-height: 1.3;
}

.cfg__pane {
  min-width: 0;
}

.cfg__site-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.cfg__badge {
  display: grid;
  place-items: center;
  inline-size: 30px;
  block-size: 22px;
  border: 1px solid var(--ck-line-strong);
  border-radius: 4px;
  font-size: 10px;
  font-weight: 700;
  color: var(--ck-ink-70);
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
  border-top: 1px solid var(--ck-line);
  background: var(--ck-paper);
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
