/**
 * 独立联调用的宿主替身。MoviePilot 真正的宿主会注入自己的 Vuetify 主题，
 * 这里按 MoviePilot v2 的主题值复刻一份浅色 / 深色，用来验证插件是否真的跟随主题。
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
    // hash 里带 dark 就直接进深色，方便两套主题各截一张对比
    defaultTheme: location.hash.includes('dark') ? 'mpDark' : 'mpLight',
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

// 假宿主接口：让运行台在没有后端的情况下也能走完「加载 -> 有数据」的全过程，
// 用来审查通电动画与对账清单的排版。故意留 600ms 延迟，好看清入场序列。
const LATENCY = 600

const FAKE_STATUS = {
  authenticated: true,
  strm_mappings: 2,
  upload_mappings: 1,
  life_monitor_enabled: true,
  life_monitor_running: true,
  strm_delete_enabled: true,
  strm_delete_watch_running: true,
  pending_sweep: '',
  running: [],
  pending_deletes: [
    {
      id: 'b1',
      mapping: '/影视/电影',
      count: 23,
      total_size: 91_247_483_648,
      created_at: '2026-09-03T21:37:00',
    },
    {
      id: 'b2',
      mapping: '/影视/剧集',
      count: 4,
      total_size: 6_402_247_483,
      created_at: '2026-09-03T22:04:00',
    },
  ],
  recent_uploads: [
    { path: '/m/A.mkv', name: '沙丘 第二部 (2024).mkv', uploaded_at: '2026-09-03 20:11', method: 'instant' },
    { path: '/m/B.mkv', name: '奥本海默 (2023).mkv', uploaded_at: '2026-09-03 19:52', method: 'upload' },
    { path: '/m/C.mkv', name: '疾速追杀4 (2023).mkv', uploaded_at: '2026-09-03 18:30', method: 'instant' },
  ],
  history: [
    { kind: 'strm_sweep', time: '2026-09-03 22:04', duration_ms: 8420, cloud_deleted: 4, scrapes_deleted: 11, cloud_dirs_deleted: 2 },
    { kind: 'strm', time: '2026-09-03 21:37', duration_ms: 24310, added: 18, updated: 3, skipped: 2861 },
    { kind: 'upload', time: '2026-09-03 20:11', duration_ms: 61200, uploaded: 1, instant: 2 },
    { kind: 'checkin', time: '2026-09-03 07:12', duration_ms: 940, continuous_day: 132, points_num: 5 },
  ],
}

const SEP = String.fromCharCode(92)

const FAKE_ITEMS = Array.from({ length: 23 }, (_, index) => ({
  record_key: `k${index}`,
  path: ['D:', 'media', '电影', `示例片名 ${index + 1} (2024)`, `示例片名 ${index + 1} (2024) - 2160p.strm`].join(SEP),
  cloud_path: `/影视/电影/示例片名 ${index + 1} (2024)/示例片名 ${index + 1} (2024) - 2160p.mkv`,
  file_id: `${8000 + index}`,
  name: `示例片名 ${index + 1} (2024) - 2160p.mkv`,
  size: 3_900_000_000 + index * 411_000_000,
}))

const wait = value => new Promise(resolve => setTimeout(() => resolve(value), LATENCY))

const fakeApi = {
  get: (path, options) => {
    if (path.endsWith('/status')) return wait({ ...FAKE_STATUS })
    if (path.endsWith('/strm/sweep/pending')) {
      const batch = FAKE_STATUS.pending_deletes.find(item => item.id === options?.params?.batch_id)
      const items = FAKE_ITEMS.slice(0, batch ? batch.count : 0)
      return wait({ total: items.length, items, total_size: batch?.total_size || 0 })
    }
    if (path.endsWith('/config')) return wait({})
    return wait({})
  },
  post: () => wait({ success: true, message: '已开始' }),
}

const Harness = {
  setup() {
    const theme = useTheme()
    // #page / #config 直接指定视图，方便截图对比
    const view = ref(location.hash.includes('page') ? 'page' : 'config')
    const toggle = () => {
      const next = theme.global.name.value === 'mpLight' ? 'mpDark' : 'mpLight'
      if (typeof theme.change === 'function') theme.change(next)
      else theme.global.name.value = next
    }
    return () =>
      h('div', { style: 'min-height:100vh;background:rgb(var(--v-theme-background));padding:24px' }, [
        h('div', { style: 'display:flex;gap:8px;margin-bottom:16px' }, [
          h(components.VBtn, { size: 'small', onClick: toggle }, () => `主题：${theme.global.name.value}`),
          h(
            components.VBtn,
            { size: 'small', onClick: () => (view.value = view.value === 'config' ? 'page' : 'config') },
            () => `视图：${view.value}`,
          ),
        ]),
        h(
          components.VCard,
          { style: 'max-width:58rem;margin:auto;overflow:hidden' },
          () => [h(view.value === 'config' ? Config : Page, { key: view.value, api: fakeApi })],
        ),
      ])
  },
}

createApp(Harness).use(vuetify).mount('#app')
