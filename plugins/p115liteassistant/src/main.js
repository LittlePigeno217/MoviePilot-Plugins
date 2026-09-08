/**
 * 独立联调用的宿主替身。MoviePilot 真正的宿主会注入自己的 Vuetify 主题，
 * 这里按 MoviePilot v2 的主题值复刻一份浅色 / 深色，用来验证插件是否真的跟随主题。
 */
import { createApp, h, ref } from 'vue'
import { createVuetify, useTheme } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import 'vuetify/styles'
import AppPage from './components/AppPage.vue'
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
  pending_sweep: '全部记录',
  running: ['strm'],
  tasks: [
    { kind: 'strm', label: '生成 STRM', elapsed_ms: 134000, holds_cloud_lock: true },
  ],
  pending_deletes: [
    {
      id: 'b1',
      mapping: '/影视/电影',
      count: 2314,
      total_size: 91_247_483_648,
      items_truncated: true,
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
    { path: '/m/A.mkv', name: '沙丘 第二部 (2024).mkv', target: '/影视/电影/沙丘 第二部 (2024)', uploaded_at: '2026-09-03 20:11', method: 'instant' },
    { path: '/m/B.mkv', name: '奥本海默 (2023).mkv', target: '/影视/电影/奥本海默 (2023)', uploaded_at: '2026-09-03 19:52', method: 'upload' },
    { path: '/m/C.mkv', name: '疾速追杀4 (2023).mkv', target: '/影视/电影/疾速追杀4 (2023)', uploaded_at: '2026-09-03 18:30', method: 'instant' },
    { path: '/m/D.mkv', name: '沙丘 (2021).mkv', target: '/影视/电影/沙丘 (2021)', uploaded_at: '2026-09-03 17:44', method: 'instant' },
    { path: '/m/E.mkv', name: '繁花 S01E12.mkv', target: '/影视/剧集/繁花 (2024)/Season 01', uploaded_at: '2026-09-03 16:20', method: 'upload' },
    { path: '/m/F.mkv', name: '繁花 S01E11.mkv', target: '/影视/剧集/繁花 (2024)/Season 01', uploaded_at: '2026-09-03 16:18', method: 'upload' },
    { path: '/m/G.mkv', name: '三体 S01E30.mkv', target: '/影视/剧集/三体 (2023)/Season 01', uploaded_at: '2026-09-02 23:02', method: 'instant' },
    { path: '/m/H.mkv', name: '流浪地球2 (2023).mkv', target: '/影视/电影/流浪地球2 (2023)', uploaded_at: '2026-09-02 21:30', method: 'instant' },
  ],
  history: [
    { kind: 'strm_sweep', time: '2026-09-03 22:04', duration_ms: 8420, cloud_deleted: 4, scrapes_deleted: 11, cloud_dirs_deleted: 2 },
    { kind: 'strm', time: '2026-09-03 21:37', duration_ms: 24310, added: 18, updated: 3, skipped: 2861 },
    { kind: 'upload', time: '2026-09-03 20:11', duration_ms: 61200, uploaded: 1, instant: 2 },
    { kind: 'checkin', time: '2026-09-03 07:12', duration_ms: 940, continuous_day: 132, points_num: 5 },
    { kind: 'strm_sweep', time: '2026-09-02 20:04', duration_ms: 3100, pending: 23, already_gone: 2 },
    { kind: 'strm', time: '2026-09-02 19:37', duration_ms: 15400, skipped: 2843 },
    { kind: 'upload', time: '2026-09-02 18:02', duration_ms: 210400, uploaded: 6, instant: 1, errors: 1 },
    { kind: 'checkin', time: '2026-09-02 07:05', duration_ms: 1120, already: true, continuous_day: 131 },
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

const FAKE_LOG = [
  '【INFO】2026-09-05 19:11:07,480 - strm_watch.py - 【STRM监听】已开始监听 1 个 STRM 输出目录，删除事件安静 30 秒后上报反向删除',
  '【INFO】2026-09-05 19:11:07,481 - life_monitor.py - 【115生活监控】监控线程已启动',
  '【INFO】2026-09-05 19:12:44,102 - api.py - 【STRM同步】开始执行，模式：增量，有效映射：2',
  '【INFO】2026-09-05 19:12:44,310 - strm.py - 【STRM同步】开始处理映射：/影视/电影 -> /strm/电影',
  '【WARNING】2026-09-05 19:13:02,884 - client.py - 【115接口】列目录被限流，等 2.0 秒后重试（第 1 次）',
  '【INFO】2026-09-05 19:13:20,551 - strm.py - 【STRM同步】/影视/电影 完成：新增 18，更新 3，跳过 2861',
  '【INFO】2026-09-05 19:13:20,552 - strm.py - 【STRM同步】开始处理映射：/影视/剧集 -> /strm/剧集',
  '【ERROR】2026-09-05 19:13:41,220 - strm.py - 【STRM同步】写入失败，保留旧文件：/strm/剧集/某剧 (2024)/S01E07.strm',
  '【INFO】2026-09-05 19:13:58,004 - api.py - 【STRM反向删除】任务已排队，等当前任务结束（全部记录）',
]

const FAKE_CLOUD_DIRS = [
  { name: '电影', cid: '31' },
  { name: '剧集', cid: '32' },
  { name: '动漫', cid: '33' },
  { name: '纪录片', cid: '34' },
]

const FAKE_LOCAL_DIRS = [
  { name: 'strm', path: 'strm' },
  { name: 'watch', path: 'watch' },
  { name: 'config', path: 'config' },
]

const FAKE_DISK_ITEMS = [
  { id: '31', name: '电影', is_dir: true, size: 0, mtime: 1789000000, pickcode: '' },
  { id: '32', name: '剧集', is_dir: true, size: 0, mtime: 1788900000, pickcode: '' },
  { id: '900001', name: '沙丘 第二部 (2024) - 2160p.mkv', is_dir: false, size: 48_318_382_080, mtime: 1788800000, pickcode: 'abc123' },
  { id: '900002', name: '沙丘 第二部 (2024).nfo', is_dir: false, size: 3182, mtime: 1788800100, pickcode: 'abc124' },
  { id: '900003', name: '奥本海默 (2023) - 2160p.mkv', is_dir: false, size: 61_204_398_080, mtime: 1788700000, pickcode: 'abc125' },
]

const FAKE_AUDIT = {
  records: 2861,
  roots: ['/strm/电影', '/strm/剧集'],
  groups: [
    {
      key: 'duplicate',
      title: '重复生成',
      hint: '同一个 115 文件生成了多份 STRM，媒体库里会出现重复条目。',
      count: 2,
      rows: [
        { token: 'abc123', count: 3, cloud_path: '/影视/电影/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.mkv',
          paths: ['/strm/电影/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.strm', '/strm/电影/沙丘2/沙丘 第二部.strm', '/strm/电影/待整理/沙丘 第二部 (2024) - 2160p.strm'] },
        { token: 'abc999', count: 2, cloud_path: '/影视/电影/奥本海默 (2023)/奥本海默 (2023) - 2160p.mkv',
          paths: ['/strm/电影/奥本海默 (2023)/奥本海默 (2023) - 2160p.strm', '/strm/电影/待整理/奥本海默.strm'] },
      ],
    },
    {
      key: 'incomplete',
      title: '集号不连续',
      hint: '同一季里集号缺号。要么没刮到，要么网盘上真缺这几集。',
      count: 1,
      rows: [{ folder: '/strm/剧集/某剧 (2024)/Season 01', season: 1, have: 10, span: '1-12', missing: [7, 11], missing_count: 2 }],
    },
    {
      key: 'untracked',
      title: '记录里没有的 STRM',
      hint: '输出目录里有、记录里没有。反向删除看不见它们，本地删了不会联动网盘。',
      count: 3,
      rows: [
        { path: '/strm/电影/手工放的/某片.strm', size: 78, root: '/strm/电影' },
        { path: '/strm/电影/一次性任务/另一片.strm', size: 81, root: '/strm/电影' },
        { path: '/strm/剧集/改过目录/残留.strm', size: 74, root: '/strm/剧集' },
      ],
    },
    {
      key: 'unlinkable',
      title: '取不到链',
      hint: '记录里既没有 pickcode 也没有 file_id，这条 STRM 的 302 一定失败。',
      count: 1,
      rows: [{ path: '/strm/电影/老记录/早年入库.strm', cloud_path: '/影视/电影/早年入库' }],
    },
  ],
}

const FAKE_LEDGER = {
  records: 990,
  roots: ['/strm/电影', '/strm/剧集'],
  has_seeding: true,
  seeding_note: '',
  seeds: 69,
  seeds_matched: 60,
  has_cloud_check: true,
  cloud_unchecked: 2,
  cloud_budget: 60,
  cloud_cooldown: 0,
  cloud_note: '还有 2 行没核对过网盘',
  summary: { source_left: 48_318_382_080, cloud_gone: 1, untracked: 1 },
  channels: [
    { id: 'c1', label: 'STRM 通道 1' },
    { id: 'u1', label: '上传通道 1' },
  ],
  rows: [
    {
      id: 'tv|陀枪师姐|2004|4', kind: 'tv', title: '陀枪师姐', year: '2004', season: 4,
      channel: 'STRM 通道 1', channel_id: 'c1', in_library: 'yes', files: 39, size: 62_000_000_000,
      folder: '/影视/剧集/陀枪师姐/Season 04', cloud_folder: '/影视/剧集/陀枪师姐/Season 04', source_folder: '',
      episodes: [], missing: [19], span: '1-40', strm_gone: 0, flags: ['season_gap'],
      strm_paths: new Array(39).fill('/strm/剧集/陀枪师姐/Season 04/x.strm'),
      source_paths: [], file_ids: new Array(39).fill('9001'), pickcodes: [],
      upload_target: '', source_uploaded: 0, source_pending: 0,
      seeds: 1, seeding: true, cloud_state: 'yes', cloud_checked_at: 1788800000, library_at: 1_600_000_000,
    },
    {
      id: 'movie|沙丘 第二部|2024|', kind: 'movie', title: '沙丘 第二部', year: '2024', season: null,
      channel: 'STRM 通道 1', channel_id: 'c1', in_library: 'yes', files: 3, size: 48_318_382_080,
      folder: '/影视/电影/沙丘 第二部 (2024)', cloud_folder: '/影视/电影/沙丘 第二部 (2024)',
      source_folder: '/watch/inbox/沙丘 第二部 (2024)',
      episodes: [], missing: [], span: '', strm_gone: 0, flags: ['source_left'],
      strm_paths: ['/strm/电影/沙丘 第二部 (2024)/a.strm', '/strm/电影/沙丘 第二部 (2024)/b.strm', '/strm/电影/沙丘 第二部 (2024)/c.strm'],
      source_paths: ['/watch/inbox/沙丘 第二部 (2024)/沙丘 第二部 (2024) - 2160p.mkv'],
      file_ids: ['900001', '900002', '900003'], pickcodes: ['abc123'],
      upload_target: '/影视/电影/沙丘 第二部 (2024)', source_uploaded: 1, source_pending: 0,
      seeds: 1, seeding: true, cloud_state: 'no', cloud_checked_at: 1788900000, source_size: 48_318_382_080, library_at: 1_710_000_000,
    },
    {
      id: 'movie|奥本海默|2023|', kind: 'movie', title: '奥本海默', year: '2023', season: null,
      channel: 'STRM 通道 1', channel_id: 'c1', in_library: 'yes', files: 1, size: 61_204_398_080,
      folder: '/影视/电影/奥本海默 (2023)', cloud_folder: '/影视/电影/奥本海默 (2023)', source_folder: '',
      episodes: [], missing: [], span: '', strm_gone: 1, flags: ['strm_gone', 'duplicate'],
      strm_paths: ['/strm/电影/奥本海默 (2023)/a.strm'],
      source_paths: [], file_ids: ['900004'], pickcodes: ['abc125'],
      upload_target: '', source_uploaded: 0, source_pending: 0, library_at: 1_680_000_000,
    },
    {
      id: 'tv|某剧|2024|1', kind: 'tv', title: '某剧', year: '2024', season: 1,
      channel: '上传通道 1', channel_id: 'u1', in_library: 'no', files: 12, size: 86_000_000_000,
      folder: '/watch/剧集/某剧 (2024)/Season 01', cloud_folder: '', source_folder: '/watch/剧集/某剧 (2024)/Season 01',
      episodes: [], missing: [], span: '1-12', strm_gone: 0, flags: [],
      strm_paths: [], source_paths: new Array(12).fill('/watch/剧集/某剧 (2024)/Season 01/e01.mkv'),
      file_ids: [], pickcodes: [],
      upload_target: '/影视/剧集/某剧 (2024)/Season 01', source_uploaded: 0, source_pending: 12,
      seeds: 0, seeding: false,
    },
    {
      id: 'movie|手工放的||', kind: 'movie', title: '手工放的', year: '', season: null,
      channel: '记录缺失', channel_id: 'untracked', in_library: 'unknown', files: 1, size: 78,
      folder: '/strm/电影/手工放的', cloud_folder: '', source_folder: '',
      episodes: [], missing: [], span: '', strm_gone: 0, flags: ['untracked'],
      strm_paths: ['/strm/电影/手工放的/某片.strm'], source_paths: [], file_ids: [], pickcodes: [],
      upload_target: '', source_uploaded: 0, source_pending: 0,
    },
  ],
}

const wait = value => new Promise(resolve => setTimeout(() => resolve(value), LATENCY))

const fakeApi = {
  get: (path, options) => {
    if (path.endsWith('/status')) return wait({ ...FAKE_STATUS })
    if (path.endsWith('/strm/sweep/pending')) {
      const batch = FAKE_STATUS.pending_deletes.find(item => item.id === options?.params?.batch_id)
      const items = FAKE_ITEMS.slice(0, batch ? batch.count : 0)
      return wait({ total: items.length, items, total_size: batch?.total_size || 0 })
    }
    if (path.endsWith('/logs/tail')) {
      // 真后端按字节偏移给增量，这里简化成「第一次给一整屏，之后没有新行」
      const start = Number(options?.params?.offset || 0)
      return wait({ lines: start ? [] : FAKE_LOG, next_offset: 1, size: 99999 })
    }
    if (path.endsWith('/browse-115')) return wait({ cid: options?.params?.cid || '0', items: FAKE_CLOUD_DIRS })
    if (path.endsWith('/browse-local')) {
      return wait({ base: '/', roots: [{ name: '/', path: '/' }], current: options?.params?.path || '', items: FAKE_LOCAL_DIRS })
    }
    if (path.endsWith('/ledger')) return wait({ success: true, message: '', data: FAKE_LEDGER })
    if (path.endsWith('/library/audit')) return wait({ success: true, message: '', data: FAKE_AUDIT })
    if (path.endsWith('/disk/list')) return wait({ success: true, message: '', data: { cid: options?.params?.cid || '0', items: FAKE_DISK_ITEMS } })
    if (path.endsWith('/config')) return wait({})
    return wait({})
  },
  post: () => wait({ success: true, message: '已开始' }),
}

const Harness = {
  setup() {
    const theme = useTheme()
    // #app / #page / #config 直接指定视图，方便截图对比。
    // app = 侧栏全页入口（AppPage 自带纸面与外边距），page / config = 插件列表里的卡片。
    const view = ref(
      location.hash.includes('app') ? 'app' : location.hash.includes('page') ? 'page' : 'config',
    )
    const VIEWS = ['app', 'page', 'config']
    const toggle = () => {
      const next = theme.global.name.value === 'mpLight' ? 'mpDark' : 'mpLight'
      if (typeof theme.change === 'function') theme.change(next)
      else theme.global.name.value = next
    }
    return () =>
      h('div', { style: 'min-height:100vh;background:rgb(var(--v-theme-background));padding:24px 0 0' }, [
        h('div', { style: 'display:flex;gap:8px;margin:0 24px 16px' }, [
          h(components.VBtn, { size: 'small', onClick: toggle }, () => `主题：${theme.global.name.value}`),
          h(
            components.VBtn,
            {
              size: 'small',
              onClick: () => {
                view.value = VIEWS[(VIEWS.indexOf(view.value) + 1) % VIEWS.length]
              },
            },
            () => `视图：${view.value}`,
          ),
        ]),
        view.value === 'app'
          ? h(AppPage, { key: 'app', api: fakeApi })
          : h(
              components.VCard,
              { style: 'max-width:58rem;margin:0 auto 24px;overflow:hidden' },
              () => [h(view.value === 'config' ? Config : Page, { key: view.value, api: fakeApi })],
            ),
      ])
  },
}

createApp(Harness).use(vuetify).mount('#app')
