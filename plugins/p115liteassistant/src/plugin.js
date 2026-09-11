export const PLUGIN_ID = 'P115LiteAssistant'

// 与后端 notify.py 的 NOTIFY_TYPE_NAMES/SWITCHS_NAMES 一致（均自 MoviePilot MessageType 源派生）。
// 运行时后端 get_config 会注入 notify_types（同步优先），此静态表仅作加载期回退。
export const NOTIFY_TYPES = [
  { title: '资源下载', value: 'Download' },
  { title: '整理入库', value: 'Organize' },
  { title: '订阅', value: 'Subscribe' },
  { title: '站点', value: 'SiteMessage' },
  { title: '媒体服务器', value: 'MediaServer' },
  { title: '手动处理', value: 'Manual' },
  { title: '插件', value: 'Plugin' },
  { title: '智能体', value: 'Agent' },
  { title: '其它', value: 'Other' },
]

export const DEFAULT_CONFIG = {
  enabled: false,
  cookie: '',
  moviepilot_address: '',
  link_redirect_mode: 'cookie',
  strm_incremental: true,
  strm_download_sidecars: false,
  strm_delete_cloud_on_missing: false,
  strm_delete_sweep_cron: '37 */2 * * *',
  strm_delete_watch: false,
  strm_delete_confirm_threshold: 16,
  strm_notify: false,
  strm_notify_type: 'Organize',
  strm_mappings: [],
  upload_mappings: [],
  upload_notify: false,
  upload_notify_type: 'Organize',
  upload_include_sidecars: true,
  upload_generate_strm: false,
  upload_delete_source: false,
  upload_conflict_policy: 'ask',
  upload_media_extensions: '.mp4,.mkv,.ts,.iso,.rmvb,.avi,.mov,.mpeg,.mpg,.wmv,.3gp,.asf,.m4v,.flv,.m2ts,.tp,.f4v',
  upload_sidecar_extensions: '.nfo,.jpg,.jpeg,.png,.webp,.srt,.ass,.ssa,.sup',
  checkin_enabled: false,
  checkin_time_range: '06:00-09:00',
  checkin_notify: false,
  checkin_notify_type: 'Plugin',
  same_playback: false,
  life_monitor_enabled: false,
}

export const NOTIFICATION_EVENTS = [
  { event: 'strm', enabledKey: 'strm_notify', typeKey: 'strm_notify_type' },
  { event: 'upload', enabledKey: 'upload_notify', typeKey: 'upload_notify_type' },
  { event: 'checkin', enabledKey: 'checkin_notify', typeKey: 'checkin_notify_type' },
]

const SAFE_REVERSE_DELETE = Object.freeze({
  strm_delete_cloud_on_missing: true,
  strm_delete_sweep_cron: '37 */2 * * *',
  strm_delete_watch: false,
  strm_delete_confirm_threshold: 16,
})

export function clone(value) {
  return JSON.parse(JSON.stringify(value ?? {}))
}

export function newId() {
  return globalThis.crypto?.randomUUID?.() || `m${Date.now()}${Math.random().toString(16).slice(2, 8)}`
}

export function normalizeConfig(value = {}) {
  const config = { ...clone(DEFAULT_CONFIG), ...clone(value) }
  config.strm_mappings = Array.isArray(config.strm_mappings)
    ? config.strm_mappings.map(mapping => ({ id: newId(), ...mapping }))
    : []
  config.upload_mappings = Array.isArray(config.upload_mappings)
    ? config.upload_mappings.map(mapping => ({ id: newId(), strm_target: '', ...mapping }))
    : []
  return config
}

function present(value) {
  return Boolean(String(value ?? '').trim())
}

export function mappingStats(config = {}) {
  const summarize = (items, usable) => {
    const result = { usable: 0, incomplete: 0, disabled: 0 }
    for (const item of Array.isArray(items) ? items : []) {
      if (!item || typeof item !== 'object' || item.enabled === false) {
        result.disabled += 1
      } else if (usable(item)) {
        result.usable += 1
      } else {
        result.incomplete += 1
      }
    }
    return result
  }
  return {
    strm: summarize(
      config.strm_mappings,
      item => present(item.source_cid) && present(item.target_dir),
    ),
    upload: summarize(
      config.upload_mappings,
      item => present(item.source) && present(item.target)
        && (!config.upload_generate_strm || present(item.strm_target)),
    ),
  }
}

export function deriveAuthState(config = {}, statusState = {}) {
  if (statusState.ready !== true || statusState.failed === true) return 'unknown'
  const data = statusState.data
  if (!data || typeof data !== 'object' || data.error || typeof data.authenticated !== 'boolean') return 'unknown'
  if (data.authenticated) return 'authorized'
  return present(config.cookie) ? 'expired' : 'unauthorized'
}

export function deriveNotificationSettings(config = {}) {
  const events = {}
  for (const meta of NOTIFICATION_EVENTS) {
    events[meta.event] = {
      checked: Boolean(config[meta.enabledKey]),
      type: String(config[meta.typeKey] || 'Plugin'),
    }
  }
  const selected = NOTIFICATION_EVENTS.filter(meta => events[meta.event].checked)
  const compared = selected.length >= 2 ? selected : NOTIFICATION_EVENTS
  const types = new Set(compared.map(meta => events[meta.event].type))
  const mode = types.size <= 1 ? 'unified' : 'separate'
  const preferred = selected[0] || NOTIFICATION_EVENTS[0]
  return {
    enabled: selected.length > 0,
    events,
    mode,
    unifiedType: events[preferred.event].type,
    inconsistent: mode === 'separate',
  }
}

export function applyNotificationSettings(config = {}, uiState = {}) {
  const result = clone(config)
  const master = Boolean(uiState.enabled)
  const mode = uiState.mode === 'separate' ? 'separate' : 'unified'
  for (const meta of NOTIFICATION_EVENTS) {
    const event = uiState.events?.[meta.event] || {}
    const checked = master && Boolean(event.checked)
    result[meta.enabledKey] = checked
    if (mode === 'separate') {
      // 分别设置模式只写「已选事件」的类型；未选事件类型原样保留，
      // 避免本次保存把用户之前单独设置的类型静默覆盖。
      if (checked) {
        result[meta.typeKey] = String(event.type || result[meta.typeKey] || 'Plugin')
      }
    } else if (checked) {
      result[meta.typeKey] = String(uiState.unifiedType || result[meta.typeKey] || 'Plugin')
    }
  }
  return result
}

export function deriveReverseDeleteMode(config = {}) {
  if (!config.strm_delete_cloud_on_missing) return 'off'
  const exact = config.strm_delete_sweep_cron === SAFE_REVERSE_DELETE.strm_delete_sweep_cron
    && config.strm_delete_watch === SAFE_REVERSE_DELETE.strm_delete_watch
    && Number(config.strm_delete_confirm_threshold) === SAFE_REVERSE_DELETE.strm_delete_confirm_threshold
  return exact ? 'safe' : 'custom'
}

export function applyReverseDeleteMode(config = {}, mode = 'off') {
  const result = clone(config)
  if (mode === 'off') {
    result.strm_delete_cloud_on_missing = false
  } else if (mode === 'safe') {
    Object.assign(result, SAFE_REVERSE_DELETE)
  } else {
    result.strm_delete_cloud_on_missing = true
  }
  return result
}

function normalizedPath(value) {
  let text = String(value || '').trim().replace(/\\/g, '/').replace(/\/{2,}/g, '/')
  if (text.length > 1) text = text.replace(/\/+$/, '')
  if (!text || text.split('/').includes('..')) return null
  const windows = /^[A-Za-z]:\//.test(text)
  if (!windows && !text.startsWith('/')) return null
  if (windows) text = text.toLowerCase()
  const root = windows ? text.slice(0, 2) : '/'
  const rest = windows ? text.slice(2) : text
  const segments = rest.split('/').filter(Boolean)
  return { root, segments }
}

function pathRelation(left, right) {
  const a = normalizedPath(left)
  const b = normalizedPath(right)
  if (!a || !b) return 'invalid'
  if (a.root !== b.root) return 'separate'
  const shorter = a.segments.length <= b.segments.length ? a : b
  const longer = shorter === a ? b : a
  return shorter.segments.every((part, index) => part === longer.segments[index]) ? 'overlap' : 'separate'
}

function validTimeWindow(value) {
  const match = String(value || '').trim().match(/^(\d{2}):(\d{2})-(\d{2}):(\d{2})$/)
  if (!match) return false
  const [, h1, m1, h2, m2] = match.map(Number)
  return h1 < 24 && h2 < 24 && m1 < 60 && m2 < 60
}

export function validateConfig(config = {}) {
  const errors = []
  const add = (section, field, message, extra = {}) => errors.push({ section, field, message, ...extra })
  const strmMappings = Array.isArray(config.strm_mappings) ? config.strm_mappings : []
  const uploadMappings = Array.isArray(config.upload_mappings) ? config.upload_mappings : []

  strmMappings.forEach((mapping, index) => {
    if (!mapping || mapping.enabled === false) return
    if (!present(mapping.source_cid)) add('strm', `strm-${index}`, `STRM 通道 ${index + 1} 还没有选择 115 源目录。`, { mappingIndex: index })
    if (!present(mapping.target_dir)) add('strm', `strm-${index}`, `STRM 通道 ${index + 1} 还没有选择本地输出目录。`, { mappingIndex: index })
  })

  uploadMappings.forEach((mapping, index) => {
    if (!mapping || mapping.enabled === false) return
    if (!present(mapping.source)) add('upload', `upload-${index}`, `上传通道 ${index + 1} 还没有选择本地源目录。`, { mappingIndex: index })
    if (!present(mapping.target)) add('upload', `upload-${index}`, `上传通道 ${index + 1} 还没有选择 115 目标目录。`, { mappingIndex: index })
    if (config.upload_generate_strm && !present(mapping.strm_target)) {
      add('upload', `upload-${index}`, `上传通道 ${index + 1} 开启了生成 STRM，还没有选择 STRM 输出目录。`, { mappingIndex: index })
    }
  })

  const stats = mappingStats(config)
  const enabledUploads = uploadMappings.filter(item => item && item.enabled !== false)
  const needsAddress = stats.strm.usable > 0 || (config.upload_generate_strm && enabledUploads.length > 0)
  if (needsAddress) {
    const address = String(config.moviepilot_address || '').trim()
    if (!address) {
      add('start', 'moviepilot_address', '当前会生成 STRM，请填写播放设备能访问的 MoviePilot 地址。')
    } else {
      try {
        const parsed = new URL(address)
        if (!['http:', 'https:'].includes(parsed.protocol) || !parsed.host) throw new Error('invalid')
      } catch {
        add('start', 'moviepilot_address', 'MoviePilot 访问地址必须是完整的 http 或 https 地址。')
      }
    }
  }

  const enabledWithSource = uploadMappings
    .map((mapping, index) => ({ mapping, index }))
    .filter(item => item.mapping && item.mapping.enabled !== false && present(item.mapping.source))
  const invalidSources = new Set()
  for (const item of enabledWithSource) {
    if (normalizedPath(item.mapping.source)) continue
    invalidSources.add(item.index)
    add('upload', `upload-${item.index}`, `上传通道 ${item.index + 1} 的源目录必须是绝对路径，且不能包含 ..。`, { mappingIndex: item.index })
  }
  for (let left = 0; left < enabledWithSource.length; left += 1) {
    for (let right = left + 1; right < enabledWithSource.length; right += 1) {
      const a = enabledWithSource[left]
      const b = enabledWithSource[right]
      if (invalidSources.has(a.index) || invalidSources.has(b.index)) continue
      if (pathRelation(a.mapping.source, b.mapping.source) !== 'overlap') continue
      add('upload', `upload-${a.index}`, `上传通道 ${a.index + 1} 与通道 ${b.index + 1} 的源目录相同或互为父子目录。`, { mappingIndex: a.index })
      add('upload', `upload-${b.index}`, `上传通道 ${b.index + 1} 与通道 ${a.index + 1} 的源目录相同或互为父子目录。`, { mappingIndex: b.index })
    }
  }

  if (!validTimeWindow(config.checkin_time_range)) {
    add('automation', 'checkin_time_range', '签到时间窗请按 HH:mm-HH:mm 填写，并使用有效的时分。')
  }
  const cron = String(config.strm_delete_sweep_cron || '').trim()
  if (config.strm_delete_cloud_on_missing && cron && cron.split(/\s+/).length !== 5) {
    add('strm', 'reverse_cron', '反向清理巡检周期需要填写五段 cron 表达式。', { advanced: true })
  }
  if (config.upload_delete_source && (enabledUploads.length === 0 || stats.upload.incomplete > 0)) {
    add('upload', 'upload_delete_source', '开启删源前，请先补全并开启至少一条上传通道。')
  }
  if (config.life_monitor_enabled && stats.strm.usable === 0) {
    add('automation', 'life_monitor_enabled', '网盘变化自动同步需要至少一条可用的 STRM 映射。')
  }
  return errors
}

const WRITABLE_CONFIG_KEYS = Object.freeze(Object.keys(DEFAULT_CONFIG))

export function toWritableConfig(config = {}) {
  const result = {}
  for (const key of WRITABLE_CONFIG_KEYS) {
    if (Object.prototype.hasOwnProperty.call(config, key)) result[key] = clone(config[key])
  }
  return result
}

function unwrap(response) {
  if (response && typeof response === 'object' && response.data && !Object.prototype.hasOwnProperty.call(response, 'success')) {
    return response.data
  }
  return response || {}
}

export async function pluginGet(api, path, params) {
  if (!api?.get) throw new Error('MoviePilot 接口不可用，请重新打开插件')
  const response = unwrap(await api.get(`plugin/${PLUGIN_ID}${path}`, { params }))
  return Object.prototype.hasOwnProperty.call(response, 'data') ? response.data : response
}

export async function pluginPost(api, path, payload = {}) {
  if (!api?.post) throw new Error('MoviePilot 接口不可用，请重新打开插件')
  const response = unwrap(await api.post(`plugin/${PLUGIN_ID}${path}`, payload))
  return {
    success: response.success !== false,
    message: response.message || '',
    data: Object.prototype.hasOwnProperty.call(response, 'data') ? response.data : response,
  }
}

/**
 * MoviePilot 通过 provide('moviepilot:toast') 把宿主的消息条交给远程组件，
 * 这样插件不会再挂载自己的一套通知容器。宿主缺席时（独立联调）退回本地条。
 */
export function useHostNotice(injected, local) {
  const speak = (text, kind = 'info') => {
    const message = String(text || '').trim()
    if (!message) return
    const host = injected?.value ?? injected
    const method = host?.[kind] || host?.info
    if (typeof method === 'function') {
      method.call(host, message)
      return
    }
    if (typeof host === 'function') {
      host(message, kind)
      return
    }
    local(message, kind)
  }
  return {
    info: text => speak(text, 'info'),
    success: text => speak(text, 'success'),
    error: text => speak(text, 'error'),
    warning: text => speak(text, 'warning'),
    say: speak,
  }
}
