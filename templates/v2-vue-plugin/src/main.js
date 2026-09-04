/**
 * 独立联调用的宿主替身。MoviePilot 真正的宿主会注入自己的 Vuetify 主题，这里按 MoviePilot v2
 * 的主题值复刻一份浅色 / 深色，用来验证插件是否真的跟随主题（kit.scss 里不允许写死颜色，
 * 全靠这些 --v-theme-* 变量）。同时提供一个假的 api，让两个视图在没有后端时也能渲染出数据。
 *
 * 只服务 `npm run dev`，不进生产构建（vite.config.js 里有说明）。
 *
 * 无头截图点不了按钮，所以主题与视图都能从 URL 指定：?theme=dark&view=config
 */
import { createApp, h, ref } from 'vue'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'
import Config from './components/Config.vue'
import Page from './components/Page.vue'

const query = new URLSearchParams(globalThis.location?.search || '')
const INITIAL_THEME = query.get('theme') === 'dark' ? 'mpDark' : 'mpLight'
const INITIAL_VIEW = query.get('view') === 'config' ? 'config' : 'page'

const SHARED = {
  success: '#56CA00',
  error: '#FF4C51',
  warning: '#FFB400',
  info: '#16B1FF',
  'on-primary': '#FFFFFF',
}

const vuetify = createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: INITIAL_THEME,
    themes: {
      mpLight: {
        dark: false,
        colors: { primary: '#8D51F9', background: '#F4F5FA', surface: '#FFFFFF', 'on-surface': '#3A3541', ...SHARED },
        variables: { 'border-color': '#3A3541', 'border-opacity': 0.12, 'medium-emphasis-opacity': 0.68 },
      },
      mpDark: {
        dark: true,
        colors: { primary: '#6E66ED', background: '#0E1116', surface: '#14161F', 'on-surface': '#E7E3FC', ...SHARED },
        variables: { 'border-color': '#E7E3FC', 'border-opacity': 0.12, 'medium-emphasis-opacity': 0.68 },
      },
    },
  },
})

// ── 假数据：形状与 __init__.py 里 /status、/config 的返回一致 ──────────
const pad = value => String(value).padStart(2, '0')
const stamp = daysAgo => {
  const date = new Date(Date.now() - daysAgo * 86400000)
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} 08:10:02`
}

const FAKE_CONFIG = { enabled: true, notify: true, cron: '10 8 * * *', target: '/媒体库/已整理' }
const FAKE_STATUS = {
  enabled: true,
  next_run_time: '9 小时 30 分钟后',
  last_run: stamp(0),
  history: [
    { kind: '执行', time: stamp(0), duration_ms: 8400, handled: 12, skipped: 40, errors: 1 },
    { kind: '执行', time: stamp(1), duration_ms: 420, handled: 3, skipped: 128 },
    { kind: '执行', time: stamp(2), duration_ms: 135000, skipped: 2761 },
  ],
}

// 故意慢一点：好截到「正在读取…」那一态
const LATENCY = 600
const wait = value => new Promise(resolve => setTimeout(() => resolve(value), LATENCY))

const api = path => {
  if (String(path).includes('/config')) return wait(FAKE_CONFIG)
  if (String(path).includes('/status')) return wait(FAKE_STATUS)
  return wait({ success: true, message: '已开始（假的）' })
}

const App = {
  setup() {
    const view = ref(INITIAL_VIEW)
    const saving = ref(false)
    const save = payload => {
      saving.value = true
      console.log('save', payload)
      setTimeout(() => (saving.value = false), 400)
    }
    return () =>
      h('div', { style: 'min-height:100vh;background:rgb(var(--v-theme-background));padding:24px' }, [
        h('div', { style: 'max-width:960px;margin:0 auto;border-radius:12px;overflow:hidden' }, [
          view.value === 'config'
            ? h(Config, {
                api,
                initialConfig: FAKE_CONFIG,
                saving: saving.value,
                onSave: save,
                onSwitch: () => (view.value = 'page'),
                onClose: () => console.log('close'),
              })
            : h(Page, {
                api,
                onSwitch: () => (view.value = 'config'),
                onClose: () => console.log('close'),
                onAction: () => console.log('action'),
              }),
        ]),
      ])
  },
}

createApp(App).use(vuetify).mount('#app')
