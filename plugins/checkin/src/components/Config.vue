<script setup>
// 自用签到 · 设置页。视觉与台账页同一套语言，校验逻辑不变：
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

    <button v-if="local.text" type="button" class="cfg__local" :class="`cfg__local--${local.kind}`" @click="local.text = ''">
      {{ local.text }}
      <span class="cfg__local-x">知道了</span>
    </button>

    <section class="ck-sheet">
      <div class="ck-sheet__head">
        <h3 class="ck-title">执行方式</h3>
        <p class="ck-hint">插件关掉时定时任务不会注册，手动签到也不会执行。</p>
      </div>

      <div class="cfg__switches">
        <v-switch v-model="config.enabled" color="primary" density="compact" hide-details label="启用插件" />
        <v-switch v-model="config.notify" color="primary" density="compact" hide-details label="执行后发送通知" />
      </div>

      <div class="cfg__fields">
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
    </section>

    <section v-for="site in siteList" :key="site.key" class="ck-sheet">
      <div class="ck-sheet__head">
        <h3 class="ck-title cfg__site-title">
          <span class="cfg__badge ck-mono" aria-hidden="true">{{ site.badge }}</span>
          {{ site.title }}
          <span class="ck-chip">{{ site.mode }}</span>
          <span v-if="pending(site.key)" class="ck-chip ck-chip--warn">待填写</span>
        </h3>
        <v-switch
          v-model="config.sites[site.key].enabled"
          color="primary"
          density="compact"
          hide-details
          :label="config.sites[site.key].enabled ? '已启用' : '已关闭'"
        />
      </div>

      <div class="cfg__fields">
        <template v-if="site.key === 'right_forum'">
          <v-textarea
            v-model="config.sites[site.key].cookie"
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
            v-model="config.sites[site.key].email"
            :label="site.key === 'flzt' ? '登录邮箱' : '登录账号'"
            variant="outlined"
            density="compact"
            autocomplete="off"
            hide-details
          />
          <v-text-field
            v-model="config.sites[site.key].password"
            label="密码"
            type="password"
            variant="outlined"
            density="compact"
            autocomplete="new-password"
            hide-details
          />
        </template>
        <v-switch
          v-model="config.sites[site.key].use_proxy"
          color="primary"
          density="compact"
          hide-details
          label="通过代理访问"
        />
      </div>
    </section>

    <footer class="cfg__foot">
      <span class="cfg__foot-note ck-muted">保存后立即生效，无需重启 MoviePilot。</span>
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
  margin-bottom: 10px;
}

.cfg__fields {
  display: grid;
  gap: 12px 14px;
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

@media (max-width: 620px) {
  .cfg__foot-note {
    display: none;
  }
}
</style>
