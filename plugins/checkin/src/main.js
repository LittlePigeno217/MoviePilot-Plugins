/**
 * 独立联调用的宿主替身。MoviePilot 真正的宿主会注入自己的 Vuetify 主题，
 * 这里按 MoviePilot v2 的主题值复刻一份浅色 / 深色，用来验证插件是否真的跟随主题。
 * 同时提供一个假的 api，让运行台在没有后端的情况下也能渲染出数据。
 */
import { createApp, h, ref } from 'vue'
import { createVuetify, useTheme } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'
import Config from './components/Config.vue'
import Page from './components/Page.vue'

// 无头截图没法点按钮，所以主题与视图都能从 URL 指定：?theme=dark&view=config
const query = new URLSearchParams(globalThis.location?.search || '')
const INITIAL_THEME = query.get('theme') === 'dark' ? 'mpDark' : 'mpLight'
const INITIAL_VIEW = query.get('view') === 'config' ? 'config' : 'page'

const vuetify = createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: INITIAL_THEME,
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
          info: '#16B1FF',
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
          info: '#16B1FF',
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
    { site: 'flzt', site_name: 'FLZT', status: '签到成功', message: '操作成功', account: 'me@example.com', reward_mb: '1025.83', total_traffic: '142.22 GB', time: stamp(0) },
    { site: 'right_forum', site_name: '恩山无线论坛', status: '今日已签到', message: '今日积分：1；连续签到：1 天；总签到天数：28 天', account: 'Cookie 登录态', reward_mb: '-', total_traffic: '-', time: stamp(0) },
    { site: 'ypojie', site_name: '易破解', status: '执行失败', message: '本次签到增加：0积分', account: '-', reward_mb: '-', total_traffic: '-', time: stamp(0) },
  ] },
  { version: 2, time: stamp(1), status: '全部成功', message: '3 个站点全部签到成功', success_count: 3, failure_count: 0, site_count: 3, details: [
    { site: 'flzt', site_name: 'FLZT', status: '签到成功', message: '操作成功', account: 'me@example.com', reward_mb: '1850.28', total_traffic: '141.21 GB', time: stamp(1) },
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
  // 后端回的是 TimerUtils.time_difference() 的文字，不是时间戳
  next_run_time: '9小时30分钟后',
  task_status: '等待',
  // 漏签补跑视图：今天 08:10 那次没签成，巡检已经补过 1 次
  catchup: { cron: '*/30 * * * *', due_at: '08:10', used: 1, max: 5, pending: true },
  history: FAKE_HISTORY,
  history_count: FAKE_HISTORY.length,
  sites: [
    { key: 'flzt', name: 'FLZT', mode: '账号密码', enabled: true, use_proxy: false, configured: true, account: 'me@example.com', last_status: '签到成功', last_message: '操作成功', reward_mb: '1025.83', total_traffic: '142.22 GB', last_run: stamp(0) },
    { key: 'right_forum', name: '恩山无线论坛', mode: 'Cookie', enabled: true, use_proxy: true, configured: true, account: 'Cookie 登录态', last_status: '今日已签到', last_message: '今日积分：1；连续签到：1 天；总签到天数：28 天', reward_mb: '-', total_traffic: '-', last_run: stamp(0) },
    { key: 'ypojie', name: '易破解', mode: '账号密码', enabled: true, use_proxy: false, configured: false, account: '', last_status: '执行失败', last_message: 'body,div,html,p,span{margin:0;padding:0;border:0}', reward_mb: '-', total_traffic: '-', last_run: stamp(0) },
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
    const view = ref(INITIAL_VIEW)
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
