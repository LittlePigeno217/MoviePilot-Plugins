/**
 * 独立联调用的宿主替身。MoviePilot 真正的宿主会注入自己的 Vuetify 主题，
 * 这里按 MoviePilot v2 的主题值复刻一份浅色 / 深色，用来验证插件是否真的跟随主题。
 * 同时提供一个假的 api，让台账页在没有后端的情况下也能渲染出数据。
 */
import { createApp, h, ref } from 'vue'
import { createVuetify, useTheme } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'
import Config from './components/Config.vue'
import Page from './components/Page.vue'

const vuetify = createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: 'mpLight',
    themes: {
      mpLight: {
        dark: false,
        colors: {
          primary: '#8D51F9',
          background: '#F4F5FA',
          surface: '#FFFFFF',
          'on-surface': '#3A3541',
          'on-primary': '#FFFFFF',
          success: '#56CA00',
          error: '#FF4C51',
          warning: '#FFB400',
        },
        variables: { 'border-color': '#3A3541', 'border-opacity': 0.12, 'medium-emphasis-opacity': 0.68 },
      },
      mpDark: {
        dark: true,
        colors: {
          primary: '#6E66ED',
          background: '#0E1116',
          surface: '#14161F',
          'on-surface': '#E7E3FC',
          'on-primary': '#FFFFFF',
          success: '#56CA00',
          error: '#FF4C51',
          warning: '#FFB400',
        },
        variables: { 'border-color': '#E7E3FC', 'border-opacity': 0.12, 'medium-emphasis-opacity': 0.68 },
      },
    },
  },
})

// ── 假数据：形状与 __init__.py 的 /status、/config 返回一致 ──────────
const pad = n => String(n).padStart(2, '0')
const stamp = (back, hour = 8, minute = 10) => {
  const d = new Date()
  d.setDate(d.getDate() - back)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(hour)}:${pad(minute)}:02`
}

const FAKE_CONFIG = {
  enabled: true,
  notify: true,
  cron: '10 8 * * *',
  timeout: 10,
  retry_count: 3,
  sites: {
    flzt: { enabled: true, use_proxy: false, email: 'me@example.com', password: 'secret' },
    right_forum: { enabled: true, use_proxy: true, cookie: 'auth=abcdefghijklmnop; saltkey=qrstuvwx' },
    ypojie: { enabled: true, use_proxy: false, email: '', password: '' },
  },
}

const FAKE_HISTORY = [
  { version: 2, time: stamp(0), status: '部分成功', message: '2 个站点成功，1 个失败', success_count: 2, failure_count: 1, site_count: 3, details: [
    { site: 'flzt', site_name: 'FLZT', status: '签到成功', message: '签到成功，获得 128MB 上传量', account: 'me@example.com', reward_mb: '128', total_traffic: '32.5GB', time: stamp(0) },
    { site: 'right_forum', site_name: '恩山无线论坛', status: '今日已签到', message: '今日已签到，明天再来', account: 'Cookie', reward_mb: '-', total_traffic: '-', time: stamp(0) },
    { site: 'ypojie', site_name: '易破解', status: '执行失败', message: '账号或密码未填写', account: '-', reward_mb: '-', total_traffic: '-', time: stamp(0) },
  ] },
  { version: 2, time: stamp(1), status: '全部成功', message: '3 个站点全部签到成功', success_count: 3, failure_count: 0, site_count: 3, details: [
    { site: 'flzt', site_name: 'FLZT', status: '签到成功', message: '签到成功，获得 96MB 上传量', account: 'me@example.com', reward_mb: '96', total_traffic: '32.4GB', time: stamp(1) },
  ] },
  { version: 2, time: stamp(2), status: '执行失败', message: '网络连接超时', success_count: 0, failure_count: 3, site_count: 3, details: [] },
  { version: 2, time: stamp(3), status: '全部成功', message: '3 个站点全部签到成功', success_count: 3, failure_count: 0, site_count: 3, details: [] },
  { version: 2, time: stamp(4), status: '全部成功', message: '3 个站点全部签到成功', success_count: 3, failure_count: 0, site_count: 3, details: [] },
  { version: 2, time: stamp(6), status: '部分成功', message: '2 个站点成功，1 个失败', success_count: 2, failure_count: 1, site_count: 3, details: [] },
  { version: 2, time: stamp(7), status: '全部成功', message: '3 个站点全部签到成功', success_count: 3, failure_count: 0, site_count: 3, details: [] },
]

const FAKE_STATUS = {
  enabled: true,
  notify: true,
  cron: '10 8 * * *',
  configured: true,
  enabled_site_count: 3,
  configured_site_count: 2,
  last_status: '部分成功',
  last_run: stamp(0),
  last_result: FAKE_HISTORY[0],
  next_run_time: stamp(-1),
  task_status: '已注册',
  history: FAKE_HISTORY,
  history_count: FAKE_HISTORY.length,
  sites: [
    { key: 'flzt', name: 'FLZT', mode: '账号密码', enabled: true, use_proxy: false, configured: true, account: 'me@example.com', last_status: '签到成功', last_message: '签到成功，获得 128MB 上传量', last_run: stamp(0) },
    { key: 'right_forum', name: '恩山无线论坛', mode: 'Cookie', enabled: true, use_proxy: true, configured: true, account: 'Cookie', last_status: '今日已签到', last_message: '今日已签到，明天再来', last_run: stamp(0) },
    { key: 'ypojie', name: '易破解', mode: '账号密码', enabled: true, use_proxy: false, configured: false, account: '', last_status: '执行失败', last_message: '账号或密码未填写', last_run: stamp(0) },
  ],
}

const wait = ms => new Promise(resolve => setTimeout(resolve, ms))

const fakeApi = {
  async get(path) {
    await wait(220)
    if (path.endsWith('/config')) return { data: FAKE_CONFIG }
    if (path.endsWith('/status')) return { data: FAKE_STATUS }
    if (path.endsWith('/history')) return { data: FAKE_HISTORY }
    return { data: {} }
  },
  async post(path) {
    await wait(600)
    if (path.endsWith('/run')) return { success: true, message: '2 个站点成功，1 个失败' }
    if (path.endsWith('/test-login')) return { success: true, message: '3 个站点可连通' }
    if (path.endsWith('/history/clear')) return { success: true, message: '历史已清空' }
    return { success: true, message: '' }
  },
}

const Harness = {
  setup() {
    const theme = useTheme()
    const view = ref('page')
    const saving = ref(false)
    const lastSavedAt = ref(0)

    const toggleTheme = () => {
      const next = theme.global.name.value === 'mpLight' ? 'mpDark' : 'mpLight'
      if (typeof theme.change === 'function') theme.change(next)
      else theme.global.name.value = next
    }
    const toggleView = () => {
      view.value = view.value === 'config' ? 'page' : 'config'
    }
    const onSave = async () => {
      saving.value = true
      await wait(700)
      saving.value = false
      lastSavedAt.value = Date.now()
    }

    return () =>
      h('div', { style: 'min-height:100vh;background:rgb(var(--v-theme-background));padding:24px' }, [
        h('div', { style: 'display:flex;gap:8px;margin-bottom:16px' }, [
          h(components.VBtn, { size: 'small', onClick: toggleTheme }, () => `主题：${theme.global.name.value}`),
          h(components.VBtn, { size: 'small', onClick: toggleView }, () => `视图：${view.value}`),
        ]),
        h(components.VCard, { style: 'max-width:58rem;margin:auto;overflow:hidden' }, () => [
          view.value === 'config'
            ? h(Config, {
                key: 'config',
                api: fakeApi,
                initialConfig: FAKE_CONFIG,
                saving: saving.value,
                lastSavedAt: lastSavedAt.value,
                onSave,
                onSwitch: toggleView,
              })
            : h(Page, { key: 'page', api: fakeApi, onSwitch: toggleView }),
        ]),
      ])
  },
}

createApp(Harness).use(vuetify).mount('#app')
